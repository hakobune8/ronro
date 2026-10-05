// Offline browser regression for the Controller and /control audio cursor.
// NODE_PATH=<bundled node_modules> node tests/live_audio_resume_qa.cjs
// No microphone, Provider, network, or real meeting data is used.
const assert = require('node:assert/strict');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { chromium } = require('playwright');

const root = path.resolve(__dirname, '..');

async function prepare(page) {
  await page.evaluate(() => {
    const track = { stop() {}, getSettings: () => ({}), label: 'synthetic', kind: 'audio', readyState: 'live', muted: false, enabled: true };
    const stream = { getTracks: () => [track], getAudioTracks: () => [track] };
    Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: { getUserMedia: async () => stream } });
    window.AudioContext = class {
      constructor() { this.sampleRate = 48000; this.audioWorklet = { addModule: async () => {} }; this.destination = {}; }
      async resume() {}
      async close() {}
      createMediaStreamSource() { return { connect() {}, disconnect() {} }; }
      createGain() { return { gain: { value: 0 }, connect() { return { connect() {} }; } }; }
    };
    window.AudioWorkletNode = class {
      constructor() { this.port = {}; window.__testWorklet = this; }
      connect() { return { connect() {} }; }
      disconnect() {}
    };
    window.WebSocket = class {
      static OPEN = 1;
      constructor() { this.readyState = 1; this.frames = []; window.__testSocket = this; }
      send(frame) { this.frames.push(frame); }
      close() { this.readyState = 3; this.onclose?.(); }
    };
    window.__testSnapshot = (lastSequence, audioEnd) => ({
      live_state: { runtime_state: 'active', mode: 'continuous', audio_chunk_sequence: lastSequence, audio_end_seconds: audioEnd },
    });
  });
}

async function assertFrame(page, expectedSequence, expectedStart) {
  const result = await page.evaluate(() => {
    window.__testWorklet.port.onmessage({ data: { type: 'pcm', samples: new Float32Array(2400), sampleRate: 24000 } });
    const frame = window.__testSocket.frames.find((item) => item instanceof ArrayBuffer);
    if (!frame) return null;
    const view = new DataView(frame);
    return { sequence: view.getUint32(8, true), start: view.getFloat64(12, true) };
  });
  assert.ok(result, 'audio frame was not sent');
  assert.equal(result.sequence, expectedSequence);
  assert.ok(Math.abs(result.start - expectedStart) < 1e-6);
}

async function checkControl(browser, startedSequence, startedEnd, acceptedSequence, acceptedEnd) {
  const page = await browser.newPage();
  await page.goto(pathToFileURL(path.join(root, 'prototype/web/index.html')).href);
  await prepare(page);
  await page.evaluate(({ startedSequence, startedEnd }) => {
    // /api/live/start may be older than the connection handshake if the
    // previous capture accepts frames while the new socket is connecting.
    getJson = async () => ({ ...window.__testSnapshot(startedSequence, startedEnd), websocket_url: 'ws://synthetic' });
    applyLiveSnapshot = () => {};
    setStatus = () => {};
    liveLog = () => {};
    requestLiveMicrophone = async () => navigator.mediaDevices.getUserMedia();
    document.getElementById('live-pilot-audio-consent').hidden = true;
  }, { startedSequence, startedEnd });
  await page.evaluate(() => startLiveSession('continuous'));
  const before = await page.evaluate(() => Boolean(window.__testWorklet));
  assert.equal(before, false, '/control started audio before the server handshake');
  await page.evaluate(({ acceptedSequence, acceptedEnd }) => {
    const socket = window.__testSocket;
    socket.onopen();
    if (acceptedSequence !== null) {
      socket.onmessage({ data: JSON.stringify({ type: 'runtime_snapshot', snapshot: window.__testSnapshot(acceptedSequence, acceptedEnd) }) });
    }
    socket.onmessage({ data: JSON.stringify({ type: 'stt_connected' }) });
  }, { acceptedSequence, acceptedEnd });
  if (acceptedSequence === null) {
    await page.waitForFunction(() => window.__testSocket.readyState === 3);
    assert.equal(await page.evaluate(() => Boolean(window.__testWorklet)), false);
    await page.close();
    return;
  }
  await page.waitForFunction(() => Boolean(window.__testWorklet));
  await assertFrame(page, acceptedSequence + 1, acceptedEnd);
  await page.close();
}

async function checkControlConsentPreflight(browser) {
  const page = await browser.newPage();
  await page.goto(pathToFileURL(path.join(root, 'prototype/web/index.html')).href);
  await prepare(page);
  await page.evaluate(() => {
    window.__startCalls = 0;
    getJson = async (route) => {
      if (route.startsWith('/api/live?')) return { live_state: { runtime_state: 'idle', pilot_audio: { enabled: true } } };
      if (route === '/api/live/start') {
        window.__startCalls += 1;
        return { ...window.__testSnapshot(-1, 0), websocket_url: 'ws://synthetic' };
      }
      throw new Error(`unexpected route: ${route}`);
    };
  });
  await page.evaluate(() => startLiveSession('continuous'));
  assert.equal(await page.evaluate(() => window.__startCalls), 0, 'recording began without consent');
  assert.equal(await page.locator('#live-pilot-audio-consent').isVisible(), true);
  await page.locator('#live-all-participants-consented').check();
  await page.evaluate(() => startLiveSession('continuous'));
  assert.equal(await page.evaluate(() => window.__startCalls), 1);
  await page.close();
}

async function checkPhone(browser, acceptedSequence, acceptedEnd) {
  const page = await browser.newPage();
  await page.goto(pathToFileURL(path.join(root, 'prototype/web/session.html')).href);
  await prepare(page);
  await page.evaluate(() => { render = () => {}; refresh = async () => {}; setNotice = () => {}; connectSocket('ws://synthetic'); });
  const before = await page.evaluate(() => Boolean(window.__testWorklet));
  assert.equal(before, false, '/session started audio before the server handshake');
  await page.evaluate(({ acceptedSequence, acceptedEnd }) => {
    const socket = window.__testSocket;
    socket.onopen();
    if (acceptedSequence !== null) {
      socket.onmessage({ data: JSON.stringify({ type: 'runtime_snapshot', snapshot: window.__testSnapshot(acceptedSequence, acceptedEnd) }) });
    }
    socket.onmessage({ data: JSON.stringify({ type: 'stt_connected' }) });
  }, { acceptedSequence, acceptedEnd });
  if (acceptedSequence === null) {
    await page.waitForFunction(() => window.__testSocket.readyState === 3);
    assert.equal(await page.evaluate(() => Boolean(window.__testWorklet)), false);
    await page.close();
    return;
  }
  await page.waitForFunction(() => Boolean(window.__testWorklet));
  await assertFrame(page, acceptedSequence + 1, acceptedEnd);
  await page.close();
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    await checkControlConsentPreflight(browser);
    await checkControl(browser, -1, 0, -1, 0);
    await checkControl(browser, 40, 4.1, 86, 8.7);
    await checkControl(browser, 86, 8.7, null, 0);
    await checkPhone(browser, -1, 0);
    await checkPhone(browser, 86, 8.7);
    await checkPhone(browser, null, 0);
    console.log('audio resume QA: consent preflight, fresh start, reconnect, and missing-cursor fail-closed on /control and /session');
  } finally {
    await browser.close();
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
