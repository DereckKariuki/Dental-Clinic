"""Webhook behaviour: signatures, and the spec §7 emergency path."""

import base64
import hashlib
import hmac
import io
import json

import pytest

from dentaldesk import webhook
from dentaldesk.webhook import (
    InboundMessage, SignatureError, emergency_message, handle_inbound, is_emergency,
    make_app, parse_meta_payload, parse_twilio_payload, verify_challenge,
    verify_meta_signature, verify_twilio_signature,
)

SECRET = "app-secret"


# -- signatures ---------------------------------------------------------------


def _sign(body: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_valid_meta_signature_is_accepted():
    body = b'{"entry":[]}'
    verify_meta_signature(body, _sign(body), SECRET)


@pytest.mark.parametrize(
    "header",
    [None, "", "deadbeef", "sha256=deadbeef", "sha1=" + "0" * 40],
)
def test_bad_meta_signature_is_rejected(header):
    with pytest.raises(SignatureError):
        verify_meta_signature(b'{"entry":[]}', header, SECRET)


def test_tampered_body_is_rejected():
    signature = _sign(b'{"entry":[]}')
    with pytest.raises(SignatureError):
        verify_meta_signature(b'{"entry":[{"evil":1}]}', signature, SECRET)


def test_twilio_signature_round_trip():
    url = "https://hooks.example.com/wa"
    params = {"Body": "hello", "From": "whatsapp:+254712345678", "MessageSid": "SM1"}
    payload = url + "".join(f"{k}{params[k]}" for k in sorted(params))
    sig = base64.b64encode(
        hmac.new(b"token", payload.encode(), hashlib.sha1).digest()
    ).decode()
    verify_twilio_signature(url, params, sig, "token")
    with pytest.raises(SignatureError):
        verify_twilio_signature(url, params, sig, "wrong-token")


def test_challenge_handshake():
    params = {"hub.mode": "subscribe", "hub.verify_token": "tok", "hub.challenge": "12345"}
    assert verify_challenge(params, "tok") == "12345"
    with pytest.raises(SignatureError):
        verify_challenge(params, "other")
    with pytest.raises(SignatureError):
        verify_challenge({"hub.mode": "unsubscribe"}, "tok")


# -- emergency detection ------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "my face is swollen",
        "There is bleeding that won't stop",
        "I can't swallow properly",
        "tooth knocked out in an accident",
        "Niko na maumivu makali",
        "meno yangu imevunjika",
        "kuna damu mdomoni",
        "URGENT please help",
    ],
)
def test_emergency_keywords_are_caught(text):
    assert is_emergency(text)


@pytest.mark.parametrize(
    "text",
    [
        "Hi, do you do implants? How much roughly?",
        "What time do you open on Saturday?",
        "Cleaning ni ngapi?",
        "Can I book a check-up next week?",
    ],
)
def test_ordinary_enquiries_are_not_emergencies(text):
    assert not is_emergency(text)


def test_emergency_message_matches_the_spec_wording(clinic):
    msg = emergency_message(clinic)
    assert msg == (
        "If this is urgent, please call us on +254700000000 now, or go to "
        "casualty at MP Shah Hospital. I'll also flag this for the team."
    )
    # Spec §6: use "casualty", never "A&E" or "ER".
    assert "casualty" in msg
    assert "A&E" not in msg and " ER " not in msg


def test_emergency_names_the_hospital_from_knowledge_only(clinic):
    assert clinic.get("emergency.casualty.name") in emergency_message(clinic)


def test_emergency_triggers_reply_and_manager_sms(clinic):
    action = handle_inbound(InboundMessage("c1", "+254700111222", "my jaw is swollen"), clinic)
    assert action.reply_text == emergency_message(clinic)
    assert action.tags == ["EMERGENCY_KEYWORD"]
    assert action.sms_alerts and action.sms_alerts[0][0] == clinic.get(
        "emergency.practice_manager_sms"
    )
    assert action.forward_to_agent


