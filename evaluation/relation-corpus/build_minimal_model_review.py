"""Offline, Evidence-linked review of the one-relation hypothesis.

Reads preserved author/Human annotations; writes an HTML diagnostic artifact.
No Product imports, provider calls, audio, or Analyzer rerun.
"""

from __future__ import annotations

from collections import Counter
from html import escape
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def load(name: str) -> dict:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def h(value: object) -> str:
    return escape(str(value), quote=True)


def main() -> None:
    corpus = load("corpus.json")
    human = load("human_review.json")
    model = load("minimal_model_classification.json")
    pairs = {p["id"]: (case, p) for case in corpus["controlled_cases"] for p in case["candidate_pairs"]}
    hp = {p["id"]: p for p in human["pairs"]}
    mp = {p["id"]: p for p in model["pairs"]}
    assert len(pairs) == len(hp) == len(mp) == 31
    assert set(pairs) == set(hp) == set(mp)
    allowed = set(model["allowed"])
    for pair_id, (case, author) in pairs.items():
        nodes = {n["id"]: n for n in case["nodes"]}
        evidence = {e["id"] for e in case["evidence"]}
        human_pair, selected = hp[pair_id], mp[pair_id]
        assert selected["classification"] in allowed
        assert human_pair["outcome"] in {"present", "none", "uncertain"}
        assert set(human_pair["evidence_ids"]) <= evidence
        assert selected["interpretation_ja"].strip()
        if selected["classification"] == "provenance":
            assert "strained" in selected
            assert author["source"] in nodes and author["target"] in nodes
        if selected["classification"] in {"supports", "opposes"}:
            assert author["existing_mapping"] == selected["classification"]

    author_counts = Counter(p["outcome"] for _, p in pairs.values())
    human_counts = Counter(p["outcome"] for p in hp.values())
    model_counts = Counter(p["classification"] for p in mp.values())
    assert author_counts == {"present": 16, "none": 9, "uncertain": 6}
    assert human_counts == {"present": 19, "none": 10, "uncertain": 2}
    assert model_counts == {"provenance": 12, "none": 14, "uncertain": 2, "supports": 2, "opposes": 1}
    agreement = sum(p["outcome"] == hp[pair_id]["outcome"] for pair_id, (_, p) in pairs.items())
    assert agreement == 27
    conflicts = [pair_id for pair_id, (_, p) in pairs.items() if p["outcome"] != hp[pair_id]["outcome"]]
    assert conflicts == ["r1-p2", "r3-p7", "r4-p6", "r5-p5"]

    sections = []
    for case in corpus["controlled_cases"]:
        node_by_id = {n["id"]: n for n in case["nodes"]}
        case_pairs = [(p, mp[p["id"]]) for p in case["candidate_pairs"]]
        sequence = "<span class='sep'>→</span>".join(
            f'<span class="node">{h(n["id"])}：{h(n["label"])}</span>' for n in case["nodes"]
        )
        arguments = [x for x in case_pairs if x[1]["classification"] in {"supports", "opposes"}]
        minimal = [x for x in case_pairs if x[1]["classification"] in {"provenance", "supports", "opposes"}]
        def edge_list(items: list) -> str:
            if not items:
                return '<span class="quiet">確定的なNode間Edgeなし。Node自体は残る。</span>'
            return "".join(
                f'<div class="edge {h(result["classification"])}"><b>{h(p["source"])} → {h(p["target"])}</b><span>{h(result["classification"])}</span><small>{h(result["interpretation_ja"])}</small></div>'
                for p, result in items
            )
        review_rows = "".join(
            f'<tr><td>{h(p["id"])}</td><td>{h(p["source"])} → {h(p["target"])}</td><td>{h(p["outcome"])}</td><td>{h(hp[p["id"]]["outcome"])}</td><td>{h(hp[p["id"]]["interpretation"])}</td><td><b>{h(result["classification"])}</b></td><td>{h(result["interpretation_ja"])}</td></tr>'
            for p, result in case_pairs
        )
        live = case["presentation_probe"]["live_context_nodes"]
        live_edges = [(p, m) for p, m in minimal if p["source"] in live and p["target"] in live]
        latest = case["nodes"][-1]
        roots = case["presentation_probe"]["final_entry_nodes"]
        root_text = " / ".join(f'{h(i)}：{h(node_by_id[i]["label"])}' for i in roots)
        sections.append(f'''<section class="case"><h2>{h(case["id"])} — {h(case["archetype"])}</h2><p>{h(case["setting"])}</p>
<div class="variants"><div class="variant"><h3>A｜sequence only</h3><div class="sequence">{sequence}</div><p>順番は分かるが理由の線は描かない。</p></div>
<div class="variant"><h3>B｜supports / opposes only</h3>{edge_list(arguments)}<p>構造上のNodeはすべて保持。</p></div>
<div class="variant"><h3>C｜+ discussion provenance</h3>{edge_list(minimal)}<p>意味が立証できる直接Edgeのみ。none・uncertainは描かない。</p></div></div>
<div class="views"><div><h3>Live｜局所 {len(live)} Node</h3><p>{' / '.join(h(i) for i in live)}</p>{edge_list(live_edges)}<div class="latest"><b>最新NodeのCanonical全文（この評価例のNode）</b><br>{h(latest["label"])}</div></div>
<div><h3>Final｜複数入口</h3><p>閲覧入口：{root_text}</p><p>{h(case["presentation_probe"]["note"])}</p><p>すべてのNodeと確定的なEdgeを参照可能。入口はPresentation上の整理であり、新しいCanonical Root Entityではない。</p></div></div>
<details><summary>31ペア中のこのケースの判定・Evidenceを確認</summary><table><tr><th>Pair</th><th>向き</th><th>作者</th><th>Human</th><th>Humanの解釈</th><th>最小モデル</th><th>線の採否理由</th></tr>{review_rows}</table></details></section>''')
    html = f'''<!doctype html><html lang="ja"><meta charset="utf-8"><title>RONRO｜最小Relationモデル比較</title><style>
body{{font-family:-apple-system,BlinkMacSystemFont,'Hiragino Kaku Gothic ProN','Yu Gothic',sans-serif;max-width:1700px;margin:auto;padding:28px 35px 90px;background:#f2f6f8;color:#18303c;line-height:1.55}}h1{{font-size:34px}}h2{{font-size:25px}}.lead{{font-size:18px}}.note{{background:#fff1d9;border-left:6px solid #c78719;padding:14px 18px}}.case{{background:#fff;border:1px solid #d1dfe4;border-radius:16px;margin:28px 0;padding:23px}}.variants{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}}.variant,.views>div{{background:#f7fafb;border:1px solid #d7e4e9;border-radius:10px;padding:14px;min-width:0}}h3{{font-size:19px;margin:0 0 12px}}.sequence{{display:flex;flex-wrap:wrap;gap:6px;align-items:center}}.node{{background:white;border:1px solid #a6bbc5;border-radius:8px;padding:7px 10px;font-size:15px}}.sep{{color:#637b84}}.edge{{border-left:4px solid #568e9c;padding:7px 9px;margin:8px 0;background:white}}.edge.supports{{border-color:#2c8555}}.edge.opposes{{border-color:#bc593f}}.edge span{{float:right;font-size:13px}}.edge small{{display:block;margin-top:4px;color:#36525f}}.quiet{{color:#526874}}.views{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:15px}}.latest{{background:#e6f2f3;border-radius:8px;padding:11px;margin-top:10px}}table{{width:100%;border-collapse:collapse;font-size:14px}}th,td{{padding:8px;border-bottom:1px solid #d8e4e8;text-align:left;vertical-align:top}}th{{background:#e8f0f3}}details{{margin-top:15px}}summary{{cursor:pointer;font-weight:700}}
</style><main><h1>最小Relationモデル：A/B/C比較</h1><p class="lead">時系列だけ、既存の支持／反対だけ、そこに1種類の「議論上の生じ方」を足した場合を、同じR1–R5で比較します。線は物理的因果・解決・Decision確定を意味しません。</p><p class="note">これは作者作成の会議例によるオフライン概念図です。Humanの判定は独立した意味レビューですが、最小Edge集合への変換はこのSpikeの設計判断です。T1/T2の実際のRelation精度や普通の参加者の理解度は未測定です。<a href="review-blind.html">各発言EvidenceとNodeはこちら</a>。</p>{''.join(sections)}<h2>Human Reviewで確認したいこと</h2><ol><li>線で「なぜこのNodeがここにあるか」が分かるか</li><li>漏水・落葉の線を物理的因果と誤解しないか</li><li>課題→選択肢、Option→Decision、Decision/Open Item→Actionは自然か</li><li>別件を別の入口として読めるか</li><li>比較対象の兄弟案に追加の線が必要か</li><li>線が多すぎないか、薄すぎないか</li></ol></main></html>'''
    (ROOT / "minimal-model-review.html").write_text(html, encoding="utf-8")
    print(json.dumps({"pair_count": len(pairs), "author_human_agreement": agreement,
                      "disagreement_ids": conflicts, "minimal_model": dict(model_counts),
                      "strained_provenance": sum(bool(p.get("strained")) for p in mp.values() if p["classification"] == "provenance")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
