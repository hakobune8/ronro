"""Deterministic, incremental layout projection for the M5 Discussion Map."""

from __future__ import annotations

import copy
from typing import Any, Iterable
from .display_labels import display_projection
from .semantic_projection import focused_flow


MAIN_LANE_GAP = 320
CARD_GAP = 112


class StableLayout:
    """Keep node placement keyed by canonical Node ID.

    This is deliberately a lane/card projection, not a general graph layout.
    Existing placements are never re-packed. New Nodes receive the next slot
    in their inferred home lane; parked and archived Nodes move only to their
    dedicated display lane while retaining their home placement.
    """

    def __init__(self) -> None:
        self._placements: dict[str, dict[str, Any]] = {}
        from .shared_projection import SharedProjection
        self.shared_projection = SharedProjection()

    def reset(self) -> None:
        self._placements.clear()
        self.shared_projection.reset()

    def project(
        self,
        graph: dict[str, Any],
        events: Iterable[dict[str, Any]] = (),
    ) -> dict[str, Any]:
        nodes = list(graph.get("nodes", []))
        edges = list(graph.get("edges", []))
        ordered_events = sorted(events, key=lambda event: event["sequence"])
        node_ids = {node["id"] for node in nodes}
        self._placements = {
            node_id: placement
            for node_id, placement in self._placements.items()
            if node_id in node_ids
        }

        for node in nodes:
            if node["id"] in self._placements:
                continue
            home_lane_id = self._infer_home_lane(node, nodes, edges, ordered_events)
            self._placements[node["id"]] = {
                "home_lane_id": home_lane_id,
                "home_order": self._next_order(home_lane_id, "home_order"),
                "park_order": None,
                "archive_order": None,
            }

        topic_nodes = [node for node in nodes if node["type"] == "topic"]
        topic_lane_ids = [f"topic:{node['id']}" for node in topic_nodes]
        main_lane_ids = list(topic_lane_ids)
        if any(
            node["status"] not in {"parked", "archived"}
            and self._placements[node["id"]]["home_lane_id"] == "unassigned"
            for node in nodes
        ):
            main_lane_ids.append("unassigned")

        current_topic_id = graph.get("current_topic", {}).get("primary_topic_id")
        current_lane_id = f"topic:{current_topic_id}" if current_topic_id else None
        lane_labels = {f"topic:{node['id']}": node["label"] for node in topic_nodes}
        lane_labels["unassigned"] = "Other Discussion Items"
        lane_labels["parking"] = "Parking Lot"
        lane_labels["archived"] = "Archived History"

        lane_index = {lane_id: index for index, lane_id in enumerate(main_lane_ids)}
        positions: dict[str, dict[str, Any]] = {}
        lane_nodes: dict[str, list[str]] = {lane_id: [] for lane_id in main_lane_ids}
        parked_nodes: list[str] = []
        archived_nodes: list[str] = []
        node_by_id = {node["id"]: node for node in nodes}

        for node in nodes:
            placement = self._placements[node["id"]]
            if node["status"] == "parked":
                if placement["park_order"] is None:
                    placement["park_order"] = self._next_order("parking", "park_order")
                display_lane_id = "parking"
                display_order = placement["park_order"]
                parked_nodes.append(node["id"])
                display_lane_index = len(main_lane_ids)
            elif node["status"] == "archived":
                if placement["archive_order"] is None:
                    placement["archive_order"] = self._next_order("archived", "archive_order")
                display_lane_id = "archived"
                display_order = placement["archive_order"]
                archived_nodes.append(node["id"])
                display_lane_index = len(main_lane_ids) + 1
            else:
                display_lane_id = placement["home_lane_id"]
                display_order = placement["home_order"]
                lane_nodes.setdefault(display_lane_id, []).append(node["id"])
                display_lane_index = lane_index.get(display_lane_id, len(main_lane_ids))

            positions[node["id"]] = {
                "node_id": node["id"],
                "lane_id": display_lane_id,
                "home_lane_id": placement["home_lane_id"],
                "order": display_order,
                "lane_index": display_lane_index,
                "x": 24 + display_lane_index * MAIN_LANE_GAP,
                "y": 24 + display_order * CARD_GAP,
                "visible": node["status"] != "archived",
            }

        lanes: list[dict[str, Any]] = []
        for lane_id in main_lane_ids:
            topic_id = lane_id.removeprefix("topic:") if lane_id.startswith("topic:") else None
            lane_nodes_for_id = lane_nodes.get(lane_id, [])
            lanes.append(
                {
                    "id": lane_id,
                    "kind": "topic" if topic_id else "unassigned",
                    "topic_id": topic_id,
                    "label": lane_labels[lane_id],
                    "current": lane_id == current_lane_id,
                    "node_ids": lane_nodes_for_id,
                    "node_count": len(lane_nodes_for_id),
                    "summary": self._lane_summary(
                        lane_nodes_for_id,
                        node_by_id,
                    ),
                }
            )
        if parked_nodes:
            lanes.append(
                {
                    "id": "parking",
                    "kind": "parking",
                    "topic_id": None,
                    "label": lane_labels["parking"],
                    "current": False,
                    "node_ids": parked_nodes,
                    "node_count": len(parked_nodes),
                    "summary": self._lane_summary(parked_nodes, node_by_id),
                }
            )
        if archived_nodes:
            lanes.append(
                {
                    "id": "archived",
                    "kind": "archived",
                    "topic_id": None,
                    "label": lane_labels["archived"],
                    "current": False,
                    "node_ids": archived_nodes,
                    "node_count": len(archived_nodes),
                    "summary": self._lane_summary(archived_nodes, node_by_id),
                }
            )

        return {
            "lanes": lanes,
            "positions": positions,
            "current_topic_id": current_topic_id,
            "current_lane_id": current_lane_id,
            "hidden_archived_count": len(archived_nodes),
        }

    @staticmethod
    def _lane_summary(
        node_ids: list[str],
        node_by_id: dict[str, dict[str, Any]],
    ) -> dict[str, int]:
        lane_nodes = [node_by_id[node_id] for node_id in node_ids if node_id in node_by_id]
        return {
            "decisions": sum(node["type"] == "decision" for node in lane_nodes),
            "candidate_decisions": sum(
                node["type"] == "decision" and node["status"] == "candidate"
                for node in lane_nodes
            ),
            "confirmed_decisions": sum(
                node["type"] == "decision" and node["status"] == "confirmed"
                for node in lane_nodes
            ),
            "open_items": sum(
                node["type"] == "open_item"
                and node["status"] not in {"archived", "resolved"}
                for node in lane_nodes
            ),
            "actions": sum(
                node["type"] == "action" and node["status"] != "archived"
                for node in lane_nodes
            ),
            "parked": sum(node["status"] == "parked" for node in lane_nodes),
            "archived": sum(node["status"] == "archived" for node in lane_nodes),
        }

    def _next_order(self, lane_id: str, field: str) -> int:
        values = [
            placement[field]
            for placement in self._placements.values()
            if placement.get("home_lane_id") == lane_id and placement.get(field) is not None
        ]
        if lane_id in {"parking", "archived"}:
            values = [
                placement[field]
                for placement in self._placements.values()
                if placement.get(field) is not None
            ]
        return max(values, default=-1) + 1

    @staticmethod
    def _infer_home_lane(
        node: dict[str, Any],
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        events: list[dict[str, Any]],
    ) -> str:
        if node["type"] == "topic":
            return f"topic:{node['id']}"

        node_id = node["id"]
        node_by_id = {item["id"]: item for item in nodes}
        for edge in edges:
            if edge["target_node_id"] != node_id:
                continue
            source = node_by_id.get(edge["source_node_id"])
            if source and source["type"] == "topic" and edge["type"] in {"contains", "has_option"}:
                return f"topic:{source['id']}"

        node_event_ids = set(node.get("source_event_ids", []))
        node_sequence = next(
            (event["sequence"] for event in events if event["event_id"] in node_event_ids),
            None,
        )
        if node_sequence is not None:
            focus_topic_id: str | None = None
            for event in events:
                if event["sequence"] > node_sequence:
                    break
                if event["event_type"] in {"topic_focus_changed", "set_current_topic"}:
                    focus_topic_id = event["payload"]["topic_id"]
                elif event["event_type"] in {"move_to_parking_lot", "archive_node"}:
                    if event["payload"].get("node_id") == focus_topic_id:
                        focus_topic_id = None
            if focus_topic_id and focus_topic_id in node_by_id:
                return f"topic:{focus_topic_id}"

        return "unassigned"


