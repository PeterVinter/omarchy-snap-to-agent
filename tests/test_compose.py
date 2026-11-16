import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "helper"))
import compose  # noqa: E402

CTX = {"app_class": "foot", "title": "build failed in ~/Work/foo", "workspace": "2", "monitor": "HDMI-A-1",
       "cwd": "/tmp", "git": {"branch": "feature/x", "dirty": True}, "omarchy_version": "4.5.0-3",
       "time": "2026-11-16 23:00:00 +0100",
       "logs": "Nov 16 app[1]: using token=ghp_0123456789abcdefghijklmnopqrstuvwxyzAB now"}
SHOT = {"path": "/tmp/x/20261116-230000-000.png", "width": 1920, "height": 1080}


class ComposeTests(unittest.TestCase):
    def test_block_has_the_expected_facts(self):
        b = compose.context_block(CTX, SHOT, "region")
        for want in ["App: foot", "build failed", "workspace 2, monitor HDMI-A-1", "Directory: /tmp (git: feature/x, uncommitted changes)",
                     "Omarchy: 4.5.0-3", "Screenshot: /tmp/x/20261116-230000-000.png (1920x1080)", "### Recent log lines"]:
            self.assertIn(want, b)

    def test_focused_window_fallback_is_flagged_for_regions(self):
        b = compose.context_block(dict(CTX, window_source="focused"), SHOT, "region")
        self.assertIn("no window was found under the selected region", b)
        self.assertNotIn("no window was found", compose.context_block(dict(CTX, window_source="under-region"), SHOT, "region"))
        self.assertNotIn("no window was found", compose.context_block(dict(CTX, window_source="focused"), SHOT, "window"))

    def test_text_only_leaves_the_image_out(self):
        b = compose.context_block(CTX, SHOT, "region", send_image=False)
        self.assertNotIn("20261116-230000-000.png", b)
        self.assertIn("not sent (text only)", b)

    def test_fence_is_longer_than_backticks_in_content(self):
        b = compose.context_block(dict(CTX, logs="a ``` b"), SHOT)
        self.assertIn("````\na ``` b\n````", b)

    def test_secrets_never_reach_the_prompt(self):
        r = compose.compose("why does GITHUB_TOKEN=ghp_0123456789abcdefghijklmnopqrstuvwxyzAB fail?", CTX, SHOT, "region", agent="claude")
        self.assertNotIn("ghp_0123456789", r["prompt"])
        self.assertNotIn("ghp_0123456789", r["context"])
        self.assertNotIn("ghp_0123456789", r["question"])
        self.assertTrue(all("original" not in f for f in r["findings"]))
        self.assertGreaterEqual(len(r["findings"]), 2)
        self.assertIn("likely secret(s) were replaced", r["prompt"])

    def test_undo_one_masking(self):
        r = compose.compose("x", CTX, SHOT, "region", agent="claude")
        fid = r["findings"][0]["id"]
        again = compose.compose("x", CTX, SHOT, "region", agent="claude", allow=[fid])
        self.assertIn("ghp_0123456789", again["prompt"])
        self.assertFalse(again["findings"][0]["masked"])

    def test_edited_context_is_used_and_still_masked(self):
        r = compose.compose("x", CTX, SHOT, "region", agent="claude",
                            context_text="my notes password=hunter22pass")
        self.assertIn("my notes", r["prompt"])
        self.assertNotIn("hunter22pass", r["prompt"])
        self.assertNotIn("Screenshot:", r["prompt"])

    def test_source_text_block_for_text_modes(self):
        src = {"kind": "error", "text": "Command: make\nExit code: 2\n\nOutput:\nboom"}
        r = compose.compose("", CTX, None, "error", agent="claude", source=src)
        self.assertIn("### The failed command", r["context"])
        self.assertIn("Exit code: 2", r["prompt"])
        self.assertFalse(r["has_image"])
        self.assertNotIn("image_path_only", r["notes"])
        self.assertNotIn("Screenshot:", r["prompt"])

    def test_source_text_is_masked(self):
        src = {"kind": "clipboard", "text": "export TOKEN=ghp_0123456789abcdefghijklmnopqrstuvwxyzAB"}
        r = compose.compose("q", dict(CTX, logs=""), None, "clipboard", agent="claude", source=src)
        self.assertNotIn("ghp_0123456789", r["prompt"])

    def test_secrets_visible_in_the_image_warn_and_text_only_drops_the_image(self):
        ocr_text = "GITHUB_TOKEN=ghp_0123456789abcdefghijklmnopqrstuvwxyzAB"
        r = compose.compose("q", dict(CTX, logs=""), SHOT, "region", agent="claude", ocr_text=ocr_text)
        self.assertIn("image_has_secrets", r["notes"])
        self.assertEqual(r["image_secrets"], ["github-token"])
        self.assertNotIn("ghp_0123456789", r["prompt"])
        t = compose.compose("q", dict(CTX, logs=""), SHOT, "region", agent="claude", ocr_text=ocr_text, send_image=False)
        self.assertIn("image_not_sent", t["notes"])
        self.assertNotIn("image_has_secrets", t["notes"])
        self.assertNotIn("20261116-230000-000.png", t["prompt"])
        self.assertIn("MASKED:github-token", t["prompt"])

    def test_missing_ocr_is_noted_but_does_not_block(self):
        r = compose.compose("q", CTX, SHOT, "region", agent="claude", ocr_missing=True)
        self.assertIn("ocr_missing", r["notes"])
        self.assertTrue(r["ok"])

    def test_question_overrides_come_from_config(self):
        r = compose.compose("", CTX, SHOT, "error", agent="claude", questions={"error": "Fix this please"})
        self.assertEqual(r["question"], "Fix this please")
        r = compose.compose("", CTX, SHOT, "error", agent="claude", questions={"error": "  "})
        self.assertEqual(r["question"], "Explain this error and suggest a fix.")

    def test_default_source_tells_where_the_question_came_from(self):
        self.assertEqual(compose.compose("mine", CTX, SHOT, "error", agent="claude")["default_source"], "user")
        self.assertEqual(compose.compose("", CTX, SHOT, "error", agent="claude")["default_source"], "builtin")
        self.assertEqual(compose.compose("", CTX, SHOT, "error", agent="claude", questions={"error": "Fix"})["default_source"], "config")

    def test_auto_mode_is_flagged_only_when_on_and_only_where_it_applies(self):
        self.assertNotIn("auto_mode", compose.compose("q", CTX, SHOT, "region", agent="claude")["notes"])
        self.assertIn("auto_mode", compose.compose("q", CTX, SHOT, "region", agent="claude", auto=True)["notes"])
        self.assertNotIn("auto_mode", compose.compose("q", CTX, SHOT, "region", agent="pi", auto=True)["notes"])

    def test_default_question_per_mode(self):
        r = compose.compose("  ", CTX, SHOT, "error", agent="claude")
        self.assertEqual(r["question"], "Explain this error and suggest a fix.")

    def test_target_notes(self):
        self.assertIn("generic_agent", compose.compose("q", CTX, SHOT, "region", agent="new-agent")["notes"])
        self.assertIn("clipboard_paste", compose.compose("q", CTX, SHOT, "region", agent="kimi")["notes"])
        self.assertIn("image_path_only", compose.compose("q", CTX, SHOT, "region", agent="claude")["notes"])
        t = compose.compose("q", dict(CTX, cwd="/tmp"), SHOT, "region", agent="claude")["target"]
        self.assertEqual(t["cwd"], "/tmp")
        self.assertEqual(t["display"], "Claude Code")

    def test_missing_directory_falls_back_to_work_then_home(self):
        with tempfile.TemporaryDirectory() as home:
            old = os.environ.get("HOME")
            os.environ["HOME"] = home
            try:
                t = compose.compose("q", dict(CTX, cwd="/no/such/dir"), SHOT, "region", agent="claude")["target"]
                self.assertEqual(t["cwd"], home)
                os.mkdir(os.path.join(home, "Work"))
                t = compose.compose("q", dict(CTX, cwd="/no/such/dir"), SHOT, "region", agent="claude")["target"]
                self.assertEqual(t["cwd"], os.path.join(home, "Work"))
                self.assertEqual(t["cwd_display"], "~/Work")
            finally:
                os.environ["HOME"] = old

    def test_no_default_agent_is_reported(self):
        with tempfile.TemporaryDirectory() as home:
            old = os.environ.get("XDG_CONFIG_HOME")
            os.environ["XDG_CONFIG_HOME"] = home
            try:
                r = compose.compose("q", CTX, SHOT, "region")
            finally:
                os.environ.pop("XDG_CONFIG_HOME") if old is None else os.environ.__setitem__("XDG_CONFIG_HOME", old)
        self.assertFalse(r["ok"])
        self.assertEqual(r["target"]["problem"], "missing-file")
        self.assertIn("no_default_agent", r["notes"])

    def test_oversize_context_goes_to_a_file(self):
        with tempfile.TemporaryDirectory() as d:
            shot = dict(SHOT, path=os.path.join(d, "a.png"))
            big = dict(CTX, logs="line\n" * 30000)
            r = compose.compose("q", big, shot, "region", agent="claude", write_file=True)
            self.assertTrue(r["oversize"])
            self.assertTrue(os.path.exists(r["file"]))
            self.assertEqual(oct(os.stat(r["file"]).st_mode & 0o777), "0o600")
            self.assertIn(r["file"], r["prompt"])
            self.assertLess(len(r["prompt"]), 500)
            self.assertGreater(len(r["full_prompt"]), compose.INLINE_LIMIT)
            self.assertIn("context_in_file", r["notes"])


if __name__ == "__main__":
    unittest.main()
