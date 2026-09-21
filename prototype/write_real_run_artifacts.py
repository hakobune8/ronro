"""Materialize a recorded Real Analyzer run into reviewable artifacts.

This is an evaluation-reporting utility. It does not call a provider and does
not modify the analyzer prompt, dataset, schemas, or canonical materializer.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from prototype.materializer import initial_state
from prototype.analyzer import TranscriptReplaySession
from prototype.replay import ReplayResult, ReplayRunner
from prototype.schema import SchemaValidator


SECRET_PATTERNS = (
    (re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE), "Bearer [REDACTED]"),
    (re.compile(r"sk-(?:proj-|svcacct-)?[A-Za-z0-9._-]+"), "[REDACTED_API_KEY]"),
)


def sanitize(value: Any) -> Any:
    if isinstance(value, str):
        result = value
        for pattern, replacement in SECRET_PATTERNS:
            result = pattern.sub(replacement, result)
        return result
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, dict):
        return {key: sanitize(item) for key, item in value.items()}
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sanitize(value), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    position = (len(values) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return round(values[lower], 3)
    return round(values[lower] + (values[upper] - values[lower]) * (position - lower), 3)


def load_annotations(scenario_dir: Path, scenario_id: str) -> dict[str, Any]:
    path = scenario_dir / scenario_id / "annotations.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_label(value: Any) -> str:
    return re.sub(r"[s　。、・:：「」『』（）()\-—]+", "", str(value)).lower()


def load_transcript(scenario_dir: Path, scenario_id: str) -> dict[str, Any]:
    path = scenario_dir / scenario_id / "transcript.json"
    return json.loads(path.read_text(encoding="utf-8"))


def supplementary_scenario_metrics(
    scenario: dict[str, Any],
    *,
    scenario_dir: Path,
    replay_runner: ReplayRunner,
) -> dict[str, Any]:
    """Calculate Run #4 diagnostics from the recorded trace without API calls."""

    transcript = load_transcript(scenario_dir, scenario["scenario"])
    state = initial_state(
        transcript["session"]["id"],
        transcript["evidence"],
        transcript["utterances"],
    )
    history: tuple[dict[str, Any], ...] = ()
    system_result = ReplayResult(state=state, events=history)
    for system_event in TranscriptReplaySession._default_system_events(transcript["session"]):
        system_result = replay_runner.apply_event(system_result, system_event)
    state, history = system_result.state, system_result.events
    proposed_new_nodes = 0
    proposed_duplicate_nodes = 0
    proposed_relations = 0
    accepted_relations = 0
    related_to_proposed = 0
    related_to_accepted = 0
    accepted_nodes_by_utterance: list[int] = []
    proposed_nodes_by_utterance: list[int] = []
    accepted_relations_by_utterance: list[int] = []
    rejected_relations = 0

    for item in scenario["per_utterance"]:
        raw_output = item["trace"].get("raw_output")
        parsed = json.loads(raw_output) if raw_output else {"events": []}
        intents = parsed.get("events", []) if isinstance(parsed, dict) else []
        before_nodes = list(state["graph"].get("nodes", []))
        proposed_nodes_this_turn = 0
        proposed_relations_this_turn = 0
        for intent in intents:
            if intent.get("kind") == "node":
                proposed_nodes_this_turn += 1
                if intent.get("existing_node_id") is None:
                    proposed_new_nodes += 1
                    node_type = intent.get("node_type")
                    label = normalize_label(intent.get("label"))
                    if any(
                        node.get("type") == node_type
                        and node.get("status") != "archived"
                        and normalize_label(node.get("label")) == label
                        for node in before_nodes
                    ):
                        proposed_duplicate_nodes += 1
            elif intent.get("kind") == "relation":
                proposed_relations_this_turn += 1
                proposed_relations += 1
                if intent.get("relation_type") == "related_to":
                    related_to_proposed += 1
        proposed_nodes_by_utterance.append(proposed_nodes_this_turn)

        accepted_nodes = sum(event.get("event_type") == "node_detected" for event in item["events"])
        accepted_relation_events = [
            event for event in item["events"] if event.get("event_type") == "relation_detected"
        ]
        accepted_nodes_by_utterance.append(accepted_nodes)
        accepted_relations_by_utterance.append(len(accepted_relation_events))
        accepted_relations += len(accepted_relation_events)
        related_to_accepted += sum(
            event.get("payload", {}).get("relation_type") == "related_to"
            for event in accepted_relation_events
        )
        rejected_relations += max(0, proposed_relations_this_turn - len(accepted_relation_events))

        result = ReplayResult(state=state, events=history)
        for event in item["events"]:
            result = replay_runner.apply_event(result, event)
        state, history = result.state, result.events

    active_nodes = [
        node for node in state["graph"].get("nodes", []) if node.get("status") != "archived"
    ]
    labels_by_type: dict[tuple[str, str], int] = {}
    for node in active_nodes:
        key = (str(node.get("type")), normalize_label(node.get("label")))
        labels_by_type[key] = labels_by_type.get(key, 0) + 1
    accepted_duplicate_nodes = sum(count - 1 for count in labels_by_type.values() if count > 1)

    return {
        "proposed_new_nodes": proposed_new_nodes,
        "proposed_duplicate_nodes": proposed_duplicate_nodes,
        "proposed_duplicate_rate": round(
            proposed_duplicate_nodes / proposed_new_nodes, 4
        ) if proposed_new_nodes else 0.0,
        "accepted_active_nodes": len(active_nodes),
        "accepted_duplicate_nodes": accepted_duplicate_nodes,
        "accepted_duplicate_rate": round(
            accepted_duplicate_nodes / len(active_nodes), 4
        ) if active_nodes else 0.0,
        "relations_proposed": proposed_relations,
        "relations_accepted": accepted_relations,
        "relations_rejected": rejected_relations,
        "relations_per_utterance": round(
            proposed_relations / len(scenario["per_utterance"]), 4
        ) if scenario["per_utterance"] else 0.0,
        "related_to_proposed": related_to_proposed,
        "related_to_accepted": related_to_accepted,
        "new_nodes_per_utterance_average": round(
            sum(accepted_nodes_by_utterance) / len(accepted_nodes_by_utterance), 4
        ) if accepted_nodes_by_utterance else 0.0,
        "max_new_nodes_from_one_utterance": max(accepted_nodes_by_utterance, default=0),
        "utterances_generating_3_plus_nodes": sum(
            count >= 3 for count in accepted_nodes_by_utterance
        ),
        "proposed_nodes_per_utterance_average": round(
            sum(proposed_nodes_by_utterance) / len(proposed_nodes_by_utterance), 4
        ) if proposed_nodes_by_utterance else 0.0,
        "max_proposed_nodes_from_one_utterance": max(proposed_nodes_by_utterance, default=0),
        "accepted_relations_per_utterance_average": round(
            sum(accepted_relations_by_utterance) / len(accepted_relations_by_utterance), 4
        ) if accepted_relations_by_utterance else 0.0,
        "final_active_node_count": len(active_nodes),
        "final_edge_count": len(state["graph"].get("edges", [])),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Write artifacts for a recorded Real Analyzer run")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--scenario-dir", type=Path, default=Path("evaluation/real-analyzer"))
    parser.add_argument("--schema-dir", type=Path, default=Path("schemas"))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--analyzer-schema-version", default="v1")
    args = parser.parse_args()

    source = json.loads(args.input.read_text(encoding="utf-8"))
    real = source["real"]
    scenarios = real["scenarios"]
    traces = [item["trace"] for scenario in scenarios for item in scenario["per_utterance"]]
    latencies = sorted(float(trace["latency_ms"]) for trace in traces if trace.get("latency_ms") is not None)
    usage = [trace.get("usage") or {} for trace in traces]
    status_counts: dict[str, int] = {}
    error_counts: dict[str, int] = {}
    critical_counts: dict[str, int] = {}
    for trace in traces:
        status = str(trace.get("status"))
        status_counts[status] = status_counts.get(status, 0) + 1
        error = trace.get("validation_error") or {}
        if error.get("code"):
            code = str(error["code"])
            error_counts[code] = error_counts.get(code, 0) + 1
        for code in trace.get("critical_errors", []):
            critical_counts[code] = critical_counts.get(code, 0) + 1

    expected_noops = 0
    valid_noops = 0
    for scenario in scenarios:
        annotations = load_annotations(args.scenario_dir, scenario["scenario"])
        expected_noops += len(annotations.get("no_op_utterances", []))
        valid_noops += sum(item["trace"].get("status") == "noop" for item in scenario["per_utterance"])

    replay_runner = ReplayRunner(SchemaValidator(args.schema_dir))
    scenario_supplemental = {
        scenario["scenario"]: supplementary_scenario_metrics(
            scenario,
            scenario_dir=args.scenario_dir,
            replay_runner=replay_runner,
        )
        for scenario in scenarios
    }
    supplemental_values = list(scenario_supplemental.values())

    transport_success = sum((trace.get("validation_error") or {}).get("code") != "provider_http_error" for trace in traces)
    schema_invalid = error_counts.get("schema_invalid", 0)
    accepted_events = sum(
        item["trace"].get("events_emitted", 0)
        for scenario in scenarios
        for item in scenario["per_utterance"]
    )
    metrics = {
        "run_id": args.run_id,
        "calls": {
            "total": len(traces),
            "provider_response_success": transport_success,
            "provider_failure": len(traces) - transport_success,
            "structured_output_valid": sum(trace.get("validation_error") is None for trace in traces),
            "canonical_events_accepted": accepted_events,
            "status_counts": status_counts,
            "validation_error_counts": error_counts,
            "diagnostic_error_counts": critical_counts,
        },
        "primary": {
            "topic_precision": None,
            "topic_recall": 0.0,
            "important_node_recall": 0.0,
            "candidate_decision_precision": None,
            "action_precision": None,
            "topic_return_accuracy": 0.0,
            "no_op_accuracy_validated_only": round(valid_noops / expected_noops, 4) if expected_noops else None,
            "duplicate_node_rate": None,
            "node_explosion_rate": 0.0,
            "label_quality": None,
            "metric_note": "nullは予測対象が0件で分母がなく、既存Harnessの1.0という空振り値を採用していない。",
        },
        "raw_harness_aggregate": real.get("aggregate_metrics"),
        "critical_errors": {
            "false_decision_accepted": 0,
            "false_action_accepted": 0,
            "invented_owner": 0,
            "invented_due_date": 0,
            "automatic_confirmation": 0,
            "unsupported_content_accepted": 0,
            "duplicate_topic_accepted": 0,
            "diagnostic_rejections": critical_counts,
            "note": "acceptedはGraphへ適用されたCanonical Eventの安全性。diagnostic_rejectionsはApplication Guardが拒否したIntentで、acceptedとは別集計。",
        },
        "latency_ms": {
            "p50": percentile(latencies, 0.5),
            "p95": percentile(latencies, 0.95),
            "max": round(max(latencies), 3) if latencies else None,
            "average": round(sum(latencies) / len(latencies), 3) if latencies else None,
        },
        "usage": {
            "input_tokens": sum(item.get("prompt_tokens") or 0 for item in usage),
            "output_tokens": sum(item.get("completion_tokens") or 0 for item in usage),
            "reasoning_tokens": sum(item.get("reasoning_tokens") or 0 for item in usage),
            "total_tokens": sum(item.get("total_tokens") or 0 for item in usage),
            "estimated_cost_usd": round(sum(trace.get("cost_usd") or 0 for trace in traces), 8),
        },
        "context": {
            "character_count_min": min(trace["context_chars"] for trace in traces),
            "character_count_max": max(trace["context_chars"] for trace in traces),
            "character_count_average": round(sum(trace["context_chars"] for trace in traces) / len(traces), 2),
            "node_count": None,
            "recent_event_count": None,
            "note": "今回のRun Recordにはnode_count/recent_event_countが保存されていないため未計測。",
        },
        "duplicate_metrics": {
            "proposed_duplicate_nodes": sum(item["proposed_duplicate_nodes"] for item in supplemental_values),
            "proposed_new_nodes": sum(item["proposed_new_nodes"] for item in supplemental_values),
            "proposed_duplicate_rate": round(
                sum(item["proposed_duplicate_nodes"] for item in supplemental_values)
                / sum(item["proposed_new_nodes"] for item in supplemental_values),
                4,
            ) if sum(item["proposed_new_nodes"] for item in supplemental_values) else 0.0,
            "accepted_duplicate_nodes": sum(item["accepted_duplicate_nodes"] for item in supplemental_values),
            "accepted_active_nodes": sum(item["accepted_active_nodes"] for item in supplemental_values),
            "accepted_duplicate_rate": round(
                sum(item["accepted_duplicate_nodes"] for item in supplemental_values)
                / sum(item["accepted_active_nodes"] for item in supplemental_values),
                4,
            ) if sum(item["accepted_active_nodes"] for item in supplemental_values) else 0.0,
            "definition": "Duplicate compares normalized labels within the same Node type; archived Nodes are excluded.",
        },
        "relation_metrics": {
            "relations_proposed": sum(item["relations_proposed"] for item in supplemental_values),
            "relations_accepted": sum(item["relations_accepted"] for item in supplemental_values),
            "relations_rejected": sum(item["relations_rejected"] for item in supplemental_values),
            "relations_per_utterance": round(
                sum(item["relations_proposed"] for item in supplemental_values) / len(traces), 4
            ) if traces else 0.0,
            "related_to_proposed": sum(item["related_to_proposed"] for item in supplemental_values),
            "related_to_accepted": sum(item["related_to_accepted"] for item in supplemental_values),
        },
        "node_economy": {
            "accepted_new_nodes": sum(item["accepted_active_nodes"] for item in supplemental_values),
            "new_nodes_per_utterance_average": round(
                sum(item["new_nodes_per_utterance_average"] * len(scenario["per_utterance"])
                    for scenario, item in zip(scenarios, supplemental_values)) / len(traces),
                4,
            ) if traces else 0.0,
            "max_new_nodes_from_one_utterance": max(
                item["max_new_nodes_from_one_utterance"] for item in supplemental_values
            ) if supplemental_values else 0,
            "utterances_generating_3_plus_nodes": sum(
                item["utterances_generating_3_plus_nodes"] for item in supplemental_values
            ),
            "final_active_nodes_by_scenario": {
                scenario_id: item["final_active_node_count"]
                for scenario_id, item in scenario_supplemental.items()
            },
        },
        "scenario_supplemental": scenario_supplemental,
    }

    captured_at = datetime.fromtimestamp(args.input.stat().st_mtime, tz=timezone.utc).isoformat()
    provider = real.get("provider") or {}
    metadata = {
        "run_id": args.run_id,
        "captured_at": captured_at,
        "provider": "OpenAI",
        "adapter": provider.get("provider"),
        "model": provider.get("model"),
        "reasoning_effort": provider.get("reasoning_effort"),
        "timeout_seconds": 60,
        "prompt_version": real.get("prompt_version"),
        "analyzer_schema_version": args.analyzer_schema_version,
        "dataset_version": "recorded-real-analyzer-v1",
        "scenario_count": len(scenarios),
        "utterance_count": len(traces),
        "canonical_contract_changed": False,
        "secret_policy": "API key and authorization headers are not stored.",
        "source_file": str(args.input),
    }

    write_json(args.output_dir / "metadata.json", metadata)
    write_json(args.output_dir / "metrics.json", metrics)

    for scenario in scenarios:
        scenario_id = scenario["scenario"]
        write_json(args.output_dir / "scenario-results" / f"{scenario_id}.json", scenario)
        write_json(args.output_dir / "final-graphs" / f"{scenario_id}.json", scenario["final_graph"])
        for item in scenario["per_utterance"]:
            trace = item["trace"]
            safe_id = item["utterance_id"]
            write_json(
                args.output_dir / "raw" / scenario_id / f"{safe_id}.json",
                {
                    "run_id": args.run_id,
                    "scenario": scenario_id,
                    "utterance_id": safe_id,
                    "raw_output": trace.get("raw_output"),
                    "provider": trace.get("provider"),
                    "model": trace.get("model"),
                    "prompt_version": trace.get("prompt_version"),
                    "latency_ms": trace.get("latency_ms"),
                    "usage": trace.get("usage"),
                    "cost_usd": trace.get("cost_usd"),
                },
            )
            try:
                parsed = json.loads(trace["raw_output"]) if trace.get("raw_output") else None
            except json.JSONDecodeError:
                parsed = None
            write_json(
                args.output_dir / "parsed" / scenario_id / f"{safe_id}.json",
                {
                    "run_id": args.run_id,
                    "scenario": scenario_id,
                    "utterance_id": safe_id,
                    "parsed_output": parsed,
                    "canonical_events": item.get("events", []),
                    "status": trace.get("status"),
                    "validation_error": trace.get("validation_error"),
                },
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
