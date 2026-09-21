"""Application services used by the M4/M5 Prototype UI."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .analyzer import FakeAnalyzer, TranscriptReplaySession
from .commands import CommandSession
from .errors import PrototypeError
from .fixtures import Fixture, FixtureLoader
from .layout import StableLayout, map_projection
from .real_analyzer import RealAnalyzer
from .recorded import RecordedScenario, RecordedScenarioLoader
from .replay import ReplayRunner
from .schema import SchemaValidator
from .ui_scenarios import build_large_map_fixture, build_pilot_shared_fixture


@dataclass
class _Runtime:
    fixture: Any
    session: Any
    layout: StableLayout
    mode: str


class DeveloperPrototypeApp:
    """Small in-memory application boundary; no persistence or production API."""

    def __init__(self, fixtures_dir: Path | str, schema_dir: Path | str) -> None:
        self.validator = SchemaValidator(schema_dir)
        self.loader = FixtureLoader(fixtures_dir, self.validator)
        self.replay_runner = ReplayRunner(self.validator)
        self.handler_sessions: dict[str, _Runtime] = {}
        self.fixtures = {fixture.fixture_id: fixture for fixture in self.loader.load_all()}
        self.recorded_loader = RecordedScenarioLoader(Path(fixtures_dir).parent / "real-analyzer")
        self.recorded_scenarios = {
            scenario.scenario_id: scenario
            for scenario in self.recorded_loader.load_all()
        }
        # Developer-only presentation stress scenario; it is not part of the
        # 12 Golden Fixtures and does not alter the canonical domain contract.
        large_map = build_large_map_fixture()
        self.fixtures[large_map.fixture_id] = large_map
        pilot_shared = build_pilot_shared_fixture()
        self.fixtures[pilot_shared.fixture_id] = pilot_shared

    def list_fixtures(self) -> list[dict[str, Any]]:
        fixtures = [
            {
                "fixture_id": fixture.fixture_id,
                "name": fixture.name,
                "status": fixture.status,
                "has_invalid_cases": fixture.has_invalid_cases,
                "transcript_replay": True,
                "kind": "fixture",
            }
            for fixture in self.fixtures.values()
        ]
        fixtures.extend(
            {
                "fixture_id": scenario.scenario_id,
                "name": scenario.name,
                "status": "recorded-evaluation",
                "has_invalid_cases": False,
                "transcript_replay": True,
                "kind": "recorded",
            }
            for scenario in self.recorded_scenarios.values()
        )
        return fixtures

    def reset_session(
        self,
        fixture_id: str,
        through_sequence: int | None = None,
        *,
        mode: str = "events",
    ) -> dict[str, Any]:
        if mode in {"real", "recorded_fake"}:
            scenario = self._scenario(fixture_id)
            analyzer = (
                RealAnalyzer.from_environment(
                    schema_validator=self.validator,
                    meeting_goal=scenario.session.get("goal"),
                )
                if mode == "real"
                else FakeAnalyzer()
            )
            session = TranscriptReplaySession.from_documents(
                session=scenario.session,
                evidence=scenario.evidence,
                utterances=scenario.utterances,
                replay_runner=self.replay_runner,
                analyzer=analyzer,
                replay_mode=mode,
            )
            if through_sequence is not None:
                if through_sequence < 0:
                    raise PrototypeError("request_invalid", "Transcript sequence must be non-negative")
                for _ in range(min(through_sequence, len(session.utterances))):
                    session.step()
            runtime_document: Any = scenario
        else:
            fixture = self._fixture(fixture_id)
            runtime_document = fixture
        if mode == "transcript":
            session = TranscriptReplaySession.from_fixture(fixture, self.replay_runner)
            if through_sequence is not None:
                if through_sequence < 0:
                    raise PrototypeError("request_invalid", "Transcript sequence must be non-negative")
                for _ in range(min(through_sequence, len(session.utterances))):
                    session.step()
        elif mode == "events":
            session = CommandSession.from_fixture(
                fixture,
                self.replay_runner,
                through_sequence=through_sequence,
            )
        elif mode not in {"real", "recorded_fake"}:
            raise PrototypeError("request_invalid", f"Unsupported replay mode: {mode}")
        layout = StableLayout()
        layout.project(session.result.state["graph"], session.result.events)
        self.handler_sessions[fixture_id] = _Runtime(
            fixture=runtime_document,
            session=session,
            layout=layout,
            mode=mode,
        )
        return self.session_snapshot(fixture_id)

    def session_snapshot(self, fixture_id: str) -> dict[str, Any]:
        runtime = self.handler_sessions.get(fixture_id)
        if runtime is None:
            self.reset_session(fixture_id)
            runtime = self.handler_sessions[fixture_id]
        result = runtime.session.result
        current_events = list(result.events)
        if runtime.mode in {"transcript", "real", "recorded_fake"}:
            replay = runtime.session.replay_metadata()
        else:
            fixture_events = list(runtime.fixture.events)
            is_fixture_prefix = current_events == fixture_events[: len(current_events)]
            current_sequence = result.state["graph"]["last_event_sequence"]
            total_sequence = fixture_events[-1]["sequence"] if fixture_events else 0
            replay = {
                "enabled": is_fixture_prefix,
                "mode": "events",
                "current_sequence": current_sequence,
                "total_sequence": total_sequence,
                "complete": is_fixture_prefix and current_sequence >= total_sequence,
            }
        snapshot = {
            "fixture_id": fixture_id,
            "fixture_name": runtime.fixture.name,
            "state": copy.deepcopy(result.state),
            "events": copy.deepcopy(list(result.events)),
            "map": copy.deepcopy(map_projection(result.state, result.events, runtime.layout)),
            "replay": replay,
            "can_undo": runtime.session.can_undo(),
            "undo_target_event_id": result.events[-1]["event_id"] if runtime.session.can_undo() else None,
        }
        if runtime.mode in {"transcript", "real", "recorded_fake"}:
            snapshot["transcript"] = {
                "current_utterance": copy.deepcopy(runtime.session.current_utterance),
                "analysis_status": runtime.session.analysis_status,
                "analysis_errors": copy.deepcopy(runtime.session.analysis_errors),
            }
            snapshot["analyzer_runs"] = copy.deepcopy(getattr(runtime.session.analyzer, "run_history", []))
        return snapshot

    def execute_command(self, fixture_id: str, command: dict[str, Any]) -> dict[str, Any]:
        runtime = self.handler_sessions.get(fixture_id)
        if runtime is None:
            self.reset_session(fixture_id)
            runtime = self.handler_sessions[fixture_id]
        result = runtime.session.execute(command)
        runtime.layout.project(result.result.state["graph"], result.result.events)
        snapshot = self.session_snapshot(fixture_id)
        snapshot["applied_event"] = copy.deepcopy(result.event)
        return snapshot

    def step_transcript(self, fixture_id: str) -> dict[str, Any]:
        runtime = self.handler_sessions.get(fixture_id)
        if runtime is None or runtime.mode not in {"transcript", "real", "recorded_fake"}:
            self.reset_session(fixture_id, mode="transcript")
            runtime = self.handler_sessions[fixture_id]
        runtime.session.step()
        runtime.layout.project(runtime.session.result.state["graph"], runtime.session.result.events)
        return self.session_snapshot(fixture_id)

    def _fixture(self, fixture_id: str) -> Fixture:
        try:
            return self.fixtures[fixture_id]
        except KeyError as exc:
            raise PrototypeError("fixture_not_found", f"Unknown Fixture: {fixture_id}") from exc

    def _scenario(self, scenario_id: str) -> RecordedScenario:
        try:
            return self.recorded_scenarios[scenario_id]
        except KeyError as exc:
            raise PrototypeError("scenario_not_found", f"Unknown Recorded Scenario: {scenario_id}") from exc
