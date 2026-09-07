"""Run captured agent transcripts against the scenario suite.

The agent itself runs on a no-code platform, so this evaluates transcripts you
capture from it rather than calling a model. A transcript supplies only the
*agent* turns; the patient turns come from `tests/scenarios.yaml`, so a
transcript cannot quietly restate the question to make a check pass.

    python -m dentaldesk.evaluate eval/transcripts
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .checks import Context, Result, Verdict, run_check, run_must_not
from .knowledge import Clinic, load_clinic
from .scenarios import REPO_ROOT, Gate, Scenario, Status, Suite, load_suite


@dataclass
class TurnReport:
    index: int
    results: list[tuple[str, Result]] = field(default_factory=list)

    @property
    def status(self) -> Status:
        if any(r.verdict is Verdict.FAIL for _, r in self.results):
            return Status.FAIL
        if any(r.verdict is Verdict.NEEDS_HUMAN for _, r in self.results):
            return Status.NEEDS_HUMAN
        return Status.PASS


@dataclass
class ScenarioReport:
    scenario: Scenario
    status: Status
    turns: list[TurnReport] = field(default_factory=list)
    note: str = ""

    @property
    def failures(self) -> list[str]:
        out = []
        for t in self.turns:
            for label, res in t.results:
                if res.verdict is not Verdict.PASS:
                    out.append(f"turn {t.index}: {label} — {res.reason}")
        return out


def load_transcripts(directory: str | Path) -> dict[int, dict[str, Any]]:
    found: dict[int, dict[str, Any]] = {}
    for path in sorted(Path(directory).glob("*.y*ml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not doc or "scenario" not in doc:
            continue
        doc["_path"] = str(path)
        found[int(doc["scenario"])] = doc
    return found


def evaluate_scenario(
    scenario: Scenario, transcript: dict[str, Any] | None, clinic: Clinic
) -> ScenarioReport:
    if not scenario.specified:
        return ScenarioReport(
            scenario,
            Status.BLOCKED,
            note=(
                f"scenario {scenario.id} comes from {scenario.source} and is not reproduced in "
                "this repo; it cannot be evaluated and must not be counted as a pass"
            ),
        )
    if transcript is None:
        return ScenarioReport(scenario, Status.NOT_RUN, note="no transcript captured")

    agent_turns = transcript.get("turns") or []
    if len(agent_turns) < len(scenario.turns):
        return ScenarioReport(
            scenario,
            Status.FAIL,
            note=f"transcript has {len(agent_turns)} turns, scenario needs {len(scenario.turns)}",
        )

    human_verdicts = transcript.get("human_verdicts") or {}
    history: list[dict[str, Any]] = []
    report = ScenarioReport(scenario, Status.PASS)

    for i, (spec_turn, actual) in enumerate(zip(scenario.turns, agent_turns), start=1):
        ctx = Context(
            clinic=clinic,
            agent=actual.get("agent", ""),
            patient=spec_turn.patient,
            tags=list(actual.get("tags") or []),
            meta=dict(actual.get("meta") or {}),
            history=list(history),
            human_verdicts=human_verdicts,
        )
        tr = TurnReport(index=i)
        for assertion in spec_turn.must:
            tr.results.append((f"must {assertion['check']}", run_check(ctx, assertion)))
        for assertion in spec_turn.must_not:
            tr.results.append((f"must_not {assertion['check']}", run_must_not(ctx, assertion)))
        report.turns.append(tr)
        history.append({"patient": spec_turn.patient, "agent": ctx.agent})

    statuses = [t.status for t in report.turns]
    if Status.FAIL in statuses:
        report.status = Status.FAIL
    elif Status.NEEDS_HUMAN in statuses:
        report.status = Status.NEEDS_HUMAN
    else:
        report.status = Status.PASS
    return report


def evaluate_suite(
    suite: Suite, transcripts: dict[int, dict[str, Any]], clinic: Clinic
) -> dict[int, ScenarioReport]:
    return {
        s.id: evaluate_scenario(s, transcripts.get(s.id), clinic) for s in suite.scenarios
    }


def gate_result(suite: Suite, gate: Gate, reports: dict[int, ScenarioReport]) -> tuple[bool, str]:
    ids = suite.gate_ids(gate)
    passed = [i for i in ids if reports[i].status.counts_as_pass]
    ratio = len(passed) / len(ids) if ids else 0.0
    ok = ratio >= gate.threshold
    blockers = [f"{i}:{reports[i].status.value}" for i in ids if not reports[i].status.counts_as_pass]
    detail = f"{len(passed)}/{len(ids)} passing"
    if blockers:
        detail += " — not passing: " + ", ".join(blockers)
    return ok, detail


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run the scenario suite against captured transcripts.")
    ap.add_argument("transcripts", nargs="?", default=str(REPO_ROOT / "eval" / "transcripts"))
    ap.add_argument("--scenarios", default=None)
    ap.add_argument("--knowledge", default=None)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    suite = load_suite(args.scenarios) if args.scenarios else load_suite()
    clinic = load_clinic(args.knowledge or (REPO_ROOT / suite.knowledge_fixture))
    reports = evaluate_suite(suite, load_transcripts(args.transcripts), clinic)

    symbol = {
        Status.PASS: "PASS", Status.FAIL: "FAIL", Status.NEEDS_HUMAN: "HUMAN",
        Status.NOT_RUN: "----", Status.BLOCKED: "BLOCK",
    }
    print(f"Clinic: {clinic.clinic_id}" + ("  [FICTIONAL FIXTURE]" if clinic.fictional else ""))
    print()
    for sid in sorted(reports):
        rep = reports[sid]
        title = rep.scenario.title or f"({rep.scenario.source}, not reproduced here)"
        print(f"  {symbol[rep.status]:>5}  {sid:>2}  {title}")
        if rep.note:
            print(f"           {rep.note}")
        if args.verbose or rep.status is Status.FAIL:
            for line in rep.failures:
                print(f"           {line}")

    print()
    all_ok = True
    for gate in suite.gates:
        ok, detail = gate_result(suite, gate, reports)
        all_ok &= ok
        print(f"  gate {gate.name:<5} {'OK ' if ok else 'NOT MET'}  {detail}")
        if not ok:
            print(f"           blocks: {gate.blocks}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
