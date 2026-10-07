"""Verify an RFC-0009 Core wheel against the source and synthetic R5 replay.

Usage: python scripts/verify_core_wheel.py WHEEL CLEAN_PYTHON [SDIST]
The supplied interpreter must have the wheel installed and must not have this
repository on PYTHONPATH. Only public controlled corpus data is used.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluation.tooling.semantic_hypothesis_review import build_case
from prototype.commands import HumanCommandHandler
from prototype.layout import StableLayout, map_projection
from prototype.replay import ReplayRunner, canonical_json
from prototype.schema import SchemaValidator
from prototype.service_final_record import prepare_final_record, render_final_pdf


IMPLEMENTATION = (
    "commands", "display_labels", "errors", "fixtures", "layout",
    "materializer", "relation_correction", "replay", "schema",
    "semantic_canvas", "semantic_projection", "service_errors",
    "service_final_record", "shared_projection", "store",
)
SCHEMAS = (
    "analyzer-output-v2.schema.json", "analyzer-output-v3.schema.json",
    "discussion-domain.schema.json", "discussion-event.schema.json",
    "real-analyzer-output.schema.json",
)


def _check_contents(wheel: Path) -> None:
    with ZipFile(wheel) as archive:
        names = set(archive.namelist())
        dist_info = f"ronro_core-{wheel.name.split('-')[1]}.dist-info/"
        allowed_metadata = {dist_info + item for item in (
            "METADATA", "WHEEL", "RECORD", "licenses/LICENSE",
        )}
        required = {
            "ronro_core/__init__.py", "ronro_core/_impl/__init__.py",
            *(f"ronro_core/_impl/{name}.py" for name in IMPLEMENTATION),
            *(f"ronro_core/schemas/{name}" for name in SCHEMAS),
        }
        missing = required - names
        unexpected = names - required - allowed_metadata
        if missing or unexpected:
            raise AssertionError(f"Core wheel inventory mismatch: missing={missing}, unexpected={unexpected}")
        for wrapper in ("ronro_core/__init__.py", "ronro_core/_impl/__init__.py"):
            if (ROOT / wrapper).read_bytes() != archive.read(wrapper):
                raise AssertionError(f"Bundled Core wrapper diverges from source: {wrapper}")
        for name in IMPLEMENTATION:
            source = (ROOT / "prototype" / f"{name}.py").read_bytes()
            installed = archive.read(f"ronro_core/_impl/{name}.py")
            if source != installed:
                raise AssertionError(f"Bundled Core diverges from source: {name}")
        for name in SCHEMAS:
            if (ROOT / "schemas" / name).read_bytes() != archive.read(f"ronro_core/schemas/{name}"):
                raise AssertionError(f"Bundled Schema diverges from source: {name}")


def _check_sdist(sdist: Path) -> None:
    prefix = sdist.name.removesuffix(".tar.gz") + "/"
    allowed = {
        "README.md", "LICENSE", "pyproject.toml", ".gitignore", "PKG-INFO",
        "ronro_core/__init__.py", "ronro_core/_impl/__init__.py",
        *(f"prototype/{name}.py" for name in IMPLEMENTATION),
        *(f"schemas/{name}" for name in SCHEMAS),
    }
    with tarfile.open(sdist, "r:gz") as archive:
        names = {member.name.removeprefix(prefix) for member in archive.getmembers() if member.isfile()}
        missing = allowed - names - {".gitignore"}
        unexpected = names - allowed
        if missing or unexpected:
            raise AssertionError(f"Core sdist inventory mismatch: missing={missing}, unexpected={unexpected}")


def _system_event(session_id: str, sequence: int, kind: str, payload: dict) -> dict:
    return {
        "event_id": f"wheel-check-{sequence}", "session_id": session_id,
        "sequence": sequence, "event_type": kind,
        "occurred_at": "2026-09-23T01:05:00Z", "actor": "system",
        "source_evidence_ids": [], "payload": payload,
    }


def _synthetic_payload() -> dict:
    corpus = json.loads((ROOT / "evaluation/relation-corpus/corpus.json").read_text(encoding="utf-8"))
    case = next(case for case in corpus["controlled_cases"] if case["id"] == "R5")
    classes = json.loads((ROOT / "evaluation/relation-corpus/minimal_model_classification.json").read_text(
        encoding="utf-8"))
    accepted, ids = build_case(case, {pair["id"]: pair["classification"] for pair in classes["pairs"]})
    runner = ReplayRunner(SchemaValidator(ROOT / "schemas"))
    session_id = accepted.state["graph"]["session_id"]
    accepted = HumanCommandHandler(runner).handle(accepted, {
        "command_type": "correct_relation",
        "old_relation": {"source_node_id": ids["r5-n1"], "target_node_id": ids["r5-n3"],
                         "relation_type": "discussion_provenance"},
        "new_relation": None, "declared_independent": True,
        "expected_revision": accepted.state["graph"]["revision"],
        "occurred_at": "2026-09-23T01:00:00Z", "source_evidence_ids": [],
    }).result
    finalizing = len(accepted.events) + 1
    accepted = runner.apply_event(accepted, _system_event(
        session_id, finalizing, "session_finalizing",
        {"last_evidence_sequence": len(accepted.state["evidence"])},
    ))
    accepted = runner.apply_event(accepted, _system_event(
        session_id, finalizing + 1, "session_ended",
        {"drain_status": "complete", "final_graph_revision": finalizing, "pending_analysis": False},
    ))
    return {"session_id": session_id, "evidence": accepted.state["evidence"],
            "utterances": accepted.state["utterances"], "events": accepted.events}


def _source_result(payload: dict) -> dict:
    validator = SchemaValidator(ROOT / "schemas")
    replay = ReplayRunner(validator).replay_events(**payload)
    record = prepare_final_record(replay, final_revision=replay.state["graph"]["revision"],
                                  schema_validator=validator)
    pdf = render_final_pdf(record)
    return {"state": canonical_json(replay.state), "canvas": record["canvas"],
            "projection": map_projection(replay.state, replay.events, StableLayout())["semantic_canvas"],
            "pdf_sha256": hashlib.sha256(pdf).hexdigest()}


WHEEL_CHECK = """
import hashlib, json, sys
import ronro_core as core
payload = json.load(sys.stdin)
validator = core.SchemaValidator(core.bundled_schema_dir())
replay = core.ReplayRunner(validator).replay_events(**payload)
record = core.prepare_final_record(replay, final_revision=replay.state['graph']['revision'],
                                   schema_validator=validator)
