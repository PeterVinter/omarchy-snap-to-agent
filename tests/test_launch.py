import os
import subprocess
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


def inner(cmd):
    """The command the private-file wrapper runs, without the env prefix and the wrapper itself."""
    if launch.STARTER in cmd:
        return cmd[cmd.index(launch.STARTER) + 3:]
    return cmd


def prefix(cmd):
    return cmd[:cmd.index("python3")] if "python3" in cmd else cmd


class LaunchTests(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()

    def test_claude_runs_in_a_terminal_without_auto_flags(self):
        plan = agents.build_launch("claude", "help me", as_argument=True)
        run, spawn = Fake({"omarchy-agent-account-home": (0, "", ""), "env": (1, "", "")}), Spawn()
        with with_binaries("claude"):
            r = launch.launch(plan, "/tmp", run=run, spawn=spawn, home=self.home, environ={})
        argv, kw = spawn.calls[0]
        self.assertEqual(argv[:2], ["omarchy-launch-tui", "--app-id=org.omarchy.agent"])
        self.assertEqual(argv[-5:], ["claude", "--permission-mode", "manual", "--", agents.PROMPT_MARKER])
        self.assertNotIn("help me", argv)  # the prompt is not on any command line we start
        self.assertEqual(kw["cwd"], "/tmp")
        self.assertTrue(kw["start_new_session"])
        for bad in agents.FORBIDDEN_FLAGS:
            self.assertNotIn(bad, argv)
        self.assertFalse(r["clipboard"])

    def test_account_home_is_pinned_like_omarchy_does(self):
        plan = agents.build_launch("claude", "q", as_argument=True)
        run = Fake({"omarchy-agent-account-home": (0, "/acct/work", ""), "env": (1, "", "")})
        cmd = launch.agent_command(plan, run, self.home, {})
        self.assertEqual(cmd[:5], ["env", "-u", "CLAUDE_CONFIG_DIR", "OMARCHY_AGENT_CLAUDE_HOME=/acct/work",
                                   "CLAUDE_CONFIG_DIR=/acct/work"])
        self.assertEqual(inner(cmd)[0], "claude")

    def test_users_own_provider_home_is_left_alone(self):
        plan = agents.build_launch("codex", "q", as_argument=True)
        cmd = launch.agent_command(plan, Fake({"env": (1, "", "")}), self.home, {"CODEX_HOME": "/mine"})
        self.assertEqual(inner(cmd)[0], "codex")
        self.assertEqual(prefix(cmd), [])

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

    def test_default_claude_start_is_plain_with_the_prompt_on_the_clipboard(self):
        plan = agents.build_launch("claude", "the prompt")
        run, spawn = Fake({"env": (1, "", "")}), Spawn()
        with with_binaries("claude"):
            r = launch.launch(plan, "/tmp", run=run, spawn=spawn, home=self.home, environ={})
        self.assertIn((["wl-copy"], "the prompt"), run.calls)
        self.assertEqual(spawn.calls[0][0][-3:], ["claude", "--permission-mode", "manual"])
        self.assertNotIn("the prompt", " ".join(spawn.calls[0][0]))
        self.assertTrue(r["clipboard"])

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
        self.assertEqual(cmd[:3], ["python3", "-I", launch.STARTER])
        self.assertEqual(inner(cmd), ["amp"])
        self.assertNotIn("first message", cmd)

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
        plan = agents.build_launch("claude", prompt, as_argument=True)
        bin_dir = os.path.join(self.home, ".local", "bin")
        os.makedirs(bin_dir)
        own = os.path.join(bin_dir, "claude")
        with open(own, "w") as f:
            f.write("#!/bin/sh\n")
        os.chmod(own, 0o755)
        cmd = launch.agent_command(plan, Fake({"env": (1, "", ""), "omarchy-agent-account-home": (0, "", "")}), self.home, {})
        self.assertEqual(cmd[-1], agents.PROMPT_MARKER)
        self.assertNotIn(prompt, cmd)
        self.assertIn(own, cmd)


class RunnerTests(unittest.TestCase):
    def test_a_command_that_leaves_a_background_process_does_not_time_out(self):
        import runner
        with tempfile.TemporaryDirectory() as d:
            fake = os.path.join(d, "wl-copy")
            with open(fake, "w") as f:  # like wl-copy: serves in a background process that keeps the pipes
                f.write("#!/bin/bash\ncat > /dev/null\n(sleep 8 &)\n")
            os.chmod(fake, 0o755)
            with mock.patch.dict(os.environ, {"PATH": d + os.pathsep + os.environ["PATH"]}):
                code, _, _ = runner.run(["wl-copy"], timeout=3, input="text")
        self.assertEqual(code, 0)


class PrivatePromptTests(unittest.TestCase):
    """Runs the real wrapper with a stand-in agent: the text arrives intact and is never on a command line."""

    NASTY = "line one & \\1 'quoted' \"dq\" $HOME `x` $(y)\n  line two  *\n@@ not the marker @@"

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.out = os.path.join(self.dir, "out")
        self.agent = os.path.join(self.dir, "fake-agent")
        with open(self.agent, "w") as f:
            f.write('#!/bin/bash\nprintf "%s\\0" "$@" > "$OUT_ARGS"\ncat > "$OUT_IN"\n')
        os.chmod(self.agent, 0o755)
        self.env = dict(os.environ, OUT_ARGS=self.out + ".args", OUT_IN=self.out + ".in", XDG_RUNTIME_DIR=self.dir)

    def _run(self, plan):
        path = launch.write_prompt_file(plan.get("stdin") if plan["how"] == "stdin" else plan["prompt"], self.env)
        self.assertEqual(oct(os.stat(path).st_mode & 0o777), "0o600")
        plan = dict(plan, argv=[self.agent] + plan["argv"][1:])
        if plan.get("private_argv"):
            plan["private_argv"] = [self.agent] + plan["private_argv"][1:]
        else:
            plan["argv"] = [self.agent]
        cmd = launch.agent_command(plan, Fake({"env": (1, "", "")}), self.dir, {"CODEX_HOME": "x"}, path)
        self.assertNotIn("one &", " ".join(cmd))
        subprocess.run(cmd, env=self.env, check=True, stdin=subprocess.DEVNULL)
        self.assertFalse(os.path.exists(path))  # deleted as soon as it was read

    def test_marker_is_the_same_in_the_planner_and_the_starter(self):
        import start_agent
        self.assertEqual(start_agent.MARKER, agents.PROMPT_MARKER)

    def test_the_command_has_no_shell_syntax_for_a_launcher_to_mangle(self):
        # A live test showed that the terminal launcher re-parses the command it is given.
        cmd = launch.agent_command(agents.build_launch("claude", "p"), Fake({"env": (1, "", "")}), self.dir, {}, "/run/user/1/f")
        for word in cmd:
            for bad in ("${", "$(", "`", '"', "'", ";", "|"):
                self.assertNotIn(bad, word)

    def test_a_long_stdin_prompt_is_delivered_whole(self):
        long = ("x" * 99) + "\n"
        long = long * 900  # about 90 KB, larger than a pipe buffer
        self._run(agents.build_launch("amp", long))
        self.assertEqual(open(self.out + ".in").read(), long + "\n")

    def test_argument_agent_gets_the_exact_text(self):
        self._run(agents.build_launch("kilo", self.NASTY, as_argument=True))  # prompt joined to a flag: --prompt=<text>
        args = open(self.out + ".args").read().split("\0")[:-1]
        self.assertEqual(args, ["--prompt=" + self.NASTY])

    def test_argument_agent_with_separate_argument(self):
        self._run(agents.build_launch("codex", self.NASTY, as_argument=True))
        args = open(self.out + ".args").read().split("\0")[:-1]
        self.assertEqual(args, ["--", self.NASTY])

    def test_stdin_agent_gets_the_exact_text_and_a_newline(self):
        self._run(agents.build_launch("amp", self.NASTY))
        self.assertEqual(open(self.out + ".in").read(), self.NASTY + "\n")

    def test_launch_writes_a_private_file_and_cleans_up_when_the_start_fails(self):
        plan = agents.build_launch("claude", "secret text")
        def boom(*a, **k):
            raise OSError("no terminal")
        with with_binaries("claude"), self.assertRaises(launch.LaunchError):
            launch.launch(plan, "/tmp", run=Fake({"env": (1, "", "")}), spawn=boom, home=self.dir,
                          environ={"XDG_RUNTIME_DIR": self.dir})
        self.assertEqual([n for n in os.listdir(self.dir) if n.startswith("snap-to-agent-prompt-")], [])


if __name__ == "__main__":
    unittest.main()
