"""Score private real-Analyzer R1–R5 runs after generation, never as model input.

Evidence-linked Node matching is a diagnostic proxy, not semantic Ground Truth.
Unmatched and unlisted edges remain for Human review rather than being scored
as false by default.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = {"provenance": "discussion_provenance", "supports": "supports", "opposes": "opposes"}


def score_run(run: dict[str, Any], case: dict[str, Any], classifications: dict[str, str]) -> dict[str, Any]:
    events = {event["event_id"]: event for event in run["events"]}
    nodes = [node for node in run["graph"]["nodes"] if node["type"] != "topic"]
    refs = {node["id"]: {eid for event_id in node["source_event_ids"]
                         for eid in events[event_id]["source_evidence_ids"]} for node in nodes}
    mapping: dict[str, str] = {}
    ambiguous: list[str] = []
    for target in case["nodes"]:
        anchor = target["evidence_ids"][0]
        matches = [node for node in nodes if anchor in refs[node["id"]]]
        if len(matches) == 1:
            mapping[target["id"]] = matches[0]["id"]
        elif matches:
            typed = [node for node in matches if node["type"] == target["type"]]
            if len(typed) == 1:
                mapping[target["id"]] = typed[0]["id"]
            else:
                ambiguous.append(target["id"])
    edges = {(edge["source_node_id"], edge["target_node_id"], edge["type"])
             for edge in run["graph"]["edges"] if edge["type"] in EXPECTED.values()}
    compared = []
    matched_edges: set[tuple[str, str, str]] = set()
    for pair in case["candidate_pairs"]:
        source, target = mapping.get(pair["source"]), mapping.get(pair["target"])
        if source is None or target is None:
            compared.append({"pair": pair["id"], "status": "endpoint_unmatched"})
            continue
        expected = classifications[pair["id"]]
        found = sorted(kind for a, b, kind in edges if a == source and b == target)
        if expected in EXPECTED:
            hit = EXPECTED[expected] in found
            if hit:
                matched_edges.add((source, target, EXPECTED[expected]))
            status = "hit" if hit else "miss"
        else:
            status = "unexpected_direct_edge" if found else "correctly_unconnected"
        compared.append({"pair": pair["id"], "status": status, "expected": expected, "found": found})
    outside = [edge for edge in edges if edge not in matched_edges and not any(
        item.get("status") == "unexpected_direct_edge" and
        item["pair"] == pair["id"] for item in compared for pair in case["candidate_pairs"]
        if mapping.get(pair["source"]) == edge[0] and mapping.get(pair["target"]) == edge[1])]
    return {"case": case["id"], "run": run["run"], "node_matches": len(mapping),
            "node_total": len(case["nodes"]), "ambiguous_nodes": ambiguous,
            "generated_semantic_edges": len(edges), "pairs": compared,
            "outside_candidate_pairs": [list(edge) for edge in outside]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.output.is_absolute() or ROOT in args.output.parents:
        raise ValueError("Scored artifact must be private and outside the repository")
    corpus = {case["id"]: case for case in json.loads(
        (ROOT / "evaluation/relation-corpus/corpus.json").read_text())["controlled_cases"]}
    classifications = {pair["id"]: pair["classification"] for pair in json.loads(
        (ROOT / "evaluation/relation-corpus/minimal_model_classification.json").read_text())["pairs"]}
    runs = json.loads(args.input.read_text())["results"]
    scored = [score_run(run, corpus[run["case_id"]], classifications) for run in runs]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"scores": scored}, ensure_ascii=False, indent=2))
    summary: dict[str, int] = {}
    for run in scored:
        for pair in run["pairs"]:
            summary[pair["status"]] = summary.get(pair["status"], 0) + 1
    print(json.dumps({"runs": len(scored), "pair_status": summary,
                      "extra_edges_needing_review": sum(len(run["outside_candidate_pairs"]) for run in scored)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
