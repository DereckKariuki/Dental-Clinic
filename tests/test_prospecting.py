"""Spec §3 qualification test scoring."""

from datetime import datetime, timedelta

import pytest

from dentaldesk.prospecting.qualify import (
    CallResult, Survey, Tier, assess, load_surveys, rank,
)

SENT = datetime(2026, 9, 1, 20, 0)


def survey(**kw) -> Survey:
    base = dict(
        name="Test Dental",
        area="Westlands",
        kind="private",
        chairs=3,
        owner_dentist="Dr. Test",
        rating=4.6,
        review_count=80,
        services=("implants", "aligners"),
        insurers=("britam",),
        has_whatsapp=True,
        runs_ads=True,
        whatsapp_sent_at=SENT,
        whatsapp_replied_at=None,
        call_midday=CallResult.VOICEMAIL,
        call_after_close=CallResult.VOICEMAIL,
    )
    base.update(kw)
    return Survey(**base)


def test_tier_a_needs_no_whatsapp_reply_and_both_calls_missed():
    """Spec §3: Tier A = no WhatsApp reply within 12 hours AND voicemail on both."""
    assert assess(survey()).tier is Tier.A


def test_reply_inside_twelve_hours_is_not_tier_a():
    a = assess(survey(whatsapp_replied_at=SENT + timedelta(hours=11, minutes=59)))
    assert a.tier is Tier.B  # still missed both calls
    assert a.survey.failed_whatsapp_test is False


def test_reply_after_twelve_hours_counts_as_a_failure():
    a = assess(survey(whatsapp_replied_at=SENT + timedelta(hours=12, minutes=1)))
    assert a.survey.failed_whatsapp_test is True
    assert a.tier is Tier.A


def test_one_answered_call_drops_to_tier_b():
    assert assess(survey(call_midday=CallResult.ANSWERED)).tier is Tier.B


def test_answering_everything_is_tier_c():
    a = assess(
        survey(
            whatsapp_replied_at=SENT + timedelta(minutes=10),
            call_midday=CallResult.ANSWERED,
            call_after_close=CallResult.ANSWERED,
        )
    )
    assert a.tier is Tier.C
    assert a.opening_line is None


def test_untested_clinic_is_never_tier_a():
    """No evidence, no tier — go and run the test rather than guessing one."""
    a = assess(survey(whatsapp_sent_at=None, call_midday=None, call_after_close=None))
    assert a.tier is Tier.C
    assert "WhatsApp test not run" in a.missing
    assert "both calls not logged" in a.missing


def test_opening_line_only_exists_where_the_evidence_does():
    assert "both went to voicemail" in assess(survey()).opening_line
    assert assess(survey(call_midday=CallResult.ANSWERED)).opening_line is None


@pytest.mark.parametrize(
    "kw,expected",
    [
        ({"kind": "government"}, "skip list"),
        ({"kind": "mission"}, "skip list"),
        ({"kind": "hospital_department"}, "skip list"),
        ({"advertises_budget_extraction": True}, "budget extractions"),
        ({"chairs": 9}, "chairs"),
        ({"review_count": 4}, "reviews"),
        ({"rating": 3.9}, "rated"),
        ({"has_whatsapp": False}, "no WhatsApp number"),
    ],
)
def test_disqualifiers(kw, expected):
    a = assess(survey(**kw))
    assert a.tier is Tier.SKIP
    assert any(expected in d for d in a.disqualifiers)
    assert a.opening_line is None


def test_qualifiers_are_reported():
    a = assess(survey(review_phrases=("hawajibu simu kabisa",)))
    joined = " ".join(a.qualifiers)
    assert "priority area" in joined
    assert "high-value work" in joined
    assert "private cover" in joined
    assert "already paying for leads" in joined
    assert "hawajibu simu" in joined


def test_non_priority_area_is_not_a_disqualifier():
    a = assess(survey(area="Eldoret"))
    assert a.tier is Tier.A
    assert not any("priority area" in q for q in a.qualifiers)


def test_rank_puts_tier_a_first():
    results = rank([
        survey(name="Answers Everything", whatsapp_replied_at=SENT + timedelta(minutes=5),
               call_midday=CallResult.ANSWERED, call_after_close=CallResult.ANSWERED),
        survey(name="Government Clinic", kind="government"),
        survey(name="Silent Practice"),
        survey(name="Half Silent", call_midday=CallResult.ANSWERED),
    ])
    assert [a.tier for a in results] == [Tier.A, Tier.B, Tier.C, Tier.SKIP]
    assert results[0].survey.name == "Silent Practice"


def test_csv_round_trip(tmp_path):
    path = tmp_path / "surveys.csv"
    path.write_text(
        "name,area,chairs,rating,review_count,services,insurers,has_whatsapp,"
        "whatsapp_sent_at,call_midday,call_after_close\n"
        "Quiet Dental,Kilimani,2,4.7,60,implants|veneers,jubilee|aar,yes,"
        "2026-09-01T20:00:00,voicemail,voicemail\n",
        encoding="utf-8",
    )
    surveys = load_surveys(path)
    assert len(surveys) == 1
    s = surveys[0]
    assert s.services == ("implants", "veneers")
    assert s.has_whatsapp is True
    assert s.call_midday is CallResult.VOICEMAIL
    assert assess(s).tier is Tier.A
