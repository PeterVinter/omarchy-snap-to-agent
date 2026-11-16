"""Agent adapters: how to start each Omarchy coding agent with a first prompt.

Every adapter starts the agent in its normal, ask-before-acting mode. Omarchy's
own launcher (omarchy-agent) adds auto-approve flags to most agents; those are
left out on purpose. An agent without an adapter, or one that cannot take a
first prompt interactively, gets the generic fallback: it is started plain and
the prompt goes to the clipboard.

The table follows `omarchy-default-agent` in Omarchy 4.5. A newer Omarchy may
list more agents; they use the fallback until an adapter is added.
"""
import os
import shutil

# Command lines are lists of arguments; the marker PROMPT stands for the prompt.
PROMPT = object()

# name: (display name, "how", argv template)
#   how "arg"       the prompt is part of the command line
#   how "stdin"     the prompt is piped in as the first message
#   how "clipboard" the agent has no safe interactive prompt option: start it
#                   plain and put the prompt on the clipboard
_ADAPTERS = {
    # Claude Code's own default can be "auto" (it was on a fresh install of 2.1.325), so ask for
    # "manual", the mode that asks before it acts. This is a safe flag, not an auto-approve one.
    "claude":       ("Claude Code",     "arg", ["claude", "--permission-mode", "manual", "--", PROMPT]),
    "codex":        ("Codex",           "arg", ["codex", "--", PROMPT]),
    "grok":         ("Grok",            "arg", ["grok", "--", PROMPT]),
    "opencode":     ("OpenCode",        "arg", ["opencode", "--prompt", PROMPT]),
    "kilo":         ("Kilo",            "arg", ["kilo", ("--prompt=", PROMPT)]),
    "agy":          ("Antigravity",     "arg", ["agy", "--prompt-interactive", PROMPT]),
    "copilot":      ("GitHub Copilot",  "arg", ["copilot", "--interactive", PROMPT]),
    "qwen":         ("Qwen Code",       "arg", ["qwen", ("--prompt-interactive=", PROMPT)]),
    "cursor-agent": ("Cursor CLI",      "arg", ["cursor-agent", "agent", "--", PROMPT]),
    "muse":         ("Muse Code",       "arg", ["muse", "--", PROMPT]),
    "omp":          ("Oh My Pi",        "arg", ["omp", "--", PROMPT]),
    "ori":          ("Ori",             "arg", ["ori", "code", "--interactive", "--prompt", PROMPT]),
    "pi":           ("Pi",              "arg", ["pi", PROMPT]),
    "mcode":        ("MiniMax Code",    "arg", ["mcode", "--", PROMPT]),
    "kiro-cli":     ("Kiro CLI",        "arg", ["kiro-cli", "chat", "--", PROMPT]),
    "devin":        ("Devin CLI",       "arg", ["devin", "--", PROMPT]),
    "commandcode":  ("Command Code",    "arg", ["commandcode", "--", PROMPT]),
    "hermes":       ("Hermes",          "arg", ["env", "-u", "HERMES_SESSION_SOURCE", "hermes", "chat", "--tui", ("--query=", PROMPT)]),
    "openclaw":     ("OpenClaw",        "arg", ["omarchy-launch-openclaw", "--tui", "--message", PROMPT]),
    "amp":          ("Amp",             "stdin", ["amp"]),
    # Only a non-interactive prompt mode, or a browser UI without a prompt option.
    "kimi":         ("Kimi",            "clipboard", ["kimi"]),
    "crush":        ("Crush",           "clipboard", ["crush"]),
    "dsh":          ("DeepSeek Harness", "clipboard", ["dsh", "web"]),
    "freebuff":     ("Freebuff",        "clipboard", ["freebuff"]),
}

# The same agents started the way Omarchy's own launcher (omarchy-agent) starts them, with the
# agent's auto-approve option. Used ONLY when the user turns on "agent auto mode" in the settings;
# the default is off. Left out on purpose: pi, ori, mcode, openclaw and freebuff (Omarchy adds no
# such option for them) and dsh (its option is "danger-full-access", which is too broad to switch
# on from a checkbox). A prompt too large for the command line still starts without the flag.
AUTO = {
    "claude":       ["claude", "--permission-mode", "auto", "--", PROMPT],
    "codex":        ["codex", "--approve-for-me", "--", PROMPT],
    "grok":         ["grok", "--permission-mode", "bypassPermissions", "--", PROMPT],
    "opencode":     ["opencode", "--auto", "--prompt", PROMPT],
    "kilo":         ["kilo", "--auto", ("--prompt=", PROMPT)],
    "agy":          ["agy", "--dangerously-skip-permissions", "--prompt-interactive", PROMPT],
    "copilot":      ["copilot", "--allow-all", "--interactive", PROMPT],
    "qwen":         ["qwen", "--yolo", ("--prompt-interactive=", PROMPT)],
    "cursor-agent": ["cursor-agent", "--yolo", "--trust", "agent", "--", PROMPT],
    "muse":         ["muse", "--approval-mode", "never", "--", PROMPT],
    "omp":          ["omp", "--auto-approve", "--", PROMPT],
    "kiro-cli":     ["kiro-cli", "chat", "--trust-all-tools", "--", PROMPT],
    "devin":        ["devin", "--permission-mode", "dangerous", "--respect-workspace-trust", "false", "--", PROMPT],
    "commandcode":  ["commandcode", "--yolo", "--", PROMPT],
    "hermes":       ["env", "-u", "HERMES_SESSION_SOURCE", "hermes", "chat", "--yolo", "--tui", ("--query=", PROMPT)],
    "amp":          ["amp", "--dangerously-allow-all"],
    "kimi":         ["kimi", "--yolo"],
    "crush":        ["crush", "--yolo"],
}


