"""Builds what is shown in the preview and what is sent: question + context block.

Everything that leaves this module is masked. The originals of masked secrets
stay inside this process; the panel refers to them by id (to undo one).
"""
import os

import agents
import context as ctxmod
import history
import mask as maskmod
import ocr as _ocr

DEFAULT_QUESTIONS = {
    "region": "Help me with what is on my screen.",
    "window": "Help me with what is in this window.",
    "error": "Explain this error and suggest a fix.",
    "notification": "Explain this notification and tell me whether I need to act.",
    "clipboard": "Help me with this text.",
}
INLINE_LIMIT = 24_000

IMAGE_NOTES = {
    "path": "The screenshot is a file on this machine. Open it if you can view images; otherwise use the OCR text.",
}


SOURCE_LABELS = {
    "error": "### The failed command",
    "clipboard": "### Clipboard text",
    "selection": "### Selected text",
    "notification": "### Notification",
}


def default_question(mode, overrides=None):
    text = (overrides or {}).get(mode)
    return text if isinstance(text, str) and text.strip() else DEFAULT_QUESTIONS.get(mode, DEFAULT_QUESTIONS["region"])


def ocr_kinds(text):
    return _ocr.secret_kinds(text or "")


def _fence(text):
    """A code fence longer than any backtick run inside the text."""
    longest = run = 0
    for ch in text:
        run = run + 1 if ch == "`" else 0
        longest = max(longest, run)
    return "`" * max(3, longest + 1)


def _fenced(label, text):
    f = _fence(text)
    return "%s\n%s\n%s\n%s" % (label, f, text.rstrip("\n"), f)


def context_block(ctx, shot=None, mode="region", agent_image_mode="path", ocr_text="", send_image=True, source=None):
    """The markdown context block, unmasked. ctx and shot come from context.gather / capture."""
    ctx = ctx or {}
    lines = ["## Context (Omarchy Snap to Agent, %s capture)" % mode]
    app = ctx.get("app_class") or "unknown"
    title = ctx.get("title")
    lines.append('- App: %s%s' % (app, ' - "%s"' % title if title else ""))
    if mode == "region" and ctx.get("window_source") == "focused":
        lines.append("  (This is the focused window; no window was found under the selected region.)")
    elif mode == "region" and ctx.get("window_source") == "focused-region-unknown":
        lines.append("  (This is the focused window; the selected region may show something else.)")
    where = ["workspace %s" % ctx["workspace"]] if ctx.get("workspace") else []
    if ctx.get("monitor"):
        where.append("monitor %s" % ctx["monitor"])
    if where:
        lines.append("- Screen: " + ", ".join(where))
    cwd = ctx.get("cwd")
    if cwd:
        git = ctx.get("git")
        extra = " (git: %s%s)" % (git["branch"], ", uncommitted changes" if git.get("dirty") else "") if git else ""
        lines.append("- Directory: %s%s" % (ctxmod.tilde(cwd), extra))
    if ctx.get("omarchy_version"):
        lines.append("- Omarchy: %s" % ctx["omarchy_version"])
    if ctx.get("time"):
        lines.append("- Captured: %s" % ctx["time"])
    if shot and send_image:
        lines.append("- Screenshot: %s (%sx%s)" % (shot.get("path"), shot.get("width"), shot.get("height")))
        lines.append("  " + IMAGE_NOTES.get(agent_image_mode, IMAGE_NOTES["path"]))
    elif shot:
        lines.append("- Screenshot: not sent (text only)")
    parts = ["\n".join(lines)]
    if source and str(source.get("text", "")).strip():
        parts.append(_fenced(SOURCE_LABELS.get(source.get("kind"), "### Text"), str(source["text"]).strip()))
    if ocr_text and ocr_text.strip():
        parts.append(_fenced("### Text found in the screenshot (OCR, may contain errors)", ocr_text.strip()))
    if ctx.get("logs"):
        parts.append(_fenced("### Recent log lines", ctx["logs"]))
    return "\n\n".join(parts)


def strip_image_refs(text, shot):
    """Removes the screenshot path and the image notes from text that is sent without the image,
    including from a context the user edited by hand."""
    path = str((shot or {}).get("path") or "")
    notes = set(IMAGE_NOTES.values())
    kept = []
    for line in str(text).split("\n"):
        if line.strip() in notes or (path and path in line and line.lstrip().startswith("- Screenshot:")):
            continue
        kept.append(line)
    out = "\n".join(kept)
    if path:
        out = out.replace(path, "[screenshot not sent]")
    if "- Screenshot:" not in out:
        out = out.rstrip("\n") + "\n- Screenshot: not sent (text only)"
    return out


