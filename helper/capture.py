"""Screen capture: a region or the active window, saved as a PNG in the cache.

Coordinates are Hyprland's global logical coordinates, which is what both slurp
and grim use, so monitors with different scales need no special handling here.
"""
import json
import os
import re
import shutil
import tempfile
import time

import runner as _runner

MAX_EDGE = 1920
MAX_BYTES = 2_000_000
MIN_EDGE = 600
_GEOM = re.compile(r"^\s*(-?\d{1,6}),(-?\d{1,6})\s+(\d{1,6})x(\d{1,6})\s*$")


class CaptureError(Exception):
    def __init__(self, code, message=""):
        super().__init__(message or code)
        self.code = code
        self.message = message or code


def cache_dir():
    base = os.environ.get("SNAP_TO_AGENT_CACHE") or os.path.join(
        os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache"), "snap-to-agent")
    os.makedirs(base, mode=0o700, exist_ok=True)
    return base


def parse_geometry(text):
    """Parses "x,y wxh" into ints. Raises CaptureError for anything else."""
    m = _GEOM.match(str(text or ""))
    if not m:
        raise CaptureError("bad-geometry", "expected 'x,y WxH'")
    x, y, w, h = (int(g) for g in m.groups())
    if w < 1 or h < 1:
        raise CaptureError("bad-geometry", "empty area")
    return x, y, w, h


def fmt_geometry(g):
    return "%d,%d %dx%d" % g


def active_window(run=_runner.run):
    """The focused window as Hyprland describes it, or None."""
    code, out, _ = run(["hyprctl", "activewindow", "-j"])
    if code != 0:
        raise CaptureError("no-hyprland", "hyprctl failed")
    try:
        win = json.loads(out or "{}")
    except ValueError:
        return None
    return win if isinstance(win, dict) and win.get("address") else None


def window_geometry(win):
    try:
        x, y = (int(v) for v in win["at"])
        w, h = (int(v) for v in win["size"])
    except (KeyError, TypeError, ValueError):
        raise CaptureError("no-window", "window has no geometry")
    if w < 1 or h < 1:
        raise CaptureError("no-window", "window has no size")
    return x, y, w, h


def select_region(run=_runner.run):
    code, out, _ = run(["slurp", "-f", "%x,%y %wx%h"], timeout=120)
    if code == 127:
        raise CaptureError("missing-slurp", "slurp is not installed")
    if code != 0 or not out.strip():
        raise CaptureError("cancelled", "selection cancelled")
    return parse_geometry(out)


def pick_region_tool(preference="auto"):
    """"omasnap" (Omarchy's own selector) when it is there, else "slurp". A preference wins if usable."""
    if preference == "slurp":
        return "slurp"
    if preference in ("auto", "omasnap") and shutil.which("omasnap"):
        return "omasnap"
    return "slurp"


def select_with_omasnap(run=_runner.run):
    """Lets the user pick a region with omasnap and returns the saved picture's path.

    omasnap draws the overlay and saves the cropped capture into a folder given by
    OMASNAP_SCREENSHOT_DIR, so there is no geometry to read, only the picture.
    Raises CaptureError("cancelled") when nothing was saved and ("missing-omasnap") when absent.
    """
    folder = tempfile.mkdtemp(dir=cache_dir(), prefix=".omasnap-")
    try:
        code, _, err = run(["env", "OMASNAP_SCREENSHOT_DIR=" + folder, "omasnap", "--capture-region", "--save"],
                           timeout=180)
        if code == 127:
            raise CaptureError("missing-omasnap", "omasnap is not installed")
        pictures = sorted((os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(".png")),
                          key=os.path.getmtime)
        if not pictures:
            raise CaptureError("cancelled", "selection cancelled")
        target = new_path()
        shutil.move(pictures[-1], target)
        return target
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def new_path():
    t = time.time()
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(t)) + "-%03d" % int((t % 1) * 1000)
    return os.path.join(cache_dir(), stamp + ".png")


def image_size(path, run=_runner.run):
    code, out, _ = run(["magick", "identify", "-format", "%w %h", path])
    try:
        w, h = out.split()
        return int(w), int(h)
    except (ValueError, TypeError):
        return 0, 0


def shrink(path, run=_runner.run, max_edge=None, max_bytes=None):
    """Scales to MAX_EDGE on the long side, then 15% smaller per step until under MAX_BYTES.

    Stops after 8 steps or before the short side would drop under MIN_EDGE.

    Returns True when the file was changed. Without ImageMagick the image is
    sent as captured and that is reported by the caller.
    """
    max_edge = max_edge or MAX_EDGE
    max_bytes = max_bytes or MAX_BYTES
    code, _, _ = run(["magick", path, "-resize", "%dx%d>" % (max_edge, max_edge), "-strip", path])
    if code == 127:
        return False
    for _ in range(8):
        if os.path.getsize(path) <= max_bytes:
            break
        w, h = image_size(path, run)
        if min(w, h) * 0.85 < MIN_EDGE:
            break
        run(["magick", path, "-resize", "85%", path])
    return True


def capture(mode, geometry=None, run=_runner.run, guard=None, limits=None, region_tool="auto"):
    """Captures and returns {path, geometry, width, height, bytes, window}.

    mode "region": geometry "x,y WxH" skips the selector (used by tests and the CLI).
    mode "window": the focused window.
    guard(geometry, window) may raise CaptureError to stop before anything is captured.
    limits is {"max_edge", "max_bytes"}.
    """
    win = None
    if mode == "region" and not geometry and pick_region_tool(region_tool) == "omasnap":
        # No geometry comes back from omasnap, so the guard checks every visible window first.
        if guard:
            guard(None, None)
        path = select_with_omasnap(run)
        os.chmod(path, 0o600)
        limits = limits or {}
        shrunk = shrink(path, run, limits.get("max_edge"), limits.get("max_bytes"))
        w, h = image_size(path, run)
        return {"path": path, "geometry": "", "width": w, "height": h, "bytes": os.path.getsize(path),
                "shrunk": shrunk, "window": None, "tool": "omasnap"}
    if mode == "region":
        g = parse_geometry(geometry) if geometry else select_region(run)
    elif mode == "window":
        win = active_window(run)
        if not win:
            raise CaptureError("no-window", "no focused window")
        g = window_geometry(win)
    else:
        raise CaptureError("bad-mode", "unknown mode: %s" % mode)
    if guard:
        guard(g, win)
    path = new_path()
    code, _, err = run(["grim", "-g", fmt_geometry(g), path], timeout=30)
    if code == 127:
        raise CaptureError("missing-grim", "grim is not installed")
    if code != 0 or not os.path.exists(path):
        raise CaptureError("capture-failed", (err or "grim failed").strip()[:200])
    os.chmod(path, 0o600)
    limits = limits or {}
    shrunk = shrink(path, run, limits.get("max_edge"), limits.get("max_bytes"))
    w, h = image_size(path, run)
    return {"path": path, "geometry": fmt_geometry(g), "width": w, "height": h,
            "bytes": os.path.getsize(path), "shrunk": shrunk, "window": win}
