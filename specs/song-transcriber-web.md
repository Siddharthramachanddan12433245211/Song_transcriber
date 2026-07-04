# Spec: Shabd Web — Free Song Transcription Website (v1)

Status: Approved by owner 2026-07-05 ("Yes, go ahead" — host on Hugging Face
Spaces free tier). Product decisions below were surfaced in chat; technical
decisions made by engineer and stated transparently.

## One-line pitch
A free public website where anyone can upload a song (or any audio/video),
wait a few minutes, and download the transcribed lyrics/subtitles — powered by
the existing Shabd engine, hosted at zero cost.

## Who is it for
- People who want the lyrics/words of their own recordings: covers, practice
  takes, demos, voice memos, lectures, podcasts.
- Owner's goal: attract visitors; later add minimal advertising (roadmap).

## Hosting decision (the reason this project exists)
- **Host: Hugging Face Spaces, free CPU tier** — 2 vCPU, 16 GB RAM, $0,
  no credit card, public URL under the owner's existing account
  (`Siddharth7021`). Deployed as a Docker Space on port 7860.
- Replit was evaluated and rejected: free tier is 0.5 vCPU / 512 MB, sleeps
  after 5 min, free deployments expire after 30 days — cannot run this app.
- Known free-tier trade-offs (accepted): jobs run one at a time in a queue;
  Space sleeps after ~48 h of no visits (next visitor waits ~1–2 min);
  disk is wiped on restart (fine — we keep nothing).

## Product truth (stated out loud, owner accepted)
Unlike the desktop app ("nothing leaves your device"), the website receives
user uploads on the server. Mitigation: files are deleted right after
processing (input) and within ~2 hours (output); nothing is logged or kept.
The page must say this plainly.

## Web-specific limits (engineer's defaults; all env-overridable)
| Limit | Default | Env var | Why |
|---|---|---|---|
| Max upload size | 50 MB | `SHABD_WEB_MAX_MB` | free CPU + typical song ≤ 10 MB |
| Max audio length | 15 min | `SHABD_WEB_MAX_MINUTES` | keep the queue moving |
| Accuracy tiers offered | fast, balanced | `SHABD_WEB_TIERS` | high/max too slow on 2 vCPU |
| Default tier | fast (Whisper "base") | — | ~song-length wait |
| Max queue length | 10 waiting jobs | `SHABD_WEB_MAX_QUEUE` | fail fast with a friendly message |
| File retention | ≤ 2 hours | `SHABD_WEB_RETENTION_MINUTES` | privacy + disk |

Accepted residual risk (review 2026-07-05): a file whose header *lies* about
a short duration passes the pre-check and is only rejected after transcribing
— it could occupy the single worker for a long stretch. Hard to construct,
bounded by the 50 MB cap, revisit if abuse is ever observed.

## Features (v1)
1. One page: upload file → pick tier/language/output format → live progress
   with queue position → read result in the page + download the file.
2. Output formats: plain lyrics text (.txt, default), subtitles (.srt, .vtt).
3. Language auto-detect (or manual pick), optional translate-to-English,
   custom vocabulary box (artist names, unusual words).
4. Jobs run strictly one at a time through a single worker queue; one shared
   engine instance so the model stays loaded between jobs (no reload cost).
5. Model warm-up on server start (env `SHABD_WEB_WARMUP=1`, on in Docker only)
   so the first visitor doesn't pay the model download wait.
6. Ad placeholders remain in the page (two small boxes); real ad code is a
   later, owner-approved step (needs own domain — out of scope v1).

## Must NEVER (web version)
1. Keep or log user media/transcripts beyond the retention window.
2. Run more than one transcription at once (free CPU would thrash).
3. Accept a file over the size/length limits without a clear, friendly error.
4. Claim a job finished if any stage failed.
5. Break the existing desktop app, CLI, or their tests.

## Out of scope for v1 (roadmap)
Own domain + real AdSense integration; per-IP rate limiting; vocal separation
("enhance for songs" pre-step — heavy on CPU); accounts/history; GPU tier.

## Dependencies (flagged per global rules)
- **waitress** (new, ~1 MB, pure Python): production web server that runs the
  Flask app on both Windows (testable locally) and Linux (in the Space).
  Chosen over gunicorn because gunicorn cannot run on Windows, so we could
  never test the real server locally.
- Docker base image `python:3.10-slim` (matches local venv Python 3.10).
- No other new packages. `huggingface_hub` (already installed) is used by the
  deploy script to upload the Space.

## Success criteria
1. All existing tests still green; new web unit tests green (fake engine —
   no model download in unit tests).
2. Local end-to-end proof: real server boots on Windows, a real audio file is
   submitted over HTTP, progresses, completes, and the transcript downloads.
3. Live Space serves the same flow at its public URL (verified after owner
   provides the Hugging Face access token).

## Assumptions made on owner's behalf (say-it-out-loud list)
A1. Space name `Siddharth7021/shabd`; page title "Shabd — free song & speech
    transcription". Rename is a 1-minute change later.
A2. Default output = plain lyrics text (song users read words, not timestamps).
A3. The Replit files (`.replit`, `replit.nix`) are removed — dead end.
A4. English UI; wording targets "transcribe YOUR recordings" (keeps ad
    networks and copyright concerns at arm's length).
