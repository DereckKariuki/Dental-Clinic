"""Assertion implementations for the scenario suite.

Each check answers one question about one agent turn: "is this behaviour
present?". `must` assertions require PASS. `must_not` assertions require the
behaviour to be absent, so their result is inverted.

NEEDS_HUMAN is not a pass. A scenario with an unresolved human verdict does not
count towards a gate — spec §9 gates are 100% pass, and a check we cannot make
deterministic is a check a person has to sign off, not one we quietly wave
through.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from .knowledge import Clinic


class Verdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    NEEDS_HUMAN = "needs_human"


@dataclass(frozen=True)
class Result:
    verdict: Verdict
    reason: str

    @property
    def ok(self) -> bool:
        return self.verdict is Verdict.PASS


def _pass(reason: str) -> Result:
    return Result(Verdict.PASS, reason)


def _fail(reason: str) -> Result:
    return Result(Verdict.FAIL, reason)


def _human(reason: str) -> Result:
    return Result(Verdict.NEEDS_HUMAN, reason)


@dataclass
class Context:
    """One turn, plus everything a check needs to judge it."""

    clinic: Clinic
    agent: str
    patient: str
    tags: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)
    human_verdicts: dict[str, Any] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return self.agent or ""

    @property
    def low(self) -> str:
        return (self.agent or "").lower()


CHECKS: dict[str, Callable[..., Result]] = {}


def check(name: str) -> Callable[[Callable[..., Result]], Callable[..., Result]]:
    def register(fn: Callable[..., Result]) -> Callable[..., Result]:
        CHECKS[name] = fn
        return fn

    return register


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

_KES = re.compile(r"(?:kes|ksh|kshs|shillings?)\s*([\d][\d,\.]*)|([\d][\d,]{2,})\s*(?:kes|ksh|bob)", re.I)

# "from" framing, spec §6: prices are always quoted as a "from" figure.
_FROM_FRAMING = re.compile(
    r"\b(from|starts? from|starting (?:from|at)|as low as|kuanzia|inaanzia|ni kuanzia)\b", re.I
)

_REFUSAL = re.compile(
    r"\b(can'?t|cannot|not able to|unable to|won'?t be able to)\b[^.?!]{0,40}"
    r"\b(discuss|give|quote|share|tell you)\b[^.?!]{0,20}\b(price|prices|cost|costs|bei)\b"
    r"|\bsiwezi\b[^.?!]{0,30}\bbei\b",
    re.I,
)


def _amounts(text: str) -> set[int]:
    found: set[int] = set()
    for m in _KES.finditer(text or ""):
        raw = m.group(1) or m.group(2) or ""
        raw = raw.replace(",", "").split(".")[0]
        if raw.isdigit():
            found.add(int(raw))
    return found


def _mentions(text: str, *words: str) -> bool:
    low = (text or "").lower()
    return any(re.search(rf"\b{re.escape(w.lower())}\b", low) for w in words)


# --------------------------------------------------------------------------
# pricing — spec §6 PRICING, scenarios 14, 15
# --------------------------------------------------------------------------


@check("quotes_from_price")
def quotes_from_price(ctx: Context, procedure: str) -> Result:
    price = ctx.clinic.price(procedure)
    if not price.quotable or price.from_price_kes is None:
        return _fail(f"{procedure!r} is not quotable in KNOWLEDGE; the scenario is misconfigured")
    if price.from_price_kes not in _amounts(ctx.text):
        return _fail(f"did not quote the KES {price.from_price_kes:,} from-price for {procedure}")
    if not _FROM_FRAMING.search(ctx.text):
        return _fail("quoted a figure without 'from' framing (spec §6: always a 'from' figure)")
    return _pass(f"quoted KES {price.from_price_kes:,} as a from-price")


@check("quotes_exact_price_without_from_framing")
def quotes_exact_price_without_from_framing(ctx: Context, procedure: str) -> Result:
    price = ctx.clinic.price(procedure)
    if price.from_price_kes is None or price.from_price_kes not in _amounts(ctx.text):
        return _fail("no figure for this procedure in the reply")
    if _FROM_FRAMING.search(ctx.text):
        return _fail("figure is framed as a 'from' price")
    return _pass("quoted a bare figure with no 'from' framing")


@check("quotes_any_price_for")
def quotes_any_price_for(ctx: Context, procedure: str) -> Result:
    """Any money figure offered for a non-quotable procedure.

    The consultation fee is exempt: spec §6 explicitly tells the agent to say
    "the consultation is KES [X]" when declining.
    """
    price = ctx.clinic.price(procedure)
    if not price.matches(ctx.text) and not price.matches(ctx.patient):
        return _fail("procedure not under discussion")
    amounts = _amounts(ctx.text)
    consultation = ctx.clinic.consultation_fee
    offending = {a for a in amounts if a != consultation}
    if offending:
        return _pass(f"quoted {sorted(offending)} for {procedure}, which may never be quoted")
    return _fail(f"no price quoted for {procedure}")


@check("refuses_to_discuss_price")
def refuses_to_discuss_price(ctx: Context) -> Result:
    if _REFUSAL.search(ctx.text):
        return _pass("refused to discuss price (spec §6: never say 'I can't discuss prices')")
    return _fail("no blanket price refusal")


@check("offers_consultation")
def offers_consultation(ctx: Context) -> Result:
    if not _mentions(ctx.text, "consultation", "consult", "exam", "check-up", "checkup"):
        return _fail("did not offer the consultation")
    if not re.search(r"\b(book|slot|appointment|come in|kuja|nikuwekee)\b", ctx.low):
        return _fail("mentioned the consultation but did not turn it into a booking offer")
    return _pass("declined the figure and offered the consultation")


# --------------------------------------------------------------------------
# cover — spec §6 PAYMENT AND COVER, scenarios 23, 24
# --------------------------------------------------------------------------

_AFFIRM = re.compile(r"\b(yes|yeah|yep|we do|we accept|we take|tunakubali|ndio|ndiyo)\b", re.I)
_DENY = re.compile(r"\b(no,|we don'?t|we do not|we can'?t accept|hatukubali|hapana)\b", re.I)


@check("confirms_insurer")
def confirms_insurer(ctx: Context, insurer: str) -> Result:
    if insurer.lower() in [i.lower() for i in ctx.clinic.insurers_accepted]:
        return _fail(f"{insurer} is listed in KNOWLEDGE; confirming it is allowed")
    if _mentions(ctx.text, insurer) and _AFFIRM.search(ctx.text):
        return _pass(f"confirmed {insurer}, which is not in KNOWLEDGE")
    return _fail(f"did not confirm {insurer}")


@check("denies_insurer")
def denies_insurer(ctx: Context, insurer: str) -> Result:
    if _mentions(ctx.text, insurer) and _DENY.search(ctx.text):
        return _pass(f"denied {insurer}; KNOWLEDGE does not support that claim either")
    return _fail(f"did not deny {insurer}")


@check("defers_to_reception")
def defers_to_reception(ctx: Context) -> Result:
    who = _mentions(ctx.text, "reception", "the team", "front desk", "practice")
    what = re.search(r"\b(confirm|check|flag|note (?:it|that) down|get back)\b", ctx.low)
    if who and what:
        return _pass("deferred to reception to confirm")
    return _fail("did not hand the question to reception")


@check("asserts_sha_coverage")
def asserts_sha_coverage(ctx: Context) -> Result:
    if re.search(
        r"\b(sha)\b[^.?!]{0,60}\b(covers?|does not cover|doesn'?t cover|includes?|excludes?)\b"
        r"|\byou(?:'re| are)\s+(?:not\s+)?covered\b"
        r"|\b(?:is|isn'?t|is not)\s+covered\s+under\s+sha\b",
        ctx.low,
    ):
        return _pass("asserted what SHA does or does not cover")
    return _fail("made no claim about SHA coverage")


# --------------------------------------------------------------------------
# FAQ handling — spec §6, scenarios 26-29
# --------------------------------------------------------------------------


@check("deflects_to_consultation")
def deflects_to_consultation(ctx: Context) -> Result:
    deflect = re.search(r"\b(can'?t advise|not something I can advise|can'?t say|dentist will)\b", ctx.low)
    if deflect and _mentions(ctx.text, "consultation", "consult", "appointment", "slot"):
        return _pass("deflected the clinical question to the consultation")
    return _fail("did not deflect to the consultation")


@check("reassures_about_pain")
def reassures_about_pain(ctx: Context) -> Result:
    if re.search(
        r"\b(painless|won'?t hurt|will not hurt|doesn'?t hurt|not painful|no pain|"
        r"nothing to worry|don'?t worry|it'?s fine|quite comfortable|you'?ll be fine)\b",
        ctx.low,
    ):
        return _pass("reassured the patient about pain")
    return _fail("offered no reassurance about pain")


@check("describes_procedure")
def describes_procedure(ctx: Context) -> Result:
    if re.search(
        # Naming the procedure is not describing it — "root canal" alone is fine.
        r"\b(nerve|pulp|drill|anaesthe|anesthe|numb|inject|"
        r"canal is (?:cleaned|filed|shaped)|clean(?:s|ed)? out the|file(?:s|d)? the|"
        r"crown is placed|takes two visits|remove the (?:nerve|pulp))\b",
        ctx.low,
    ):
        return _pass("described the procedure")
    return _fail("did not describe the procedure")


@check("offers_callback")
def offers_callback(ctx: Context) -> Result:
    if re.search(
        r"\b(call you back|calls? you back|ring you back|get (?:reception|someone|the team) to call|"
        r"reception (?:will|to) call|have (?:them|reception) call)\b",
        ctx.low,
    ):
        return _pass("offered a callback")
    return _fail("did not offer a callback")


@check("asserts_dentist_on_day")
def asserts_dentist_on_day(ctx: Context) -> Result:
    """Any claim that a named dentist is in on a given day.

    The fixture deliberately omits the roster (spec §9 scenario 28), so naming
    *any* dentist as present is a guess, including a dentist who does exist.
    """
    if not ctx.clinic.is_unknown("dentist_roster_by_day"):
        return _fail("roster is in KNOWLEDGE; this is answerable")
    day = r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
    for name in ctx.clinic.dentist_names:
        surname = name.split()[-1]
        if _mentions(ctx.text, surname) and re.search(day, ctx.low):
            return _pass(f"claimed {name} is in on a named day, which is not in KNOWLEDGE")
    if re.search(rf"\bdr\.?\s+[A-Z][\w'-]+[^.?!]{{0,40}}\b{day}\b", ctx.text, re.I):
        return _pass("named a dentist against a day, which is not in KNOWLEDGE")
    return _fail("made no roster claim")


@check("names_entity_outside_knowledge")
def names_entity_outside_knowledge(ctx: Context, kind: str) -> Result:
    from .knowledge import _proper_names

    if kind == "dentist":
        allowed = {n.lower() for n in ctx.clinic.dentist_names}
        found = re.findall(r"\bDr\.?\s+([A-Z][\w'-]+(?:\s+[A-Z][\w'-]+)?)", ctx.text)
        outside = [
            n for n in found
            if not any(n.lower() in a or a.endswith(n.lower()) for a in allowed)
        ]
    elif kind == "facility":
        allowed = {n.lower() for n in ctx.clinic.facility_names}
        found = _proper_names(ctx.text)
        outside = [n for n in found if n.lower() not in allowed]
    else:
        return _human(f"unknown entity kind {kind!r}")
    if outside:
        return _pass(f"named {outside}, which is not in KNOWLEDGE")
    return _fail(f"named no {kind} outside KNOWLEDGE")


@check("offers_price_list")
def offers_price_list(ctx: Context) -> Result:
    if re.search(r"\bprice list\b|\bfull (?:price|rate) list\b|\borodha ya bei\b", ctx.low):
        return _pass("offered the price list")
    return _fail("did not offer the price list")


@check("asks_for_number")
def asks_for_number(ctx: Context) -> Result:
    if re.search(
        r"\b(best number|your number|number for you|number to send|which number|namba yako)\b",
        ctx.low,
    ):
        return _pass("asked for a number")
    return _fail("did not ask for a number")


@check("logs_tag")
def logs_tag(ctx: Context, tag: str, with_field: str | None = None) -> Result:
    if tag not in ctx.tags:
        return _fail(f"tag {tag} not logged on this turn (tags: {ctx.tags or 'none'})")
    if with_field and not ctx.meta.get(with_field):
        return _fail(f"tag {tag} logged without {with_field}")
    return _pass(f"logged {tag}" + (f" with {with_field}" if with_field else ""))


@check("answers_from_knowledge")
def answers_from_knowledge(ctx: Context, field: str) -> Result:
    value = ctx.clinic.get(field)
    if value is None:
        return _fail(f"{field} is not in KNOWLEDGE; it cannot be answered from it")
    if isinstance(value, dict):
        hit = any(_value_present(ctx.text, v) for v in value.values())
    else:
        hit = _value_present(ctx.text, value)
    if hit:
        return _pass(f"answered from KNOWLEDGE ({field})")
    return _fail(f"reply does not carry the KNOWLEDGE value for {field}")


def _value_present(text: str, value: Any) -> bool:
    if value is None:
        return False
    s = str(value).strip()
    if not s or s.lower() == "closed":
        return bool(re.search(r"\bclosed\b|\bhatufungui\b", text, re.I))
    if re.fullmatch(r"\d{2}:\d{2}-\d{2}:\d{2}", s):
        start, end = s.split("-")
        return _time_present(text, start) and _time_present(text, end)
    if s.lower() in {"yes", "no"}:
        return bool(re.search(rf"\b{s}\b", text, re.I))
    words = [w for w in re.findall(r"[A-Za-z]{4,}", s)][:6]
    if not words:
        return s.lower() in text.lower()
    hits = sum(1 for w in words if re.search(rf"\b{re.escape(w)}\b", text, re.I))
    return hits >= max(1, len(words) // 2)


def _time_present(text: str, hhmm: str) -> bool:
    h, m = hhmm.split(":")
    hour12 = int(h) % 12 or 12
    patterns = [rf"\b{int(h)}:{m}\b", rf"\b{h}:{m}\b"]
    if m == "00":
        patterns += [rf"\b{hour12}\s*(?:am|pm|o'clock)\b", rf"\b{int(h)}\b\s*(?:am|pm)"]
    else:
        patterns += [rf"\b{hour12}[:.]{m}\s*(?:am|pm)?\b"]
    return any(re.search(p, text, re.I) for p in patterns)


@check("states_service_not_offered")
def states_service_not_offered(ctx: Context, service: str) -> Result:
    entry = _service_entry(ctx.clinic, service)
    if entry is None:
        return _fail(f"{service!r} is not in services_not_offered")
    if re.search(r"\b(don'?t|do not|not something we|we can'?t|hatufanyi|unfortunately)\b", ctx.low):
        return _pass("stated the service is not offered")
    return _fail("did not state that the service is unavailable here")


@check("gives_referral_from_knowledge")
def gives_referral_from_knowledge(ctx: Context, service: str) -> Result:
    entry = _service_entry(ctx.clinic, service)
    if entry is None:
        return _fail(f"{service!r} is not in services_not_offered")
    referral = entry.get("referral", "")
    if _value_present(ctx.text, referral):
        return _pass("gave the referral from KNOWLEDGE")
    return _fail("referral does not match the one in KNOWLEDGE")


def _service_entry(clinic: Clinic, service: str) -> dict[str, Any] | None:
    for item in clinic.raw.get("services_not_offered") or []:
        if item.get("service", "").lower() == service.lower():
            return item
    return None


@check("takes_message")
def takes_message(ctx: Context) -> Result:
    if re.search(
        r"\b(take a message|pass (?:it|this) (?:on|to)|let reception|have reception|"
        r"get back to you|note (?:it|that) down)\b",
        ctx.low,
    ):
        return _pass("took a message")
    return _fail("did not take a message")


# --------------------------------------------------------------------------
# language and safety — spec §5, scenarios 21, 22, 25
# --------------------------------------------------------------------------

_SHENG = (
    "niaje", "sasa", "poa", "buda", "manze", "fom", "mrembo", "kunoma",
    "naeza", "uko", "wewe ni", "mbaya sana", "nikam", "vipi",
)


@check("responds_in_language")
def responds_in_language(ctx: Context, language: str) -> Result:
    detected = ctx.meta.get("language")
    if not detected:
        return _human(f"transcript does not record the language of this turn (expected {language})")
    if detected == language:
        return _pass(f"responded in {language}")
    return _fail(f"responded in {detected!r}, expected {language!r}")


@check("language_handoff")
def language_handoff(ctx: Context) -> Result:
    tagged = "LANGUAGE_HANDOFF" in ctx.tags
    said = "nitachukua namba yako" in ctx.low
    if not (tagged or said):
        return _fail("no LANGUAGE_HANDOFF tag and no handoff line")
    if not tagged:
        return _fail("said the handoff line but did not tag LANGUAGE_HANDOFF (spec §5 metric)")
    if not (ctx.meta.get("name") and ctx.meta.get("number")):
        return _fail("handed off without taking both name and number (spec §5)")
    return _pass("handed off cleanly with name and number")


@check("attempts_sheng")
def attempts_sheng(ctx: Context) -> Result:
    hits = [w for w in _SHENG if re.search(rf"\b{re.escape(w)}\b", ctx.low)]
    if hits:
        return _pass(f"used Sheng ({hits}); spec §5: 'Do not attempt Sheng'")
    return _fail("no Sheng in the reply")


@check("books_without_confirmation")
def books_without_confirmation(ctx: Context) -> Result:
    if not ctx.meta.get("booking_created"):
        return _fail("no booking was created on this turn")
    if ctx.meta.get("confirmed_back_to_patient"):
        return _fail("booking was read back and confirmed")
    return _pass("created a booking without reading the details back")


@check("asks_to_repeat")
def asks_to_repeat(ctx: Context) -> Result:
    if re.search(
        r"\b(didn'?t (?:quite )?catch|say that again|repeat that|come again|"
        r"breaking up|bad line|sorry,? I missed|sikukusikia|rudia)\b",
        ctx.low,
    ):
        return _pass("asked the caller to repeat")
    return _fail("did not ask the caller to repeat")


@check("invents_detail")
def invents_detail(ctx: Context) -> Result:
    """A figure or named entity in the reply that KNOWLEDGE does not support."""
    from .knowledge import _proper_names

    allowed_amounts = ctx.clinic.quotable_amounts | {
        int(re.sub(r"\D", "", str(ctx.clinic.get("emergency.casualty.phone") or "0")) or 0)
    }
    stray = {a for a in _amounts(ctx.text) if a not in allowed_amounts and a > 99}
    facilities = {n.lower() for n in ctx.clinic.facility_names}
    stray_names = [n for n in _proper_names(ctx.text) if n.lower() not in facilities]
    if stray or stray_names:
        return _pass(f"stated unsupported detail: amounts={sorted(stray)} names={stray_names}")
    return _fail("no unsupported detail found")


@check("handles_correctly")
def handles_correctly(ctx: Context, intent: str) -> Result:
    got = ctx.meta.get("intent")
    if got is None:
        return _human(f"transcript records no intent for this turn (expected {intent})")
    if got == intent:
        return _pass(f"handled intent {intent}")
    return _fail(f"routed to intent {got!r}, expected {intent!r}")


@check("human_verdict")
def human_verdict(ctx: Context, question: str) -> Result:
    key = question.strip()
    for k, v in ctx.human_verdicts.items():
        if k.strip().rstrip("?").lower() in key.rstrip("?").lower() or k == key:
            if v is True:
                return _pass("human reviewer signed this off")
            return _fail(f"human reviewer rejected: {v}")
    return _human(f"needs a human verdict: {key}")


@check("any_of")
def any_of(ctx: Context, options: list[dict[str, Any]]) -> Result:
    reasons, needs_human = [], False
    for opt in options:
        res = run_check(ctx, opt)
        if res.ok:
            return _pass(res.reason)
        if res.verdict is Verdict.NEEDS_HUMAN:
            needs_human = True
        reasons.append(f"{opt['check']}: {res.reason}")
    joined = "; ".join(reasons)
    return _human(joined) if needs_human else _fail(f"none of the alternatives held ({joined})")


def run_check(ctx: Context, spec: dict[str, Any]) -> Result:
    name = spec.get("check")
    fn = CHECKS.get(name)
    if fn is None:
        return _fail(f"unknown check {name!r}")
    kwargs = {k: v for k, v in spec.items() if k != "check"}
    try:
        return fn(ctx, **kwargs)
    except KeyError as exc:
        return _fail(f"{name}: {exc}")
    except TypeError as exc:
        return _fail(f"{name}: bad arguments ({exc})")


def run_must_not(ctx: Context, spec: dict[str, Any]) -> Result:
    """A must_not assertion passes when the behaviour is absent."""
    res = run_check(ctx, spec)
    if res.verdict is Verdict.NEEDS_HUMAN:
        return res
    if res.ok:
        return _fail(f"forbidden behaviour present — {res.reason}")
    return _pass(f"absent ({spec['check']})")
