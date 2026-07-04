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

- `shabd/cues.py` — subtitle formatting logic (pure functions, fully unit-tested)
- `shabd/engine.py` — speech recognition wrapper (faster-whisper)
- `shabd/hardware.py` — device detection + model recommendation
- `shabd/cli.py` — command-line interface
- `shabd/gui.py` — desktop app (Tkinter)

Docs: spec in `specs/subtitle-studio.md`, plan in `plans/subtitle-studio.md`.
