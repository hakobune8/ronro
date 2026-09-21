"""Run the 30-minute Recorded Discussion product evaluation.

The Real Analyzer is called once to freeze normal Analyzer output.  That
recording is then replayed through two identical branches: Type D OFF and
Type D ON.  This keeps the comparison causal and avoids spending a second
set of LLM calls on an otherwise identical transcript.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from .analyzer import CandidateEvent, TranscriptReplaySession
from .commands import HumanCommandHandler
from .layout import StableLayout, map_projection
from .materializer import initial_state
from .real_analyzer import (
    PROMPT_VERSION_V4,
    RealAnalyzer,
    OpenAICompatibleProvider,
    provider_configuration_summary,
)
from .recorded_30min import DATASET_VERSION, build_golden_annotations, build_recorded_30min_dataset
from .replay import ReplayResult, ReplayRunner
from .schema import SchemaValidator
from .type_d_decision import TypeDDecisionLayer


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "evaluation" / "30min"
SCHEMA_VERSION = "v2"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize(value: str) -> str:
    return re.sub(r"[\s　。、・:：「」『』（）()\-—!?！？]+", "", value).lower()


def copy_as_candidate(event: Mapping[str, Any]) -> CandidateEvent:
    return CandidateEvent(
        event_id=str(event["event_id"]),
        session_id=str(event["session_id"]),
        event_type=str(event["event_type"]),
        occurred_at=str(event["occurred_at"]),
        source_evidence_ids=tuple(str(value) for value in event.get("source_evidence_ids", [])),
        payload=copy.deepcopy(dict(event.get("payload", {}))),
        actor=str(event.get("actor", "analyzer")),
    )


def default_system_events(session: Mapping[str, Any]) -> list[dict[str, Any]]:
    return TranscriptReplaySession._default_system_events(session)


def run_normal_analyzer(
    dataset: Mapping[str, Any],
    *,
    validator: SchemaValidator,
    provider: OpenAICompatibleProvider,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Call RealAnalyzer once and retain accepted normal Events plus traces."""

    runner = ReplayRunner(validator)
    analyzer = RealAnalyzer(
        provider=provider,
        schema_validator=validator,
        meeting_goal=dataset["session"].get("goal"),
        prompt_version=PROMPT_VERSION_V4,
        output_schema_version=SCHEMA_VERSION,
    )
    session = TranscriptReplaySession.from_documents(
        session=dataset["session"],
        evidence=dataset["evidence"],
        utterances=dataset["utterances"],
        replay_runner=runner,
        analyzer=analyzer,
        replay_mode="recorded-real-cache",
    )
    records: list[dict[str, Any]] = []
    for utterance in session.utterances:
        before = len(session.result.events)
        session.step()
        accepted_events = list(session.result.events)[before:]
        records.append(
            {
                "utterance_id": utterance["id"],
                "sequence": utterance["sequence"],
                "text": utterance["text"],
                "events": copy.deepcopy(accepted_events),
                "trace": copy.deepcopy(analyzer.last_trace or {}),
            }
        )
    return records, {
        "provider": provider_configuration_summary(provider),
        "prompt_version": PROMPT_VERSION_V4,
        "schema_version": SCHEMA_VERSION,
        "call_count": len(records),
        "accepted_event_count": len(session.result.events) - 2,
        "validation_failure_count": sum(bool(item["trace"].get("validation_error")) for item in records),
        "provider_failure_count": sum(item["trace"].get("status") == "failed" for item in records),
    }


def event_time(utterance: Mapping[str, Any]) -> str:
    return str(utterance["ended_at"])


def find_node(graph: Mapping[str, Any], label: str, *, node_type: str | None = None) -> dict[str, Any] | None:
    needle = normalize(label)
    candidates = [
        node
        for node in graph.get("nodes", [])
        if node.get("status") != "archived"
        and (node_type is None or node.get("type") == node_type)
        and (needle in normalize(str(node.get("label", ""))) or normalize(str(node.get("label", ""))) in needle)
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda node: (node.get("type") != node_type if node_type else False, node["id"]))[0]


