import fs from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { chromium } from 'playwright';

const SOURCE = Object.freeze({
  test_id: 'T1-A-AUTO',
  parent_test_id: 'T1-A',
  title: '中国圏広域地方計画シンポジウム',
  publisher: '国土交通省 中国地方整備局',
  official_page: 'https://www.cgr.mlit.go.jp/kikaku/kokudo_keisei/r6sakutei/symposium/index.html',
  video_url: 'https://www.youtube.com/watch?v=2fd1F2W8k60',
  start_time: '01:24:00',
  end_time: '01:39:00',
  start_seconds: 5040,
  duration_seconds: 900,
  input_method: 'official_playback_linux_virtual_loopback',
});

const mode = process.argv[process.argv.indexOf('--mode') + 1] || 'preflight';
const confirm15MinuteRun = process.argv.includes('--confirm-15-minute-run');
const baseUrl = process.env.RONRO_BASE_URL;
const outputPath = process.env.T1A_AUTO_OUTPUT || '/runner/runtime/t1a-auto-summary.json';
const sanityStartSeconds = Number(process.env.T1A_AUTO_SANITY_START_SECONDS || 4800);
const sanityDurationSeconds = Number(process.env.T1A_AUTO_SANITY_DURATION_SECONDS || 20);
const pauseDurationSeconds = Number(process.env.T1A_AUTO_PAUSE_SECONDS || 8);
const pollIntervalMs = Number(process.env.T1A_AUTO_POLL_INTERVAL_MS || 1000);
const expectedTrackSubstring = (process.env.T1A_AUTO_EXPECTED_TRACK_SUBSTRING || 'ronro_t1a').toLowerCase();
const prepareSourceBeforeSession = process.env.T1A_AUTO_PREPARE_SOURCE_BEFORE_SESSION === '1';
const preplaySourceBeforeSession = process.env.T1A_AUTO_PREPLAY_SOURCE_BEFORE_SESSION === '1';

if (!baseUrl) throw new Error('RONRO_BASE_URL is required');
if (!['preflight', 'sanity', 't1-a'].includes(mode)) {
  throw new Error(`Unsupported mode: ${mode}`);
}
if (mode === 't1-a' && !confirm15MinuteRun) {
  throw new Error('The 15-minute run requires --confirm-15-minute-run');
}

const origin = new URL(baseUrl).origin;
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function safeTrack(track) {
  if (!track) return null;
  return {
    label: track.label || null,
    selected_input_label: track.selected_input_label || null,
    expected_input_present: Boolean(track.expected_input_present),
    kind: track.kind || null,
    ready_state: track.readyState || null,
    muted: Boolean(track.muted),
    enabled: Boolean(track.enabled),
    sample_rate: track.settings?.sampleRate || null,
    channel_count: track.settings?.channelCount || null,
    device_id_present: Boolean(track.settings?.deviceId),
  };
}

function assertLoopbackTrack(track) {
  const label = [track?.label, track?.selected_input_label, track?.expected_input_label]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();
  const normalizedLabel = label.replace(/[^a-z0-9]+/g, '');
  const normalizedExpected = expectedTrackSubstring.replace(/[^a-z0-9]+/g, '');
  if (normalizedExpected && !normalizedLabel.includes(normalizedExpected) && !track?.expected_input_present) {
    throw new Error(`Browser microphone track does not match expected loopback '${expectedTrackSubstring}': ${track?.label || 'unknown'}`);
  }
}

function safeSnapshot(snapshot) {
  const live = snapshot?.live_state || {};
  const graph = snapshot?.state?.graph || {};
  const queue = live.queue || {};
  const metrics = live.metrics || {};
  return {
    runtime_state: live.runtime_state || null,
    websocket_state: live.websocket_state || null,
    stt_state: live.stt_state || null,
    audio_chunk_sequence: live.audio_chunk_sequence ?? null,
    final_utterance_count: live.final_utterance_count ?? metrics.final_utterance_count ?? 0,
    graph_revision: graph.revision ?? live.graph_revision ?? null,
    rendered_revision: live.rendered_revision ?? metrics.rendered_revision ?? null,
    queue: {
      pending: queue.pending ?? null,
      processing: queue.processing ?? null,
      failed: queue.failed ?? null,
    },
    audio_diagnostics: live.audio_diagnostics || null,
    transport_diagnostics: live.transport_diagnostics || null,
    drain: live.drain || metrics.drain || null,
  };
}

