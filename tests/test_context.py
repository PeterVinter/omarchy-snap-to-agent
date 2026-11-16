import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "helper"))
import context  # noqa: E402


def fake(overrides=None):
    answers = {
        "hyprctl": (0, json.dumps([{"id": 0, "name": "DP-1"}, {"id": 1, "name": "HDMI-A-1"}]), ""),
        "omarchy-cmd-terminal-cwd": (0, "/tmp\n", ""),
        "git": (0, "feature/x\n", ""),
        "journalctl": (0, "2026-11-16T10:00:00 foo[1]: something failed\n", ""),
        "omarchy": (0, "4.5.0-3\n", ""),
    }
    answers.update(overrides or {})

    def run(argv, timeout=15, input=None):
        if argv[0] == "git" and "status" in argv:
            return 0, " M file\n", ""
        return answers.get(argv[0], (127, "", ""))
    return run


TERM = {"class": "foot", "title": "~/Work", "pid": 4242, "monitor": 1, "workspace": {"id": 2, "name": "2"}}
APP = {"class": "chromium", "title": "Page", "pid": 99, "monitor": 0, "workspace": {"id": 1, "name": "1"}}


class ContextTests(unittest.TestCase):
    def test_terminal_window_gets_cwd_and_git(self):
        c = context.gather(TERM, run=fake(), home="/home/x")
        self.assertEqual(c["cwd"], "/tmp")
        self.assertEqual(c["cwd_from"], "terminal")
        self.assertEqual(c["git"], {"branch": "feature/x", "dirty": True})
        self.assertEqual(c["monitor"], "HDMI-A-1")
        self.assertEqual(c["workspace"], "2")
        self.assertEqual(c["omarchy_version"], "4.5.0-3")
        self.assertIn("something failed", c["logs"])

    def test_other_apps_start_in_home(self):
        c = context.gather(APP, run=fake(), home="/home/x")
        self.assertEqual(c["cwd"], "/home/x")
        self.assertEqual(c["cwd_from"], "home")
        self.assertIsNone(c["git"])
        self.assertFalse(c["terminal"])

    def test_omarchy_tui_windows_count_as_terminals(self):
        self.assertTrue(context.is_terminal("org.omarchy.agent"))
        self.assertTrue(context.is_terminal("Alacritty"))
        self.assertFalse(context.is_terminal("chromium"))

    def test_missing_tools_do_not_break_it(self):
        nothing = lambda argv, timeout=15, input=None: (127, "", "")  # noqa: E731
        c = context.gather(TERM, run=nothing, home="/home/x")
        self.assertEqual(c["cwd"], "/home/x")
        self.assertEqual(c["logs"], "")
        self.assertEqual(c["omarchy_version"], "")

    def test_no_window_still_gives_a_record(self):
        c = context.gather(None, run=fake(), home="/home/x")
        self.assertEqual(c["app_class"], "")
        self.assertEqual(c["cwd"], "/home/x")

    def test_bad_values_are_rejected(self):
        self.assertEqual(context.terminal_cwd("123; rm"), "")
        self.assertEqual(context.recent_logs("abc"), "")
        self.assertEqual(context.omarchy_version(fake({"omarchy": (0, "4.5; rm -rf\n", "")})), "")
        rel = fake({"omarchy-cmd-terminal-cwd": (0, "relative/dir\n", "")})
        self.assertEqual(context.terminal_cwd(5000, rel), "")

    def test_logs_are_capped(self):
        big = "x" * 50000
        c = context.gather(TERM, run=fake({"journalctl": (0, big, "")}), home="/home/x")
        self.assertLessEqual(len(c["logs"]), context.MAX_LOG_BYTES)

    def test_tilde(self):
        self.assertEqual(context.tilde("/home/x/Work/a", "/home/x"), "~/Work/a")
        self.assertEqual(context.tilde("/home/x", "/home/x"), "~")
        self.assertEqual(context.tilde("/home/xy", "/home/x"), "/home/xy")


class WindowAtTests(unittest.TestCase):
    CLIENTS = [
        {"class": "back", "at": [0, 0], "size": [1000, 1000], "workspace": {"id": 1}, "focusHistoryID": 3, "mapped": True},
        {"class": "front", "at": [100, 100], "size": [300, 300], "workspace": {"id": 1}, "focusHistoryID": 0, "mapped": True},
        {"class": "hidden", "at": [100, 100], "size": [300, 300], "workspace": {"id": 1}, "focusHistoryID": 0, "hidden": True},
        {"class": "other-ws", "at": [100, 100], "size": [300, 300], "workspace": {"id": 7}, "focusHistoryID": 0},
        {"class": "elsewhere", "at": [2000, 0], "size": [500, 500], "workspace": {"id": 2}, "focusHistoryID": 1},
    ]

    def fake_run(self, argv, timeout=15, input=None):
        if argv[:2] == ["hyprctl", "clients"]:
            return 0, json.dumps(self.CLIENTS), ""
        return 0, json.dumps([{"id": 0, "activeWorkspace": {"id": 1}}, {"id": 1, "activeWorkspace": {"id": 2}}]), ""

    def test_picks_the_most_recent_visible_window_under_the_point(self):
        self.assertEqual(context.window_at(200, 200, self.fake_run)["class"], "front")
        self.assertEqual(context.window_at(900, 900, self.fake_run)["class"], "back")
        self.assertEqual(context.window_at(2100, 100, self.fake_run)["class"], "elsewhere")

    def test_nothing_under_the_point(self):
        self.assertIsNone(context.window_at(5000, 5000, self.fake_run))

    def test_bad_output_is_ignored(self):
        bad = lambda argv, timeout=15, input=None: (0, "not json", "")  # noqa: E731
        self.assertIsNone(context.window_at(1, 1, bad))


if __name__ == "__main__":
    unittest.main()
