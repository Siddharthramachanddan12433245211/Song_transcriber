# Spec: Shabd — Offline Subtitle Studio (v1)

Status: Approved for build (product decisions made autonomously per owner's
instruction "go for it… it needs to be a really accurate subtitle generator").
Every decision is reversible after first delivery.

## One-line pitch
Drop in any video or audio file, get accurate, professionally formatted subtitles
out — fully offline, on your own computer, nothing uploaded anywhere.

## Who is it for
- YouTubers / reels creators who need captions (platforms reward captioned video).
- Teachers & students with recorded lectures.
- Podcasters, journalists (interview transcripts).
- Anyone with privacy-sensitive recordings (nothing may leave the device).

## The problem
Online subtitle tools upload your media (privacy risk, slow for big files, often
paid per minute). Free auto-captions (YouTube's) are inaccurate and unformatted.
Existing offline tools are command-line only — unusable for non-technical people.

## Accuracy strategy (the core requirement)
1. **Model**: OpenAI's Whisper family — state of the art for open speech
   recognition — run locally via the faster-whisper engine (4× faster than the
   reference implementation on CPU, identical accuracy).
2. **Voice-activity detection (VAD)**: audio is pre-screened so the model never
   "hallucinates" text during silence or music.
3. **Word-level timestamps**: each subtitle appears exactly when the words are
   spoken, not merely near them.
4. **Custom vocabulary**: user can type names/brand/technical terms; these are fed
   to the model as context so they're spelled correctly.
5. **Beam search decoding** (width 5) with temperature fallback — the engine
   considers alternatives instead of taking the first guess.
6. **Professional formatting rules** (Netflix-style): max 42 characters/line,
   max 2 lines, 1–6 s on screen, split at sentence boundaries and natural pauses,
   balanced line breaks, minimum gap between subtitles.
7. **Signal-based quality filters** (no hard-coded phrase blacklists): segments
   are dropped/flagged using the model's own confidence signals
   (no-speech probability, log-probability, compression ratio).

## Model tiers (user-selectable; app recommends based on hardware)
| Tier | Whisper model | Notes on this machine (4-core Ryzen, no NVIDIA GPU) |
|------|---------------|------------------------------------------------------|
| Fast | base | quick drafts, ~1× video length |
| Balanced | small | good accuracy, ~2× video length |
| High (default) | medium | very good accuracy, ~4× video length |
| Maximum | large-v3 | best available accuracy, slow on this CPU (~8×) |
Models download once (75 MB – 3 GB) then work offline forever. If an NVIDIA GPU
is present the app uses it automatically and Maximum becomes practical.

## Features (v1)
1. Tkinter desktop app (double-click launcher) + full CLI for power users.
2. Batch queue: multiple files processed one after another.
3. Input: any common video/audio (mp4, mkv, mov, webm, mp3, wav, m4a, flac, ogg…)
   — decoded in-process (bundled FFmpeg libraries; user installs nothing extra).
4. Language: auto-detect (99 languages incl. Hindi) or manual pick;
   optional "translate to English" mode.
5. Output: .srt and/or .vtt subtitles + optional plain-text transcript,
   saved next to the source file (or a chosen folder).
6. Live progress: percentage + subtitle lines appear as they're recognized;
   cancellable at any time.
7. All heavy work on a background thread — the window never freezes.

## Must NEVER
1. Upload media, transcripts, or telemetry anywhere. (Only network use ever:
   one-time model download from Hugging Face, clearly indicated.)
2. Freeze the UI during transcription.
3. Overwrite an existing subtitle file without warning.
4. Claim a file finished if any stage failed.

## Out of scope for v1 (roadmap)
Speaker labels (diarization), burned-in subtitles (video export), subtitle editor
with waveform, GPU support for AMD (not supported by the engine), translation to
languages other than English, installer (.exe packaging via PyInstaller).

## Monetization (later, owner's call)
Free: single file at a time, Fast/Balanced tiers. Pro (one-time ₹1,499 or
$19): batch queue, High/Maximum tiers, transcript export, priority support.
Packaging as a signed .exe installer is the step that makes selling practical.

## Dependencies (flagged per global rules — no approval loop available, so listed
transparently): Python packages `faster-whisper` (+ its components: ctranslate2,
huggingface-hub, tokenizers, onnxruntime, av). ~250 MB in a project-local .venv.
No system-wide installs; delete the project folder and it's all gone.

## Success criteria
1. Unit tests green (subtitle formatting, timing rules, output formats).
2. End-to-end test green: synthesized speech WAV → pipeline → subtitle file
   containing the spoken words at sane timestamps.
3. Full flow works offline after first model download.

## Assumptions made on owner's behalf
A1. Desktop app (not web) — privacy story + big local files.
A2. Windows-first; code stays OS-portable except the .bat launcher.
A3. Default output = .srt next to the source file with same name.
A4. UI in English; Hindi UI is roadmap.
A5. Working brand "Shabd"; no trademark search yet.