async function requestJson(request, requestPath, options = {}) {
  const response = await request.fetch(requestPath, { ...options, failOnStatusCode: false });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok()) {
    throw new Error(`${options.method || 'GET'} ${requestPath} failed: ${response.status()} ${JSON.stringify(payload)}`);
  }
  return payload;
}

async function readLive(request, controllerId) {
  return requestJson(request, `/api/live?controller_id=${encodeURIComponent(controllerId)}`);
}

async function waitForLive(request, controllerId, predicate, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  let last = null;
  while (Date.now() < deadline) {
    last = await readLive(request, controllerId);
    if (predicate(last)) return last;
    await sleep(pollIntervalMs);
  }
  throw new Error(`Timed out waiting for live state: ${JSON.stringify(safeSnapshot(last))}`);
}

async function installTrackProbe(context) {
  await context.addInitScript((expectedLabelSubstring) => {
    const media = navigator.mediaDevices;
    if (!media || window.__ronroT1AProbed) return;
    const original = media.getUserMedia.bind(media);
    media.getUserMedia = async (constraints) => {
      let requestedConstraints = constraints;
      let beforeDevices = [];
      if (constraints?.audio && typeof constraints.audio === 'object' && !constraints.audio.deviceId) {
        const expected = String(expectedLabelSubstring || '').toLowerCase();
        beforeDevices = await media.enumerateDevices();
        const loopback = beforeDevices.find((device) => device.kind === 'audioinput'
          && String(device.label || '').toLowerCase().includes(expected)
          && device.deviceId);
        if (loopback) {
          requestedConstraints = {
            ...constraints,
            audio: { ...constraints.audio, deviceId: { exact: loopback.deviceId } },
          };
        }
      }
      const stream = await original(requestedConstraints);
      const track = stream.getAudioTracks()[0];
      const settings = track?.getSettings?.() || {};
      const afterDevices = await media.enumerateDevices();
      const selected = afterDevices.find((device) => device.kind === 'audioinput'
        && device.deviceId === settings.deviceId);
      const expectedDevice = afterDevices.find((device) => device.kind === 'audioinput'
        && String(device.label || '').toLowerCase().includes(String(expectedLabelSubstring || '').toLowerCase()));
      window.__ronroT1AAudioTrack = {
        label: track?.label || null,
        selected_input_label: selected?.label || null,
        expected_input_label: expectedDevice?.label || null,
        expected_input_present: Boolean(expectedDevice),
        kind: track?.kind || null,
        readyState: track?.readyState || null,
        muted: Boolean(track?.muted),
        enabled: Boolean(track?.enabled),
        settings: {
          sampleRate: settings.sampleRate || null,
          channelCount: settings.channelCount || null,
          deviceId: settings.deviceId || null,
        },
      };
      return stream;
    };
    window.__ronroT1AProbed = true;
  }, expectedTrackSubstring);
}

async function sourceVideo(page) {
  const video = page.locator('video').first();
  await video.waitFor({ state: 'attached', timeout: 30000 });
  await page.waitForTimeout(3000);
  await video.evaluate((element) => {
    if (element.readyState >= 2) return;
    return new Promise((resolve) => element.addEventListener('canplay', resolve, { once: true }));
  });
  return video;
}

