import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "helper"))
import agents  # noqa: E402
import launch  # noqa: E402


class Fake:
    def __init__(self, answers=None):
        self.calls, self.answers = [], answers or {}

    def __call__(self, argv, timeout=15, input=None):
        self.calls.append((argv, input))
        return self.answers.get(argv[0], (0, "", ""))


class Spawn:
    def __init__(self):
        self.calls = []

    def __call__(self, argv, **kw):
        self.calls.append((argv, kw))


def with_binaries(*present):
    return mock.patch("launch.shutil.which", lambda name: "/usr/bin/" + name if name in present else None)


class LaunchTests(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()

    def test_claude_runs_in_a_terminal_without_auto_flags(self):
        plan = agents.build_launch("claude", "help me")
        run, spawn = Fake({"omarchy-agent-account-home": (0, "", ""), "env": (1, "", "")}), Spawn()
        with with_binaries("claude"):
            r = launch.launch(plan, "/tmp", run=run, spawn=spawn, home=self.home, environ={})
        argv, kw = spawn.calls[0]
        self.assertEqual(argv[:2], ["omarchy-launch-tui", "--app-id=org.omarchy.agent"])
        self.assertEqual(argv[-3:], ["claude", "--", "help me"])
        self.assertEqual(kw["cwd"], "/tmp")
        self.assertTrue(kw["start_new_session"])
        for bad in agents.FORBIDDEN_FLAGS:
            self.assertNotIn(bad, argv)
        self.assertFalse(r["clipboard"])

    def test_account_home_is_pinned_like_omarchy_does(self):
        plan = agents.build_launch("claude", "q")
        run = Fake({"omarchy-agent-account-home": (0, "/acct/work", ""), "env": (1, "", "")})
        cmd = launch.agent_command(plan, run, self.home, {})
        self.assertEqual(cmd[:6], ["env", "-u", "CLAUDE_CONFIG_DIR", "OMARCHY_AGENT_CLAUDE_HOME=/acct/work",
                                   "CLAUDE_CONFIG_DIR=/acct/work", "claude"])

    def test_users_own_provider_home_is_left_alone(self):
        plan = agents.build_launch("codex", "q")
        cmd = launch.agent_command(plan, Fake({"env": (1, "", "")}), self.home, {"CODEX_HOME": "/mine"})
        self.assertEqual(cmd[0], "codex")

    def test_clipboard_agent_gets_prompt_on_clipboard_and_a_toast(self):
        plan = agents.build_launch("kimi", "the prompt")
        run, spawn = Fake(), Spawn()
        with with_binaries("kimi"):
            r = launch.launch(plan, "/tmp", run=run, spawn=spawn, home=self.home, environ={})
        self.assertIn((["wl-copy"], "the prompt"), run.calls)
        self.assertTrue(any(c[0][0] == "omarchy-notification-send" for c in run.calls))
        self.assertTrue(r["clipboard"] and r["notified"])
        self.assertEqual(spawn.calls[0][0][-1], "kimi")
        self.assertNotIn("the prompt", spawn.calls[0][0])

    def test_failed_clipboard_does_not_start_the_agent(self):
        plan = agents.build_launch("kimi", "p")
        spawn = Spawn()
        with with_binaries("kimi"), self.assertRaises(launch.LaunchError) as cm:
            launch.launch(plan, "/tmp", run=Fake({"wl-copy": (1, "", "no display")}), spawn=spawn, home=self.home)
        self.assertEqual(cm.exception.code, "clipboard-failed")
        self.assertEqual(spawn.calls, [])

    def test_amp_gets_its_prompt_on_stdin_inside_the_terminal(self):
        plan = agents.build_launch("amp", "first message")
        cmd = launch.agent_command(plan, Fake({"env": (1, "", "")}), self.home, {})
        self.assertEqual(cmd[:2], ["bash", "-c"])
        self.assertIn("exec \"$0\"", cmd[2])
        self.assertEqual(cmd[3:], ["amp", "first message"])

    def test_unknown_agent_uses_generic_fallback(self):
        plan = agents.build_launch("brand-new", "p")
        run, spawn = Fake(), Spawn()
        with with_binaries("brand-new"):
            r = launch.launch(plan, "/tmp", run=run, spawn=spawn, home=self.home, environ={})
        self.assertTrue(r["clipboard"])
        self.assertEqual(spawn.calls[0][0][-1], "brand-new")

    def test_not_installed_is_reported_before_anything_runs(self):
        spawn = Spawn()
        with with_binaries(), self.assertRaises(launch.LaunchError) as cm:
            launch.launch(agents.build_launch("claude", "p"), "/tmp", run=Fake({"env": (1, "", "")}), spawn=spawn, home=self.home)
        self.assertEqual(cm.exception.code, "not-installed")
        self.assertEqual(spawn.calls, [])

    def test_no_agent_is_an_error(self):
        with self.assertRaises(launch.LaunchError) as cm:
            launch.launch(agents.build_launch("", "p"), "/tmp", run=Fake(), spawn=Spawn(), home=self.home)
        self.assertEqual(cm.exception.code, "no-agent")

    def test_missing_directory_falls_back_to_work_then_home(self):
        spawn = Spawn()
        with with_binaries("claude"):
            launch.launch(agents.build_launch("claude", "p"), "/no/such", run=Fake({"env": (1, "", "")}), spawn=spawn,
                          home=self.home, environ={})
        self.assertEqual(spawn.calls[0][1]["cwd"], self.home)
        os.mkdir(os.path.join(self.home, "Work"))
        with with_binaries("claude"):
            launch.launch(agents.build_launch("claude", "p"), self.home, run=Fake({"env": (1, "", "")}), spawn=spawn,
                          home=self.home, environ={})
        self.assertEqual(spawn.calls[1][1]["cwd"], os.path.join(self.home, "Work"))

    def test_dry_run_changes_nothing(self):
        run, spawn = Fake({"env": (1, "", "")}), Spawn()
        with with_binaries("kimi"):
            r = launch.launch(agents.build_launch("kimi", "p"), "/tmp", run=run, spawn=spawn, dry_run=True, home=self.home)
        self.assertTrue(r["dry_run"])
        self.assertEqual(spawn.calls, [])
        self.assertFalse(any(c[0][0] in ("wl-copy", "omarchy-notification-send") for c in run.calls))

    def test_users_own_install_wins_but_a_mise_wrapper_does_not(self):
        bin_dir = os.path.join(self.home, ".local", "bin")
        os.makedirs(bin_dir)
        own = os.path.join(bin_dir, "claude")
        with open(own, "w") as f:
            f.write("#!/bin/sh\necho real\n")
        os.chmod(own, 0o755)
        mise_missing = Fake({"env": (1, "", "")})
        self.assertEqual(launch.user_install("claude", mise_missing, self.home), own)
        mise_has_it = Fake({"env": (0, "/x/claude", "")})
        self.assertEqual(launch.user_install("claude", mise_has_it, self.home), "")
        with open(own, "w") as f:
            f.write("#!/bin/sh\nexec mise x claude -- claude \"$@\"\n")
        self.assertEqual(launch.user_install("claude", mise_missing, self.home), "")

    def test_the_prompt_argument_is_never_rewritten(self):
        prompt = "please run claude now"
        plan = agents.build_launch("claude", prompt)
        bin_dir = os.path.join(self.home, ".local", "bin")
        os.makedirs(bin_dir)
        own = os.path.join(bin_dir, "claude")
        with open(own, "w") as f:
            f.write("#!/bin/sh\n")
        os.chmod(own, 0o755)
        cmd = launch.agent_command(plan, Fake({"env": (1, "", ""), "omarchy-agent-account-home": (0, "", "")}), self.home, {})
        self.assertEqual(cmd[-1], prompt)
        self.assertIn(own, cmd)


if __name__ == "__main__":
    unittest.main()
