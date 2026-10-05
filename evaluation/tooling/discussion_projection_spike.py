"""Offline, private-only Live/Final projection review from retained Graphs.

No provider calls or Product imports. Output embeds transcript-derived Graph
labels and MUST remain outside Public Git.
"""
import argparse
import json
from pathlib import Path


ORDINARY = {"idea", "option", "concern"}
INACTIVE = {"archived", "resolved", "completed", "revoked", "parked"}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def active(node):
    return node["status"] not in INACTIVE


def ordered_nodes(graph):
    # Saved Graph order follows accepted node_detected Events for these runs.
    # No update Events occur in either source Graph; this is not a general
    # substitute for the complete Event log.
    return [n for n in graph["nodes"] if active(n)]


def data_for(graph, grid_ids=None, source="", limitation=""):
    nodes = ordered_nodes(graph)
    ordinary = [n for n in nodes if n["type"] in ORDINARY]
    by_id = {n["id"]: n for n in nodes}
    current = graph["current_topic"].get("primary_topic_id")
    topic = by_id.get(current)
    grid = [by_id[i] for i in (grid_ids or [n["id"] for n in ordinary[-6:]]) if i in by_id]
    # Latest meaningful Node in current Topic if a direct Topic relation is
    # available; otherwise newest ordinary Node. "contains" is membership,
    # never rendered as a semantic relation between discussion Nodes.
    members = {e["target_node_id"] for e in graph["edges"] if e["type"] == "contains" and e["source_node_id"] == current}
    # For saved data, updated_at is unchanged from creation. For future
    # material node updates it gives a deterministic latest-activity order;
    # a production design must filter non-material touch Events explicitly.
    activity = lambda n: (n["updated_at"], n["created_at"], nodes.index(n))
    in_topic = [n for n in ordinary if n["id"] in members]
    history = sorted(in_topic or ordinary, key=activity)
    focus = history[-1] if history else None
    index = history.index(focus) if focus else -1
    flow = history[max(0, index - 3):index + 1] if focus else []
    rail = {k: [n for n in nodes if (n["type"] == "decision" and n["status"] == k) if k in {"candidate", "confirmed"}]
            for k in ("candidate", "confirmed")}
    rail["open_item"] = [n for n in nodes if n["type"] == "open_item"]
    rail["action"] = [n for n in nodes if n["type"] == "action"]
    def pack(n):
        return {"id": n["id"], "type": n["type"], "status": n["status"],
                "canonical": n["label"], "display": n.get("display_label") or n["label"],
                "has_display_label": bool(n.get("display_label")),
                "change": "更新" if n["updated_at"] != n["created_at"] else "追加",
                "created_at": n["created_at"], "updated_at": n["updated_at"],
                "evidence_count": len(n.get("evidence_ids", [])),
                "source_event_count": len(n.get("source_event_ids", []))}
    return {"source": source, "limitation": limitation, "revision": graph["revision"],
            "topic": pack(topic) if topic else None,
            "grid": [pack(n) for n in grid], "flow": [pack(n) for n in flow],
            "latest": pack(focus) if focus else None,
            "nodes": [pack(n) for n in nodes],
            "rail": {k: [pack(n) for n in v] for k, v in rail.items()},
            "edge_types": {t: sum(e["type"] == t for e in graph["edges"]) for t in {e["type"] for e in graph["edges"]}},
            "ordinary_count": len(ordinary)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--t1", type=Path, required=True, help="private saved T1 evaluation directory")
    p.add_argument("--t1-metrics", type=Path, required=True)
    p.add_argument("--t2", type=Path, required=True, help="private saved T2 failed-run snapshot")
    p.add_argument("--out", type=Path, required=True, help="PRIVATE output directory outside Git")
    args = p.parse_args()
    root = Path(__file__).resolve().parents[2]
    if args.out.resolve().is_relative_to(root) or args.out.exists():
        p.error("output must be a new private directory outside Public Git")
    metrics = read(args.t1_metrics)
    datasets = {}
    for minute in (5, 10, 15):
        graph = read(args.t1 / "snapshots" / f"{minute:02}min.json")["graph"]
        slots = metrics["snapshots"][str(minute)]["stable"]["slots"]
        datasets[f"t1-{minute}"] = data_for(graph, slots, f"T1・{minute}分", "保存済みGraph。Node間の関係はTopic包含のみ。")
    t1_final = read(args.t1 / "graph-final.json")
    datasets["final-t1"] = data_for(t1_final, source="T1・会議後の記録", limitation="保存済みT1最終Graph。意味的なNode間の矢印は存在しないため、流れは検出順。")
    datasets["final-t1"]["checkpoints"] = [
        {"time": f"{minute}分", "nodes": datasets[f"t1-{minute}"]["flow"][-2:]}
        for minute in (5, 10, 15)
    ]
    t2_snapshot = read(args.t2)["snapshot"]
    datasets["t2-short"] = data_for(t2_snapshot["state"]["graph"], source="T2・中断した約6分の保存Graph",
                                    limitation="30分完走データではない。後続の完走Runに4件・計5.248秒の空Provider itemがあり、内容完全性は未確認。")
    assert len(datasets["final-t1"]["nodes"]) == 38
    assert len(datasets["t2-short"]["nodes"]) == 12
    assert all(set(d["edge_types"]) <= {"contains"} for d in datasets.values())
    assert all(d["latest"] is None or d["latest"]["id"] == d["flow"][-1]["id"] for d in datasets.values())
    args.out.mkdir(parents=True)
    payload = json.dumps(datasets, ensure_ascii=False).replace("<", "\\u003c")
    template = (Path(__file__).with_suffix(".html")).read_text(encoding="utf-8")
    (args.out / "index.html").write_text(template.replace("__PRIVATE_DATA__", payload), encoding="utf-8")
    manifest = {k: {"revision": v["revision"], "nodes": len(v["nodes"]), "flow_nodes": len(v["flow"]),
                    "semantic_node_edges": sum(c for t, c in v["edge_types"].items() if t != "contains"),
                    "display_labels_present": sum(n["has_display_label"] for n in v["nodes"])} for k, v in datasets.items()}
    (args.out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.out / "index.html"), "manifest": manifest}, ensure_ascii=False))


if __name__ == "__main__":
    main()