async function seekAndPlay(video, seconds) {
  let lastError = null;
  for (let attempt = 0; attempt < 6; attempt += 1) {
    try {
      const state = await video.evaluate(async (element, position) => {
        element.currentTime = position;
        const deadline = Date.now() + 10000;
        while (Math.abs(element.currentTime - position) > 3 && Date.now() < deadline) {
          await new Promise((resolve) => window.setTimeout(resolve, 250));
        }
        if (Math.abs(element.currentTime - position) > 3) {
          throw new Error(`Official player did not seek to ${position}s (at ${element.currentTime}s)`);
        }
        if (element.paused) {
          await Promise.race([
            element.play(),
            new Promise((_, reject) => window.setTimeout(
              () => reject(new Error('Official player play() timed out')),
              5000,
            )),
          ]);
        }
        return { paused: element.paused, current_time: element.currentTime };
      }, seconds);
      await sleep(1500);
      return state;
    } catch (error) {
      lastError = error;
      await sleep(2000);
    }
  }
  throw lastError || new Error(`Could not start official playback at ${seconds}s`);
}

async function pauseVideo(video) {
  await video.evaluate((element) => element.pause());
  return video.evaluate((element) => ({ paused: element.paused, current_time: element.currentTime }));
}

async function startController(page, request) {
  const controllerId = await page.evaluate(() => {
    let value = window.localStorage.getItem('ronro.controller.instance');
    if (!value) {
      value = window.crypto?.randomUUID?.() || `t1a-auto-${Date.now()}`;
      window.localStorage.setItem('ronro.controller.instance', value);
    }
    return value;
  });
  const before = await readLive(request, controllerId);
  const beforeLive = before?.live_state || {};
  const restartableStates = new Set(['ended', 'ended_with_incomplete_processing', 'failed', 'disconnected']);
  if (beforeLive.controller?.status === 'owned_by_other' && !restartableStates.has(beforeLive.runtime_state)) {
    throw new Error('Cannot start automated evaluation: another controller owns the active session');
  }
  if (beforeLive.runtime_state !== 'idle' && !restartableStates.has(beforeLive.runtime_state)) {
    throw new Error(`Cannot start automated evaluation from live state: ${beforeLive.runtime_state || 'unknown'}`);
  }
  if (restartableStates.has(beforeLive.runtime_state)
      && beforeLive.controller?.status === 'owned_by_other') {
    // A completed session keeps its historical controller marker for display,
    // while the backend intentionally permits the next session to claim a new
    // controller. Claim that next session through the normal API, then reload
    // the existing controller page so its read-only snapshot is current.
    await requestJson(request, '/api/live/start', {
      method: 'POST',
      data: { mode: 'continuous', controller_id: controllerId },
    });
    await page.reload({ waitUntil: 'domcontentloaded', timeout: 30000 });
  }
  const startButton = page.locator('#start-button');
  const restartable = restartableStates.has(beforeLive.runtime_state);
  if (restartable) {
    // The existing controller intentionally keeps the final view visible after
    // an ended session and hides Start. Re-expose only that existing control in
    // the isolated evaluation page so its normal click handler can create the
    // next session; no product UI or API semantics are changed.
    await startButton.evaluate((element) => {
      element.hidden = false;
      element.disabled = false;
    });
  }
  if (restartable) {
    // The page refresh loop may immediately re-render the ended/starting
    // state and hide the button again. Dispatch the same DOM click event
    // without changing the product handler or API contract.
    await startButton.dispatchEvent('click');
  } else {
    await startButton.click();
  }
  const trackHandle = await page.waitForFunction(
    () => window.__ronroT1AAudioTrack || null,
    null,
    { timeout: 30000 },
  );
  const rawTrack = await trackHandle.jsonValue();
  const active = await waitForLive(
    request,
    controllerId,
    (snapshot) => snapshot?.live_state?.runtime_state === 'active'
      && snapshot?.live_state?.websocket_state === 'connected',
  );
  return { controllerId, before: safeSnapshot(before), track: safeTrack(rawTrack), active: safeSnapshot(active) };
}

async function startEvaluation(request, id) {
  return requestJson(request, '/api/live/evaluation/start', {
    method: 'POST',
    data: {
      evaluation_session_id: id,
      participant_count: 2,
      discussion_theme: '自然な公開パネルディスカッション',
      raw_audio_consent: false,
    },
  });
}

