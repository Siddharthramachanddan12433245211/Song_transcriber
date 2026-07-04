"""GUI smoke test: window builds, options collect correctly, teardown clean.
Skips gracefully in a display-less environment."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestGuiSmoke(unittest.TestCase):
    def setUp(self):
        try:
            import tkinter
            self.root = tkinter.Tk()
            self.root.withdraw()
        except Exception as e:  # headless CI etc.
            self.skipTest("no display: %s" % e)

    def tearDown(self):
        try:
            self.root.destroy()
        except Exception:
            pass

    def test_app_builds_and_collects_options(self):
        from shabd import gui
        app = gui.App(self.root)

        opts = app.collect_options()
        self.assertIn(opts["tier"], ("fast", "balanced", "high", "max"))
        self.assertEqual(opts["language"], "auto")
        self.assertEqual(opts["task"], "transcribe")
        self.assertEqual(opts["formats"], ["srt"])
        self.assertIsNone(opts["output_dir"])
        self.assertFalse(opts["overwrite"])
        self.assertIsNone(opts["vocab"])

        # user-changed widgets flow through
        app.lang_var.set("hi — Hindi")
        app.fmt_txt.set(True)
        app.vocab_var.set("Shabd, Ryzen")
        opts = app.collect_options()
        self.assertEqual(opts["language"], "hi")
        self.assertEqual(opts["formats"], ["srt", "txt"])
        self.assertEqual(opts["vocab"], "Shabd, Ryzen")

    def test_typed_language_code_accepted(self):
        from shabd import gui
        app = gui.App(self.root)
        app.lang_var.set("sw")  # typed ISO code, not from the list
        self.assertEqual(app.collect_options()["language"], "sw")


if __name__ == "__main__":
    unittest.main(verbosity=2)
