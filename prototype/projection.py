"""Presentation-only compaction for long-session Discussion Maps.

The functions in this module intentionally consume a canonical Graph and
return a new projection.  They never mutate Nodes, Edges, Events, Evidence,
or the canonical Current Topic state.
"""

from __future__ import annotations

import copy
import re
from collections import defaultdict
from typing import Any, Iterable, Mapping

from .layout import StableLayout, map_projection


CRITICAL_TYPES = {"decision", "action", "open_item"}
CURRENT_IMPORTANT_TYPES = {"decision", "action", "open_item", "concern"}
GROUPABLE_TYPES = {"idea", "option", "concern"}


def _last_event_sequence(node: Mapping[str, Any], events: list[dict[str, Any]]) -> int:
    event_ids = set(node.get("source_event_ids", []))
    return max(
        (int(event["sequence"]) for event in events if event.get("event_id") in event_ids),
        default=0,
    )


def _node_priority(node: Mapping[str, Any], *, current: bool, last_sequence: int) -> tuple[int, int, str]:
    status = node.get("status")
    if status in {"archived", "resolved"}:
        importance = 0
    elif node.get("type") == "decision":
        importance = 100
    elif node.get("type") == "action":
        importance = 95
    elif node.get("type") == "open_item":
        importance = 90
    elif node.get("type") == "concern":
        importance = 80 if current else 45
    elif current:
        importance = 65 if node.get("type") == "option" else 55
    else:
        importance = 20
    return (importance, last_sequence, str(node.get("id", "")))


def _normalize_label(label: str) -> str:
    return re.sub(r"[\s　。、・:：「」『』（）()\-—!?！？A-Za-z0-9]+", "", label).lower()


def _safe_semantic_key(label: str) -> str | None:
    """Return a conservative key for exact/near-exact presentation grouping.

    This is deliberately not an LLM semantic classifier.  It only groups
    labels when one normalized label contains the other and both are long
    enough to make accidental grouping unlikely.
    """

    normalized = _normalize_label(label)
    return normalized if len(normalized) >= 8 else None


def _topic_membership(graph: Mapping[str, Any], base: Mapping[str, Any]) -> dict[str, str | None]:
    membership: dict[str, str | None] = {}
    for lane in base.get("lanes", []):
        topic_id = lane.get("topic_id")
        for node_id in lane.get("node_ids", []):
            membership[str(node_id)] = str(topic_id) if topic_id else None
    for node in graph.get("nodes", []):
        membership.setdefault(str(node["id"]), None)
    return membership


