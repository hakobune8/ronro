# T1-A-AUTO: Official Playback via Linux Audio Loopback

This directory contains an evaluation-only runner for RONRO's fixed T1-A
source. It uses the official YouTube player in Chromium and routes the player
output through a Linux PulseAudio loopback monitor into the existing RONRO
`/session` microphone path.

```text
Official YouTube player
        ↓
Linux PulseAudio null sink / monitor
        ↓
Chromium getUserMedia
        ↓
RONRO AudioWorklet → PCM16LE / 24 kHz → WSS /live
        ↓
Realtime STT → Analyzer → Graph → Shared View
```

## Scope and safety

`T1-A-AUTO` is a separate evaluation path. It is not the Mac/BlackHole
manual Browser Gate for `T1-A`, and it is not the iPhone Safari acceptance
test. Its result must be reported separately from those gates.

- The source is played by the official YouTube player; no download, media URL
  extraction, audio extraction, or platform restriction bypass is used.
- The runner does not persist source video, raw audio, complete transcripts, or
  long verbatim excerpts. The output is metadata, counts, diagnostics, and
  snapshot-safe graph statistics.
- Semantic correspondence between source speech and Final STT remains a
  human review item. The runner collects evidence but does not claim semantic
  accuracy automatically.
- `--mode t1-a` requires the explicit `--confirm-15-minute-run` flag. The
  runner does not automatically claim semantic accuracy for the result.
- The runner is evaluation tooling. It must not be added to the RONRO
  production container.
- The image applies an evaluation-only Chrome policy that allows audio capture
  only for `https://ronro.hakobune8.com/*` and denies it for other origins.
  The runner also uses an origin-scoped Playwright microphone grant and
  `--use-fake-ui-for-media-stream` so the unattended evaluation can pass the
  browser permission boundary. It does not use
  `--use-fake-device-for-media-stream`, synthetic audio, or direct PCM
  injection. The policy file is `chrome-policies/ronro-t1a-auto.json` and
  must not be copied to a general browser or product image.
- Chromium runs headed under Xvfb because Chromium's headless shell may mute
  player audio. Xvfb only supplies the unattended display surface; the source
  audio still comes from the official player through a real PulseAudio null
  sink and remapped input source.

## Build

From the repository root:

```sh
docker build -t ronro-t1a-auto-eval:local evaluation/real-world/t1a-auto
```

The image uses the matching Playwright browser image and npm package version.
The Playwright image supplies the browser and system dependencies; the
Playwright package is installed separately by this image's `Dockerfile`.
See the [Playwright Docker documentation](https://playwright.dev/docs/next/docker)
for the upstream image and version-matching guidance.

## Runtime configuration

Set `RONRO_BASE_URL` to the already deployed private RONRO origin. Mount the
ignored runtime directory if the JSON summary is needed outside the container:

```sh
docker run --rm \
  -e RONRO_BASE_URL=https://<private-ronro-host> \
  -v "$PWD/evaluation/real-world/t1a-auto/runtime:/runner/runtime" \
  ronro-t1a-auto-eval:local \
  --mode preflight
```

The container creates a PulseAudio null sink named `ronro_t1a_loopback` and a
remapped input source named `ronro_t1a_input`. The browser track label and
basic track settings are recorded without persisting the raw device
identifier. In the completed run the track was `RONRO_T1A_Input`, live,
unmuted, mono, and 48 kHz.

## Modes

### Preflight

```sh
docker run --rm \
  -e RONRO_BASE_URL=https://<private-ronro-host> \
  -v "$PWD/evaluation/real-world/t1a-auto/runtime:/runner/runtime" \
  ronro-t1a-auto-eval:local --mode preflight
```

Preflight opens `/session`, checks `getUserMedia`, starts a fresh evaluation
and controller session, and verifies the loopback track, AudioWorklet/WSS
path, and active state. It does not start source playback.

### Short sanity run

```sh
docker run --rm \
  -e RONRO_BASE_URL=https://<private-ronro-host> \
  -v "$PWD/evaluation/real-world/t1a-auto/runtime:/runner/runtime" \
  ronro-t1a-auto-eval:local --mode sanity
```

Sanity uses a short, non-evaluation portion of the fixed official video,
observes playback, pause, and resume, and writes a safe summary. A human must
confirm that at least three consecutive Finals correspond to the source and
that no demo or stale content appears before the Browser/loopback gate is
considered passed.

### Fixed T1-A-AUTO run

The fixed continuous segment is `01:24:00–01:39:00` (900 seconds). It is not
started by the normal commands above. The explicit
`--confirm-15-minute-run` flag is required to start it:

```sh
docker run --rm \
  -e RONRO_BASE_URL=https://<private-ronro-host> \
  -v "$PWD/evaluation/real-world/t1a-auto/runtime:/runner/runtime" \
  ronro-t1a-auto-eval:local \
  --mode t1-a --confirm-15-minute-run
```

Snapshots are requested at 5, 10, and 15 minutes. The runner stops the RONRO
session and waits for drain before completing. Review the generated summary
as a private runtime artifact; do not commit it automatically. Semantic
correspondence between a Final and source speech remains a separate quality
gate.

## Output

The default output is:

```text
evaluation/real-world/t1a-auto/runtime/t1a-auto-summary.json
```

The path is ignored by the repository. Source media and complete transcripts
are intentionally absent from the output. T2, T3, the iPhone Pilot, and the
Mac/BlackHole manual gate are outside this runner's scope.

## Latest automated run

The fixed T1-A-AUTO run was completed unattended using the official player,
Linux PulseAudio loopback, Chromium under Xvfb, the existing `/session` UI,
and the deployed RONRO Live Pipeline. The run was operationally complete:
the audio track was live, the WebSocket stayed connected, the 5/10/15-minute
snapshots were collected, and session drain completed with no failed queue
items.

It did not pass the T1 quality gate. Only one Final was produced during the
15-minute run, with no detected topic, node, relation, action, open item, or
decision candidate. Source correspondence therefore remains unverified and
the result is not evidence that the official discussion formed a useful
論点図. The run is recorded as `C. T1 QUALITY ISSUE — Analyze before T2`.
