"""Load the scenario suite (spec §9) and compute its gates."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = REPO_ROOT / "tests" / "scenarios.yaml"


class Status(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    NEEDS_HUMAN = "needs_human"
    NOT_RUN = "not_run"
    BLOCKED = "blocked"  # specified nowhere we can read — cannot be evaluated

    @property
    def counts_as_pass(self) -> bool:
        return self is Status.PASS


@dataclass(frozen=True)
class Turn:
    patient: str
    must: tuple[dict[str, Any], ...]
    must_not: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class Scenario:
    id: int
    status: str
    source: str
    channel: str
    title: str | None = None
    spec_quote: str | None = None
    notes: str | None = None
    requires_audio: bool = False
    turns: tuple[Turn, ...] = ()

    @property
    def specified(self) -> bool:
        return self.status == "specified"


@dataclass(frozen=True)
class Gate:
    name: str
    lo: int
    hi: int
    threshold: float
    blocks: str

    def covers(self, scenario_id: int) -> bool:
        return self.lo <= scenario_id <= self.hi


@dataclass(frozen=True)
class Suite:
    scenarios: tuple[Scenario, ...]
    gates: tuple[Gate, ...]
    knowledge_fixture: str

    def by_id(self, scenario_id: int) -> Scenario:
        for s in self.scenarios:
            if s.id == scenario_id:
                return s
        raise KeyError(scenario_id)

    def gate_ids(self, gate: Gate) -> list[int]:
        return [s.id for s in self.scenarios if gate.covers(s.id)]


def load_suite(path: str | Path = DEFAULT_PATH) -> Suite:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    scenarios = []
    for item in raw["scenarios"]:
        turns = tuple(
            Turn(
                patient=t["patient"],
                must=tuple(t.get("must") or ()),
                must_not=tuple(t.get("must_not") or ()),
            )
            for t in (item.get("turns") or [])
        )
        scenarios.append(
            Scenario(
                id=item["id"],
                status=item.get("status", "specified"),
                source=item.get("source", "unknown"),
                channel=item.get("channel", "both"),
                title=item.get("title"),
                spec_quote=item.get("spec_quote"),
                notes=item.get("notes"),
                requires_audio=bool(item.get("requires_audio")),
                turns=turns,
            )
        )
    gates = tuple(
        Gate(name=name, lo=g["range"][0], hi=g["range"][1], threshold=float(g["threshold"]),
             blocks=g.get("blocks", ""))
        for name, g in (raw.get("gates") or {}).items()
    )
    return Suite(
        scenarios=tuple(sorted(scenarios, key=lambda s: s.id)),
        gates=gates,
        knowledge_fixture=raw.get("knowledge_fixture", ""),
    )
