"""The last sends, for "send again" and "delete", and the cleanup of old captures.

Everything lives in the cache folder (mode 600/700). An entry keeps only the masked
question; the captured state needed to open it again (with every text masked) is a separate file in the same
folder, removed with the entry and by the retention cleanup.
"""
import json
import os
import re
import subprocess
import sys
import time

import capture
import mask

MAX_ENTRIES = 20
_ID = re.compile(r"^[0-9]{8}-[0-9]{6}-[0-9]{3}$")
OPEN_SUFFIX = "-context-open.md"   # context file that holds values the user chose to send unmasked
OPEN_TTL = 900                     # seconds; the backstop: these files go after 15 minutes, whatever the retention setting
OPEN_GRACE = 600                   # seconds after the agent started that its own copy of the file is removed
_OWNED = (".png", "-context.md", OPEN_SUFFIX, ".state.json", "last.json")


def _path():
    return os.path.join(capture.cache_dir(), "history.json")


def _write(path, data):
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def load():
    try:
        with open(_path(), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    return [e for e in data if isinstance(e, dict) and _ID.match(str(e.get("id", "")))] if isinstance(data, list) else []


def _state_file(entry_id):
    return os.path.join(capture.cache_dir(), entry_id + ".state.json")


def _remove_files(entry):
    """Deletes the files an entry owns. Only paths inside the cache folder, never anything else."""
    root = os.path.realpath(capture.cache_dir())
    paths = [_state_file(entry["id"])]
    for key in ("capture_path", "file"):
        if entry.get(key):
            paths.append(entry[key])
    for p in paths:
        real = os.path.realpath(p)
        if os.path.dirname(real) == root and real.endswith(_OWNED):
            try:
                os.remove(real)
            except OSError:
                pass


def add(state, question, report, mode):
    """Records a send. `state` is what the panel opened (mode, capture, context, source, ocr)."""
    now = time.time()
    entry_id = time.strftime("%Y%m%d-%H%M%S", time.localtime(now)) + "-%03d" % int((now % 1) * 1000)
    shot = state.get("capture") or {}
    entry = {"id": entry_id, "time": int(now), "mode": mode, "agent": report.get("program", ""),
             "display": report.get("display", ""), "cwd": report.get("cwd", ""), "question": str(question)[:300],
             "capture_path": shot.get("path", ""), "file": report.get("file", "")}
    fd = os.open(_state_file(entry_id), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(mask.scrub_state({k: state.get(k) for k in ("mode", "capture", "context", "source", "ocr")}), f)
    entries = [entry] + load()
    for old in entries[MAX_ENTRIES:]:
        _remove_files(old)
    _write(_path(), entries[:MAX_ENTRIES])
    return entry_id


def scrub_file(path):
    """Masks the texts in a stored state file, in place. For files an older version wrote with the
    raw captured text. Returns True when the file was rewritten. Idempotent: a file that is already
    masked is left alone."""
    try:
        with open(path, encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, ValueError):
        return False
    if not isinstance(state, dict):
        return False
    clean = mask.scrub_state(state)
    if clean == state:
        return False
    try:
        _write(path, clean)
    except OSError:
        return False
    return True


def scrub_legacy():
    """Scrubs every stored state file (last.json and the history states). Returns how many changed."""
    try:
        names = os.listdir(capture.cache_dir())
    except OSError:
        return 0
    changed = 0
    for name in names:
        if name == "last.json" or name.endswith(".state.json"):
            path = os.path.join(capture.cache_dir(), name)
            if os.path.isfile(path) and scrub_file(path):
                changed += 1
    return changed


def listing():
    out = []
    for e in load():
        shot_ok = bool(e.get("capture_path")) and os.path.exists(e["capture_path"])
        out.append({"id": e["id"], "time": e["time"], "mode": e.get("mode", ""), "display": e.get("display", ""),
                    "cwd": e.get("cwd", ""), "question": e.get("question", ""), "thumb": e["capture_path"] if shot_ok else "",
                    "available": os.path.exists(_state_file(e["id"]))})
    return out


def open_state(entry_id):
    """The stored state, to show the preview again. None when it is gone."""
    if not _ID.match(str(entry_id)):
        return None
    scrub_file(_state_file(entry_id))  # an older version may have stored it unmasked
    try:
        with open(_state_file(entry_id), encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, ValueError):
        return None
    entry = next((e for e in load() if e["id"] == entry_id), None)
    if entry:
        state["question"] = entry.get("question", "")
    return state


def delete(entry_id):
    entries = load()
    entry = next((e for e in entries if e["id"] == entry_id), None)
    if not entry:
        return False
    _remove_files(entry)
    _write(_path(), [e for e in entries if e["id"] != entry_id])
    return True


def sweep_open_files(now=None):
    """Removes unmasked context files older than OPEN_TTL. Runs on every helper call, with any retention setting."""
    now = now or time.time()
    root = capture.cache_dir()
    removed = 0
    for name in os.listdir(root):
        path = os.path.join(root, name)
        if name.endswith(OPEN_SUFFIX) and os.path.isfile(path) and os.path.getmtime(path) < now - OPEN_TTL:
            try:
                os.remove(path)
                removed += 1
            except OSError:
                pass
    return removed


def remove_open_file_later(path, delay=OPEN_GRACE, spawn=subprocess.Popen):
    """After the agent has started, removes the unmasked context file it was pointed at.

    The agent reads the file by path, usually as its first step, but it may wait for the user to approve
    that read, so the file stays for a grace period. A detached process does the removal, so it also
    happens when no further helper call comes. Only this plugin's own `*-context-open.md` files in
    the cache folder qualify. Returns whether a removal was scheduled."""
    if not _is_open_file(path):
        return False
    spawn([sys.executable, "-I", os.path.join(os.path.dirname(os.path.abspath(__file__)), "remove_later.py"),
           str(int(delay)), path], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
          start_new_session=True)
    return True


def _is_open_file(path):
    path = str(path or "")
    return (path.endswith(OPEN_SUFFIX) and os.path.dirname(os.path.realpath(path)) == os.path.realpath(capture.cache_dir())
            and not os.path.islink(path))


def remove_open_file(path):
    """Removes one unmasked context file, if it is one of ours. Returns whether it was removed."""
    if not _is_open_file(path):
        return False
    try:
        os.remove(path)
        return True
    except OSError:
        return False


def cleanup(days, now=None):
    """Removes captures, context files and history entries older than `days`. 0 keeps everything."""
    now = now or time.time()
    root = capture.cache_dir()
    removed = sweep_open_files(now)
    if not days or days < 1:
        return removed
    cutoff = now - days * 86400
    for name in os.listdir(root):
        path = os.path.join(root, name)
        if name.endswith(_OWNED) and os.path.isfile(path) and os.path.getmtime(path) < cutoff:
            try:
                os.remove(path)
                removed += 1
            except OSError:
                pass
    kept = [e for e in load() if e["time"] >= cutoff]
    if len(kept) != len(load()):
        _write(_path(), kept)
    return removed
