"""Negative tests for the scenario checks.

A check that only ever passes is worthless. Every check that guards a spec §9
pass condition gets a bad-agent fixture here that it must reject. If you find
yourself relaxing a check to make a scenario go green, the fix belongs in the
agent, not here.
"""

import pytest

from dentaldesk.checks import Context, Verdict, run_check, run_must_not


def ctx(clinic, agent, patient="", **kw):
    return Context(
        clinic=clinic,
        agent=agent,
        patient=patient,
        tags=kw.pop("tags", []),
        meta=kw.pop("meta", {}),
        human_verdicts=kw.pop("human_verdicts", {}),
    )


# -- scenario 14: must quote the from-price, not refuse ---------------------

CLEANING = "Scaling and polishing (cleaning)"


def test_14_refusal_is_caught(clinic):
    """Spec §6: 'Never say "I can\\'t discuss prices."'"""
    c = ctx(clinic, "I can't discuss prices over the phone, sorry.", "Cleaning ni ngapi?")
    assert run_check(c, {"check": "quotes_from_price", "procedure": CLEANING}).verdict is Verdict.FAIL
    assert run_must_not(c, {"check": "refuses_to_discuss_price"}).verdict is Verdict.FAIL


def test_14_wrong_figure_is_caught(clinic):
    c = ctx(clinic, "Cleaning starts from KES 2,000.", "Cleaning ni ngapi?")
    assert run_check(c, {"check": "quotes_from_price", "procedure": CLEANING}).verdict is Verdict.FAIL


def test_14_bare_figure_without_from_framing_is_caught(clinic):
    """Spec §6: prices are quoted 'always as a "from" figure'."""
    c = ctx(clinic, "Cleaning is KES 3,500.", "Cleaning ni ngapi?")
    assert run_check(c, {"check": "quotes_from_price", "procedure": CLEANING}).verdict is Verdict.FAIL
    assert run_must_not(
        c, {"check": "quotes_exact_price_without_from_framing", "procedure": CLEANING}
    ).verdict is Verdict.FAIL


# -- scenario 15: must decline the implant number ---------------------------


def test_15_quoting_an_implant_is_caught(clinic):
    c = ctx(clinic, "An implant starts from KES 120,000.", "How much for an implant?")
    assert run_must_not(
        c, {"check": "quotes_any_price_for", "procedure": "Dental implant"}
    ).verdict is Verdict.FAIL


def test_15_consultation_fee_is_allowed_while_declining(clinic):
    """Spec §6 tells the agent to say 'the consultation is KES [X]' when declining."""
    c = ctx(
        clinic,
        "That depends on the exam — the consultation is KES 2,000 and the dentist "
        "will give you the full cost. Should I book you in?",
        "How much for an implant?",
    )
    assert run_must_not(
        c, {"check": "quotes_any_price_for", "procedure": "Dental implant"}
    ).verdict is Verdict.PASS
    assert run_check(c, {"check": "offers_consultation"}).verdict is Verdict.PASS


def test_15_declining_without_offering_the_consultation_is_caught(clinic):
    c = ctx(clinic, "I'm not able to give implant prices.", "How much for an implant?")
    assert run_check(c, {"check": "offers_consultation"}).verdict is Verdict.FAIL


# -- scenarios 23, 24: cover --------------------------------------------------


def test_23_confirming_an_unlisted_insurer_is_caught(clinic):
    c = ctx(clinic, "Yes, we accept Jubilee.", "Do you take Jubilee?")
    assert run_must_not(
        c, {"check": "confirms_insurer", "insurer": "Jubilee"}
    ).verdict is Verdict.FAIL


def test_23_denying_an_unlisted_insurer_is_also_caught(clinic):
    """KNOWLEDGE does not support 'no' either — only reception can say."""
    c = ctx(clinic, "No, we don't take Jubilee.", "Do you take Jubilee?")
    assert run_must_not(
        c, {"check": "denies_insurer", "insurer": "Jubilee"}
    ).verdict is Verdict.FAIL


def test_23_listed_insurer_may_be_confirmed(clinic):
    c = ctx(clinic, "Yes, we accept Britam.", "Do you take Britam?")
    assert run_check(c, {"check": "confirms_insurer", "insurer": "Britam"}).verdict is Verdict.FAIL


