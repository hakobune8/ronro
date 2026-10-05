"""Create private offline snapshots of the actual Shared HTML. No server/LLM."""
import argparse
import copy
import json
from pathlib import Path

from prototype.layout import StableLayout, map_projection
from prototype.schema import SchemaValidator
from shared_projection_spike import replay


def main(args):
    root=Path(__file__).resolve().parents[2]
    data=json.loads(args.live.read_text());original=copy.deepcopy(data)
    history=replay(data,SchemaValidator(root/'schemas'))
    html=(root/'prototype/web/shared.html').read_text()
    args.out.mkdir(parents=True,exist_ok=False)
    layout=StableLayout();summary=[]
    for minute in (5,10,15):
        saved=json.loads((args.snapshots/f'{minute:02}min.json').read_text())
        row=next(r for r in reversed(history) if r['revision']==saved['graph']['revision'])
        state={**data['state'],'graph':saved['graph']}
        events=[e for e in data['events'] if e['sequence']<=row['sequence']]
        projection=map_projection(state,events,layout)
        assert projection['shared']['slots']==row['choices']['stable']
        assert projection['shared']==map_projection(state,events,StableLayout())['shared']
        snapshot={'state':{'graph':saved['graph']},'map':projection,'live_state':{'runtime_state':'active'}}
        payload=json.dumps(snapshot,ensure_ascii=False).replace('<','\\u003c')
        page=html.replace("const snapshot = demoFixture ? await fetchDemo() : await fetchLive();",'const snapshot = '+payload+';')
        page=page.replace('if (!demoFixture) window.setInterval(refresh, 1000);','// Offline immutable snapshot; no polling.')
        (args.out/f'{minute:02}min.html').write_text(page)
        summary.append({'minute':minute,'revision':saved['graph']['revision'],'overflow':projection['shared']['overflow']})
    assert original==data
    (args.out/'index.html').write_text('<meta charset="utf-8"><h1>実装済みShared View：保存T1再生</h1><p>Private / 視覚QA未完了。稼働表示は保存状態のモックです。音声再実行・接続なし。</p>'+''.join(f'<p><a href="{m:02}min.html">{m}分のShared View</a></p>' for m in (5,10,15)))
    print(json.dumps(summary))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--live',type=Path,required=True);p.add_argument('--snapshots',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    main(p.parse_args())
