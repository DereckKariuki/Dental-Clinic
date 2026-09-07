"""Integrity of the scenario suite itself (spec §9).

These tests guard the suite against the easiest way to make a red gate go
green: quietly editing the pass conditions.
"""

import pytest

from dentaldesk.checks import CHECKS
from dentaldesk.evaluate import evaluate_suite, gate_result, load_transcripts
from dentaldesk.scenarios import Status

SPEC_SPECIFIED = {14, 15, 21, 22, 23, 24, 25, 26, 27, 28, 29}


def test_all_twenty_nine_scenarios_are_present(suite):
    assert [s.id for s in suite.scenarios] == list(range(1, 30))


def test_gates_match_the_spec(suite):
    gates = {g.name: g for g in suite.gates}
    # Spec §9: "13-25 must pass 100%. 26-29 must pass 100%".
    assert (gates["core"].lo, gates["core"].hi, gates["core"].threshold) == (13, 25, 1.0)
    assert (gates["faq"].lo, gates["faq"].hi, gates["faq"].threshold) == (26, 29, 1.0)


def test_the_kenya_pack_scenarios_are_the_ones_specified(suite):
    specified = {s.id for s in suite.scenarios if s.specified}
    assert specified == SPEC_SPECIFIED


def test_specified_scenarios_carry_their_spec_quote_and_assertions(suite):
    for s in suite.scenarios:
        if not s.specified:
            continue
        assert s.spec_quote, f"scenario {s.id} has no spec_quote to check the assertions against"
        assert s.turns, f"scenario {s.id} has no turns"
        assertions = sum(len(t.must) + len(t.must_not) for t in s.turns)
        assert assertions, f"scenario {s.id} asserts nothing and would pass on any reply"


def _walk(assertions):
    for a in assertions:
        yield a
        for option in a.get("options", []) or []:
            yield from _walk([option])


def test_every_assertion_names_a_real_check(suite):
    for s in suite.scenarios:
        for t in s.turns:
            for a in _walk(list(t.must) + list(t.must_not)):
                assert a["check"] in CHECKS, f"scenario {s.id}: unknown check {a['check']!r}"


def test_unspecified_scenarios_are_blocked_not_passed(suite, clinic, repo_root):
    reports = evaluate_suite(suite, load_transcripts(repo_root / "eval" / "transcripts"), clinic)
    for s in suite.scenarios:
        if not s.specified:
            assert reports[s.id].status is Status.BLOCKED, (
                f"scenario {s.id} is not reproduced in this repo and must never report a pass"
            )


def test_reference_transcripts_pass_every_specified_scenario(suite, clinic, repo_root):
    reports = evaluate_suite(suite, load_transcripts(repo_root / "eval" / "transcripts"), clinic)
    failures = {
        sid: reports[sid].failures
        for sid in SPEC_SPECIFIED
        if reports[sid].status is not Status.PASS
    }
    assert not failures, failures


def test_core_gate_is_not_met_while_first_pack_scenarios_are_missing(suite, clinic, repo_root):
    """The spec's own gate is 13-25 at 100%. Six of those are unavailable.

    This test exists so nobody 'fixes' the red gate by deleting the blocked
    scenarios. When the first build pack is recovered, fill 13 and 16-20 in and
    this test should be updated to assert the gate is met.
    """
    reports = evaluate_suite(suite, load_transcripts(repo_root / "eval" / "transcripts"), clinic)
    core = next(g for g in suite.gates if g.name == "core")
    ok, detail = gate_result(suite, core, reports)
    assert not ok, "core gate reported green — check that 13 and 16-20 were not dropped"
    assert "13:blocked" in detail


def test_faq_gate_is_met_by_the_reference_transcripts(suite, clinic, repo_root):
    reports = evaluate_suite(suite, load_transcripts(repo_root / "eval" / "transcripts"), clinic)
    faq = next(g for g in suite.gates if g.name == "faq")
    ok, detail = gate_result(suite, faq, reports)
    assert ok, detail


def test_a_missing_transcript_is_not_a_pass(suite, clinic):
    reports = evaluate_suite(suite, {}, clinic)
    for sid in SPEC_SPECIFIED:
        assert reports[sid].status is Status.NOT_RUN
        assert not reports[sid].status.counts_as_pass


@pytest.mark.parametrize("sid", sorted(SPEC_SPECIFIED))
def test_an_empty_reply_fails_every_specified_scenario(suite, clinic, sid):
    """Sanity: no scenario passes on silence."""
    scenario = suite.by_id(sid)
    transcript = {
        "scenario": sid,
        "turns": [{"agent": ""} for _ in scenario.turns],
        "human_verdicts": {},
    }
    reports = evaluate_suite(suite, {sid: transcript}, clinic)
    assert reports[sid].status is not Status.PASS
