"""Unit tests for shabd.cues — the subtitle formatting brain."""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shabd import cues  # noqa: E402


def mk_words(pairs):
    """pairs: [(text, start, end), ...] -> word dicts"""
    return [{"text": t, "start": s, "end": e} for (t, s, e) in pairs]


def steady_words(text, start=0.0, per_word=0.4):
    """Evenly timed words from a sentence string."""
    out = []
    t = start
    for tok in text.split():
        out.append({"text": tok, "start": t, "end": t + per_word * 0.85})
        t += per_word
    return out


class TestTimestamps(unittest.TestCase):
    def test_zero(self):
        self.assertEqual(cues.format_timestamp(0), "00:00:00,000")

    def test_typical(self):
        self.assertEqual(cues.format_timestamp(3661.5), "01:01:01,500")

    def test_rounding_carry(self):
        self.assertEqual(cues.format_timestamp(59.9996), "00:01:00,000")

    def test_vtt_separator(self):
        self.assertEqual(cues.format_timestamp(1.25, "."), "00:00:01.250")

    def test_negative_clamped(self):
        self.assertEqual(cues.format_timestamp(-3), "00:00:00,000")


class TestWrap(unittest.TestCase):
    def test_short_single_line(self):
        self.assertEqual(cues.wrap_lines("Hello there."), ["Hello there."])

    def test_two_lines_within_limit(self):
        text = "This is a fairly long subtitle sentence that must wrap into two lines"
        lines = cues.wrap_lines(text)
        self.assertEqual(len(lines), 2)
        for line in lines:
            self.assertLessEqual(len(line), 42)
        self.assertEqual(" ".join(lines), text)

    def test_prefers_punctuation_split(self):
        text = "After the meeting ended, everyone went straight home"
        lines = cues.wrap_lines(text)
        self.assertEqual(lines[0], "After the meeting ended,")

    def test_single_long_word_kept(self):
        word = "x" * 60
        self.assertEqual(cues.wrap_lines(word), [word])


class TestNormalizeWords(unittest.TestCase):
    def test_drops_empty_and_cleans(self):
        words = cues.normalize_words(
            [{"text": "  hi  ", "start": 0, "end": 0.5},
             {"text": "   ", "start": 0.5, "end": 0.6},
             {"text": "there", "start": 0.6, "end": 1.0}]
        )
        self.assertEqual([w["text"] for w in words], ["hi", "there"])

    def test_repairs_missing_times(self):
        words = cues.normalize_words(
            [{"text": "a", "start": 1.0, "end": 1.5},
             {"text": "b", "start": None, "end": None},
             {"text": "c", "start": 2.0, "end": 1.0}]  # end < start
        )
        self.assertEqual(words[1]["start"], 1.5)
        self.assertEqual(words[1]["end"], 1.5)
        self.assertEqual(words[2]["end"], words[2]["start"])

    def test_synthesize_words_even_spread(self):
        out = cues.synthesize_words("one two three four", 10.0, 12.0)
        self.assertEqual(len(out), 4)
        self.assertAlmostEqual(out[0]["start"], 10.0)
        self.assertAlmostEqual(out[1]["start"], 10.5)
        self.assertAlmostEqual(out[-1]["end"], 12.0)


