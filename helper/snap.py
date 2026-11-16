#!/usr/bin/env python3
"""Command line entry point for Omarchy Snap to Agent. Prints JSON, never crashes.

  snap.py capture region|window|error|clipboard [--geometry "x,y WxH"]
  snap.py capture notification --index N
  snap.py notifications           the newest notifications, for the picker
  snap.py agent                   the default agent
  snap.py last                    the last capture
  snap.py compose|send|copy       JSON on one line on stdin (send also takes --dry-run)
  snap.py install-hook [--yes] | uninstall-hook | hook-status
  snap.py history | history-open ID | history-delete ID | cleanup
  snap.py settings-get | settings-set (JSON on stdin) | settings-reset
"""
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agents  # noqa: E402
import blocklist  # noqa: E402
import capture  # noqa: E402
import compose  # noqa: E402
import config  # noqa: E402
import context  # noqa: E402
import history  # noqa: E402
import hook  # noqa: E402
import launch  # noqa: E402
import ocr  # noqa: E402
import runner  # noqa: E402
import sources  # noqa: E402


class Problem(Exception):
    def __init__(self, code, message=""):
        super().__init__(message or code)
        self.code = code
        self.message = message or code


def _blocked_error(found):
    return capture.CaptureError("blocked", "%s is on the blocklist" % (found.get("class") or "this window"))


def _guard_for(cfg):
    """Stops a capture before it starts when a blocked window is in the way."""
    def guard(geometry, win):
        windows = [win] if win else context.visible_windows()
        found = blocklist.find_blocked(windows, cfg["blocklist"], None if win else geometry)
        if found:
            raise _blocked_error(found)
    return guard


def _check_focused(cfg):
    """For text modes: the focused window must not be a blocked one."""
    try:
        win = capture.active_window()
    except capture.CaptureError:
        return None
    found = blocklist.find_blocked([win] if win else [], cfg["blocklist"])
    if found:
        raise _blocked_error(found)
    return win


def _with_ocr(state, cfg):
    shot = state.get("capture")
    if not shot or not cfg["ocr"]:
        return
    result = ocr.read_text(shot["path"])
    state["ocr"] = {"text": result.get("text", ""), "missing": bool(result.get("missing")),
                    "package": result.get("package", "")}


def _finish(mode, shot, win, source, cfg, extra_context=None, focused=None, window_source=None):
    ctx = context.gather(win or focused)
    ctx["window_source"] = window_source or ("window" if win else "focused")
    if extra_context:
        ctx.update(extra_context)
    state = {"mode": mode, "capture": shot, "context": ctx}
    if source:
        state["source"] = source
    _with_ocr(state, cfg)
    save_last(state)
    return dict(state, ok=True)


