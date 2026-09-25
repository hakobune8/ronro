// Offline 1920x1080 browser QA for the Semantic Canvas candidate.
// Start the local prototype server first; no provider calls or recording data.
const { chromium } = require('playwright');
const { execFileSync } = require('node:child_process');

const python = `import copy
import json
from datetime import datetime,timedelta,timezone
from pathlib import Path
from evaluation.tooling.semantic_hypothesis_review import build_case
from prototype.display_labels import POLICY_VERSION, VERSION as LABEL_VERSION, content_hash
from prototype.layout import StableLayout, map_projection
counts=((5,False),(15,False),(30,False),(60,False),(100,False),(300,False),(300,True))
for count,branched in counts:
    sid=f'canvas-scale-{count}' + ('-branched' if branched else '')
    nodes=[]; events=[]
    edges=[]
    subjects=('避難所の給水','物資の配分','道路の復旧','河川の点検','地域間の連携',
              '要配慮者の移動','通信手段の確保','被害情報の共有','復旧人員の調整','住民への周知')
    places=('北部','南部','東部','西部','沿岸部')
    phases=('現状を確認','不足箇所を整理','対応案を検討','実施条件を確認','懸念を共有','次の調査を決める')
    for index in range(count):
        eid=f'event-{index:04d}'
        occurred_at=(datetime(2026,9,25,tzinfo=timezone.utc)+timedelta(seconds=index*12)).isoformat().replace('+00:00','Z')
        subject=subjects[(index//30)%len(subjects)]
        part=index%30
        label=subject if part==0 else f'{subject}：{places[(part-1)//6]}の{phases[(part-1)%6]}'
        nodes.append({'id':f'n{index}','type':'idea','status':'active','label':label,
                      'created_at':occurred_at,'updated_at':occurred_at,
                      'evidence_ids':[f'e{index}'],'source_event_ids':[eid]})
        events.append({'event_id':eid,'sequence':index*2+1,'event_type':'node_detected',
                       'occurred_at':occurred_at,'source_evidence_ids':[f'e{index}'],
                       'payload':{'node_type':'idea','label':label}})
        if branched and index%30:
            base=(index//30)*30
            parent=base+(index%30-1)//3
            rid=f'edge-{index:04d}'
            edges.append({'id':rid,'type':'discussion_provenance','source_node_id':f'n{parent}',
                          'target_node_id':f'n{index}','source_event_ids':[rid]})
            events.append({'event_id':rid,'sequence':index*2+2,'event_type':'relation_detected',
                           'source_evidence_ids':[f'e{index}'],
                           'payload':{'source_node_id':f'n{parent}','target_node_id':f'n{index}',
                                      'relation_type':'discussion_provenance'}})
    graph={'session_id':sid,'revision':count,'nodes':nodes,'edges':edges,
           'current_topic':{'primary_topic_id':None}}
    state={'graph':graph}
    projected=map_projection(state,events,StableLayout())
    projected['shared']={}
    print(json.dumps({'count':count,'branched':branched,'state':state,'map':projected,
                      'live_state':{'runtime_state':'active'}},ensure_ascii=False))
root=Path.cwd()
cases=json.loads((root/'evaluation/relation-corpus/corpus.json').read_text())['controlled_cases']
classes={p['id']:p['classification'] for p in json.loads((root/'evaluation/relation-corpus/minimal_model_classification.json').read_text())['pairs']}
result,ids=build_case(cases[3],classes)
focus_id=ids['r4-n5']
node=next(node for node in result.state['graph']['nodes'] if node['id']==focus_id)
presentation={focus_id:{'version':LABEL_VERSION,'policy':POLICY_VERSION,
                        'content_hash':content_hash(node),
                        'sequence':result.state['graph']['last_event_sequence'],
                        'display_label':'倉庫の水を三避難所へ再配置する'}}
print(json.dumps({'count':'r4','branched':False,'state':result.state,
                  'map':map_projection(result.state,result.events,StableLayout(),presentation),
                  'live_state':{'runtime_state':'active'}},ensure_ascii=False))
for case_name,repetitions in (('r4-medium',2),('r4-long',8)):
    long_state=copy.deepcopy(result.state)
    long_node=next(item for item in long_state['graph']['nodes'] if item['id']==focus_id)
    long_node['label']=''.join(['三避難所の初日の飲料水不足について、既存倉庫の水を再配置する案が決定候補として挙がった。']*repetitions)
    long_presentation={focus_id:{'version':LABEL_VERSION,'policy':POLICY_VERSION,
                                 'content_hash':content_hash(long_node),
                                 'sequence':long_state['graph']['last_event_sequence'],
                                 'display_label':'倉庫の水を三避難所へ再配置する'}}
    print(json.dumps({'count':case_name,'branched':False,'state':long_state,
                      'map':map_projection(long_state,result.events,StableLayout(),long_presentation),
                      'live_state':{'runtime_state':'active'}},ensure_ascii=False))
spaced_state=copy.deepcopy(result.state)
spaced_events=copy.deepcopy(result.events)
for index,item in enumerate(spaced_state['graph']['nodes']):
    at=f'2026-09-25T00:{(2,5,8,12,19)[index]:02d}:00Z'
    item['created_at']=at
    item['updated_at']=at
    for event in spaced_events:
        if event['event_id'] in item.get('source_event_ids',[]):
            event['occurred_at']=at
for case_name,repetitions in (('r4-timed',1),('r4-timed-long',8)):
    timed_state=copy.deepcopy(spaced_state)
    timed_node=next(item for item in timed_state['graph']['nodes'] if item['id']==focus_id)
    if repetitions>1:
        timed_node['label']=''.join(['三避難所の初日の飲料水不足について、既存倉庫の水を再配置する案が決定候補として挙がった。']*repetitions)
    timed_presentation={focus_id:{'version':LABEL_VERSION,'policy':POLICY_VERSION,
                                  'content_hash':content_hash(timed_node),
                                  'sequence':timed_state['graph']['last_event_sequence'],
                                  'display_label':'倉庫の水を三避難所へ再配置する'}}
    print(json.dumps({'count':case_name,'branched':False,'state':timed_state,
                      'map':map_projection(timed_state,spaced_events,StableLayout(),timed_presentation),
                      'live_state':{'runtime_state':'active'}},ensure_ascii=False))`;
