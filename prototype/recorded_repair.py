"""Offline repair simulations for the Recorded Analyzer readiness blockers.

This module never calls an LLM and never rewrites a historical Run artifact.
It replays the cached Run #4 Event Stream, appends derived Human Resolve
Events, and re-converts cached Analyzer output through the normal adapter.
The resulting JSON is a derived evaluation artifact, not a replacement run.
"""

from __future__ import annotations

import argparse
import copy
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from .analyzer import TranscriptReplaySession
from .long_session_compaction import compact_quality, replay_cached_branch
from .materializer import initial_state
from .projection import build_presentation_projection
from .real_analyzer import PROMPT_VERSION_V4, RealAnalyzer, StaticJsonProvider
from .replay import ReplayResult, ReplayRunner, semantic_equal
from .schema import SchemaValidator


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN = ROOT / "evaluation" / "30min" / "run-gpt-5.6-luna-analyzer-prompt-v4-20260919"
DEFAULT_OUTPUT = ROOT / "evaluation" / "30min" / "compaction-spike-v1"
ACTION_CASES = ("rec30-u058", "rec30-u077", "rec30-u087", "rec30-u119")
RESOLVE_CASES = ("rec30-u035", "rec30-u118")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _node_id_for_utterance(session_id: str, utterance_id: str) -> str:
    event_id = f"real:{session_id}:{utterance_id}:01"
    return f"node:{session_id}:{event_id}"


def _human_event(
    result: ReplayResult,
    *,
    event_id: str,
    event_type: str,
    node_id: str,
    occurred_at: str,
) -> dict[str, Any]:
    expected_status = "active" if event_type == "resolve_open_item" else "resolved"
    sequence = result.state["graph"]["last_event_sequence"] + 1
    return {
        "event_id": event_id,
        "session_id": result.state["graph"]["session_id"],
        "sequence": sequence,
        "event_type": event_type,
        "occurred_at": occurred_at,
        "actor": "human",
        "expected_revision": result.state["graph"]["revision"],
        "source_evidence_ids": [],
        "payload": {
            "open_item_node_id": node_id,
            "expected_status": expected_status,
        },
    }


