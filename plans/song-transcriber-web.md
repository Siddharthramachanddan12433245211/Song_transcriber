# Plan: Shabd Web — Free Song Transcription Website

Spec: specs/song-transcriber-web.md. Branch: feature/song-transcriber-web.
Each task is small, testable in one sitting, and committed on completion.

1. **Record the inherited breakage.** Reproduce and log (Mistakes.md) the two
   defects from the unreviewed "Replit" commits: duplicate `download_file`
   route (server crashes on import) and orphan Jinja fragments in
   `templates/index.html` (TemplateSyntaxError). Evidence captured before any
   fix. ✅ reproduced 2026-07-05.
2. **Rebuild `shabd/web.py` to spec.** Single-worker job queue (one shared
   Engine), queue position in status, upload-size / duration / queue-length
   limits, tier allowlist, retention sweep (delete input after job, outputs
   after 2 h), `/health` endpoint, waitress `main()`. Remove duplicate route.
3. **Rebuild `templates/index.html`.** Fix broken fragments, add progress-bar
   CSS, queue-position display, song-focused copy, privacy note, limits note,
   tier options rendered from server config (only allowed tiers shown).
4. **Unit tests `tests/test_web.py` (fake engine, no model).** Cover: happy
   path submit→status→download, rejected extension, over-size, over-duration,
   full queue, disallowed tier falls back, retention sweep deletes old files,
   template renders. All existing tests stay green.
5. **Local end-to-end proof (real server, real model).** Boot waitress on
   Windows, POST the e2e synthesized WAV over real HTTP with tier=fast…
   actually `tiny` model (cached from prior e2e) to stay quick, poll to done,
   download transcript, assert the spoken words are present.
6. **Deployment package.** `Dockerfile` (python:3.10-slim, non-root user,
   port 7860, warmup on), `deploy/space_README.md` (HF Space metadata),
   `tools/deploy_space.py` (stages files + uploads via huggingface_hub using
   HF_TOKEN env), remove `.replit`/`replit.nix`, rewrite README web section.
7. **Review gate.** Run code-reviewer agent on the branch diff; resolve all
   CRITICAL findings; append lessons to Mistakes.md.
8. **Merge to main** (tests green + review passed), leave deploy-ready.
9. **Owner step: Hugging Face token** (3 plain steps provided in chat), then
   run the deploy script, verify the live URL end-to-end, hand over the link.

Task 9 needs the owner; everything else is autonomous.
