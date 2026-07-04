"""Web interface — free public song/speech transcription.

Spec: specs/song-transcriber-web.md. Designed for a small free CPU host
(Hugging Face Spaces, 2 vCPU): jobs run strictly one at a time through a
single worker thread that shares one Engine, so the model stays loaded
between jobs. Uploaded files are deleted right after processing; outputs
are swept after a retention window. Nothing is stored or logged.
"""

import os
import queue
import tempfile
import threading
import time
from uuid import uuid4

from flask import (Flask, jsonify, render_template, request,
                   send_from_directory)
from werkzeug.utils import secure_filename

from . import engine as engine_mod


def _env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


# Limits are spec §Web-specific limits; every one is env-overridable.
MAX_MB = _env_int("SHABD_WEB_MAX_MB", 50)
MAX_MINUTES = _env_int("SHABD_WEB_MAX_MINUTES", 15)
MAX_QUEUE = _env_int("SHABD_WEB_MAX_QUEUE", 10)
RETENTION_MINUTES = _env_int("SHABD_WEB_RETENTION_MINUTES", 120)

_tier_env = os.environ.get("SHABD_WEB_TIERS", "fast,balanced")
ALLOWED_TIERS = [t.strip() for t in _tier_env.split(",")
                 if t.strip() in engine_mod.MODEL_TIERS] or ["fast"]
DEFAULT_TIER = ALLOWED_TIERS[0]

ALLOWED_FORMATS = ("txt", "srt", "vtt")
ALLOWED_EXTENSIONS = {ext.lstrip(".").lower()
                      for ext in engine_mod.MEDIA_EXTENSIONS}

UPLOAD_DIR = os.path.join(tempfile.gettempdir(), "shabd_web")
os.makedirs(UPLOAD_DIR, exist_ok=True)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"))
app.config["MAX_CONTENT_LENGTH"] = MAX_MB * 1024 * 1024

_jobs = {}
_jobs_lock = threading.Lock()
_job_queue = queue.Queue()
_engine = engine_mod.Engine()
_worker_started = threading.Event()
_seq_counter = {"n": 0}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def probe_duration_seconds(path):
    """Best-effort media duration from the container header.

    Returns None when unknown/unreadable — the length limit then can't be
    pre-checked and the engine's own decode is the final arbiter.
    """
    try:
        import av
        with av.open(path) as container:
            if container.duration:
                return container.duration / 1_000_000.0
    except Exception:
        return None
    return None


def _set_job(job_id, **data):
    with _jobs_lock:
        _jobs.setdefault(job_id, {}).update(data)


def _get_job(job_id):
    with _jobs_lock:
        entry = _jobs.get(job_id)
        if entry is None:
            return None
        snapshot = dict(entry)
    if snapshot.get("status") == "queued":
        snapshot["position"] = _queue_position(job_id)
    return snapshot


def _queue_position(job_id):
    """1 = next in line. Counts queued jobs submitted before this one."""
    with _jobs_lock:
        me = _jobs.get(job_id)
        if me is None:
            return None
        ahead = sum(1 for j in _jobs.values()
                    if j.get("status") == "queued" and j["seq"] < me["seq"])
    return ahead + 1


def _queued_count():
    with _jobs_lock:
        return sum(1 for j in _jobs.values() if j.get("status") == "queued")


def sweep_old_files(now=None):
    """Delete outputs/uploads and job records past the retention window."""
    now = now if now is not None else time.time()
    cutoff = now - RETENTION_MINUTES * 60
    for name in os.listdir(UPLOAD_DIR):
        path = os.path.join(UPLOAD_DIR, name)
        try:
            if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                os.remove(path)
        except OSError:
            pass
    with _jobs_lock:
        stale = [jid for jid, j in _jobs.items()
                 if j.get("status") in ("done", "error")
                 and j.get("finished", now) < cutoff]
        for jid in stale:
            del _jobs[jid]


def _run_job(job_id):
    job = _get_job(job_id)
    input_path = job["input_path"]
    try:
        _set_job(job_id, status="running", progress=0, message="Starting…")

        def on_progress(frac):
            _set_job(job_id, progress=int(frac * 100),
                     message="Transcribing… %d%%" % int(frac * 100))

        def on_status(message):
            _set_job(job_id, message=message)

        result = _engine.transcribe_file(
            input_path,
            tier_or_model=job["tier"],
            language=job["language"],
            task=job["task"],
            vocab=job["vocab"],
            device="cpu",
            compute_type="int8",
            on_progress=on_progress,
            on_status=on_status,
        )
        if MAX_MINUTES and result["duration"] > MAX_MINUTES * 60:
            raise ValueError(
                "This recording is %.1f minutes long; the free service accepts "
                "up to %d minutes." % (result["duration"] / 60.0, MAX_MINUTES))

        out_paths = engine_mod.write_outputs(
            result, input_path, [job["format"]],
            output_dir=UPLOAD_DIR, overwrite=True)
        out_path = out_paths[0]
        encoding = "utf-8-sig" if job["format"] in ("srt", "txt") else "utf-8"
        with open(out_path, encoding=encoding) as f:
            output_text = f.read()

        _set_job(
            job_id,
            status="done", progress=100, message="Completed",
            finished=time.time(),
            download_url="/download/%s?name=%s" % (
                os.path.basename(out_path), job["nice_name"]),
            output_text=output_text,
            format=job["format"],
            language=result["language"],
            confidence=int(result["language_probability"] * 100),
        )
    except Exception as exc:
        _set_job(job_id, status="error", finished=time.time(),
                 message="Sorry, this file could not be transcribed. (%s)"
                         % exc.__class__.__name__,
                 detail=str(exc))
    finally:
        try:
            os.remove(input_path)
        except OSError:
            pass


