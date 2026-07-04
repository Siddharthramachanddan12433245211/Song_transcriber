# Shabd — Offline Subtitle Studio

Accurate subtitles for any video or audio file, generated entirely on your own
computer. No uploads, no accounts, no internet needed (after a one-time model
download).

## Quick start (Windows)
1. Double-click `run_shabd.bat` (first run may take a minute).
2. Click **Add files…** and pick your video/audio.
3. Pick an accuracy tier (the app recommends one for your PC) and click **Start**.
4. Your `.srt` subtitle file appears next to the video. Done.

Tip: type names/technical words into the **Custom vocabulary** box so they're
spelled correctly.

## Command line
```
.venv\Scripts\python -m shabd.cli "C:\path\video.mp4" --tier high --formats srt,txt
.venv\Scripts\python -m shabd.cli --help
```

## Developer setup
```
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m unittest discover -s tests -v      # fast unit tests
.venv\Scripts\python tests\e2e_test.py                     # full pipeline test (downloads tiny model once)
```

## Web app
Run the Flask web UI locally:
```
.venv\Scripts\python -m shabd.web
```
Then open `http://127.0.0.1:5000/` in your browser.

This version is intended for free CPU transcription. It uses your existing code and runs the model locally on the server.

Optional environment variables:
- `SHABD_SECRET_KEY` to override the Flask secret key

Use the web form to upload a media file and download the generated transcript.

### Monetization / ads
I added lightweight ad placeholders in `templates/index.html` so you can replace them with real ad code later.
- The ads are non-intrusive and only appear in two small banner areas.
- For real monetization, integrate Google AdSense or any ad network into those placeholders.

- `shabd/cues.py` — subtitle formatting logic (pure functions, fully unit-tested)
- `shabd/engine.py` — speech recognition wrapper (faster-whisper)
- `shabd/hardware.py` — device detection + model recommendation
- `shabd/cli.py` — command-line interface
- `shabd/gui.py` — desktop app (Tkinter)
- `shabd/web.py` — lightweight Flask web interface

Docs: spec in `specs/subtitle-studio.md`, plan in `plans/subtitle-studio.md`.

## Pre-release manual checklist
1. All tests green (`unittest discover` + `tests\e2e_test.py`).
2. Offline check: after models are downloaded, disconnect Wi-Fi and confirm a
   transcription completes (spec success criterion 3 — can't be automated well).
3. Try one real video with Hindi or accented speech at the High tier.
