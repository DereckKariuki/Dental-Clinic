"""Inbound WhatsApp webhook.

Scope (project rule): the agent runtime is Make/n8n plus the LLM. This webhook
only does the things that must not be left to a no-code scenario —

  * verify the provider signature before anything else touches the payload;
  * detect emergency keywords and emit the spec §7 first message, which must be
    exact and must not depend on a model deciding to send it;
  * forward the conversation on, and hold nothing.

Nothing here writes patient data to disk. There is no database, no cache and no
message body in any log line — see `redaction.py` and spec §8.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping
from urllib.parse import urlencode

from .knowledge import Clinic
from .redaction import redact_mapping

log = logging.getLogger(__name__)

# Spec §7: the first message of every conversation with emergency keywords.
EMERGENCY_TEMPLATE = (
    "If this is urgent, please call us on {number} now, or go to casualty "
    "at {hospital}. I'll also flag this for the team."
)

# English, Swahili and the common Sheng spellings. Deliberately broad: a false
# positive costs one extra safety message, a false negative costs a patient.
EMERGENCY_KEYWORDS: tuple[str, ...] = (
    "emergency", "urgent", "swelling", "swollen", "bleeding", "blood",
    "knocked out", "knocked-out", "broken tooth", "cracked tooth", "abscess",
    "pus", "can't breathe", "cant breathe", "can't swallow", "cant swallow",
    "trouble breathing", "severe pain", "unbearable", "accident", "trauma",
    "fever", "face is swollen",
    # Swahili / Sheng
    "dharura", "kuvimba", "imevimba", "damu", "inatoka damu", "maumivu makali",
    "inauma sana", "imevunjika", "sitaki kupumua", "usaha",
)

_KEYWORD_RE = re.compile(
    "|".join(rf"\b{re.escape(k)}\b" if k[-1].isalnum() else re.escape(k)
             for k in EMERGENCY_KEYWORDS),
    re.I,
)


class SignatureError(ValueError):
    """The request did not carry a valid provider signature."""


# --------------------------------------------------------------------------
# signature verification
# --------------------------------------------------------------------------


def verify_meta_signature(raw_body: bytes, header: str | None, app_secret: str) -> None:
    """Meta / 360dialog: X-Hub-Signature-256, HMAC-SHA256 over the raw body."""
    if not header or not header.startswith("sha256="):
        raise SignatureError("missing or malformed X-Hub-Signature-256")
    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, header[len("sha256="):]):
        raise SignatureError("signature mismatch")


def verify_twilio_signature(
    url: str, params: Mapping[str, str], header: str | None, auth_token: str
) -> None:
    """Twilio: X-Twilio-Signature, HMAC-SHA1 over the URL plus sorted params."""
    if not header:
        raise SignatureError("missing X-Twilio-Signature")
    payload = url + "".join(f"{k}{params[k]}" for k in sorted(params))
    digest = hmac.new(auth_token.encode(), payload.encode("utf-8"), hashlib.sha1).digest()
    if not hmac.compare_digest(base64.b64encode(digest).decode(), header):
        raise SignatureError("signature mismatch")


def verify_challenge(params: Mapping[str, str], verify_token: str) -> str:
    """Meta's GET subscription handshake. Returns the challenge to echo back."""
    if params.get("hub.mode") != "subscribe":
        raise SignatureError("unexpected hub.mode")
    if not hmac.compare_digest(params.get("hub.verify_token", ""), verify_token):
        raise SignatureError("verify_token mismatch")
    return params.get("hub.challenge", "")


# --------------------------------------------------------------------------
# inbound handling
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class InboundMessage:
    """One inbound WhatsApp message. Held in memory for the life of a request."""

    conversation_id: str
    sender: str
    text: str
    is_first_message: bool = True

    @property
    def sender_ref(self) -> str:
        """A stable, non-reversing reference for logs and metrics."""
        return "wa_" + hashlib.sha256(self.sender.encode()).hexdigest()[:12]


@dataclass
class Action:
    """What the caller should do next. No side effects are taken here."""

    reply_text: str | None = None
    sms_alerts: list[tuple[str, str]] = field(default_factory=list)
    forward_to_agent: bool = True
    tags: list[str] = field(default_factory=list)


def is_emergency(text: str) -> bool:
    return bool(_KEYWORD_RE.search(text or ""))


def emergency_message(clinic: Clinic) -> str:
    number = clinic.get("clinic.phone_primary")
    hospital = clinic.get("emergency.casualty.name")
    if not number or not hospital:
        # Validation should have caught this long before a patient did.
        raise ValueError(
            f"{clinic.clinic_id}: KNOWLEDGE lacks clinic.phone_primary or "
            "emergency.casualty.name; the spec §7 emergency message cannot be sent"
        )
    return EMERGENCY_TEMPLATE.format(number=number, hospital=hospital)


