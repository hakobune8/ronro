"""Run the Context Strategy v1/v2 diagnostic on a separate spike dataset.

This script intentionally does not load or rerun evaluation/real-analyzer.
It keeps analyzer-prompt-v4, the frozen model, and the canonical conversion
path unchanged. Context v2 adds only one previous finalized utterance to the
provider-facing Context.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import re
import time
from pathlib import Path
from typing import Any, Iterable, Mapping

from .real_analyzer import (
    AnalysisContextBuilder,
    OpenAICompatibleProvider,
    PROMPT_VERSION_V4,
    RealAnalyzer,
)
from .schema import SchemaValidator


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "evaluation" / "context-spike" / "dataset.json"
DEFAULT_OUTPUT = ROOT / "evaluation" / "runs" / "context-strategy-v2-gpt-5.6-luna-analyzer-prompt-v4-20260919"
FROZEN_MODEL = "gpt-5.6-luna"
FROZEN_REASONING = "medium"
HUMAN_EVENT_TYPES = {
    "confirm_decision",
    "revoke_decision",
    "rename_node",
    "archive_node",
    "merge_nodes",
    "move_to_parking_lot",
    "restore_from_parking_lot",
    "update_action",
    "set_current_topic",
    "undo_last_correction",
}


class PreviousUtteranceContextBuilder(AnalysisContextBuilder):
    """The v2 experiment adds exactly one finalized utterance."""

    def __init__(self, previous_utterance: Mapping[str, Any] | None, *, include_previous: bool) -> None:
        super().__init__()
        self.previous_utterance = copy.deepcopy(dict(previous_utterance)) if previous_utterance else None
        self.include_previous = include_previous

    def build(
        self,
        *,
        utterance: Mapping[str, Any],
        current_graph: Mapping[str, Any],
        recent_events: Iterable[Mapping[str, Any]],
        meeting_goal: str | None,
    ) -> dict[str, Any]:
        context = super().build(
            utterance=utterance,
            current_graph=current_graph,
            recent_events=recent_events,
            meeting_goal=meeting_goal,
        )
        if self.include_previous:
            previous = self.previous_utterance
            context["previous_utterance"] = (
                {
                    "id": previous.get("id"),
                    "sequence": previous.get("sequence"),
                    "speaker": previous.get("speaker"),
                    "text": previous.get("text"),
                    "evidence_ids": list(previous.get("evidence_ids", [])),
                }
                if previous
                else None
            )
        return context


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def redact(value: Any) -> Any:
    if isinstance(value, str):
        value = re.sub(r"Bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", value, flags=re.IGNORECASE)
        value = re.sub(r"sk-(?:proj-|svcacct-)?[A-Za-z0-9._-]+", "[REDACTED_API_KEY]", value)
        return value
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, dict):
        return {key: redact(item) for key, item in value.items()}
    return value


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    position = (len(values) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return round(values[lower], 3)
    return round(values[lower] + (values[upper] - values[lower]) * (position - lower), 3)


def normalized_event(candidate: Any, sequence: int) -> dict[str, Any]:
    return candidate.to_event(sequence)


def parse_raw_output(trace: Mapping[str, Any]) -> dict[str, Any]:
    raw = trace.get("raw_output")
    if not raw:
        return {"events": []}
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {"events": []}
    return parsed if isinstance(parsed, dict) else {"events": []}


def collect_existing_refs(value: Any) -> list[str]:
    refs: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "existing_node_id" and isinstance(item, str) and item:
                refs.append(item)
            else:
                refs.extend(collect_existing_refs(item))
    elif isinstance(value, list):
        for item in value:
            refs.extend(collect_existing_refs(item))
    return refs


def contains_event_type(events: list[dict[str, Any]], event_type: str) -> bool:
    return any(event.get("event_type") == event_type for event in events)


def contains_node_type(events: list[dict[str, Any]], node_type: str) -> bool:
    return any(
        event.get("event_type") == "node_detected"
        and event.get("payload", {}).get("node_type") == node_type
        for event in events
    )


def has_new_topic(events: list[dict[str, Any]]) -> bool:
    return any(
        event.get("event_type") == "node_detected"
        and event.get("payload", {}).get("node_type") == "topic"
        for event in events
    )


def event_ids(events: list[dict[str, Any]]) -> list[str]:
    return [str(event.get("event_id")) for event in events]


def evaluate_case(
    case: Mapping[str, Any],
    *,
    variant: str,
    output_dir: Path,
    validator: SchemaValidator,
    provider: OpenAICompatibleProvider,
) -> dict[str, Any]:
    include_previous = variant == "v2"
    previous = case.get("previous_utterance")
    builder = PreviousUtteranceContextBuilder(previous, include_previous=include_previous)
    analyzer = RealAnalyzer(
        provider=provider,
        schema_validator=validator,
        meeting_goal=case.get("meeting_goal"),
        context_builder=builder,
        prompt_version=PROMPT_VERSION_V4,
        output_schema_version="v2",
    )

    current = copy.deepcopy(case["current_utterance"])
    graph = copy.deepcopy(case["graph"])
    recent_events = copy.deepcopy(case.get("recent_events", []))
    context = builder.build(
        utterance=current,
        current_graph=graph,
        recent_events=recent_events,
        meeting_goal=case.get("meeting_goal"),
    )

    started = time.perf_counter()
    candidates = analyzer.analyze(current, graph, recent_events)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    trace = copy.deepcopy(analyzer.last_trace or {})
    parsed = parse_raw_output(trace)
    canonical_events = [
        normalized_event(candidate, index + 1)
        for index, candidate in enumerate(candidates)
    ]
    for event in canonical_events:
        validator.validate_event(event)

    expected = case.get("expected", {})
    refs = collect_existing_refs(parsed)
    graph_node_ids = {
        str(node.get("id"))
        for node in graph.get("nodes", [])
        if isinstance(node, Mapping)
    }
    decision_present = contains_node_type(canonical_events, "decision")
    action_present = contains_node_type(canonical_events, "action")
    focus_targets = [
        event.get("payload", {}).get("topic_id")
        for event in canonical_events
        if event.get("event_type") == "topic_focus_changed"
    ]
    focus_forbidden = bool(expected.get("focus_change_forbidden"))
    decision_class = expected.get("decision_class", "none")
    strong_expected = decision_class in {"strong_or_candidate", "candidate_possible"}
    false_strong_decision = decision_present and not strong_expected
    automatic_confirmation = any(
        event.get("event_type") in HUMAN_EVENT_TYPES
        for event in canonical_events
    ) or any(
        isinstance(intent, Mapping) and intent.get("event_type") in HUMAN_EVENT_TYPES
        for intent in parsed.get("events", [])
    )
    action_values = [
        intent.get("action", {})
        for intent in parsed.get("events", [])
        if isinstance(intent, Mapping)
        and intent.get("kind") == "node"
        and intent.get("node_type") == "action"
    ]
    raw_action_present = bool(action_values)
    current_text = str(current.get("text", ""))
    proposed_invented_owner = any(
        isinstance(action, Mapping)
        and action.get("owner") not in (None, "")
        and str(action.get("owner")) not in current_text
        for action in action_values
    )
    proposed_invented_due = any(
        isinstance(action, Mapping)
        and action.get("due_date") not in (None, "")
        and str(action.get("due_date")) not in current_text
        for action in action_values
    )
    accepted_action_payloads = [
        event.get("payload", {}).get("action", {})
        for event in canonical_events
        if event.get("event_type") == "node_detected"
        and event.get("payload", {}).get("node_type") == "action"
    ]
    accepted_invented_owner = any(
        payload.get("owner") not in (None, "")
        and str(payload.get("owner")) not in current_text
        for payload in accepted_action_payloads
        if isinstance(payload, Mapping)
    )
    accepted_invented_due = any(
        payload.get("due_date") not in (None, "")
        and str(payload.get("due_date")) not in current_text
        for payload in accepted_action_payloads
        if isinstance(payload, Mapping)
    )

    expected_refs = set(expected.get("reference_target_ids", []))
    reference_hit = bool(expected_refs.intersection(refs))
    reference_wrong = any(ref not in graph_node_ids for ref in refs)
    relevant_node_ids = {
        str(node.get("id"))
        for node in context.get("relevant_nodes", [])
        if isinstance(node, Mapping)
    }
    reference_context_available = bool(expected_refs.intersection(relevant_node_ids))
    reference_available_case = bool(
        expected.get("reference_required")
        and not expected.get("reference_safe_when_omitted")
        and reference_context_available
    )
    existing_node_reference_hit = bool(
        reference_available_case
        and reference_hit
        and not reference_wrong
        and expected_refs.issubset(relevant_node_ids)
    )
    target = expected.get("topic_return_target")
    topic_return_hit = target in focus_targets if target else None
    noop_hit = len(canonical_events) == 0 if expected.get("no_op_expected") else None
    action_hit = action_present if expected.get("action_expected") else None
    omitted_target_safe = (
        expected.get("reference_safe_when_omitted")
        and not any(ref == next(iter(expected_refs), None) for ref in refs)
        and not reference_wrong
    )
    ambiguous_safe = (
        expected.get("ambiguous_reference")
        and not decision_present
        and not focus_targets
        and not reference_wrong
    )
    focus_safe = not focus_forbidden or not focus_targets
    node_ids = [event.get("event_id") for event in canonical_events if event.get("event_type") == "node_detected"]

    result = {
        "case_id": case["case_id"],
        "category": case.get("category"),
        "formation_type": case.get("formation_type"),
        "variant": variant,
        "utterance": current,
        "previous_utterance_in_context": copy.deepcopy(previous) if include_previous else None,
        "context": redact(context),
        "trace": redact(trace),
        "parsed_output": redact(parsed),
        "canonical_events": redact(canonical_events),
        "candidate_event_ids": event_ids(canonical_events),
        "metrics": {
            "reference_hit": reference_hit,
            "reference_required": bool(expected.get("reference_required")),
            "reference_safe_when_omitted": bool(expected.get("reference_safe_when_omitted")),
            "reference_wrong": reference_wrong,
            "reference_context_available": reference_context_available,
            "reference_available_case": reference_available_case,
            "existing_node_reference_hit": existing_node_reference_hit,
            "topic_return_hit": topic_return_hit,
            "decision_present": decision_present,
            "strong_expected": strong_expected,
            "false_strong_decision": false_strong_decision,
            "action_present": action_present,
            "raw_action_present": raw_action_present,
            "false_action_proposed": raw_action_present and not bool(expected.get("action_expected")),
            "action_hit": action_hit,
            "noop_hit": noop_hit,
            "automatic_confirmation": automatic_confirmation,
            "proposed_invented_owner": proposed_invented_owner,
            "proposed_invented_due": proposed_invented_due,
            "accepted_invented_owner": accepted_invented_owner,
            "accepted_invented_due": accepted_invented_due,
            "omitted_target_safe": omitted_target_safe,
            "ambiguous_reference_safe": ambiguous_safe,
            "focus_safe": focus_safe,
            "new_topic": has_new_topic(canonical_events),
            "event_count": len(canonical_events),
            "context_chars": trace.get("context_chars", builder.measure(context).get("context_chars")),
            "estimated_context_tokens": trace.get("estimated_tokens", builder.measure(context).get("estimated_tokens")),
            "latency_ms": trace.get("latency_ms", elapsed_ms),
            "total_elapsed_ms": trace.get("total_elapsed_ms", elapsed_ms),
            "usage": trace.get("usage", {}),
            "cost_usd": trace.get("cost_usd"),
            "api_success": trace.get("raw_output") is not None,
            "analyzer_output_valid": (
                trace.get("raw_output") is not None
                and trace.get("validation_error") is None
            ),
            "status": trace.get("status"),
            "validation_error": trace.get("validation_error"),
        },
    }

    case_dir = output_dir / variant / "cases" / case["case_id"]
    write_json(case_dir / "context.json", redact(context))
    write_json(case_dir / "raw-output.json", {"raw_output": trace.get("raw_output")})
    write_json(case_dir / "parsed-output.json", redact(parsed))
    write_json(case_dir / "canonical-events.json", redact(canonical_events))
    write_json(case_dir / "result.json", result)
    return result


def aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    def bool_values(key: str, *, only_required: bool = False) -> list[bool]:
        selected = [
            item["metrics"]
            for item in results
            if not only_required or item["metrics"].get(f"{key}_required")
        ]
        return [bool(item.get(key)) for item in selected]

    def rate(values: list[bool]) -> float | None:
        return round(sum(values) / len(values), 4) if values else None

    references = [
        bool(item["metrics"].get("reference_hit"))
        for item in results
        if item["metrics"].get("reference_required")
        and not item["metrics"].get("reference_safe_when_omitted")
    ]
    available_references = [
        bool(item["metrics"].get("existing_node_reference_hit"))
        for item in results
        if item["metrics"].get("reference_available_case")
    ]
    topic_returns = [
        item["metrics"]["topic_return_hit"]
        for item in results
        if item["metrics"].get("topic_return_hit") is not None
    ]
    type_c = [
        item["metrics"]["decision_present"]
        for item in results
        if item.get("formation_type") == "C"
        and item["metrics"].get("strong_expected")
        and item.get("category") == "type_c_decision"
    ]
    type_d = [
        item["metrics"]["decision_present"]
        for item in results
        if item.get("formation_type") == "D"
        and item["metrics"].get("strong_expected")
        and item.get("category") in {"type_d_agreement", "proposal_reference"}
    ]
    weak_agreement = [
        item["metrics"]["false_strong_decision"]
        for item in results
        if item["case_id"] == "ctx-007-weak-agreement"
    ]
    actions = [
        item["metrics"]["action_hit"]
        for item in results
        if item["metrics"].get("action_hit") is not None
    ]
    noops = [
        item["metrics"]["noop_hit"]
        for item in results
        if item["metrics"].get("noop_hit") is not None
    ]
    omitted_safety = [
        item["metrics"]["omitted_target_safe"]
        for item in results
        if item["metrics"].get("omitted_target_safe") is not None
    ]
    ambiguous_safety = [
        item["metrics"]["ambiguous_reference_safe"]
        for item in results
        if item.get("category") == "ambiguous_reference"
    ]
    focus_safety = [
        item["metrics"]["focus_safe"]
        for item in results
        if item["metrics"].get("focus_safe") is not None
    ]
    latencies = [
        float(item["metrics"]["latency_ms"])
        for item in results
        if item["metrics"].get("latency_ms") is not None
    ]
    input_tokens = [
        int(item["metrics"]["usage"].get("prompt_tokens"))
        for item in results
        if item["metrics"].get("usage", {}).get("prompt_tokens") is not None
    ]
    output_tokens = [
        int(item["metrics"]["usage"].get("completion_tokens"))
        for item in results
        if item["metrics"].get("usage", {}).get("completion_tokens") is not None
    ]
    total_tokens = [
        int(item["metrics"]["usage"].get("total_tokens"))
        for item in results
        if item["metrics"].get("usage", {}).get("total_tokens") is not None
    ]
    costs = [
        float(item["metrics"]["cost_usd"])
        for item in results
        if item["metrics"].get("cost_usd") is not None
    ]
    return {
        "case_count": len(results),
        "reference_resolution_accuracy": rate(references),
        "reference_evaluable_cases": len(references),
        "existing_node_reference_accuracy": rate(available_references),
        "existing_node_reference_evaluable_cases": len(available_references),
        "reference_context_available_cases": sum(
            bool(item["metrics"].get("reference_context_available"))
            for item in results
            if item["metrics"].get("reference_required")
        ),
        "topic_return_accuracy": rate([bool(value) for value in topic_returns]),
        "type_c_strong_decision_recall": rate(type_c),
        "type_d_strong_decision_recall": rate(type_d),
        "weak_agreement_false_decision_rate": rate(weak_agreement),
        "multi_turn_action_accuracy": rate(actions),
        "no_op_accuracy": rate(noops),
        "omitted_relevant_node_safety": rate(omitted_safety),
        "ambiguous_reference_safety": rate(ambiguous_safety),
        "focus_pollution_safety": rate(focus_safety),
        "automatic_confirmation": sum(
            bool(item["metrics"]["automatic_confirmation"]) for item in results
        ),
        "proposed_invented_owner": sum(
            bool(item["metrics"]["proposed_invented_owner"]) for item in results
        ),
        "proposed_invented_due": sum(
            bool(item["metrics"]["proposed_invented_due"]) for item in results
        ),
        "accepted_invented_owner": sum(
            bool(item["metrics"]["accepted_invented_owner"]) for item in results
        ),
        "accepted_invented_due": sum(
            bool(item["metrics"]["accepted_invented_due"]) for item in results
        ),
        "false_strong_decision_count": sum(
            bool(item["metrics"]["false_strong_decision"]) for item in results
        ),
        "false_action_proposed_count": sum(
            bool(item["metrics"].get("false_action_proposed")) for item in results
        ),
        "event_count": sum(int(item["metrics"]["event_count"]) for item in results),
        "context_chars": {
            "min": min((int(item["metrics"]["context_chars"]) for item in results), default=None),
            "max": max((int(item["metrics"]["context_chars"]) for item in results), default=None),
            "average": round(
                sum(int(item["metrics"]["context_chars"]) for item in results) / len(results), 2
            ) if results else None,
        },
        "latency_ms": {
            "p50": percentile(latencies, 0.5),
            "p95": percentile(latencies, 0.95),
            "max": max(latencies) if latencies else None,
            "average": round(sum(latencies) / len(latencies), 3) if latencies else None,
        },
        "tokens": {
            "input": sum(input_tokens),
            "output": sum(output_tokens),
            "total": sum(total_tokens),
        },
        "cost_usd": round(sum(costs), 6),
        "api_success": sum(bool(item["metrics"].get("api_success")) for item in results),
        "analyzer_output_valid": sum(
            bool(item["metrics"].get("analyzer_output_valid")) for item in results
        ),
        "conversion_failures": sum(
            bool(item["metrics"].get("api_success"))
            and not bool(item["metrics"].get("analyzer_output_valid"))
            for item in results
        ),
        "provider_failures": sum(
            not bool(item["metrics"].get("api_success"))
            for item in results
        ),
    }


def pollution_cases(v1: list[dict[str, Any]], v2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    v1_by_id = {item["case_id"]: item for item in v1}
    results: list[dict[str, Any]] = []
    for item in v2:
        if item["case_id"] not in {
            "ctx-007-weak-agreement",
            "ctx-009-noop",
            "ctx-010-ambiguous-reference",
            "ctx-012-omitted-relevant-node",
            "ctx-013-mention-no-focus",
        }:
            continue
        m = item["metrics"]

        def is_polluted(candidate: Mapping[str, Any]) -> bool:
            return (
                bool(candidate["metrics"]["false_strong_decision"])
                or bool(candidate["metrics"].get("false_action_proposed"))
                or not bool(candidate["metrics"]["focus_safe"])
                or bool(candidate["metrics"]["reference_wrong"])
                or (
                    candidate["category"] in {"noop", "ambiguous_reference"}
                    and candidate["metrics"]["event_count"] > 0
                )
            )

        v1_item = v1_by_id[item["case_id"]]
        polluted_v1 = is_polluted(v1_item)
        polluted_v2 = is_polluted(item)
        results.append({
            "case_id": item["case_id"],
            "v1_event_count": v1_item["metrics"]["event_count"],
            "v2_event_count": m["event_count"],
            "v1_polluted": polluted_v1,
            "v2_polluted": polluted_v2,
            "polluted": polluted_v2,
        })
    return results


def build_summary(
    *,
    cases: list[Mapping[str, Any]],
    all_results: Mapping[str, list[dict[str, Any]]],
    run_id: str,
    model: str,
    reasoning_effort: str,
) -> dict[str, Any]:
    pollution = pollution_cases(all_results["v1"], all_results["v2"])
    return {
        "run_id": run_id,
        "prompt_version": PROMPT_VERSION_V4,
        "model": model,
        "reasoning_effort": reasoning_effort,
        "variants": {
            "v1": aggregate(all_results["v1"]),
            "v2": aggregate(all_results["v2"]),
        },
        "context_pollution": {
            "cases": pollution,
            "v1_polluted_cases": sum(item["v1_polluted"] for item in pollution),
            "v2_polluted_cases": sum(item["v2_polluted"] for item in pollution),
            "case_count": len(pollution),
            "v1_rate": round(
                sum(item["v1_polluted"] for item in pollution) / len(pollution), 4
            ) if pollution else None,
            "v2_rate": round(
                sum(item["v2_polluted"] for item in pollution) / len(pollution), 4
            ) if pollution else None,
        },
        "case_comparison": [
            {
                "case_id": case["case_id"],
                "v1_events": len(next(
                    item for item in all_results["v1"]
                    if item["case_id"] == case["case_id"]
                )["canonical_events"]),
                "v2_events": len(next(
                    item for item in all_results["v2"]
                    if item["case_id"] == case["case_id"]
                )["canonical_events"]),
            }
            for case in cases
        ],
    }


def reaggregate_existing(output_dir: Path, dataset_path: Path) -> int:
    """Refresh only derived summary metrics; never calls the provider."""

    dataset = read_json(dataset_path)
    cases = dataset.get("cases", [])
    metadata = read_json(output_dir / "metadata.json")
    cases_by_id = {case["case_id"]: case for case in cases}
    all_results: dict[str, list[dict[str, Any]]] = {"v1": [], "v2": []}
    for variant in all_results:
        for case in cases:
            result_path = output_dir / variant / "cases" / case["case_id"] / "result.json"
            result = read_json(result_path)
            parsed = result.get("parsed_output", {})
            parsed_events = parsed.get("events", []) if isinstance(parsed, Mapping) else []
            raw_action_present = any(
                isinstance(intent, Mapping)
                and intent.get("kind") == "node"
                and intent.get("node_type") == "action"
                for intent in parsed_events
            )
            expected = cases_by_id[case["case_id"]].get("expected", {})
            result["metrics"]["raw_action_present"] = raw_action_present
            result["metrics"]["false_action_proposed"] = (
                raw_action_present and not bool(expected.get("action_expected"))
            )
            write_json(result_path, result)
            all_results[variant].append(result)
    summary = build_summary(
        cases=cases,
        all_results=all_results,
        run_id=output_dir.name,
        model=metadata.get("model", FROZEN_MODEL),
        reasoning_effort=metadata.get("reasoning_effort", FROZEN_REASONING),
    )
    write_json(output_dir / "summary.json", redact(summary))
    print(json.dumps(redact(summary), ensure_ascii=False, indent=2))
    return 0


def run(args: argparse.Namespace) -> int:
    if args.reaggregate_only:
        return reaggregate_existing(args.output_dir, args.dataset)
    dataset = read_json(args.dataset)
    cases = dataset.get("cases", [])
    if not isinstance(cases, list) or not cases:
        raise SystemExit("Context spike dataset has no cases")
    provider = OpenAICompatibleProvider.from_environment()
    if not provider.configured:
        raise SystemExit("Provider is not configured. Load .env in the shell; no API call was made.")
    if provider.model != FROZEN_MODEL:
        raise SystemExit(f"Baseline model mismatch: expected {FROZEN_MODEL}, got {provider.model}")
    if provider.reasoning_effort != FROZEN_REASONING:
        raise SystemExit(
            f"Baseline reasoning mismatch: expected {FROZEN_REASONING}, got {provider.reasoning_effort}"
        )

    validator = SchemaValidator(args.schema_dir)
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        output_dir / "metadata.json",
        {
            "run_id": output_dir.name,
            "run_kind": "context_strategy_spike",
            "dataset_version": dataset.get("dataset_version"),
            "case_count": len(cases),
            "prompt_version": PROMPT_VERSION_V4,
            "model": provider.model,
            "reasoning_effort": provider.reasoning_effort,
            "timeout_seconds": provider.timeout_seconds,
            "context_variants": ["v1", "v2"],
            "v1": "Current Utterance + Goal + Current Topic + Relevant Nodes + Recent Events",
            "v2": "v1 + Previous 1 finalized utterance (speaker, text, evidence_ids)",
            "canonical_contract_changed": False,
            "baseline_runs_reexecuted": False,
            "api_key_stored": False,
        },
    )

    all_results: dict[str, list[dict[str, Any]]] = {"v1": [], "v2": []}
    for variant in ("v1", "v2"):
        for index, case in enumerate(cases, start=1):
            result = evaluate_case(
                case,
                variant=variant,
                output_dir=output_dir,
                validator=validator,
                provider=provider,
            )
            all_results[variant].append(result)
            print(
                f"{variant} {index}/{len(cases)} {case['case_id']} "
                f"status={result['metrics']['status']} events={result['metrics']['event_count']}",
                flush=True,
            )

    summary = build_summary(
        cases=cases,
        all_results=all_results,
        run_id=output_dir.name,
        model=provider.model,
        reasoning_effort=provider.reasoning_effort,
    )
    write_json(output_dir / "summary.json", redact(summary))
    print(json.dumps(redact(summary), ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Context Strategy v1/v2 diagnostic spike")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--schema-dir", type=Path, default=ROOT / "schemas")
    parser.add_argument(
        "--reaggregate-only",
        action="store_true",
        help="Recompute summary.json from saved results without making API calls",
    )
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
