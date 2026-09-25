// Render the synthetic meeting with the actual Shared View browser code.
// Requires the local prototype server at 127.0.0.1:18080. No provider calls.
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { chromium } = require('playwright');

const root = path.resolve(__dirname, '..');
const out = path.join(root, 'tmp', 'canvas-motion');
const scenes = JSON.parse(fs.readFileSync(path.join(root, 'tmp', 'canvas-motion-scenes.json'), 'utf8'));
fs.mkdirSync(out, { recursive: true });

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 1, reducedMotion: 'no-preference' });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  let currentSnapshot = scenes[0].snapshot;
  await page.route('**/api/live', route => route.fulfill({ contentType: 'application/json',
    body: JSON.stringify(currentSnapshot) }));
  await page.goto('http://127.0.0.1:18080/shared?viewport=1920x1080', { waitUntil: 'networkidle' });
  const entries = [];
  const nodeGeometry = new Map();
  for (let index = 0; index < scenes.length; index++) {
    const item = scenes[index];
    currentSnapshot = item.snapshot;
    await page.evaluate(({ snapshot }) => {
      renderShared(snapshot);
    }, item);
    const state = await page.evaluate(() => ({
      focus: document.querySelector('.canvas-node.focus')?.dataset.nodeId || null,
      nodeCount: document.querySelectorAll('.canvas-node').length,
      final: document.querySelector('.shared-main')?.classList.contains('final'),
      scrollX: document.documentElement.scrollWidth > innerWidth,
      scrollY: document.documentElement.scrollHeight > innerHeight,
      detailTime: document.querySelector('.canvas-detail-time')?.textContent || null,
      nodeTime: document.querySelector('.canvas-node.focus .canvas-time')?.textContent || null,
      markerCount: document.querySelectorAll('.canvas-final-marker').length,
      finalRelationCount: document.querySelectorAll('.canvas-final-relations line').length,
      finalRelationArrows: [...document.querySelectorAll('.canvas-final-relations line')]
        .every(line => !!line.getAttribute('marker-end')),
      sharedTargetTipGap: (() => {
        const lines=[...document.querySelectorAll('.canvas-final-relations line[data-target="move"]')];
        if (lines.length<2) return null;
        const tips=lines.map(line=>({x:Number(line.getAttribute('x2')),y:Number(line.getAttribute('y2'))}));
        return Math.min(...tips.flatMap((tip,index)=>tips.slice(index+1)
          .map(other=>Math.hypot(tip.x-other.x,tip.y-other.y))));
      })(),
      noRelationLabels: !document.querySelector('.canvas-edge-label, .relation-badge'),
      noDetachedFinalEdges: !document.querySelector('.canvas-world .canvas-edge') &&
        !document.querySelector('.canvas-final-leaders'),
      finalMarkerTypes: [...document.querySelectorAll('.canvas-final-marker')]
        .map(node => ({id:node.dataset.nodeId, type:[...node.classList].find(value =>
          ['idea','option','concern','decision','open_item','action'].includes(value)),
          independent:node.classList.contains('independent'),
          unconfirmed:node.classList.contains('unconfirmed')})),
      finalMarkerLines: Object.fromEntries([...document.querySelectorAll('.canvas-final-marker')]
        .map(node => {
          const label=node.querySelector('.canvas-final-label');
          return [node.dataset.nodeId,Math.round(label.getBoundingClientRect().height /
            parseFloat(getComputedStyle(label).lineHeight))];
        })),
      finalLabelsFit: [...document.querySelectorAll('.canvas-final-label')]
        .every(label => label.scrollWidth <= label.clientWidth + 2),
      roadTermIntact: (() => {
        const card=document.querySelector('.canvas-final-marker[data-node-id="truck-risk"]');
        const word=[...card?.querySelectorAll('.canvas-word') || []]
          .find(node => node.textContent === '通行止め');
        return !!word && word.getClientRects().length === 1 &&
          card.querySelector('.canvas-final-label').textContent === '輸送路が一部通行止めの可能性';
      })(),
      counts: Object.fromEntries([...document.querySelectorAll('.canvas-count')]
        .map(item => [item.dataset.countType, Number(item.querySelector('strong')?.textContent)])),
      geometry: Object.fromEntries([...document.querySelectorAll('.canvas-node')]
        .map(node => [node.dataset.nodeId, {
          width: getComputedStyle(node).width,
          fontSize: getComputedStyle(node.querySelector('.canvas-label')).fontSize,
        }])),
      peripheralCardOverlaps: [...document.querySelectorAll('.canvas-peripheral')].filter(peripheral => {
        const a = peripheral.getBoundingClientRect();
        return [...document.querySelectorAll('.canvas-node')].some(node => {
          const b = node.getBoundingClientRect();
          return Math.min(a.right,b.right)-Math.max(a.left,b.left)>4 &&
            Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)>4;
        });
      }).length,
    }));
    const expected = item.snapshot.map.semantic_canvas;
    const expectedCounts = {idea:0,option:0,concern:0,candidate:0,confirmed:0,open_item:0,action:0};
    for (const node of expected.nodes) {
      if (['archived','revoked','resolved','completed'].includes(node.status)) continue;
      const key=node.type==='decision' ? (node.status==='confirmed' ? 'confirmed' : 'candidate') : node.type;
      if (Object.hasOwn(expectedCounts,key)) expectedCounts[key]++;
    }
    if (state.scrollX || state.scrollY || (!state.final && state.nodeCount > 5) ||
      (!state.final && state.focus !== expected.focus_id) ||
      (!state.final && state.focus && state.detailTime !== state.nodeTime) ||
      JSON.stringify(state.counts)!==JSON.stringify(expectedCounts) ||
      (state.final && (state.markerCount === 0 || state.finalRelationCount === 0 ||
        !state.finalRelationArrows || !state.noRelationLabels ||
        state.sharedTargetTipGap === null || state.sharedTargetTipGap < 18 ||
        !['move','sms','decision'].every(id => state.finalMarkerLines[id] === 1) ||
        !state.finalLabelsFit || !state.roadTermIntact ||
        !state.noDetachedFinalEdges ||
        !['decision','open_item','action'].every(type => state.finalMarkerTypes.some(item => item.type===type)) ||
        !state.finalMarkerTypes.some(item => item.independent) ||
        !state.finalMarkerTypes.some(item => item.unconfirmed)))) {
      throw new Error(`Scene ${index + 1} invalid: ${JSON.stringify(state)}`);
    }
    for (const [nodeId, geometry] of Object.entries(state.geometry)) {
      if (nodeGeometry.has(nodeId) && JSON.stringify(nodeGeometry.get(nodeId))!==JSON.stringify(geometry)) {
        throw new Error(`Node ${nodeId} changed size when focus moved: ${JSON.stringify(geometry)}`);
      }
      nodeGeometry.set(nodeId,geometry);
    }
    for (let frame = 0; frame < 5; frame++) {
      await page.waitForTimeout(frame === 0 ? 75 : 145);
      const filename = path.join(out, `scene-${String(index).padStart(2, '0')}-${frame}.jpg`);
      await page.screenshot({ path: filename, type: 'jpeg', quality: 86 });
      entries.push({ filename, duration: frame === 4 ? 1.6 : .145 });
    }
    if (state.final) await page.screenshot({ path: path.join(out, 'final-review.png'), type: 'png' });
    console.log(`${index + 1}/${scenes.length} ${item.title}: ${JSON.stringify(state)}`);
  }
  await browser.close();
  if (errors.length) throw new Error(`Browser errors: ${errors.join('; ')}`);
  const manifest = path.join(out, 'frames.txt');
  fs.writeFileSync(manifest, entries.map(({ filename, duration }) =>
    `file '${filename.replaceAll("'", "'\\''")}'\nduration ${duration}`).join('\n') +
    `\nfile '${entries.at(-1).filename}'\n`);
  const movie = path.join(root, 'tmp', 'ronro-semantic-canvas-motion.mp4');
  const result = spawnSync('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0',
    '-i', manifest, '-vf', 'fps=24,format=yuv420p', '-c:v', 'libx264', '-crf', '22',
    '-preset', 'medium', '-movflags', '+faststart', movie], { encoding: 'utf8' });
  if (result.status !== 0) throw new Error(`ffmpeg: ${result.stderr}`);
  console.log(`VIDEO ${movie}`);
})().catch(error => { console.error(error); process.exit(1); });
