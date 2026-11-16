"""Settings: built-in defaults merged with ~/.config/snap-to-agent/config.json.

A missing or broken file means the defaults, never a crash. Unknown keys are
ignored and wrongly typed values fall back to the default.
"""
import copy
import json
import os

DEFAULTS = {
    "retention_days": 7,
    "ocr": True,
    "hook": False,
    "image": {"max_edge": 1920, "max_bytes": 2_000_000},
    "questions": {},  # mode -> text, overrides compose.DEFAULT_QUESTIONS
    "blocklist": {
        # Case-insensitive substrings of the window class or title. Best effort:
        # a site name is only seen when it is in the window title.
        "classes": ["keepassxc", "1password", "bitwarden", "enpass", "proton-pass", "seahorse",
                    "gnome-keyring", "org.gnome.seahorse"],
        "titles": ["bankid", "internetbank", "online banking", "netbank", "swedbank", "handelsbanken",
                   "nordea", "paypal", "revolut", "hsbc", "1password", "bitwarden", "keepass",
                   "incognito", "private browsing", "inprivate", "(private)", "private window"],
    },
}


def config_path():
    home = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(home, "snap-to-agent", "config.json")


def _merge(default, given):
    """Takes `given` where it has the same type as the default; recurses into dicts."""
    out = copy.deepcopy(default)
    if not isinstance(given, dict):
        return out
    for key, value in default.items():
        if key not in given:
            continue
        got = given[key]
        if isinstance(value, dict) and isinstance(got, dict):
            out[key] = _merge(value, got) if value else {k: str(v) for k, v in got.items() if isinstance(v, str)}
        elif isinstance(value, bool):
            if isinstance(got, bool):
                out[key] = got
        elif isinstance(value, int):
            if isinstance(got, int) and not isinstance(got, bool) and got >= 0:
                out[key] = got
        elif isinstance(value, list):
            if isinstance(got, list) and all(isinstance(x, str) for x in got):
                out[key] = [x.strip().lower() for x in got if x.strip()][:200]
    return out


def load(path=None):
    try:
        with open(path or config_path(), encoding="utf-8") as f:
            given = json.load(f)
    except (OSError, ValueError):
        given = {}
    return _merge(DEFAULTS, given)


# Bounds applied when settings are saved from the panel.
_LIMITS = {"retention_days": (0, 3650)}
_IMAGE_LIMITS = {"max_edge": (200, 8000), "max_bytes": (100_000, 20_000_000)}


def _clamp(value, low, high):
    return max(low, min(high, value))


def save(updates, path=None):
    """Merges known, valid settings into the file and returns the effective config.

    Unknown keys and wrongly typed values are dropped, numbers are kept within sane bounds.
    The file is written with mode 600 and replaced atomically.
    """
    current = load(path)
    merged = _merge(current, updates if isinstance(updates, dict) else {})
    for key, (low, high) in _LIMITS.items():
        merged[key] = _clamp(merged[key], low, high)
    for key, (low, high) in _IMAGE_LIMITS.items():
        merged["image"][key] = _clamp(merged["image"][key], low, high)
    target = path or config_path()
    os.makedirs(os.path.dirname(target), mode=0o700, exist_ok=True)
    tmp = target + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2)
        f.write("\n")
    os.replace(tmp, target)
    return merged


def reset(path=None):
    try:
        os.remove(path or config_path())
    except OSError:
        pass
    return load(path)