def latest_candidate(graph: Mapping[str, Any]) -> dict[str, Any] | None:
    candidates = [
        node
        for node in graph.get("nodes", [])
        if node.get("type") == "decision" and node.get("status") == "candidate"
    ]
    return candidates[-1] if candidates else None


def execute_human_plan(
    result: ReplayResult,
    plan: Mapping[str, Any],
    *,
    utterance: Mapping[str, Any],
    handler: HumanCommandHandler,
    eligible_decision_ids: set[str] | None = None,
) -> tuple[ReplayResult, dict[str, Any]]:
    command_name = str(plan["command"])
    graph = result.state["graph"]
    target: dict[str, Any] | None = None
    command: dict[str, Any] = {
        "expected_revision": graph["revision"],
        "occurred_at": event_time(utterance),
        "source_evidence_ids": list(utterance.get("evidence_ids", [])),
    }

    if command_name == "confirm_latest_candidate":
        target = latest_candidate(graph)
        if eligible_decision_ids is not None:
            target = next(
                (
                    node
                    for node in reversed(graph.get("nodes", []))
                    if node.get("id") in eligible_decision_ids
                    and node.get("type") == "decision"
                    and node.get("status") == "candidate"
                ),
                None,
            )
        if target is None:
            return result, {"status": "skipped", "command": command_name, "reason": "no_candidate"}
        command.update({"command_type": "confirm_decision", "decision_node_id": target["id"]})
    elif command_name == "revoke_label":
        target = find_node(graph, str(plan.get("target", "")), node_type="decision")
        if target is None or target.get("status") != "confirmed":
            return result, {"status": "skipped", "command": command_name, "reason": "no_confirmed_target"}
        command.update({"command_type": "revoke_decision", "decision_node_id": target["id"]})
    elif command_name in {"park_topic", "restore_topic"}:
        target = find_node(graph, str(plan.get("target", "")), node_type="topic")
        if target is None:
            # Parking is a valid Human Correction for any non-Decision
            # Discussion Node.  The plan names the intended Topic, but a
            # realistic Analyzer may represent a digression as an Option or
            # Idea rather than a Topic.
            target = find_node(graph, str(plan.get("target", "")))
        if target is None:
            return result, {"status": "skipped", "command": command_name, "reason": "topic_not_found"}
        command.update(
            {
                "command_type": "move_to_parking_lot" if command_name == "park_topic" else "restore_from_parking_lot",
                "node_id": target["id"],
            }
        )
    else:
        return result, {"status": "skipped", "command": command_name, "reason": "unsupported_plan"}

    try:
        command_result = handler.handle(result, command)
    except Exception as exc:  # A plan miss is recorded, not allowed to corrupt the branch.
        return result, {
            "status": "error",
            "command": command_name,
            "reason": getattr(exc, "code", "command_failed"),
            "message": str(exc),
            "target_node_id": target.get("id") if target else None,
        }
    return command_result.result, {
        "status": "applied",
        "command": command_name,
        "event": copy.deepcopy(command_result.event),
        "target_node_id": target.get("id") if target else None,
    }


def count_graph(graph: Mapping[str, Any]) -> dict[str, Any]:
    nodes = [node for node in graph.get("nodes", []) if node.get("status") != "archived"]
    topics = [node for node in nodes if node.get("type") == "topic"]
    child_nodes = [node for node in nodes if node.get("type") != "topic"]
    return {
        "topic_count": len(topics),
        "final_node_count": len(nodes),
        "nodes_per_topic": round(len(child_nodes) / len(topics), 4) if topics else 0.0,
        "open_item_count": sum(node.get("type") == "open_item" for node in nodes),
        "action_count": sum(node.get("type") == "action" for node in nodes),
        "candidate_decision_count": sum(node.get("type") == "decision" and node.get("status") == "candidate" for node in nodes),
        "confirmed_decision_count": sum(node.get("type") == "decision" and node.get("status") == "confirmed" for node in nodes),
        "revoked_decision_count": sum(node.get("type") == "decision" and node.get("status") == "revoked" for node in nodes),
        "parking_count": sum(node.get("status") == "parked" for node in graph.get("nodes", [])),
        "relation_count": len(graph.get("edges", [])),
    }


