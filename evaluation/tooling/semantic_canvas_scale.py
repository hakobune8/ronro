"""Synthetic Canvas latency/replay probe; no meeting or Provider data is used.

Run from the repository root with ``PYTHONPATH=. python evaluation/tooling/semantic_canvas_scale.py``.
The workload intentionally includes many late links, which exercise the
expensive accepted-Graph re-layout path rather than only an unchanged cache.
"""

from __future__ import annotations

import json
import statistics
import time

from prototype.layout import StableLayout
from prototype.semantic_canvas import project_semantic_canvas


def graph_at(size: int) -> tuple[dict, list[dict]]:
    nodes = [{"id": f"n{i}", "type": "idea", "status": "active",
              "label": f"合成論点 {i}", "source_event_ids": [f"node-{i}"]}
             for i in range(size)]
    events = [{"event_id": f"node-{i}", "sequence": i + 1,
               "event_type": "node_detected", "payload": {}}
              for i in range(size)]
    edges = []
    for i in range(1, size):
        parent = (i - 1) // 2
        event_id = f"relation-{i}"
        relation = {"source_node_id": f"n{parent}", "target_node_id": f"n{i}",
                    "relation_type": "discussion_provenance"}
        edges.append({"id": event_id, "type": relation["relation_type"],
                      "source_node_id": relation["source_node_id"],
                      "target_node_id": relation["target_node_id"],
                      "source_event_ids": [event_id]})
        events.append({"event_id": event_id, "sequence": size + i,
                       "event_type": "relation_detected", "payload": relation})
    return {"session_id": "synthetic-scale", "revision": size, "nodes": nodes,
            "edges": edges, "current_topic": {"primary_topic_id": None}}, events


def elapsed(call):
    started = time.perf_counter()
    value = call()
    return value, round(time.perf_counter() - started, 4)


def main() -> None:
    results = []
    for size in (100, 300, 600, 1000):
        graph, events = graph_at(size)
        layout = StableLayout()
        cold, cold_seconds = elapsed(lambda: layout.canvas_projection(graph, events, {}))
        warm, warm_seconds = elapsed(lambda: layout.canvas_projection(graph, events, {}))
        assert cold == warm
        # An explicit Human correction removes one late link. Reconstruct and
        # compare with a fresh projector to catch session-state dependence.
        graph["edges"] = graph["edges"][:-1]
        graph["revision"] += 1
        events.append({"event_id": "human-correction", "sequence": size * 2,
                       "event_type": "correct_relation",
                       "payload": {"old_relation": {"source_node_id": f"n{(size - 2) // 2}",
                                                    "target_node_id": f"n{size - 1}",
                                                    "relation_type": "discussion_provenance"},
                                   "new_relation": None, "declared_independent": True}})
        corrected, correction_seconds = elapsed(lambda: layout.canvas_projection(graph, events, {}))
        assert corrected == project_semantic_canvas(graph, events)
        results.append({"nodes": size, "relations_before_correction": size - 1,
                        "cold_seconds": cold_seconds, "warm_seconds": warm_seconds,
                        "correction_seconds": correction_seconds,
                        "cold_replay_equal": True})
    print(json.dumps({"workload": "synthetic_late_link_tree", "results": results,
                      "median_cold_seconds": statistics.median(item["cold_seconds"] for item in results)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
