import os
import tempfile
import threading
from uuid import uuid4

from flask import (Flask, flash, jsonify, redirect, render_template, request,
                   send_from_directory, url_for)
from werkzeug.utils import secure_filename

from . import engine as engine_mod

UPLOAD_DIR = os.path.join(tempfile.gettempdir(), "shabd_web")
os.makedirs(UPLOAD_DIR, exist_ok=True)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR)
app.secret_key = os.environ.get("SHABD_SECRET_KEY", "shabd-web-secret-key")
app.config["MAX_CONTENT_LENGTH"] = 600 * 1024 * 1024

ALLOWED_EXTENSIONS = {ext.lstrip(".").lower() for ext in engine_mod.MEDIA_EXTENSIONS}

job_status = {}
job_lock = threading.Lock()


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_upload(file_storage):
    filename = secure_filename(file_storage.filename) or "upload"
    dest_name = f"{uuid4().hex}_{filename}"
    dest_path = os.path.join(UPLOAD_DIR, dest_name)
    file_storage.save(dest_path)
    return dest_path, dest_name


def _set_job_status(job_id, **data):
    with job_lock:
        entry = job_status.setdefault(job_id, {})
        entry.update(data)


def _get_job_status(job_id):
    with job_lock:
        return dict(job_status.get(job_id, {}))


def _process_job(job_id, input_path, input_name, tier, language, task, fmt, vocab):
    _set_job_status(job_id, status="running", progress=0, message="Queued", input_name=input_name)
    try:
        engine = engine_mod.Engine()

        def on_progress(frac):
            _set_job_status(job_id, progress=int(frac * 100), message=f"Transcribing {int(frac * 100)}%")

        def on_segment(text, start, end):
            snippet = text[:120].replace("\n", " ")
            _set_job_status(job_id, message=f"Segment: {snippet}")

        def on_status(message):
            _set_job_status(job_id, message=message)

        result = engine.transcribe_file(
            input_path,
            tier_or_model=tier,
            language=language,
            task=task,
            vocab=vocab,
            device="cpu",
            compute_type="int8",
            on_progress=on_progress,
            on_segment=on_segment,
            on_status=on_status,
        )
        out_paths = engine_mod.write_outputs(
            result,
            input_path,
            [fmt],
            output_dir=UPLOAD_DIR,
            overwrite=True,
        )
        out_path = out_paths[0]
        with open(out_path, encoding="utf-8-sig" if fmt in ("srt", "txt") else "utf-8") as f:
            output_text = f.read()

        with app.app_context():
            download_url = url_for("download_file", filename=os.path.basename(out_path))

        _set_job_status(
            job_id,
            status="done",
            progress=100,
            message="Completed",
            download_url=download_url,
            output_text=output_text,
            format=fmt,
            language=result["language"],
            confidence=int(result["language_probability"] * 100),
        )
    except Exception as exc:
        _set_job_status(job_id, status="error", message=str(exc))


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/submit", methods=["POST"])
def submit():
    media = request.files.get("media")
    if not media or media.filename == "":
        return jsonify(success=False, error="Please upload a media file."), 400
    if not allowed_file(media.filename):
        return jsonify(success=False, error="Unsupported file type. Please upload audio or video."), 400

    tier = request.form.get("tier", "high")
    language = request.form.get("language", "auto").strip() or "auto"
    task = request.form.get("task", "transcribe")
    fmt = request.form.get("format", "srt")
    vocab = request.form.get("vocab", "").strip() or None

    input_path, input_name = save_upload(media)
    job_id = uuid4().hex
    _set_job_status(job_id, status="queued", progress=0, message="Waiting to start", input_name=media.filename)
    worker = threading.Thread(
        target=_process_job,
        args=(job_id, input_path, input_name, tier, language, task, fmt, vocab),
        daemon=True,
    )
    worker.start()
    return jsonify(success=True, job_id=job_id)


@app.route("/status/<job_id>")
def status(job_id):
    status_data = _get_job_status(job_id)
    if not status_data:
        return jsonify(success=False, error="Unknown job ID."), 404
    return jsonify(success=True, **status_data)


@app.route("/download/<filename>")
def download_file(filename):
    return send_from_directory(UPLOAD_DIR, filename, as_attachment=True)


@app.route("/download/<filename>")
def download_file(filename):
    return send_from_directory(UPLOAD_DIR, filename, as_attachment=True)


def main():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    main()
