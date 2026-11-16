#!/usr/bin/env python3
"""Command line entry point for Omarchy Snap to Agent. Prints JSON, never crashes.

  snap.py capture region|window [--geometry "x,y WxH"]
  snap.py agent
  snap.py compose|send|copy   (JSON on stdin; send also takes --dry-run)
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agents  # noqa: E402
import capture  # noqa: E402
import compose  # noqa: E402
import context  # noqa: E402
import launch  # noqa: E402


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
        source = "window" if win else ""
        if mode == "region" and not win:
            x, y, w, h = capture.parse_geometry(shot["geometry"])
            win = context.window_at(x + w // 2, y + h // 2)
            source = "under-region" if win else ""
        if not win:
            win, source = focused, "focused"
        ctx = context.gather(win)
        ctx["window_source"] = source
        state = {"mode": mode, "capture": shot, "context": ctx}
        save_last(state)
        return dict(state, ok=True)
    except capture.CaptureError as e:
        return {"ok": False, "error": e.code, "message": e.message}


def save_last(state):
    """Keeps the last capture so `resend` can open it again. Local, mode 600."""
    path = os.path.join(capture.cache_dir(), "last.json")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(state, f)


def read_state():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        raise capture.CaptureError("bad-input", "expected JSON on stdin")
    if not isinstance(data, dict):
        raise capture.CaptureError("bad-input", "expected a JSON object")
    return data


def _compose(data, write_file=False):
    allow = [i for i in data.get("allow", []) if isinstance(i, int)]
    return compose.compose(
        str(data.get("question", "")), data.get("context") or {}, data.get("capture"),
        str(data.get("mode", "region")), allow=allow, ocr_text=str(data.get("ocr_text", "")),
        send_image=data.get("send_image", True) is not False,
        context_text=data.get("context_text") if isinstance(data.get("context_text"), str) else None,
        write_file=write_file)


def cmd_compose(_args):
    r = _compose(read_state())
    r.pop("full_prompt", None)
    return dict(r, ok=r["ok"], error=None if r["ok"] else "no-default-agent")


def cmd_send(args):
    """Starts the agent. Only ever called after the user confirmed the preview."""
    r = _compose(read_state(), write_file=True)
    if not r["ok"]:
        return {"ok": False, "error": "no-default-agent", "problem": r["target"].get("problem", "")}
    t = r["target"]
    plan = agents.build_launch(t["agent"], r["prompt"])
    try:
        report = launch.launch(plan, t["cwd"], dry_run="--dry-run" in args)
    except launch.LaunchError as e:
        return {"ok": False, "error": e.code, "message": e.message}
    return {"ok": True, "display": report["display"], "cwd": report["cwd"], "clipboard": report["clipboard"],
            "notified": report["notified"], "file": r["file"], "dry_run": report["dry_run"],
            "program": plan["agent"]}


def cmd_copy(_args):
    r = _compose(read_state())
    try:
        launch.copy_only(r["full_prompt"])
    except launch.LaunchError as e:
        return {"ok": False, "error": e.code, "message": e.message}
    return {"ok": True}


def cmd_agent(_args):
    name, problem = agents.default_agent()
    if problem:
        return {"ok": False, "error": "no-default-agent", "problem": problem}
    ad = agents.adapter_for(name)
    return {"ok": True, "agent": name, "display": ad["display"], "known": ad["known"],
            "installed": agents.installed(name), "how": ad["how"]}


def main(argv):
    cmds = {"capture": cmd_capture, "agent": cmd_agent, "compose": cmd_compose, "send": cmd_send, "copy": cmd_copy}
    if not argv or argv[0] not in cmds:
        out = {"ok": False, "error": "usage", "message": "capture region|window | agent | compose | send | copy"}
    else:
        try:
            out = cmds[argv[0]](argv[1:])
        except capture.CaptureError as e:
            out = {"ok": False, "error": e.code, "message": e.message}
        except Exception as e:  # last resort: report, do not crash the shell
            out = {"ok": False, "error": "internal", "message": "%s: %s" % (type(e).__name__, e)}
    print(json.dumps(out))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