def _capture_image(mode, geometry, cfg):
    try:
        focused = capture.active_window()
    except capture.CaptureError:
        focused = None
    shot = capture.capture(mode, geometry, guard=_guard_for(cfg), limits=cfg["image"])
    win = shot.pop("window", None)
    source = "window" if win else ""
    if mode == "region" and not win:
        x, y, w, h = capture.parse_geometry(shot["geometry"])
        win = context.window_at(x + w // 2, y + h // 2)
        source = "under-region" if win else ""
    if not win:
        win, source = focused, "focused"
    return _finish(mode, shot, win, None, cfg, window_source=source)


def _capture_error(cfg):
    win = _check_focused(cfg)
    rec = hook.read_last()
    if not rec:
        raise capture.CaptureError("no-error-recorded", "no failed command has been recorded")
    output, found, shot = "", False, None
    tmux = shutil.which("tmux")
    if rec["pane"] and tmux:
        code, text, _ = runner.run([tmux, "capture-pane", "-p", "-J", "-S", "-300", "-t", rec["pane"]], timeout=5)
        if code == 0:
            output, found = hook.extract_output(text, rec["command"])
    extra = {"cwd": context.launch_dir(rec["cwd"]), "cwd_from": "terminal"}
    extra["git"] = context.git_info(rec["cwd"])
    if not output.strip() and win:
        # No terminal text to read (foot, ghostty outside tmux): capture the window and read it.
        shot = capture.capture("window", guard=_guard_for(cfg), limits=cfg["image"])
        shot.pop("window", None)
    source = {"kind": "error", "text": sources.error_text(rec, output, found)}
    return _finish("error", shot, win, source, cfg, extra, win)


def _capture_clipboard(cfg):
    win = _check_focused(cfg)
    text = sources.read_text_clipboard()
    if text.get("ok"):
        return _finish("clipboard", None, win, {"kind": text["kind"], "text": text["text"]}, cfg, None, win)
    if text.get("error") == "missing-wl-paste":
        raise capture.CaptureError("missing-wl-paste", "wl-clipboard is not installed")
    path = capture.new_path()
    if sources.clipboard_image(path):
        os.chmod(path, 0o600)
        capture.shrink(path, max_edge=cfg["image"]["max_edge"], max_bytes=cfg["image"]["max_bytes"])
        w, h = capture.image_size(path)
        shot = {"path": path, "geometry": "", "width": w, "height": h, "bytes": os.path.getsize(path), "shrunk": True}
        return _finish("clipboard", shot, win, None, cfg, None, win)
    raise capture.CaptureError("empty-clipboard", "nothing is selected or copied")


def _capture_notification(index, cfg):
    win = _check_focused(cfg)
    listing = sources.list_notifications()
    if not listing["ok"]:
        raise capture.CaptureError(listing["error"], "no notification to send")
    if not 0 <= index < len(listing["items"]):
        raise capture.CaptureError("bad-index", "no such notification")
    item = listing["items"][index]
    return _finish("notification", None, win, {"kind": "notification", "text": sources.notification_text(item)},
                   cfg, None, win)


def _cleanup(cfg=None):
    """Old captures go after the retention period (7 days by default)."""
    try:
        history.cleanup((cfg or config.load())["retention_days"])
    except OSError:
        pass


def cmd_capture(args):
    mode = args[0] if args else ""
    _cleanup()
    geometry = args[args.index("--geometry") + 1] if "--geometry" in args and args.index("--geometry") + 1 < len(args) else None
    cfg = config.load()
    try:
        if mode in ("region", "window"):
            return _capture_image(mode, geometry, cfg)
        if mode == "error":
            return _capture_error(cfg)
        if mode == "clipboard":
            return _capture_clipboard(cfg)
        if mode == "notification":
            try:
                index = int(args[args.index("--index") + 1]) if "--index" in args else 0
            except (ValueError, IndexError):
                raise capture.CaptureError("bad-index", "--index needs a number")
            return _capture_notification(index, cfg)
        raise capture.CaptureError("bad-mode", "unknown mode: %s" % mode)
    except capture.CaptureError as e:
        return {"ok": False, "error": e.code, "message": e.message}


def cmd_notifications(_args):
    return sources.list_notifications()


def save_last(state):
    """Keeps the last capture so `resend` can open it again. Local, mode 600."""
    path = os.path.join(capture.cache_dir(), "last.json")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(state, f)


def read_state():
    # One JSON object on one line: the shell writes it without closing stdin.
    try:
        data = json.loads(sys.stdin.readline())
    except ValueError:
        raise capture.CaptureError("bad-input", "expected JSON on stdin")
    if not isinstance(data, dict):
        raise capture.CaptureError("bad-input", "expected a JSON object")
    return data


def _compose(data, write_file=False):
    allow = [i for i in data.get("allow", []) if isinstance(i, int)]
    cfg = config.load()
    ocr_state = data.get("ocr") if isinstance(data.get("ocr"), dict) else {}
    source = data.get("source") if isinstance(data.get("source"), dict) else None
    return compose.compose(
        str(data.get("question", "")), data.get("context") or {}, data.get("capture"),
        str(data.get("mode", "region")), allow=allow, ocr_text=str(ocr_state.get("text", "")),
        send_image=data.get("send_image", True) is not False,
        context_text=data.get("context_text") if isinstance(data.get("context_text"), str) else None,
        write_file=write_file, source=source, ocr_missing=bool(ocr_state.get("missing")),
        questions=cfg["questions"])


def cmd_compose(_args):
    r = _compose(read_state())
    r.pop("full_prompt", None)
    return dict(r, ok=r["ok"], error=None if r["ok"] else "no-default-agent")


def cmd_send(args):
    """Starts the agent. Only ever called after the user confirmed the preview."""
    data = read_state()
    r = _compose(data, write_file=True)
    if not r["ok"]:
        return {"ok": False, "error": "no-default-agent", "problem": r["target"].get("problem", "")}
    t = r["target"]
    plan = agents.build_launch(t["agent"], r["prompt"])
    try:
        report = launch.launch(plan, t["cwd"], dry_run="--dry-run" in args)
    except launch.LaunchError as e:
        return {"ok": False, "error": e.code, "message": e.message}
    done = {"ok": True, "display": report["display"], "cwd": report["cwd"], "clipboard": report["clipboard"],
            "notified": report["notified"], "file": r["file"], "dry_run": report["dry_run"],
            "program": plan["agent"]}
    if not report["dry_run"]:
        try:
            history.add(data, r["question"], done, str(data.get("mode", "region")))
        except OSError:
            pass  # a full disk must not turn a successful send into an error
    return done


def cmd_copy(_args):
    r = _compose(read_state())
    try:
        launch.copy_only(r["full_prompt"])
    except launch.LaunchError as e:
        return {"ok": False, "error": e.code, "message": e.message}
    return {"ok": True}


def cmd_last(_args):
    """The last capture, for "send again". Local file only."""
    try:
        with open(os.path.join(capture.cache_dir(), "last.json"), encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, ValueError):
        return {"ok": False, "error": "no-last", "message": "nothing captured yet"}
    shot = state.get("capture")
    if shot and not os.path.exists(str(shot.get("path", ""))):
        return {"ok": False, "error": "no-last", "message": "the last capture is gone"}
    return dict(state, ok=True)


def cmd_history(_args):
    _cleanup()
    return {"ok": True, "items": history.listing()}


def cmd_history_open(args):
    state = history.open_state(args[0] if args else "")
    if not state:
        return {"ok": False, "error": "no-last", "message": "that entry is gone"}
    return dict(state, ok=True)


def cmd_history_delete(args):
    return {"ok": history.delete(args[0] if args else "")}


def cmd_settings_get(_args):
    cfg = config.load()
    status = hook.status()
    cfg["hook"] = any(status.values())  # the real state of the shell files, not a stored flag
    return {"ok": True, "config": cfg, "hook": status, "defaults": config.DEFAULTS,
            "path": config.config_path()}


def cmd_settings_set(_args):
    data = read_state()
    cfg = config.save(data.get("config"))
    return {"ok": True, "config": cfg}


def cmd_settings_reset(_args):
    return {"ok": True, "config": config.reset()}


def cmd_cleanup(_args):
    return {"ok": True, "removed": history.cleanup(config.load()["retention_days"])}


def cmd_agent(_args):
    name, problem = agents.default_agent()
    if problem:
        return {"ok": False, "error": "no-default-agent", "problem": problem}
    ad = agents.adapter_for(name)
    return {"ok": True, "agent": name, "display": ad["display"], "known": ad["known"],
            "installed": agents.installed(name), "how": ad["how"]}


def cmd_install_hook(args):
    """Adds the hook to ~/.bashrc (and ~/.zshrc if it exists), after asking."""
    if "--yes" not in args:
        if not sys.stdin.isatty():
            return {"ok": False, "error": "consent-needed", "message": "run it in a terminal, or pass --yes"}
        print("This adds a marked block to ~/.bashrc (and ~/.zshrc if it exists) that loads\n%s\n"
              "It records the last failed command (command, exit code, directory) so you can send it to your agent.\n"
              "Remove it any time with: snap-to-agent uninstall-hook" % os.path.join(hook.plugin_dir(), "hook"),
              file=sys.stderr)
        if input("Install? [y/N] ").strip().lower() not in ("y", "yes"):
            return {"ok": False, "error": "declined", "message": "nothing was changed"}
    changed = hook.install()
    return {"ok": True, "changed": changed, "note": "Open a new terminal for it to take effect."}


def cmd_uninstall_hook(_args):
    return {"ok": True, "changed": hook.uninstall()}


def cmd_hook_status(_args):
    return {"ok": True, "installed": hook.status(), "last": hook.read_last()}


def main(argv):
    cmds = {"capture": cmd_capture, "notifications": cmd_notifications, "agent": cmd_agent, "last": cmd_last,
            "compose": cmd_compose, "send": cmd_send, "copy": cmd_copy,
            "install-hook": cmd_install_hook, "uninstall-hook": cmd_uninstall_hook, "hook-status": cmd_hook_status,
            "history": cmd_history, "history-open": cmd_history_open, "history-delete": cmd_history_delete,
            "settings-get": cmd_settings_get, "settings-set": cmd_settings_set, "settings-reset": cmd_settings_reset,
            "cleanup": cmd_cleanup}
    if not argv or argv[0] not in cmds:
        out = {"ok": False, "error": "usage", "message": " | ".join(sorted(cmds))}
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
