import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "helper"))
import agents  # noqa: E402

PROMPT = "Explain this error\n--yolo is not a flag here"
OMARCHY_AGENT = "/usr/share/omarchy/bin/omarchy-default-agent"


def omarchy_agent_names():
    """The agent names Omarchy itself accepts, read from its own script, if present."""
    try:
        with open(OMARCHY_AGENT, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return []
    m = re.search(r"# omarchy:args=\[([^\]]+)\]", text)
    return m.group(1).split("|") if m else []


class AdapterTests(unittest.TestCase):
    def test_every_agent_builds_a_plan(self):
        for name in agents.known_agents():
            plan = agents.build_launch(name, PROMPT)
            self.assertTrue(plan["known"], name)
            self.assertTrue(plan["argv"], name)
            if plan["how"] == "clipboard":
                self.assertEqual(plan["clipboard"], PROMPT, name)
            elif plan["how"] == "stdin":
                self.assertEqual(plan["stdin"], PROMPT, name)
            else:
                self.assertTrue(any(PROMPT in a for a in plan["argv"]), name)

    def test_no_auto_approve_flags_anywhere(self):
        for name in agents.known_agents():
            plan = agents.build_launch(name, "hello")
            argv = plan["argv"]
            for i, arg in enumerate(argv):
                for bad in agents.FORBIDDEN_FLAGS:
                    self.assertFalse(arg == bad or arg.startswith(bad + "="), "%s uses %s" % (name, bad))
                if arg in agents.SAFE_ONLY_WITH:
                    self.assertEqual(argv[i + 1], agents.SAFE_ONLY_WITH[arg], "%s: unsafe value for %s" % (name, arg))
                if arg.startswith("--permission-mode="):
                    self.assertEqual(arg.split("=", 1)[1], "manual")

    def test_claude_is_asked_for_manual_mode_explicitly(self):
        argv = agents.build_launch("claude", "hello", as_argument=True)["argv"]
        self.assertEqual(argv[:3], ["claude", "--permission-mode", "manual"])
        self.assertEqual(argv[-2:], ["--", "hello"])

    def test_prompt_starting_with_dash_stays_literal(self):
        for name in ["claude", "codex", "opencode", "kilo", "qwen", "hermes", "cursor-agent"]:
            plan = agents.build_launch(name, "--version", as_argument=True)
            joined = plan["argv"]
            # Either behind "--", or bound to its own flag with "=" or a value flag.
            idx = max(i for i, a in enumerate(joined) if "--version" in a)
            safe = ("--" in joined[:idx]) or joined[idx].startswith("--") and "=" in joined[idx] \
                or joined[idx - 1].startswith("--")
            self.assertTrue(safe, "%s: %r" % (name, joined))

    def test_clipboard_agents_start_plain(self):
        for name in ["kimi", "crush", "dsh", "freebuff"]:
            plan = agents.build_launch(name, PROMPT)
            self.assertEqual(plan["how"], "clipboard")
            self.assertFalse(any(PROMPT in a for a in plan["argv"]))

    def test_by_default_no_agent_gets_the_prompt_on_a_command_line(self):
        secret = "SECRET-PROMPT-TEXT"
        for name in agents.known_agents():
            plan = agents.build_launch(name, secret)
            self.assertIsNone(plan["private_argv"], name)
            self.assertFalse(any(secret in a for a in plan["argv"]), name)
            if name == "amp":
                self.assertEqual(plan["how"], "stdin")  # a private pipe, not an argument
            else:
                self.assertEqual(plan["how"], "clipboard", name)
                self.assertEqual(plan["clipboard"], secret, name)
            for bad in agents.FORBIDDEN_FLAGS:
                self.assertNotIn(bad, plan["argv"], name)

    def test_default_start_of_claude_still_asks_first(self):
        self.assertEqual(agents.build_launch("claude", "p")["argv"], ["claude", "--permission-mode", "manual"])
        self.assertEqual(agents.build_launch("claude", "p", auto=True)["argv"], ["claude", "--permission-mode", "auto"])

    def test_opting_in_passes_the_prompt_as_an_argument(self):
        plan = agents.build_launch("claude", "p", as_argument=True)
        self.assertEqual(plan["how"], "arg")
        self.assertIn("p", plan["argv"])
        self.assertIsNotNone(plan["private_argv"])
        self.assertEqual(agents.build_launch("amp", "p", as_argument=True)["how"], "stdin")

    def test_amp_pipes_the_prompt(self):
        plan = agents.build_launch("amp", PROMPT)
        self.assertEqual(plan["how"], "stdin")
        self.assertEqual(plan["argv"], ["amp"])

    def test_unknown_agent_uses_generic_fallback(self):
        plan = agents.build_launch("brand-new-agent", PROMPT)
        self.assertFalse(plan["known"])
        self.assertEqual(plan["argv"], ["brand-new-agent"])
        self.assertEqual(plan["clipboard"], PROMPT)
        self.assertEqual(plan["note"], "generic")

    def test_no_agent_is_reported(self):
        self.assertEqual(agents.build_launch("", PROMPT)["how"], "none")

    def test_huge_prompt_goes_to_clipboard_instead_of_argv(self):
        plan = agents.build_launch("claude", "x" * (agents.MAX_ARG_BYTES + 10), as_argument=True)
        self.assertEqual(plan["how"], "clipboard")
        self.assertEqual(plan["argv"], ["claude", "--permission-mode", "manual"])

    def test_huge_prompt_never_leaves_a_bare_env_command(self):
        big = "x" * (agents.MAX_ARG_BYTES + 10)
        self.assertEqual(agents.build_launch("hermes", big, as_argument=True)["argv"], ["hermes"])
        self.assertEqual(agents.build_launch("openclaw", big, as_argument=True)["argv"], ["omarchy-launch-openclaw", "--tui"])
        self.assertEqual(agents.build_launch("kiro-cli", big, as_argument=True)["argv"], ["kiro-cli", "chat"])
        self.assertEqual(agents.binary_of(["env", "-u", "X", "hermes", "chat"]), "hermes")

    def test_images_are_passed_as_path_until_tested(self):
        for name in agents.known_agents():
            self.assertEqual(agents.build_launch(name, "x")["image_mode"], "path", name)

    def test_covers_every_agent_omarchy_lists(self):
        listed = omarchy_agent_names()
        if not listed:
            self.skipTest("omarchy-default-agent not found")
        aliases = {"agy": "agy"}
        for name in listed:
            plan = agents.build_launch(aliases.get(name, name), "hi")
            self.assertTrue(plan["known"], "no adapter for %s" % name)


class AutoModeTests(unittest.TestCase):
    def test_default_never_uses_auto(self):
        for name in agents.known_agents():
            plan = agents.build_launch(name, "hi")
            self.assertFalse(plan["auto"], name)
            self.assertEqual(plan["argv"], agents.build_launch(name, "hi", auto=False)["argv"])

    def test_auto_changes_the_command_only_for_agents_with_an_option(self):
        for name in agents.known_agents():
            safe = agents.build_launch(name, "hi", as_argument=True)
            auto = agents.build_launch(name, "hi", auto=True, as_argument=True)
            if agents.has_auto(name):
                self.assertTrue(auto["auto"], name)
                self.assertNotEqual(auto["argv"], safe["argv"], name)
            else:
                self.assertFalse(auto["auto"], name)
                self.assertEqual(auto["argv"], safe["argv"], name)

    def test_auto_commands_match_omarchys_launcher(self):
        a = lambda n: agents.build_launch(n, "p", auto=True, as_argument=True)["argv"]  # noqa: E731
        self.assertEqual(a("claude"), ["claude", "--permission-mode", "auto", "--", "p"])
        self.assertEqual(a("codex"), ["codex", "--approve-for-me", "--", "p"])
        self.assertEqual(a("opencode"), ["opencode", "--auto", "--prompt", "p"])
        self.assertEqual(a("kimi"), ["kimi", "--yolo"])

    def test_agents_without_a_known_option_stay_safe(self):
        for name in ("pi", "ori", "mcode", "openclaw", "freebuff", "dsh", "brand-new-agent"):
            self.assertFalse(agents.has_auto(name), name)
            self.assertFalse(agents.build_launch(name, "x", auto=True)["auto"], name)

    def test_amp_and_clipboard_agents_keep_their_way_of_taking_a_prompt(self):
        amp = agents.build_launch("amp", "p", auto=True)
        self.assertEqual((amp["how"], amp["stdin"], amp["argv"][0]), ("stdin", "p", "amp"))
        kimi = agents.build_launch("kimi", "p", auto=True)
        self.assertEqual((kimi["how"], kimi["clipboard"]), ("clipboard", "p"))


class DefaultAgentTests(unittest.TestCase):
    def write(self, home, content):
        d = os.path.join(home, "omarchy", "defaults")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "agent"), "w") as f:
            f.write(content)

    def test_reads_at_call_time(self):
        with tempfile.TemporaryDirectory() as home:
            self.write(home, "claude\n")
            self.assertEqual(agents.default_agent(home), ("claude", ""))
            self.write(home, "codex\n")
            self.assertEqual(agents.default_agent(home), ("codex", ""))

    def test_problems_are_named(self):
        with tempfile.TemporaryDirectory() as home:
            self.assertEqual(agents.default_agent(home), ("", "missing-file"))
            self.write(home, "\n")
            self.assertEqual(agents.default_agent(home), ("", "empty"))
            self.write(home, "bad name; rm\n")
            self.assertEqual(agents.default_agent(home), ("", "unreadable"))


if __name__ == "__main__":
    unittest.main()