def _worker_loop():
    while True:
        job_id = _job_queue.get()
        try:
            _run_job(job_id)
        finally:
            sweep_old_files()
            _job_queue.task_done()


def _ensure_worker():
    if not _worker_started.is_set():
        with _jobs_lock:
            if not _worker_started.is_set():
                threading.Thread(target=_worker_loop, daemon=True,
                                 name="shabd-web-worker").start()
                _worker_started.set()


def warm_up_default_model():
    """Pre-load the default tier's model so visitor #1 doesn't wait for it."""
    def _warm():
        try:
            _engine.load_model(engine_mod.tier_to_model(DEFAULT_TIER),
                               device="cpu", compute_type="int8")
        except Exception:
            pass  # first real job will retry and surface any problem
    threading.Thread(target=_warm, daemon=True, name="shabd-web-warmup").start()


@app.errorhandler(413)
def too_large(_e):
    return jsonify(success=False,
                   error="File is too big — the free service accepts up to "
                         "%d MB." % MAX_MB), 413


@app.route("/", methods=["GET"])
def index():
    tiers = [(t, engine_mod.MODEL_TIERS[t][1]) for t in ALLOWED_TIERS]
    return render_template("index.html", tiers=tiers,
                           default_tier=DEFAULT_TIER,
                           languages=engine_mod.COMMON_LANGUAGES,
                           max_mb=MAX_MB, max_minutes=MAX_MINUTES,
                           retention_minutes=RETENTION_MINUTES)


@app.route("/health")
def health():
    return jsonify(status="ok", queued=_queued_count())


@app.route("/submit", methods=["POST"])
def submit():
    media = request.files.get("media")
    if not media or not media.filename:
        return jsonify(success=False, error="Please choose a file first."), 400
    if not allowed_file(media.filename):
        return jsonify(success=False,
                       error="Unsupported file type. Please upload audio or "
                             "video (mp3, wav, m4a, mp4…)."), 400
    if _queued_count() >= MAX_QUEUE:
        return jsonify(success=False,
                       error="The free queue is full right now — please try "
                             "again in a few minutes."), 429

    filename = secure_filename(media.filename) or "upload"
    input_path = os.path.join(UPLOAD_DIR, "%s_%s" % (uuid4().hex, filename))
    media.save(input_path)

    duration = probe_duration_seconds(input_path)
    if duration is not None and MAX_MINUTES and duration > MAX_MINUTES * 60:
        try:
            os.remove(input_path)
        except OSError:
            pass
        return jsonify(success=False,
                       error="This recording is %.1f minutes long; the free "
                             "service accepts up to %d minutes."
                             % (duration / 60.0, MAX_MINUTES)), 400

    tier = request.form.get("tier", DEFAULT_TIER)
    if tier not in ALLOWED_TIERS:
        tier = DEFAULT_TIER
    fmt = request.form.get("format", ALLOWED_FORMATS[0])
    if fmt not in ALLOWED_FORMATS:
        fmt = ALLOWED_FORMATS[0]
    language = (request.form.get("language", "auto").strip() or "auto")[:16]
    task = request.form.get("task", "transcribe")
    if task not in ("transcribe", "translate"):
        task = "transcribe"
    vocab = request.form.get("vocab", "").strip()[:500] or None

    job_id = uuid4().hex
    with _jobs_lock:
        _seq_counter["n"] += 1
        seq = _seq_counter["n"]
    _set_job(job_id, status="queued", progress=0, seq=seq,
             message="Waiting in line…", created=time.time(),
             input_name=media.filename, input_path=input_path,
             nice_name=os.path.splitext(filename)[0] or "transcript",
             tier=tier, language=language, task=task, format=fmt, vocab=vocab)
    _ensure_worker()
    _job_queue.put(job_id)
    return jsonify(success=True, job_id=job_id)


@app.route("/status/<job_id>")
def status(job_id):
    job = _get_job(job_id)
    if job is None:
        return jsonify(success=False, error="Unknown job ID."), 404
    public = {k: job.get(k) for k in
              ("status", "progress", "message", "position", "input_name",
               "download_url", "output_text", "format", "language",
               "confidence") if job.get(k) is not None}
    if job.get("status") == "queued" and public.get("position"):
        public["message"] = "Waiting — you are #%d in line" % public["position"]
    return jsonify(success=True, **public)


@app.route("/download/<filename>")
def download_file(filename):
    nice = secure_filename(request.args.get("name", "")) or "transcript"
    ext = os.path.splitext(filename)[1]
    return send_from_directory(UPLOAD_DIR, filename, as_attachment=True,
                               download_name=nice + ext)


def main():
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 7860))
    if os.environ.get("SHABD_WEB_WARMUP") == "1":
        warm_up_default_model()
    _ensure_worker()
    try:
        from waitress import serve
        print("Shabd web listening on http://%s:%d" % (host, port))
        serve(app, host=host, port=port, threads=8)
    except ImportError:
        app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
