# Real-world Discussion Evaluation

This document records the public-safe evaluation boundary for RONRO's
real-world discussion tests. Source video, source audio, complete transcripts,
and detailed runtime artifacts are never committed here.

## T1-A source

| Field | Value |
|---|---|
| Test | T1-A |
| Title | 中国圏広域地方計画シンポジウム |
| Publisher | 国土交通省 中国地方整備局 |
| Official page | https://www.cgr.mlit.go.jp/kikaku/kokudo_keisei/r6sakutei/symposium/index.html |
| Official video | https://www.youtube.com/watch?v=2fd1F2W8k60 |
| Selected segment | 01:24:00–01:39:00, continuous 15 minutes |
| Input policy | Official Player playback only; no download or extraction |

The fixed segment is intentionally not edited or assembled from multiple
locations. Playback and source-content review are separate from the product
runtime acceptance gate.

## Product finalization candidate

The continuous-audio spike used synthetic or human-owned audio and did not
change the Analyzer, Graph, canonical event contract, or Projection.

| Condition | Input | Finals | Boundary observation | Drain |
|---|---:|---:|---|---|
| A — natural meeting-like | 117.5 s | 8 | 8 Server VAD boundaries; max unfinalized 17.1 s | ended |
| B — long continuous turn | 117.2 s | 4 | 3 bounded fallbacks; 1 session-end flush; max unfinalized 31.5 s | ended |

Safety counters for both conditions were zero for automatic confirmation,
invented owner, invented due date, evidence loss, graph corruption, Analyzer
failure, and queue failure. The focused and full test suite was green at 168
tests.

The candidate Pilot configuration is:

- normal finalization: Provider `server_vad`
- safety bound: `server_vad_bounded`
- maximum unfinalized duration: 30 seconds
- generic code default: `none` for compatibility outside the Pilot overlay

The bounded fallback is not an unconditional periodic commit. It is used only
when meaningful audio remains unfinalized. Long turns can exceed the normal
latency target; the validation reference was p50 9.063 seconds and p95 13.838
seconds. Pilot runtime metadata should record VAD, fallback, session-end
boundary counts, and maximum unfinalized duration.

## T1 audio provenance gate

The official-playback path is a separate evaluation-environment gate:

```text
Official Player → evaluation loopback → browser capture
→ RONRO Live Audio Pipeline
```

The automated loopback run proved that the browser and WebSocket could remain
active, but it did not establish that the captured signal corresponded to the
official source content. The source-provenance gate therefore remains blocked
until player progression, loopback energy correlation, and at least three
consecutive source-matching Finals are observed. This is not evidence against
the validated `server_vad_bounded` product candidate.

The evaluation runner under `evaluation/real-world/t1a-auto/` is optional,
evaluation-only tooling. It must not be copied into the product image. Its
runtime output is ignored and must remain private.

## Latest provenance gate result

The candidate was not advanced to the fixed 15-minute T1-A interval. A short
official-player diagnostic confirmed the loopback signal path: the browser
track was `RONRO_T1A_Input`, playback produced non-silent monitor energy,
Pause reduced the energy to silence, and Resume restored it. However, the
YouTube watch-page video element later reset from the selected position to
`currentTime=0` with `readyState=0` and no main-frame navigation. The short
run therefore did not establish three consecutive source-matching Finals.

This is classified as an **evaluation player lifecycle failure**, not as a
failure of the validated `server_vad_bounded` product configuration. The
fixed `01:24:00–01:39:00` run remains pending. No source audio, video, full
transcript, or long verbatim excerpt was persisted or committed.

## Public artifact policy

Public-safe artifacts are limited to source metadata, configuration policy,
aggregate graph statistics, latency metrics, safety counters, and short human
review notes. Keep screenshots, provider identifiers, detailed diagnostics,
audio, video, and complete transcript-derived artifacts in private runtime
storage.

T1-A has not been re-run as a 15-minute evaluation in this candidate step.
T2 and T3 are not executed here.
