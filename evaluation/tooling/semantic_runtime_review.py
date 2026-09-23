"""Private review entry point from actual Analyzer-generated Canonical Graphs.

The output is intentionally outside Public Git and contains generated Node
labels. Human-reviewed expectations remain a comparison, never model input.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from prototype.semantic_projection import focused_flow, final_discussion_map

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--score", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.output.is_absolute() or ROOT in args.output.parents:
        raise ValueError("Human review artifact must remain outside Public Git")
    scores = {(row["case"], row["run"]): row for row in json.loads(args.score.read_text())["scores"]}
    datasets = {}
    for run in json.loads(args.input.read_text())["results"]:
        graph, events = run["graph"], run["events"]
        key = f"{run['case_id']}-{run['run']}"
        datasets[key] = {"case": run["case_id"], "run": run["run"], "graph": graph,
                         "flow": focused_flow(graph, events), "final": final_discussion_map(graph, events),
                         "score": scores[(run["case_id"], run["run"])]}
    payload = json.dumps(datasets, ensure_ascii=False).replace("</", "<\\/")
    page = '''<!doctype html><html lang="ja"><meta charset="utf-8"><title>RONRO 実Analyzer意味Graphレビュー</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#eef2f5;color:#172e3a;font-family:-apple-system,"Hiragino Kaku Gothic ProN","Yu Gothic",sans-serif}
header{padding:14px 22px;background:#fff;display:flex;gap:20px;align-items:center}select{font-size:18px;padding:6px}button{font-size:17px;padding:7px 16px;border:1px solid #b8c7ce;background:#fff;border-radius:8px;cursor:pointer}button.active{background:#163f52;color:#fff}.note{padding:10px 22px;color:#405863;font-size:15px}
.stage{width:1920px;height:1080px;overflow:hidden;background:#f8fbfc;position:relative;padding:54px 68px}.capture header,.capture .note{display:none}.title{font-size:28px;font-weight:700;margin:0 0 28px}.sub{font-size:17px;color:#59727d}.panes{display:grid;grid-template-columns:1330px 430px;gap:40px;height:900px}.overview{background:#fff;border:1px solid #d9e4e9;border-radius:22px;padding:42px;overflow:hidden}.detail{background:#edf3f5;border-radius:18px;padding:28px;overflow:hidden}.detail h3{font-size:22px;color:#3a5765;margin:0 0 22px}.detail p{font-size:23px;line-height:1.6;overflow-wrap:anywhere}.node{border:2px solid #b7cbd4;border-radius:17px;background:#fff;padding:20px 25px;min-width:0}.node .label{font-size:31px;font-weight:650;line-height:1.38;overflow-wrap:anywhere}.node .meta{font-size:15px;color:#687f8a;margin-top:10px}.focus-view .node .meta{display:none}.node.focus{border:4px solid #1e6681;background:#eff8fa}.node.focus .label{font-size:37px}.row{display:flex;gap:18px;justify-content:center;align-items:stretch;margin:12px 0}.row .node{flex:1;max-width:560px}.connector{color:#557889;text-align:center;font-size:20px;margin:15px}.arg{border-left:6px solid #51a283;padding-left:18px}.arg.opposes{border-color:#b76d6d}.arg .label{font-size:25px}.argtag{font-size:17px;color:#267858}.arg.opposes .argtag{color:#a04f4f}.arguments{margin-top:35px;padding-top:20px;border-top:2px dashed #c1d1d9}.empty{font-size:24px;color:#78909b;margin:40px}.maplist{display:grid;grid-template-columns:repeat(2,1fr);gap:24px}.group{background:#fff;border:1px solid #dae5e9;border-radius:18px;padding:23px;overflow:hidden}.group h3{font-size:20px;margin:0 0 12px;color:#476675}.group .node{margin:10px 0;padding:14px}.group .node .label{font-size:24px}.edge{font-size:19px;padding:10px;border-bottom:1px solid #e1e9ed}.edge.provenance{color:#4a6d7c}.edge.supports{color:#217952}.edge.opposes{color:#ae5a55}.scroll{overflow:auto;height:820px}.score{font-size:19px;line-height:1.8}.small{font-size:17px;color:#58717d}
.focus-view .participant-side{display:flex;flex-direction:column;gap:16px;min-height:0}.focus-view .detail{flex:0 0 auto;max-height:300px}.focus-view .detail p{margin:0}.focus-view .state-rail{flex:1;min-height:0;background:#fff;border:1px solid #d9e4e9;border-radius:18px;padding:22px 28px;overflow:hidden}.focus-view .state-section{padding:11px 0;border-bottom:1px solid #e0e8ec}.focus-view .state-section:last-child{border-bottom:0}.focus-view .state-section h3{margin:0 0 6px;font-size:23px;line-height:1.25}.focus-view .state-section.candidate h3{color:#84682c}.focus-view .state-section.confirmed h3{color:#276746}.focus-view .state-section.open h3{color:#6c548e}.focus-view .state-section.action h3{color:#27704a}.focus-view .state-item{font-size:21px;line-height:1.34;font-weight:600;overflow-wrap:anywhere}.focus-view .state-empty,.focus-view .state-more{font-size:18px;color:#697e89}.focus-view .state-detail{font-size:17px;color:#526b76;font-weight:400}
</style><header><strong>実Analyzer生成Graph・Human Review</strong><select id="dataset"></select><button data-view="graph">Canonical Graph</button><button data-view="focused">Focused Flow</button><button data-view="final">Final Map</button></header><div class="note">実Analyzerから生成したNode/Relationです。Human想定線で置換していません。線は現在の解釈であり、人が訂正できます。R5の事前Human決定は新規実行に注入していません。</div><div id="stage" class="stage"></div>
<script>const data=__DATA__;const q=new URLSearchParams(location.search);if(q.get('screenshot')==='1')document.body.classList.add('capture');let key=q.get('dataset')||'R3-3',view=q.get('view')||'focused';const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));const node=(n,cls='')=>`<div class="node ${cls}"><div class="label">${esc(n.label)}</div><div class="meta">${esc(n.type)}・${esc(n.status)}</div></div>`;
const byId=d=>Object.fromEntries(d.graph.nodes.map(n=>[n.id,n]));
function focused(d){
 const f=d.flow,n=f.nodes,focus=n.find(x=>x.position==='focus');
 const parents=n.filter(x=>['parent','ancestor'].includes(x.position));
 const children=n.filter(x=>['child','descendant'].includes(x.position));
 const args=n.filter(x=>['argument','context'].includes(x.position));
 const argumentCard=x=>{const incoming=f.argument_edges.find(e=>e.source_node_id===x.id&&e.target_node_id===focus?.id);
   const outgoing=f.argument_edges.find(e=>e.source_node_id===focus?.id&&e.target_node_id===x.id);
   const edge=incoming||outgoing;const kind=edge?.type==='opposes'?'opposes':'';
   const caption=incoming?(kind?'この話への懸念':'この話を支える理由'):
     outgoing?(kind?'この話が反対する案':'この話が後押しする案'):'あわせて出た話';
   return `<div class="node arg ${kind}"><div class="argtag">${caption}</div><div class="label">${esc(x.label)}</div></div>`};
 const live=d.graph.nodes.filter(x=>!['archived','revoked','resolved','completed'].includes(x.status));
 const state=(title,cls,items,showEmpty=false)=>items.length||showEmpty?`<section class="state-section ${cls}"><h3>${title}</h3>${items.slice(0,2).map(x=>`<div class="state-item">${esc(x.label)}${x.type==='action'&&(x.action?.owner||x.action?.due_date)?`<div class="state-detail">${[x.action.owner?'担当：'+x.action.owner:'',x.action.due_date?'期限：'+x.action.due_date:''].filter(Boolean).map(esc).join(' ／ ')}</div>`:''}</div>`).join('')||'<div class="state-empty">まだありません</div>'}${items.length>2?`<div class="state-more">ほか${items.length-2}件</div>`:''}</section>`:'';
 const rail=state('決定候補','candidate',live.filter(x=>x.type==='decision'&&x.status==='candidate'),true)+state('確定事項','confirmed',live.filter(x=>x.type==='decision'&&x.status==='confirmed'))+state('未解決事項','open',live.filter(x=>x.type==='open_item'),true)+state('次の対応','action',live.filter(x=>x.type==='action'));
 return `<h1 class="title">今話していること <span class="sub">● 聞き取り中</span></h1><div class="panes"><div class="overview">${parents.length?`<div class="row">${parents.map(x=>node(x)).join('')}</div><div class="connector">この話を受けて ┊</div>`:''}${focus?`<div class="row">${node(focus,'focus')}</div>`:'<div class="empty">話を整理しています</div>'}${children.length?`<div class="connector">┊ ここから出た話</div><div class="row">${children.map(x=>node(x)).join('')}</div>`:''}${args.length?`<div class="arguments"><div class="row">${args.map(argumentCard).join('')}</div></div>`:''}</div><aside class="participant-side"><div class="detail"><h3>新しく加わったこと</h3><p>${esc(f.latest_detail?.canonical||'')}</p></div><div class="state-rail">${rail}</div></aside></div>`
}
function graph(d){const nodes=d.graph.nodes.filter(n=>n.type!=='topic'),edges=d.graph.edges.filter(e=>['discussion_provenance','supports','opposes'].includes(e.type)),lookup=byId(d),s=d.score;return `<h1 class="title">Analyzer生成 Canonical Graph <span class="sub">${esc(d.case)}・Run ${d.run}</span></h1><div class="maplist"><div class="group scroll"><h3>Nodes ${nodes.length}</h3>${nodes.map(x=>node(x)).join('')}</div><div class="group scroll"><h3>意味Relation ${edges.length}</h3>${edges.map(e=>`<div class="edge ${e.type}">${esc(lookup[e.source_node_id]?.label)}<br> ${e.type==='discussion_provenance'?'┊ 議論を受けて':e.type==='supports'?'＋ 支持':'－ 反対'}<br>${esc(lookup[e.target_node_id]?.label)}</div>`).join('')||'<p>意味Relationなし</p>'}<h3>Human Corpusとの照合</h3><div class="score">hit ${s.pairs.filter(x=>x.status==='hit').length} ／ miss ${s.pairs.filter(x=>x.status==='miss').length} ／ 比較不可 ${s.pairs.filter(x=>x.status==='endpoint_unmatched').length}<br>候補外の線 ${s.outside_candidate_pairs.length}：個別確認が必要</div></div></div>`}
function finalMap(d){const f=d.final,lookup=byId(d),root=f.verified_roots.map(id=>lookup[id]).filter(Boolean),unlinked=f.unlinked.map(id=>lookup[id]).filter(Boolean),prov=f.semantic_edges.filter(e=>e.type==='discussion_provenance');return `<h1 class="title">会議後・複数入口の論点図 <span class="sub">${esc(d.case)}・Run ${d.run}</span></h1><div class="maplist"><div class="group scroll"><h3>人が独立と明示した入口 ${root.length}</h3>${root.map(x=>node(x)).join('')||'<p class="small">この実行では明示的な独立宣言なし</p>'}<h3>関係未確認のNode ${unlinked.length}</h3><p class="small">結線がないだけでは独立Rootと断定しません。後の議論・訂正でつながる可能性があります。</p>${unlinked.map(x=>node(x)).join('')}</div><div class="group scroll"><h3>議論由来の骨格 ${prov.length}</h3>${prov.map(e=>`<div class="edge provenance">${esc(lookup[e.source_node_id]?.label)}<br>┊ 議論を受けて<br>${esc(lookup[e.target_node_id]?.label)}</div>`).join('')||'<p>未確認</p>'}<h3>論拠・懸念</h3>${f.semantic_edges.filter(e=>e.type!=='discussion_provenance').map(e=>`<div class="edge ${e.type}">${esc(lookup[e.source_node_id]?.label)} ${e.type==='supports'?'＋ 支持':'－ 反対'} ${esc(lookup[e.target_node_id]?.label)}</div>`).join('')||'<p>未確認</p>'}</div></div>`}
function render(){const d=data[key],stage=document.getElementById('stage');stage.classList.toggle('focus-view',view==='focused');stage.innerHTML=view==='graph'?graph(d):view==='final'?finalMap(d):focused(d);document.querySelectorAll('button').forEach(b=>b.classList.toggle('active',b.dataset.view===view));history.replaceState(null,'',`?dataset=${key}&view=${view}`)}const sel=document.getElementById('dataset');sel.innerHTML=Object.keys(data).map(k=>`<option value="${k}">${k}</option>`).join('');sel.value=key;sel.onchange=()=>{key=sel.value;render()};document.querySelectorAll('button').forEach(b=>b.onclick=()=>{view=b.dataset.view;render()});render();</script></html>'''.replace("__DATA__", payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(page, encoding="utf-8")
    print(f"private review datasets: {len(datasets)}")


if __name__ == "__main__":
    main()
