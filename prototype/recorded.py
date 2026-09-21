"""Loader for Recorded Transcript evaluation scenarios.

Recorded scenarios intentionally do not contain a Golden Graph.  Their
annotations are semantic evaluation targets for a provider-backed Analyzer;
the canonical Graph is still produced only by the existing Event Stream and
Materializer path.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import FixtureError


@dataclass(frozen=True)
class RecordedScenario:
    scenario_id: str
    name: str
    path: Path
    session: dict[str, Any]
    evidence: list[dict[str, Any]]
    utterances: list[dict[str, Any]]
    annotations: dict[str, Any]

    @property
    def display_name(self) -> str:
        return f"{self.scenario_id} · {self.name}"


class RecordedScenarioLoader:
    """Discover and validate the small, human-authored spike dataset."""

    def __init__(self, scenarios_dir: Path | str) -> None:
        self.scenarios_dir = Path(scenarios_dir)

    def discover(self) -> list[Path]:
        if not self.scenarios_dir.is_dir():
            # The public package may intentionally omit the optional recorded
            # evaluation dataset. Fixture-based development remains usable.
            return []
        return sorted(
            path
            for path in self.scenarios_dir.iterdir()
            if path.is_dir() and path.name.startswith("scenario-")
        )

    def load_all(self) -> list[RecordedScenario]:
        return [self.load(path) for path in self.discover()]

    @staticmethod
    def _read_json(path: Path) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise FixtureError("scenario_json_invalid", f"Unable to read {path}: {exc}", path=str(path)) from exc

    def load(self, path: Path | str) -> RecordedScenario:
        scenario_path = Path(path)
        transcript = self._read_json(scenario_path / "transcript.json")
        annotations = self._read_json(scenario_path / "annotations.json")
        if not isinstance(transcript, dict) or not isinstance(annotations, dict):
            raise FixtureError("scenario_invalid", f"Scenario {scenario_path.name} must contain JSON objects")
        session = transcript.get("session")
        evidence = transcript.get("evidence")
        utterances = transcript.get("utterances")
        if not isinstance(session, dict) or not isinstance(evidence, list) or not isinstance(utterances, list):
            raise FixtureError("scenario_invalid", f"Scenario {scenario_path.name} has an invalid transcript shape")
        session_id = session.get("id")
        if not isinstance(session_id, str) or not session_id:
            raise FixtureError("scenario_invalid", f"Scenario {scenario_path.name} is missing session.id")
        evidence_ids = {item.get("id") for item in evidence if isinstance(item, dict)}
        evidence_sequences = [item.get("sequence") for item in evidence]
        utterance_sequences = [item.get("sequence") for item in utterances]
        if evidence_sequences != list(range(1, len(evidence) + 1)):
            raise FixtureError("scenario_sequence_invalid", f"Evidence sequence is not contiguous in {scenario_path.name}")
        if utterance_sequences != list(range(1, len(utterances) + 1)):
            raise FixtureError("scenario_sequence_invalid", f"Utterance sequence is not contiguous in {scenario_path.name}")
        for item in evidence:
            if item.get("session_id") != session_id or not item.get("text"):
                raise FixtureError("scenario_evidence_invalid", f"Invalid Evidence in {scenario_path.name}")
        for item in utterances:
            if item.get("session_id") != session_id or not item.get("text"):
                raise FixtureError("scenario_utterance_invalid", f"Invalid Utterance in {scenario_path.name}")
            if not set(item.get("evidence_ids", [])) <= evidence_ids:
                raise FixtureError("scenario_reference_invalid", f"Utterance {item.get('id')} references missing Evidence")
        scenario_id = scenario_path.name
        return RecordedScenario(
            scenario_id=scenario_id,
            name=str(session.get("title") or scenario_id),
            path=scenario_path,
            session=copy.deepcopy(session),
            evidence=copy.deepcopy(evidence),
            utterances=copy.deepcopy(utterances),
            annotations=copy.deepcopy(annotations),
        )
