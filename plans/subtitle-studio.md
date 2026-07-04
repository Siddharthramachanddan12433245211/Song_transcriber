# Plan: Shabd — Offline Subtitle Studio (v1)

Small numbered tasks, each testable in one sitting; something runnable early.

1. **Scaffold + docs** — repo, spec, plan, README, CLAUDE.md, Mistakes.md,
   .gitignore. Verify: first commit on feature branch.
2. **Environment** — project-local .venv, install faster-whisper, pin exact
   versions in requirements.txt. Verify: `import faster_whisper` succeeds.
   (Dependency flag: faster-whisper + components, ~250 MB, local venv only.)
3. **Subtitle logic** (shabd/cues.py) — pure functions, no model:
   word→cue grouping (42 chars/line, ≤2 lines, 1–6 s, sentence/pause-aware
   splitting), balanced 2-line wrapping, timing normalization (gaps, overlaps,
   min duration), SRT/VTT/TXT serialization. Verify: unittest suite green.
4. **Engine + hardware** (shabd/engine.py, shabd/hardware.py) — faster-whisper
   wrapper (VAD, word timestamps, beam 5, vocabulary prompt, confidence filters,
   streaming progress callbacks, cancellation), device detection + model tier
   recommendation. Verify: unit-level import + fake-callback tests.
5. **CLI** (shabd/cli.py) — batch, model/language/format/vocab options, safe
   output naming (no silent overwrite). Verify: --help runs; used by e2e test.
6. **End-to-end accuracy test** — synthesize known speech to WAV using Windows'
   built-in text-to-speech, run the real pipeline with the tiny model, assert the
   words come back and timestamps are sane. Verify: test green (first run
   downloads ~75 MB model).
7. **GUI** (shabd/gui.py) — file queue, options panel, custom vocabulary box,
   progress bar + live subtitle preview, cancel button; all transcription on a
   worker thread with a message queue to the UI. run_shabd.bat launcher.
   Verify: window opens; job runs from the GUI; smoke test in suite.
8. **Code review** — code-reviewer agent; resolve all CRITICAL findings; re-test.
9. **Merge + delivery** — merge to main, delivery summary (usage steps, accuracy
   notes, monetization next steps).

Approval-needed items: task 2's dependencies (surfaced in spec §Dependencies —
proceeding under owner's standing "don't ask until it's created" instruction).
