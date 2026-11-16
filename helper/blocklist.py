"""Windows that must never be captured: password managers, banking, private browsing."""


def match(window, blocklist):
    """Returns why a window is blocked ("class:keepassxc"), or "" when it is fine."""
    cls = str((window or {}).get("class", "")).lower()
    title = str((window or {}).get("title", "")).lower()
    for pattern in blocklist.get("classes", []):
        if pattern and pattern in cls:
            return "class:" + pattern
    for pattern in blocklist.get("titles", []):
        if pattern and pattern in title:
            return "title:" + pattern
    return ""


def overlaps(window, geometry):
    """True when a window's box and an (x, y, w, h) area share any pixels."""
    try:
        wx, wy = window["at"]
        ww, wh = window["size"]
        gx, gy, gw, gh = geometry
    except (KeyError, TypeError, ValueError):
        return False
    return wx < gx + gw and gx < wx + ww and wy < gy + gh and gy < wy + wh


def find_blocked(windows, blocklist, geometry=None):
    """The first blocked window among `windows` (those under `geometry` when given).

    Returns {"class", "reason"} or None. Only the class is reported, never the title.
    """
    for w in windows or []:
        if geometry is not None and not overlaps(w, geometry):
            continue
        reason = match(w, blocklist)
        if reason:
            return {"class": str(w.get("class", "")), "reason": reason}
    return None
