from __future__ import annotations

import re

SECRET_PATTERNS = [
    re.compile(r"(?i)\b(api[_-]?key|password|secret|token|client[_-]?secret|private[_-]?key|access[_-]?token|refresh[_-]?token|oauth[_-]?token)\s*[:=]\s*['\"]?[^\s'\"]{8,}"),
    re.compile(r"(?i)\bAuthorization\s*:\s*(?:Bearer|Basic)\s+[A-Za-z0-9._~+/-]{8,}"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{12,}"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bya29\.[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{16,}\b"),
    re.compile(r"\bAIza[A-Za-z0-9_-]{30,}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
]


def sanitize_text(text: str, *, max_chars: int = 4000) -> str:
    if any(pattern.search(text) for pattern in SECRET_PATTERNS):
        raise ValueError("content appears to contain a secret")
    text = re.sub(r"(?is)<(?:chain-of-thought|thinking)>.*?</(?:chain-of-thought|thinking)>", "[reasoning removed]", text)
    text = re.sub(r"(?im)^\s*(?:chain[- ]of[- ]thought|internal reasoning)\s*:.*$", "[reasoning removed]", text)
    return text.strip()[:max_chars]
