import json
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "helper"))
import compose  # noqa: E402
import history  # noqa: E402
import mask  # noqa: E402
import snap  # noqa: E402

KEY = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
PWD_LINE = "DB_PASSWORD=hunter2hunter2"


def state():
    return {"mode": "clipboard", "capture": {"path": "/x/a.png", "width": 10},
            "context": {"title": "term", "log": "token=%s" % KEY, "git": {"branch": "main"}},
            "source": {"kind": "clipboard", "text": "use %s here\n%s" % (KEY, PWD_LINE)},
            "ocr": {"text": "found %s on screen" % KEY, "missing": False}}


class ScrubTests(unittest.TestCase):
    def test_every_text_is_masked_and_the_rest_is_kept(self):
        out = mask.scrub_state(state())
        dumped = json.dumps(out)
        self.assertNotIn(KEY, dumped)
        self.assertNotIn("hunter2hunter2", dumped)
        self.assertIn("[MASKED:github-token:", out["source"]["text"])
        self.assertEqual(out["capture"], {"path": "/x/a.png", "width": 10})
        self.assertEqual(out["context"]["git"], {"branch": "main"})
        self.assertEqual(out["mode"], "clipboard")

    def test_the_input_is_not_changed(self):
        s = state()
        mask.scrub_state(s)
        self.assertIn(KEY, s["source"]["text"])

    def test_ocr_keeps_which_secrets_the_picture_showed(self):
        out = mask.scrub_state(state())
        self.assertEqual(out["ocr"]["secret_kinds"], ["github-token"])
        again = mask.scrub_state(out)  # scrubbing twice must not lose the warning
        self.assertEqual(again["ocr"]["secret_kinds"], ["github-token"])

    def test_send_again_still_warns_about_the_screenshot(self):
        saved = mask.scrub_state(state())
        r = compose.compose("q", {}, saved["capture"], "region", agent="claude", ocr_text=saved["ocr"]["text"],
                            ocr_secret_kinds=saved["ocr"]["secret_kinds"])
        self.assertEqual(r["image_secrets"], ["github-token"])
        self.assertEqual(compose.compose("q", {}, saved["capture"], "region", agent="claude")["image_secrets"], [])


class DiskTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SNAP_TO_AGENT_CACHE"] = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop("SNAP_TO_AGENT_CACHE", None)

    def all_text(self):
        out = ""
        for name in os.listdir(self.tmp.name):
            path = os.path.join(self.tmp.name, name)
            if os.path.isfile(path) and not name.endswith(".png"):
                out += open(path, encoding="utf-8").read()
        return out

    def test_last_json_holds_no_raw_secret(self):
        snap.save_last(state())
        text = self.all_text()
        self.assertIn("last.json", os.listdir(self.tmp.name))
        self.assertNotIn(KEY, text)
        self.assertNotIn("hunter2hunter2", text)
        self.assertEqual(oct(os.stat(os.path.join(self.tmp.name, "last.json")).st_mode & 0o777), "0o600")

    def test_history_holds_no_raw_secret(self):
        history.add(state(), "why?", {"program": "claude", "display": "Claude Code", "cwd": "/tmp", "file": ""}, "clipboard")
        text = self.all_text()
        self.assertTrue(any(n.endswith(".state.json") for n in os.listdir(self.tmp.name)))
        self.assertNotIn(KEY, text)
        self.assertNotIn("hunter2hunter2", text)

    def test_retention_cleanup_removes_an_old_last_json(self):
        snap.save_last(state())
        path = os.path.join(self.tmp.name, "last.json")
        old = time.time() - 10 * 86400
        os.utime(path, (old, old))
        history.cleanup(7)
        self.assertFalse(os.path.exists(path))
        snap.save_last(state())
        history.cleanup(7)
        self.assertTrue(os.path.exists(path))  # a fresh one stays


class LegacyFileTests(unittest.TestCase):
    """Files written by 0.3.x and 0.4.0 hold the raw text; they must not survive an upgrade."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SNAP_TO_AGENT_CACHE"] = self.tmp.name
        self.last = os.path.join(self.tmp.name, "last.json")
        self.entry = os.path.join(self.tmp.name, "20260101-120000-000.state.json")
        for path in (self.last, self.entry):
            with open(path, "w", encoding="utf-8") as f:
                json.dump(state(), f)  # the old format: raw

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop("SNAP_TO_AGENT_CACHE", None)

    def raw_left(self):
        return [p for p in (self.last, self.entry) if KEY in open(p).read() or "hunter2hunter2" in open(p).read()]

    def test_scrub_legacy_masks_old_files_in_place(self):
        self.assertEqual(len(self.raw_left()), 2)
        self.assertEqual(history.scrub_legacy(), 2)
        self.assertEqual(self.raw_left(), [])
        self.assertEqual(history.scrub_legacy(), 0)  # idempotent: nothing left to change
        self.assertEqual(json.load(open(self.last))["ocr"]["secret_kinds"], ["github-token"])

    def test_the_cleanup_every_capture_runs_scrubs_them_even_with_retention_off(self):
        snap._cleanup({"retention_days": 0})
        self.assertEqual(self.raw_left(), [])
        self.assertTrue(os.path.exists(self.last))  # scrubbed, not deleted

    def test_send_again_never_returns_the_raw_text_from_an_old_last_json(self):
        out = snap.cmd_last([])
        self.assertTrue(out["ok"] or out["error"] == "no-last")
        self.assertNotIn(KEY, json.dumps(out))
        self.assertEqual(self.raw_left(), [p for p in [self.entry]])  # only the file not asked for yet

    def test_opening_an_old_history_entry_never_returns_the_raw_text(self):
        out = history.open_state("20260101-120000-000")
        self.assertNotIn(KEY, json.dumps(out))
        self.assertNotIn("hunter2hunter2", json.dumps(out))
        self.assertEqual(self.raw_left(), [self.last])

    def test_a_broken_or_foreign_file_is_left_alone(self):
        with open(self.last, "w") as f:
            f.write("not json")
        with open(self.entry, "w") as f:
            f.write("[1, 2]")
        self.assertEqual(history.scrub_legacy(), 0)
        self.assertEqual(open(self.last).read(), "not json")


if __name__ == "__main__":
    unittest.main()
