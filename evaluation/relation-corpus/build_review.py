"""Validate the small, human-owned corpus and build offline review pages.

This is evaluation tooling only. It never calls Analyzer, STT, or a provider.
The blind page deliberately omits the author's relation annotations.
"""

from __future__ import annotations

import html
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATA = json.loads((ROOT / "corpus.json").read_text(encoding="utf-8"))


def h(value: object) -> str:
    return html.escape(str(value), quote=True)


def validate() -> None:
    assert len(DATA["controlled_cases"]) == 5
    assert {case["id"] for case in DATA["controlled_cases"]} == {"R1", "R2", "R3", "R4", "R5"}
    assert {probe["evidence_status"] for probe in DATA["real_world_probes"]} == {"UNVERIFIABLE"}
    valid_outcomes = set(DATA["outcome_values"])
    valid_mappings = set(DATA["mapping_values"])
    valid_sources = {"supports": {"idea", "option"}, "opposes": {"idea", "option", "concern"}}
    valid_targets = {"supports": {"idea", "option", "decision"}, "opposes": {"idea", "option", "decision"}}
    for case in DATA["controlled_cases"]:
        evidence = {item["id"] for item in case["evidence"]}
        nodes = {item["id"]: item for item in case["nodes"]}
        assert len(evidence) == len(case["evidence"])
        assert len(nodes) == len(case["nodes"])
        for node in nodes.values():
            assert set(node["evidence_ids"]) <= evidence
        probe = case["presentation_probe"]
        assert 3 <= len(probe["live_context_nodes"]) <= 5
        assert set(probe["live_context_nodes"]) <= set(nodes)
        assert set(probe["final_entry_nodes"]) <= set(nodes)
        assert len(probe["final_entry_nodes"]) >= 1
        for pair in case["candidate_pairs"]:
            assert pair["source"] in nodes and pair["target"] in nodes
            assert pair["source"] != pair["target"]
            assert pair["outcome"] in valid_outcomes
            assert pair["existing_mapping"] in valid_mappings
            assert set(pair["evidence_ids"]) <= evidence
            if pair["existing_mapping"] in valid_sources:
                assert pair["outcome"] == "present"
                assert nodes[pair["source"]]["type"] in valid_sources[pair["existing_mapping"]]
                assert nodes[pair["target"]]["type"] in valid_targets[pair["existing_mapping"]]


def page(title: str, sections: list[str], *, blind: bool) -> str:
    purpose = (
        "独立注釈用。以下には作者の関係判定・分類・既存型への対応を表示しません。"
        if blind else
        "作者の意図した関係を表示します。Humanの独立判定や実世界での正解を意味しません。"
    )
    return f"""<!doctype html><html lang="ja"><meta charset="utf-8"><title>{h(title)}</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,'Hiragino Kaku Gothic ProN','Yu Gothic',sans-serif;max-width:1420px;margin:auto;padding:25px 35px 90px;background:#f4f7f8;color:#162a35;line-height:1.55}}
h1{{font-size:32px}}h2{{margin-top:50px;border-bottom:3px solid #78aab5;padding-bottom:8px}}h3{{font-size:20px;margin-bottom:8px}}.notice{{padding:15px 18px;background:#fff2d9;border-left:5px solid #ce8700}}.case{{background:white;border:1px solid #d6e1e5;border-radius:14px;padding:22px;margin:24px 0}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:15px}}.box{{background:#f8fafb;border:1px solid #d9e2e7;border-radius:9px;padding:12px}}.item{{margin:7px 0}}small{{color:#55717c}}table{{border-collapse:collapse;width:100%;font-size:15px}}td,th{{border-bottom:1px solid #dce5e9;padding:9px;text-align:left;vertical-align:top}}th{{background:#e8f0f3}}.pass{{color:#116959;font-weight:700}}.none{{color:#596873}}.uncertain{{color:#a36606;font-weight:700}}.map{{padding:15px;background:#edf4f6;border-radius:9px;margin:11px 0}}a{{color:#086d84}}.no-line{{font-weight:700;color:#a36606}}
</style><main><h1>{h(title)}</h1><p class="notice">{purpose} T1/T2は発言本文の参照ができないためUNVERIFIABLE。収録した発言は全てこのSpike用に作成した日本語会議例です。Nodeは分析結果ではなく、作者が用意した評価単位です。</p>
<p>各ペアは「関係あり／意味的関係なし／Evidence不足」を選べます。隣同士でも無関係でよく、独立した入口も許します。発言順の矢印を因果関係と読まないでください。</p>
{''.join(sections)}</main></html>"""


def evidence_section(case: dict) -> str:
    evidence = "".join(
        f'<p class="item"><strong>{h(e["id"])}</strong> <small>{h(e["speaker"])}</small>：{h(e["text"])}</p>'
        for e in case["evidence"]
    )
    nodes = "".join(
        f'<p class="item"><strong>{h(n["id"])}</strong> <small>{h(n["type"])}</small>：{h(n["label"])}</p>'
        for n in case["nodes"]
    )
    return f'<div class="grid"><div class="box"><h3>Evidence（作者作成）</h3>{evidence}</div><div class="box"><h3>評価用Node</h3>{nodes}</div></div>'


def blind_case(case: dict) -> str:
    rows = "".join(
        f'<tr><td>{h(p["id"])}</td><td>{h(p["source"])} → {h(p["target"])}</td><td>□あり　□なし　□不確実</td><td>＿＿＿＿＿＿＿＿</td></tr>'
        for p in case["candidate_pairs"]
    )
    return f'<section class="case"><h2>{h(case["id"])}｜{h(case["archetype"])}</h2><p>{h(case["setting"])}</p>{evidence_section(case)}<h3>独立注釈</h3><table><tr><th>Pair</th><th>Node</th><th>判定</th><th>関係を自然言語で／Evidence</th></tr>{rows}</table><p>独立Rootはどれか？　＿＿＿＿　　Topicへの回帰は意味的関係か、時系列か？　＿＿＿＿</p></section>'


