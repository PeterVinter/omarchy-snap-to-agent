import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "helper"))
import sources  # noqa: E402


def write(data):
    d = tempfile.mkdtemp()
    p = os.path.join(d, "history.json")
    with open(p, "w") as f:
        f.write(data if isinstance(data, str) else json.dumps(data))
    return p


class NotificationTests(unittest.TestCase):
    def test_newest_first_with_a_limit(self):
        rows = [{"app": "a%d" % i, "summary": "s%d" % i, "body": "b", "ts": 1794865658 - i} for i in range(30)]
        r = sources.list_notifications(write(rows))
        self.assertTrue(r["ok"])
        self.assertEqual(len(r["items"]), sources.NOTIFICATION_LIMIT)
        self.assertEqual(r["items"][0]["app"], "a0")
        self.assertEqual([i["index"] for i in r["items"]][:3], [0, 1, 2])

    def test_empty_and_broken_files_give_named_errors(self):
        self.assertEqual(sources.list_notifications("/no/such")["error"], "no-notifications")
        self.assertEqual(sources.list_notifications(write([]))["error"], "no-notifications")
        self.assertEqual(sources.list_notifications(write("{ nope"))["error"], "notifications-unreadable")
        self.assertEqual(sources.list_notifications(write({"a": 1}))["error"], "notifications-unreadable")

    def test_odd_entries_are_skipped_and_long_text_is_cut(self):
        r = sources.list_notifications(write([1, None, {"summary": ""}, {"app": "x", "summary": "ok", "body": "y" * 5000, "ts": "bad"}]))
        self.assertEqual(len(r["items"]), 1)
        self.assertLessEqual(len(r["items"][0]["body"]), 2000)
        self.assertEqual(r["items"][0]["time"], "")

    def test_text_form(self):
        t = sources.notification_text({"app": "mail", "time": "2026-11-16 10:00:00", "summary": "Hi", "body": "There"})
        self.assertEqual(t, "App: mail\nTime: 2026-11-16 10:00:00\nSummary: Hi\nBody: There")


class ClipboardTests(unittest.TestCase):
    def run_with(self, answers):
        def run(argv, timeout=15, input=None):
            return answers.get(tuple(argv), (1, "", "Nothing is copied"))
        return run

    def test_selection_wins_over_clipboard(self):
        r = sources.read_text_clipboard(self.run_with({("wl-paste", "-p", "-n"): (0, "picked", ""), ("wl-paste", "-n"): (0, "copied", "")}))
        self.assertEqual((r["kind"], r["text"]), ("selection", "picked"))

    def test_clipboard_when_no_selection(self):
        r = sources.read_text_clipboard(self.run_with({("wl-paste", "-n"): (0, "copied", "")}))
        self.assertEqual((r["kind"], r["text"]), ("clipboard", "copied"))

    def test_empty_binary_and_missing(self):
        self.assertEqual(sources.read_text_clipboard(self.run_with({}))["error"], "empty-clipboard")
        self.assertEqual(sources.read_text_clipboard(self.run_with({("wl-paste", "-n"): (0, "a\x00b", "")}))["error"], "empty-clipboard")
        self.assertEqual(sources.read_text_clipboard(lambda a, timeout=15, input=None: (127, "", ""))["error"], "missing-wl-paste")

    def test_text_is_capped(self):
        r = sources.read_text_clipboard(self.run_with({("wl-paste", "-n"): (0, "x" * 100000, "")}))
        self.assertEqual(len(r["text"]), sources.MAX_TEXT)

    def test_image_only_when_png_is_offered(self):
        self.assertFalse(sources.clipboard_image("/tmp/x.png", self.run_with({("wl-paste", "--list-types"): (0, "text/plain\n", "")})))


if __name__ == "__main__":
    unittest.main()
