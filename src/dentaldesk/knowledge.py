"""Load and validate a clinic KNOWLEDGE file.

KNOWLEDGE is the only source the agent may answer facts from (spec §6, FAQ
HANDLING). A clinic that fails validation must not go in front of a patient.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Spec §6 PRICING: "You MAY NOT ... quote implants, ortho, veneers, surgery, or
# anything complex". A price_list entry in one of these categories is forced
# non-quotable regardless of what the file says.
NEVER_QUOTABLE_CATEGORIES = frozenset({"implant", "ortho", "veneers", "surgery", "complex"})

# Spec §6 PAYMENT AND COVER: "If they mention SHA: do not assert what SHA
# covers." SHA may therefore never sit in the accepted-insurer list, which is
# the one list the agent is allowed to confirm from.
FORBIDDEN_INSURERS = frozenset({"sha", "nhif", "shif"})

_REQUIRED_DAYS = (
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
)


class KnowledgeError(ValueError):
    """Raised when a KNOWLEDGE file is not fit to serve patients from."""


@dataclass(frozen=True)
class Price:
    procedure: str
    aliases: tuple[str, ...] = ()
    from_price_kes: int | None = None
    quotable: bool = False
    category: str | None = None
    is_consultation_fee: bool = False

    def matches(self, text: str) -> bool:
        haystack = text.lower()
        for name in (self.procedure, *self.aliases):
            if re.search(rf"\b{re.escape(name.lower())}\b", haystack):
                return True
        return False


@dataclass(frozen=True)
class Clinic:
    clinic_id: str
    raw: dict[str, Any]
    prices: tuple[Price, ...]
    fictional: bool = False
    warnings: tuple[str, ...] = field(default=())

    # -- lookups the checks and the prompt assembler need ------------------

    def price(self, procedure: str) -> Price:
        for p in self.prices:
            if p.procedure.lower() == procedure.lower():
                return p
        raise KeyError(f"{procedure!r} is not in the price list for {self.clinic_id}")

    def find_price(self, text: str) -> Price | None:
        """The price-list entry a free-text mention refers to, longest name first."""
        best: Price | None = None
        best_len = 0
        for p in self.prices:
            for name in (p.procedure, *p.aliases):
                if len(name) > best_len and p.matches(name) and re.search(
                    rf"\b{re.escape(name.lower())}\b", text.lower()
                ):
                    best, best_len = p, len(name)
        return best

    @property
    def consultation_fee(self) -> int | None:
        for p in self.prices:
            if p.is_consultation_fee:
                return p.from_price_kes
        return None

    @property
    def quotable_amounts(self) -> set[int]:
        amounts = {p.from_price_kes for p in self.prices if p.quotable and p.from_price_kes}
        return {a for a in amounts if a is not None}

    @property
    def insurers_accepted(self) -> tuple[str, ...]:
        return tuple(self.raw.get("payment", {}).get("insurers_accepted") or ())

    @property
    def dentist_names(self) -> tuple[str, ...]:
        names = []
        owner = self.raw.get("clinic", {}).get("owner_dentist")
        if owner:
            names.append(owner)
        names.extend(self.raw.get("dentists", []) or [])
        return tuple(names)

    @property
    def facility_names(self) -> tuple[str, ...]:
        """Named outside facilities the agent is permitted to mention."""
        names = [self.raw.get("clinic", {}).get("name", "")]
        casualty = self.raw.get("emergency", {}).get("casualty", {})
        if casualty.get("name"):
            names.append(casualty["name"])
        for item in self.raw.get("services_not_offered", []) or []:
            names.extend(_proper_names(item.get("referral", "")))
        return tuple(n for n in names if n)

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.raw
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def is_unknown(self, key: str) -> bool:
        for item in self.raw.get("unknowns", []) or []:
            if item == key:
                return True
            if isinstance(item, dict) and key in (item.get("insurer"), item.get("field")):
                return True
        return False


_PROPER_NAME = re.compile(
    r"\b((?:[A-Z][\w'-]+ )*[A-Z][\w'-]+ (?:Hospital|Clinic|Centre|Center|Dental|Practice|Unit))\b"
)


def _proper_names(text: str) -> list[str]:
    return [m.group(1) for m in _PROPER_NAME.finditer(text or "")]


def validate(raw: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Return (errors, warnings) for a parsed KNOWLEDGE document."""
    errors: list[str] = []
    warnings: list[str] = []

    def require(dotted: str, why: str) -> Any:
        node: Any = raw
        for part in dotted.split("."):
            if not isinstance(node, dict) or not node.get(part):
                errors.append(f"missing {dotted}: {why}")
                return None
            node = node[part]
        return node

    require("clinic_id", "every clinic needs a stable id")
    require("clinic.name", "used in the agent's opening")
    require("clinic.phone_primary", "[NUMBER] in the WhatsApp emergency message (spec §7)")

    # Spec §6 EMERGENCY: the casualty must be named specifically, with its road,
    # and verified by a human rather than taken from the model's general
    # knowledge of Nairobi hospitals.
    require("emergency.casualty.name", "spec §6: name the nearest 24-hour casualty specifically")
    require("emergency.casualty.road", "spec §6: the casualty's road is required")
    require("emergency.casualty.verified_on", "spec §6: verify each one, do not rely on the model")
    require("emergency.casualty.verified_by", "spec §6: a human must own the verification")
    if raw.get("emergency", {}).get("casualty", {}).get("open_24h") is not True:
        errors.append("emergency.casualty.open_24h must be true: spec §6 requires a 24-hour casualty")
    numbers = raw.get("emergency", {}).get("emergency_numbers") or []
    if not {"999", "112"} <= set(map(str, numbers)):
        errors.append("emergency.emergency_numbers must include both 999 and 112 (spec §6)")

    hours = raw.get("opening_hours") or {}
    for day in _REQUIRED_DAYS:
        if day not in hours:
            errors.append(f"opening_hours.{day} missing: spec §6 forbids approximating hours")

    # Spec §6 PRICING.
    prices = raw.get("price_list") or []
    if not prices:
        errors.append("price_list is empty: spec §7 requires a published price list")
    seen_consultation = False
    for i, entry in enumerate(prices):
        where = f"price_list[{i}] ({entry.get('procedure', '?')})"
        category = (entry.get("category") or "").lower()
        quotable = bool(entry.get("quotable"))
        if category in NEVER_QUOTABLE_CATEGORIES and quotable:
            errors.append(
                f"{where}: category {category!r} may never be quotable (spec §6 pricing)"
            )
        if quotable and not entry.get("from_price_kes"):
            errors.append(f"{where}: quotable entries need a from_price_kes (spec §6: 'from' figures)")
        if not quotable and entry.get("from_price_kes"):
            warnings.append(
                f"{where}: carries a price but is not quotable; the agent must never read it out"
            )
        if entry.get("is_consultation_fee"):
            seen_consultation = True
    if not seen_consultation:
        errors.append(
            "no price_list entry marked is_consultation_fee: spec §6 needs 'the consultation is KES [X]'"
        )

    # Spec §6 PAYMENT AND COVER.
    insurers = raw.get("payment", {}).get("insurers_accepted")
    if insurers is None:
        errors.append(
            "payment.insurers_accepted missing: use an empty list to mean 'confirm no insurer'"
        )
    else:
        for name in insurers:
            if str(name).strip().lower() in FORBIDDEN_INSURERS:
                errors.append(
                    f"payment.insurers_accepted contains {name!r}: spec §6 forbids asserting SHA cover"
                )

    # Spec §9 scenario 29.
    for i, item in enumerate(raw.get("services_not_offered") or []):
        if not item.get("referral"):
            errors.append(
                f"services_not_offered[{i}]: needs a referral; scenario 29 forbids inventing a clinic"
            )

    # Spec §7 WhatsApp additions.
    if raw.get("whatsapp", {}).get("send_price_list_as_message"):
        require("location.maps_pin", "spec §7: send the location pin on booking")
        require("whatsapp.response_time_promise", "spec §7 KNOWLEDGE addition")

    if raw.get("fictional") and "FICTIONAL" not in yaml.safe_dump(raw).upper():
        warnings.append("fictional clinic: mark test data clearly so it never ships")

    return errors, warnings


def load_clinic(path: str | Path, *, strict: bool = True) -> Clinic:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise KnowledgeError(f"{path}: not a YAML mapping")
    errors, warnings = validate(raw)
    if errors and strict:
        listed = "\n  - ".join(errors)
        raise KnowledgeError(f"{path} is not fit to serve patients from:\n  - {listed}")
    prices = tuple(
        Price(
            procedure=e["procedure"],
            aliases=tuple(e.get("aliases") or ()),
            from_price_kes=e.get("from_price_kes"),
            quotable=bool(e.get("quotable")) and (e.get("category") or "").lower()
            not in NEVER_QUOTABLE_CATEGORIES,
            category=e.get("category"),
            is_consultation_fee=bool(e.get("is_consultation_fee")),
        )
        for e in (raw.get("price_list") or [])
    )
    return Clinic(
        clinic_id=raw.get("clinic_id", str(path)),
        raw=raw,
        prices=prices,
        fictional=bool(raw.get("fictional")),
        warnings=tuple(warnings),
    )
