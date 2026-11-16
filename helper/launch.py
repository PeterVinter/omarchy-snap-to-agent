"""Starts the default agent in a terminal window with the prompt.

Follows how omarchy-agent starts agents (same terminal launcher and app id,
account homes, a user's own install in ~/.local/bin) but never adds an
auto-approve flag, so the agent asks before it acts.
"""
import os
import shutil
import subprocess

import agents
import context as ctxmod
import runner as _runner

APP_ID = "org.omarchy.agent"
_ACCOUNT_ENV = {"claude": "CLAUDE_CONFIG_DIR", "codex": "CODEX_HOME", "grok": "GROK_HOME"}

_CLIP_TEXT = {  # used only when Omarchy's own i18n catalog cannot be read
    "title": "%s takes no starting prompt",
    "generic_title": "%s was started without the prompt",
    "body": "Your prompt is on the clipboard. Paste it into the session.",
}


class LaunchError(Exception):
    def __init__(self, code, message=""):
        super().__init__(message or code)
        self.code = code
        self.message = message or code


def _is_mise_wrapper(path):
    try:
        with open(path, "rb") as f:
            head = f.read(4096)
    except OSError:
        return False
    return b"mise use " in head or b"mise x " in head


def user_install(agent, run=_runner.run, home=None):
    """Path of the user's own install in ~/.local/bin, when it should win over PATH.

    Same rule as omarchy-agent: a real file there that is not a mise wrapper, and
    mise has no install of its own, is the user's choice.
    """
    home = home or os.path.expanduser("~")
    path = os.path.join(home, ".local", "bin", agent)
    if not (os.path.isfile(path) and os.access(path, os.X_OK)) or _is_mise_wrapper(path):
        return ""
    code, _, _ = run(["env", "MISE_OFFLINE=1", "mise", "which", agent], timeout=5)
    return path if code != 0 else ""


def account_prefix(agent, run=_runner.run, environ=None):
    """`env ...` words that pin the active Claude, Codex or Grok account. [] for other agents."""
    home_env = _ACCOUNT_ENV.get(agent)
    if not home_env:
        return []
    environ = os.environ if environ is None else environ
    pin = "OMARCHY_AGENT_%s_HOME" % agent.upper()
    if environ.get(home_env) and environ.get(home_env) != environ.get(pin):
        return []  # an explicit provider home of the user's own wins
    code, out, _ = run(["omarchy-agent-account-home", agent], timeout=5)
    home = out if code == 0 else ""
    prefix = ["env", "-u", home_env, "%s=%s" % (pin, home)]
    if home:
        prefix.append("%s=%s" % (home_env, home))
    return prefix


def agent_command(plan, run=_runner.run, home=None, environ=None):
    """The command to run inside the terminal, for a plan from agents.build_launch."""
    argv = list(plan["argv"])
    if not argv:
        raise LaunchError("no-agent", "no agent to start")
    binary = agents.binary_of(argv)
    # Replace the program name only, never an argument that happens to match it.
    own = user_install(plan["agent"], run, home) if plan["agent"] == binary else ""
    if own:
        argv[argv.index(binary)] = own
    if plan["how"] == "stdin" and plan.get("stdin") is not None:
        # The first message goes in on stdin, as omarchy-agent does for Amp.
        argv = ["bash", "-c", 'printf "%s\\n" "$1" | exec "$0"', argv[0], plan["stdin"]]
    return account_prefix(plan["agent"], run, environ) + argv


def terminal_command(command):
    return ["omarchy-launch-tui", "--app-id=" + APP_ID] + command


def _notify(plan, run):
    def say(key, *args):
        code, out, _ = run(["omarchy-i18n"] + [key] + list(args), timeout=5)
        return out.strip() if code == 0 and out.strip() else ""
    if plan["known"]:
        title = say("agents.promptOnClipboard", plan["display"]) or _CLIP_TEXT["title"] % plan["display"]
        body = say("agents.promptOnClipboardBody") or _CLIP_TEXT["body"]
    else:
        title = _CLIP_TEXT["generic_title"] % plan["display"]
        body = _CLIP_TEXT["body"]
    code, _, _ = run(["omarchy-notification-send", "-g", "\U000f0207", title, body], timeout=5)
    return code == 0


def launch(plan, cwd, run=_runner.run, spawn=subprocess.Popen, dry_run=False, home=None, environ=None):
    """Starts the agent. Returns a report; raises LaunchError with a code the panel can translate."""
    home = home or os.path.expanduser("~")
    if plan.get("how") == "none" or not plan.get("argv"):
        raise LaunchError("no-agent", "no default agent")
    if shutil.which(agents.binary_of(plan["argv"])) is None and not user_install(plan["agent"], run, home):
        raise LaunchError("not-installed", "%s is not installed" % plan["display"])
    cwd = ctxmod.launch_dir(cwd, home)
    command = agent_command(plan, run, home, environ)
    full = terminal_command(command)
    report = {"ok": True, "display": plan["display"], "cwd": cwd, "command": full,
              "clipboard": plan["clipboard"] is not None, "notified": False, "dry_run": dry_run}
    if dry_run:
        return report
    if plan["clipboard"] is not None:
        code, _, err = run(["wl-copy"], timeout=5, input=plan["clipboard"])
        if code != 0:
            raise LaunchError("clipboard-failed", (err or "wl-copy failed").strip()[:200])
        report["notified"] = _notify(plan, run)
    try:
        spawn(full, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
              start_new_session=True)
    except OSError as e:
        raise LaunchError("start-failed", str(e))
    return report


def copy_only(text, run=_runner.run):
    code, _, err = run(["wl-copy"], timeout=5, input=text)
    if code != 0:
        raise LaunchError("clipboard-failed", (err or "wl-copy failed").strip()[:200])
    return {"ok": True}