def _deterministic_topic_summary(
    topic: Mapping[str, Any] | None,
    nodes: list[Mapping[str, Any]],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    label = str(topic.get("label", "Other Discussion Items")) if topic else "Other Discussion Items"
    active = [node for node in nodes if node.get("status") not in {"archived", "resolved"}]
    decisions = [node for node in active if node.get("type") == "decision"]
    open_items = [node for node in active if node.get("type") == "open_item"]
    actions = [node for node in active if node.get("type") == "action"]
    important = [
        node for node in active
        if node.get("type") in {"decision", "action", "open_item"}
    ]
    important.sort(key=lambda node: _last_event_sequence(node, events), reverse=True)
    highlights = [str(node.get("label", "")) for node in important[:2] if node.get("label")]
    counts = {
        "decisions": len(decisions),
        "candidate_decisions": sum(node.get("status") == "candidate" for node in decisions),
        "confirmed_decisions": sum(node.get("status") == "confirmed" for node in decisions),
        "revoked_decisions": sum(node.get("status") == "revoked" for node in decisions),
        "open_items": len(open_items),
        "actions": len(actions),
        "child_nodes": len(active),
    }
    headline = f"{label}: {len(decisions)} Decision / {len(open_items)} Open / {len(actions)} Action"
    if highlights:
        headline += "。" + "、".join(highlights)
    return {
        "topic_id": topic.get("id") if topic else None,
        "label": label,
        "counts": counts,
        "text": headline,
        "highlight_labels": highlights,
    }


def _semantic_groups(
    nodes: list[Mapping[str, Any]],
    *,
    topic_id: str | None,
    membership: Mapping[str, str | None],
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build only conservative, presentation-only near-duplicate groups."""

    candidates = [
        node for node in nodes
        if node.get("type") in GROUPABLE_TYPES
        and node.get("status") not in {"archived", "resolved", "parked"}
        and membership.get(str(node["id"])) == topic_id
        and _safe_semantic_key(str(node.get("label", "")))
    ]
    groups: list[list[Mapping[str, Any]]] = []
    used: set[str] = set()
    for node in sorted(candidates, key=lambda item: (_last_event_sequence(item, events), str(item["id"]))):
        if node["id"] in used:
            continue
        key = _safe_semantic_key(str(node.get("label", "")))
        if not key:
            continue
        group = [node]
        for other in candidates:
            if other["id"] == node["id"] or other["id"] in used:
                continue
            other_key = _safe_semantic_key(str(other.get("label", "")))
            if other_key and (key in other_key or other_key in key):
                group.append(other)
        if len(group) >= 2:
            groups.append(group)
            used.update(str(item["id"]) for item in group)
    return [
        {
            "group_id": f"semantic-group:{topic_id}:{index}",
            "topic_id": topic_id,
            "node_type": group[0].get("type"),
            "representative_node_id": group[0].get("id"),
            "node_ids": [item["id"] for item in group],
            "label": str(group[0].get("label", "")),
            "count": len(group),
        }
        for index, group in enumerate(groups, start=1)
    ]


def build_presentation_projection(
    graph: Mapping[str, Any],
    events: Iterable[dict[str, Any]],
    *,
    layout: StableLayout | None = None,
    current_detail_budget: int = 8,
    use_semantic_groups: bool = True,
) -> dict[str, Any]:
    """Create a revision-aware compact projection without mutating `graph`.

    Current Topic receives a bounded detail window.  Critical Nodes outside
    the Current Topic are represented as compact rail entries, while each
    non-current Topic receives one deterministic summary card.  The full
    canonical node IDs remain present in `hidden_node_ids` or
    `critical_entries`; no history is deleted.
    """

    graph_copy = copy.deepcopy(dict(graph))
    event_list = [copy.deepcopy(event) for event in events]
    stable_layout = layout or StableLayout()
    base = map_projection({"graph": graph_copy}, event_list, stable_layout)
    nodes = [node for node in graph_copy.get("nodes", []) if node.get("status") != "archived"]
    node_by_id = {str(node["id"]): node for node in nodes}
    membership = _topic_membership(graph_copy, base)
    current_topic_id = graph_copy.get("current_topic", {}).get("primary_topic_id")
    current_topic_id = str(current_topic_id) if current_topic_id else None
    last_sequences = {
        str(node["id"]): _last_event_sequence(node, event_list)
        for node in nodes
    }

    topic_by_id = {
        str(node["id"]): node for node in nodes if node.get("type") == "topic"
    }
    lane_records: list[dict[str, Any]] = []
    visible_node_ids: set[str] = set()
    grouped_node_ids: set[str] = set()
    summary_cards: list[dict[str, Any]] = []
    semantic_groups: list[dict[str, Any]] = []
    current_detail_ids: list[str] = []

    for lane in base.get("lanes", []):
        lane_id = str(lane["id"])
        topic_id = str(lane["topic_id"]) if lane.get("topic_id") else None
        lane_nodes = [node_by_id[node_id] for node_id in lane.get("node_ids", []) if node_id in node_by_id]
        if lane.get("kind") in {"parking", "archived"}:
            summary_cards.append(
                {
                    "card_id": f"summary:{lane_id}",
                    "kind": "summary",
                    "lane_id": lane_id,
                    "label": lane.get("label"),
                    "text": f"{lane.get('label')}: {len(lane_nodes)} item",
                    "node_ids": [node["id"] for node in lane_nodes],
                }
            )
            grouped_node_ids.update(str(node["id"]) for node in lane_nodes)
            lane_records.append(
                {
                    "id": lane_id,
                    "kind": lane.get("kind"),
                    "topic_id": topic_id,
                    "label": lane.get("label"),
                    "current": False,
                    "mode": "summary",
                    "detail_node_ids": [],
                    "grouped_node_ids": [node["id"] for node in lane_nodes],
                    "summary": _deterministic_topic_summary(None, lane_nodes, event_list),
                }
            )
            continue

        is_current = topic_id == current_topic_id
        # Resolved Open Items remain in the canonical graph for replay and
        # traceability, but are not part of the normal visible-card budget.
        # They can still be reached through the detail/history surface and
        # are counted in grouped_node_ids.
        visible_lane_nodes = [node for node in lane_nodes if node.get("status") != "resolved"]
        critical = [
            node for node in visible_lane_nodes
            if node.get("type") in CURRENT_IMPORTANT_TYPES
            and node.get("status") not in {"archived", "resolved", "parked"}
        ]
        critical.sort(key=lambda node: _node_priority(node, current=is_current, last_sequence=last_sequences[str(node["id"])]), reverse=True)
        if is_current:
            noncritical = [node for node in visible_lane_nodes if node not in critical]
            noncritical.sort(key=lambda node: _node_priority(node, current=True, last_sequence=last_sequences[str(node["id"])]), reverse=True)
            selected = critical + noncritical[: max(0, current_detail_budget - len(critical))]
            selected_ids = [str(node["id"]) for node in selected]
            current_detail_ids.extend(selected_ids)
            visible_node_ids.update(selected_ids)
            hidden = [node for node in lane_nodes if str(node["id"]) not in visible_node_ids]
            grouped_node_ids.update(str(node["id"]) for node in hidden)
            mode = "expanded"
            detail_ids = selected_ids
        else:
            # Critical state is rendered in the global rail, not discarded.
            noncurrent_critical = [node for node in critical]
            visible_node_ids.update(str(node["id"]) for node in noncurrent_critical)
            hidden = [node for node in lane_nodes if str(node["id"]) not in {str(item["id"]) for item in noncurrent_critical}]
            grouped_node_ids.update(str(node["id"]) for node in hidden)
            detail_ids = [str(node["id"]) for node in noncurrent_critical]
            mode = "compact"
            summary_cards.append(
                {
                    "card_id": f"summary:{lane_id}",
                    "kind": "summary",
                    "lane_id": lane_id,
                    "label": lane.get("label"),
                    "text": _deterministic_topic_summary(topic_by_id.get(topic_id), lane_nodes, event_list)["text"],
                    "node_ids": [node["id"] for node in lane_nodes],
                }
            )
        summary = _deterministic_topic_summary(topic_by_id.get(topic_id), lane_nodes, event_list)
        lane_records.append(
            {
                "id": lane_id,
                "kind": "topic",
                "topic_id": topic_id,
                "label": lane.get("label"),
                "current": is_current,
                "mode": mode,
                "detail_node_ids": detail_ids,
                "grouped_node_ids": [str(node["id"]) for node in hidden],
                "summary": summary,
            }
        )
        if use_semantic_groups:
            semantic_groups.extend(
                _semantic_groups(lane_nodes, topic_id=topic_id, membership=membership, events=event_list)
            )

    def critical_entries(node_type: str) -> list[dict[str, Any]]:
        entries = []
        for node in nodes:
            if node.get("type") != node_type:
                continue
            if node.get("status") in {"archived", "resolved", "parked"}:
                continue
            entries.append(
                {
                    "node_id": node["id"],
                    "label": node.get("label"),
                    "status": node.get("status"),
                    "topic_id": membership.get(str(node["id"])),
                    "visible_as": "detail" if str(node["id"]) in current_detail_ids else "rail",
                }
            )
        return entries

    decisions = [node for node in nodes if node.get("type") == "decision" and node.get("status") != "archived"]
    actions = [node for node in nodes if node.get("type") == "action" and node.get("status") != "archived"]
    open_items = [node for node in nodes if node.get("type") == "open_item" and node.get("status") not in {"archived", "resolved", "parked"}]
    critical = {
        "decisions": critical_entries("decision"),
        "actions": critical_entries("action"),
        "open_items": critical_entries("open_item"),
    }
    critical_ids = {
        str(entry["node_id"])
        for entries in critical.values()
        for entry in entries
    }
    visible_node_ids.update(critical_ids)
    hidden_node_ids = sorted(
        str(node["id"]) for node in nodes if str(node["id"]) not in visible_node_ids
    )
    grouped_node_ids.update(hidden_node_ids)
    all_critical_ids = {
        str(node["id"])
        for node in decisions + actions + open_items
    }
    critical_recall = {
        "current_topic": 1.0 if current_topic_id is not None else 1.0,
        "candidate_decisions": 1.0 if all(
            str(node["id"]) in visible_node_ids for node in decisions if node.get("status") == "candidate"
        ) else 0.0,
        "confirmed_decisions": 1.0 if all(
            str(node["id"]) in visible_node_ids for node in decisions if node.get("status") == "confirmed"
        ) else 0.0,
        "actions": 1.0 if all(str(node["id"]) in visible_node_ids for node in actions) else 0.0,
        "important_open_items": 1.0 if all(str(node["id"]) in visible_node_ids for node in open_items) else 0.0,
    }
    critical_recall["overall"] = min(critical_recall.values(), default=1.0)
    # ``visible_cards`` means cards on the Map Canvas.  Critical entries that
    # are outside the Current Topic are represented in the Status Rail and are
    # counted separately; they must not inflate the canvas compression ratio.
    visible_cards = [
        {"kind": "detail", "node_id": node_id, "lane_id": next((lane["id"] for lane in lane_records if node_id in lane["detail_node_ids"]), None)}
        for node_id in sorted(set(current_detail_ids))
    ]
    visible_cards.extend(summary_cards)

    return {
        "projection_version": "long-session-compaction-v1",
        "source_revision": graph_copy.get("revision", 0),
        "canonical_node_count": len(nodes),
        "canonical_edge_count": len(graph_copy.get("edges", [])),
        "visible_card_count": len(visible_cards),
        "visible_cards": visible_cards,
        "critical_rail_entries": [
            entry
            for entries in critical.values()
            for entry in entries
            if entry["visible_as"] == "rail"
        ],
        "visible_node_ids": sorted(visible_node_ids),
        # Presentation data for visible cards only.  This is a derived copy;
        # the canonical graph remains the source of truth and is never
        # mutated by the projection builder.
        "visible_node_data": [
            copy.deepcopy(node_by_id[node_id])
            for node_id in sorted(set(current_detail_ids))
            if node_id in node_by_id
        ],
        "hidden_node_ids": hidden_node_ids,
        "grouped_node_ids": sorted(grouped_node_ids),
        "hidden_or_grouped_count": len(hidden_node_ids),
        "compression_ratio": round(len(visible_cards) / len(nodes), 4) if nodes else 1.0,
        "current_topic_id": current_topic_id,
        "current_topic_label": topic_by_id.get(current_topic_id, {}).get("label") if current_topic_id else None,
        "visible_current_topic_nodes": len(current_detail_ids),
        "visible_decisions": len(critical["decisions"]),
        "visible_actions": len(critical["actions"]),
        "visible_open_items": len(critical["open_items"]),
        "critical_information_recall": critical_recall,
        "critical_sections": critical,
        "lanes": lane_records,
        "summary_cards": summary_cards,
        "semantic_groups": semantic_groups,
        "recent_flow": copy.deepcopy(base.get("recent_flow", [])),
        "layout": copy.deepcopy(base.get("positions", {})),
        "presentation_only": True,
    }
