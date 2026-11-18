"""Masks likely secrets in text before it is shown or sent.

Pure functions, standard library only. Every secret is replaced by a numbered
placeholder such as [MASKED:github-token:2]. mask() returns the originals too,
so the panel can undo one masking. The originals live in the panel's memory only: anything that
goes to disk passes through scrub_state() first.
"""
import re

# (kind, compiled pattern, group that holds the secret or 0 for the whole match)
_RULES = [
    ("private-key", re.compile(
        r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|\Z)",
        re.S), 0),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"), 0),
    ("aws-key", re.compile(r"\b(?:AKIA|ASIA|AGPA|AIDA|AROA)[0-9A-Z]{16}\b"), 0),
    ("github-token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b"), 0),
    ("anthropic-key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}"), 0),
    ("openai-key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}"), 0),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"), 0),
    ("google-key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"), 0),
    ("stripe-key", re.compile(r"\b(?:sk|rk)_(?:live|test)_[0-9A-Za-z]{16,}\b"), 0),
    ("bearer-token", re.compile(r"(?i)\bbearer\s+([A-Za-z0-9._~+/=-]{16,})"), 1),
    ("url-credentials", re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s/:@]+:([^\s/@]{3,})@"), 1),
    # .env lines and key=value / key: value assignments with a telling name.
    ("assignment", re.compile(
        r"(?im)\b[A-Z0-9_.-]*(?:password|passwd|secret|token|api[_-]?key|access[_-]?key|private[_-]?key|auth)[A-Z0-9_.-]*"
        r"\s*[:=]\s*[\"']?([^\s\"'#]{6,})"), 1),
]

PLACEHOLDER = "[MASKED:%s:%d]"
_PLACEHOLDER_RE = re.compile(r"\[MASKED:[a-z-]+:\d+\]")


def mask(text, allow=(), start=1):
    """Returns {"text": masked text, "findings": [{id, kind, original, placeholder, masked}]}.

    Ids follow the order of the secrets in the text, counted from `start`, so the same input always gives
    the same ids. Ids in `allow` are left unmasked (the user's undo); they stay in
    the findings list with masked=False.
    """
    allow = set(allow or ())
    first_id = start
    text = str(text or "")
    spans = []  # (begin, end, kind)
    for kind, rx, group in _RULES:
        for m in rx.finditer(text):
            begin, end = m.span(group)
            if begin == end or _PLACEHOLDER_RE.fullmatch(text[begin:end]):
                continue
            spans.append((begin, end, kind))
    # Longest first, so a private key block beats lines inside it; drop overlaps.
    spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))
    kept = []
    last_end = -1
    for begin, end, kind in spans:
        if begin >= last_end:
            kept.append((begin, end, kind))
            last_end = end
        elif end > last_end and kept and kept[-1][0] == begin:
            kept[-1] = (begin, end, kept[-1][2])
            last_end = end
    out = []
    findings = []
    pos = 0
    for i, (a, b, kind) in enumerate(kept, first_id):
        out.append(text[pos:a])
        placeholder = PLACEHOLDER % (kind, i)
        masked = i not in allow
        out.append(placeholder if masked else text[a:b])
        findings.append({"id": i, "kind": kind, "original": text[a:b], "placeholder": placeholder,
                         "masked": masked})
        pos = b
    out.append(text[pos:])
    return {"text": "".join(out), "findings": findings}


def unmask(text, findings, finding_id):
    """Puts one original back (the user's undo)."""
    for f in findings:
        if f["id"] == finding_id:
            return text.replace(f["placeholder"], f["original"], 1)
    return text


def has_secrets(text):
    return bool(mask(text)["findings"])


def _scrub(value):
    if isinstance(value, str):
        return mask(value)["text"]
    if isinstance(value, dict):
        return {k: _scrub(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    return value


def scrub_state(state):
    """A copy of a captured state that is safe to keep on disk: every text in it is masked.

    The OCR record also keeps which kinds of secrets the picture showed (`secret_kinds`), because the
    masked OCR text can no longer tell, and "send again" must still warn about the screenshot.
    """
    out = _scrub(state if isinstance(state, dict) else {})
    ocr = state.get("ocr") if isinstance(state, dict) else None
    if isinstance(ocr, dict) and isinstance(out.get("ocr"), dict):
        kinds = []
        for f in mask(str(ocr.get("text", "")))["findings"]:
            if f["kind"] not in kinds:
                kinds.append(f["kind"])
        out["ocr"]["secret_kinds"] = kinds or [k for k in ocr.get("secret_kinds", []) if isinstance(k, str)]
    return out
