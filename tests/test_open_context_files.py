"""Unmasked context files (`*-context-open.md`) must not outlive the agent start or the sweep limit."""
import os
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "helper"))
import history  # noqa: E402
import snap  # noqa: E402

HELPER = os.path.join(os.path.dirname(__file__), "..", "helper")


class OpenContextFileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.realpath(self.tmp.name)
        os.environ["SNAP_TO_AGENT_CACHE"] = self.dir

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop("SNAP_TO_AGENT_CACHE", None)

    def file(self, name, age=0):
        p = os.path.join(self.dir, name)
        with open(p, "w") as f:
            f.write("x")
        if age:
            t = time.time() - age
            os.utime(p, (t, t))
        return p

    def test_the_sweep_runs_on_every_helper_call_not_only_on_capture(self):
        old = self.file("a-context-open.md", age=history.OPEN_TTL + 60)
        fresh = self.file("b-context-open.md")
        with mock.patch("builtins.print"):
            snap.main(["agent"])  # any command, not a capture
        self.assertFalse(os.path.exists(old))
        self.assertTrue(os.path.exists(fresh))

    def test_the_sweep_leaves_masked_context_files_to_the_retention_setting(self):
        masked = self.file("c-context.md", age=10 * 86400)
        history.sweep_open_files()
        self.assertTrue(os.path.exists(masked))

    def test_a_removal_is_scheduled_for_an_open_file_only(self):
        spawn = mock.Mock()
        opened = self.file("a-context-open.md")
        masked = self.file("b-context.md")
        self.assertTrue(history.remove_open_file_later(opened, delay=5, spawn=spawn))
        argv = spawn.call_args[0][0]
        self.assertEqual(argv[-2:], ["5", opened])
        self.assertTrue(spawn.call_args[1]["start_new_session"])
        spawn.reset_mock()
        self.assertFalse(history.remove_open_file_later(masked, spawn=spawn))
        self.assertFalse(history.remove_open_file_later("", spawn=spawn))
        spawn.assert_not_called()

    def test_files_outside_the_cache_folder_or_symlinks_are_never_removed(self):
        with tempfile.TemporaryDirectory() as other:
            outside = os.path.join(other, "z-context-open.md")
            open(outside, "w").close()
            self.assertFalse(history.remove_open_file(outside))
            self.assertTrue(os.path.exists(outside))
            link = os.path.join(self.dir, "l-context-open.md")
            os.symlink(outside, link)
            self.assertFalse(history.remove_open_file(link))
            self.assertTrue(os.path.exists(outside))

    def test_the_detached_remover_deletes_the_file_after_its_delay(self):
        opened = self.file("a-context-open.md")
        env = dict(os.environ)
        subprocess.run([sys.executable, "-I", os.path.join(HELPER, "remove_later.py"), "0", opened], check=True, env=env, timeout=10)
        self.assertFalse(os.path.exists(opened))

    def test_the_remover_ignores_a_bad_delay(self):
        opened = self.file("a-context-open.md")
        r = subprocess.run([sys.executable, "-I", os.path.join(HELPER, "remove_later.py"), "soon", opened], env=dict(os.environ), timeout=10)
        self.assertEqual(r.returncode, 2)
        self.assertTrue(os.path.exists(opened))

    def test_send_schedules_the_removal_only_after_the_agent_started(self):
        opened = self.file("a-context-open.md")
        r = {"ok": True, "target": {"agent": "claude", "cwd": "/tmp"}, "prompt": "p", "file": opened, "history_question": "q"}
        report = {"display": "Claude", "cwd": "/tmp", "clipboard": False, "notified": False, "dry_run": False}
        with mock.patch.object(snap, "read_state", return_value={"mode": "region"}), \
                mock.patch.object(snap, "_compose", return_value=r), \
                mock.patch.object(snap.agents, "build_launch", return_value={"agent": "claude", "auto": False}), \
                mock.patch.object(snap.history, "add"), \
                mock.patch.object(snap.history, "remove_open_file_later") as later:
            with mock.patch.object(snap.launch, "launch", return_value=report):
                self.assertTrue(snap.cmd_send([])["ok"])
                later.assert_called_once_with(opened)
            later.reset_mock()
            with mock.patch.object(snap.launch, "launch", side_effect=snap.launch.LaunchError("start-failed", "x")):
                self.assertFalse(snap.cmd_send([])["ok"])
                later.assert_not_called()  # nothing started, so the user can still send again
            later.reset_mock()
            with mock.patch.object(snap.launch, "launch", return_value=dict(report, dry_run=True)):
                snap.cmd_send(["--dry-run"])
                later.assert_not_called()


if __name__ == "__main__":
    unittest.main()
