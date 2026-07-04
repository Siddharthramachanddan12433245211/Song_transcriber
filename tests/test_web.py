"""Unit tests for the web interface (spec: song-transcriber-web.md).

A fake engine stands in for faster-whisper, so these run in seconds with no
model download. The real job queue/worker thread is exercised for real.
"""

import io
import os
import time
import unittest

from shabd import web


class FakeEngine:
    """Records what it was asked to do and returns a canned transcription."""

    def __init__(self):
        self.calls = []

    def transcribe_file(self, path, tier_or_model="fast", language=None,
                        task="transcribe", vocab=None, device=None,
                        compute_type=None, on_progress=None, on_segment=None,
                        on_status=None, cancel_event=None):
        self.calls.append({"path": path, "tier": tier_or_model,
                           "language": language, "task": task, "vocab": vocab})
        if on_progress:
            on_progress(1.0)
        return {
            "words": [{"text": "hello", "start": 0.0, "end": 0.4},
                      {"text": "world", "start": 0.5, "end": 0.9}],
            "language": "en",
            "language_probability": 0.93,
            "duration": 1.0,
        }


def wav_upload(name="song.wav", size=2048):
    return {"media": (io.BytesIO(b"RIFF" + b"\x00" * size), name)}


class WebTests(unittest.TestCase):
    def setUp(self):
        self.client = web.app.test_client()
        self.fake = FakeEngine()
        self._real_engine = web._engine
        web._engine = self.fake
        self._real_probe = web.probe_duration_seconds
        web.probe_duration_seconds = lambda path: 60.0
        self._real_max_queue = web.MAX_QUEUE
        self._real_max_len = web.app.config["MAX_CONTENT_LENGTH"]
        with web._jobs_lock:
            web._jobs.clear()

    def tearDown(self):
        web._engine = self._real_engine
        web.probe_duration_seconds = self._real_probe
        web.MAX_QUEUE = self._real_max_queue
        web.app.config["MAX_CONTENT_LENGTH"] = self._real_max_len

    def _submit(self, data=None, **kwargs):
        payload = wav_upload(**kwargs)
        payload.update(data or {})
        return self.client.post("/submit", data=payload,
                                content_type="multipart/form-data")

    def _wait_done(self, job_id, timeout=10.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            data = self.client.get("/status/%s" % job_id).get_json()
            if data.get("status") in ("done", "error"):
                return data
            time.sleep(0.05)
        self.fail("job did not finish in time")

    def test_page_renders_with_allowed_tiers_only(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn("Shabd", html)
        for tier in web.ALLOWED_TIERS:
            self.assertIn('value="%s"' % tier, html)
        for blocked in ("high", "max"):
            if blocked not in web.ALLOWED_TIERS:
                self.assertNotIn('value="%s"' % blocked, html)

    def test_submit_transcribe_download_happy_path(self):
        resp = self._submit(data={"format": "txt"})
        self.assertEqual(resp.status_code, 200)
        job_id = resp.get_json()["job_id"]

        data = self._wait_done(job_id)
        self.assertEqual(data["status"], "done", data.get("message"))
        self.assertIn("hello world", data["output_text"])
        self.assertEqual(data["language"], "en")

        dl = self.client.get(data["download_url"])
        self.assertEqual(dl.status_code, 200)
        self.assertIn(b"hello world", dl.data)
        self.assertIn("song", dl.headers["Content-Disposition"])
        dl.close()

        deadline = time.time() + 3
        input_path = self.fake.calls[0]["path"]
        while os.path.exists(input_path) and time.time() < deadline:
            time.sleep(0.05)
        self.assertFalse(os.path.exists(input_path),
                         "uploaded file must be deleted after processing")

    def test_rejects_unsupported_extension(self):
        resp = self._submit(name="malware.exe")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Unsupported", resp.get_json()["error"])

    def test_rejects_file_over_size_limit(self):
        web.app.config["MAX_CONTENT_LENGTH"] = 1024
        resp = self._submit(size=4096)
        self.assertEqual(resp.status_code, 413)
        self.assertIn("too big", resp.get_json()["error"])

    def test_rejects_recording_over_duration_limit(self):
        web.probe_duration_seconds = lambda path: (web.MAX_MINUTES + 1) * 60.0
        resp = self._submit()
        self.assertEqual(resp.status_code, 400)
        self.assertIn("minutes", resp.get_json()["error"])

    def test_rejects_when_queue_full(self):
        web.MAX_QUEUE = 0
        resp = self._submit()
        self.assertEqual(resp.status_code, 429)
        self.assertIn("queue is full", resp.get_json()["error"])

    def test_disallowed_tier_falls_back_to_default(self):
        resp = self._submit(data={"tier": "max"})
        job_id = resp.get_json()["job_id"]
        self._wait_done(job_id)
        self.assertEqual(self.fake.calls[-1]["tier"], web.DEFAULT_TIER)

    def test_unknown_job_id_is_404(self):
        resp = self.client.get("/status/nope")
        self.assertEqual(resp.status_code, 404)

    def test_sweep_deletes_only_old_files(self):
        old_path = os.path.join(web.UPLOAD_DIR, "old_file.txt")
        new_path = os.path.join(web.UPLOAD_DIR, "new_file.txt")
        for p in (old_path, new_path):
            with open(p, "w") as f:
                f.write("x")
        stale = time.time() - (web.RETENTION_MINUTES * 60 + 60)
        os.utime(old_path, (stale, stale))
        web.sweep_old_files()
        self.assertFalse(os.path.exists(old_path), "old file must be swept")
        self.assertTrue(os.path.exists(new_path), "fresh file must remain")
        os.remove(new_path)


if __name__ == "__main__":
    unittest.main()
