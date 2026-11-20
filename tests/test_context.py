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

    def test_other_apps_start_in_the_default_directory(self):
        c = context.gather(APP, run=fake(), home="/home/x")
        self.assertEqual(c["cwd"], "/home/x")
        self.assertEqual(c["cwd_from"], "default")
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

    def test_launch_dir_prefers_work_over_home(self):
        import tempfile
        with tempfile.TemporaryDirectory() as home:
            self.assertEqual(context.launch_dir("", home), home)
            self.assertEqual(context.launch_dir(home, home), home)
            os.mkdir(os.path.join(home, "Work"))
            self.assertEqual(context.launch_dir("", home), os.path.join(home, "Work"))
            self.assertEqual(context.launch_dir(home, home), os.path.join(home, "Work"))
            self.assertEqual(context.launch_dir("/no/such/dir", home), os.path.join(home, "Work"))
            self.assertEqual(context.launch_dir("/tmp", home), "/tmp")

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
        none = {"id": 0, "name": ""}
        return 0, json.dumps([{"id": 0, "activeWorkspace": {"id": 1}, "specialWorkspace": none},
                              {"id": 1, "activeWorkspace": {"id": 2}, "specialWorkspace": none}]), ""

    def test_picks_the_most_recent_visible_window_under_the_point(self):
        self.assertEqual(context.window_at(200, 200, self.fake_run)["class"], "front")
        self.assertEqual(context.window_at(900, 900, self.fake_run)["class"], "back")
        self.assertEqual(context.window_at(2100, 100, self.fake_run)["class"], "elsewhere")

    def test_nothing_under_the_point(self):
        self.assertIsNone(context.window_at(5000, 5000, self.fake_run))

    def test_bad_output_is_ignored(self):
        bad = lambda argv, timeout=15, input=None: (0, "not json", "")  # noqa: E731
        self.assertIsNone(context.window_at(1, 1, bad))


class VisibleWindowsTests(unittest.TestCase):
    def run_with(self, clients, monitors, code=0):
        def run(argv, timeout=15, input=None):
            return code, json.dumps(clients if argv[1] == "clients" else monitors), ""
        return context.visible_windows(run)

    def test_special_workspace_windows_count_when_one_is_showing(self):
        clients = [{"class": "normal", "workspace": {"id": 1}}, {"class": "scratch", "workspace": {"id": -98}}]
        shown = self.run_with(clients, [{"activeWorkspace": {"id": 1}, "specialWorkspace": {"id": -98}}])
        self.assertEqual(sorted(w["class"] for w in shown), ["normal", "scratch"])

    def test_a_hidden_special_workspace_does_not_count(self):
        clients = [{"class": "normal", "workspace": {"id": 1}}, {"class": "scratch", "workspace": {"id": -98}}]
        shown = self.run_with(clients, [{"activeWorkspace": {"id": 1}, "specialWorkspace": {"id": 0}}])
        self.assertEqual([w["class"] for w in shown], ["normal"])

    def test_unknown_visibility_is_none_not_empty(self):
        self.assertIsNone(self.run_with([], [], code=1))
        bad = lambda argv, timeout=15, input=None: (0, "not json", "")  # noqa: E731
        self.assertIsNone(context.visible_windows(bad))


# Real `hyprctl ... -j` layouts, read from the Hyprland sources (src/debug/HyprCtl.cpp at v0.56.2,
# src/ipc/s1/Commands.cpp at v0.57.2). 0.57 identifies a workspace by `address`; only numbered
# workspaces keep an `id`, and a special workspace never has one.
def ws56(wid, name=""):
    return {"id": wid, "name": name or str(wid)}


def ws57(address, numbered=None, special=False):
    w = {"address": address, "type": "special" if special else "normal", "name": address}
    if numbered is not None:
        w["id"] = numbered
    return w


NO_SPECIAL_57 = {"address": "", "type": "", "name": ""}


