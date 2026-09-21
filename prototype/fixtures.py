"""Discovery and contract validation for Evaluation Fixtures."""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .errors import FixtureError, PrototypeError
from .schema import SchemaValidator


_FIXTURE_DIRECTORY = re.compile(r"^(?P<id>\d{3})-(?P<name>.+)$")
_REQUIRED_FILES = ("README.md", "evidence.json", "events.json", "expected-final-graph.json")


@dataclass(frozen=True)
class Fixture:
    """A valid base replay plus optional invalid-event cases."""

    fixture_id: str
    name: str
    path: Path
    evidence: list[dict[str, Any]]
    events: list[dict[str, Any]]
    expected: dict[str, Any]
    invalid_cases: list[dict[str, Any]]

    @property
    def has_invalid_cases(self) -> bool:
        return bool(self.invalid_cases)

    @property
    def status(self) -> str:
        return "valid-base-with-invalid-cases" if self.has_invalid_cases else "valid-base"


class FixtureLoader:
    """Load fixtures and validate them against the canonical schemas."""

    def __init__(
        self,
        fixtures_dir: Path | str,
        schema_validator: SchemaValidator,
    ) -> None:
        self.fixtures_dir = Path(fixtures_dir)
        self.schema_validator = schema_validator

    def discover(self) -> list[Path]:
        if not self.fixtures_dir.is_dir():
            raise FixtureError(
                "fixture_not_found",
                f"Fixture directory does not exist: {self.fixtures_dir}",
                path=str(self.fixtures_dir),
            )
        paths = []
        for path in self.fixtures_dir.iterdir():
            if path.is_dir() and _FIXTURE_DIRECTORY.match(path.name):
                paths.append(path)
        return sorted(paths, key=lambda path: path.name)

    @staticmethod
    def _read_json(path: Path) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise FixtureError(
                "fixture_file_missing",
                f"Required fixture file is missing: {path}",
                path=str(path),
            ) from exc
        except json.JSONDecodeError as exc:
            raise FixtureError(
                "fixture_json_invalid",
                f"Invalid JSON in {path}: {exc.msg}",
                path=str(path),
                details={"line": exc.lineno, "column": exc.colno},
            ) from exc

    def load_all(self) -> list[Fixture]:
        return [self.load(path) for path in self.discover()]

    def load(self, path: Path | str) -> Fixture:
        fixture_path = Path(path)
        match = _FIXTURE_DIRECTORY.match(fixture_path.name)
        if match is None:
            raise FixtureError(
                "fixture_name_invalid",
                f"Fixture directory must use NNN-name format: {fixture_path}",
                path=str(fixture_path),
            )
        for filename in _REQUIRED_FILES:
            if not (fixture_path / filename).is_file():
                raise FixtureError(
                    "fixture_file_missing",
                    f"Fixture {fixture_path.name} is missing {filename}",
                    path=str(fixture_path / filename),
                )

        evidence = self._read_json(fixture_path / "evidence.json")
        events = self._read_json(fixture_path / "events.json")
        expected = self._read_json(fixture_path / "expected-final-graph.json")
        invalid_path = fixture_path / "invalid-cases.json"
        invalid_cases = self._read_json(invalid_path) if invalid_path.exists() else []

        self._validate_base(
            fixture_path,
            evidence=evidence,
            events=events,
            expected=expected,
        )
        if not isinstance(invalid_cases, list):
            raise FixtureError(
                "fixture_invalid_cases_invalid",
                "invalid-cases.json must contain an array",
                path=str(invalid_path),
            )

        return Fixture(
            fixture_id=match.group("id"),
            name=match.group("name"),
            path=fixture_path,
            evidence=copy.deepcopy(evidence),
            events=copy.deepcopy(events),
            expected=copy.deepcopy(expected),
            invalid_cases=copy.deepcopy(invalid_cases),
        )

    def _validate_base(
        self,
        fixture_path: Path,
        *,
        evidence: Any,
        events: Any,
        expected: Any,
    ) -> None:
        if not isinstance(evidence, list):
            raise FixtureError(
                "fixture_evidence_invalid",
                "evidence.json must contain an array",
                path=str(fixture_path / "evidence.json"),
            )
        if not isinstance(events, list):
            raise FixtureError(
                "fixture_events_invalid",
                "events.json must contain an array",
                path=str(fixture_path / "events.json"),
            )
        if not isinstance(expected, dict):
            raise FixtureError(
                "fixture_expected_invalid",
                "expected-final-graph.json must contain an object",
                path=str(fixture_path / "expected-final-graph.json"),
            )

        try:
            self.schema_validator.validate_domain(expected)
        except PrototypeError as exc:
            raise FixtureError(
                exc.code,
                f"{fixture_path.name}: {exc.message}",
                path=exc.path,
                details=exc.details,
            ) from exc

        session_id = expected["session"]["id"]
        if expected["evidence"] != evidence:
            raise FixtureError(
                "evidence_mismatch",
                "evidence.json must equal the expected domain evidence list",
                path=str(fixture_path),
            )
        self._validate_evidence(evidence, session_id, fixture_path)
        self._validate_utterances(expected["utterances"], session_id, evidence, fixture_path)
        self._validate_events(events, session_id, evidence, fixture_path)
        self._validate_expected_graph(expected, events, evidence, fixture_path)

    @staticmethod
    def _validate_evidence(
        evidence: list[dict[str, Any]],
        session_id: str,
        fixture_path: Path,
    ) -> None:
        ids: set[str] = set()
        sequences: list[int] = []
        for item in evidence:
            if item["session_id"] != session_id:
                raise FixtureError(
                    "session_mismatch",
                    f"Evidence {item.get('id')} belongs to another session",
                    path=str(fixture_path),
                )
            if item["id"] in ids:
                raise FixtureError(
                    "duplicate_evidence_id",
                    f"Duplicate evidence id {item['id']}",
                    path=str(fixture_path),
                )
            ids.add(item["id"])
            sequences.append(item["sequence"])
        if sequences != list(range(1, len(sequences) + 1)):
            raise FixtureError(
                "invalid_evidence_sequence",
                "Evidence sequence must be contiguous starting at 1",
                path=str(fixture_path),
            )

    @staticmethod
    def _validate_utterances(
        utterances: list[dict[str, Any]],
        session_id: str,
        evidence: list[dict[str, Any]],
        fixture_path: Path,
    ) -> None:
        evidence_ids = {item["id"] for item in evidence}
        sequences = []
        for item in utterances:
            if item["session_id"] != session_id:
                raise FixtureError(
                    "session_mismatch",
                    f"Utterance {item.get('id')} belongs to another session",
                    path=str(fixture_path),
                )
            if not set(item["evidence_ids"]).issubset(evidence_ids):
                raise FixtureError(
                    "missing_reference",
                    f"Utterance {item['id']} references missing Evidence",
                    path=str(fixture_path),
                )
            sequences.append(item["sequence"])
        if sequences != list(range(1, len(sequences) + 1)):
            raise FixtureError(
                "invalid_utterance_sequence",
                "Utterance sequence must be contiguous starting at 1",
                path=str(fixture_path),
            )

    def _validate_events(
        self,
        events: list[dict[str, Any]],
        session_id: str,
        evidence: list[dict[str, Any]],
        fixture_path: Path,
    ) -> None:
        evidence_ids = {item["id"] for item in evidence}
        event_ids: set[str] = set()
        sequences: list[int] = []
        for event in events:
            try:
                self.schema_validator.validate_event(event)
            except PrototypeError as exc:
                raise FixtureError(
                    exc.code,
                    f"{fixture_path.name}: {exc.message}",
                    path=exc.path,
                    details=exc.details,
                ) from exc
            if event["session_id"] != session_id:
                raise FixtureError(
                    "session_mismatch",
                    f"Event {event['event_id']} belongs to another session",
                    path=str(fixture_path),
                )
            if event["event_id"] in event_ids:
                raise FixtureError(
                    "duplicate_event_id",
                    f"Duplicate event id {event['event_id']}",
                    path=str(fixture_path),
                )
            event_ids.add(event["event_id"])
            sequences.append(event["sequence"])
            if not set(event["source_evidence_ids"]).issubset(evidence_ids):
                raise FixtureError(
                    "missing_reference",
                    f"Event {event['event_id']} references missing Evidence",
                    path=str(fixture_path),
                )
            if event["actor"] == "human" and event.get("expected_revision") != event["sequence"] - 1:
                raise FixtureError(
                    "revision_mismatch",
                    f"Human Event {event['event_id']} must expect revision {event['sequence'] - 1}",
                    path=str(fixture_path),
                )
        if sequences != list(range(1, len(sequences) + 1)):
            raise FixtureError(
                "invalid_event_sequence",
                "Base Event sequence must be contiguous starting at 1",
                path=str(fixture_path),
            )

    @staticmethod
    def _validate_expected_graph(
        expected: dict[str, Any],
        events: list[dict[str, Any]],
        evidence: list[dict[str, Any]],
        fixture_path: Path,
    ) -> None:
        graph = expected["graph"]
        event_ids = {event["event_id"] for event in events}
        evidence_ids = {item["id"] for item in evidence}
        if graph["session_id"] != expected["session"]["id"]:
            raise FixtureError("session_mismatch", "Graph and Session IDs differ", path=str(fixture_path))
        if graph["revision"] != len(events) or graph["last_event_sequence"] != len(events):
            raise FixtureError(
                "revision_mismatch",
                "Expected Graph revision must equal the base Event count",
                path=str(fixture_path),
            )
        if expected["session"]["graph_revision"] != graph["revision"]:
            raise FixtureError(
                "revision_mismatch",
                "Session graph_revision must equal Graph revision",
                path=str(fixture_path),
            )
        node_ids = {node["id"] for node in graph["nodes"]}
        for node in graph["nodes"]:
            if not set(node["source_event_ids"]).issubset(event_ids):
                raise FixtureError(
                    "missing_reference",
                    f"Node {node['id']} references missing Event",
                    path=str(fixture_path),
                )
            if not set(node["evidence_ids"]).issubset(evidence_ids):
                raise FixtureError(
                    "missing_reference",
                    f"Node {node['id']} references missing Evidence",
                    path=str(fixture_path),
                )
        for edge in graph["edges"]:
            if edge["source_node_id"] not in node_ids or edge["target_node_id"] not in node_ids:
                raise FixtureError(
                    "missing_reference",
                    f"Edge {edge['id']} references missing Node",
                    path=str(fixture_path),
                )

