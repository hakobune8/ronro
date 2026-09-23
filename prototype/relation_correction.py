"""Conservative spoken correction interpreter for the working semantic graph.

Only explicit correction language is handled. Ambiguous references request
clarification and never mutate the Graph or fall through to Analyzer inference.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from .semantic_projection import focused_flow

SEMANTIC = {"discussion_provenance", "supports", "opposes"}


def _shape(edge: Mapping[str, Any]) -> dict[str, str]:
    return {"source_node_id": edge["source_node_id"],
            "target_node_id": edge["target_node_id"],
            "relation_type": edge.get("type", edge.get("relation_type"))}


def _matches(graph: Mapping[str, Any], phrase: str) -> list[str]:
    token = re.sub(r"[\s　。、の話案]+", "", phrase)
    if len(token) < 2:
        return []
    return [node["id"] for node in graph["nodes"] if node["type"] != "topic"
            and token in re.sub(r"[\s　。、]+", "", node["label"])]


def interpret_relation_correction(
    text: str, graph: Mapping[str, Any], events: Sequence[dict[str, Any]],
) -> dict[str, Any] | None:
    """Return a precise Human command or clarification, never a guessed edge."""
    normalized = re.sub(r"[\s　。]+", "", text)
    edges = [edge for edge in graph["edges"] if edge["type"] in SEMANTIC]
    focus = focused_flow(graph, events)["focus_id"]
    if "その二つは関係ありません" in normalized or "この二つは関係ありません" in normalized:
        local_ids = {node["id"] for node in focused_flow(graph, events)["nodes"]}
        visible = [edge for edge in edges if edge["source_node_id"] in local_ids
                   and edge["target_node_id"] in local_ids]
        if len(visible) == 1:
            return {"command_type": "correct_relation", "old_relation": _shape(visible[0]), "new_relation": None}
        return {"clarification": "どの二つの論点の線を外しますか？"}
    if "これは別の論点です" in normalized or "これは独立した論点です" in normalized:
        incoming = [edge for edge in edges if edge["type"] == "discussion_provenance" and edge["target_node_id"] == focus]
        if len(incoming) == 1:
            return {"command_type": "correct_relation", "old_relation": _shape(incoming[0]),
                    "new_relation": None, "declared_independent": True}
        return {"clarification": "どの論点へのつながりを外しますか？"}
    origin = re.search(r"これはさっきの(.+?)の話から出た", normalized)
    if origin:
        sources = _matches(graph, origin.group(1))
        if focus and len(sources) == 1 and sources[0] != focus:
            incoming = [edge for edge in edges if edge["type"] == "discussion_provenance" and edge["target_node_id"] == focus]
            if len(incoming) <= 1:
                return {"command_type": "correct_relation",
                        "old_relation": _shape(incoming[0]) if incoming else None,
                        "new_relation": {"source_node_id": sources[0], "target_node_id": focus,
                                         "relation_type": "discussion_provenance"}}
        return {"clarification": "元の論点と、つなぎたい論点を確認してください。"}
    endpoint = re.search(r"この懸念は(.+?)ではなく(.+?)について", normalized)
    if endpoint:
        nodes = {node["id"]: node for node in graph["nodes"]}
        old_targets, new_targets = _matches(graph, endpoint.group(1)), _matches(graph, endpoint.group(2))
        old_edges = [edge for edge in edges if edge["type"] in {"supports", "opposes"}
                     and nodes[edge["source_node_id"]]["type"] == "concern"
                     and edge["target_node_id"] in old_targets]
        if len(old_edges) == 1:
            target_type = nodes[old_edges[0]["target_node_id"]]["type"]
            new_targets = [node_id for node_id in new_targets if nodes[node_id]["type"] == target_type]
        if len(old_edges) == 1 and len(new_targets) == 1:
            new = _shape(old_edges[0]); new["target_node_id"] = new_targets[0]
            return {"command_type": "correct_relation", "old_relation": _shape(old_edges[0]), "new_relation": new}
        return {"clarification": "どの案への懸念か、もう少し具体的に教えてください。"}
    if "支持ではなく反対" in normalized or "反対ではなく支持" in normalized:
        attached = [edge for edge in edges if focus in (edge["source_node_id"], edge["target_node_id"])
                    and edge["type"] in {"supports", "opposes"}]
        if len(attached) == 1:
            new = _shape(attached[0])
            new["relation_type"] = "opposes" if "支持ではなく反対" in normalized else "supports"
            return {"command_type": "correct_relation", "old_relation": _shape(attached[0]), "new_relation": new}
        return {"clarification": "どの線の支持・反対を変えますか？"}
    return None