def recent_topic_flow(
    events: Iterable[dict[str, Any]],
    graph: dict[str, Any],
    limit: int = 7,
) -> list[dict[str, Any]]:
    """Project recent topic focus events without duplicating canonical state."""

    node_labels = {node["id"]: node["label"] for node in graph.get("nodes", [])}
    flow: list[dict[str, Any]] = []
    last_topic_id: str | None = None
    for event in sorted(events, key=lambda item: item["sequence"]):
        if event["event_type"] not in {"topic_focus_changed", "set_current_topic"}:
            continue
        topic_id = event["payload"]["topic_id"]
        if topic_id == last_topic_id:
            continue
        flow.append(
            {
                "topic_id": topic_id,
                "label": node_labels.get(topic_id, topic_id),
                "event_id": event["event_id"],
                "sequence": event["sequence"],
                "mode": "human" if event["event_type"] == "set_current_topic" else "derived",
            }
        )
        last_topic_id = topic_id
    return flow[-limit:]


def recent_discussion_flow(
    graph: dict[str, Any], events: Iterable[dict[str, Any]],
    display_labels: dict[str, str] | None = None, limit: int = 3,
) -> list[dict[str, Any]]:
    """Recent within-Topic points; chronology, never an inferred semantic edge."""

    labels = display_labels or {}
    sequence = {event["event_id"]: event["sequence"] for event in events}
    current_topic_id = graph.get("current_topic", {}).get("primary_topic_id")
    topic_members = {edge["target_node_id"] for edge in graph.get("edges", [])
                     if edge["type"] in {"contains", "has_option"}
                     and edge["source_node_id"] == current_topic_id}
    any_topic_members = {edge["target_node_id"] for edge in graph.get("edges", [])
                         if edge["type"] in {"contains", "has_option"}}
    candidates = []
    for node in graph.get("nodes", []):
        if node["type"] not in {"idea", "option", "concern"} or node["status"] in {"archived", "parked"}:
            continue
        if current_topic_id and node["id"] not in topic_members and node["id"] in any_topic_members:
            continue
        last_sequence = max((sequence.get(event_id, 0) for event_id in node.get("source_event_ids", [])), default=0)
        if last_sequence:
            candidates.append({"node_id": node["id"], "label": labels.get(node["id"]) or node["label"],
                               "sequence": last_sequence})
    return sorted(candidates, key=lambda item: (-item["sequence"], item["node_id"]))[:limit]


