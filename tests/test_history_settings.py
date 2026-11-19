import json
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "helper"))
import config  # noqa: E402
import history  # noqa: E402


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SNAP_TO_AGENT_CACHE"] = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop("SNAP_TO_AGENT_CACHE", None)

    def make(self, n=1, image=True):
        path = ""
        if image:
            path = os.path.join(self.tmp.name, "shot-%d.png" % n)
            with open(path, "wb") as f:
                f.write(b"png")
        state = {"mode": "region", "capture": {"path": path} if image else None, "context": {"app_class": "foot", "logs": "token=abc123456"},
                 "source": None, "ocr": {"text": "x"}}
        time.sleep(0.002)
        return history.add(state, "why?", {"program": "claude", "display": "Claude Code", "cwd": "/tmp/x", "file": ""}, "region")

    def test_add_list_open_delete(self):
        a = self.make(1)
        entries = history.listing()
        self.assertEqual(len(entries), 1)
        self.assertEqual((entries[0]["display"], entries[0]["cwd"], entries[0]["question"]), ("Claude Code", "/tmp/x", "why?"))
        self.assertTrue(entries[0]["thumb"].endswith("shot-1.png"))
        state = history.open_state(a)
        self.assertEqual(state["question"], "why?")
        self.assertEqual(state["mode"], "region")
        self.assertTrue(history.delete(a))
        self.assertEqual(history.listing(), [])
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "shot-1.png")))
        self.assertIsNone(history.open_state(a))
        self.assertFalse(history.delete(a))

    def test_newest_first_and_capped_at_twenty(self):
        ids = [self.make(i) for i in range(25)]
        listed = [e["id"] for e in history.listing()]
        self.assertEqual(len(listed), history.MAX_ENTRIES)
        self.assertEqual(listed[0], ids[-1])
        # The five dropped entries lose their files too.
        for i in range(5):
            self.assertFalse(os.path.exists(os.path.join(self.tmp.name, ids[i] + ".state.json")))
            self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "shot-%d.png" % i)))

    def test_files_have_private_modes_and_ids_are_checked(self):
        a = self.make()
        self.assertEqual(oct(os.stat(os.path.join(self.tmp.name, a + ".state.json")).st_mode & 0o777), "0o600")
        self.assertEqual(oct(os.stat(os.path.join(self.tmp.name, "history.json")).st_mode & 0o777), "0o600")
        for bad in ["../../etc/passwd", "x", "", "20261116-230000-000/../a"]:
            self.assertIsNone(history.open_state(bad))
            self.assertFalse(history.delete(bad))

    def test_delete_never_removes_files_outside_the_cache(self):
        outside = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        outside.close()
        try:
            entry_id = history.add({"mode": "region", "capture": {"path": outside.name}, "context": {}}, "q",
                                   {"program": "claude", "display": "C", "cwd": "/", "file": ""}, "region")
            history.delete(entry_id)
            self.assertTrue(os.path.exists(outside.name))
        finally:
            os.remove(outside.name)

    def test_broken_history_file_is_an_empty_history(self):
        with open(os.path.join(self.tmp.name, "history.json"), "w") as f:
            f.write("{ nope")
        self.assertEqual(history.listing(), [])
        self.make()
        self.assertEqual(len(history.listing()), 1)

    def test_unmasked_context_files_expire_after_an_hour_even_with_retention_off(self):
        old = os.path.join(self.tmp.name, "a-context-open.md")
        fresh = os.path.join(self.tmp.name, "b-context-open.md")
        masked = os.path.join(self.tmp.name, "c-context.md")
        for p in (old, fresh, masked):
            with open(p, "w") as f:
                f.write("x")
        t = time.time() - 2 * 3600
        os.utime(old, (t, t))
        os.utime(masked, (t, t))
        self.assertEqual(history.cleanup(0), 1)
        self.assertFalse(os.path.exists(old))
        self.assertTrue(os.path.exists(fresh))
        self.assertTrue(os.path.exists(masked))  # masked files follow the retention setting

    def test_cleanup_removes_only_old_owned_files(self):
        old = self.make(1)
        keep = self.make(2)
        long_ago = time.time() - 9 * 86400
        for name in (old + ".state.json", "shot-1.png"):
            os.utime(os.path.join(self.tmp.name, name), (long_ago, long_ago))
        stranger = os.path.join(self.tmp.name, "notes.txt")
        with open(stranger, "w") as f:
            f.write("mine")
        os.utime(stranger, (long_ago, long_ago))
        entries = history.load()
        entries[-1]["time"] = int(long_ago)
        history._write(history._path(), entries)
        self.assertEqual(history.cleanup(7), 2)
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "shot-1.png")))
        self.assertTrue(os.path.exists(os.path.join(self.tmp.name, "shot-2.png")))
        self.assertTrue(os.path.exists(stranger))
        self.assertEqual([e["id"] for e in history.listing()], [keep])

    def test_zero_days_keeps_everything(self):
        self.make()
        long_ago = time.time() - 400 * 86400
        for name in os.listdir(self.tmp.name):
            os.utime(os.path.join(self.tmp.name, name), (long_ago, long_ago))
        self.assertEqual(history.cleanup(0), 0)
        self.assertTrue(os.path.exists(os.path.join(self.tmp.name, "shot-1.png")))


class SaveSettingsTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "snap-to-agent", "config.json")

    def test_save_merges_validates_and_keeps_private(self):
        out = config.save({"retention_days": 30, "ocr": False, "image": {"max_edge": 100, "max_bytes": 99_999_999},
                           "questions": {"error": "Fix it", "window": 5}, "evil": "x", "hook": "no"}, self.path)
        self.assertEqual(out["retention_days"], 30)
        self.assertFalse(out["ocr"])
        self.assertEqual(out["image"], {"max_edge": 200, "max_bytes": 20_000_000})
        self.assertEqual(out["questions"], {"error": "Fix it"})
        self.assertNotIn("evil", out)
        self.assertFalse(out["hook"])
        self.assertEqual(oct(os.stat(self.path).st_mode & 0o777), "0o600")
        again = config.save({"retention_days": 99999}, self.path)
        self.assertEqual(again["retention_days"], 3650)
        self.assertFalse(again["ocr"])  # earlier choice stays

    def test_blocklist_edits_round_trip(self):
        config.save({"blocklist": {"classes": ["  MyVault ", ""], "titles": ["Secret Bank"]}}, self.path)
        loaded = config.load(self.path)
        self.assertEqual(loaded["blocklist"]["classes"], ["myvault"])
        self.assertEqual(loaded["blocklist"]["titles"], ["secret bank"])

    def test_non_dict_updates_change_nothing_and_reset_restores_defaults(self):
        config.save({"retention_days": 3}, self.path)
        self.assertEqual(config.save("junk", self.path)["retention_days"], 3)
        self.assertEqual(config.reset(self.path)["retention_days"], 7)
        self.assertFalse(os.path.exists(self.path))


if __name__ == "__main__":
    unittest.main()
