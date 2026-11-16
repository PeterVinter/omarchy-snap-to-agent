"""Text from screenshots with tesseract, and a check for secrets shown in the image."""
import runner as _runner
import mask as _mask

MAX_TEXT = 20_000


def read_text(path, run=_runner.run):
    """Returns {ok, text, missing}. Never raises: without tesseract the plugin still works."""
    code, out, err = run(["tesseract", path, "-", "--psm", "6"], timeout=30)
    if code == 127:
        return {"ok": False, "text": "", "missing": True, "package": "tesseract"}
    if code != 0:
        return {"ok": False, "text": "", "missing": False, "error": (err or "").strip()[:200]}
    text = "\n".join(line.rstrip() for line in out.splitlines()).strip()
    return {"ok": True, "text": text[:MAX_TEXT], "missing": False}


def secret_kinds(text):
    """The kinds of secrets visible in OCR text, e.g. ["github-token"]. [] when none."""
    seen = []
    for f in _mask.mask(text)["findings"]:
        if f["kind"] not in seen:
            seen.append(f["kind"])
    return seen
