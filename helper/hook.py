"""Installs and removes the shell hook, and reads what it recorded.

The hook is installed only on request (`snap-to-agent install-hook`), by adding one clearly
marked block to ~/.bashrc and ~/.zshrc (the latter only if it exists). Removing it takes that
block out again and deletes the recorded file.
"""
import os
import time

BEGIN = "# >>> omarchy-snap-to-agent hook >>>"
END = "# <<< omarchy-snap-to-agent hook <<<"
STALE_SECONDS = 6 * 3600


def plugin_dir():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def state_dir(home=None):
    """Where the hook writes. An explicit `home` (tests) wins over the environment."""
    if home:
        return os.path.join(home, ".local", "state", "snap-to-agent")
    base = os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state")
    return os.path.join(base, "snap-to-agent")


def _block(shell, base):
    script = os.path.join(base, "hook", "snap-hook." + shell)
    return "%s\n[ -r '%s' ] && . '%s'\n%s\n" % (BEGIN, script, script, END)


def _rc_files(home):
    files = [("bash", os.path.join(home, ".bashrc"))]
    zshrc = os.path.join(home, ".zshrc")
    if os.path.exists(zshrc):
        files.append(("zsh", zshrc))
    return files


def _strip(text):
    """The text without our block, and whether there was one."""
    if BEGIN not in text:
        return text, False
    start = text.index(BEGIN)
    end = text.find(END, start)
    if end < 0:
        return text, False
    end += len(END)
    if text[end:end + 1] == "\n":
        end += 1
    return text[:start] + text[end:], True


def status(home=None):
    home = home or os.path.expanduser("~")
    out = {}
    for shell, path in _rc_files(home):
        try:
            with open(path, encoding="utf-8") as f:
                out[shell] = BEGIN in f.read()
        except OSError:
            out[shell] = False
    return out


def install(home=None, base=None):
    """Adds the block (once). Returns the files that changed."""
    home = home or os.path.expanduser("~")
    base = base or plugin_dir()
    changed = []
    for shell, path in _rc_files(home):
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except FileNotFoundError:
            text = ""
        if BEGIN in text:
            continue
        if text and not text.endswith("\n"):
            text += "\n"
        with open(path, "w", encoding="utf-8") as f:
            f.write(text + "\n" + _block(shell, base))
        changed.append(path)
    return changed


def uninstall(home=None):
    """Removes the block and the recorded file. Returns the files that changed."""
    home = home or os.path.expanduser("~")
    changed = []
    for _, path in _rc_files(home):
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        new, found = _strip(text)
        if found:
            new = new.rstrip("\n") + "\n" if new.strip() else ""
            with open(path, "w", encoding="utf-8") as f:
                f.write(new)
            changed.append(path)
    try:
        os.remove(os.path.join(state_dir(home), "last-error.txt"))
    except OSError:
        pass
    return changed


def read_last(home=None, now=None):
    """What the hook recorded: {rc, time, cwd, pane, command, stale} or None."""
    try:
        with open(os.path.join(state_dir(home), "last-error.txt"), encoding="utf-8", errors="replace") as f:
            lines = f.read().split("\n")
    except OSError:
        return None
    if len(lines) < 6 or lines[0] != "v1":
        return None
    try:
        fields = {k: v for k, v in (line.split("=", 1) for line in lines[1:5])}
        rc = int(fields["rc"])
        stamp = int(fields["time"])
    except (ValueError, KeyError):
        return None
    command = "\n".join(lines[5:]).strip()
    if not command:
        return None
    return {"rc": rc, "time": stamp, "cwd": fields.get("cwd", ""), "pane": fields.get("pane", ""),
            "command": command[:2000], "stale": (now or time.time()) - stamp > STALE_SECONDS}


def extract_output(pane_text, command, max_lines=200, max_bytes=64_000):
    """The failed command's output from a terminal pane's text.

    Looks for the last line that shows the command, takes what follows, and drops the final
    line (the new prompt). If the command is not on screen the last lines are used.
    """
    lines = [l.rstrip() for l in str(pane_text or "").splitlines()]
    while lines and not lines[-1]:
        lines.pop()
    key = command.strip().splitlines()[0][:60] if command.strip() else ""
    idx = max((i for i, l in enumerate(lines) if key and key in l), default=-1)
    out = lines[idx + 1:] if idx >= 0 else lines
    if idx >= 0 and out:
        out = out[:-1]  # the prompt that came back
    out = out[-max_lines:]
    text = "\n".join(out)
    return text[-max_bytes:], idx >= 0