def handle_inbound(message: InboundMessage, clinic: Clinic) -> Action:
    """Decide what happens to one inbound message.

    Spec §7: WhatsApp carries no emergency transfer. On emergency keywords we
    send the safety message ourselves and alert the practice manager by SMS,
    rather than trusting the model to do it.
    """
    action = Action()
    if is_emergency(message.text):
        action.tags.append("EMERGENCY_KEYWORD")
        if message.is_first_message:
            action.reply_text = emergency_message(clinic)
        manager = clinic.get("emergency.practice_manager_sms")
        if manager:
            action.sms_alerts.append(
                (
                    manager,
                    "Possible dental emergency on WhatsApp. Open the conversation "
                    f"in the console: {message.conversation_id}",
                )
            )
        else:
            log.error(
                "clinic %s has no emergency.practice_manager_sms; nobody was alerted",
                clinic.clinic_id,
            )
    # Everything else is the agent's job, on the platform.
    log.info(
        "inbound conversation=%s sender=%s tags=%s",
        message.conversation_id,
        message.sender_ref,
        action.tags or "-",
    )
    return action


# --------------------------------------------------------------------------
# payload parsing
# --------------------------------------------------------------------------


def parse_meta_payload(body: Mapping[str, Any]) -> list[InboundMessage]:
    """Pull messages out of a Meta Cloud API / 360dialog webhook body."""
    out: list[InboundMessage] = []
    for entry in body.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            value = change.get("value") or {}
            for msg in value.get("messages", []) or []:
                text = (msg.get("text") or {}).get("body", "")
                sender = msg.get("from", "")
                out.append(
                    InboundMessage(
                        conversation_id=msg.get("id", ""),
                        sender=sender,
                        text=text,
                        # Meta does not tell us; the platform holds conversation
                        # state, so callers that know better should override.
                        is_first_message=True,
                    )
                )
    return out


def parse_twilio_payload(params: Mapping[str, str]) -> list[InboundMessage]:
    if not params.get("Body") and not params.get("From"):
        return []
    return [
        InboundMessage(
            conversation_id=params.get("MessageSid", ""),
            sender=params.get("From", "").removeprefix("whatsapp:"),
            text=params.get("Body", ""),
        )
    ]


# --------------------------------------------------------------------------
# WSGI app
# --------------------------------------------------------------------------


def make_app(
    clinic: Clinic,
    app_secret: str,
    verify_token: str,
    forward: Callable[[InboundMessage, Action], None] | None = None,
) -> Callable[[dict, Callable], list[bytes]]:
    """A minimal WSGI app for the Meta / 360dialog webhook.

    `forward` is where the message goes next — the Make or n8n hook. It is
    called with the message and the decided action; it must not persist
    anything locally.
    """

    def app(environ: dict, start_response: Callable) -> list[bytes]:
        def respond(status: str, body: bytes = b"", ctype: str = "text/plain") -> list[bytes]:
            start_response(status, [("Content-Type", ctype), ("Content-Length", str(len(body)))])
            return [body]

        method = environ.get("REQUEST_METHOD", "GET")
        if method == "GET":
            from urllib.parse import parse_qsl

            params = dict(parse_qsl(environ.get("QUERY_STRING", "")))
            try:
                challenge = verify_challenge(params, verify_token)
            except SignatureError as exc:
                log.warning("webhook handshake rejected: %s", exc)
                return respond("403 Forbidden")
            return respond("200 OK", challenge.encode())

        if method != "POST":
            return respond("405 Method Not Allowed")

        try:
            length = int(environ.get("CONTENT_LENGTH") or 0)
        except ValueError:
            length = 0
        raw = environ["wsgi.input"].read(length) if length else b""

        try:
            verify_meta_signature(raw, environ.get("HTTP_X_HUB_SIGNATURE_256"), app_secret)
        except SignatureError as exc:
            log.warning("webhook signature rejected: %s", exc)
            return respond("403 Forbidden")

        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            log.warning("webhook body was not JSON")
            return respond("400 Bad Request")

        for message in parse_meta_payload(body):
            action = handle_inbound(message, clinic)
            if forward is not None:
                forward(message, action)

        # 200 fast; the platform retries on anything else.
        return respond("200 OK")

    return app


def safe_debug_payload(body: Mapping[str, Any]) -> str:
    """The only representation of a payload that may be logged or filed."""
    return json.dumps(redact_mapping(dict(body)), sort_keys=True)


__all__ = [
    "EMERGENCY_TEMPLATE", "EMERGENCY_KEYWORDS", "SignatureError", "InboundMessage",
    "Action", "handle_inbound", "is_emergency", "emergency_message",
    "parse_meta_payload", "parse_twilio_payload", "verify_meta_signature",
    "verify_twilio_signature", "verify_challenge", "make_app", "safe_debug_payload",
]