pdf = core.render_final_pdf(record)
print(json.dumps({'state': core.canonical_json(replay.state), 'canvas': record['canvas'],
                  'projection': core.map_projection(replay.state, replay.events,
                                                    core.StableLayout())['semantic_canvas'],
                  'pdf_sha256': hashlib.sha256(pdf).hexdigest()}, ensure_ascii=False, sort_keys=True))
"""


def main() -> None:
    if len(sys.argv) not in {3, 4}:
        raise SystemExit("Usage: python scripts/verify_core_wheel.py WHEEL CLEAN_PYTHON [SDIST]")
    wheel, clean_python = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).absolute()
    _check_contents(wheel)
    if len(sys.argv) == 4:
        _check_sdist(Path(sys.argv[3]).resolve())
    payload = _synthetic_payload()
    source = _source_result(payload)
    with tempfile.TemporaryDirectory() as workdir:
        process = subprocess.run(
            [str(clean_python), "-c", WHEEL_CHECK], input=json.dumps(payload, ensure_ascii=False),
            text=True, capture_output=True, cwd=workdir, check=False,
            env={key: value for key, value in os.environ.items() if key != "PYTHONPATH"},
        )
    if process.returncode:
        raise AssertionError(f"Clean-environment Core failed: {process.stderr.strip()}")
    if json.loads(process.stdout) != source:
        raise AssertionError("Core wheel Graph/Canvas/PDF differs from repository source")
    print(f"Core wheel verified: {len(IMPLEMENTATION)} modules, {len(SCHEMAS)} schemas, "
          "identical Graph/Canvas/PDF")


if __name__ == "__main__":
    main()
