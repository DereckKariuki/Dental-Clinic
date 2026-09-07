"""Score clinics against the spec §3 target list and qualification test.

This is business data — clinic names, public numbers, response times. No
patient data passes through here.

    python -m dentaldesk.prospecting.qualify surveys.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

# Spec §3.
PRIORITY_AREAS: tuple[str, ...] = (
    "westlands", "kilimani", "lavington", "karen", "parklands", "gigiri",
    "runda", "kileleshwa", "upper hill",
    "nyali", "milimani",
    "thika road", "ngong road",
)
HIGH_VALUE_SERVICES = frozenset({"implants", "aligners", "invisalign", "veneers", "full-mouth"})
PRIVATE_INSURERS = frozenset(
    {"jubilee", "britam", "aar", "madison", "cic", "apa", "old mutual"}
)
SKIP_KINDS = frozenset(
    {"government", "mission", "hospital_department", "single_chair_low_income"}
)
MIN_REVIEWS = 25
MIN_RATING = 4.3
MAX_CHAIRS = 4
# Spec §3: "Tier A = no WhatsApp reply within 12 hours and voicemail on both calls."
WHATSAPP_REPLY_WINDOW = timedelta(hours=12)

# Review phrases worth grepping for (spec §3, step 3).
REVIEW_SIGNALS: tuple[str, ...] = ("hawajibu simu", "no one answers", "never replied")


class Tier(str, Enum):
    A = "A"  # fails the WhatsApp test and both calls — spec's definition
    B = "B"  # fails one of the two
    C = "C"  # answers both — no evidence to lead with
    SKIP = "SKIP"  # does not qualify in


class CallResult(str, Enum):
    ANSWERED = "answered"
    VOICEMAIL = "voicemail"
    NO_ANSWER = "no_answer"

    @property
    def is_miss(self) -> bool:
        return self is not CallResult.ANSWERED


@dataclass
class Survey:
    """One clinic, as observed by the spec §3 qualification test."""

    name: str
    area: str = ""
    kind: str = "private"
    chairs: int | None = None
    owner_dentist: str = ""
    rating: float | None = None
    review_count: int | None = None
    services: tuple[str, ...] = ()
    insurers: tuple[str, ...] = ()
    has_whatsapp: bool = False
    runs_ads: bool = False
    advertises_budget_extraction: bool = False
    review_phrases: tuple[str, ...] = ()
    whatsapp_sent_at: datetime | None = None
    whatsapp_replied_at: datetime | None = None
    call_midday: CallResult | None = None
    call_after_close: CallResult | None = None

    @property
    def whatsapp_reply_hours(self) -> float | None:
        if not self.whatsapp_sent_at:
            return None
        if not self.whatsapp_replied_at:
            return None
        return (self.whatsapp_replied_at - self.whatsapp_sent_at).total_seconds() / 3600.0

    @property
    def failed_whatsapp_test(self) -> bool | None:
        """True when no reply arrived inside 12 hours. None if not yet tested."""
        if not self.whatsapp_sent_at:
            return None
        if self.whatsapp_replied_at is None:
            return True
        return self.whatsapp_replied_at - self.whatsapp_sent_at > WHATSAPP_REPLY_WINDOW

    @property
    def both_calls_missed(self) -> bool | None:
        if self.call_midday is None or self.call_after_close is None:
            return None
        return self.call_midday.is_miss and self.call_after_close.is_miss


@dataclass
class Assessment:
    survey: Survey
    tier: Tier
    disqualifiers: list[str] = field(default_factory=list)
    qualifiers: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    @property
    def opening_line(self) -> str | None:
        """Spec §3's opening line, only when the evidence actually supports it."""
        if self.tier is not Tier.A:
            return None
        return (
            "I WhatsApp'd you on Tuesday evening asking about implants. No reply. "
            "I called twice as well — both went to voicemail. Can I show you what "
            "happens to those enquiries instead?"
        )


def _disqualify(s: Survey) -> list[str]:
    out: list[str] = []
    if s.kind in SKIP_KINDS:
        out.append(f"skip list: {s.kind} (spec §3)")
    if s.advertises_budget_extraction:
        out.append("advertises budget extractions — wrong economics")
    if s.chairs is not None and s.chairs > MAX_CHAIRS:
        out.append(f"{s.chairs} chairs, target is 1-{MAX_CHAIRS}")
    if s.review_count is not None and s.review_count < MIN_REVIEWS:
        out.append(f"{s.review_count} reviews, need {MIN_REVIEWS}+")
    if s.rating is not None and s.rating < MIN_RATING:
        out.append(f"rated {s.rating}, need {MIN_RATING}+")
    if not s.has_whatsapp:
        out.append("no WhatsApp number listed — the primary channel is unavailable")
    return out


