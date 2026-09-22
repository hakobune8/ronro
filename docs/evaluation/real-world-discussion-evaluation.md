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

## Source acquisition and reproducible-ingestion policy

Real-world evaluation sources are selected using all of the following
criteria:

1. authoritative publisher and publicly accessible source;
2. discussion-like content with a fixed, continuous segment;
3. an evaluation use that does not require redistributing the source;
4. reproducible ingestion by an officially permitted route.

Reproducible ingestion is a first-class criterion. A source can remain a
valid research candidate while being unsuitable for unattended automation if
its only permitted route is an interactive player. RONRO must not use
`yt-dlp`, `youtube-dl`, media URL extraction, undocumented endpoints, ad
bypass, or other platform-restriction workarounds. No source media is added
to the repository.

### Official route review

The following review covers the currently selected T1, T2, and T3 sources.
The statements about missing direct media are limited to the official pages
and linked official materials reviewed for this evaluation; they are not a
claim about every asset that a publisher may expose elsewhere.

| Test | Officially exposed material | Direct official media / transcript found | Recommended route | Decision |
|---|---|---|---|---|
| T1 — 中国圏広域地方計画シンポジウム | Official event page, 100-minute panel archive player, and event flyer | No direct MP4/audio or official transcript/minutes link identified on the reviewed page | Human-controlled official Player playback with the fixed `01:24:00–01:39:00` segment | **C — Human-controlled Official Playback required** |
| T2 — インフラメンテナンス九州フォーラム2025, 第3部 | Official event page, official panel YouTube video, panel materials, and event-result PDF | No direct MP4/audio or official transcript/minutes link identified in the reviewed page/materials | Human-controlled official Player playback if T2 is later run | **C — Human-controlled Official Playback required** |
| T3 — 令和6年度 国総研講演会, Part III panel | Official event page, official panel YouTube video, panel slides, and official Q&A material | No direct MP4/audio or transcript/minutes link identified in the reviewed page/materials | Human-controlled official Player playback if T3 is later run | **C — Human-controlled Official Playback required** |

The T1 page identifies the event and its panel-discussion archive video on the
official YouTube route ([T1 official page](https://www.cgr.mlit.go.jp/kikaku/kokudo_keisei/r6sakutei/symposium/index.html)).
The T2 page links the selected panel to its official video and provides
official materials and a result record ([T2 official page](https://www.qsr.mlit.go.jp/useful/n-shiryo/kikaku/infrastructure_maintenance_r7.html),
[T2 event result PDF](https://www.qsr.mlit.go.jp/site_files/file/s_top/kikaku/infrastructure_maintenance/r7forum_kekka.pdf)).
The T3 page links the target panel video and supporting presentation material
([T3 official page](https://www.nilim.go.jp/lab/bbg/koen2024-1.html),
[T3 panel video](https://youtu.be/Y5dHlc8WgL8),
[T3 panel slides](https://www.nilim.go.jp/lab/bbg/kouenkai/kouenkai2024/koen2024/pdf/4_3bu-panel_discussion.pdf)).

The reviewed panel-video links are:

- T2 Part 3: https://www.youtube.com/watch?v=X6zfzHltRWA
- T3 Part III panel: https://youtu.be/Y5dHlc8WgL8

No independently stable alternate player was verified for T1. The automated
watch-page run showed a media-element lifecycle reset after playback had
progressed, so it cannot be treated as a reproducible unattended source
route. This does not invalidate the official source or the product pipeline;
it means that source playback must be controlled by a person for this
evaluation. Normal player UI, including any ordinary player/interstitial
handling, may be handled manually. Restrictions must not be bypassed.

## T1-H human-controlled official playback procedure

T1-H is the canonical execution route for T1 while no stable direct official
media route is available. Source playback is the only manual part; the RONRO
timer, snapshots, metrics, safety checks, drain, and report remain automated.

1. Open the [official T1 page](https://www.cgr.mlit.go.jp/kikaku/kokudo_keisei/r6sakutei/symposium/index.html)
   and its official video player.
2. Handle ordinary player UI or any normal pre-roll/interstitial manually;
   do not bypass ads, extract a stream URL, or download media.
3. Create a fresh RONRO session outside the fixed interval and run a short
   30–90 second provenance check.
4. Before audio starts, confirm Evidence, utterances, queue, and graph state
   are empty.
5. Confirm the approved loopback route and the browser track, then verify
   Play → non-silent signal, Pause → silence, and Resume → non-silent signal.
6. Require three consecutive Finals that semantically match the currently
   heard source speech. Also verify that Pause stops new meaningful Finals
   after any buffered completion and Resume restores source-corresponding
   Finals. If this fails, stop and do not consume the fixed segment.
7. Create a second fresh T1 session, seek to exactly `01:24:00`, and confirm
   the player remains stable near `5040` seconds.
8. Start RONRO capture and its evaluation timer, then start the official
   player. Record any start synchronization delta.
9. Play continuously through `01:39:00` without pause, seek, skip, or restart.
   RONRO automatically captures the 5-, 10-, and 15-minute snapshots and
   private screenshots/metrics when available.
10. Stop RONRO intake at the fixed end, complete STT/queue/analyzer drain,
    and review the final state and the three scheduled snapshots.

If the player resets, reloads, stops, or leaves the selected interval, mark
the run invalid as an evaluation-player lifecycle failure. Preserve its
metadata as a failed run and do not reinterpret it as a product result.

## T2/T3 route status

T2 and T3 remain metadata-only preparation items. Their official PDFs, slides,
Q&A, and event-result materials can support provenance and human review, but
they do not replace the preferred audio evaluation. Neither T2 nor T3 has
been executed. If their official pages continue to expose only player-based
video, both require the same human-controlled playback route; no timecode is
invented here.

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

Current source-route decisions:

- T1: **C — Human-controlled Official Playback required**.
- T2: **C — Human-controlled Official Playback required if executed**.
- T3: **C — Human-controlled Official Playback required if executed**.

The fixed T1 interval and source have not been replaced. This document update
only resolves the execution-route recommendation; it does not run T1, T2, or
T3.
