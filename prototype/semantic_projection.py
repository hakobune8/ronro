"""Opt-in, deterministic semantic-graph projections; no canonical mutations.

WORKING HYPOTHESIS: discussion_provenance expresses discussion origin, not
physical causation. These projections do not replace the deployed six-card UI.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

SEMANTIC = {"discussion_provenance", "supports", "opposes"}
INACTIVE = {"archived", "parked"}
def _ordered(events: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(events, key=lambda event: (event["sequence"], event["event_id"]))


def _node_view(node: Mapping[str, Any], display_labels: Mapping[str, str]) -> dict[str, Any]:
    return {
        "id": node["id"], "type": node["type"], "status": node["status"],
        "label": display_labels.get(node["id"]) or node["label"],
        "canonical": node["label"],
    }


def focused_flow(
    graph: Mapping[str, Any], events: Sequence[dict[str, Any]],
    display_labels: Mapping[str, str] | None = None, *, max_nodes: int = 5,
) -> dict[str, Any]:
    """Show a sparse 3–5-node local neighborhood, without filling for density."""
    if max_nodes < 1:
        raise ValueError("max_nodes must be positive")
    labels = display_labels or {}
    nodes = {n["id"]: n for n in graph["nodes"] if n["type"] != "topic" and n["status"] not in INACTIVE}
    ordered = _ordered(events)
    sequence = {event["event_id"]: event["sequence"] for event in ordered}

    def rank(node_id: str) -> tuple[int, str]:
        node = nodes[node_id]
        return max((sequence.get(e, 0) for e in node.get("source_event_ids", [])), default=0), node_id

    latest_id = max(nodes, key=rank) if nodes else None
    focus_id = latest_id
    last_correction = next((e for e in reversed(ordered) if e["event_type"] == "correct_relation"), None)
    if last_correction and (not latest_id or last_correction["sequence"] > rank(latest_id)[0]):
        relation = last_correction["payload"].get("new_relation") or last_correction["payload"].get("old_relation")
        if relation and relation["target_node_id"] in nodes:
            focus_id = relation["target_node_id"]
    # A later explicit Topic Return may shift location without creating a Node.
    last_focus = next((e for e in reversed(ordered) if e["event_type"] in {"topic_focus_changed", "set_current_topic"}), None)
    if last_focus and (not latest_id or last_focus["sequence"] > rank(latest_id)[0]):
        topic_id = last_focus["payload"].get("topic_id")
        children = {
            edge["target_node_id"] for edge in graph["edges"]
            if edge["type"] in {"contains", "has_option"} and edge["source_node_id"] == topic_id
        } & nodes.keys()
        if children:
            focus_id = max(children, key=rank)
        else:
            # A newly focused Topic with no discussion Node must not keep
            # presenting the prior Topic's last Node as the current point.
            focus_id = None

    if focus_id is None:
        return {"version": "focused-flow-hypothesis-1", "focus_id": None,
                "latest_detail": None, "nodes": [], "edges": [],
                "backbone_edges": [], "argument_edges": [], "recent_unlinked": [], "movement": []}

    candidates: dict[str, int] = {}
    for edge in graph["edges"]:
        if edge["type"] not in SEMANTIC:
            continue
        source, target = edge["source_node_id"], edge["target_node_id"]
        if source not in nodes or target not in nodes:
            continue
        if target == focus_id:
            candidates[source] = min(candidates.get(source, 9), 0 if edge["type"] == "discussion_provenance" else 2)
        elif source == focus_id:
            candidates[target] = min(candidates.get(target, 9), 1 if edge["type"] == "discussion_provenance" else 2)
    direct = set(candidates)
    second_hop_roles: dict[str, str] = {}
    for edge in graph["edges"]:
        if edge["type"] not in SEMANTIC:
            continue
        source, target = edge["source_node_id"], edge["target_node_id"]
        if source in direct and target in nodes and target != focus_id:
            candidates[target] = min(candidates.get(target, 9), 3)
            second_hop_roles.setdefault(target, "descendant" if edge["type"] == "discussion_provenance" else "context")
        if target in direct and source in nodes and source != focus_id:
            candidates[source] = min(candidates.get(source, 9), 3)
            second_hop_roles.setdefault(source, "ancestor" if edge["type"] == "discussion_provenance" else "context")
    neighbor_ids = sorted(candidates, key=lambda node_id: (candidates[node_id], -rank(node_id)[0], node_id))[:max_nodes - 1]
    selected = {focus_id, *neighbor_ids}
    position = {focus_id: "focus"}
    for node_id in neighbor_ids:
        position[node_id] = ("parent" if candidates[node_id] == 0 else
                             "child" if candidates[node_id] == 1 else
                             "argument" if candidates[node_id] == 2 else
                             second_hop_roles.get(node_id, "context"))
    views = [{**_node_view(nodes[node_id], labels), "position": position[node_id]}
             for node_id in [focus_id, *neighbor_ids]]
    edges = [dict(edge) for edge in graph["edges"] if edge["type"] in SEMANTIC
             and edge["source_node_id"] in selected and edge["target_node_id"] in selected]
    # A sparse semantic graph must not look like a one-point meeting. Show
    # recent discussion separately, without inventing semantic connections.
    current_topic_id = graph.get("current_topic", {}).get("primary_topic_id")
    topic_members = {edge["target_node_id"] for edge in graph["edges"]
                     if edge["type"] in {"contains", "has_option"}
                     and edge["source_node_id"] == current_topic_id}
    recent_unlinked = []
    if not edges:
        discussion_ids = {node_id for node_id, node in nodes.items()
                          if node["type"] in {"idea", "option", "concern"}}
        recent_ids = (discussion_ids & topic_members) if topic_members else discussion_ids
        recent_ids -= selected
        recent_unlinked = [_node_view(nodes[node_id], labels) for node_id in
                           sorted(recent_ids, key=lambda node_id: (-rank(node_id)[0], node_id))[:2]]
    movement = [{"sequence": e["sequence"], "event_type": e["event_type"]}
                for e in ordered if e["event_type"] in {"topic_focus_changed", "set_current_topic"}]
    return {"version": "focused-flow-hypothesis-1", "focus_id": focus_id,
            "latest_detail": _node_view(nodes[latest_id], {}) if latest_id else None,
            "nodes": views, "edges": edges,
            "backbone_edges": [edge for edge in edges if edge["type"] == "discussion_provenance"],
            "argument_edges": [edge for edge in edges if edge["type"] in {"supports", "opposes"}],
            "recent_unlinked": recent_unlinked,
            "movement": movement}


def final_discussion_map(
    graph: Mapping[str, Any], events: Sequence[dict[str, Any]],
    display_labels: Mapping[str, str] | None = None, *, overview_limit: int = 12,
) -> dict[str, Any]:
    """Multi-root overview plus all Canonical details and separate chronology."""
    labels = display_labels or {}
    nodes = {n["id"]: n for n in graph["nodes"] if n["type"] != "topic" and n["status"] not in INACTIVE}
    semantic = [dict(edge) for edge in graph["edges"] if edge["type"] in SEMANTIC
                and edge["source_node_id"] in nodes and edge["target_node_id"] in nodes]
    incoming = {edge["target_node_id"] for edge in semantic if edge["type"] == "discussion_provenance"}
    roots = sorted(set(nodes) - incoming, key=lambda nid: (nodes[nid].get("created_at") or "", nid))
    declared = {event["payload"]["old_relation"]["target_node_id"]
                for event in events if event["event_type"] == "correct_relation"
                and event["payload"].get("declared_independent")
                and event["payload"].get("old_relation")}
    # No incoming provenance alone does not verify independence. An explicit
    # Human correction does; all other entries remain conservative candidates.
    verified_roots = [node_id for node_id in roots if node_id in declared]
    unlinked = [node_id for node_id in roots if node_id not in declared]
    children: dict[str, list[str]] = {}
    for edge in semantic:
        if edge["type"] == "discussion_provenance":
            children.setdefault(edge["source_node_id"], []).append(edge["target_node_id"])
    overview: list[str] = []
    pending = list(roots)
    while pending and len(overview) < overview_limit:
        nid = pending.pop(0)
        if nid in overview:
            continue
        overview.append(nid)
        pending.extend(sorted(children.get(nid, [])))
    chosen = set(overview)
    return {
        "version": "final-map-hypothesis-1",
        "roots": roots,
        "verified_roots": verified_roots,
        "unlinked": unlinked,
        "overview": [_node_view(nodes[nid], labels) for nid in overview],
        "overview_edges": [e for e in semantic if e["source_node_id"] in chosen and e["target_node_id"] in chosen],
        "hidden_detail_count": len(nodes) - len(overview),
        "detail": [_node_view(nodes[nid], {}) for nid in sorted(nodes)],
        "semantic_edges": semantic,
        "chronology": [{"sequence": e["sequence"], "event_type": e["event_type"]}
                       for e in _ordered(events) if e["event_type"] in
                       {"node_detected", "topic_focus_changed", "set_current_topic"}],
    }
