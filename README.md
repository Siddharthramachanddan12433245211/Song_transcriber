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

## Web app (free public song transcription)
Spec: `specs/song-transcriber-web.md`. Run the web UI locally:
```
.venv\Scripts\python -m shabd.web
```
Then open `http://127.0.0.1:7860/` in your browser.

Jobs run one at a time through a queue; uploads are limited (50 MB / 15 min
by default) and files are auto-deleted (inputs right after processing,
outputs after 2 h). All limits are env-overridable — see the table in the spec.

### Hosting (Hugging Face Spaces, free CPU tier)
The web app deploys as a Docker Space (2 vCPU / 16 GB, $0):
```
set HF_TOKEN=hf_xxx     (WRITE token from hf.co/settings/tokens)
.venv\Scripts\python tools\deploy_space.py
```
Live URL: `https://huggingface.co/spaces/Siddharth7021/shabd`. Re-run the
script to redeploy after changes. (Replit was evaluated and rejected — its
free tier cannot host this; see spec §Hosting decision.)

### Web tests
```
.venv\Scripts\python -m unittest discover -s tests -v   # includes web unit tests
.venv\Scripts\python tests\e2e_web_test.py              # real server + real model over HTTP
```

### Monetization / ads
Two placeholder ad boxes exist in `templates/index.html`. Real ad code
(AdSense etc.) is a later, owner-approved step — it needs its own domain.

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