async function addEvaluationSnapshot(request, minute) {
  return requestJson(request, '/api/live/evaluation/snapshot', {
    method: 'POST',
    data: { minute },
  });
}

async function stopController(page, request, controllerId) {
  page.once('dialog', (dialog) => dialog.accept());
  await page.locator('#end-button').click();
  return waitForLive(
    request,
    controllerId,
    (snapshot) => ['ended', 'ended_with_incomplete_processing', 'failed']
      .includes(snapshot?.live_state?.runtime_state),
    120000,
  );
}

async function finishEvaluation(request) {
  return requestJson(request, '/api/live/evaluation/end', { method: 'POST' });
}

async function main() {
  const evaluationId = `t1a-auto-${Date.now()}`;
  const startedAt = new Date().toISOString();
  const browser = await chromium.launch({
    headless: false,
    args: [
      '--autoplay-policy=no-user-gesture-required',
      '--disable-dev-shm-usage',
      ...(origin.startsWith('http://')
        ? [`--unsafely-treat-insecure-origin-as-secure=${origin}`]
        : []),
      // Evaluation-only unattended browser: bypass the permission prompt;
      // capture still comes from the real PulseAudio loopback input.
      '--use-fake-ui-for-media-stream',
    ],
  });
  const context = await browser.newContext({ baseURL: origin });
  // This evaluation-only browser is intentionally unattended. Grant microphone
  // permission for the RONRO origin only; the audio source remains the real
  // PulseAudio loopback monitor and no synthetic media is enabled.
  await context.grantPermissions(['microphone'], { origin });
  await installTrackProbe(context);
  const request = context.request;
  const controller = await context.newPage();
  const sourcePage = await context.newPage();
  let controllerId = null;
  let liveStopped = false;
  let evaluationFinished = false;
  const result = {
    test_id: SOURCE.test_id,
    parent_test_id: SOURCE.parent_test_id,
    mode,
    state: 'waiting_for_browser_gate',
    source: SOURCE,
    started_at: startedAt,
    input: {
      sink: process.env.RONRO_AUDIO_SINK || 'ronro_t1a_loopback',
      source: process.env.RONRO_AUDIO_SOURCE || `${process.env.RONRO_AUDIO_SINK || 'ronro_t1a_loopback'}.monitor`,
      raw_audio_persisted: false,
      complete_transcript_persisted: false,
    },
    browser: { track: null, source_playback: null },
    snapshots: [],
    observations: [],
    semantic_match_review: 'human_review_required',
    failures: [],
  };

  try {
    const sourceStart = mode === 't1-a' ? SOURCE.start_seconds : sanityStartSeconds;
    await controller.goto(`${origin}/session`, { waitUntil: 'domcontentloaded', timeout: 30000 });
    // The normal product UI keeps the ended session's final view visible and
    // hides Start. startController() re-exposes that existing control only in
    // this isolated evaluation context before using its normal click handler.
    await controller.locator('#start-button').waitFor({ state: 'attached', timeout: 30000 });
    const sourceUrl = new URL(SOURCE.video_url);
    sourceUrl.searchParams.set('t', `${sourceStart}s`);
    await sourcePage.goto(sourceUrl.toString(), { waitUntil: 'domcontentloaded', timeout: 60000 });
    const video = await sourceVideo(sourcePage);
    let preparedSource = null;
    if ((prepareSourceBeforeSession || preplaySourceBeforeSession) && mode !== 'preflight') {
      // Evaluation-only preparation: resolve a slow/unstable player seek while
      // no RONRO session is active. The normal preparation pauses at the fixed
      // position; preplay mode leaves the official source running so provider
      // startup cannot spend the candidate's 30-second bound on idle loopback.
      await seekAndPlay(video, sourceStart);
      preparedSource = preplaySourceBeforeSession
        ? await video.evaluate((element) => ({ paused: element.paused, current_time: element.currentTime }))
        : await pauseVideo(video);
      result.browser.source_prepared = preparedSource;
    }
    await startEvaluation(request, evaluationId);

    const initial = await controller.evaluate(() => ({ ready: Boolean(navigator.mediaDevices?.getUserMedia) }));
    if (!initial.ready) throw new Error('getUserMedia is unavailable in the evaluation browser');

  const started = await startController(controller, request);
  assertLoopbackTrack(started.track);
  controllerId = started.controllerId;
    result.browser.track = started.track;
    result.observations.push({ phase: 'controller_before_start', snapshot: started.before });
    result.observations.push({ phase: 'controller_active', snapshot: started.active });
    result.state = 'ready_for_source_playback';

    if (mode === 'preflight') {
      result.note = 'Browser and loopback preflight completed; source playback was not started.';
      return result;
    }

    const sourceDuration = mode === 't1-a' ? SOURCE.duration_seconds : sanityDurationSeconds;
    result.state = 'running';
    result.browser.source_playback = preplaySourceBeforeSession
      ? await video.evaluate((element) => ({ paused: element.paused, current_time: element.currentTime }))
      : preparedSource
      ? await video.evaluate(async (element) => {
        if (element.paused) await element.play();
        return { paused: element.paused, current_time: element.currentTime };
      })
      : await seekAndPlay(video, sourceStart);
    const runStarted = Date.now();
    result.source_playback_started_at = new Date().toISOString();

    if (mode === 'sanity') {
      await sleep(sourceDuration * 1000);
      const during = await readLive(request, controllerId);
      result.observations.push({ phase: 'source_playback', snapshot: safeSnapshot(during) });
      const paused = await pauseVideo(video);
      result.browser.source_pause = paused;
      const pauseBefore = during?.live_state?.final_utterance_count || 0;
      await sleep(pauseDurationSeconds * 1000);
      const pauseAfterSnapshot = await readLive(request, controllerId);
      result.observations.push({ phase: 'source_paused', snapshot: safeSnapshot(pauseAfterSnapshot) });
      result.pause_final_delta = (pauseAfterSnapshot?.live_state?.final_utterance_count || 0) - pauseBefore;
      result.browser.source_resume = await seekAndPlay(video, paused.current_time);
      await sleep(sourceDuration * 1000);
      const resumed = await readLive(request, controllerId);
      result.observations.push({ phase: 'source_resumed', snapshot: safeSnapshot(resumed) });
    } else {
      for (const minute of [5, 10, 15]) {
        const target = minute * 60 * 1000;
        const elapsed = Date.now() - runStarted;
        await sleep(Math.max(0, target - elapsed));
        const snapshot = await readLive(request, controllerId);
        await addEvaluationSnapshot(request, minute);
        result.snapshots.push({ minute, observation: safeSnapshot(snapshot) });
      }
    }

    result.state = 'draining';
    const ended = await stopController(controller, request, controllerId);
    liveStopped = true;
    result.observations.push({ phase: 'ended', snapshot: safeSnapshot(ended) });
    result.evaluation = await finishEvaluation(request);
    evaluationFinished = true;
    result.state = 'completed';
    return result;
  } catch (error) {
    result.state = 'failed';
    result.failures.push(String(error?.stack || error));
    throw error;
  } finally {
    if (controllerId && !liveStopped) {
      await requestJson(request, '/api/live/stop', {
        method: 'POST',
        data: { controller_id: controllerId },
      }).catch(() => {});
    }
    if (!evaluationFinished) await finishEvaluation(request).catch(() => {});
    await fs.mkdir(path.dirname(outputPath), { recursive: true }).catch(() => {});
    await fs.writeFile(outputPath, `${JSON.stringify(result, null, 2)}\n`, 'utf8').catch(() => {});
    await context.close().catch(() => {});
    await browser.close().catch(() => {});
  }
}

main().then((result) => {
  console.log(JSON.stringify({
    test_id: result.test_id,
    mode: result.mode,
    state: result.state,
    track: result.browser.track,
    snapshots: result.snapshots.map((item) => item.minute),
    semantic_match_review: result.semantic_match_review,
    output: outputPath,
  }, null, 2));
}).catch((error) => {
  console.error(error?.stack || error);
  process.exitCode = 1;
});
