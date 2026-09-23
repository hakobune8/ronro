"""Private, real-provider R1–R5 acceptance through Analyzer→Event→Materializer.

Run as a module from the repository root. Never writes the API key, raw audio,
or any public evaluation artifact. Human-reviewed pair labels are not included
in Analyzer input; scoring is a separate step after capture.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from prototype.materializer import initial_state
from prototype.real_analyzer import PROMPT_VERSION_V6, PROMPT_VERSION_V7, PROMPT_VERSION_V8, PROMPT_VERSION_V9, RealAnalyzer
from prototype.replay import ReplayResult, ReplayRunner
from prototype.schema import SchemaValidator

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "evaluation" / "relation-corpus" / "corpus.json"
MODEL = "gpt-5.6-luna"


def load_existing_key(kubeconfig: Path) -> None:
    """Read only the existing secret, keeping its value in process memory."""
    completed = subprocess.run(
        ["kubectl", "--kubeconfig", str(kubeconfig), "--request-timeout=10s",
         "-n", "discussion-map-pilot", "get", "secret", "discussion-map-openai", "-o", "json"],
        capture_output=True, check=True, timeout=20,
    )
    encoded = json.loads(completed.stdout)["data"]["OPENAI_API_KEY"]
    os.environ["OPENAI_API_KEY"] = base64.b64decode(encoded, validate=True).decode("utf-8")


def run_case(case: dict[str, Any], run_number: int, validator: SchemaValidator, prompt_version: str) -> dict[str, Any]:
    sid = f"semantic-acceptance-{case['id'].lower()}-{run_number}"
    runner = ReplayRunner(validator)
    result = ReplayResult(initial_state(sid, [], []), ())
    analyzer = RealAnalyzer.from_environment(
        schema_validator=validator,
        meeting_goal=case["setting"],
        prompt_version=prompt_version,
        output_schema_version="v3",
    )

    def apply(event_type: str, payload: dict[str, Any], refs: list[str], actor: str = "system") -> None:
        nonlocal result
        seq = len(result.events) + 1
        event = {"event_id": f"{sid}:system-{seq}", "session_id": sid, "sequence": seq,
                 "event_type": event_type, "occurred_at": "2026-09-23T00:00:00Z",
                 "actor": actor, "source_evidence_ids": refs, "payload": payload}
        result = runner.apply_event(result, event)

    apply("session_created", {"title": case["archetype"], "goal": case["setting"]}, [])
    apply("session_started", {}, [])
    steps = []
    for index, item in enumerate(case["evidence"], start=1):
        if item.get("kind") == "human_command":
            # A prior Human confirmation is not speech. Do not fabricate its
            # missing candidate Decision or preload a Golden Graph.
            continue
        evidence = {"id": item["id"], "session_id": sid, "sequence": index,
                    "timestamp": f"2026-09-23T00:00:{index:02d}Z",
                    "speaker": item["speaker"], "text": item["text"]}
        utterance = {"id": f"utt-{index:02d}", "session_id": sid, "sequence": index,
                     "evidence_ids": [item["id"]], "text": item["text"],
                     "started_at": evidence["timestamp"], "ended_at": evidence["timestamp"]}
        result.state["evidence"].append(evidence)
        result.state["utterances"].append(utterance)
        candidates = analyzer.analyze(utterance, result.state["graph"], result.events)
        accepted, rejected = [], []
        for candidate in candidates:
            event = candidate.to_event(len(result.events) + 1)
            try:
                result = runner.apply_event(result, event)
                accepted.append(event)
            except Exception as exc:
                rejected.append({"event": event, "error_code": getattr(exc, "code", type(exc).__name__)})
        trace = analyzer.last_trace or {}
        steps.append({"evidence_id": item["id"], "utterance": item["text"],
                      "analyzer_status": trace.get("status"),
                      "validation_error_code": (trace.get("validation_error") or {}).get("code"),
                      "usage": trace.get("usage"), "cost_usd": trace.get("cost_usd"),
                      "raw_output": trace.get("raw_output"),
                      "accepted": accepted, "rejected": rejected})
        print(f"{case['id']} run {run_number} turn {index}: {trace.get('status')} "
              f"accepted={len(accepted)} rejected={len(rejected)}", flush=True)

    validator.validate_domain(result.state)
    return {"case_id": case["id"], "run": run_number, "session_id": sid,
            "model": analyzer.model, "provider": analyzer.provider_name,
            "prompt_version": analyzer.prompt_version,
            "output_schema_version": analyzer.output_schema_version,
            "steps": steps, "graph": result.state["graph"], "events": result.events}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kubeconfig", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--prompt-version", choices=[PROMPT_VERSION_V6, PROMPT_VERSION_V7, PROMPT_VERSION_V8, PROMPT_VERSION_V9], default=PROMPT_VERSION_V6)
    parser.add_argument("--cases", nargs="+", default=["R1", "R2", "R3", "R4", "R5"])
    args = parser.parse_args()
    if args.runs < 1 or not args.output.is_absolute() or ROOT in args.output.parents:
        raise ValueError("Use positive runs and an absolute private output path outside the repository")
    load_existing_key(args.kubeconfig)
    os.environ["REAL_ANALYZER_MODEL"] = MODEL
    os.environ.setdefault("REAL_ANALYZER_REASONING_EFFORT", "medium")
    validator = SchemaValidator(ROOT / "schemas")
    cases = {case["id"]: case for case in json.loads(CORPUS.read_text(encoding="utf-8"))["controlled_cases"]}
    results = []
    for case_id in args.cases:
        for run_number in range(1, args.runs + 1):
            results.append(run_case(cases[case_id], run_number, validator, args.prompt_version))
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps({"results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"completed {len(results)} private runs", flush=True)


if __name__ == "__main__":
    main()
