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
            for arg in plan["argv"]:
                for bad in agents.FORBIDDEN_FLAGS:
                    self.assertFalse(arg == bad or arg.startswith(bad + "="), "%s uses %s" % (name, bad))

    def test_prompt_starting_with_dash_stays_literal(self):
        for name in ["claude", "codex", "opencode", "kilo", "qwen", "hermes", "cursor-agent"]:
            plan = agents.build_launch(name, "--version")
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
        plan = agents.build_launch("claude", "x" * (agents.MAX_ARG_BYTES + 10))
        self.assertEqual(plan["how"], "clipboard")
        self.assertEqual(plan["argv"], ["claude"])

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