def test_emergency_message_is_only_the_first_message(clinic):
    """Spec §7: the *first* message of the conversation, not every message."""
    action = handle_inbound(
        InboundMessage("c1", "+254700111222", "still swollen", is_first_message=False), clinic
    )
    assert action.reply_text is None
    assert "EMERGENCY_KEYWORD" in action.tags
    assert action.sms_alerts, "the team must still be alerted"


def test_ordinary_message_gets_no_canned_reply(clinic):
    action = handle_inbound(InboundMessage("c2", "+254700111222", "do you open Saturday?"), clinic)
    assert action.reply_text is None
    assert action.tags == []
    assert action.forward_to_agent


def test_missing_casualty_in_knowledge_raises_rather_than_improvising(clinic):
    import copy

    from dentaldesk.knowledge import Clinic

    raw = copy.deepcopy(clinic.raw)
    del raw["emergency"]["casualty"]["name"]
    broken = Clinic(clinic_id="broken", raw=raw, prices=clinic.prices)
    with pytest.raises(ValueError, match="emergency.casualty.name"):
        emergency_message(broken)


# -- payload parsing ----------------------------------------------------------


def test_parse_meta_payload():
    body = {"entry": [{"changes": [{"value": {"messages": [
        {"id": "wamid.1", "from": "254712345678", "text": {"body": "hi"}}
    ]}}]}]}
    messages = parse_meta_payload(body)
    assert len(messages) == 1
    assert messages[0].conversation_id == "wamid.1"
    assert messages[0].text == "hi"


def test_parse_meta_payload_tolerates_status_only_callbacks():
    assert parse_meta_payload({"entry": [{"changes": [{"value": {"statuses": [{}]}}]}]}) == []
    assert parse_meta_payload({}) == []


def test_parse_twilio_payload_strips_the_whatsapp_prefix():
    msgs = parse_twilio_payload(
        {"MessageSid": "SM1", "From": "whatsapp:+254712345678", "Body": "hi"}
    )
    assert msgs[0].sender == "+254712345678"


# -- WSGI app -----------------------------------------------------------------


def _request(app, method="POST", body=b"", signature=None, query=""):
    status = {}

    def start_response(code, headers):
        status["code"] = code
        status["headers"] = headers

    environ = {
        "REQUEST_METHOD": method,
        "QUERY_STRING": query,
        "CONTENT_LENGTH": str(len(body)),
        "wsgi.input": io.BytesIO(body),
    }
    if signature is not None:
        environ["HTTP_X_HUB_SIGNATURE_256"] = signature
    out = app(environ, start_response)
    return status["code"], b"".join(out)


def test_app_rejects_unsigned_posts(clinic):
    seen = []
    app = make_app(clinic, SECRET, "tok", forward=lambda m, a: seen.append(m))
    code, _ = _request(app, body=b'{"entry":[]}')
    assert code.startswith("403")
    assert not seen


def test_app_forwards_signed_messages(clinic):
    seen = []
    app = make_app(clinic, SECRET, "tok", forward=lambda m, a: seen.append((m, a)))
    body = json.dumps({"entry": [{"changes": [{"value": {"messages": [
        {"id": "wamid.2", "from": "254712345678", "text": {"body": "my gum is bleeding"}}
    ]}}]}]}).encode()
    code, _ = _request(app, body=body, signature=_sign(body))
    assert code.startswith("200")
    assert len(seen) == 1
    message, action = seen[0]
    assert action.reply_text == emergency_message(clinic)


def test_app_answers_the_verification_handshake(clinic):
    app = make_app(clinic, SECRET, "tok")
    code, body = _request(
        app, method="GET",
        query="hub.mode=subscribe&hub.verify_token=tok&hub.challenge=99",
    )
    assert code.startswith("200")
    assert body == b"99"


def test_app_rejects_a_bad_verify_token(clinic):
    app = make_app(clinic, SECRET, "tok")
    code, _ = _request(
        app, method="GET",
        query="hub.mode=subscribe&hub.verify_token=nope&hub.challenge=99",
    )
    assert code.startswith("403")


def test_app_rejects_malformed_json_after_a_valid_signature(clinic):
    app = make_app(clinic, SECRET, "tok")
    body = b"not json"
    code, _ = _request(app, body=body, signature=_sign(body))
    assert code.startswith("400")