def target(agent, cwd, has_image=True, auto=False, as_argument=False):
    """Who gets it and where, for the 'Sending to' line, plus note codes for the panel."""
    notes = []
    name, problem = (agent, "") if agent else agents.default_agent()
    if problem or not name:
        return {"ok": False, "problem": problem or "empty", "notes": ["no_default_agent"]}
    ad = agents.adapter_for(name)
    cwd = ctxmod.launch_dir(cwd)
    if not ad["known"]:
        notes.append("generic_agent")
    elif ad["how"] == "arg":
        notes.append("prompt_visible" if as_argument else "paste_prompt")
    else:
        notes.append("clipboard_paste" if ad["how"] == "clipboard" else "stdin_prompt")
    if has_image and agents.image_mode(name) == "path":
        notes.append("image_path_only")
    if auto and agents.has_auto(name):
        notes.append("auto_mode")
    if not agents.installed(name):
        notes.append("agent_not_installed")
    return {"ok": True, "agent": name, "display": ad["display"], "known": ad["known"], "how": ad["how"],
            "cwd": cwd, "cwd_display": ctxmod.tilde(cwd), "image_mode": agents.image_mode(name),
            "installed": agents.installed(name), "notes": notes}


def compose(question, ctx, shot, mode, agent=None, allow=(), ocr_text="", send_image=True,
            context_text=None, write_file=False, source=None, ocr_missing=False, questions=None, auto=False, as_argument=False,
            ocr_secret_kinds=None):
    """Returns the preview record. `context_text` replaces the generated block (the user edited it)."""
    has_image = bool(shot) and send_image
    tgt = target(agent, (ctx or {}).get("cwd"), has_image, auto, as_argument)
    image_mode = tgt.get("image_mode", "path")
    given = (question or "").strip()
    override = (questions or {}).get(mode)
    default_source = "user" if given else ("config" if isinstance(override, str) and override.strip() else "builtin")
    question = given or default_question(mode, questions)
    block = context_text if context_text is not None else context_block(
        ctx, shot, mode, image_mode, ocr_text, send_image, source)
    if shot and not send_image and context_text is not None:
        block = strip_image_refs(block, shot)
    saved = [k for k in (ocr_secret_kinds or []) if isinstance(k, str)]
    image_secrets = (ocr_kinds(ocr_text) or saved) if shot else []

    qm = maskmod.mask(question, allow)
    kept_question = maskmod.mask(question)["text"]  # what history stores: masked whatever was undone for sending
    cm = maskmod.mask(block, allow, start=len(qm["findings"]) + 1)
    findings = qm["findings"] + cm["findings"]
    masked_count = sum(1 for f in findings if f["masked"])
    header = "---\nContext captured by Omarchy Snap to Agent."
    if masked_count:
        header += " %d likely secret(s) were replaced by [MASKED:...] placeholders." % masked_count
    prompt = "%s\n\n%s\n\n%s" % (qm["text"], header, cm["text"])

    notes = list(tgt.get("notes", []))
    if shot and image_secrets and send_image:
        notes.append("image_has_secrets")
    if shot and not send_image:
        notes.append("image_not_sent")
    if shot and ocr_missing:
        notes.append("ocr_missing")
    result = {"ok": tgt.get("ok", False), "target": tgt, "question": qm["text"], "history_question": kept_question, "context": cm["text"],
              "image_secrets": image_secrets, "has_image": bool(shot), "default_source": default_source,
              "prompt": prompt, "full_prompt": prompt, "oversize": len(prompt) > INLINE_LIMIT, "file": "", "notes": notes,
              # Originals stay here; the panel only gets what it needs to show and undo.
              "findings": [{"id": f["id"], "kind": f["kind"], "masked": f["masked"], "placeholder": f["placeholder"]}
                           for f in findings]}
    if result["oversize"]:
        result["notes"].append("context_in_file")
        base = os.path.splitext((shot or {}).get("path") or "")[0]
        # A file that holds values the user chose to send unmasked is short-lived (see history.cleanup).
        unmasked = any(not f["masked"] for f in findings)
        path = (base + (history.OPEN_SUFFIX if unmasked else "-context.md")) if base else ""
        short = "%s\n\nThe full context is in this file, read it first:\n%s" % (qm["text"], path)
        if write_file and path:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(prompt)
            result["file"] = path
            result["prompt"] = short
        elif path:
            result["prompt"] = short
    return result
