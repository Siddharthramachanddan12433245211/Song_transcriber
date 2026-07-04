# Shabd — project rules for Claude

- Spec: specs/subtitle-studio.md. Plan: plans/subtitle-studio.md. No code without spec.
- Always use the project venv: `.venv\Scripts\python` (never global Python).
- Commands:
  - unit tests: `.venv\Scripts\python -m unittest discover -s tests -v`
  - e2e test:   `.venv\Scripts\python tests\e2e_test.py` (downloads tiny model once, slow)
  - GUI:        `run_shabd.bat` / `.venv\Scripts\python -m shabd.gui`
- All subtitle/timing logic lives in shabd/cues.py as pure functions (unit-testable,
  no model, no I/O). engine.py owns the model; gui.py owns the window; gui.py must
  never do transcription on the UI thread.
- No hard-coded phrase blacklists for filtering — use model confidence signals.
- Never add a dependency without flagging it in the spec first.
- Mistakes log: Mistakes.md (append whenever anything goes wrong).