class Hyprland057Tests(unittest.TestCase):
    def run_with(self, clients, monitors):
        def run(argv, timeout=15, input=None):
            return 0, json.dumps(clients if argv[1] == "clients" else monitors), ""
        return context.visible_windows(run)

    def classes(self, shown):
        return sorted(w["class"] for w in shown)

    def test_a_showing_special_workspace_counts(self):
        clients = [{"class": "normal", "workspace": ws57("1", 1)},
                   {"class": "scratch", "workspace": ws57("special:magic", special=True)},
                   {"class": "away", "workspace": ws57("2", 2)}]
        monitors = [{"activeWorkspace": ws57("1", 1), "specialWorkspace": ws57("special:magic", special=True)}]
        self.assertEqual(self.classes(self.run_with(clients, monitors)), ["normal", "scratch"])

    def test_no_special_workspace_showing(self):
        clients = [{"class": "normal", "workspace": ws57("1", 1)},
                   {"class": "scratch", "workspace": ws57("special:magic", special=True)}]
        monitors = [{"activeWorkspace": ws57("1", 1), "specialWorkspace": NO_SPECIAL_57}]
        self.assertEqual(self.classes(self.run_with(clients, monitors)), ["normal"])

    def test_a_named_normal_workspace_has_no_id_and_still_matches(self):
        clients = [{"class": "named", "workspace": ws57("work")}]
        monitors = [{"activeWorkspace": ws57("work"), "specialWorkspace": NO_SPECIAL_57}]
        self.assertEqual(self.classes(self.run_with(clients, monitors)), ["named"])

    def test_two_special_workspaces_are_told_apart(self):
        clients = [{"class": "a", "workspace": ws57("special:a", special=True)},
                   {"class": "b", "workspace": ws57("special:b", special=True)}]
        monitors = [{"activeWorkspace": ws57("1", 1), "specialWorkspace": ws57("special:b", special=True)}]
        self.assertEqual(self.classes(self.run_with(clients, monitors)), ["b"])

    def test_two_monitors(self):
        clients = [{"class": "one", "workspace": ws57("1", 1)}, {"class": "two", "workspace": ws57("2", 2)},
                   {"class": "three", "workspace": ws57("3", 3)}]
        monitors = [{"activeWorkspace": ws57("1", 1), "specialWorkspace": NO_SPECIAL_57},
                    {"activeWorkspace": ws57("2", 2), "specialWorkspace": NO_SPECIAL_57}]
        self.assertEqual(self.classes(self.run_with(clients, monitors)), ["one", "two"])

    def test_window_at_reads_the_new_layout(self):
        clients = [{"class": "scratch", "at": [0, 0], "size": [100, 100], "workspace": ws57("special:magic", special=True)}]
        monitors = [{"activeWorkspace": ws57("1", 1), "specialWorkspace": ws57("special:magic", special=True)}]
        run = lambda argv, timeout=15, input=None: (0, json.dumps(clients if argv[1] == "clients" else monitors), "")  # noqa: E731
        self.assertEqual(context.window_at(5, 5, run)["class"], "scratch")


class UnknownLayoutTests(unittest.TestCase):
    """When the layout is not one we know, visibility is unknown: None, never an empty list."""

    def run_with(self, clients, monitors):
        def run(argv, timeout=15, input=None):
            return 0, json.dumps(clients if argv[1] == "clients" else monitors), ""
        return context.visible_windows(run)

    GOOD_CLIENT = {"class": "x", "workspace": ws56(1)}

    def test_a_monitor_without_a_special_workspace_field(self):
        self.assertIsNone(self.run_with([self.GOOD_CLIENT], [{"activeWorkspace": ws56(1)}]))

    def test_a_special_workspace_with_neither_address_nor_id(self):
        self.assertIsNone(self.run_with([self.GOOD_CLIENT], [{"activeWorkspace": ws56(1), "specialWorkspace": {"name": "x"}}]))

    def test_a_future_layout_without_address_or_id_on_the_active_workspace(self):
        self.assertIsNone(self.run_with([self.GOOD_CLIENT], [{"activeWorkspace": {"name": "1"}, "specialWorkspace": ws56(0)}]))

    def test_a_visible_client_whose_workspace_cannot_be_read(self):
        monitors = [{"activeWorkspace": ws56(1), "specialWorkspace": ws56(0)}]
        self.assertIsNone(self.run_with([{"class": "x", "workspace": {"name": "?"}}], monitors))

    def test_an_unreadable_client_that_is_hidden_does_not_stop_the_capture(self):
        monitors = [{"activeWorkspace": ws56(1), "specialWorkspace": ws56(0)}]
        clients = [self.GOOD_CLIENT, {"class": "gone", "hidden": True, "workspace": {"name": "?"}}]
        self.assertEqual([w["class"] for w in self.run_with(clients, monitors)], ["x"])

    def test_wrong_types(self):
        for monitors in ({"a": 1}, [None], [{"activeWorkspace": {"id": "1"}, "specialWorkspace": ws56(0)}],
                         [{"activeWorkspace": ws56(1), "specialWorkspace": {"id": "x"}}],
                         [{"activeWorkspace": ws56(1), "specialWorkspace": {"address": 5}}]):
            self.assertIsNone(self.run_with([self.GOOD_CLIENT], monitors), monitors)

    def test_clients_that_are_not_objects(self):
        self.assertIsNone(self.run_with(["x"], [{"activeWorkspace": ws56(1), "specialWorkspace": ws56(0)}]))

    def test_window_at_gives_up_on_an_unknown_layout(self):
        run = lambda argv, timeout=15, input=None: (0, json.dumps([{"at": [0, 0], "size": [9, 9], "workspace": {"name": "?"}}]  # noqa: E731
                                                                  if argv[1] == "clients" else [{"activeWorkspace": ws56(1), "specialWorkspace": ws56(0)}]), "")
        self.assertIsNone(context.window_at(1, 1, run))


if __name__ == "__main__":
    unittest.main()
