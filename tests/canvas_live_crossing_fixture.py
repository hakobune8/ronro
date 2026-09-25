"""Public-safe synthetic Live Canvas crossing/reflow progression."""

from __future__ import annotations

import copy
import json

from prototype.layout import StableLayout, map_projection
from prototype.semantic_canvas import CELL_X, CELL_Y


def build_crossing_scenes() -> list[dict]:
    cells = {"issue": (0, 0), "option": (1, 1), "concern": (0, 1), "open": (1, 0)}
    labels = {"issue": ("concern", "三避難所で飲料水が不足"),
              "option": ("option", "倉庫の水を再配置する"),
              "concern": ("concern", "輸送路が一部通行止め"),
              "open": ("open_item", "三避難所への配送経路が未確認")}
    nodes = [{"id": node_id, "type": kind, "status": "active", "label": label,
              "created_at": f"2026-09-25T00:0{index}:00Z",
              "updated_at": f"2026-09-25T00:0{index}:00Z",
              "evidence_ids": [f"synthetic-{node_id}"], "source_event_ids": [f"node-{node_id}"]}
             for index, (node_id, (kind, label)) in enumerate(labels.items(), 1)]
    events = [{"event_id": f"node-{node['id']}", "sequence": index,
               "event_type": "node_detected", "source_evidence_ids": node["evidence_ids"],
               "payload": {"node_type": node["type"], "label": node["label"]}}
              for index, node in enumerate(nodes, 1)]

    def relation(source: str, target: str, sequence: int) -> dict:
        event_id = f"relation-{source}-{target}"
        events.append({"event_id": event_id, "sequence": sequence,
                       "event_type": "relation_detected",
                       "source_evidence_ids": [f"synthetic-{target}"],
                       "payload": {"source_node_id": source, "target_node_id": target,
                                   "relation_type": "discussion_provenance"}})
        return {"id": event_id, "type": "discussion_provenance",
                "source_node_id": source, "target_node_id": target,
                "source_event_ids": [event_id]}

    edges = [relation("issue", "option", 5), relation("issue", "open", 6)]
    layout = StableLayout()
    layout._canvas_placements.update({node_id: {"cell": cell, "x": cell[0] * CELL_X,
                                                 "y": cell[1] * CELL_Y,
                                                 "placement": "unconfirmed"}
                                      for node_id, cell in cells.items()})
    layout._canvas_placements["__canvas_layout_meta__"] = {"last_relation_sequence": 6}

    def snapshot(revision: int) -> dict:
        graph = {"session_id": "synthetic-live-crossing", "revision": revision,
                 "nodes": copy.deepcopy(nodes), "edges": copy.deepcopy(edges),
                 "current_topic": {"primary_topic_id": None}}
        state = {"session": {"id": "synthetic-live-crossing", "title": "防災対応の検討会"},
                 "graph": graph}
        projected = map_projection(state, copy.deepcopy(events), layout)
        projected["shared"] = {}
        return {"state": state, "map": projected, "live_state": {"runtime_state": "active"}}

    before = snapshot(6)
    edges.append(relation("concern", "open", 7))
    after = snapshot(7)
    return [before, after]


if __name__ == "__main__":
    print(json.dumps(build_crossing_scenes(), ensure_ascii=False))
