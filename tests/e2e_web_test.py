"""End-to-end WEB test (slow; run explicitly, not via unittest discover).

Boots the REAL web server (waitress) as a separate process, uploads a
synthesized-speech WAV over real HTTP exactly like a site visitor, polls the
job to completion (real 'base' model — downloads once), and verifies the
transcript downloads with the expected words. Exit code 0 = pass.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import httpx  # noqa: E402  (already a faster-whisper dependency)

from e2e_test import KEY_WORDS, MIN_KEY_HITS, make_tts_wav  # noqa: E402

PORT = 7861
BASE = "http://127.0.0.1:%d" % PORT
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PYTHON = os.path.join(PROJECT_ROOT, ".venv", "Scripts", "python.exe")


def wait_for_server(timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if httpx.get(BASE + "/health", timeout=2).status_code == 200:
                return
        except httpx.HTTPError:
            time.sleep(0.5)
    raise AssertionError("server did not come up on %s" % BASE)


def main():
    tmp = tempfile.mkdtemp(prefix="shabd_e2e_web_")
    wav = os.path.join(tmp, "my song take 1.wav")
    env = dict(os.environ, PORT=str(PORT), SHABD_WEB_WARMUP="0")
    server = None
    try:
        print("1/5 Generating known speech via Windows TTS…")
        make_tts_wav(wav)

        print("2/5 Booting the real web server (waitress)…")
        server = subprocess.Popen(
            [PYTHON, "-m", "shabd.web"], cwd=PROJECT_ROOT, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        wait_for_server()
        print("   up: " + BASE)

        print("3/5 Uploading over real HTTP (tier=fast, format=txt)…")
        with open(wav, "rb") as f:
            resp = httpx.post(
                BASE + "/submit",
                files={"media": ("my song take 1.wav", f, "audio/wav")},
                data={"tier": "fast", "language": "en", "format": "txt"},
                timeout=60)
        assert resp.status_code == 200, resp.text
        job_id = resp.json()["job_id"]
        print("   job accepted: " + job_id)

        print("4/5 Polling job to completion (model downloads on first run)…")
        deadline = time.time() + 600
        data = None
        while time.time() < deadline:
            data = httpx.get(BASE + "/status/" + job_id, timeout=10).json()
            if data.get("status") in ("done", "error"):
                break
            time.sleep(2)
        assert data and data.get("status") == "done", "job failed: %r" % (data,)

        transcript = data["output_text"].lower()
        hits = [w for w in KEY_WORDS if w in transcript]
        assert len(hits) >= MIN_KEY_HITS, (
            "expected >=%d of %s, got %s in: %s"
            % (MIN_KEY_HITS, KEY_WORDS, hits, transcript))
        assert data["language"] == "en", "language detection failed"

        print("5/5 Downloading the transcript file…")
        dl = httpx.get(BASE + data["download_url"], timeout=30)
        assert dl.status_code == 200
        assert any(w in dl.text.lower() for w in hits)
        cd = dl.headers.get("content-disposition", "")
        assert "my_song_take_1.txt" in cd, "friendly filename missing: " + cd

        print("\nE2E WEB PASS — words found: %s | language: en | download OK"
              % hits)
        return 0
    finally:
        if server is not None:
            server.terminate()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
