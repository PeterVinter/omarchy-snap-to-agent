#!/usr/bin/env python3
"""Command line entry point for Omarchy Snap to Agent. Prints JSON, never crashes.

  snap.py capture region|window [--geometry "x,y WxH"]
  snap.py agent
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agents  # noqa: E402
import capture  # noqa: E402
import context  # noqa: E402


def cmd_capture(args):
    mode = args[0] if args else ""
    geometry = None
    if "--geometry" in args:
        i = args.index("--geometry")
        geometry = args[i + 1] if i + 1 < len(args) else ""
    try:
        # The window that has focus now is the context, before any panel opens.
        focused = None
        try:
            focused = capture.active_window()
        except capture.CaptureError:
            pass
        shot = capture.capture(mode, geometry)
        win = shot.pop("window", None)
        if mode == "region" and not win:
            x, y, w, h = capture.parse_geometry(shot["geometry"])
            win = context.window_at(x + w // 2, y + h // 2)
        win = win or focused
        return {"ok": True, "capture": shot, "context": context.gather(win)}
    except capture.CaptureError as e:
        return {"ok": False, "error": e.code, "message": e.message}


def cmd_agent(_args):
    name, problem = agents.default_agent()
    if problem:
        return {"ok": False, "error": "no-default-agent", "problem": problem}
    ad = agents.adapter_for(name)
    return {"ok": True, "agent": name, "display": ad["display"], "known": ad["known"],
            "installed": agents.installed(name), "how": ad["how"]}


def main(argv):
    cmds = {"capture": cmd_capture, "agent": cmd_agent}
    if not argv or argv[0] not in cmds:
        out = {"ok": False, "error": "usage", "message": "capture region|window | agent"}
    else:
        try:
            out = cmds[argv[0]](argv[1:])
        except Exception as e:  # last resort: report, do not crash the shell
            out = {"ok": False, "error": "internal", "message": "%s: %s" % (type(e).__name__, e)}
    print(json.dumps(out))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
