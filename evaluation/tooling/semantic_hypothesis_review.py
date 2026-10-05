"""Build private R1–R5 review from controlled Evidence and canonical replay.

This is an evaluation helper, not a claim about actual Analyzer generation.
Run from the repository root with an explicit output path outside Public Git.
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

from prototype.replay import ReplayResult, ReplayRunner
from prototype.materializer import initial_state
from prototype.schema import SchemaValidator
from prototype.semantic_projection import focused_flow, final_discussion_map

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "evaluation" / "relation-corpus"
MAPPING = {"provenance": "discussion_provenance", "supports": "supports", "opposes": "opposes"}


def build_case(case: dict, classifications: dict[str, str]) -> tuple[ReplayResult, dict[str, str]]:
    sid = f"hypothesis-{case['id'].lower()}"
    evidence = [
        {"id": e["id"], "session_id": sid, "sequence": i + 1,
         "timestamp": f"2026-09-23T00:00:{i:02d}Z", "speaker": e["speaker"], "text": e["text"]}
        for i, e in enumerate(case["evidence"])
    ]
    result = ReplayResult(initial_state(sid, evidence, []), ())
    runner = ReplayRunner(SchemaValidator(ROOT / "schemas"))
    ids: dict[str, str] = {}

    def append(event_type: str, payload: dict, refs: list[str], *, actor: str = "analyzer") -> None:
        nonlocal result
        seq = len(result.events) + 1
        event = {"event_id": f"{sid}:evt-{seq:03d}", "session_id": sid, "sequence": seq,
                 "event_type": event_type, "occurred_at": f"2026-09-23T00:01:{seq:02d}Z",
                 "actor": actor, "source_evidence_ids": refs, "payload": payload}
        if actor == "human":
            event["expected_revision"] = result.state["graph"]["revision"]
        result = runner.apply_event(result, event)

    append("session_created", {"title": case["archetype"], "goal": case["setting"]}, [], actor="system")
    append("session_started", {}, [], actor="system")

    emitted_pairs: set[str] = set()
    def append_available_pairs() -> None:
        for pair in case["candidate_pairs"]:
            relation_type = MAPPING.get(classifications[pair["id"]])
            if relation_type and pair["id"] not in emitted_pairs and pair["source"] in ids and pair["target"] in ids:
                append("relation_detected", {"source_node_id": ids[pair["source"]],
                                             "target_node_id": ids[pair["target"]],
                                             "relation_type": relation_type}, pair["evidence_ids"])
                emitted_pairs.add(pair["id"])

    for node in case["nodes"]:
        payload = {"node_type": node["type"], "label": node["label"]}
        if node["type"] == "action":
            payload["action"] = {"owner": node.get("owner"), "due_date": node.get("due")}
        append("node_detected", payload, node["evidence_ids"])
        ids[node["id"]] = f"node:{sid}:{result.events[-1]['event_id']}"
        if node["type"] == "decision" and node.get("status") == "confirmed":
            append("confirm_decision", {"decision_node_id": ids[node["id"]],
                                        "expected_status": "candidate"}, [], actor="human")
        append_available_pairs()
    runner.schema_validator.validate_domain(result.state)
    return result, ids


def _card(node: dict, *, extra: str = "") -> str:
    return (f'<div class="card {html.escape(extra)}"><small>{html.escape(node["type"])}'
            f' · {html.escape(node["status"])}</small><div>{html.escape(node["label"])}</div></div>')


def _final_tree(graph: dict, final: dict) -> str:
    views = {node["id"]: node for node in final["overview"]}
    children: dict[str, list[str]] = {}
    for edge in final["overview_edges"]:
        if edge["type"] == "discussion_provenance":
            children.setdefault(edge["source_node_id"], []).append(edge["target_node_id"])
    visited: set[str] = set()
    def branch(node_id: str) -> str:
        if node_id not in views:
            return ""
        if node_id in visited:
            return f'<div class="reference">↳ {html.escape(views[node_id]["label"])}（上で表示）</div>'
        visited.add(node_id)
        inner = ''.join(branch(child) for child in children.get(node_id, []))
        return f'<div class="branch">{_card(views[node_id])}<div class="children">{inner}</div></div>'
    roots = ''.join(f'<div class="root"><div class="root-tag">議論の入口／未結線</div>{branch(root)}</div>'
                    for root in final["roots"] if root in views)
    argument_edges = [e for e in final["overview_edges"] if e["type"] in {"supports", "opposes"}]
    args = ''.join(f'<div class="argument {e["type"]}">{html.escape(views[e["source_node_id"]]["label"])}'
                   f' ─{e["type"]}→ {html.escape(views[e["target_node_id"]]["label"])}</div>' for e in argument_edges)
    return roots + (f'<div class="arguments">{args}</div>' if args else '')


def render() -> tuple[str, dict]:
    corpus = json.loads((CORPUS / "corpus.json").read_text(encoding="utf-8"))
    classifications = {p["id"]: p["classification"] for p in json.loads(
        (CORPUS / "minimal_model_classification.json").read_text(encoding="utf-8"))["pairs"]}
    sections = []
    summary = {}
    for case in corpus["controlled_cases"]:
        result, _ = build_case(case, classifications)
        graph, events = result.state["graph"], result.events
        # Show the last connected moment as well as the eventual final state;
        # an independent later root is still allowed to become current.
        runner = ReplayRunner(SchemaValidator(ROOT / "schemas"))
        preview = ReplayResult(initial_state(graph["session_id"], result.state["evidence"], []), ())
        connected = None
        for event in events:
            preview = runner.apply_event(preview, event)
            if event["event_type"] == "relation_detected":
                candidate = focused_flow(preview.state["graph"], preview.events)
                if len(candidate["nodes"]) >= 2:
                    connected = candidate
        live = connected or focused_flow(graph, events)
        live_at_end = focused_flow(graph, events)
        final = final_discussion_map(graph, events)
        nodes = [n for n in graph["nodes"] if n["type"] != "topic"]
        six = nodes[-6:]
        edge_labels = []
        by_id = {n["id"]: n for n in nodes}
        for edge in graph["edges"]:
            edge_labels.append(f'{by_id[edge["source_node_id"]]["label"]}  ─{edge["type"]}→  {by_id[edge["target_node_id"]]["label"]}')
        summary[case["id"]] = {"nodes": len(nodes), "edges": len(edge_labels),
                               "roots": len(final["roots"]), "live_nodes": len(live["nodes"])}
        ancestors = [n for n in live["nodes"] if n["position"] == "ancestor"]
        parents = [n for n in live["nodes"] if n["position"] == "parent"]
        others = [n for n in live["nodes"] if n["position"] in {"child", "descendant", "argument", "context"}]
        center = next(n for n in live["nodes"] if n["position"] == "focus")
        live_edges = [e for e in live["edges"]]
        live_links = ''.join(
            f'<div class="edge-line {e["type"]}">{html.escape(by_id[e["source_node_id"]]["label"])}'
            f' ─ {"議論を受けて" if e["type"] == "discussion_provenance" else e["type"]} ─ '
            f'{html.escape(by_id[e["target_node_id"]]["label"])}</div>' for e in live_edges)
        upstream = (('<div class="flow-row">' + ''.join(_card(n) for n in ancestors) + '</div>'
                     '<div class="flow-guide">議論を受けて ↓</div>') if ancestors else '')
        upstream += (('<div class="flow-row">' + ''.join(_card(n) for n in parents) + '</div>'
                      '<div class="flow-guide">議論を受けて ↓</div>') if parents else '')
        sections.append(f'''<section id="{case['id']}">
          <h2>{case['id']} · {html.escape(case['archetype'])}</h2>
          <p>{html.escape(case['setting'])}</p>
          <div class="cols">
            <article><h3>A 現行6カード</h3>{''.join(_card(n) for n in six)}</article>
            <article><h3>B Focused Flow</h3><p>結線が生じた時点の局所図</p>
            {upstream}
            {_card(center, extra='focus')}
            <div class="flow-row">{''.join(_card(n) for n in others)}</div>
            <div class="live-links">{live_links}</div>
            <h4>最新の追加・更新（Canonical全文）</h4><p>{html.escape(live['latest_detail']['canonical']) if live['latest_detail'] else 'なし'}</p>
            <p class="note">最終時点の焦点：{html.escape(by_id[live_at_end['focus_id']]['label']) if live_at_end['focus_id'] else 'なし'}（別Rootへ移動してもよい）</p></article>
            <article><h3>C 会議後・複数Root</h3><p>入口／未結線 {len(final['roots'])} · 詳細 {len(final['detail'])}件</p>
            {_final_tree(graph, final)}
            <details><summary>Canonical詳細</summary>{''.join(_card(n) for n in final['detail'])}</details></article>
          </div></section>''')
    page = '''<!doctype html><html lang="ja"><meta charset="utf-8"><title>RONRO 最小意味Graph 仮説</title>
    <style>body{font-family:-apple-system,"Yu Gothic",sans-serif;background:#f5f7fa;color:#1c2937;margin:0;padding:28px}nav{position:sticky;top:0;background:#fff;padding:16px;z-index:1}nav a{margin-right:24px}section{margin:30px auto;max-width:1800px;border-top:2px solid #ccd6e2;padding:22px}.cols{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px}article{background:white;padding:22px;border-radius:14px;min-width:0}.card{border:1px solid #bfcbd8;border-radius:10px;padding:12px;margin:10px 0;font-size:20px;line-height:1.45;overflow-wrap:anywhere}.card.focus{border:3px solid #2563eb;background:#eef5ff}.card small{display:block;color:#52677b;font-size:13px}.flow-row{display:flex;gap:8px;align-items:stretch}.flow-row .card{flex:1;min-width:0;font-size:17px}.flow-guide{border-left:2px solid #90a9c3;margin:4px 0 4px 20px;padding:8px;color:#435e78}.live-links{border-top:1px dashed #c9d4df;margin-top:8px}.edge-line{font-size:13px;padding:5px 0;color:#465d73}.edge-line.supports,.argument.supports{color:#187047}.edge-line.opposes,.argument.opposes{color:#a13737}.root{border:1px solid #cbd8e5;padding:8px 12px;border-radius:12px;margin:10px 0}.root-tag{font-size:13px;color:#5d7387}.branch .card{font-size:17px}.children{margin-left:20px;border-left:2px solid #bdd0e4;padding-left:10px}.arguments{border-top:1px dashed #b9cbdc;padding-top:8px}.argument{font-size:14px;padding:5px}.reference{font-size:14px;color:#52677b;padding:6px}.note{font-size:14px;color:#52677b}summary{cursor:pointer}p{line-height:1.6}</style>
    <nav><strong>最小意味Graph・仮説実装 Human Review</strong>　<a href="#R1">R1</a><a href="#R2">R2</a><a href="#R3">R3</a><a href="#R4">R4</a><a href="#R5">R5</a></nav>
    <p>Controlled Corpusに対するHuman分類をCanonical EventへReplayした比較。実Analyzerの生成精度は未検証です。線は議論上の由来であり物理的因果ではありません。</p>
    <p>確認: 今の論点／なぜ出たか／因果の誤読／支持・反対の区別／独立Root／Decision・Actionの経緯／線の密度／会議後の価値。</p>''' + ''.join(sections) + '</html>'
    return page, summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    page, summary = render()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(page, encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