def current_topic_label(graph: Mapping[str, Any]) -> str | None:
    current_id = graph.get("current_topic", {}).get("primary_topic_id")
    for node in graph.get("nodes", []):
        if node.get("id") == current_id:
            return str(node.get("label"))
    return None


def static_quality(snapshot: Mapping[str, Any], *, type_d_false: int, type_d_auto_confirm: int) -> dict[str, Any]:
    """Provide a reviewable static rubric estimate for the shared-display map.

    The values are deliberately labelled as a static review, not participant
    study results.  A later UX study can replace them with human ratings.
    """

    counts = snapshot["counts"]
    topic_count = counts["topic_count"]
    node_count = counts["final_node_count"]
    nodes_per_topic = counts["nodes_per_topic"]
    clarity = 5 if topic_count <= 6 and node_count <= 24 else 4 if topic_count <= 8 and node_count <= 36 else 3 if topic_count <= 10 and node_count <= 50 else 2
    density = 5 if nodes_per_topic <= 3 else 4 if nodes_per_topic <= 5 else 3 if nodes_per_topic <= 7 else 2
    decision_safety = 5 if type_d_false == 0 and type_d_auto_confirm == 0 else 3
    coherence = 5 if snapshot["orphan_non_topic_count"] == 0 else 4 if snapshot["orphan_non_topic_count"] <= 2 else 3
    stability = 5 if snapshot["layout_position_changes"] == 0 else 4
    usefulness = round((clarity + density + decision_safety + coherence + stability) / 5, 2)
    return {
        "clarity": clarity,
        "density": density,
        "decision_safety": decision_safety,
        "topic_coherence": coherence,
        "stability": stability,
        "usefulness": usefulness,
        "rating_source": "static_projection_review",
    }


