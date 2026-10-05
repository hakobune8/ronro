// Short, synthetic production-browser smoke for /control reconnect framing.
// Uses no real microphone or meeting content. Run only when /api/live is idle.
const assert = require('node:assert/strict');
const { chromium } = require('playwright');

const base = 'https://ronro.hakobune8.com';
const terminal = new Set(['ended', 'ended_with_incomplete_processing', 'failed']);

async function state() {
  const response = await fetch(`${base}/api/live`);
  assert.equal(response.status, 200);
  return (await response.json()).live_state;
}

async function until(check, milliseconds = 20000) {
  const deadline = Date.now() + milliseconds;
  while (Date.now() < deadline) {
    if (await check()) return;
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
  throw new Error('Timed out waiting for production browser/session state');
}

(async () => {
  assert.ok(['idle', ...terminal].includes((await state()).runtime_state), 'Refusing to interrupt an active session');
  const browser = await chromium.launch({ headless: true });
  let page;
  let controller;
  try {
    page = await browser.newPage();
    await page.addInitScript(() => {
      window.__sentSequences = [];
      const send = WebSocket.prototype.send;
      WebSocket.prototype.send = function (frame) {
        if (frame instanceof ArrayBuffer) window.__sentSequences.push(new DataView(frame).getUint32(8, true));
        return send.call(this, frame);
      };
      const track = { stop() {}, getSettings: () => ({}), label: 'synthetic', kind: 'audio', readyState: 'live', muted: false, enabled: true };
      const stream = { getTracks: () => [track], getAudioTracks: () => [track] };
      Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: { getUserMedia: async () => stream } });
      window.AudioContext = class {
        constructor() { this.sampleRate = 24000; this.audioWorklet = { addModule: async () => {} }; this.destination = {}; }
        async resume() {}
        async close() {}
        createMediaStreamSource() { return { connect() {}, disconnect() {} }; }
        createGain() { return { gain: { value: 0 }, connect() { return { connect() {} }; } }; }
      };
      window.AudioWorkletNode = class {
        constructor() { this.port = {}; }
        connect() { return { connect() {} }; }
        disconnect() {}
      };
    });
    await page.goto(`${base}/control`, { waitUntil: 'domcontentloaded' });
    controller = await page.evaluate(() => controllerInstanceId());
    await page.locator('#live-all-participants-consented').check();
    await page.locator('#live-start-continuous').click();
    await page.waitForFunction(() => Boolean(liveWorklet), null, { timeout: 20000 });
    await page.evaluate(() => {
      const samples = new Float32Array(2400);
      for (let i = 0; i < samples.length; i++) samples[i] = 0.02 * Math.sin(i / 17);
      liveWorklet.port.onmessage({ data: { type: 'pcm', samples, sampleRate: 24000 } });
    });
    await until(async () => (await state()).audio_chunk_sequence === 0);
    await page.evaluate(() => liveSocket.close());
    await page.waitForFunction(() => liveSocket === null);
    await until(async () => (await state()).stt_state === 'disconnected');
    await page.locator('#live-start-continuous').click();
    await page.waitForFunction(() => Boolean(liveWorklet), null, { timeout: 20000 });
    await page.evaluate(() => {
      const samples = new Float32Array(2400);
      for (let i = 0; i < samples.length; i++) samples[i] = 0.02 * Math.sin(i / 19);
      liveWorklet.port.onmessage({ data: { type: 'pcm', samples, sampleRate: 24000 } });
    });
    await until(async () => (await state()).audio_chunk_sequence === 1);
    assert.deepEqual(await page.evaluate(() => window.__sentSequences), [0, 1]);
    console.log('production browser reconnect: accepted audio frame sequences 0, 1; no sequence reset');
  } finally {
    if (controller && !terminal.has((await state()).runtime_state)) {
      await fetch(`${base}/api/live/stop`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ controller_id: controller }),
      });
      await until(async () => terminal.has((await state()).runtime_state), 60000);
    }
    if (page) await page.close();
    await browser.close();
    const final = await state();
    console.log(JSON.stringify({ runtime_state: final.runtime_state,
      audio_chunk_sequence: final.audio_chunk_sequence,
      possible_gap_count: final.metrics?.possible_evidence_gap_count,
      queue: { pending: final.queue?.pending, processing: final.queue?.processing, failed: final.queue?.failed } }));
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
