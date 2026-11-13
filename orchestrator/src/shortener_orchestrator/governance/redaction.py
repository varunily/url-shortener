import re

_PATTERNS = [
    (re.compile(r"(?i)(password|token|secret|api[_-]?key)(\s*[=:]\s*)([^\s,;\"']+)"),
     lambda match: match.group(0) if re.fullmatch(r"\$\{[A-Z_][A-Z0-9_]*\}", match.group(3))
     else match.group(1) + match.group(2) + "[REDACTED]"),
    (re.compile(r"(?i)(authorization\s*:\s*bearer\s+)\S+"), r"\1[REDACTED]"),
    (re.compile(r"(https?://)[^/\s:@]+:[^@\s/]+@"), r"\1[REDACTED]@"),
]

def redact(value: str) -> str:
    for pattern, replacement in _PATTERNS:
        value = pattern.sub(replacement, value)
    return value

def sanitize(value):
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, dict):
        return {key: ("[REDACTED]" if re.fullmatch(r"(?i)(password|secret|api_key|access_token)", key)
                      else sanitize(item)) for key, item in value.items()}
    return value
