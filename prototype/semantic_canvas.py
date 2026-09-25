"""Deterministic, non-canonical world placement and Auto Camera projection.

Accepted Graph and Event History determine Product positions. Explicit initial
positions are only for synthetic geometry diagnostics, not runtime persistence.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .semantic_projection import focused_flow


VERSION = "semantic-canvas-v2"
SEMANTIC = {"discussion_provenance", "supports", "opposes"}
CELL_X = 440
CELL_Y = 285
ROOT_GAP_X = 1900
ROOT_GAP_Y = 1450


def _event_order(events: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return sorted(events, key=lambda item: (int(item.get("sequence", 0)), str(item.get("event_id", ""))))


def _root_cell(index: int) -> tuple[int, int]:
    """Place currently independent regions on a deterministic outward spiral."""
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


def _proper_cross(a: Mapping[str, Any], b: Mapping[str, Any],
                  c: Mapping[str, Any], d: Mapping[str, Any]) -> bool:
    def side(p: Mapping[str, Any], q: Mapping[str, Any], r: Mapping[str, Any]) -> float:
        return (q["x"] - p["x"]) * (r["y"] - p["y"]) - (q["y"] - p["y"]) * (r["x"] - p["x"])
    return side(a, b, c) * side(a, b, d) < 0 and side(c, d, a) * side(c, d, b) < 0


def _line_hits_card(a: Mapping[str, Any], b: Mapping[str, Any],
                    card: Mapping[str, Any]) -> bool:
    # Conservative world-space footprint of the 390px Live card. A line
    # crossing a third Node is worse than a line-to-line crossing.
    x, y = card["x"], card["y"]
    corners = ({"x": x - 202, "y": y - 95}, {"x": x + 202, "y": y - 95},
               {"x": x + 202, "y": y + 95}, {"x": x - 202, "y": y + 95})
    return any(_proper_cross(a, b, corner, corners[(index + 1) % 4])
               for index, corner in enumerate(corners))


def _conflict_score(node_id: str, positions: Mapping[str, Mapping[str, Any]],
                    edges: Sequence[Mapping[str, Any]]) -> int:
    incident = [edge for edge in edges if node_id in
                (edge["source_node_id"], edge["target_node_id"])]
    score = 0
    for edge in incident:
        source, target = edge["source_node_id"], edge["target_node_id"]
        a, b = positions[source], positions[target]
        for other in edges:
            ends = {other["source_node_id"], other["target_node_id"]}
            if node_id in ends or source in ends or target in ends:
                continue
            if _proper_cross(a, b, positions[other["source_node_id"]],
                             positions[other["target_node_id"]]):
                score += 1
        for other_id, other_pos in positions.items():
            if other_id not in (source, target) and _line_hits_card(a, b, other_pos):
                score += 10
    for edge in edges:
        if node_id in (edge["source_node_id"], edge["target_node_id"]):
            continue
        if _line_hits_card(positions[edge["source_node_id"]],
                           positions[edge["target_node_id"]], positions[node_id]):
            score += 10
    return score


def _repair_new_relation(source_id: str, target_id: str,
                         positions: dict[str, dict[str, Any]],
                         edges: Sequence[Mapping[str, Any]]) -> bool:
    # Try the target first, then the source. Only an actual reduction in
    # crossings/card obstruction permits movement. No force layout or global
    # recentering is used; at most one Node moves per new Relation.
    offsets = ((0, 1), (-1, 0), (1, 0), (0, -1),
               (-1, 1), (1, 1), (-1, -1), (1, -1),
               (0, 2), (-2, 0), (2, 0), (0, -2))
    occupied = {tuple(item["cell"]) for item in positions.values()}
    best: tuple[int, int, int, str, tuple[int, int]] | None = None
    for priority, node_id in enumerate((target_id, source_id)):
        current = positions[node_id]
        baseline = _conflict_score(node_id, positions, edges)
        if not baseline:
            continue
        cx, cy = current["cell"]
        for dx, dy in offsets:
            cell = (cx + dx, cy + dy)
            if cell in occupied:
                continue
            x, y = cell[0] * CELL_X, cell[1] * CELL_Y
            if any(other_id != node_id and abs(other["x"] - x) < 410
                   and abs(other["y"] - y) < 200 for other_id, other in positions.items()):
                continue
            positions[node_id] = {**current, "cell": cell, "x": x, "y": y}
            remaining = _conflict_score(node_id, positions, edges)
            positions[node_id] = current
            if remaining < baseline:
                candidate = (remaining, abs(dx) + abs(dy), priority, node_id, cell)
                if best is None or candidate < best:
                    best = candidate
    if best is None:
        return False
    _, _, _, node_id, cell = best
    positions[node_id] = {**positions[node_id], "cell": cell,
                          "x": cell[0] * CELL_X, "y": cell[1] * CELL_Y}
    return True


def _creation_anchor(node: Mapping[str, Any], events: list[Mapping[str, Any]],
                     creation_sequence: int, known_nodes: set[str],
                     accepted_relations: set[tuple[str, str, str]]) -> tuple[str, str] | None:
    """Use creation-Evidence relations for initial placement; later links may reflow."""
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
        if (source, target, relation) not in accepted_relations:
            continue
        if relation == "discussion_provenance" and target == target_id and source in known_nodes:
            candidates.append((0, int(event["sequence"]), str(source), "child"))
        elif relation in {"supports", "opposes"} and source == target_id and target in known_nodes:
            candidates.append((1, int(event["sequence"]), str(target), relation))
    if not candidates:
        return None
    _, _, anchor, placement = min(candidates)
    return anchor, placement


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
                            *, initial_positions: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Project one world for Live and Final from the accepted Graph and Events.

    ``initial_positions`` permits controlled synthetic geometry tests only.
    Runtime callers omit it, so a cold replay and an incremental render agree.
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
    accepted_relations = {(str(edge["source_node_id"]), str(edge["target_node_id"]), str(edge["type"]))
                          for edge in graph.get("edges", []) if edge.get("type") in SEMANTIC}
    positions: dict[str, dict[str, Any]] = {}
    occupied: set[tuple[int, int]] = set()
    root_count = 0
    for node_id in ordered_nodes:
        if initial_positions is not None and node_id in initial_positions:
            position = initial_positions[node_id]
            cell = tuple(position["cell"])
            positions[node_id] = {**position, "cell": cell}
            occupied.add(cell)
            if position.get("placement") != "linked":
                root_count += 1
            continue
        node = all_nodes[node_id]
        anchor = _creation_anchor(node, ordered, creation[node_id], set(positions), accepted_relations)
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
    edges = [{"id": edge["id"], "source_node_id": edge["source_node_id"],
              "target_node_id": edge["target_node_id"], "type": edge["type"],
              "source_event_ids": tuple(edge.get("source_event_ids") or ())}
             for edge in graph.get("edges", []) if edge.get("type") in SEMANTIC
             and edge.get("source_node_id") in positions and edge.get("target_node_id") in positions]
    accepted = {(edge["source_node_id"], edge["target_node_id"], edge["type"]): edge for edge in edges}
    active: dict[tuple[str, str, str], dict[str, Any]] = {}
    for event in ordered:
        if event.get("event_type") not in {"relation_detected", "correct_relation"}:
            continue
        payload = event.get("payload") or {}
        relation = payload.get("new_relation") if event.get("event_type") == "correct_relation" else payload
        if not relation:
            continue
        source, target = relation.get("source_node_id"), relation.get("target_node_id")
        kind = relation.get("relation_type")
        key = (source, target, kind)
        edge = accepted.get(key)
        if edge is None or key in active:
            continue
        if edge["source_event_ids"] and event.get("event_id") not in edge["source_event_ids"]:
            continue
        active[key] = edge
        sequence = int(event.get("sequence", 0))
        available = {nid: position for nid, position in positions.items() if creation[nid] <= sequence}
        visible_edges = [item for item in active.values()
                         if item["source_node_id"] in available and item["target_node_id"] in available]
        if source in available and target in available and _repair_new_relation(source, target, available, visible_edges):
            positions.update(available)
    # Presentation must not expose Event bookkeeping as a new Relation field.
    edges = [{key: value for key, value in edge.items() if key != "source_event_ids"} for edge in edges]
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
    # Spoken correction and the participant Canvas must share one current
    # discussion target; archived/parked history is not a correction focus.
    semantic_focus = focused_flow(graph, ordered)
    focus_id = semantic_focus["focus_id"]
    focusable = {nid: all_nodes[nid] for nid in all_nodes
                 if all_nodes[nid]["status"] not in {"archived", "parked"}}
    primary = _neighborhood(focus_id, focusable, edges, activity, positions)
    latest_id = semantic_focus["latest_detail"]["id"] if semantic_focus["latest_detail"] else None
    if primary:
        # The 1920x1080 stage is approximately 978px high. Reserve its top and
        # the lower subtitle band before choosing a camera target. If distant
        # context cannot fit at readable scale, omit the least useful neighbor
        # rather than shrink the entire Canvas below the approved 0.74 scale.
        anchor_y, top_center, bottom_center = 978 * .45, 110, 760
        while True:
            xs = [positions[nid]["x"] for nid in primary]
            ys = [positions[nid]["y"] for nid in primary]
            span = max(max(xs) - min(xs), (max(ys) - min(ys)) * 1.45)
            scale = max(0.74, min(1.0, 1000 / max(span + 320, 1)))
            if len(primary) == 1 or (max(ys) - min(ys)) * scale <= bottom_center - top_center:
                break
            primary.pop()
        focus_x, focus_y = positions[focus_id]["x"], positions[focus_id]["y"]
        preferred_y = focus_y + (sum(ys) / len(ys) - focus_y) * 0.5
        lowest_y = max(ys) - (bottom_center - anchor_y) / scale
        highest_y = min(ys) + (anchor_y - top_center) / scale
        live_camera = {"x": focus_x,
                       "y": min(max(preferred_y, lowest_y), highest_y),
                       "scale": scale,
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
