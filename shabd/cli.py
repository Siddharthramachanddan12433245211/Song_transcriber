"""Command-line interface.

Examples:
  python -m shabd.cli video.mp4
  python -m shabd.cli lecture.mp3 --tier max --language hi --formats srt,txt
  python -m shabd.cli a.mp4 b.mp4 --vocab "Shabd, Ryzen, Anthropic"
"""

import argparse
import os
import sys
import time

from . import __version__, engine as engine_mod, hardware


def make_parser():
    p = argparse.ArgumentParser(
        prog="shabd",
        description="Shabd — accurate offline subtitles for any video/audio file.",
    )
    p.add_argument("inputs", nargs="+", help="video/audio file(s)")
    p.add_argument("--tier", default=None,
                   choices=list(engine_mod.MODEL_TIERS.keys()),
                   help="accuracy tier (default: recommended for this machine)")
    p.add_argument("--model", default=None,
                   help="advanced: exact Whisper model name (overrides --tier)")
    p.add_argument("--language", default="auto",
                   help="ISO code like hi, en — or 'auto' (default)")
    p.add_argument("--task", default="transcribe",
                   choices=["transcribe", "translate"],
                   help="translate = subtitles in English regardless of speech language")
    p.add_argument("--formats", default="srt",
                   help="comma-separated: srt,vtt,txt (default srt)")
    p.add_argument("--output-dir", default=None,
                   help="where to save (default: next to each input file)")
    p.add_argument("--vocab", default=None,
                   help="comma-separated names/terms to spell correctly")
    p.add_argument("--overwrite", action="store_true",
                   help="allow replacing existing subtitle files")
    p.add_argument("--quiet", action="store_true", help="no live text preview")
    p.add_argument("--version", action="version", version="Shabd " + __version__)
    return p


def main(argv=None):
    args = make_parser().parse_args(argv)
    tier = args.model or args.tier or hardware.recommend_tier()
    formats = [f for f in args.formats.split(",") if f.strip()]

    print("Shabd %s — %s" % (__version__, hardware.describe()))
    print("Model: %s | Language: %s | Task: %s | Formats: %s" % (
        engine_mod.tier_to_model(tier), args.language, args.task, ",".join(formats)))

    eng = engine_mod.Engine()
    failures = 0
    for path in args.inputs:
        print("\n=== %s ===" % path)
        t0 = time.time()
        state = {"last_pct": -1}

        def on_progress(frac):
            pct = int(frac * 100)
            if pct != state["last_pct"]:
                state["last_pct"] = pct
                sys.stdout.write("\r[%3d%%]" % pct)
                sys.stdout.flush()

        def on_segment(text, start, end):
            if not args.quiet:
                sys.stdout.write("\r[%3d%%] %s\n" % (max(state["last_pct"], 0), text))
                sys.stdout.flush()

        try:
            result = eng.transcribe_file(
                path, tier_or_model=tier, language=args.language,
                task=args.task, vocab=args.vocab,
                on_progress=on_progress, on_segment=on_segment,
                on_status=lambda m: print(m),
            )
            written = engine_mod.write_outputs(
                result, path, formats,
                output_dir=args.output_dir, overwrite=args.overwrite,
            )
            elapsed = time.time() - t0
            print("\rDetected language: %s (%.0f%% confidence)" % (
                result["language"], result["language_probability"] * 100))
            print("Done in %.1fs (media length %.1fs). Wrote:" % (elapsed, result["duration"]))
            for w in written:
                print("  " + w)
        except FileExistsError as e:
            failures += 1
            print("\rSKIPPED: %s already exists (use --overwrite to replace)" % e)
        except FileNotFoundError:
            failures += 1
            print("\rERROR: file not found: %s" % path)
        except Exception as e:  # report faithfully, keep batch going
            failures += 1
            print("\rERROR on %s: %s" % (path, e))

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
