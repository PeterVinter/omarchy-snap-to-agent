"""Masks likely secrets in text before it is shown or sent.

Pure functions, standard library only. Every secret is replaced by a numbered
placeholder such as [MASKED:github-token:2]. mask() returns the originals too,
so the panel can undo one masking; the originals are never written to disk.
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


def mask(text):
    """Returns {"text": masked text, "findings": [{id, kind, original, placeholder}]}."""
    text = str(text or "")
    spans = []  # (start, end, kind)
    for kind, rx, group in _RULES:
        for m in rx.finditer(text):
            start, end = m.span(group)
            if start == end or _PLACEHOLDER_RE.fullmatch(text[start:end]):
                continue
            spans.append((start, end, kind))
    # Longest first, so a private key block beats lines inside it; drop overlaps.
    spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))
    kept = []
    last_end = -1
    for start, end, kind in spans:
        if start >= last_end:
            kept.append((start, end, kind))
            last_end = end
        elif end > last_end and kept and kept[-1][0] == start:
            kept[-1] = (start, end, kept[-1][2])
            last_end = end
    out = []
    findings = []
    pos = 0
    for i, (start, end, kind) in enumerate(kept, 1):
        out.append(text[pos:start])
        placeholder = PLACEHOLDER % (kind, i)
        out.append(placeholder)
        findings.append({"id": i, "kind": kind, "original": text[start:end], "placeholder": placeholder})
        pos = end
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
