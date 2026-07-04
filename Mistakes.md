# Mistakes log

Append-only. Every time something goes wrong (bug shipped, test missed, wrong
assumption), record: date, what happened, root cause, prevention.

## 2026-07-04 — Review caught a timing bug the unit tests missed
- **What**: A subtitle made of a single word with a long time span could stay
  on screen up to 9+ seconds, violating the 1–6 s spec rule (review finding C1).
  Also: no protection against backward-jumping word timestamps (M1), a spec
  promise (compression-ratio filter) not implemented (M2), non-atomic
  multi-format writes (M3), unsafe window close during a running job (M4),
  and no fast unit tests for engine.py (M5).
- **Root cause**: All unit-test fixtures generated well-behaved, evenly timed
  word streams — the tests mirrored the happy path instead of attacking edges.
  Engine logic was buried inside a method that required a real model to run.
- **Prevention**: Adversarial fixtures added (lone long word, backward times,
  hallucination segments). Segment processing extracted into a model-free
  function (`engine.collect_words`) so it stays unit-testable. Rule of thumb
  recorded: for every "must never" in the spec, write the test that tries to
  make it happen.

## 2026-07-05 — "Replit-ready web app" was committed but never ran
- **What**: Two commits added a Flask web app + Replit config and the README
  claimed it worked ("This project is ready to deploy on Replit"). In reality
  `shabd/web.py` crashed on import (duplicate `download_file` route) and
  `templates/index.html` had orphan Jinja fragments (`{% endif %}` with no
  `{% if %}` → TemplateSyntaxError). Both reproduced with failing output on
  2026-07-05 before fixing. Also: no spec, no plan, no tests, committed
  straight to main — every phase rule skipped. Replit itself was a dead end
  (free tier cannot host this).
- **Root cause**: Feature was written and "declared done" without ever
  starting the server or rendering the page once; process gates (spec → plan
  → test → review) bypassed.
- **Prevention**: Web work now has its own spec/plan; unit tests must include
  "server imports and page renders"; nothing is called done without a real
  HTTP round-trip proof. Hosting claims require checking the host's current
  pricing page first.
