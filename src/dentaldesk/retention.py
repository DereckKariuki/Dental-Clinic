"""30-day retention, then delete (spec §8).

Call recordings and transcripts live on the voice / WhatsApp platform. This
module is the driver that walks a platform's records and deletes anything past
the retention window. It never copies record content locally — it works from
ids and timestamps, and its audit trail carries counts and ids only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Protocol

RETENTION_DAYS = 30

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Record:
    """A retained artefact on a platform. Ids and times only — never content."""

    id: str
    created_at: datetime
    kind: str = "transcript"  # transcript | recording

    def age_days(self, now: datetime) -> float:
        return (now - self.created_at).total_seconds() / 86400.0


class RecordStore(Protocol):
    """The slice of a platform API this needs. Implement per platform."""

    name: str

    def list_records(self) -> Iterable[Record]: ...

    def delete_record(self, record_id: str) -> None: ...


@dataclass(frozen=True)
class PurgeReport:
    store: str
    examined: int
    deleted: tuple[str, ...]
    failed: tuple[tuple[str, str], ...]
    dry_run: bool

    @property
    def ok(self) -> bool:
        return not self.failed

    def __str__(self) -> str:
        verb = "would delete" if self.dry_run else "deleted"
        line = f"{self.store}: examined {self.examined}, {verb} {len(self.deleted)}"
        if self.failed:
            line += f", FAILED {len(self.failed)}"
        return line


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def cutoff(now: datetime | None = None, days: int = RETENTION_DAYS) -> datetime:
    return (now or _utcnow()) - timedelta(days=days)


def due_for_deletion(
    records: Iterable[Record], now: datetime | None = None, days: int = RETENTION_DAYS
) -> list[Record]:
    """Records at or past the retention window.

    A record exactly `days` old is due: the window is "keep for 30 days", not
    "keep for 30 days and a bit".
    """
    limit = cutoff(now, days)
    return [r for r in records if r.created_at <= limit]


def purge(
    store: RecordStore,
    now: datetime | None = None,
    days: int = RETENTION_DAYS,
    dry_run: bool = False,
) -> PurgeReport:
    records = list(store.list_records())
    due = due_for_deletion(records, now, days)
    deleted: list[str] = []
    failed: list[tuple[str, str]] = []
    for record in due:
        if dry_run:
            deleted.append(record.id)
            continue
        try:
            store.delete_record(record.id)
        except Exception as exc:  # noqa: BLE001 - one bad record must not stop the purge
            failed.append((record.id, f"{type(exc).__name__}: {exc}"))
            log.error("retention: failed to delete %s from %s", record.id, store.name)
        else:
            deleted.append(record.id)
    report = PurgeReport(
        store=store.name,
        examined=len(records),
        deleted=tuple(deleted),
        failed=tuple(failed),
        dry_run=dry_run,
    )
    # Ids and counts only. Never record content.
    log.info("retention: %s", report)
    return report
