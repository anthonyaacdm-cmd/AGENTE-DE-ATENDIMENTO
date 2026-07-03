import re

PII_PATTERNS = [
    r'\b\d{3}\.\d{3}\.\d{3}-\d{2}\b',
    r'\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b',
    r'\b\d{11}\b',
    r'\b\d{4}-\d{4}-\d{4}-\d{4}\b',
    r'\b\d{4}\s\d{4}\s\d{4}\s\d{4}\b',
    r'\b\d{16}\b',
]


def strip_pii(text: str) -> str:
    for pattern in PII_PATTERNS:
        text = re.sub(pattern, "[REDACTED]", text)
    return text