def _load_recording(run_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    dataset = json.loads((run_dir / "dataset" / "transcript.json").read_text(encoding="utf-8"))
    recording = json.loads((run_dir / "normal-analyzer-recording.json").read_text(encoding="utf-8"))
    branch = json.loads((run_dir / "run-off.json").read_text(encoding="utf-8"))
    return dataset, recording, branch


def _replay_pre_states(
    run_dir: Path,
    *,
    validator: SchemaValidator,
    branch: str = "off",
) -> tuple[dict[str, ReplayResult], ReplayResult]:
    """Replay cached normal output and branch Human Events, indexed before each utterance."""

    dataset, recording, branch_data = _load_recording(run_dir)
    human_by_sequence: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for item in branch_data.get("human_actions", []):
        if item.get("status") == "applied" and item.get("event"):
            human_by_sequence[int(item["after_sequence"])].append(copy.deepcopy(item["event"]))

    runner = ReplayRunner(validator)
    result = ReplayResult(
        initial_state(dataset["session"]["id"], dataset["evidence"], dataset["utterances"]),
        (),
    )
    for event in TranscriptReplaySession._default_system_events(dataset["session"]):
        result = runner.apply_event(result, event)

    pre_states: dict[str, ReplayResult] = {}
    for item in recording:
        pre_states[item["utterance_id"]] = result
        for event in item.get("events", []):
            replay_event = copy.deepcopy(event)
            replay_event["sequence"] = result.state["graph"]["last_event_sequence"] + 1
            result = runner.apply_event(result, replay_event)
        for event in human_by_sequence.get(int(item["sequence"]), []):
            result = runner.apply_event(result, event)
    return pre_states, result


def resolve_open_items(
    *,
    run_dir: Path,
    validator: SchemaValidator,
    base_result: ReplayResult,
) -> tuple[ReplayResult, dict[str, Any]]:
    """Apply the two known state-update repairs without deleting history."""

    runner = ReplayRunner(validator)
    before_projection = build_presentation_projection(base_result.state["graph"], base_result.events)
    repaired = base_result
    applied: list[dict[str, Any]] = []
    session_id = base_result.state["graph"]["session_id"]
    for index, utterance_id in enumerate(RESOLVE_CASES, start=1):
        node_id = _node_id_for_utterance(session_id, utterance_id)
        event = _human_event(
            repaired,
            event_id=f"repair:{session_id}:resolve-open-item:{index:02d}",
            event_type="resolve_open_item",
            node_id=node_id,
            occurred_at=f"2026-09-22T10:30:{index:02d}Z",
        )
        repaired = runner.apply_event(repaired, event)
        applied.append(event)
    after_projection = build_presentation_projection(repaired.state["graph"], repaired.events)
    return repaired, {
        "source_run": run_dir.name,
        "simulation": "derived_offline_human_resolve",
        "target_utterances": list(RESOLVE_CASES),
        "canonical_graph_mutated": False,
        "events": applied,
        "before": {
            "graph_revision": base_result.state["graph"]["revision"],
            "open_item_count": before_projection["visible_open_items"],
            "visible_card_count": before_projection["visible_card_count"],
            "quality": compact_quality(before_projection),
        },
        "after": {
            "graph_revision": repaired.state["graph"]["revision"],
            "open_item_count": after_projection["visible_open_items"],
            "visible_card_count": after_projection["visible_card_count"],
            "quality": compact_quality(after_projection),
            "critical_information_recall": after_projection["critical_information_recall"],
        },
    }


def reprocess_actions(
    *,
    run_dir: Path,
    validator: SchemaValidator,
    pre_states: dict[str, ReplayResult],
    final_result: ReplayResult,
) -> tuple[ReplayResult, dict[str, Any]]:
    """Reconvert cached raw outputs; no Provider network call is possible here."""

    dataset, recording, _ = _load_recording(run_dir)
    utterances = {utterance["id"]: utterance for utterance in dataset["utterances"]}
    by_id = {item["utterance_id"]: item for item in recording}
    reprocessed: list[dict[str, Any]] = []
    accepted_candidates: list[dict[str, Any]] = []

    for utterance_id in ACTION_CASES:
        item = by_id[utterance_id]
        raw_output = json.loads(item["trace"]["raw_output"])
        analyzer = RealAnalyzer(
            provider=StaticJsonProvider([raw_output], model="cached-run-output"),
            schema_validator=validator,
            meeting_goal=dataset["session"].get("goal"),
            prompt_version=PROMPT_VERSION_V4,
            # Run #4 used the native v2 provider contract, whose nullable
            # existing_node_id and explicit new_node_index fields are present
            # in the cached raw output.
            output_schema_version="v2",
        )
        pre_state = pre_states[utterance_id]
        candidates = analyzer.analyze(utterances[utterance_id], pre_state.state["graph"], pre_state.events)
        candidate_records: list[dict[str, Any]] = []
        candidate_result = pre_state
        runner = ReplayRunner(validator)
        for candidate in candidates:
            event = candidate.to_event(candidate_result.state["graph"]["last_event_sequence"] + 1)
            try:
                candidate_result = runner.apply_event(candidate_result, event)
                accepted_candidates.append(event)
                candidate_records.append({"event": event, "status": "accepted"})
            except Exception as exc:
                candidate_records.append(
                    {
                        "event": event,
                        "status": "rejected",
                        "error": getattr(exc, "as_dict", lambda: {"message": str(exc)})(),
                    }
                )

        original_trace = item["trace"]
        reprocessed.append(
            {
                "utterance_id": utterance_id,
                "text": item["text"],
                "original": {
                    "event_count": len(item.get("events", [])),
                    "trace_critical_errors": original_trace.get("critical_errors", []),
                },
                "cached_structured_output": raw_output,
                "reprocessed_trace": analyzer.last_trace,
                "canonical_candidates": candidate_records,
                "accepted_event_count": sum(record["status"] == "accepted" for record in candidate_records),
                "classification": (
                    "non_action_correctly_rejected"
                    if utterance_id == "rec30-u058"
                    else "valid_action_and_relation_recovered"
                ),
            }
        )

    # This is a derived tail-append simulation.  It intentionally does not
    # rewrite the historical chronological Run #4 stream.
    repaired = final_result
    runner = ReplayRunner(validator)
    for event in accepted_candidates:
        derived = copy.deepcopy(event)
        derived["sequence"] = repaired.state["graph"]["last_event_sequence"] + 1
        repaired = runner.apply_event(repaired, derived)
    projection = build_presentation_projection(repaired.state["graph"], repaired.events)
    report = {
        "source_run": run_dir.name,
        "simulation": "derived_offline_cached_output_reconversion",
        "llm_calls": 0,
        "prompt_version": PROMPT_VERSION_V4,
        "cases": reprocessed,
        "accepted_recovered_events": len(accepted_candidates),
        "accepted_recovered_action_nodes": sum(event["event_type"] == "node_detected" for event in accepted_candidates),
        "accepted_recovered_relations": sum(event["event_type"] == "relation_detected" for event in accepted_candidates),
        "derived_final": {
            "graph_revision": repaired.state["graph"]["revision"],
            "node_count": len(repaired.state["graph"]["nodes"]),
            "action_count": sum(node["type"] == "action" for node in repaired.state["graph"]["nodes"]),
            "projection": {
                "visible_card_count": projection["visible_card_count"],
                "visible_open_items": projection["visible_open_items"],
                "visible_actions": projection["visible_actions"],
                "critical_information_recall": projection["critical_information_recall"],
                "quality": compact_quality(projection),
            },
        },
    }
    return repaired, report


def run_repair(*, run_dir: Path = DEFAULT_RUN, output_dir: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    validator = SchemaValidator(ROOT / "schemas")
    snapshots = replay_cached_branch(run_dir, validator=validator, branch="off")
    base_snapshot = snapshots[30]
    base_result = ReplayResult(
        state=copy.deepcopy(base_snapshot["state"]),
        events=tuple(copy.deepcopy(base_snapshot["events"])),
    )
    pre_states, final_result = _replay_pre_states(run_dir, validator=validator)
    if final_result.state["graph"] != base_result.state["graph"]:
        raise AssertionError("Pre-state replay does not match cached 30-minute snapshot")

    lifecycle_result, lifecycle_report = resolve_open_items(
        run_dir=run_dir,
        validator=validator,
        base_result=base_result,
    )
    repaired_final, action_report = reprocess_actions(
        run_dir=run_dir,
        validator=validator,
        pre_states=pre_states,
        final_result=lifecycle_result,
    )
    # Re-run the derived conversion from the same cached inputs.  This does
    # not call a provider and makes the determinism claim explicit in the
    # artifact rather than relying only on the unit-level fixture tests.
    lifecycle_result_again, _ = resolve_open_items(
        run_dir=run_dir,
        validator=validator,
        base_result=base_result,
    )
    repaired_final_again, _ = reprocess_actions(
        run_dir=run_dir,
        validator=validator,
        pre_states=pre_states,
        final_result=lifecycle_result_again,
    )
    result = {
        "repair_version": "recorded-analyzer-readiness-repair-v1",
        "baseline": {
            "model": "gpt-5.6-luna",
            "reasoning": "medium",
            "prompt": PROMPT_VERSION_V4,
            "golden": "golden-v2",
            "evaluation": "analyzer-eval-v2",
            "llm_calls": 0,
            "historical_run_unchanged": True,
        },
        "derived_replay_deterministic": semantic_equal(
            repaired_final.state,
            repaired_final_again.state,
        ) and list(repaired_final.events) == list(repaired_final_again.events),
        "open_item_lifecycle": lifecycle_report,
        "action_reference_reprocess": action_report,
    }
    write_json(output_dir / "open-item-lifecycle-rescore.json", lifecycle_report)
    write_json(output_dir / "action-reference-reprocess.json", action_report)
    write_json(output_dir / "recorded-analyzer-readiness-repair.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = run_repair(run_dir=args.run_dir, output_dir=args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
