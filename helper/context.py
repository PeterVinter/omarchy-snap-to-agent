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


class UnknownFormat(ValueError):
    """The compositor's JSON is not in a layout this code knows, so visibility cannot be decided."""


def _ws_key(ws):
    """A comparable identity for a workspace object, or None if it is not in a known layout.

    Hyprland 0.56 identifies a workspace by `id`. Hyprland 0.57 adds `address` (and only numbered
    workspaces keep an `id`), so `address` is preferred when present."""
    if not isinstance(ws, dict):
        return None
    address = ws.get("address")
    if isinstance(address, str) and address:
        return ("address", address)
    wid = ws.get("id")
    if isinstance(wid, int) and not isinstance(wid, bool):
        return ("id", wid)
    return None


def _special_key(ws):
    """The special workspace a monitor shows: its key, or None when none is showing.

    Raises UnknownFormat when the field is not in a known layout, so callers stop instead of
    treating "cannot tell" as "no special workspace"."""
    if not isinstance(ws, dict):
        raise UnknownFormat("specialWorkspace is missing")
    if "address" in ws:  # 0.57: an empty address means none is showing
        if not isinstance(ws["address"], str):
            raise UnknownFormat("specialWorkspace.address")
        return _ws_key(ws)
    if "id" in ws:  # 0.56: id 0 means none is showing
        wid = ws["id"]
        if not isinstance(wid, int) or isinstance(wid, bool):
            raise UnknownFormat("specialWorkspace.id")
        return None if wid == 0 else ("id", wid)
    raise UnknownFormat("specialWorkspace has neither address nor id")


def _shown_workspaces(monitors):
    """Workspace keys on screen: each monitor's active one plus a visible special workspace.

    Raises UnknownFormat if any monitor is not in a known layout."""
    if not isinstance(monitors, list):
        raise UnknownFormat("monitors")
    shown = set()
    for m in monitors:
        if not isinstance(m, dict):
            raise UnknownFormat("monitor")
        active = _ws_key(m.get("activeWorkspace"))
        if active is None:
            raise UnknownFormat("activeWorkspace")
        shown.add(active)
        special = _special_key(m.get("specialWorkspace"))
        if special is not None:
            shown.add(special)
    return shown


def _on_screen(client, shown):
    """True if a mapped, unhidden client sits on a shown workspace. Raises UnknownFormat when a
    window that would count has a workspace this code cannot read."""
    if not client.get("mapped", True) or client.get("hidden", False):
        return False
    key = _ws_key(client.get("workspace"))
    if key is None:
        raise UnknownFormat("client workspace")
    return key in shown


def visible_windows(run=_runner.run):
    """Every window that is on screen right now, most recently focused first.

    Returns None when the compositor could not be asked or answered in a layout this code does not
    know (see _ws_key), so callers can stop instead of treating "unknown" as "nothing there".
    """
    ccode, cout, _ = run(["hyprctl", "clients", "-j"])
    mcode, mout, _ = run(["hyprctl", "monitors", "-j"])
    if ccode != 0 or mcode != 0:
        return None
    try:
        clients = json.loads(cout)
        shown = _shown_workspaces(json.loads(mout))
        if not isinstance(clients, list) or not all(isinstance(c, dict) for c in clients):
            return None
        out = [c for c in clients if _on_screen(c, shown)]
    except (ValueError, TypeError, AttributeError):  # UnknownFormat is a ValueError
        return None
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
        shown = _shown_workspaces(json.loads(mout or "[]"))
    except (ValueError, TypeError, AttributeError):
        return None
    best = None
    for c in clients if isinstance(clients, list) else []:
        try:
            cx, cy = c["at"]
            cw, ch = c["size"]
            visible = _on_screen(c, shown)
            if visible and cx <= x < cx + cw and cy <= y < cy + ch:
                if best is None or c.get("focusHistoryID", 99) < best.get("focusHistoryID", 99):
                    best = c
        except UnknownFormat:
            return None
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