def map_projection(
    state: dict[str, Any],
    events: Iterable[dict[str, Any]],
    layout: StableLayout,
    presentation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build M5-only presentation data; the canonical Graph remains untouched."""

    graph = state["graph"]
    event_list = list(events)
    projected = layout.project(graph, event_list)
    nodes = graph.get("nodes", [])
    counts = {
        "topics": sum(node["type"] == "topic" and node["status"] != "archived" for node in nodes),
        "candidate_decisions": sum(node["type"] == "decision" and node["status"] == "candidate" for node in nodes),
        "confirmed_decisions": sum(node["type"] == "decision" and node["status"] == "confirmed" for node in nodes),
        "open_items": sum(node["type"] == "open_item" and node["status"] not in {"archived", "resolved"} for node in nodes),
        "actions": sum(node["type"] == "action" and node["status"] != "archived" for node in nodes),
        "parked": sum(node["status"] == "parked" for node in nodes),
    }
    display_labels = display_projection(graph, presentation)
    semantic_labels = {node_id: value["text"] for node_id, value in display_labels.items()
                       if value.get("text")}
    return {
        **projected,
        "presentation": copy.deepcopy(presentation or {}),
        "display_labels": display_labels,
        "semantic_focus": focused_flow(graph, event_list, semantic_labels),
        "recent_flow": recent_topic_flow(event_list, graph),
        "recent_discussion_flow": recent_discussion_flow(graph, event_list, semantic_labels),
        "counts": counts,
        "observation": None,
        **({"shared": layout.shared_projection.project(state, event_list)} if "evidence" in state and "utterances" in state else {}),
    }
