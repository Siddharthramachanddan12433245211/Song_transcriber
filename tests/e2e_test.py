"""End-to-end pipeline test (slow; run explicitly, not via unittest discover).

Synthesizes known speech with Windows' built-in text-to-speech, runs the REAL
transcription pipeline with the 'tiny' model (downloads ~75 MB on first run),
and verifies words + timing + file outputs. Exit code 0 = pass.
"""

import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shabd import cues, engine as engine_mod  # noqa: E402

SPOKEN = ("The quick brown fox jumps over the lazy dog. "
          "Speech recognition accuracy is tested with this sample. "
          "Subtitles must appear at the correct time.")

KEY_WORDS = ["fox", "dog", "recognition", "subtitles"]
MIN_KEY_HITS = 2  # tiny model + robotic TTS voice; default app tier is higher


def make_tts_wav(path):
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$s.Rate = -1; "
        "$s.SetOutputToWaveFile('%s'); "
        "$s.Speak('%s'); "
        "$s.Dispose()" % (path, SPOKEN.replace("'", "''"))
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        check=True, capture_output=True, text=True,
    )
    assert os.path.getsize(path) > 10000, "TTS produced an empty file"


def main():
    tmp = tempfile.mkdtemp(prefix="shabd_e2e_")
    wav = os.path.join(tmp, "sample.wav")
    try:
        print("1/4 Generating known speech via Windows TTS…")
        make_tts_wav(wav)

        print("2/4 Transcribing with the real pipeline (tiny model)…")
        eng = engine_mod.Engine()
        got_segments = []
        result = eng.transcribe_file(
            wav, tier_or_model="tiny", language="en",
            on_segment=lambda t, s, e: got_segments.append(t),
            on_status=lambda m: print("   " + m),
        )
        transcript = " ".join(w["text"] for w in result["words"]).lower()
        print("   transcript: " + transcript)

        print("3/4 Checking accuracy + timing…")
        hits = [w for w in KEY_WORDS if w in transcript]
        assert len(hits) >= MIN_KEY_HITS, (
            "expected >=%d of %s in transcript, got %s" % (MIN_KEY_HITS, KEY_WORDS, hits))
        assert result["language"] == "en", "language detection failed: %s" % result["language"]
        assert result["duration"] > 5, "duration missing"
        built = cues.build_cues(result["words"])
        assert built, "no cues built"
        assert built[0]["start"] < 3.0, "first cue starts too late"
        for c in built:
            assert 0 <= c["start"] < c["end"] <= result["duration"] + 7, "cue timing out of range"
        assert got_segments, "live segment callback never fired"

        print("4/4 Checking file outputs + overwrite protection…")
        out_dir = os.path.join(tmp, "out")
        written = engine_mod.write_outputs(result, wav, ["srt", "vtt", "txt"], output_dir=out_dir)
        assert len(written) == 3
        srt_text = open(written[0], encoding="utf-8-sig").read()
        assert "-->" in srt_text and srt_text.strip().startswith("1")
        try:
            engine_mod.write_outputs(result, wav, ["srt"], output_dir=out_dir)
            raise AssertionError("overwrite protection failed: no error raised")
        except FileExistsError:
            pass

        print("\nE2E PASS — words found: %s | language: en | %d cues | 3 files written"
              % (hits, len(built)))
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
