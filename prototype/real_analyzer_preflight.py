"""Run the frozen five-case preflight for a versioned Real Analyzer prompt."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .real_analyzer import (
    PROMPT_VERSION_V2,
    PROMPT_VERSION_V3,
    PROMPT_VERSION_V4,
    PROMPT_VERSION_V5,
    OpenAICompatibleProvider,
    RealAnalyzer,
)
from .recorded import RecordedScenarioLoader
from .replay import ReplayRunner
from .schema import SchemaValidator


CASES_V2_V3 = (
    ("scenario-a-mvp", "real-a-u001", "empty"),
    ("scenario-a-mvp", "real-a-u004", "empty"),
    ("scenario-a-mvp", "real-a-u007", "empty"),
    ("scenario-b-architecture", "real-b-u001", "empty"),
    ("scenario-e-topic-return", "real-e-u005", "topic_return"),
)

CASES_V4 = (
    ("scenario-b-architecture", "real-b-u006", "empty"),
    ("scenario-e-topic-return", "real-e-u001", "empty"),
    ("scenario-b-architecture", "real-b-u004", "empty"),
    ("scenario-d-disagreement", "real-d-u003", "empty"),
    ("scenario-c-brainstorm", "real-c-u001", "empty"),
)


def graph_for_case(kind: str) -> dict[str, Any]:
    if kind == "topic_return":
        return {
            "nodes": [
                {"id": "topic-mvp", "type": "topic", "label": "MVP範囲", "status": "active"},
                {"id": "topic-price", "type": "topic", "label": "価格モデル", "status": "active"},
            ],
            "edges": [],
            "current_topic": {"primary_topic_id": "topic-price", "mode": "derived"},
        }
    return {"nodes": [], "edges": [], "current_topic": {"primary_topic_id": None, "mode": "derived"}}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario-dir", type=Path, default=Path("evaluation/real-analyzer"))
    parser.add_argument("--schema-dir", type=Path, default=Path("schemas"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--prompt-version",
        choices=[PROMPT_VERSION_V2, PROMPT_VERSION_V3, PROMPT_VERSION_V4, PROMPT_VERSION_V5],
        default=PROMPT_VERSION_V4,
    )
    args = parser.parse_args()

    validator = SchemaValidator(args.schema_dir)
    runner = ReplayRunner(validator)
    scenarios = {scenario.scenario_id: scenario for scenario in RecordedScenarioLoader(args.scenario_dir).load_all()}
    provider = OpenAICompatibleProvider.from_environment()
    analyzer = RealAnalyzer(
        provider=provider,
        schema_validator=validator,
        prompt_version=args.prompt_version,
        output_schema_version="v2",
    )
    results = []
    cases = CASES_V4 if args.prompt_version in {PROMPT_VERSION_V4, PROMPT_VERSION_V5} else CASES_V2_V3
    for scenario_id, utterance_id, graph_kind in cases:
        scenario = scenarios[scenario_id]
        utterance = next(item for item in scenario.utterances if item["id"] == utterance_id)
        candidates = analyzer.analyze(utterance, graph_for_case(graph_kind), [])
        trace = analyzer.last_trace or {}
        error_code = (trace.get("validation_error") or {}).get("code")
        results.append(
            {
                "scenario": scenario_id,
                "utterance_id": utterance_id,
                "text": utterance["text"],
                "status": trace.get("status"),
                "api_success": error_code != "provider_http_error",
                "json_parse_success": error_code not in {"provider_output_invalid"},
                "analyzer_output_schema_valid": error_code not in {"schema_invalid"},
                "canonical_conversion_success": error_code is None,
                "canonical_event_schema_valid": error_code is None,
                "event_types": [candidate.event_type for candidate in candidates],
                "events_emitted": len(candidates),
                "trace": trace,
            }
        )

    summary = {
        "prompt_version": args.prompt_version,
        "analyzer_schema_version": "v2",
        "case_count": len(results),
        "all_api_success": all(item["api_success"] for item in results),
        "all_json_parse_success": all(item["json_parse_success"] for item in results),
        "all_analyzer_schema_valid": all(item["analyzer_output_schema_valid"] for item in results),
        "all_canonical_conversion_success": all(item["canonical_conversion_success"] for item in results),
        "all_canonical_event_schema_valid": all(item["canonical_event_schema_valid"] for item in results),
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key != "results"}, ensure_ascii=False))
    return 0 if all(summary[key] for key in (
        "all_api_success",
        "all_json_parse_success",
        "all_analyzer_schema_valid",
        "all_canonical_conversion_success",
        "all_canonical_event_schema_valid",
    )) else 1


if __name__ == "__main__":
    raise SystemExit(main())