def has_auto(agent):
    """True when this agent has an auto-approve start option the plugin knows."""
    return str(agent or "") in AUTO


# Flags that switch an agent to "do not ask". Never emitted; the test checks it.
FORBIDDEN_FLAGS = (
    "--yolo", "--auto", "--auto-approve", "--approve-for-me", "--allow-all",
    "--dangerously-skip-permissions", "--dangerously-allow-all", "--trust-all-tools",
    "--approval-mode", "--trust",
)
# Flags that are safe only with a particular value: (flag, the one allowed value).
SAFE_ONLY_WITH = {"--permission-mode": "manual"}

# Where an agent keeps its own account home (see omarchy-agent-account-home).
_ACCOUNT_ENV = {"claude": "CLAUDE_CONFIG_DIR", "codex": "CODEX_HOME", "grok": "GROK_HOME"}

# Only claim image support that was tested. Everything else gets the path in the prompt.
IMAGE_SUPPORT = {}

MAX_ARG_BYTES = 100_000


# What to run when the prompt cannot go on the command line (too large) or the
# agent takes it another way. Defaults to just the program name.
_BARE = {
    "openclaw": ["omarchy-launch-openclaw", "--tui"],
    "cursor-agent": ["cursor-agent"],
    "kiro-cli": ["kiro-cli", "chat"],
    "ori": ["ori", "code"],
}


def binary_of(template):
    """The program a template runs, looking past a leading `env [-u VAR]`."""
    i = 0
    if template and template[0] == "env":
        i = 1
        while i + 1 < len(template) and template[i] == "-u":
            i += 2
    return template[i] if i < len(template) and isinstance(template[i], str) else ""


def known_agents():
    return sorted(_ADAPTERS)


def adapter_for(agent):
    """Returns the adapter record for an agent name; a generic one for unknown names."""
    name = str(agent or "").strip()
    if name in _ADAPTERS:
        display, how, template = _ADAPTERS[name]
        return {"agent": name, "display": display, "how": how, "template": template, "known": True}
    return {"agent": name, "display": name or "unknown", "how": "clipboard",
            "template": [name] if name else [], "known": False}


def _expand(template, prompt):
    out = []
    for part in template:
        if part is PROMPT:
            out.append(prompt)
        elif isinstance(part, tuple):
            out.append("".join(prompt if p is PROMPT else p for p in part))
        else:
            out.append(part)
    return out


def image_mode(agent):
    """How the image reaches this agent: "flag" only when tested, else "path"."""
    return IMAGE_SUPPORT.get(agent, "path")


def build_launch(agent, prompt, auto=False):
    """Builds the launch plan for an agent.

    auto=True starts it with its auto-approve option (see AUTO); the default never does.

    Returns {display, known, how, argv, stdin, clipboard, image_mode, note}.
    argv is the agent command without any terminal wrapper. clipboard is the text
    to copy before launching, or None.
    """
    ad = adapter_for(agent)
    prompt = str(prompt or "")
    use_auto = bool(auto) and has_auto(ad["agent"])
    if use_auto:
        ad = dict(ad, template=AUTO[ad["agent"]])
    plan = {"agent": ad["agent"], "display": ad["display"], "known": ad["known"], "how": ad["how"],
            "argv": [], "stdin": None, "clipboard": None, "image_mode": image_mode(ad["agent"]), "note": "",
            "auto": use_auto}
    if not ad["template"]:
        plan["how"] = "none"
        plan["note"] = "no agent"
        return plan
    if ad["how"] == "arg" and len(prompt.encode("utf-8", "replace")) <= MAX_ARG_BYTES:
        plan["argv"] = _expand(ad["template"], prompt)
    elif ad["how"] == "stdin" and len(prompt.encode("utf-8", "replace")) <= MAX_ARG_BYTES:
        plan["argv"] = list(ad["template"])
        plan["stdin"] = prompt
    else:
        plan["how"] = "clipboard"
        plan["argv"] = _expand(ad["template"], prompt) if ad["how"] == "clipboard" else list(
            _BARE.get(ad["agent"], [binary_of(ad["template"])]))
        plan["clipboard"] = prompt
        plan["note"] = "paste"
    if not ad["known"]:
        plan["note"] = "generic"
    return plan


def installed(agent):
    ad = adapter_for(agent)
    return bool(ad["template"]) and shutil.which(binary_of(ad["template"])) is not None


def default_agent(config_home=None):
    """Reads the default agent at call time. Returns (name, problem).

    problem is "" when a name was found, else a short reason: missing-file,
    empty, unreadable.
    """
    home = config_home or os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    path = os.path.join(home, "omarchy", "defaults", "agent")
    try:
        with open(path, encoding="utf-8") as f:
            name = f.readline().strip()
    except FileNotFoundError:
        return "", "missing-file"
    except OSError:
        return "", "unreadable"
    if not name:
        return "", "empty"
    if not all(c.isalnum() or c in "-_." for c in name):
        return "", "unreadable"
    return name, ""
