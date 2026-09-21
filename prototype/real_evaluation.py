"""Semantic evaluation harness for the Recorded Real Analyzer Spike."""

from __future__ import annotations

import argparse
import copy
import json
import re
from pathlib import Path
from typing import Any, Callable, Iterable

from .analyzer import FakeAnalyzer, TranscriptReplaySession
from .real_analyzer import (
    PROMPT_VERSION,
    PROMPT_VERSION_V2,
    PROMPT_VERSION_V3,
    PROMPT_VERSION_V4,
    OpenAICompatibleProvider,
    Provider,
    RealAnalyzer,
    provider_configuration_summary,
)
from .recorded import RecordedScenario, RecordedScenarioLoader
from .replay import ReplayRunner
from .schema import SchemaValidator


def _normalize(value: str) -> str:
    return re.sub(r"[\s　。、・:：「」『』（）()\-—]+", "", value).lower()


def _matches(label: str, expected: dict[str, Any]) -> bool:
    normalized = _normalize(label)
    candidates = [expected.get("label", ""), *expected.get("aliases", [])]
    return any(_normalize(str(candidate)) in normalized or normalized in _normalize(str(candidate)) for candidate in candidates)


def _node_matches(nodes: Iterable[dict[str, Any]], expected: dict[str, Any]) -> list[dict[str, Any]]:
    expected_type = expected.get("type")
    return [
        node
        for node in nodes
        if (expected_type is None or node.get("type") == expected_type) and _matches(str(node.get("label", "")), expected)
    ]


def _one_to_one_match_count(nodes: list[dict[str, Any]], expected_items: list[dict[str, Any]]) -> int:
    """Count semantic matches without allowing one Node to satisfy twice."""

    remaining = list(nodes)
    matched = 0
    for expected in expected_items:
        candidates = _node_matches(remaining, expected)
        if not candidates:
            continue
        matched += 1
        remaining.remove(candidates[0])
    return matched


def _events_for_utterance(events: Iterable[dict[str, Any]], evidence_ids: set[str]) -> list[dict[str, Any]]:
    return [event for event in events if evidence_ids.intersection(event.get("source_evidence_ids", []))]


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 1.0


def evaluate_scenario(
    scenario: RecordedScenario,
    *,
    analyzer: Any,
    replay_runner: ReplayRunner,
) -> dict[str, Any]:
    """Run one scenario and calculate semantic, safety, and operational metrics."""

    session = TranscriptReplaySession.from_documents(
        session=scenario.session,
        evidence=scenario.evidence,
        utterances=scenario.utterances,
        replay_runner=replay_runner,
        analyzer=analyzer,
    )
    per_utterance: list[dict[str, Any]] = []
    for utterance in session.utterances:
        before = len(session.result.events)
        session.step()
        events = list(session.result.events)[before:]
        trace = getattr(analyzer, "last_trace", None) or {}
        per_utterance.append(
            {
                "utterance_id": utterance["id"],
                "text": utterance["text"],
                "event_count": len(events),
                "event_types": [event["event_type"] for event in events],
                "events": copy.deepcopy(events),
                "trace": copy.deepcopy(trace),
            }
        )

    graph_nodes = session.result.state["graph"]["nodes"]
    annotations = scenario.annotations
    expected_topics = annotations.get("expected_topics", [])
    expected_important = annotations.get("important_nodes", [])
    expected_decisions = annotations.get("candidate_decisions", [])
    expected_actions = annotations.get("actions", [])

    matched_topics = _one_to_one_match_count(
        [node for node in graph_nodes if node.get("type") == "topic"],
        expected_topics,
    )
    matched_important = _one_to_one_match_count(graph_nodes, expected_important)
    decision_nodes = [node for node in graph_nodes if node.get("type") == "decision"]
    action_nodes = [node for node in graph_nodes if node.get("type") == "action"]
    matched_decisions = _one_to_one_match_count(decision_nodes, expected_decisions)
    matched_actions = _one_to_one_match_count(action_nodes, expected_actions)

    expected_noops = set(annotations.get("no_op_utterances", []))
    actual_noops = {
        item["utterance_id"]
        for item in per_utterance
        if item["event_count"] == 0
    }
    no_op_correct = len(expected_noops & actual_noops)
    no_op_total = len(expected_noops)

    expected_returns = annotations.get("topic_returns", [])
    return_correct = 0
    for expected_return in expected_returns:
        item = next((item for item in per_utterance if item["utterance_id"] == expected_return["utterance_id"]), None)
        if item is None:
            continue
        target = expected_return["target_topic"]
        focus_event = next((event for event in item["events"] if event["event_type"] == "topic_focus_changed"), None)
        target_node = next(
            (
                node
                for node in graph_nodes
                if focus_event and node["id"] == focus_event["payload"].get("topic_id")
            ),
            None,
        )
        if target_node and _matches(target_node["label"], {"label": target}):
            return_correct += 1

    topic_nodes = [node for node in graph_nodes if node.get("type") == "topic"]
    normalized_topic_labels = [_normalize(str(node.get("label", ""))) for node in topic_nodes]
    duplicate_topic_nodes = len(normalized_topic_labels) - len(set(normalized_topic_labels))
    critical_errors = []
    validation_failures = 0
    latency_values: list[float] = []
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for item in per_utterance:
        trace = item["trace"]
        critical_errors.extend(trace.get("critical_errors", []))
        if trace.get("validation_error"):
            validation_failures += 1
        if isinstance(trace.get("latency_ms"), (float, int)):
            latency_values.append(float(trace["latency_ms"]))
        for key in usage:
            value = trace.get("usage", {}).get(key)
            if isinstance(value, int):
                usage[key] += value

    node_events = [item for item in per_utterance if item["event_count"]]
    explosion_events = sum(item["event_count"] > 3 for item in per_utterance)
    labels = [node["label"] for node in graph_nodes if node.get("type") != "topic"]
    label_quality = _rate(sum(5 <= len(str(label)) <= 40 for label in labels), len(labels))

    return {
        "scenario": scenario.scenario_id,
        "title": scenario.name,
        "utterance_count": len(session.utterances),
        "event_count": len(session.result.events),
        "validation_failures": validation_failures,
        "duplicate_nodes": duplicate_topic_nodes,
        "candidate_decisions": len(decision_nodes),
        "actions": len(action_nodes),
        "critical_errors": sorted(set(critical_errors)),
        "latency": {
            "count": len(latency_values),
            "total_ms": round(sum(latency_values), 3),
            "average_ms": round(sum(latency_values) / len(latency_values), 3) if latency_values else None,
            "max_ms": round(max(latency_values), 3) if latency_values else None,
        },
        "usage": usage,
        "metrics": {
            "topic_precision": _rate(matched_topics, len(topic_nodes)),
            "topic_recall": _rate(matched_topics, len(expected_topics)),
            "important_node_recall": _rate(matched_important, len(expected_important)),
            "duplicate_node_rate": _rate(duplicate_topic_nodes, len(topic_nodes)),
            "candidate_decision_precision": _rate(matched_decisions, len(decision_nodes)),
            "action_precision": _rate(matched_actions, len(action_nodes)),
            "topic_return_accuracy": _rate(return_correct, len(expected_returns)),
            "no_op_accuracy": _rate(no_op_correct, no_op_total),
            "node_explosion_rate": _rate(explosion_events, len(per_utterance)),
            "label_quality": label_quality,
        },
        "final_graph": copy.deepcopy(session.result.state["graph"]),
        "per_utterance": per_utterance,
    }


