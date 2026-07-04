"""Unit tests for shabd.engine's model-free logic: the segment collector
(confidence filtering, cancellation, callbacks) and file output safety.
No model, no network — runs in milliseconds."""

import os
import shutil
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shabd import engine  # noqa: E402


class FakeWord:
    def __init__(self, word, start, end):
        self.word = word
        self.start = start
        self.end = end


class FakeSeg:
    def __init__(self, text, start, end, words=None,
                 no_speech_prob=0.0, avg_logprob=-0.2, compression_ratio=1.2):
        self.text = text
        self.start = start
        self.end = end
        self.words = words
        self.no_speech_prob = no_speech_prob
        self.avg_logprob = avg_logprob
        self.compression_ratio = compression_ratio


class TestCollectWords(unittest.TestCase):
    def test_extracts_words_and_fires_callbacks(self):
        segs = [FakeSeg("Hello there", 0.0, 1.0,
                        words=[FakeWord(" Hello", 0.0, 0.4), FakeWord(" there", 0.5, 0.9)])]
        seen_segments = []
        progress = []
        words = engine.collect_words(iter(segs), duration=1.0,
                                     on_progress=progress.append,
                                     on_segment=lambda t, s, e: seen_segments.append(t))
        self.assertEqual([w["text"] for w in words], ["Hello", "there"])
        self.assertEqual(seen_segments, ["Hello there"])
        self.assertEqual(progress[-1], 1.0)

    def test_synthesizes_words_when_model_gives_none(self):
        segs = [FakeSeg("one two", 2.0, 4.0, words=None)]
        words = engine.collect_words(iter(segs), duration=4.0)
        self.assertEqual(len(words), 2)
        self.assertAlmostEqual(words[0]["start"], 2.0)
        self.assertAlmostEqual(words[1]["end"], 4.0)

    def test_drops_no_speech_hallucination(self):
        segs = [
            FakeSeg("real speech", 0.0, 1.0, words=[FakeWord("real", 0, 0.4), FakeWord("speech", 0.5, 1.0)]),
            FakeSeg("thanks for watching", 5.0, 6.0,
                    no_speech_prob=0.95, avg_logprob=-1.4),  # classic silence hallucination
        ]
        words = engine.collect_words(iter(segs), duration=6.0)
        self.assertEqual([w["text"] for w in words], ["real", "speech"])

    def test_drops_repetition_loop_by_compression_ratio(self):
        segs = [FakeSeg("la la la la la la la la", 0.0, 2.0,
                        compression_ratio=3.1, avg_logprob=-1.3)]
        words = engine.collect_words(iter(segs), duration=2.0)
        self.assertEqual(words, [])

    def test_keeps_confident_segment_even_with_high_no_speech(self):
        # Only the COMBINATION of low confidence + bad signal drops a segment.
        segs = [FakeSeg("quiet but real", 0.0, 1.0,
                        no_speech_prob=0.9, avg_logprob=-0.3)]
        words = engine.collect_words(iter(segs), duration=1.0)
        self.assertEqual(len(words), 3)

    def test_cancellation_raises(self):
        ev = threading.Event()
        ev.set()
        segs = iter([FakeSeg("x", 0, 1)])
        with self.assertRaises(engine.CancelledError):
            engine.collect_words(segs, duration=1.0, cancel_event=ev)


class TestWriteOutputs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="shabd_wo_")
        self.result = {"words": [{"text": "Hello.", "start": 0.0, "end": 0.5}]}
        self.src = os.path.join(self.tmp, "video.mp4")
        open(self.src, "w").close()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_writes_all_formats(self):
        written = engine.write_outputs(self.result, self.src, ["srt", "vtt", "txt"],
                                       output_dir=self.tmp)
        self.assertEqual(len(written), 3)
        for path in written:
            self.assertTrue(os.path.exists(path))
        srt = open(written[0], encoding="utf-8-sig").read()
        self.assertIn("-->", srt)
        self.assertIn("Hello.", srt)

    def test_all_or_nothing_on_conflict(self):
        # .txt already exists -> NOTHING may be written, not even the .srt.
        existing = os.path.join(self.tmp, "video.txt")
        with open(existing, "w") as f:
            f.write("precious notes")
        with self.assertRaises(FileExistsError):
            engine.write_outputs(self.result, self.src, ["srt", "txt"],
                                 output_dir=self.tmp)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "video.srt")),
                         "srt written despite txt conflict — not atomic")
        self.assertEqual(open(existing).read(), "precious notes")

    def test_overwrite_replaces(self):
        target = os.path.join(self.tmp, "video.srt")
        with open(target, "w") as f:
            f.write("old")
        written = engine.write_outputs(self.result, self.src, ["srt"],
                                       output_dir=self.tmp, overwrite=True)
        self.assertIn("Hello.", open(written[0], encoding="utf-8-sig").read())

    def test_unknown_format_rejected(self):
        with self.assertRaises(ValueError):
            engine.write_outputs(self.result, self.src, ["docx"], output_dir=self.tmp)


class TestHelpers(unittest.TestCase):
    def test_tier_mapping(self):
        self.assertEqual(engine.tier_to_model("high"), "medium")
        self.assertEqual(engine.tier_to_model("max"), "large-v3")
        self.assertEqual(engine.tier_to_model("large-v2"), "large-v2")  # raw names pass through

    def test_vocab_prompt(self):
        self.assertIsNone(engine.build_vocab_prompt(None))
        self.assertIsNone(engine.build_vocab_prompt("  ,, "))
        self.assertEqual(engine.build_vocab_prompt("Shabd, Ryzen\nAnthropic"),
                         "Glossary: Shabd, Ryzen, Anthropic.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
