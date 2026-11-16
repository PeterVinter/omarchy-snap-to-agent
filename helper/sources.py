"""Text sources that are not screenshots: clipboard and selection, notifications."""
import json
import os
import time

import runner as _runner

MAX_TEXT = 64_000
NOTIFICATION_LIMIT = 8


def _state_home():
    return os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state")


def notification_path():
    return os.path.join(_state_home(), "omarchy", "notifications", "history.json")


def _clean(text, limit):
    text = str(text or "").replace("\x00", "")
    return text if len(text) <= limit else text[:limit - 1] + "…"


def list_notifications(path=None, limit=NOTIFICATION_LIMIT):
    """The newest notifications from Omarchy's history, as plain records.

    Returns {ok, items} or {ok: False, error}. The format is Omarchy's own and may change, so
    anything unexpected gives a named error instead of a crash.
    """
    try:
        with open(path or notification_path(), encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {"ok": False, "error": "no-notifications"}
    except (OSError, ValueError):
        return {"ok": False, "error": "notifications-unreadable"}
    if not isinstance(data, list):
        return {"ok": False, "error": "notifications-unreadable"}
    items = []
    for entry in data:
        if not isinstance(entry, dict) or not (entry.get("summary") or entry.get("body")):
            continue
        ts = entry.get("ts")
        items.append({"index": len(items), "app": _clean(entry.get("app"), 80),
                      "summary": _clean(entry.get("summary"), 200), "body": _clean(entry.get("body"), 2000),
                      "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)) if isinstance(ts, (int, float)) else ""})
        if len(items) >= limit:
            break
    if not items:
        return {"ok": False, "error": "no-notifications"}
    return {"ok": True, "items": items}


def notification_text(item):
    lines = ["App: " + item["app"]] if item.get("app") else []
    if item.get("time"):
        lines.append("Time: " + item["time"])
    if item.get("summary"):
        lines.append("Summary: " + item["summary"])
    if item.get("body"):
        lines.append("Body: " + item["body"])
    return "\n".join(lines)


def read_text_clipboard(run=_runner.run):
    """The selection if there is one, else the clipboard. Returns {ok, kind, text} or {ok: False, error}."""
    for kind, argv in (("selection", ["wl-paste", "-p", "-n"]), ("clipboard", ["wl-paste", "-n"])):
        code, out, _ = run(argv, timeout=5)
        if code == 127:
            return {"ok": False, "error": "missing-wl-paste"}
        if code == 0 and out.strip() and "\x00" not in out:
            return {"ok": True, "kind": kind, "text": out[:MAX_TEXT]}
    return {"ok": False, "error": "empty-clipboard"}


def clipboard_image(path, run=_runner.run):
    """Saves an image from the clipboard to `path`. True when there was one."""
    code, types, _ = run(["wl-paste", "--list-types"], timeout=5)
    if code != 0 or "image/png" not in types.split():
        return False
    code, _, _ = run(["sh", "-c", 'wl-paste -t image/png > "$1"', "sh", path], timeout=10)
    return code == 0 and os.path.exists(path) and os.path.getsize(path) > 0


def error_text(record, output, output_found):
    """The text block for a failed command."""
    lines = ["Command: " + record["command"], "Exit code: %d" % record["rc"]]
    if record.get("cwd"):
        lines.append("Directory: " + record["cwd"])
    if record.get("stale"):
        lines.append("(This failure is more than six hours old.)")
    if output.strip():
        lines += ["", "Output" + ("" if output_found else " (the last lines on screen; the command itself was not found)") + ":", output]
    else:
        lines += ["", "(The command's output could not be read as text.)"]
    return "\n".join(lines)
