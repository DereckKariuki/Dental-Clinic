"""Scrub patient data before anything is logged.

Project rule: never write patient data to a local file or log. Under the Data
Protection Act 2019 the clinic is the controller and we are the processor
(spec §8), so patient content stays on the platform we process it on — it does
not leak into our own logs, error reports, or a personal Google Sheet.

Use `install_log_redaction()` once at process start, and `redact()` anywhere a
string is about to cross into something durable.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Iterable

# Kenyan mobile numbers: +254 7xx/1xx, 07xx/01xx, and the bare 254 form.
_PHONE = re.compile(r"(?:\+?254|0)\s?(?:7|1)\d{2}[\s-]?\d{3}[\s-]?\d{3}\b")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
# M-Pesa transaction codes: 10 alphanumerics, e.g. QGH7X2K9LM.
_MPESA_CODE = re.compile(r"\b[A-Z]{3}[A-Z0-9]{7}\b")
# Kenyan national ID / passport-ish runs of digits.
_ID_NUMBER = re.compile(r"\b\d{7,9}\b")
_DOB = re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b")

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (_EMAIL, "[email]"),
    (_PHONE, "[phone]"),
    (_MPESA_CODE, "[mpesa-code]"),
    (_DOB, "[date]"),
    (_ID_NUMBER, "[id]"),
)

# Keys whose values are patient content and are never logged, at any depth.
SENSITIVE_KEYS = frozenset(
    {
        "body", "text", "message", "messages", "transcript", "transcripts",
        "recording_url", "audio", "content", "caption", "name", "profile_name",
        "patient_name", "from", "to", "wa_id", "author", "phone", "msisdn",
        "reason_for_visit", "symptoms", "notes", "note", "insurer_member_no",
    }
)


def redact(text: str | None) -> str:
    """Replace direct identifiers in a free-text string."""
    if not text:
        return ""
    out = text
    for pattern, replacement in _PATTERNS:
        out = pattern.sub(replacement, out)
    return out


def redact_mapping(data: Any, *, _depth: int = 0) -> Any:
    """Recursively drop sensitive keys and scrub what is left.

    Whole values are dropped rather than redacted for keys we know carry patient
    content — redacting free text is best-effort, and best-effort is not a basis
    for writing someone's symptoms to disk.
    """
    if _depth > 12:
        return "[truncated]"
    if isinstance(data, dict):
        out = {}
        for key, value in data.items():
            if str(key).lower() in SENSITIVE_KEYS:
                out[key] = "[redacted]"
            else:
                out[key] = redact_mapping(value, _depth=_depth + 1)
        return out
    if isinstance(data, (list, tuple)):
        return [redact_mapping(v, _depth=_depth + 1) for v in data]
    if isinstance(data, str):
        return redact(data)
    return data


class RedactingFilter(logging.Filter):
    """Last line of defence: scrub anything that reaches a log handler."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = redact_mapping(record.args)
            else:
                record.args = tuple(
                    redact(a) if isinstance(a, str) else a for a in record.args
                )
        return True


def install_log_redaction(loggers: Iterable[str] = ("",)) -> None:
    """Attach the redacting filter to the named loggers and their handlers."""
    for name in loggers:
        logger = logging.getLogger(name)
        filt = RedactingFilter()
        logger.addFilter(filt)
        for handler in logger.handlers:
            handler.addFilter(filt)