def _qualify(s: Survey) -> list[str]:
    out: list[str] = []
    area = s.area.strip().lower()
    if any(area == a or a in area for a in PRIORITY_AREAS):
        out.append(f"priority area: {s.area}")
    if s.owner_dentist:
        out.append(f"owner-dentist findable: {s.owner_dentist}")
    services = {x.strip().lower() for x in s.services}
    if services & HIGH_VALUE_SERVICES:
        out.append("offers high-value work: " + ", ".join(sorted(services & HIGH_VALUE_SERVICES)))
    insurers = {x.strip().lower() for x in s.insurers}
    if insurers & PRIVATE_INSURERS:
        out.append("takes private cover: " + ", ".join(sorted(insurers & PRIVATE_INSURERS)))
    if s.runs_ads:
        out.append("already paying for leads")
    hits = [p for p in REVIEW_SIGNALS if any(p in r.lower() for r in s.review_phrases)]
    if hits:
        out.append("reviews mention: " + ", ".join(hits))
    return out


def assess(s: Survey) -> Assessment:
    disqualifiers = _disqualify(s)
    qualifiers = _qualify(s)
    missing: list[str] = []
    if s.failed_whatsapp_test is None:
        missing.append("WhatsApp test not run")
    if s.both_calls_missed is None:
        missing.append("both calls not logged")

    if disqualifiers:
        tier = Tier.SKIP
    elif missing:
        # Spec §3 defines Tier A by evidence. Without the evidence there is no
        # tier — do not guess one, go and run the test.
        tier = Tier.C
    elif s.failed_whatsapp_test and s.both_calls_missed:
        tier = Tier.A
    elif s.failed_whatsapp_test or s.both_calls_missed:
        tier = Tier.B
    else:
        tier = Tier.C
    return Assessment(s, tier, disqualifiers, qualifiers, missing)


def rank(surveys: Iterable[Survey]) -> list[Assessment]:
    order = {Tier.A: 0, Tier.B: 1, Tier.C: 2, Tier.SKIP: 3}
    return sorted(
        (assess(s) for s in surveys),
        key=lambda a: (order[a.tier], -len(a.qualifiers), a.survey.name.lower()),
    )


# --------------------------------------------------------------------------
# CSV I/O
# --------------------------------------------------------------------------

_LIST_FIELDS = {"services", "insurers", "review_phrases"}
_BOOL_FIELDS = {"has_whatsapp", "runs_ads", "advertises_budget_extraction"}
_TIME_FIELDS = {"whatsapp_sent_at", "whatsapp_replied_at"}
_CALL_FIELDS = {"call_midday", "call_after_close"}


def _parse_row(row: dict[str, str]) -> Survey:
    kwargs: dict[str, Any] = {}
    for key, value in row.items():
        key = (key or "").strip()
        value = (value or "").strip()
        if not key or key not in Survey.__annotations__:
            continue
        if not value:
            continue
        if key in _LIST_FIELDS:
            kwargs[key] = tuple(v.strip() for v in value.split("|") if v.strip())
        elif key in _BOOL_FIELDS:
            kwargs[key] = value.lower() in {"1", "true", "yes", "y"}
        elif key in _TIME_FIELDS:
            kwargs[key] = datetime.fromisoformat(value)
        elif key in _CALL_FIELDS:
            kwargs[key] = CallResult(value.lower())
        elif key == "chairs":
            kwargs[key] = int(value)
        elif key == "rating":
            kwargs[key] = float(value)
        elif key == "review_count":
            kwargs[key] = int(value)
        else:
            kwargs[key] = value
    return Survey(**kwargs)


def load_surveys(path: str | Path) -> list[Survey]:
    with Path(path).open(newline="", encoding="utf-8") as fh:
        return [_parse_row(row) for row in csv.DictReader(fh)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Rank surveyed clinics (spec §3).")
    ap.add_argument("csv", help="survey log; see docs/prospecting.md for columns")
    ap.add_argument("--tier", choices=[t.value for t in Tier], help="show one tier only")
    args = ap.parse_args(argv)

    results = rank(load_surveys(args.csv))
    if args.tier:
        results = [a for a in results if a.tier.value == args.tier]

    for a in results:
        hours = a.survey.whatsapp_reply_hours
        wa = "no reply" if a.survey.failed_whatsapp_test and hours is None else (
            f"{hours:.1f}h" if hours is not None else "not tested"
        )
        print(f"[{a.tier.value}] {a.survey.name} — {a.survey.area or 'area unknown'} (WhatsApp: {wa})")
        for reason in a.disqualifiers:
            print(f"      skip: {reason}")
        for reason in a.missing:
            print(f"      todo: {reason}")
        for reason in a.qualifiers:
            print(f"      +    {reason}")
    counts = {t: sum(1 for a in results if a.tier is t) for t in Tier}
    print()
    print("  " + "  ".join(f"{t.value}={counts[t]}" for t in Tier))
    return 0


if __name__ == "__main__":
    sys.exit(main())