class TestGrouping(unittest.TestCase):
    def test_short_sentence_is_one_cue(self):
        result = cues.build_cues(steady_words("Hello world, this is a test."))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["text"], "Hello world, this is a test.")

    def test_two_tiny_sentences_merge(self):
        words = steady_words("Hi. How are you today?")
        result = cues.build_cues(words)
        self.assertEqual(len(result), 1)

    def test_sentences_split_into_separate_cues(self):
        text = ("The first sentence talks about the weather today. "
                "The second sentence discusses tomorrow's plans in detail.")
        result = cues.build_cues(steady_words(text))
        self.assertEqual(len(result), 2)
        self.assertTrue(result[0]["text"].endswith("today."))

    def test_long_pause_forces_split(self):
        words = steady_words("before the pause")
        after = steady_words("after the pause", start=words[-1]["end"] + 2.0)
        result = cues.build_cues(words + after)
        self.assertEqual(len(result), 2)

    def test_long_sentence_splits_at_comma(self):
        text = ("When the monsoon finally arrived in the city after months of heat, "
                "everyone ran outside to celebrate in the rain together")
        result = cues.build_cues(steady_words(text))
        self.assertGreaterEqual(len(result), 2)
        self.assertTrue(result[0]["text"].endswith(","))

    def test_max_duration_forces_split(self):
        # Slow speech: 20 words over 16 seconds, no punctuation.
        words = steady_words(" ".join(["word"] * 20), per_word=0.8)
        result = cues.build_cues(words)
        for c in result:
            self.assertLessEqual(c["end"] - c["start"], 6.5)

    def test_no_words_lost_ever(self):
        text = ("Accuracy matters, and so does formatting. Subtitles must be readable! "
                "Even when sentences are extremely long and refuse to end anywhere, "
                "the pipeline may never silently drop a single word from the output.")
        words = steady_words(text)
        result = cues.build_cues(words)
        joined = " ".join(c["text"] for c in result)
        self.assertEqual(joined, text)

    def test_constraints_hold_on_stream(self):
        text = ("Long streams of speech need to be broken into readable pieces, "
                "with balanced lines and sane durations. Nothing should overlap. "
                "Gaps should exist between cues, and lines should stay short enough "
                "to read comfortably on a single glance at the screen.")
        result = cues.build_cues(steady_words(text, per_word=0.3))
        self.assertGreater(len(result), 1)
        for i, c in enumerate(result):
            self.assertLessEqual(len(c["lines"]), 2)
            for line in c["lines"]:
                self.assertLessEqual(len(line), 42)
            self.assertGreater(c["end"], c["start"])
            if i + 1 < len(result):
                self.assertLessEqual(c["end"], result[i + 1]["start"])

    def test_hindi_text_supported(self):
        text = "नमस्ते दोस्तों। आज हम एक नया विषय सीखेंगे।"
        result = cues.build_cues(steady_words(text))
        joined = " ".join(c["text"] for c in result)
        self.assertEqual(joined, text)
        self.assertEqual(len(result), 1)  # short sentences merge

    def test_empty_input(self):
        self.assertEqual(cues.build_cues([]), [])
        self.assertEqual(cues.build_cues(None), [])

    def test_single_long_word_capped_at_max_duration(self):
        # Review finding C1: a lone word spanning 9 s must not sit on
        # screen longer than the 6 s maximum.
        result = cues.build_cues([{"text": "Wow", "start": 0.0, "end": 9.0}])
        self.assertEqual(len(result), 1)
        self.assertLessEqual(result[0]["end"] - result[0]["start"],
                             cues.DEFAULTS["max_duration"] + 1e-9)

    def test_backward_word_times_never_overlap_cues(self):
        # Review finding M1: models can emit backward-jumping word times at
        # segment boundaries; cues must stay ordered and non-overlapping.
        words = [
            {"text": "First.", "start": 0.0, "end": 0.5},
            {"text": "Second.", "start": 2.0, "end": 2.5},
            {"text": "Rewound.", "start": 1.0, "end": 1.2},  # goes backward
            {"text": "Onward.", "start": 3.0, "end": 3.4},
        ]
        result = cues.build_cues(words)
        joined = " ".join(c["text"] for c in result)
        self.assertEqual(joined, "First. Second. Rewound. Onward.")
        for i in range(len(result) - 1):
            self.assertLessEqual(result[i]["end"], result[i + 1]["start"])
        for c in result:
            self.assertGreater(c["end"], c["start"])


class TestTiming(unittest.TestCase):
    def test_min_duration_extended_when_room(self):
        words = mk_words([("Hi.", 0.0, 0.3)])
        result = cues.build_cues(words)
        self.assertGreaterEqual(result[0]["end"] - result[0]["start"], 1.0)

    def test_min_gap_between_cues(self):
        text = "First sentence here. Second sentence follows immediately after it."
        result = cues.build_cues(steady_words(text, per_word=0.25))
        for i in range(len(result) - 1):
            gap = result[i + 1]["start"] - result[i]["end"]
            self.assertGreaterEqual(gap, cues.DEFAULTS["min_gap"] - 1e-9)


class TestSerialization(unittest.TestCase):
    def setUp(self):
        self.cues = [
            {"start": 0.0, "end": 2.0, "text": "Hello world.", "lines": ["Hello world."]},
            {"start": 2.5, "end": 5.0, "text": "Second cue here.", "lines": ["Second cue", "here."]},
        ]

    def test_srt_format(self):
        srt = cues.to_srt(self.cues)
        expected = (
            "1\n00:00:00,000 --> 00:00:02,000\nHello world.\n\n"
            "2\n00:00:02,500 --> 00:00:05,000\nSecond cue\nhere.\n"
        )
        self.assertEqual(srt, expected)

    def test_vtt_format(self):
        vtt = cues.to_vtt(self.cues)
        self.assertTrue(vtt.startswith("WEBVTT\n\n"))
        self.assertIn("00:00:02.500 --> 00:00:05.000", vtt)

    def test_txt_sentence_lines(self):
        txt = cues.to_txt(self.cues)
        self.assertEqual(txt, "Hello world.\nSecond cue here.\n")

    def test_empty(self):
        self.assertEqual(cues.to_srt([]), "")
        self.assertEqual(cues.to_vtt([]), "WEBVTT\n")
        self.assertEqual(cues.to_txt([]), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