def snapshot_summary(
    result: ReplayResult,
    layout: StableLayout,
    *,
    events_since_previous: Iterable[dict[str, Any]],
    previous_positions: Mapping[str, Mapping[str, Any]],
    type_d_false: int,
    type_d_auto_confirm: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    projection = map_projection(result.state, result.events, layout)
    counts = count_graph(result.state["graph"])
    positions = projection["positions"]
    changed = 0
    for node_id, before in previous_positions.items():
        after = positions.get(node_id)
        if after and (after.get("x"), after.get("y"), after.get("lane_id")) != (before.get("x"), before.get("y"), before.get("lane_id")):
            changed += 1
    node_ids = {node["id"] for node in result.state["graph"]["nodes"]}
    parent_ids = {
        edge["target_node_id"]
        for edge in result.state["graph"]["edges"]
        if edge["type"] in {"contains", "has_option"}
    }
    orphan_count = sum(
        node.get("type") != "topic" and node.get("status") != "archived" and node.get("id") not in parent_ids
        for node in result.state["graph"]["nodes"]
    )
    summary = {
        "revision": result.state["graph"]["revision"],
        "last_event_sequence": result.state["graph"]["last_event_sequence"],
        "current_topic": current_topic_label(result.state["graph"]),
        "counts": counts,
        "lane_count": len(projection["lanes"]),
        "topic_lane_count": sum(lane["kind"] == "topic" for lane in projection["lanes"]),
        "current_lane_id": projection["current_lane_id"],
        "compact_non_current_lanes": sum(lane["kind"] == "topic" and not lane["current"] for lane in projection["lanes"]),
        "parking_lane_present": any(lane["kind"] == "parking" for lane in projection["lanes"]),
        "recent_flow_count": len(projection["recent_flow"]),
        "layout_position_changes": changed,
        "orphan_non_topic_count": orphan_count,
        "new_event_count": len(list(events_since_previous)),
    }
    summary["quality"] = static_quality(summary, type_d_false=type_d_false, type_d_auto_confirm=type_d_auto_confirm)
    return summary, projection


def run_branch(
    dataset: Mapping[str, Any],
    golden: Mapping[str, Any],
    normal_records: list[dict[str, Any]],
    *,
    validator: SchemaValidator,
    type_d_enabled: bool,
) -> dict[str, Any]:
    runner = ReplayRunner(validator)
    result = ReplayResult(initial_state(dataset["session"]["id"], dataset["evidence"], dataset["utterances"]), ())
    for system_event in default_system_events(dataset["session"]):
        result = runner.apply_event(result, system_event)

    type_d_layer = TypeDDecisionLayer() if type_d_enabled else None
    command_handler = HumanCommandHandler(runner)
    human_plan_by_sequence: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for plan in golden.get("human_plan", []):
        human_plan_by_sequence[int(plan["after_sequence"])].append(plan)
    type_d_expectations = {
        int(item["agreement_sequence"]): item
        for item in golden.get("type_d_cases", [])
    }

    layout = StableLayout()
    previous_positions: dict[str, dict[str, Any]] = {}
    per_utterance: list[dict[str, Any]] = []
    snapshots: dict[str, dict[str, Any]] = {}
    last_snapshot_positions: dict[str, dict[str, Any]] = {}
    human_actions: list[dict[str, Any]] = []
    all_type_d_events: list[dict[str, Any]] = []
    type_d_false = 0
    type_d_true = 0
    type_d_missed = 0
    type_d_existing_candidate_covered = 0
    type_d_ambiguous_rejections = 0
    type_d_duplicate = 0
    automatic_confirmation = 0
    accepted_node_counts: list[int] = []
    accepted_relation_counts: list[int] = []

    for index, utterance in enumerate(dataset["utterances"]):
        before_event_count = len(result.events)
        normal_events: list[dict[str, Any]] = []
        normal_record = normal_records[index]
        for cached_event in normal_record["events"]:
            candidate = copy_as_candidate(cached_event)
            event = candidate.to_event(result.state["graph"]["last_event_sequence"] + 1)
            validator.validate_event(event)
            result = runner.apply_event(result, event)
            normal_events.append(event)

        typed_events: list[dict[str, Any]] = []
        type_d_trace: dict[str, Any] = {}
        if type_d_layer is not None:
            candidates = type_d_layer.analyze(utterance, result.state["graph"], result.events)
            type_d_trace = copy.deepcopy(type_d_layer.last_trace)
            for candidate in candidates:
                event = candidate.to_event(result.state["graph"]["last_event_sequence"] + 1)
                validator.validate_event(event)
                if event["event_type"] in {"confirm_decision", "revoke_decision"} or event["actor"] == "human":
                    automatic_confirmation += 1
                result = runner.apply_event(result, event)
                typed_events.append(event)
                all_type_d_events.append(event)
            if type_d_trace.get("reason") == "ambiguous_or_missing_proposal" and type_d_trace.get("proposal_candidate_ids"):
                type_d_ambiguous_rejections += 1

        expectation = type_d_expectations.get(int(utterance["sequence"]))
        typed_decision_events = [
            event for event in typed_events
            if event["event_type"] == "node_detected" and event["payload"].get("node_type") == "decision"
        ]
        existing_candidate_preserved = type_d_trace.get("reason") == "existing_candidate_preserved"
        for event in typed_decision_events:
            if expectation and expectation.get("expected"):
                type_d_true += 1
            else:
                type_d_false += 1
        if type_d_enabled and expectation and expectation.get("expected"):
            if existing_candidate_preserved:
                # The semantic decision is already represented in the graph;
                # the dedicated layer correctly avoids a duplicate candidate.
                type_d_existing_candidate_covered += 1
            elif not typed_decision_events:
                type_d_missed += 1

        # Apply deterministic Human Confirmation / Correction simulation.
        for plan in human_plan_by_sequence.get(int(utterance["sequence"]), []):
            eligible_decision_ids = {
                f"node:{dataset['session']['id']}:{event['event_id']}"
                for event in [*normal_events, *typed_events]
                if event["event_type"] == "node_detected"
                and event["payload"].get("node_type") == "decision"
            }
            result, action_result = execute_human_plan(
                result,
                plan,
                utterance=utterance,
                handler=command_handler,
                eligible_decision_ids=eligible_decision_ids,
            )
            action_result["after_sequence"] = utterance["sequence"]
            action_result["reason"] = plan.get("reason")
            human_actions.append(action_result)

        newly_applied = list(result.events)[before_event_count:]
        node_count = sum(event["event_type"] == "node_detected" for event in newly_applied if event.get("actor") == "analyzer")
        relation_count = sum(event["event_type"] == "relation_detected" for event in newly_applied if event.get("actor") == "analyzer")
        accepted_node_counts.append(node_count)
        accepted_relation_counts.append(relation_count)
        per_utterance.append(
            {
                "sequence": utterance["sequence"],
                "utterance_id": utterance["id"],
                "text": utterance["text"],
                "normal_event_count": len(normal_events),
                "type_d_event_count": len(typed_events),
                "accepted_node_count": node_count,
                "accepted_relation_count": relation_count,
                "normal_event_ids": [event["event_id"] for event in normal_events],
                "type_d_event_ids": [event["event_id"] for event in typed_events],
                "type_d_trace": type_d_trace,
                "human_actions": [
                    item for item in human_actions if item.get("after_sequence") == utterance["sequence"]
                ],
            }
        )

        layout_projection = map_projection(result.state, result.events, layout)
        previous_positions = copy.deepcopy(layout_projection["positions"])
        if int(utterance["sequence"]) in {20, 40, 60, 80, 100, 120}:
            summary, projection = snapshot_summary(
                result,
                layout,
                events_since_previous=newly_applied,
                previous_positions=last_snapshot_positions,
                type_d_false=type_d_false,
                type_d_auto_confirm=automatic_confirmation,
            )
            snapshots[str(int(utterance["sequence"]) // 4)] = {
                "minute": int(utterance["sequence"]) // 4,
                "utterance_sequence": utterance["sequence"],
                "summary": summary,
                "projection": projection,
            }
            last_snapshot_positions = copy.deepcopy(projection["positions"])

    graph = result.state["graph"]
    counts = count_graph(graph)
    type_d_predicted = type_d_true + type_d_false
    expected_type_d = sum(item.get("expected") is True for item in golden.get("type_d_cases", []))
    focus_events = [
        event for event in result.events
        if event["event_type"] in {"topic_focus_changed", "set_current_topic"}
    ]
    focus_transitions = 0
    previous_topic_id = None
    for event in focus_events:
        topic_id = event["payload"].get("topic_id")
        if topic_id != previous_topic_id:
            focus_transitions += 1
            previous_topic_id = topic_id

    return {
        "type_d_enabled": type_d_enabled,
        "event_count": len(result.events),
        "graph_revision": graph["revision"],
        "final_graph": copy.deepcopy(graph),
        "metrics": {
            **counts,
            "accepted_nodes": sum(accepted_node_counts),
            "accepted_nodes_per_utterance": round(sum(accepted_node_counts) / len(dataset["utterances"]), 4),
            "max_nodes_per_utterance": max(accepted_node_counts, default=0),
            "three_plus_node_utterance_rate": round(sum(count >= 3 for count in accepted_node_counts) / len(accepted_node_counts), 4),
            "accepted_relations": sum(accepted_relation_counts),
            "relations_per_utterance": round(sum(accepted_relation_counts) / len(dataset["utterances"]), 4),
            "topic_transitions": focus_transitions,
            "topic_transitions_per_10_minutes": round(focus_transitions / 3, 4),
            "candidate_decisions_per_30_minutes": counts["candidate_decision_count"] + counts["confirmed_decision_count"] + counts["revoked_decision_count"],
            "candidate_decisions_per_10_minutes": round((counts["candidate_decision_count"] + counts["confirmed_decision_count"] + counts["revoked_decision_count"]) / 3, 4),
            "type_d_candidates_added": type_d_predicted,
            "type_d_true_candidates": type_d_true,
            "type_d_false_candidates": type_d_false,
            "type_d_missed_expected": type_d_missed,
            "type_d_existing_candidate_covered": type_d_existing_candidate_covered,
            "type_d_required_additions": max(expected_type_d - type_d_existing_candidate_covered, 0),
            "type_d_effective_coverage": round(
                (type_d_true + type_d_existing_candidate_covered) / expected_type_d, 4
            ) if expected_type_d else 1.0,
            "type_d_ambiguous_rejections": type_d_ambiguous_rejections,
            "type_d_duplicate_candidate": type_d_duplicate,
            "automatic_confirmation": automatic_confirmation,
            "expected_type_d_candidates": expected_type_d,
        },
        "human_actions": human_actions,
        "type_d_events": all_type_d_events,
        "per_utterance": per_utterance,
        "snapshots": snapshots,
    }


def run(args: argparse.Namespace) -> int:
    dataset = build_recorded_30min_dataset()
    golden = build_golden_annotations()
    output_dir = args.output_dir
    dataset_dir = output_dir / "dataset"
    write_json(dataset_dir / "transcript.json", dataset)
    write_json(dataset_dir / "golden.json", golden)

    validator = SchemaValidator(args.schema_dir)
    if args.normal_recording:
        normal_records = json.loads(args.normal_recording.read_text(encoding="utf-8"))
        prior_metadata_path = output_dir / "metadata.json"
        prior_metadata = json.loads(prior_metadata_path.read_text(encoding="utf-8")) if prior_metadata_path.exists() else {}
        normal_metadata = {
            "provider": prior_metadata.get("provider"),
            "prompt_version": PROMPT_VERSION_V4,
            "schema_version": SCHEMA_VERSION,
            "call_count": prior_metadata.get("normal_analyzer_api_calls", 0),
            "accepted_event_count": None,
            "validation_failure_count": None,
            "provider_failure_count": None,
            "cache_replay": True,
        }
    else:
        provider = OpenAICompatibleProvider.from_environment()
        if not provider.configured:
            raise SystemExit("Real Analyzer provider is not configured; no API call was attempted.")
        normal_records, normal_metadata = run_normal_analyzer(dataset, validator=validator, provider=provider)
        write_json(output_dir / "normal-analyzer-recording.json", normal_records)

    off = run_branch(dataset, golden, normal_records, validator=validator, type_d_enabled=False)
    on = run_branch(dataset, golden, normal_records, validator=validator, type_d_enabled=True)
    write_json(output_dir / "run-off.json", off)
    write_json(output_dir / "run-on.json", on)
    write_json(output_dir / "snapshots-off.json", off["snapshots"])
    write_json(output_dir / "snapshots-on.json", on["snapshots"])

    comparison = {
        "run_id": output_dir.name,
        "type_d_off": off["metrics"],
        "type_d_on": on["metrics"],
        "human_confirmation_burden": {
            "off": sum(item.get("command") == "confirm_latest_candidate" and item.get("status") == "applied" for item in off["human_actions"]),
            "on": sum(item.get("command") == "confirm_latest_candidate" and item.get("status") == "applied" for item in on["human_actions"]),
        },
        "human_action_results": {"off": off["human_actions"], "on": on["human_actions"]},
        "normal_metadata": normal_metadata,
    }
    write_json(output_dir / "comparison.json", comparison)
    write_json(
        output_dir / "metadata.json",
        {
            "run_id": output_dir.name,
            "dataset_version": DATASET_VERSION,
            "duration_minutes": 30,
            "utterance_count": len(dataset["utterances"]),
            "provider": normal_metadata.get("provider"),
            "prompt_version": PROMPT_VERSION_V4,
            "context_strategy": "v1",
            "golden_version": golden["golden_version"],
            "evaluation_version": "recorded-30min-product-eval-v1",
            "analyzer_schema_version": SCHEMA_VERSION,
            "normal_analyzer_api_calls": normal_metadata.get("call_count", 0),
            "branch_replay_uses_cached_normal_output": True,
            "type_d_branches": ["off", "on"],
            "canonical_contract_changed": False,
            "secret_policy": "API key and authorization headers are not stored.",
        },
    )
    print(json.dumps(comparison, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the 30-minute Recorded Discussion evaluation")
    parser.add_argument("--schema-dir", type=Path, default=ROOT / "schemas")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--normal-recording", type=Path, help="Replay a previously saved normal Analyzer recording without API calls")
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
