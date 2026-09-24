// Offline 1920x1080 browser QA for the Semantic Canvas candidate.
// Start the local prototype server first; no provider calls or recording data.
const { chromium } = require('playwright');
const { execFileSync } = require('node:child_process');

const python = `import json
from prototype.layout import StableLayout, map_projection
counts=((5,False),(15,False),(30,False),(60,False),(100,False),(300,False),(300,True))
for count,branched in counts:
    sid=f'canvas-scale-{count}' + ('-branched' if branched else '')
    nodes=[]; events=[]
    edges=[]
    for index in range(count):
        eid=f'event-{index:04d}'
        nodes.append({'id':f'n{index}','type':'idea','status':'active','label':f'議論項目 {index}',
                      'evidence_ids':[f'e{index}'],'source_event_ids':[eid]})
        events.append({'event_id':eid,'sequence':index*2+1,'event_type':'node_detected',
                       'source_evidence_ids':[f'e{index}'],'payload':{'node_type':'idea','label':f'議論項目 {index}'}})
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
    const live = await page.evaluate(() => ({
      primary: document.querySelectorAll('.canvas-node:not(.mid)').length,
      displayed: document.querySelectorAll('.canvas-node').length,
      peripheral: document.querySelectorAll('.canvas-peripheral').length,
      clippedPrimary: [...document.querySelectorAll('.canvas-node:not(.mid)')].filter(node => {
        const card=node.getBoundingClientRect(), stage=document.querySelector('.canvas-stage').getBoundingClientRect();
        return card.left<stage.left-2 || card.right>stage.right+2 || card.top<stage.top-2 || card.bottom>stage.bottom+2;
      }).length,
      scrollX: document.documentElement.scrollWidth > innerWidth,
      scrollY: document.documentElement.scrollHeight > innerHeight,
    }));
    if (snapshot.count === 300) await page.screenshot({ path: '/tmp/ronro-canvas-300-' + (snapshot.branched ? 'branched' : 'roots') + '-live.png' });
    snapshot.live_state.runtime_state = 'ended';
    await page.reload({ waitUntil: 'networkidle' });
    const final = await page.evaluate(() => ({
      markers: document.querySelectorAll('.canvas-final-marker').length,
      topology: document.querySelectorAll('.canvas-final-topology circle').length,
      scrollX: document.documentElement.scrollWidth > innerWidth,
      scrollY: document.documentElement.scrollHeight > innerHeight,
    }));
    if (snapshot.count === 300) await page.screenshot({ path: '/tmp/ronro-canvas-300-' + (snapshot.branched ? 'branched' : 'roots') + '-final.png' });
    results.push({ count: snapshot.count, branched: snapshot.branched, live, final, errors });
    await page.close();
  }
  await browser.close();
  console.log(JSON.stringify(results));
  if (results.some(item => item.errors.length || item.live.scrollX || item.live.scrollY ||
    item.final.scrollX || item.final.scrollY || item.live.primary > 5 || item.live.clippedPrimary ||
    !item.final.topology)) process.exit(1);
})().catch(error => { console.error(error); process.exit(1); });