def comparison_case(case: dict) -> str:
    nodes = {n["id"]: n for n in case["nodes"]}
    sequence = " → ".join(h(n["id"]) for n in case["nodes"])
    probe = case["presentation_probe"]
    live_ids = set(probe["live_context_nodes"])
    live_nodes = " / ".join(f'{h(node_id)}：{h(nodes[node_id]["label"])}' for node_id in probe["live_context_nodes"])
    final_entries = " / ".join(f'{h(node_id)}：{h(nodes[node_id]["label"])}' for node_id in probe["final_entry_nodes"])
    existing = [p for p in case["candidate_pairs"] if p["existing_mapping"] in {"supports", "opposes"}]
    existing_text = "、".join(f'{h(p["source"])} —{h(p["existing_mapping"])}→ {h(p["target"])}' for p in existing) or "適用できる意味的Edgeなし"
    live_existing = [p for p in existing if p["source"] in live_ids and p["target"] in live_ids]
    live_intended = [p for p in case["candidate_pairs"] if p["outcome"] == "present" and p["source"] in live_ids and p["target"] in live_ids]
    live_existing_text = "、".join(f'{h(p["source"])} —{h(p["existing_mapping"])}→ {h(p["target"])}' for p in live_existing) or "該当なし"
    live_intended_text = " / ".join(f'{h(p["id"])}：{h(p["description"])}' for p in live_intended) or "確定的な意味的関係なし"
    rows = "".join(
        f'<tr><td>{h(p["id"])}</td><td>{h(nodes[p["source"]]["label"])}<br>→ {h(nodes[p["target"]]["label"])}</td><td class="{h(p["outcome"])}">{h(p["outcome"])}</td><td>{h(p["description"])}</td><td>{h(p["existing_mapping"])}</td><td>{h(", ".join(p["evidence_ids"]))}</td></tr>'
        for p in case["candidate_pairs"]
    )
    return f'''<section class="case"><h2>{h(case["id"])}｜{h(case["archetype"])}</h2><p>{h(case["setting"])}</p>{evidence_section(case)}
<h3>Live局所（{len(live_ids)} Node）とFinal全体像</h3>
<div class="map"><b>Liveの同じNode群：</b>{live_nodes}<br><small>A＝この群の発言順のみ / B＝{live_existing_text} / C＝{live_intended_text}</small></div>
<div class="map"><b>Finalの閲覧入口：</b>{final_entries}<br><small>{h(probe["note"])}。これは作者が設けた表示入口であり、新しいCanonical Root Entityではない。以下A/B/Cで全Nodeを参照する。</small></div>
<h3>診断用の三つの見方</h3>
<div class="map"><b>A｜sequence only</b><br>{sequence}<p><small>矢印＝発言順のみ。Liveなら直近3–5 Node、FinalならTopic活動履歴と全Node詳細。</small></p></div>
<div class="map"><b>B｜既存の意味的Relationのみ</b><br>{existing_text}<p><small>他のNodeを隠す意味ではない。contains/has_optionはTopic構造として別表示。支持・反対以外をrelated_toに押し込めない。</small></p></div>
<div class="map"><b>C｜作者が意図した意味</b><br>{sum(p["outcome"] == "present" for p in case["candidate_pairs"])}件の意味的接続、{sum(p["outcome"] == "none" for p in case["candidate_pairs"])}件の意味的接続なし、{sum(p["outcome"] == "uncertain" for p in case["candidate_pairs"])}件の保留。下の表の自然言語を参照。<p><small>これはCanonically accepted Relationではなく、Human照合前の評価仮説。</small></p></div>
<table><tr><th>Pair</th><th>Node labels</th><th>作者判定</th><th>自然言語の意図</th><th>既存型</th><th>Evidence</th></tr>{rows}</table>
<p><strong>時系列と意味を混同しない：</strong>{h(" → ".join(case["topic_activity"]))}。回帰・別件はEvent/Presentationで扱えます。Decision/Open Item/Actionの状態はRelationで変更しません。</p></section>'''


def main() -> None:
    validate()
    blind = [blind_case(c) for c in DATA["controlled_cases"]]
    comparison = [comparison_case(c) for c in DATA["controlled_cases"]]
    (ROOT / "review-blind.html").write_text(page("RONRO Relation Corpus｜独立注釈シート", blind, blind=True), encoding="utf-8")
    (ROOT / "comparison.html").write_text(page("RONRO Relation Corpus｜A/B/C比較", comparison, blind=False), encoding="utf-8")
    stats = {
        "controlled_archetypes": len(DATA["controlled_cases"]),
        "utterances_including_human_commands": sum(len(c["evidence"]) for c in DATA["controlled_cases"]),
        "nodes": sum(len(c["nodes"]) for c in DATA["controlled_cases"]),
        "pairs": sum(len(c["candidate_pairs"]) for c in DATA["controlled_cases"]),
        "outcomes": {v: sum(p["outcome"] == v for c in DATA["controlled_cases"] for p in c["candidate_pairs"]) for v in DATA["outcome_values"]},
        "existing_semantic_mappings": {v: sum(p["existing_mapping"] == v for c in DATA["controlled_cases"] for p in c["candidate_pairs"]) for v in ("supports", "opposes")},
    }
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