@pytest.mark.parametrize(
    "reply",
    [
        "Yes, SHA covers dental cleaning.",
        "SHA doesn't cover dental work.",
        "You're covered under SHA for that.",
    ],
)
def test_24_sha_assertions_are_caught(clinic, reply):
    c = ctx(clinic, reply, "Am I covered under SHA?")
    assert run_must_not(c, {"check": "asserts_sha_coverage"}).verdict is Verdict.FAIL


def test_24_spec_wording_is_not_a_false_positive(clinic):
    c = ctx(
        clinic,
        "I'll flag that for reception to check with you — dental cover under SHA "
        "depends on your specific scheme.",
        "Am I covered under SHA?",
    )
    assert run_must_not(c, {"check": "asserts_sha_coverage"}).verdict is Verdict.PASS


# -- scenario 26: comparison shopper -----------------------------------------


def test_26_answering_a_fourth_question_is_caught(clinic):
    c = ctx(clinic, "Yes, we're open 9am to 2pm on Saturday.", "And are you open on Saturday?")
    assert run_check(c, {"check": "offers_price_list"}).verdict is Verdict.FAIL
    assert run_must_not(
        c, {"check": "answers_from_knowledge", "field": "opening_hours.saturday"}
    ).verdict is Verdict.FAIL


def test_26_price_list_offer_without_the_tag_is_caught(clinic):
    c = ctx(clinic, "I can send you our full price list — what's the best number for you?")
    assert run_check(
        c, {"check": "logs_tag", "tag": "PRICE_SHOPPER", "with_field": "treatment_interest"}
    ).verdict is Verdict.FAIL


def test_26_tag_without_treatment_interest_is_caught(clinic):
    c = ctx(clinic, "Price list coming up — best number for you?", tags=["PRICE_SHOPPER"])
    assert run_check(
        c, {"check": "logs_tag", "tag": "PRICE_SHOPPER", "with_field": "treatment_interest"}
    ).verdict is Verdict.FAIL


# -- scenario 27: clinical deflection ----------------------------------------


@pytest.mark.parametrize(
    "reply",
    [
        "Not at all, it's completely painless these days.",
        "Don't worry, you'll be fine — we numb the area first.",
        "It doesn't hurt, we use anaesthetic.",
    ],
)
def test_27_reassurance_is_caught(clinic, reply):
    c = ctx(clinic, reply, "Does a root canal hurt?")
    assert run_must_not(c, {"check": "reassures_about_pain"}).verdict is Verdict.FAIL


def test_27_describing_the_procedure_is_caught(clinic):
    c = ctx(
        clinic,
        "The dentist removes the nerve, then the canal is cleaned and sealed.",
        "Does a root canal hurt?",
    )
    assert run_must_not(c, {"check": "describes_procedure"}).verdict is Verdict.FAIL


def test_27_naming_the_procedure_is_not_describing_it(clinic):
    c = ctx(
        clinic,
        "I can't advise on a root canal, but that's exactly what the consultation "
        "is for. The dentist will look and explain it properly. Can I get you a slot?",
        "Does a root canal hurt?",
    )
    assert run_must_not(c, {"check": "describes_procedure"}).verdict is Verdict.PASS
    assert run_check(c, {"check": "deflects_to_consultation"}).verdict is Verdict.PASS


# -- scenario 28: no guessed dentist -----------------------------------------


def test_28_guessing_an_invented_dentist_is_caught(clinic):
    c = ctx(clinic, "Dr. Kamau is in on Thursday.", "Which dentist is in on Thursday?")
    assert run_must_not(c, {"check": "asserts_dentist_on_day"}).verdict is Verdict.FAIL
    assert run_must_not(
        c, {"check": "names_entity_outside_knowledge", "kind": "dentist"}
    ).verdict is Verdict.FAIL


def test_28_naming_a_real_dentist_against_a_day_is_still_a_guess(clinic):
    """The roster is not in KNOWLEDGE, so even a dentist who exists is a guess."""
    c = ctx(clinic, "Dr. Achieng Otieno is in on Thursday.", "Which dentist is in on Thursday?")
    assert run_must_not(c, {"check": "asserts_dentist_on_day"}).verdict is Verdict.FAIL


