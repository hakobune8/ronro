"""Deterministic, non-canonical world placement and Auto Camera projection.

The world is append-only in spatial identity: accepted late Relations and Human
corrections change connectors, never the placement chosen at Node creation.
This is a presentation hypothesis, not a new Canonical Graph contract.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping, Sequence


VERSION = "semantic-canvas-v1"
SEMANTIC = {"discussion_provenance", "supports", "opposes"}
CELL_X = 440
CELL_Y = 285
ROOT_GAP_X = 1900
ROOT_GAP_Y = 1450


def _event_order(events: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return sorted(events, key=lambda item: (int(item.get("sequence", 0)), str(item.get("event_id", ""))))


def _root_cell(index: int) -> tuple[int, int]:
    """An outward square spiral; adding a Root never relocates old regions."""
    if index == 0:
        return 0, 0
    x = y = 0
    dx, dy = 1, 0
    step_limit = 1
    steps = turns = 0
    for _ in range(index):
        x += dx
        y += dy
        steps += 1
        if steps == step_limit:
            dx, dy = -dy, dx
            steps = 0
            turns += 1
            if turns % 2 == 0:
                step_limit += 1
    return x, y


def _first_free(preferred: tuple[int, int], occupied: set[tuple[int, int]],
                *, direction: str = "down") -> tuple[int, int]:
    x, y = preferred
    if preferred not in occupied:
        return preferred
    # Try nearby positions without disturbing placements already committed.
    for radius in range(1, 1000):
        candidates = ([(x + side * radius, y + offset) for offset in range(-radius, radius + 1)
                       for side in (-1, 1)] if direction == "side" else
                      [(x + offset, y + radius) for offset in range(-radius, radius + 1)] +
                      [(x + offset, y - radius) for offset in range(-radius, radius + 1)])
        for cell in candidates:
            if cell not in occupied:
                return cell
    raise ValueError("Canvas placement capacity exhausted")


def _creation_anchor(node: Mapping[str, Any], events: list[Mapping[str, Any]],
                     creation_sequence: int, known_nodes: set[str]) -> tuple[str, str] | None:
    """Use only creation-Evidence relations; late links cannot move the Node."""
    refs = set(node.get("evidence_ids") or ())
    target_id = str(node["id"])
    candidates: list[tuple[int, int, str, str]] = []
    for event in events:
        if event.get("event_type") != "relation_detected" or not refs.intersection(event.get("source_evidence_ids") or ()):
            continue
        payload = event.get("payload") or {}
        relation = payload.get("relation_type")
        if relation not in SEMANTIC or int(event.get("sequence", 0)) < creation_sequence:
            continue
        source, target = payload.get("source_node_id"), payload.get("target_node_id")
        if relation == "discussion_provenance" and target == target_id and source in known_nodes:
            candidates.append((0, int(event["sequence"]), str(source), "child"))
        elif relation in {"supports", "opposes"} and source == target_id and target in known_nodes:
            candidates.append((1, int(event["sequence"]), str(target), relation))
    if not candidates:
        return None
    _, _, anchor, placement = min(candidates)
    return anchor, placement


def _focus(graph: Mapping[str, Any], events: list[Mapping[str, Any]],
           nodes: Mapping[str, Mapping[str, Any]], activity: Mapping[str, int]) -> str | None:
    if not nodes:
        return None
    focus_id = max(nodes, key=lambda node_id: (activity[node_id], node_id))
    focus_seq = activity[focus_id]
    membership: dict[str, set[str]] = defaultdict(set)
    for edge in graph.get("edges", []):
        if edge.get("type") in {"contains", "has_option"}:
            membership[str(edge["source_node_id"])].add(str(edge["target_node_id"]))
    for event in events:
        sequence = int(event.get("sequence", 0))
        if sequence <= focus_seq:
            continue
        kind = event.get("event_type")
        payload = event.get("payload") or {}
        if kind == "correct_relation":
            relation = payload.get("new_relation") or payload.get("old_relation")
            if relation and relation.get("target_node_id") in nodes:
                focus_id, focus_seq = relation["target_node_id"], sequence
        elif kind in {"topic_focus_changed", "set_current_topic"}:
            members = membership.get(str(payload.get("topic_id")), set()) & nodes.keys()
            # A newly opened empty Topic has no Node to duplicate as focus.
            focus_id = max(members, key=lambda nid: (activity[nid], nid)) if members else None
            focus_seq = sequence
    return focus_id


def _neighborhood(focus_id: str | None, nodes: Mapping[str, Any], edges: list[dict[str, Any]],
                  activity: Mapping[str, int], positions: Mapping[str, Mapping[str, Any]],
                  limit: int = 5) -> list[str]:
    if focus_id is None:
        return []
    def close(node_id: str) -> bool:
        dx = positions[node_id]["x"] - positions[focus_id]["x"]
        dy = positions[node_id]["y"] - positions[focus_id]["y"]
        return dx * dx + dy * dy <= 1000 * 1000

    rank: dict[str, int] = {}
    for edge in edges:
        source, target = edge["source_node_id"], edge["target_node_id"]
        if source not in nodes or target not in nodes:
            continue
        if target == focus_id and close(source):
            rank[source] = min(rank.get(source, 9), 0 if edge["type"] == "discussion_provenance" else 2)
        elif source == focus_id and close(target):
            rank[target] = min(rank.get(target, 9), 1 if edge["type"] == "discussion_provenance" else 2)
    selected = [focus_id]
    selected.extend(sorted(rank, key=lambda nid: (rank[nid], -activity[nid], nid))[:limit - 1])
    if len(selected) < limit:
        second_hop: set[str] = set()
        for edge in edges:
            if edge["source_node_id"] in selected and edge["target_node_id"] in nodes:
                second_hop.add(edge["target_node_id"])
            if edge["target_node_id"] in selected and edge["source_node_id"] in nodes:
                second_hop.add(edge["source_node_id"])
        selected.extend(sorted((nid for nid in second_hop - set(selected) if close(nid)),
                               key=lambda nid: (-activity[nid], nid))[:limit - len(selected)])
    return selected


def project_semantic_canvas(graph: Mapping[str, Any], events: Sequence[Mapping[str, Any]],
                            display_labels: Mapping[str, str] | None = None,
                            placement_state: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """Project one world for Live and Final, retaining optional Presentation placements.

    ``placement_state`` belongs to a session's Projection, never to Canonical
    Nodes. A later Relation can therefore change connectors without relocating
    a Node that participants have already seen.
    """
    ordered = _event_order(events)
    by_event = {str(event.get("event_id")): int(event.get("sequence", 0)) for event in ordered}
    event_times = {str(event.get("event_id")): event.get("occurred_at") for event in ordered}
    labels = display_labels or {}
    all_nodes = {str(node["id"]): node for node in graph.get("nodes", []) if node.get("type") != "topic"}
    creation = {nid: min((by_event[event_id] for event_id in node.get("source_event_ids", ()) if event_id in by_event),
                         default=0) for nid, node in all_nodes.items()}
    activity = {nid: max((by_event[event_id] for event_id in node.get("source_event_ids", ()) if event_id in by_event),
                         default=creation[nid]) for nid, node in all_nodes.items()}
    ordered_nodes = sorted(all_nodes, key=lambda nid: (creation[nid], nid))
    declared_independent = {str((event.get("payload") or {}).get("old_relation", {}).get("target_node_id"))
                            for event in ordered if event.get("event_type") == "correct_relation"
                            and (event.get("payload") or {}).get("declared_independent")
                            and (event.get("payload") or {}).get("old_relation")}
    positions: dict[str, dict[str, Any]] = {}
    occupied: set[tuple[int, int]] = set()
    root_count = 0
    for node_id in ordered_nodes:
        if placement_state is not None and node_id in placement_state:
            position = placement_state[node_id]
            cell = tuple(position["cell"])
            positions[node_id] = {**position, "cell": cell}
            occupied.add(cell)
            if position.get("placement") != "linked":
                root_count += 1
            continue
        node = all_nodes[node_id]
        anchor = _creation_anchor(node, ordered, creation[node_id], set(positions))
        if anchor:
            parent, placement = anchor
            px, py = positions[parent]["cell"]
            if placement == "child":
                preferred = (px, py + 1)
                direction = "down"
            elif placement == "supports":
                preferred = (px - 1, py)
                direction = "side"
            else:
                preferred = (px + 1, py)
                direction = "side"
            kind = "linked"
        else:
            rx, ry = _root_cell(root_count)
            preferred = (rx * (ROOT_GAP_X // CELL_X), ry * (ROOT_GAP_Y // CELL_Y))
            direction = "side"
            root_count += 1
            kind = "independent" if node_id in declared_independent else "unconfirmed"
        cell = _first_free(preferred, occupied, direction=direction)
        occupied.add(cell)
        positions[node_id] = {"cell": cell, "x": cell[0] * CELL_X, "y": cell[1] * CELL_Y,
                              "placement": kind, "placement_anchor_id": anchor[0] if anchor else None}
        if placement_state is not None:
            placement_state[node_id] = dict(positions[node_id])

    edges = [{"id": edge["id"], "source_node_id": edge["source_node_id"],
              "target_node_id": edge["target_node_id"], "type": edge["type"]}
             for edge in graph.get("edges", []) if edge.get("type") in SEMANTIC
             and edge.get("source_node_id") in positions and edge.get("target_node_id") in positions]
    incoming = {edge["target_node_id"] for edge in edges if edge["type"] == "discussion_provenance"}
    views = []
    for node_id in ordered_nodes:
        node = all_nodes[node_id]
        source_events = [event_id for event_id in node.get("source_event_ids", ()) if event_id in by_event]
        latest_source = max(source_events, key=lambda event_id: by_event[event_id]) if source_events else None
        time_at = node.get("updated_at") or (event_times.get(latest_source) if latest_source else None)
        time_at = time_at or node.get("created_at")
        root_state = ("linked" if node_id in incoming else
                      "independent" if node_id in declared_independent else "unconfirmed")
        views.append({"id": node_id, "x": positions[node_id]["x"], "y": positions[node_id]["y"],
                      "type": node["type"], "status": node["status"],
                      "label": labels.get(node_id) or node["label"], "canonical": node["label"],
                      "time_at": time_at,
                      "root_state": root_state, "created_sequence": creation[node_id],
                      "activity_sequence": activity[node_id]})
    focus_id = _focus(graph, ordered, all_nodes, activity)
    primary = _neighborhood(focus_id, all_nodes, edges, activity, positions)
    latest_id = max(all_nodes, key=lambda nid: (activity[nid], nid)) if all_nodes else None
    if primary:
        xs = [positions[nid]["x"] for nid in primary]
        ys = [positions[nid]["y"] for nid in primary]
        # Keep focus horizontally centered. Vertically, reserve room for a
        # provenance parent above and the bounded Canonical subtitle below.
        focus_x, focus_y = positions[focus_id]["x"], positions[focus_id]["y"]
        span = max(max(xs) - min(xs), (max(ys) - min(ys)) * 1.45)
        live_camera = {"x": focus_x,
                       "y": focus_y + (sum(ys) / len(ys) - focus_y) * 0.5,
                       "scale": max(0.74, min(1.0, 1000 / max(span + 320, 1))),
                       "focus_id": focus_id}
    else:
        live_camera = {"x": 0, "y": 0, "scale": 1.0, "focus_id": None}
    # The final camera sees the same world; semantic zoom prevents tiny cards.
    if views:
        xs = [item["x"] for item in views]
        ys = [item["y"] for item in views]
        final_camera = {"x": (min(xs) + max(xs)) / 2, "y": (min(ys) + max(ys)) / 2,
                        "scale": max(0.01, min(0.85, 1270 / max(max(xs) - min(xs) + 440,
                                                                  (max(ys) - min(ys) + 280) * 1.35)))}
    else:
        final_camera = {"x": 0, "y": 0, "scale": 1.0}
    return {"version": VERSION, "session_id": graph.get("session_id"), "revision": graph.get("revision"),
            "nodes": views, "edges": edges, "focus_id": focus_id, "near_ids": primary,
            "latest_detail_id": latest_id, "live_camera": live_camera, "final_camera": final_camera,
            "root_ids": [item["id"] for item in views if item["root_state"] == "independent"],
            "unconfirmed_ids": [item["id"] for item in views if item["root_state"] == "unconfirmed"]}
