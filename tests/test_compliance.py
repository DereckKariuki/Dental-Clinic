"""Data-protection rules (spec §8) and the project's own hard rule:
never write patient data to a local file or log.
"""

import logging
from datetime import datetime, timedelta, timezone

import pytest

from dentaldesk import redaction, retention, webhook
from dentaldesk.retention import RETENTION_DAYS, Record, due_for_deletion, purge

NOW = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)


# -- redaction ---------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Call me on 0712 345 678",
        "My number is +254712345678",
        "reach me at 254712345678",
        "0112345678 is my line",
    ],
)
def test_kenyan_mobile_numbers_are_redacted(text):
    assert "[phone]" in redaction.redact(text)
    assert "345678" not in redaction.redact(text)


def test_email_mpesa_and_id_are_redacted():
    out = redaction.redact("jane@example.co.ke paid QGH7X2K9LM, ID 23456789")
    assert "[email]" in out and "[mpesa-code]" in out and "[id]" in out
    assert "jane@example.co.ke" not in out


def test_patient_content_keys_are_dropped_not_merely_scrubbed():
    payload = {
        "from": "+254712345678",
        "text": {"body": "my molar is abscessed and I am scared"},
        "meta": {"notes": "patient has diabetes"},
        "conversation_id": "conv-1",
    }
    safe = redaction.redact_mapping(payload)
    assert safe["from"] == "[redacted]"
    # `text` is itself a sensitive key, so the whole subtree goes, body included.
    assert safe["text"] == "[redacted]"
    assert safe["meta"]["notes"] == "[redacted]"
    assert safe["conversation_id"] == "conv-1"
    assert "abscessed" not in str(safe)
    assert "diabetes" not in str(safe)


def test_sensitive_keys_are_dropped_at_any_depth():
    payload = {"a": {"b": {"c": {"transcript": "he said his gum is bleeding"}}}}
    safe = redaction.redact_mapping(payload)
    assert safe["a"]["b"]["c"]["transcript"] == "[redacted]"
    assert "bleeding" not in str(safe)


def test_deep_nesting_is_truncated_rather_than_recursing_forever():
    node = {"leaf": "0712345678"}
    for _ in range(20):
        node = {"child": node}
    assert "0712345678" not in str(redaction.redact_mapping(node))


def test_log_filter_scrubs_records(caplog):
    logger = logging.getLogger("dentaldesk.test.redaction")
    logger.addFilter(redaction.RedactingFilter())
    with caplog.at_level(logging.INFO, logger=logger.name):
        logger.info("patient called from 0712345678")
    assert "0712345678" not in caplog.text
    assert "[phone]" in caplog.text


def test_safe_debug_payload_never_carries_the_message_body():
    body = {"entry": [{"changes": [{"value": {"messages": [
        {"id": "m1", "from": "+254712345678", "text": {"body": "tooth broke"}}
    ]}}]}]}
    out = webhook.safe_debug_payload(body)
    assert "tooth broke" not in out
    assert "+254712345678" not in out


def test_webhook_logs_a_hashed_sender_not_the_number(caplog, clinic):
    msg = webhook.InboundMessage("conv-9", "+254712345678", "just booking a cleaning")
    with caplog.at_level(logging.INFO, logger="dentaldesk.webhook"):
        webhook.handle_inbound(msg, clinic)
    assert "+254712345678" not in caplog.text
    assert "712345678" not in caplog.text
    assert msg.sender_ref in caplog.text
    assert "cleaning" not in caplog.text


def test_sender_ref_is_stable_and_not_reversible():
    a = webhook.InboundMessage("c", "+254712345678", "x").sender_ref
    b = webhook.InboundMessage("d", "+254712345678", "y").sender_ref
    assert a == b
    assert "712345678" not in a


# -- retention ---------------------------------------------------------------


class FakeStore:
    name = "fake-platform"

    def __init__(self, records, failing=()):
        self._records = list(records)
        self._failing = set(failing)
        self.deleted = []

    def list_records(self):
        return list(self._records)

    def delete_record(self, record_id):
        if record_id in self._failing:
            raise RuntimeError("platform said no")
        self.deleted.append(record_id)


def _rec(rid, days_old, kind="transcript"):
    return Record(id=rid, created_at=NOW - timedelta(days=days_old), kind=kind)


def test_retention_window_is_thirty_days():
    assert RETENTION_DAYS == 30


def test_records_older_than_thirty_days_are_due():
    records = [_rec("old", 31), _rec("edge", 30), _rec("fresh", 29)]
    due = {r.id for r in due_for_deletion(records, NOW)}
    assert due == {"old", "edge"}


def test_purge_deletes_only_what_is_due():
    store = FakeStore([_rec("old", 45), _rec("fresh", 2), _rec("recording", 60, "recording")])
    report = purge(store, NOW)
    assert set(store.deleted) == {"old", "recording"}
    assert report.examined == 3
    assert report.ok


def test_dry_run_deletes_nothing():
    store = FakeStore([_rec("old", 45)])
    report = purge(store, NOW, dry_run=True)
    assert store.deleted == []
    assert report.deleted == ("old",)


def test_one_failure_does_not_stop_the_purge():
    store = FakeStore([_rec("a", 40), _rec("b", 40), _rec("c", 40)], failing={"b"})
    report = purge(store, NOW)
    assert set(store.deleted) == {"a", "c"}
    assert not report.ok
    assert report.failed[0][0] == "b"


def test_purge_report_carries_ids_and_counts_only(caplog):
    store = FakeStore([_rec("old", 45)])
    with caplog.at_level(logging.INFO, logger="dentaldesk.retention"):
        report = purge(store, NOW)
    assert "examined 1" in str(report)
    assert "transcript" not in caplog.text.replace("dentaldesk.retention", "")
