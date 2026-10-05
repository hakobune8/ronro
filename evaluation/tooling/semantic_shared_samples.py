"""Render public-safe controlled growth samples through the real Shared View HTML.

The authored Corpus supplies Canonical Events; these are not claims about
Analyzer accuracy. Generated HTML/screenshots remain private until reviewed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from evaluation.tooling.semantic_hypothesis_review import CORPUS, ROOT, build_case
from prototype.layout import StableLayout, map_projection
from prototype.replay import ReplayRunner
from prototype.schema import SchemaValidator


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--real-analyzer", type=Path)
    args = parser.parse_args()
    destination = args.output_dir.resolve()
    if ROOT == destination or ROOT in destination.parents:
        raise ValueError("Samples must be written outside Public Git")
    destination.mkdir(parents=True, exist_ok=True)
    corpus = {case["id"]: case for case in json.loads((CORPUS / "corpus.json").read_text())[
        "controlled_cases"]}
    classes = {pair["id"]: pair["classification"] for pair in json.loads(
        (CORPUS / "minimal_model_classification.json").read_text())["pairs"]}
    html = (ROOT / "prototype/web/shared.html").read_text(encoding="utf-8")
    runner = ReplayRunner(SchemaValidator(ROOT / "schemas"))

    for case_id, stages in {"R4": [2, 4, 5], "R5": [4]}.items():
        completed, _ = build_case(corpus[case_id], classes)
        for stage in stages:
            prefix = []
            count = 0
            for event in completed.events:
                if event["event_type"] == "node_detected":
                    if count == stage:
                        break
                    count += 1
                prefix.append(event)
            replay = runner.replay_events(
                session_id=completed.state["graph"]["session_id"],
                evidence=completed.state["evidence"], utterances=[], events=prefix,
            )
            write_sample(destination / f"{case_id.lower()}-{stage}-focused.html", html, replay)
            if case_id == "R4" and stage == 5:
                decision = next(n for n in replay.state["graph"]["nodes"] if n["type"] == "decision")
                confirm = {
                    "event_id": "sample-r4-human-confirm", "session_id": replay.state["graph"]["session_id"],
                    "sequence": len(replay.events) + 1, "event_type": "confirm_decision",
                    "occurred_at": "2026-09-23T00:10:00Z", "actor": "human",
                    "expected_revision": replay.state["graph"]["revision"],
                    "source_evidence_ids": [],
                    "payload": {"decision_node_id": decision["id"], "expected_status": "candidate"},
                }
                confirmed = runner.apply_event(replay, confirm)
                write_sample(destination / "r4-confirmed-focused.html", html, confirmed)
    if args.real_analyzer:
        source = args.real_analyzer.resolve()
        if ROOT == source or ROOT in source.parents:
            raise ValueError("Real Analyzer artifact must remain outside Public Git")
        for run in json.loads(source.read_text(encoding="utf-8"))["results"]:
            if run["case_id"] not in {"R4", "R5"} or run["run"] != 1:
                continue
            sid = run["session_id"]
            evidence = [{"id": item["id"], "session_id": sid, "sequence": index,
                         "timestamp": f"2026-09-23T00:00:{index:02d}Z",
                         "speaker": item["speaker"], "text": item["text"]}
                        for index, item in enumerate(corpus[run["case_id"]]["evidence"], start=1)
                        if item.get("kind") != "human_command"]
            replay = runner.replay_events(session_id=sid, evidence=evidence,
                                          utterances=[], events=run["events"])
            write_sample(destination / f"{run['case_id'].lower()}-actual-focused.html", html, replay)
    page = '''<!doctype html><html lang="ja"><meta charset="utf-8"><title>論点図の成長・表示確認</title>
<style>body{margin:0;padding:32px;background:#f3f7fa;color:#20323c;font-family:-apple-system,"Yu Gothic",sans-serif}h1{font-size:28px}p{font-size:18px;line-height:1.5}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:22px}figure{margin:0;background:white;padding:14px;border-radius:14px}img{display:block;width:100%;aspect-ratio:16/9;object-fit:contain}figcaption{font-size:20px;font-weight:650;margin:10px 2px}@media(max-width:1000px){.grid{grid-template-columns:1fr}}</style>
<h1>論点図が育つとき</h1><p>制御された合成会議の同一議論を、実際のShared View描画経路で表示した例です。決定候補の確定は最後のHuman操作によるものです。実Analyzerの精度を示すものではありません。</p><div class="grid">
<figure><img src="r4-2-focused.png" alt="課題から対応案へ"><figcaption>1　課題から対応案へ</figcaption></figure>
<figure><img src="r4-4-focused.png" alt="選択肢と論拠が増える"><figcaption>2　選択肢と論拠が増える</figcaption></figure>
<figure><img src="r4-5-focused.png" alt="決定候補が現れる"><figcaption>3　決定候補が現れる</figcaption></figure>
<figure><img src="r4-confirmed-focused.png" alt="人が確定する"><figcaption>4　人が確定する</figcaption></figure>
</div><h2>別の会議構造での確認</h2><div class="grid"><figure><img src="r5-4-focused.png" alt="未解決事項と次の対応"><figcaption>未解決事項と次の対応</figcaption></figure>
__ACTUAL__</div></html>'''
    actual = ('<figure><img src="r4-actual-focused.png" alt="実Analyzer生成の決定候補">'
              '<figcaption>実Analyzer試行：決定候補（品質評価中）</figcaption></figure>'
              if args.real_analyzer else '')
    (destination / "index.html").write_text(page.replace("__ACTUAL__", actual), encoding="utf-8")
    print("controlled Shared View stages: R4 2/4/5/confirmed; R5 4; actual R4/R5 if supplied")


def write_sample(destination: Path, html: str, replay) -> None:
    snapshot = {
        "state": replay.state,
        "live_state": {"runtime_state": "active"},
        "map": map_projection(replay.state, replay.events, StableLayout()),
    }
    payload = json.dumps(snapshot, ensure_ascii=False).replace("</", "<\\/")
    shim = "<script>window.fetch=async()=>({ok:true,json:async()=>(" + payload + ")});</script><script>"
    page = html.replace("<script>", shim, 1)
    if page == html:
        raise RuntimeError("Shared View script entry point not found")
    destination.write_text(page, encoding="utf-8")


if __name__ == "__main__":
    main()