const snapshots = execFileSync('.venv/bin/python', ['-c', python], { encoding: 'utf8' })
  .trim().split('\n').map(line => JSON.parse(line));

(async () => {
  const browser = await chromium.launch({ headless: true });
  const results = [];
  for (const snapshot of snapshots) {
    const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/api/sessions/canvas-scale*', route =>
      route.fulfill({ contentType: 'application/json', body: JSON.stringify(snapshot) }));
    const url = 'http://127.0.0.1:18080/shared?fixture=canvas-scale-' + snapshot.count +
      (snapshot.branched ? '-branched' : '') + '&viewport=1920x1080';
    await page.goto(url, { waitUntil: 'networkidle' });
    const live = await page.evaluate(expected => ({
      primary: document.querySelectorAll('.canvas-node:not(.mid)').length,
      displayed: document.querySelectorAll('.canvas-node').length,
      peripheral: document.querySelectorAll('.canvas-peripheral').length,
      stageWidth: document.querySelector('.canvas-stage').getBoundingClientRect().width,
      detailInStage: !!document.querySelector('.canvas-stage > .canvas-detail'),
      focusAccentMatchesSubtitle: (() => {
        const focus=document.querySelector('.canvas-node.focus');
        const subtitle=document.querySelector('.canvas-detail');
        return !!focus && !!subtitle &&
          getComputedStyle(focus).borderTopColor===getComputedStyle(subtitle).borderTopColor;
      })(),
      nodeTimeMatchesSubtitle: (() => {
        const focusTime=document.querySelector('.canvas-node.focus .canvas-time');
        const subtitleTime=document.querySelector('.canvas-detail-time');
        return focusTime && subtitleTime ?
          focusTime.textContent===subtitleTime.textContent && focusTime.dateTime===subtitleTime.dateTime :
          !focusTime && !subtitleTime;
      })(),
      focusClock: document.querySelector('.canvas-node.focus .canvas-time')?.textContent || null,
      counts: Object.fromEntries([...document.querySelectorAll('.canvas-count')]
        .map(item => [item.dataset.countType, Number(item.querySelector('strong')?.textContent)])),
      fixedNodeGeometry: (() => {
        const nodes=[...document.querySelectorAll('.canvas-node')];
        if (!nodes.length) return false;
        const widths=new Set(nodes.map(node=>getComputedStyle(node).width));
        const sizes=new Set(nodes.map(node=>getComputedStyle(node.querySelector('.canvas-label')).fontSize));
        return widths.size===1 && sizes.size===1 &&
          getComputedStyle(nodes[0].querySelector('.canvas-label')).textWrap==='wrap';
      })(),
      peripheralBehindNodes: (() => {
        const world=document.querySelector('.canvas-world');
        const peripheral=document.querySelector('.canvas-periphery');
        return Number(getComputedStyle(world).zIndex)>Number(getComputedStyle(peripheral).zIndex);
      })(),
      subtitleHasHeading: !!document.querySelector('.canvas-detail h2'),
      typePaletteDistinct: (() => {
        const types=['idea','option','concern','decision','open_item','action'];
        const nodeColors=[], finalColors=[];
        for (const type of types) {
          const card=document.createElement('div');
          card.className=`canvas-node ${type}`;
          card.innerHTML='<span class="canvas-role">種別</span>';
          document.body.append(card);
          nodeColors.push([getComputedStyle(card).borderTopColor,
            getComputedStyle(card).backgroundColor,
            getComputedStyle(card.querySelector('.canvas-role')).backgroundColor].join('|'));
          card.remove();
          const marker=document.createElement('div');
          marker.className=`canvas-final-marker ${type}`;
          document.body.append(marker);
          finalColors.push([getComputedStyle(marker).borderTopColor,
            getComputedStyle(marker).backgroundColor].join('|'));
          marker.remove();
        }
        return new Set(nodeColors).size===types.length && new Set(finalColors).size===types.length;
      })(),
      focusCenterOffsetX: (() => {
        const focus=document.querySelector('.canvas-node.focus')?.getBoundingClientRect();
        const stage=document.querySelector('.canvas-stage').getBoundingClientRect();
        return focus ? Math.abs((focus.left+focus.right-stage.left-stage.right)/2) : 0;
      })(),
      subtitleAtBottom: (() => {
        const stage=document.querySelector('.canvas-stage').getBoundingClientRect();
        const subtitle=document.querySelector('.canvas-detail')?.getBoundingClientRect();
        return !!subtitle && Math.abs((stage.left+stage.right)/2-(subtitle.left+subtitle.right)/2)<2 &&
          stage.bottom-subtitle.bottom>=8 && stage.bottom-subtitle.bottom<=20;
      })(),
      cardsCoveredBySubtitle: (() => {
        const subtitle=document.querySelector('.canvas-detail')?.getBoundingClientRect();
        if (!subtitle) return 0;
        return [...document.querySelectorAll('.canvas-node')].filter(node => {
          const card=node.getBoundingClientRect();
          return Math.min(subtitle.right,card.right)-Math.max(subtitle.left,card.left)>4 &&
            Math.min(subtitle.bottom,card.bottom)-Math.max(subtitle.top,card.top)>4;
        }).length;
      })(),
      minSubtitleGap: (() => {
        const subtitle=document.querySelector('.canvas-detail')?.getBoundingClientRect();
        if (!subtitle) return null;
        const gaps=[...document.querySelectorAll('.canvas-node')].map(node=>node.getBoundingClientRect())
          .filter(card=>Math.min(subtitle.right,card.right)-Math.max(subtitle.left,card.left)>4)
          .map(card=>subtitle.top-card.bottom);
        return gaps.length ? Math.min(...gaps) : null;
      })(),
      hiddenEdgeLabels: (() => {
        const cards=[...document.querySelectorAll('.canvas-node')].map(node=>node.getBoundingClientRect());
        return [...document.querySelectorAll('.canvas-edge-label')].filter(label => {
          const r=label.getBoundingClientRect();
          return cards.some(card => Math.min(r.right,card.right)-Math.max(r.left,card.left)>2 &&
            Math.min(r.bottom,card.bottom)-Math.max(r.top,card.top)>2);
        }).length;
      })(),
      displayLabelIsShort: String(expected.caseId).startsWith('r4') ?
        document.querySelector('.canvas-node.focus .canvas-label')?.textContent === '倉庫の水を三避難所へ再配置する' : undefined,
      detailIsCanonical: String(expected.caseId).startsWith('r4') ?
        document.querySelector('.canvas-detail p')?.textContent ===
          expected.canvas.nodes.find(node=>node.id===expected.canvas.focus_id)?.canonical : undefined,
      subtitleComplete: (() => {
        const p=document.querySelector('.canvas-detail p');
        const subtitle=document.querySelector('.canvas-detail')?.getBoundingClientRect();
        const stage=document.querySelector('.canvas-stage').getBoundingClientRect();
        return !!p && !!subtitle && p.scrollHeight<=p.clientHeight+2 && subtitle.top>=stage.top;
      })(),
      subtitleOverflowNote: document.querySelector('.canvas-detail')?.classList.contains('is-overflowing') &&
        document.querySelector('.detail-overflow')?.textContent.trim() === '続きあり',
      subtitleLines: (() => {
        const p=document.querySelector('.canvas-detail p');
        return p ? p.clientHeight/parseFloat(getComputedStyle(p).lineHeight) : 0;
      })(),
      clippedPrimary: [...document.querySelectorAll('.canvas-node:not(.mid)')].filter(node => {
        const card=node.getBoundingClientRect(), stage=document.querySelector('.canvas-stage').getBoundingClientRect();
        return card.left<stage.left-2 || card.right>stage.right+2 || card.top<stage.top-2 || card.bottom>stage.bottom+2;
      }).length,
      scrollX: document.documentElement.scrollWidth > innerWidth,
      scrollY: document.documentElement.scrollHeight > innerHeight,
    }), { caseId: snapshot.count, canvas: snapshot.map.semantic_canvas });
    if (snapshot.count === 300) await page.screenshot({ path: '/tmp/ronro-canvas-300-' + (snapshot.branched ? 'branched' : 'roots') + '-live.png' });
    if (snapshot.count === 'r4') await page.screenshot({ path: '/tmp/ronro-canvas-r4-short-live.png' });
    if (snapshot.count === 'r4-long') await page.screenshot({ path: '/tmp/ronro-canvas-r4-long-live.png' });
    if (snapshot.count === 'r4-timed') await page.screenshot({ path: '/tmp/ronro-canvas-r4-timed-live.png' });
    if (snapshot.count === 'r4-timed-long') await page.screenshot({ path: '/tmp/ronro-canvas-r4-timed-long-live.png' });
    snapshot.live_state.runtime_state = 'ended';
    await page.reload({ waitUntil: 'networkidle' });
    const final = await page.evaluate(() => ({
      markers: document.querySelectorAll('.canvas-final-marker').length,
      markerClocks: document.querySelectorAll('.canvas-final-marker .canvas-time').length,
      markerClockOverlap: [...document.querySelectorAll('.canvas-final-marker')].filter(marker => {
        const clock=marker.querySelector('.canvas-time')?.getBoundingClientRect();
        const label=marker.querySelector('.canvas-final-label')?.getBoundingClientRect();
        const role=marker.querySelector('small')?.getBoundingClientRect();
        if (!clock) return false;
        const overlaps=other=>other && Math.min(clock.right,other.right)-Math.max(clock.left,other.left)>2 &&
          Math.min(clock.bottom,other.bottom)-Math.max(clock.top,other.top)>2;
        return overlaps(label) || overlaps(role);
      }).length,
      topology: document.querySelectorAll('.canvas-final-topology circle').length,
      stageWidth: document.querySelector('.canvas-stage').getBoundingClientRect().width,
      oldBottomNote: !!document.querySelector('.canvas-final-note'),
      neighborhoodCount: [...document.querySelectorAll('.canvas-final-marker')]
        .some(marker => /この周辺\d+件/.test(marker.textContent)),
      scrollX: document.documentElement.scrollWidth > innerWidth,
      scrollY: document.documentElement.scrollHeight > innerHeight,
    }));
    if (snapshot.count === 300) await page.screenshot({ path: '/tmp/ronro-canvas-300-' + (snapshot.branched ? 'branched' : 'roots') + '-final.png' });
    if (snapshot.count === 'r4') await page.screenshot({ path: '/tmp/ronro-canvas-r4-short-final.png' });
    if (snapshot.count === 'r4-timed') await page.screenshot({ path: '/tmp/ronro-canvas-r4-timed-final.png' });
    const expectedCounts = {idea:0,option:0,concern:0,candidate:0,confirmed:0,open_item:0,action:0};
    for (const node of snapshot.map.semantic_canvas.nodes) {
      if (['archived','revoked','resolved','completed'].includes(node.status)) continue;
      const key=node.type==='decision' ? (node.status==='confirmed' ? 'confirmed' : 'candidate') : node.type;
      if (Object.hasOwn(expectedCounts,key)) expectedCounts[key]++;
    }
    results.push({ count: snapshot.count, branched: snapshot.branched, live, final, errors,
      countsMatch: JSON.stringify(live.counts)===JSON.stringify(expectedCounts),
      near: snapshot.branched ? snapshot.map.semantic_canvas.near_ids : undefined });
    await page.close();
  }
  await browser.close();
  console.log(JSON.stringify(results));
  if (results.some(item => item.errors.length || item.live.scrollX || item.live.scrollY ||
    item.final.scrollX || item.final.scrollY || item.live.primary > 5 || item.live.clippedPrimary ||
    !item.countsMatch || !item.live.fixedNodeGeometry || !item.live.peripheralBehindNodes ||
    item.live.hiddenEdgeLabels || !item.live.detailInStage || !item.live.subtitleAtBottom ||
    item.live.subtitleHasHeading || !item.live.typePaletteDistinct ||
    !item.live.focusAccentMatchesSubtitle || !item.live.nodeTimeMatchesSubtitle ||
    (String(item.count).startsWith('r4') ?
      item.live.focusClock !== (String(item.count).startsWith('r4-timed') ? '09:19' : '09:01') || !item.final.markerClocks :
      !item.live.focusClock || !item.final.markerClocks) ||
    item.live.focusCenterOffsetX > 3 ||
    item.live.cardsCoveredBySubtitle ||
    (item.live.minSubtitleGap !== null && item.live.minSubtitleGap < 16) ||
    item.live.subtitleLines > 5.1 ||
    (['r4-long','r4-timed-long'].includes(item.count) ? !item.live.subtitleOverflowNote : !item.live.subtitleComplete) ||
    item.live.stageWidth !== item.final.stageWidth ||
    item.final.oldBottomNote || item.final.neighborhoodCount || item.final.markerClockOverlap ||
    item.live.displayLabelIsShort === false || item.live.detailIsCanonical === false ||
    !item.final.topology)) process.exit(1);
})().catch(error => { console.error(error); process.exit(1); });
