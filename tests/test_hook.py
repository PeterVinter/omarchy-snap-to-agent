import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "helper"))
import hook  # noqa: E402

BASH_HOOK = os.path.abspath(os.path.join(ROOT, "hook", "snap-hook.bash"))
ZSH_HOOK = os.path.abspath(os.path.join(ROOT, "hook", "snap-hook.zsh"))


def run_shell(argv, script, home):
    env = {"HOME": home, "PATH": os.environ["PATH"], "TERM": "dumb"}
    start = time.perf_counter()
    subprocess.run(argv, input=script, text=True, env=env, capture_output=True, timeout=60)
    return time.perf_counter() - start


def put(path, text):
    with open(path, "w") as f:
        f.write(text)


def get(path):
    with open(path) as f:
        return f.read()


def _read(home):
    return hook.read_last(home=home)


class BashHookTests(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()

    def test_failed_command_is_recorded_with_exit_code_and_directory(self):
        run_shell(["bash", "--norc", "--noprofile", "-i"], ". '%s'\ncd /tmp\nls /nonexistent-dir\nexit\n" % BASH_HOOK, self.home)
        r = _read(self.home)
        self.assertIsNotNone(r)
        self.assertEqual(r["rc"], 2)
        self.assertEqual(r["command"], "ls /nonexistent-dir")
        self.assertEqual(r["cwd"], "/tmp")
        self.assertFalse(r["stale"])

    def test_success_and_ctrl_c_are_not_recorded(self):
        run_shell(["bash", "--norc", "--noprofile", "-i"], ". '%s'\ntrue\n(exit 130)\nexit\n" % BASH_HOOK, self.home)
        self.assertIsNone(_read(self.home))

    def test_hook_is_silent_outside_interactive_shells(self):
        run_shell(["bash", "--norc", "--noprofile"], ". '%s'\nls /nonexistent-dir\n" % BASH_HOOK, self.home)
        self.assertIsNone(_read(self.home))

    def test_works_with_an_array_prompt_command_and_keeps_the_existing_one(self):
        script = "PROMPT_COMMAND=(\"echo existing-hook-ran\")\n. '%s'\nls /nonexistent-dir\nexit\n" % BASH_HOOK
        env_home = self.home
        env = {"HOME": env_home, "PATH": os.environ["PATH"]}
        p = subprocess.run(["bash", "--norc", "--noprofile", "-i"], input=script, text=True, env=env, capture_output=True)
        self.assertIn("existing-hook-ran", p.stdout)
        self.assertEqual(_read(self.home)["rc"], 2)

    def test_overhead_per_prompt_is_small(self):
        n = 400
        body = "true\n" * n + "exit\n"
        base = min(run_shell(["bash", "--norc", "--noprofile", "-i"], body, self.home) for _ in range(3))
        with_ = min(run_shell(["bash", "--norc", "--noprofile", "-i"], ". '%s'\n" % BASH_HOOK + body, self.home) for _ in range(3))
        per_prompt_ms = (with_ - base) / n * 1000
        self.assertLess(per_prompt_ms, 5.0, "%.3f ms per prompt" % per_prompt_ms)

    def test_failing_prompts_stay_cheap_too(self):
        n = 200
        body = "false\n" * n + "exit\n"
        base = min(run_shell(["bash", "--norc", "--noprofile", "-i"], body, self.home) for _ in range(3))
        with_ = min(run_shell(["bash", "--norc", "--noprofile", "-i"], ". '%s'\n" % BASH_HOOK + body, self.home) for _ in range(3))
        self.assertLess((with_ - base) / n * 1000, 5.0)


@unittest.skipUnless(shutil.which("zsh"), "zsh is not installed")
class ZshHookTests(unittest.TestCase):
    def test_failed_command_is_recorded(self):
        home = tempfile.mkdtemp()
        run_shell(["zsh", "-f", "-i"], "source '%s'\nls /nonexistent-dir\ntrue\nexit\n" % ZSH_HOOK, home)
        r = _read(home)
        self.assertIsNotNone(r)
        self.assertEqual(r["rc"], 2)
        self.assertEqual(r["command"], "ls /nonexistent-dir")


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.bashrc = os.path.join(self.home, ".bashrc")

    def test_install_adds_one_marked_block_and_is_idempotent(self):
        with open(self.bashrc, "w") as f:
            f.write("export A=1\nalias ll='ls -l'\n")
        self.assertEqual(hook.install(self.home, "/opt/plug"), [self.bashrc])
        self.assertEqual(hook.install(self.home, "/opt/plug"), [])
        text = get(self.bashrc)
        self.assertEqual(text.count(hook.BEGIN), 1)
        self.assertIn("/opt/plug/hook/snap-hook.bash", text)
        self.assertFalse(os.path.exists(os.path.join(self.home, ".zshrc")))
        self.assertEqual(hook.status(self.home), {"bash": True})

    def test_zshrc_is_only_touched_when_it_exists(self):
        put(os.path.join(self.home, ".zshrc"), "# zsh\n")
        hook.install(self.home, "/opt/plug")
        self.assertIn("snap-hook.zsh", get(os.path.join(self.home, ".zshrc")))

    def test_uninstall_restores_the_files_exactly(self):
        original = "export A=1\n\nalias ll='ls -l'\n"
        put(self.bashrc, original)
        hook.install(self.home, "/opt/plug")
        os.makedirs(hook.state_dir(self.home))
        put(os.path.join(hook.state_dir(self.home), "last-error.txt"), "v1\n")
        self.assertEqual(hook.uninstall(self.home), [self.bashrc])
        self.assertEqual(get(self.bashrc).rstrip("\n"), original.rstrip("\n"))
        self.assertFalse(os.path.exists(os.path.join(hook.state_dir(self.home), "last-error.txt")))
        self.assertEqual(hook.status(self.home), {"bash": False})
        self.assertEqual(hook.uninstall(self.home), [])

    def test_uninstall_without_any_rc_file_is_fine(self):
        self.assertEqual(hook.uninstall(self.home), [])


class ReadAndExtractTests(unittest.TestCase):
    def test_stale_and_broken_records(self):
        home = tempfile.mkdtemp()
        d = hook.state_dir(home)
        os.makedirs(d)
        p = os.path.join(d, "last-error.txt")
        put(p, "v1\nrc=1\ntime=%d\ncwd=/tmp\npane=%%3\nmake test\n" % (time.time() - 90000))
        r = hook.read_last(home=home)
        self.assertTrue(r["stale"])
        self.assertEqual((r["rc"], r["pane"], r["command"]), (1, "%3", "make test"))
        put(p, "garbage\n")
        self.assertIsNone(hook.read_last(home=home))
        put(p, "v1\nrc=x\ntime=1\ncwd=/\npane=\ncmd\n")
        self.assertIsNone(hook.read_last(home=home))

    PANE = "old stuff\n$ make test\ncc -o a a.c\na.c:3: error: expected ';'\nmake: *** [Makefile:2: a] Error 1\n$ \n\n"

    def test_output_is_what_follows_the_command(self):
        text, found = hook.extract_output(self.PANE, "make test")
        self.assertTrue(found)
        self.assertEqual(text, "cc -o a a.c\na.c:3: error: expected ';'\nmake: *** [Makefile:2: a] Error 1")

    def test_uses_the_last_occurrence_and_falls_back_to_the_tail(self):
        pane = "$ make test\nfirst run\n$ make test\nsecond run\n$ "
        self.assertEqual(hook.extract_output(pane, "make test")[0], "second run")
        text, found = hook.extract_output("a\nb\nc", "not shown")
        self.assertFalse(found)
        self.assertEqual(text, "a\nb\nc")

    def test_output_is_capped(self):
        pane = "$ big\n" + "\n".join("line %d" % i for i in range(1000)) + "\n$ "
        text, _ = hook.extract_output(pane, "big")
        self.assertEqual(len(text.splitlines()), 200)
        self.assertTrue(text.endswith("line 999"))
        self.assertLessEqual(len(hook.extract_output("$ x\n" + "y" * 200000 + "\n$ ", "x")[0]), 64000)


if __name__ == "__main__":
    unittest.main()