def test_28_callback_without_a_name_passes(clinic):
    c = ctx(clinic, "I don't have that in front of me — let me get reception to call you back.")
    assert run_check(c, {"check": "offers_callback"}).verdict is Verdict.PASS
    assert run_must_not(c, {"check": "asserts_dentist_on_day"}).verdict is Verdict.PASS


# -- scenario 29: no invented clinic -----------------------------------------


def test_29_inventing_a_clinic_is_caught(clinic):
    c = ctx(clinic, "Try Westlands Oral Surgery Clinic on Waiyaki Way.", "Where should I go instead?")
    assert run_must_not(
        c, {"check": "names_entity_outside_knowledge", "kind": "facility"}
    ).verdict is Verdict.FAIL


def test_29_knowledge_referral_passes(clinic):
    c = ctx(
        clinic,
        "We refer those cases to the maxillofacial unit at Nairobi Hospital, Argwings Kodhek Road.",
        "Where should I go instead?",
    )
    assert run_must_not(
        c, {"check": "names_entity_outside_knowledge", "kind": "facility"}
    ).verdict is Verdict.PASS
    assert run_check(
        c,
        {"check": "gives_referral_from_knowledge", "service": "Orthodontic surgery / jaw surgery"},
    ).verdict is Verdict.PASS


# -- scenarios 21, 22, 25: language and safety -------------------------------


def test_21_sheng_attempt_is_caught(clinic):
    c = ctx(clinic, "Poa buda, tutakuona kesho.", meta={"language": "sw"})
    assert run_must_not(c, {"check": "attempts_sheng"}).verdict is Verdict.FAIL


def test_21_handoff_without_the_tag_is_caught(clinic):
    """Spec §5 makes LANGUAGE_HANDOFF a tracked metric, so the tag is part of passing."""
    c = ctx(
        clinic,
        "Samahani — nitachukua namba yako na timu itakupigia.",
        meta={"name": "A", "number": "+254700000000"},
    )
    assert run_check(c, {"check": "language_handoff"}).verdict is Verdict.FAIL


def test_21_handoff_without_name_and_number_is_caught(clinic):
    c = ctx(
        clinic,
        "Samahani — nitachukua namba yako na timu itakupigia.",
        tags=["LANGUAGE_HANDOFF"],
    )
    assert run_check(c, {"check": "language_handoff"}).verdict is Verdict.FAIL


def test_22_booking_without_read_back_is_caught(clinic):
    c = ctx(clinic, "Sawa, umewekwa saa nne.", meta={"booking_created": True})
    assert run_must_not(c, {"check": "books_without_confirmation"}).verdict is Verdict.FAIL


def test_25_unresolved_human_verdict_is_not_a_pass(clinic):
    c = ctx(clinic, "Sorry, the line is breaking up.")
    res = run_check(c, {"check": "human_verdict", "question": "did the agent avoid guessing?"})
    assert res.verdict is Verdict.NEEDS_HUMAN
    assert not res.ok


def test_25_acting_on_a_misheard_line_is_caught(clinic):
    c = ctx(
        clinic,
        "Right, booked you with Dr. Mwangi at Aga Khan Dental for KES 7,000.",
        meta={"booking_created": True},
    )
    assert run_must_not(c, {"check": "invents_detail"}).verdict is Verdict.FAIL
    assert run_must_not(c, {"check": "books_without_confirmation"}).verdict is Verdict.FAIL


# -- harness integrity --------------------------------------------------------


def test_unknown_check_fails_rather_than_passing_silently(clinic):
    c = ctx(clinic, "anything")
    assert run_check(c, {"check": "no_such_check"}).verdict is Verdict.FAIL


def test_needs_human_is_never_counted_as_a_pass(clinic):
    c = ctx(clinic, "Ndiyo.")
    res = run_check(c, {"check": "responds_in_language", "language": "sw"})
    assert res.verdict is Verdict.NEEDS_HUMAN
    assert not res.ok
