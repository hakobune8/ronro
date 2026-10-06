/* Account Service Pilot demo. Real audio; no browser-side raw-audio storage. */
(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const STORAGE_KEY = 'ronro.service-demo.session';
  const RATE = 24000;
  const CHUNK = 2400;
  let csrf = null;
  let sessionId = sessionStorage.getItem(STORAGE_KEY);
  let meeting = null;
  let socket = null;
  let media = null;
  let context = null;
  let source = null;
  let worklet = null;
  let sampleQueue = [];
  let nextSequence = 0;
  let sentSamples = 0;
  let busy = false;
  let refreshPromise = null;

  function status(message, error = false) {
    $('status').textContent = message;
    $('status').classList.toggle('error', error);
  }

  async function request(path, options = {}) {
    const response = await fetch(path, { credentials: 'same-origin', cache: 'no-store', ...options });
    const type = response.headers.get('content-type') || '';
    const value = type.includes('application/json') ? await response.json() : null;
    if (!response.ok) throw new Error(value?.error?.code || `HTTP ${response.status}`);
    return value;
  }

  async function mutate(path, body, method = 'POST') {
    if (!csrf) throw new Error('ログインが必要です');
    return request(path, {
      method,
      headers: { 'Content-Type': 'application/json', 'X-Ronro-CSRF': csrf },
      body: JSON.stringify(body),
    });
  }

  function controls() {
    const state = meeting?.capture_state;
    const ended = ['ended', 'ended_incomplete'].includes(meeting?.state);
    $('create').disabled = busy || (!!sessionId && (!meeting || !ended));
    $('start').disabled = busy || !sessionId || state !== 'created' || !$('consent').checked;
    $('pause').disabled = busy || state !== 'listening' || !socket;
    $('resume').disabled = busy || !['paused', 'reconnecting', 'resuming'].includes(state)
      || !$('consent').checked || !!socket;
    $('resume').textContent = state === 'reconnecting' ? '音声を再接続' : '再開';
    $('end').disabled = busy || !sessionId || ended || meeting?.state === 'deleting';
    $('pdf').hidden = !ended;
    $('shared-link').hidden = !sessionId;
    if (sessionId) $('shared-link').href = `/shared?service=1#session=${encodeURIComponent(sessionId)}`;
    if (ended && sessionId) $('pdf').href = `/api/service/sessions/${encodeURIComponent(sessionId)}/final.pdf`;
    $('meeting-meta').textContent = sessionId
      ? `会議の状態: ${meeting?.state || '確認中'} / 音声: ${state || '確認中'} / Graph: ${meeting?.graph_revision ?? '—'}`
      : 'このブラウザで開いている会議はありません。';
  }

  async function refresh() {
    if (!sessionId) return;
    if (refreshPromise) return refreshPromise;
    refreshPromise = (async () => { try {
      const base = `/api/service/sessions/${encodeURIComponent(sessionId)}`;
      meeting = await request(base);
      controls();
    } catch (error) {
      if (['session_not_found', 'session_deleted'].includes(error.message)) {
        sessionId = null; meeting = null; sessionStorage.removeItem(STORAGE_KEY);
        status('以前の会議は利用できません。デモでは再起動後の復旧を保証しません。', true);
      } else {
        status(`状態を確認できません: ${error.message}`, true);
      }
      controls();
    } finally { refreshPromise = null; } })();
    return refreshPromise;
  }

  function resample(samples, inputRate) {
    if (inputRate === RATE) return samples;
    const count = Math.max(1, Math.round(samples.length * RATE / inputRate));
    const result = new Float32Array(count);
    const ratio = inputRate / RATE;
    for (let i = 0; i < count; i += 1) {
      const position = i * ratio, left = Math.min(samples.length - 1, Math.floor(position));
      const right = Math.min(samples.length - 1, left + 1), fraction = position - left;
      result[i] = samples[left] * (1 - fraction) + samples[right] * fraction;
    }
    return result;
  }

  function sendChunk(samples) {
    if (!socket || socket.readyState !== WebSocket.OPEN) throw new Error('音声接続がありません');
    if (socket.bufferedAmount > 512 * 1024) throw new Error('音声送信が遅延しています');
    const frame = new ArrayBuffer(20 + samples.length * 2);
    const view = new DataView(frame);
    view.setUint8(0, 68); view.setUint8(1, 77); view.setUint8(2, 65); view.setUint8(3, 80);
    view.setUint8(4, 1); view.setUint32(8, nextSequence, true);
    view.setFloat64(12, sentSamples / RATE, true);
    for (let i = 0; i < samples.length; i += 1) {
      const value = Number.isFinite(samples[i]) ? Math.max(-1, Math.min(1, samples[i])) : 0;
      view.setInt16(20 + i * 2, Math.max(-32768, Math.min(32767,
        value >= 0 ? Math.round(value * 32767) : Math.round(value * 32768))), true);
    }
    socket.send(frame); nextSequence += 1; sentSamples += samples.length;
  }

  function onSamples(samples, sourceRate) {
    try {
      sampleQueue.push(...resample(samples, sourceRate));
      while (sampleQueue.length >= CHUNK) sendChunk(sampleQueue.splice(0, CHUNK));
    } catch (error) {
      stopMic();
      status(`音声を継続できません: ${error.message}。欠落の可能性があります。`, true);
      if (socket) socket.close();
    }
  }

  function stopMic() {
    if (worklet) { worklet.port.onmessage = null; worklet.disconnect(); worklet = null; }
    if (source) { source.disconnect(); source = null; }
    if (media) { media.getTracks().forEach((track) => track.stop()); media = null; }
    if (context) { context.close().catch(() => {}); context = null; }
  }

  function flushAudio() {
    if (!sampleQueue.length) return;
    const padded = sampleQueue.splice(0);
    while (padded.length < CHUNK) padded.push(0);
    sendChunk(padded);
  }

  async function beginMicrophone() {
    if (!media) throw new Error('マイクを利用できません');
    context = new AudioContext();
    await context.resume();
    await context.audioWorklet.addModule('/static/service-audio-worklet.js');
    source = context.createMediaStreamSource(media);
    worklet = new AudioWorkletNode(context, 'discussion-map-capture', {
      numberOfInputs: 1, numberOfOutputs: 1, outputChannelCount: [1],
    });
    worklet.port.onmessage = (event) => {
      if (event.data?.type === 'pcm') onSamples(event.data.samples, event.data.sampleRate || context.sampleRate);
    };
    source.connect(worklet);
    const mute = context.createGain(); mute.gain.value = 0;
    worklet.connect(mute).connect(context.destination);
    status('音声を聞いています。議論の内容は自動で論点図へ反映されます。');
  }

  async function openAudio(generation) {
    if (socket) throw new Error('既に音声接続があります');
    const scheme = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${scheme}//${location.host}/live/service/sessions/${encodeURIComponent(sessionId)}/audio?generation=${generation}`;
    socket = new WebSocket(url);
    const connectionSocket = socket;
    let expectedClose = false;
    connectionSocket.binaryType = 'arraybuffer';
    connectionSocket.onmessage = async (message) => {
      if (socket !== connectionSocket) return;
      let event;
      try { event = JSON.parse(message.data); } catch (_) { return; }
      if (event.type === 'capture_ready') {
        try { await refresh(); if (!worklet) await beginMicrophone(); }
        catch (error) { stopMic(); status(`音声開始失敗: ${error.message}`, true); connectionSocket.close(); }
      } else if (event.type === 'final_accepted') {
        await refresh();
      } else if (event.type === 'possible_evidence_gap') {
        status('一部の音声を記録できなかった可能性があります。会議は継続できます。', true);
      } else if (event.type === 'capture_paused') {
        expectedClose = true; stopMic(); connectionSocket.close(); socket = null;
        await refresh(); status(event.end_state === 'finalizing' ? '終了処理中です。' : '休憩中です。');
      }
    };
    connectionSocket.onclose = () => {
      if (socket !== connectionSocket) return;
      const unexpected = !expectedClose;
      socket = null;
      if (unexpected) stopMic();
      sampleQueue = [];
      if (unexpected) status('音声接続が切れました。欠落の可能性があります。状態を確認して再接続してください。', true);
      void refresh();
    };
    connectionSocket.onerror = () => {
      if (socket === connectionSocket) status('音声接続で問題が発生しました。', true);
    };
  }

  async function capture(action) {
    if (!$('consent').checked) throw new Error('参加者全員の同意を確認してください');
    if (!navigator.mediaDevices?.getUserMedia) throw new Error('このブラウザではマイクを利用できません');
    media = await navigator.mediaDevices.getUserMedia({ audio: {
      channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true,
    } });
    try {
      await refresh();
      const result = action === 'reconnect'
        ? { generation: meeting.generation }
        : await mutate(`/api/service/sessions/${encodeURIComponent(sessionId)}/capture`, {
          action, operation_key: crypto.randomUUID(), expected_version: meeting.version,
        });
      nextSequence = 0; sentSamples = 0; sampleQueue = [];
      if (action !== 'reconnect') meeting = { ...meeting, capture_state: result.state,
        generation: result.generation, version: result.version };
      await openAudio(result.generation);
      status('Providerへの音声接続を確認しています。');
    } catch (error) { stopMic(); throw error; }
  }

  async function stopCapture(end) {
    if (socket && socket.readyState !== WebSocket.OPEN) throw new Error('音声接続を確認できません');
    stopMic();
    if (socket) flushAudio();
    await refresh();
    const base = `/api/service/sessions/${encodeURIComponent(sessionId)}`;
    try {
      if (end) {
        await mutate(`${base}/end`, { operation_key: crypto.randomUUID(), expected_version: meeting.version });
      } else {
        await mutate(`${base}/capture`, {
          action: 'pause', operation_key: crypto.randomUUID(), expected_version: meeting.version,
        });
      }
    } catch (error) {
      socket?.close();
      throw new Error(`${error.message}。音声接続を閉じました。欠落の可能性があります`);
    }
    if (socket) socket.send(JSON.stringify({ type: 'capture_stop', last_sequence: nextSequence - 1 }));
    else await refresh();
    status(end ? '終了処理中です。' : '休憩処理中です。');
  }

  async function action(operation) {
    if (busy) return;
    busy = true; controls();
    try { await operation(); }
    catch (error) { status(`操作できません: ${error.message}`, true); await refresh(); }
    finally { busy = false; controls(); }
  }

  async function initialize() {
    try {
      const auth = await request('/api/service/auth/session');
      csrf = auth.csrf_token;
      $('auth-off').hidden = true; $('auth-on').hidden = false;
      status('ログイン済み。Pilotデモの保存条件を確認してから開始してください。');
      if (sessionId) await refresh();
    } catch (_) {
      csrf = null; $('auth-off').hidden = false; $('auth-on').hidden = true;
      status('ログインしてください。');
    }
    controls();
    setInterval(() => { if (csrf && sessionId) void refresh(); }, 2500);
  }

  $('consent').addEventListener('change', controls);
  $('create').addEventListener('click', () => action(async () => {
    if (sessionId && meeting && !['ended', 'ended_incomplete'].includes(meeting.state)) {
      throw new Error('先に現在の会議を終了してください');
    }
    const created = await mutate('/api/service/sessions', {
      title: $('title').value.trim() || null, goal: $('goal').value.trim() || null,
    });
    sessionId = created.session_id; sessionStorage.setItem(STORAGE_KEY, sessionId);
    await refresh(); status('会議を作成しました。全員の同意を確認して音声を開始してください。');
  }));
  $('start').addEventListener('click', () => action(() => capture('start')));
  $('resume').addEventListener('click', () => action(() => capture(
    meeting?.capture_state === 'reconnecting' || meeting?.capture_state === 'resuming' ? 'reconnect' : 'resume')));
  $('pause').addEventListener('click', () => action(() => stopCapture(false)));
  $('end').addEventListener('click', () => action(() => stopCapture(true)));
  $('logout').addEventListener('click', () => action(async () => {
    if (socket) throw new Error('音声を停止してからログアウトしてください');
    await mutate('/api/service/auth/logout', {}, 'POST');
    sessionStorage.removeItem(STORAGE_KEY); location.assign('/service-demo');
  }));
  void initialize();
})();
