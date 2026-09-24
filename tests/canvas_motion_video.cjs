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
  await page.addStyleTag({ content: `
    #motion-qa-caption { position: fixed; z-index: 100; right: 42px; top: 10px;
      padding: 8px 16px; border-radius: 9px; background: rgba(21,48,70,.90);
      color: white; font: 600 19px/1.3 -apple-system, "Hiragino Kaku Gothic ProN", sans-serif;
      pointer-events: none; text-align: right; max-width: 900px; }
    #motion-qa-caption small { font-size: 14px; opacity: .85; display: block; }
  ` });
  await page.evaluate(() => {
    const caption = document.createElement('div');
    caption.id = 'motion-qa-caption';
    caption.setAttribute('aria-label', '合成テスト場面');
    document.body.append(caption);
  });
  const entries = [];
  for (let index = 0; index < scenes.length; index++) {
    const item = scenes[index];
    currentSnapshot = item.snapshot;
    await page.evaluate(({ snapshot, title, note, minute, index, total }) => {
      document.querySelector('#motion-qa-caption').innerHTML =
        `<small>合成データ · ${index + 1}/${total} · 会議 ${String(minute).padStart(2, '0')}分</small>` +
        `${title}｜${note}`;
      renderShared(snapshot);
    }, { ...item, index, total: scenes.length });
    const state = await page.evaluate(() => ({
      focus: document.querySelector('.canvas-node.focus')?.dataset.nodeId || null,
      nodeCount: document.querySelectorAll('.canvas-node').length,
      final: document.querySelector('.shared-main')?.classList.contains('final'),
      scrollX: document.documentElement.scrollWidth > innerWidth,
      scrollY: document.documentElement.scrollHeight > innerHeight,
      detailTime: document.querySelector('.canvas-detail-time')?.textContent || null,
      nodeTime: document.querySelector('.canvas-node.focus .canvas-time')?.textContent || null,
      markerCount: document.querySelectorAll('.canvas-final-marker').length,
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
    if (state.scrollX || state.scrollY || (!state.final && state.nodeCount > 5) ||
      (!state.final && state.focus !== expected.focus_id) ||
      (!state.final && state.focus && state.detailTime !== state.nodeTime) ||
      (state.final && state.markerCount === 0)) {
      throw new Error(`Scene ${index + 1} invalid: ${JSON.stringify(state)}`);
    }
    for (let frame = 0; frame < 5; frame++) {
      await page.waitForTimeout(frame === 0 ? 75 : 145);
      const filename = path.join(out, `scene-${String(index).padStart(2, '0')}-${frame}.jpg`);
      await page.screenshot({ path: filename, type: 'jpeg', quality: 86 });
      entries.push({ filename, duration: frame === 4 ? 1.6 : .145 });
    }
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
