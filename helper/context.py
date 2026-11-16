"""Context to attach to a capture: window, working directory, git, logs, versions."""
import json
import os
import re
import time

import runner as _runner

_TERMINAL_CLASSES = {"foot", "footclient", "alacritty", "kitty", "com.mitchellh.ghostty", "ghostty",
                     "org.wezfurlong.wezterm", "wezterm", "konsole", "xterm", "terminator", "tilix",
                     "gnome-terminal-server", "org.gnome.terminal", "st-256color", "st"}
MAX_LOG_BYTES = 6000


def is_terminal(window_class):
    c = str(window_class or "").lower()
    return c in _TERMINAL_CLASSES or c.startswith("org.omarchy.")


def monitor_name(monitor_id, run=_runner.run):
    code, out, _ = run(["hyprctl", "monitors", "-j"])
    try:
        for m in json.loads(out or "[]"):
            if m.get("id") == monitor_id:
                return str(m.get("name", ""))
    except (ValueError, AttributeError):
        pass
    return ""


def visible_windows(run=_runner.run):
    """Every window that is on screen right now, most recently focused first."""
    _, cout, _ = run(["hyprctl", "clients", "-j"])
    _, mout, _ = run(["hyprctl", "monitors", "-j"])
    try:
        clients = json.loads(cout or "[]")
        shown = {(m.get("activeWorkspace") or {}).get("id") for m in json.loads(mout or "[]")}
    except ValueError:
        return []
    out = [c for c in clients if isinstance(c, dict) and c.get("mapped", True) and not c.get("hidden", False)
           and (c.get("workspace") or {}).get("id") in shown]
    return sorted(out, key=lambda c: c.get("focusHistoryID", 99))


def window_at(x, y, run=_runner.run):
    """The most recently focused visible window that covers a screen point, or None.

    Used for region captures: the context should describe what is under the
    region, which is not always the window that has keyboard focus.
    """
    _, cout, _ = run(["hyprctl", "clients", "-j"])
    _, mout, _ = run(["hyprctl", "monitors", "-j"])
    try:
        clients = json.loads(cout or "[]")
        shown = {(m.get("activeWorkspace") or {}).get("id") for m in json.loads(mout or "[]")}
    except ValueError:
        return None
    best = None
    for c in clients if isinstance(clients, list) else []:
        try:
            cx, cy = c["at"]
            cw, ch = c["size"]
            visible = c.get("mapped", True) and not c.get("hidden", False) and (c.get("workspace") or {}).get("id") in shown
            if visible and cx <= x < cx + cw and cy <= y < cy + ch:
                if best is None or c.get("focusHistoryID", 99) < best.get("focusHistoryID", 99):
                    best = c
        except (KeyError, TypeError, ValueError):
            continue
    return best


def terminal_cwd(pid, run=_runner.run):
    """The shell's directory in a terminal window, via Omarchy's own helper. "" if unknown."""
    if not isinstance(pid, int) or pid < 2:
        return ""
    code, out, _ = run(["omarchy-cmd-terminal-cwd", str(pid)])
    path = out.strip()
    return path if code == 0 and path.startswith("/") and os.path.isdir(path) else ""


def git_info(cwd, run=_runner.run):
    if not cwd:
        return None
    code, out, _ = run(["git", "-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"], timeout=3)
    if code != 0 or not out.strip():
        return None
    branch = out.strip()
    _, status, _ = run(["git", "-C", cwd, "status", "--porcelain"], timeout=3)
    return {"branch": branch, "dirty": bool(status.strip())}


def recent_logs(pid, lines=50, run=_runner.run):
    """The last user-journal lines of a process, capped in size. "" when there are none."""
    if not isinstance(pid, int) or pid < 2:
        return ""
    code, out, _ = run(["journalctl", "--user", "-n", str(lines), "--no-pager", "-o", "short-iso",
                        "_PID=%d" % pid], timeout=5)
    text = out.strip() if code == 0 else ""
    if text.startswith("-- No entries"):
        return ""
    return text[-MAX_LOG_BYTES:]


def omarchy_version(run=_runner.run):
    code, out, _ = run(["omarchy", "version"], timeout=5)
    version = out.strip().splitlines()[0] if code == 0 and out.strip() else ""
    return version if re.fullmatch(r"[0-9A-Za-z._+-]{1,40}", version) else ""


def gather(win, run=_runner.run, home=None):
    """Builds the context record for the window that was focused at capture time."""
    home = home or os.path.expanduser("~")
    win = win or {}
    pid = win.get("pid") if isinstance(win.get("pid"), int) else 0
    cls = str(win.get("class", ""))
    terminal = is_terminal(cls)
    cwd = terminal_cwd(pid, run) if terminal else ""
    workspace = win.get("workspace") or {}
    return {
        "app_class": cls,
        "title": str(win.get("title", ""))[:300],
        "workspace": str(workspace.get("name", workspace.get("id", ""))),
        "monitor": monitor_name(win.get("monitor"), run) if win else "",
        "terminal": terminal,
        "cwd": launch_dir(cwd, home),
        "cwd_from": "terminal" if cwd and launch_dir(cwd, home) == cwd else "default",
        "git": git_info(cwd, run),
        "logs": recent_logs(pid, 50, run),
        "omarchy_version": omarchy_version(run),
        "time": time.strftime("%Y-%m-%d %H:%M:%S %z"),
    }


def launch_dir(cwd, home=None):
    """Where the agent starts: the resolved directory, else ~/Work if it exists, else ~.

    Same rule as omarchy-agent: agents refuse to remember folder trust for $HOME and
    would ask on every start, so a start in $HOME moves to ~/Work when that exists.
    """
    home = home or os.path.expanduser("~")
    if cwd and os.path.isdir(cwd) and os.path.realpath(cwd) != os.path.realpath(home):
        return cwd
    work = os.path.join(home, "Work")
    return work if os.path.isdir(work) else home


def tilde(path, home=None):
    home = home or os.path.expanduser("~")
    return "~" + path[len(home):] if path == home or path.startswith(home + "/") else path