def run_dataset(
    scenarios: Iterable[RecordedScenario],
    *,
    analyzer_factory: Callable[[RecordedScenario], Any],
    replay_runner: ReplayRunner,
    run_kind: str,
    prompt_version: str | None = None,
    output_schema_version: str = "v1",
) -> dict[str, Any]:
    results = []
    provider_summary: dict[str, Any] | None = None
    for scenario in scenarios:
        analyzer = analyzer_factory(scenario)
        if provider_summary is None:
            provider_summary = provider_configuration_summary(analyzer.provider) if isinstance(analyzer, RealAnalyzer) else {
                "provider": "fake",
                "model": "deterministic",
                "configured": True,
            }
        result = evaluate_scenario(scenario, analyzer=analyzer, replay_runner=replay_runner)
        result["run_kind"] = run_kind
        result["provider"] = provider_summary
        result["prompt_version"] = getattr(analyzer, "prompt_version", None)
        results.append(result)

    metric_names = [
        "topic_precision",
        "topic_recall",
        "important_node_recall",
        "duplicate_node_rate",
        "candidate_decision_precision",
        "action_precision",
        "topic_return_accuracy",
        "no_op_accuracy",
        "node_explosion_rate",
        "label_quality",
    ]
    aggregate = {
        metric: round(sum(result["metrics"][metric] for result in results) / len(results), 4) if results else None
        for metric in metric_names
    }
    return {
        "run_kind": run_kind,
        "provider": provider_summary,
        "prompt_version": prompt_version if run_kind == "real" else None,
        "dataset_count": len(results),
        "aggregate_metrics": aggregate,
        "critical_error_count": sum(len(result["critical_errors"]) for result in results),
        "validation_failure_count": sum(result["validation_failures"] for result in results),
        "scenarios": results,
    }


def run_cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Recorded Real Analyzer semantic evaluation")
    parser.add_argument("--schema-dir", type=Path, default=Path("schemas"))
    parser.add_argument("--scenario-dir", type=Path, default=Path("evaluation/real-analyzer"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--fake-only", action="store_true")
    parser.add_argument(
        "--prompt-version",
        choices=[PROMPT_VERSION, PROMPT_VERSION_V2, PROMPT_VERSION_V3, PROMPT_VERSION_V4],
        default=PROMPT_VERSION,
    )
    parser.add_argument("--analyzer-schema-version", choices=["v1", "v2"], default="v1")
    args = parser.parse_args(argv)

    validator = SchemaValidator(args.schema_dir)
    runner = ReplayRunner(validator)
    scenarios = RecordedScenarioLoader(args.scenario_dir).load_all()
    output: dict[str, Any] = {
        "dataset": [scenario.scenario_id for scenario in scenarios],
        "fake": run_dataset(
            scenarios,
            analyzer_factory=lambda scenario: FakeAnalyzer(),
            replay_runner=runner,
            run_kind="fake",
        ),
    }
    if not args.fake_only:
        provider = OpenAICompatibleProvider.from_environment()
        output["real"] = run_dataset(
            scenarios,
            analyzer_factory=lambda scenario: RealAnalyzer(
                provider=provider,
                schema_validator=validator,
                meeting_goal=scenario.session.get("goal"),
                prompt_version=args.prompt_version,
                output_schema_version=args.analyzer_schema_version,
            ),
            replay_runner=runner,
            run_kind="real",
            prompt_version=args.prompt_version,
            output_schema_version=args.analyzer_schema_version,
        )
    rendered = json.dumps(output, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli())
