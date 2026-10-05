// Record an actual 1920x1080 Live Shared View transition using synthetic Graphs.
// Requires the local prototype server and tmp/canvas-live-crossing-scenes.json.
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { chromium } = require('playwright');

const root = path.resolve(__dirname, '..');
const [before, after] = JSON.parse(fs.readFileSync(
  path.join(root, 'tmp', 'canvas-live-crossing-scenes.json'), 'utf8'));
const out = path.join(root, 'tmp', 'canvas-live-crossing');
fs.mkdirSync(out, { recursive: true });

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 1, reducedMotion: 'no-preference' });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  let currentSnapshot = before;
  await page.route('**/api/live', route => route.fulfill({contentType:'application/json',
    body:JSON.stringify(currentSnapshot)}));
  await page.goto('http://127.0.0.1:18080/shared?viewport=1920x1080',
    { waitUntil: 'networkidle' });
  await page.evaluate(snapshot => renderShared(snapshot), before);
  await page.waitForTimeout(700);
  const positions = snapshot => Object.fromEntries(snapshot.map.semantic_canvas.nodes
    .map(node => [node.id,[node.x,node.y]]));
  const prior = positions(before), next = positions(after);
  const moved = Object.keys(prior).filter(id => String(prior[id]) !== String(next[id]));
  if (moved.length !== 1 || moved[0] !== 'open')
    throw new Error(`Expected one local Live move: ${JSON.stringify(moved)}`);

  const entries = [];
  const capture = async (name, duration) => {
    const filename=path.join(out,name);
    await page.screenshot({path:filename,type:'jpeg',quality:86});
    entries.push({filename,duration});
  };
  await capture('before.jpg',2);
  currentSnapshot = after;
  await page.evaluate(snapshot => renderShared(snapshot), after);
  for (let index=0; index<16; index++) {
    await page.waitForTimeout(38);
    await capture(`motion-${String(index).padStart(2,'0')}.jpg`,.08);
  }
  await page.waitForTimeout(600);
  const finalState = await page.evaluate(() => ({
    open: (() => {
      const node=document.querySelector('.canvas-node[data-node-id="open"]');
      return [parseFloat(node.style.left),parseFloat(node.style.top)];
    })(),
    focusCenter: (() => {
      const node=document.querySelector('.canvas-node.focus').getBoundingClientRect();
      const stage=document.querySelector('.canvas-stage').getBoundingClientRect();
      return {x:Math.round((node.left+node.right)/2-stage.left),
        y:Math.round((node.top+node.bottom)/2-stage.top),
        stageWidth:Math.round(stage.width),stageHeight:Math.round(stage.height)};
    })(),
    edges:document.querySelectorAll('.canvas-edge').length,
    hiddenEdges:document.querySelector('.canvas-edges')?.classList.contains('reflowing'),
    scrollX:document.documentElement.scrollWidth>innerWidth,
    scrollY:document.documentElement.scrollHeight>innerHeight,
  }));
  await capture('after.jpg',3);
  await browser.close();
  if (errors.length || finalState.edges !== 3 || finalState.hiddenEdges ||
      finalState.scrollX || finalState.scrollY ||
      Math.abs(finalState.focusCenter.x-finalState.focusCenter.stageWidth/2)>24 ||
      String(finalState.open) !== String(next.open))
    throw new Error(`Invalid Live reflow: ${JSON.stringify({errors,finalState})}`);

  const manifest=path.join(out,'frames.txt');
  fs.writeFileSync(manifest,entries.map(({filename,duration}) =>
    `file '${filename.replaceAll("'", "'\\''")}'\nduration ${duration}`).join('\n')+
    `\nfile '${entries.at(-1).filename}'\n`);
  const movie=path.join(root,'tmp','ronro-canvas-live-crossing-reflow.mp4');
  const result=spawnSync('ffmpeg',['-y','-loglevel','error','-f','concat','-safe','0',
    '-i',manifest,'-vf','fps=24,format=yuv420p','-c:v','libx264','-crf','22',
    '-preset','medium','-movflags','+faststart',movie],{encoding:'utf8'});
  if (result.status!==0) throw new Error(`ffmpeg: ${result.stderr}`);
  console.log(JSON.stringify({movie,moved,finalState}));
})().catch(error => { console.error(error); process.exit(1); });
