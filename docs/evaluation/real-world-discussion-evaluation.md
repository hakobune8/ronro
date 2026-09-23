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

### Human-controlled retry — invalid provenance run

The next human-controlled attempt also did not pass the provenance gate. The
official page was at the intended discussion video and the player was visibly
progressing around the non-evaluation interval near `01:24:00`. An ordinary
in-player advertisement/interruption was observed during the attempt. This is
recorded as a source-playback event, not as a bypass target.

The browser capture produced multiple Finals, but their content included
unrelated sports material rather than a consecutive match to the speech then
visible in the official player. After the player was paused, additional
meaningful Finals continued beyond the short buffered-completion window. The
run therefore demonstrated neither source provenance nor the required
Pause → no new Finals behavior. It was ended and drained successfully, but it
is an invalid evaluation run and must not be counted as T1 evidence.

This narrows the remaining issue to the evaluation input route: the player
being visible and the loopback device being present do not prove that the
captured stream is exclusively the current official-player audio. The
advertisement may have contributed to the mismatch, but it is not established
as the sole cause. The fixed `01:24:00–01:39:00` evaluation must not start
until a fresh non-evaluation provenance check obtains three consecutive
source-matching Finals and passes the pause/resume gate.

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

## YouTube Audio Recognition Diagnostic — measured capture divergence

### Scope and baseline

This diagnostic compared macOS `say` with official-player playback outside
the fixed T1 interval. It did not run the 15-minute evaluation or change
product code, capture constraints, STT context, VAD, gain, or channel policy.
The deployed Control HTML matched the inspected candidate HTML byte for byte.
The runtime retained `gpt-transcribe`, the generic Japanese meeting prompt,
keywords `["論路"]`, `server_vad_bounded`, and a 30-second fallback.

The Mac route uses **CoreAudio**, the existing stereo multi-output device,
and BlackHole 2ch at 48 kHz. PulseAudio belongs to the earlier Linux/Pod
runner and is not part of this controlled Mac comparison. Earlier runtime
summaries were read without alteration; their `completed` state and live
track metadata do not establish source-matching transcription.

### Measurement method

The same temporary aggregate observers measured the existing browser
`handleLivePcm` input and the output of `liveFloatToPcm16`. Both observers
passed samples through unchanged, retained only statistics, and were removed
after the test. The first point is **after browser capture processing and
the existing worklet downmix, but before resampling**; it is not raw device
audio. Native BlackHole L/R samples were separately consumed through an
in-memory pipe, reduced to aggregates, and discarded without audio files.

Browser windows lasted 40 seconds. Native capture overlapped these windows
but was not sample-synchronized: FFmpeg startup/buffering produced about
28.4–28.6 seconds of decoded samples in a 32.4-second command. Consequently,
native-to-browser RMS ratios indicate substantial attenuation, not an exact
sample-aligned transfer function. Browser sample accounting independently
establishes the live PCM duration.

### Controlled Chrome A/B and playback-browser crossover

All three conditions used the same Chrome capture path, actual BlackHole
track, 48 kHz input, one track, `channelCount=1`, `echoCancellation=true`,
`noiseSuppression=true`, and `autoGainControl=true`. Tracks were live,
enabled, and unmuted. Output was 24 kHz mono PCM16LE through the existing
Live Transport. Each condition had a separate runtime session.

| Measurement | A: macOS say | B: YouTube in Chrome | C: YouTube in Safari, capture in Chrome |
| --- | ---: | ---: | ---: |
| Native BlackHole mono RMS, normalized | 0.0673284 | 0.0201414 | 0.0199577 |
| Native L/R correlation (uncentered) | 1.000000 | 0.999974 | 0.999973 |
| Pre-resample RMS | 0.0682945 | 0.000421315 | 0.0643738 |
| Post-PCM RMS, normalized | 0.0683117 | 0.000421115 | 0.0643368 |
| Pre-resample sample count | 1,920,256 | 1,919,616 | 1,919,744 |
| Encoded sample count | 960,000 | 960,000 | 960,000 |
| Browser wall / PCM duration | 40.001 / 40 s | 40.002 / 40 s | 40.002 / 40 s |
| Encoded chunks | 400 | 400 | 400 |
| Mean / maximum chunk interval, ms | 100.009 / 110.7 | 100.050 / 112.3 | 100.043 / 110.9 |
| Post-PCM peak | 0.999939 | 0.0375366 | 0.849731 |
| Post-PCM DC offset | -0.00000367 | 0.000000493 | 0.00000695 |
| Post-PCM nonzero ratio | 0.669842 | 0.870855 | 0.986620 |
| Post-PCM clipping ratio | 0.00000208 | 0 | 0 |
| Whole-session Finals / Partials | 4 / 110 | 0 / 0 | 7 / 599 |
| Drain | ended | ended_with_incomplete_processing | ended |

Final/Partial counts cover the whole diagnostic sessions, including setup
and drain, **not just the 40-second signal windows**. A lasted about 93 s;
C lasted about 126 s. These are not latency/semantic quality benchmarks.
The first nonempty source condition was not selected for favorable content.
Normal advertisements and manual/automation preparation intervals are not
valid T1 provenance evidence. Source playback was stopped after diagnosis.

The earliest measured material divergence is between native BlackHole audio
and the browser's pre-resample worklet output. In B the signal was attenuated
by approximately 34 dB relative to the overlapping native measurement. In C,
moving **only source playback** to Safari recovered about 44 dB at the Chrome
worklet input, while native input level remained approximately 0.020. The
capture constraints, resampler, PCM encoder, transport, and provider settings
were unchanged. Chrome's source player was paused before the crossover and
separately verified paused afterward; there was no intended dual-player mix.

Native L/R and their arithmetic mean had effectively identical RMS. Stereo
phase cancellation is not supported by these measurements. The browser
resampler preserved each condition's already-present signal level; it did
not introduce the large attenuation. Byte order and mono encoding use the
same source-independent code in all conditions.

### Layer disposition

| Layer | A/B disposition | Evidence / limitation |
| --- | --- | --- |
| 1. Source/sink topology | SAME on Mac | CoreAudio → same stereo output → BlackHole; PulseAudio N/A |
| 2. MediaStream settings | SAME | Actual Chrome track/settings reported above |
| 3. Pre-resample signal | DIFFERENT | Large source-dependent attenuation already present here |
| 4. Channels/downmix | SAME native phase relationship and implementation; browser internals UNKNOWN | Native L/R nearly identical; worklet averages channels; per-channel browser-internal processing was not instrumented |
| 5. Post-resample PCM | DIFFERENT signal; SAME conversion | Attenuation persists, sample/time accounting preserved |
| 6. Chunk cadence/duration | SAME within scheduling tolerance | 400 × 2,400 samples = 40 s; approximately 100 ms cadence |
| 7. Provider append | UNKNOWN independent wire count | Code awaits append before acknowledging each chunk; no separate provider wire counter collected |
| 8. Provider speech started/stopped | UNKNOWN exact counts | A/C boundary metadata proves some speech-boundary activity, but the public snapshot does not expose full per-condition counts |
| 9. Transcription delta | DIFFERENT | Whole-session partial counts 110 versus 0; crossover 599 |
| 10. Transcription completed | DIFFERENT | Whole-session final counts 4 versus 0; crossover 7 |

Downstream tuning was stopped after locating and reproducing the upstream
signal difference. Speech-band spectra and separate internal browser DSP
stages were not measured and remain UNKNOWN, rather than inferred from
nonzero samples or a live track.

### Safari control correction

The earlier conversational assertion that Safari plus `say` had succeeded
was not established by the recorded Safari actions and did not reproduce in
this diagnostic. With Safari capture, both sources were strongly attenuated:
`say` native RMS 0.0107092 versus pre-resample 0.000002273;
YouTube native RMS 0.00793344 versus pre-resample 0.000027944.
Neither produced Finals. Safari reported BlackHole at 48 kHz with echo
cancellation enabled, but did not expose all Chrome track settings.
Therefore the strong reproducible successful comparison is **Chrome capture
with say**, followed by Chrome capture with Safari source playback.

### Root cause, limits, and minimal recommendation

Classification: **B — signal level/quality at browser capture processing**.
The demonstrated failure mechanism is suppression of same-browser playback
before RONRO resampling. Browser echo cancellation is the strongly supported
explanation: it is enabled, and removing the source from the capturing
browser restores the signal and recognition. The individual contributions
of echo cancellation, noise suppression, and AGC were not isolated by
toggling them, so no exact internal algorithm is claimed proven.

This interpretation is consistent with the
[Media Capture specification](https://www.w3.org/TR/mediacapture-streams/#dom-mediatrackconstraintset-echocancellation)
and Chrome's description of a playback reference used by its
[echo canceller](https://developer.chrome.com/blog/more-native-echo-cancellation).
There is no evidence here for YouTube recording protection as the cause.

Decision: **A — ROOT CAUSE IDENTIFIED — EVALUATION FIX**, at the demonstrated
route/processing level. The smallest proposed evaluation setup is official
playback in Safari with RONRO capture in Chrome, keeping the current product
settings. This crossover was a diagnostic control, not a product change or
a completed provenance acceptance test.

Ordinary iPhone microphone speech is not an intentional loopback of its own
browser output. This result does not by itself demonstrate a Pilot microphone
defect; iPhone acceptance remains necessary. Globally disabling microphone
echo cancellation is not recommended on the evidence from this loopback test.

### Incomplete drain and remaining T1 gate

The failing Chrome run ended with `input_audio_buffer_commit_empty`: the
provider reported 0 ms in its commit buffer. Locally, the pending PCM and
`meaningful_audio_buffer` flag existed. That flag only means at least one
PCM sample exceeded a small amplitude threshold; it does not establish
recognizable speech or a provider speech turn. Session-end therefore sent
an explicit commit, the provider returned an error, and the existing error
path marked processing incomplete. This is not an empty completed transcript
and must not be relabeled as a successful drain. Provider-internal buffer
behavior was not independently observed.

The implemented bounded-fallback guard also requires the provider's
`_vad_speech_active` flag in VAD modes. Thirty seconds of locally nonzero PCM
alone therefore does not force a commit. This explains why continuous chunk
acceptance and an increasing local duration do not establish provider speech
recognition; the exact speech-event counts for B remain unmeasured.

A and C ended normally; C had zero STT/analyzer/queue failures and graph/render
revision 14/14. No end-to-end speech completeness or semantic safety claim
is inferred solely from those counters.

**T1-H: NOT READY.** Seven crossover Finals show recognition recovery, but
three consecutive source-matching Finals, pause/resume behavior, and stable
advertisement-free source continuity were not jointly validated. A further
short provenance gate is required. No 15-minute run, T2/T3, release, or Pilot
was performed. Raw audio, source media, complete transcripts, device IDs,
and private runtime details were not added to this report. Product files
were unchanged; only temporary aggregate observers and this documentation
were used. No commit, push, or deployment was performed.

## T1-H final provenance gate — execution attempt (2026-09-23)

The requested route remains Safari official playback → BlackHole → Chrome
RONRO capture, with the candidate and audio-processing configuration frozen.
The native browser access check reported that the Mac was locked and could
not be unlocked automatically. Manual unlock is required before proceeding.

Status: **ENVIRONMENT BLOCKED — MAC LOCKED**. No fresh provenance session,
source playback, or T1 capture was started in this attempt. Provenance is
pending, not failed on audio quality. The 15-minute evaluation and its
snapshots, scores, safety measurements, and A/B/C/D outcome remain unmeasured.
Previous diagnostic results are preserved. After manual unlock, resume with
the non-T1 provenance interval; only a complete PASS authorizes the fresh
15-minute session. No product/configuration changes or release work occurred.

## T1-H final provenance gate — resumed after unlock (2026-09-23)

**Gate: FAIL / source continuity blocked. The 15-minute T1 was not started.**
Safari official playback and Chrome RONRO capture were used; Chrome's source
tab remained paused. The deployed candidate and generic STT context were
unchanged (`server_vad_bounded`, 30-second bound, keyword `論路`). Actual
Chrome track: BlackHole 2ch (Virtual), 48 kHz, mono, live, unmuted, WSS open.
A fresh provenance-only session initially had zero Evidence/Finals, idle
analyzer, zero queue depth and no current topic. Its initial revision was 2
(session setup), not a claimed zero revision. Separate initial utterance/node
counts were not archived and must not be inferred from that revision.

### Signal and semantic provenance

| Observation | Result |
| --- | --- |
| Before playback RMS | 0 |
| Playing pre-resample RMS | 0.059759 |
| Pause window | 25.328 seconds, RMS approximately 1.29e-9 |
| Pause Final count | remained 5 after buffered completion |
| Resume window RMS | 0.063861 (aggregate window includes startup silence) |
| Three consecutive source-matching Finals | sequences 7–9, matched against official Player's displayed captions |

The three corresponding semantic units concerned local value and
administrative collaboration, the following speaker's collaboration plans,
and organizational development with local residents. Proper-name recognition
was imperfect; semantic correspondence is not a verbatim accuracy claim.
The comparison was assistant verification against displayed captions, not a
completed human map-quality review. No demo-theme content was observed.
All 10 Finals had current-session Evidence and provider item/event correlation.
This establishes recognition recovery, not completeness of all source speech.

Recorded boundary reasons for Finals 7–9 were `bounded_fallback`,
`speech_started`, `speech_started`. The latter is the actual diagnostic label;
it must not be silently relabeled as a verified `server_vad` completion reason.
Whole-session recorded reasons: bounded_fallback 3, speech_started 6,
server_vad 1. No metadata or product behavior was changed to normalize them.

### Source continuity failure and stop

The non-evaluation source began around 01:16:54.56. Pause occurred around
01:17:55.01 and Resume progressed through main-content captions at
01:19:07.07. The next observed captions were advertising content at player
times approximately 2.27 and 5.77 seconds. A subsequent read showed 11.44
seconds, and the visible Player showed a sponsor. Thus the time reset was an
observed advertisement transition, not evidence of a RONRO transport reset.

Capture was stopped immediately after detecting the transition; Safari was
paused and temporary aggregate/caption observers were removed. Some ad audio
may have entered before detection. The session is unsuitable for T1 quality
scoring, even though its last completed Finals still corresponded to the
panel. No ad bypass, source download, extraction, or raw-audio storage occurred.

### Shutdown observations (not T1 results)

- Whole provenance session: 215.844 seconds including silence and Pause;
  this is not continuous source duration.
- Finals 10; partials 654; analyzer calls 10, failures 0.
- Queue pending/processing/failed: 0/0/0; graph/render: 18/18.
- Evidence and utterance counts: 10/10; no missing reference among the
  observed Final correlation records. Untranscribed pending audio integrity
  is **not established**.
- Automatic confirmation count: 0. Full owner/due and graph-corruption
  acceptance was not completed in this interrupted provenance run.
- State: `ended_with_incomplete_processing`, STT failures 1, empty Finals 1.
  The retained error was `input_audio_buffer_commit_empty` (provider buffer
  0 ms despite an explicit commit). Queue drain completion does not turn this
  into a clean `ended` acceptance. No drain safety rule was weakened.
- Queue wait p50/p95/max: 0.001/3.223/3.223 s; analyzer:
  4.354/6.837/6.837 s; E2E: 7.395/75.322/75.322 s. These include deliberate
  Pause and fragmented boundaries and are not T1 performance scores.

T1 source interval 01:24:00–01:39:00 remains unused in this attempt.
5/10/15-minute snapshots, Q1–Q5 reviews, tokens/cost and T1 graph-quality
decision are not available. **T1 NOT READY; T2 blocked.** A/B/C/D T1 quality
classification is withheld because T1 never started. Next action requires a
source-continuity plan that accommodates the observed official-player ads
without bypassing them, and a clean short-session shutdown verification.
No product fix, release, Pilot, T2/T3, commit, push, or deployment was performed.

## T1-H provenance retry — Premium login (2026-09-23)

Safari visibly showed YouTube Premium after the human completed login.
No account credentials were inspected or recorded. The fixed browser roles,
candidate, and audio-processing settings remained unchanged.

Fresh-session evidence/utterance/node/queue counts were 0/0/0/0. Chrome's
actual input was BlackHole 2ch (Virtual), 48 kHz mono, live, WSS open.
Before playback RMS was 0. Source playback began around 01:16:44.30,
outside the fixed T1 interval. Playing aggregate pre-resample RMS was
0.063847. Finals 2–4 corresponded to consecutive official captions about
administrative intermediation, successful cooperation, and increasing
difficulty acquiring property following regeneration. Proper nouns were
imperfectly recognized; this was assistant caption comparison, not a human
map-quality score. Their actual diagnostic reasons were `speech_started`,
`speech_started`, `server_vad`; labels were not rewritten.

Pause occurred around 01:18:17.99. During a 23.195-second pause measurement,
RMS was 0 and Final count stayed at 4. Resume advanced the Player to
01:19:00.14 with readyState 4 and paused false, but **muted true**. Chrome
RMS remained 0 in the aggregate observation window (61.205 seconds,
including pre-resume time), and no new partials/Finals appeared. No mute
transition timestamp or actor was observed, so the cause is unknown; neither
a Premium effect nor a product defect is established. No advertisement or
time reset was observed in this short attempt, which does not establish
15-minute uninterrupted playback.

**Provenance Gate FAIL: Resume did not restore source signal/Finals.**
Following the stop-on-failure rule, capture was ended and Safari paused
around 01:19:16.08. Temporary aggregate and caption observers were stopped;
the product capture handler was restored. No source media was saved.

Shutdown was clean this time: state `ended`, queue pending/processing/failed
0/0/0, graph/render 10/10, Final/Evidence/utterance counts 4/4/4, partials 274,
provider item/event correlation 4/4, STT/analyzer failures 0/0, empty Finals 0,
automatic confirmations 0. No demo theme was observed. The zero missing
Evidence count concerns completed Finals only, not all spoken source content.
The reported maximum unfinalized audio of 126.5 seconds includes accumulated
silence/muted capture and is not a measurement of unfinalized speech.

Whole-session duration 215.254 seconds includes setup, pause and muted
playback. Analyzer p50/p95/max was 4.491/6.510/6.510 s; E2E was
7.905/30.897/30.897 s. These are diagnostic observations, not T1 scores.
Full semantic safety review, T1 snapshots and Q1–Q5 scores remain unperformed.

**T1 NOT STARTED / NOT READY.** Before another short Gate, the source mute
state must remain observable across Play/Pause/Resume. No product tuning or
15-minute run was performed; T2/T3, release and Pilot remain unstarted.

## T1-H completed evaluation — separated browsers, Premium playback (2026-09-23)

### Frozen subject and method

Candidate source: `c942de995a232cd878bb51806df3cd86d8cfc0a4`.
Runtime image digest:
`sha256:5967236f927b8140caed8ce54ef45754f1454bb4b0621389bb3912f12e756a0b`.
Safari official Player → BlackHole 2ch → Chrome capture → existing RONRO
Live pipeline. Actual Chrome input was BlackHole, 48 kHz mono; existing
resampling/PCM16LE 24 kHz and microphone processing were unchanged.
Realtime model: `gpt-transcribe`; generic Japanese meeting context;
keyword `論路`; `server_vad_bounded`, 30-second bound.
Analyzer: `gpt-5.6-luna`, `analyzer-prompt-v4`.
No Analyzer, STT context, projection, canonical contract or product code
was modified. No tests were rerun because this was runtime evaluation only.

Source: 中国圏広域地方計画シンポジウム, published by 国土交通省 中国地方整備局,
event date 2024-03-04.
[Official page](https://www.cgr.mlit.go.jp/kikaku/kokudo_keisei/r6sakutei/symposium/index.html),
[official video](https://www.youtube.com/watch?v=2fd1F2W8k60).
Fixed interval **01:24:00–01:39:00**, continuous 900 seconds.
Premium login was human-operated. No media download, extraction, advertisement
bypass or raw-audio persistence was used.

### Final provenance gate: PASS

After manual unmute, a new non-T1 session began with
Evidence/utterance/node/queue counts 0/0/0/0. Playing RMS was 0.083119;
Pause-window RMS approximately 8.12e-10 over 33.824 seconds, with Final count
stable at 6; Resume RMS was 0.091633 and source-corresponding Finals resumed.
Three consecutive Finals matched displayed official captions concerning
roadside stations, residential/tourism functions and relationship populations.
This was assistant caption verification, not a human verbatim annotation.
Mute remained false and source time advanced without ads/reset.
Drain: `ended`, Finals/Evidence 9/9, queue 0/0/0, graph/render 16/16,
STT/analyzer failures 0/0, empty Finals 0. Recorded reasons: bounded_fallback
7, server_vad 1, session_end 1. No demo or cross-session content was observed.
The provenance session was ended before creating the independent T1 session.

### T1 source integrity and timing

The T1 session began empty and the source was paused at 5040 seconds before
scheduled playback. The Play invocation was 1 ms after the scheduled timer;
this is invocation alignment, not measured sample-level synchronization.
There were 17,772 source monitor samples inside the running interval:
paused 0, muted 0, readyState below 3: 0, backward jumps over 0.1 s: 0.
Observed first playing time: 5040.000; terminal stop: 5940.021 seconds.
Source-stop overshoot was approximately 21 ms, an observed timer tolerance,
not a claim of sample-exact clipping. No source pause/seek/restart/ad occurred.
No capture reconnection was observed; an independent WSS reconnect counter
was not collected.

The session included approximately 56 seconds of silent pre-roll before
source start. Total capture was approximately 957.4 seconds (9,574 chunks);
source-period pre-resample samples at the 15-minute observation represented
approximately 900.89 seconds. Whole runtime duration 962.671 seconds includes
pre-roll and drain and must not be labeled 15 minutes of source speech.
Pre-resample aggregate RMS at 5/10/15 minutes: 0.086661 / 0.081657 / 0.080078.
Silence ratio, clipping ratio and independent provider append count were not
collected in this run. No raw audio was retained to derive them afterward.

### Snapshots and final graph

Automatic snapshots were saved at 5/10/15 minutes by the existing evaluation
harness. Shared View screenshots were observed near those checkpoints in
the private task; they are not public assets or exact-frame screenshots.

| Checkpoint | Finals | Partials | Topics | Nodes | Relations | Graph/render | Visible issue cards |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| 5 min | 21 | 1454 | 1 | 16 | 13 | 32/32 | 6 |
| 10 min | 41 | 2808 | 1 | 30 | 24 | 57/57 | 6 |
| 15 min, before final drain | 52 | 4310 | 1 | 38 | 31 | 72/70 | 6 |
| Final drained | 53 | 4353 | 1 | 38 | 31 | 72/72 | 6 |

Current Topic remained “道の駅を核とした地域づくり” throughout all checkpoints.
Final graph: Idea 32, Concern 4, Option 1, Topic 1; Decision candidates,
confirmed Decisions, Open Items and Actions all 0. One topic-focus event
was recorded (initial focus), with no subsequent topic transitions/return.
Duplicate Topics: 0 (only one Topic); exact duplicate labels: 0. Semantic
near-duplicates were not exhaustively annotated. Nodes/Final: 0.717;
maximum nodes linked to one Evidence: 2; all Nodes/Topic: 38 (37 non-topic).

### Quality review and failure analysis

Canonical Graph retained later ideas about MaaS/data cooperation, regional
festivals, resident participation, cycling/environment, and interregional
networks. These were largely placed under the initial roadside-station Topic.
The same six early cards remained visible at 5/10/15 minutes, while the
“other items” count grew from approximately 8 to 22 to 30 in screenshots.
Consequently graph growth did not translate into an equally useful display
of the current discussion or its changing flow.

An Option describing exclusion of repeat visitors was created from a
speaker's qualification to an example, not an evident proposed course of
action. This is an **Analyzer semantic / option-boundary issue**, not false
Decision confirmation. Geographic/proper-name strings also warrant review,
but without an independent complete source annotation no exhaustive STT
accuracy or negation-loss claim is made.

The Shared View header still displayed a prototype/demo session goal. This
is a presentation-context issue; it is not evidence of demo speech being
injected into STT. No demo-theme Final was observed.

Primary classifications: Topic detection/under-segmentation; Topic return
not represented; Projection/compaction visibility; Analyzer semantic error;
evaluation ambiguity for unannotated proper nouns. Node explosion was not
demonstrated by the aggregate node rate. No product fixes were made.

### Q1–Q5: assistant provisional review, human review pending

These scores are **not human ratings**. They document the assistant's
inspection of snapshots, graph labels and observed source context. A human
reviewer should validate them; no participant feedback or consent collection
was undertaken.

| Time | Q1 Current Topic | Q2 Main Issues | Q3 State | Q4 Flow | Q5 Meeting Value |
| --- | --- | --- | --- | --- | --- |
| 5 min | 3: broad initial topic understandable | 3: funding/recognition/cooperation visible, later details grouped | 3: no false Decisions/Actions, but an unsupported Option | 2: only one topic shown | 3: useful initial summary, limited current emphasis |
| 10 min | 2: topic label lags broader discussion | 2: new canonical issues not surfaced | 3: cautious state categories, same Option caveat | 1: shifts not visible | 2: static early cards hamper following discussion |
| 15 min | 2: early topic remains through later themes | 2: concluding/network themes hidden among accumulated items | 3: no automatic confirmation or invented task commitments | 1: no meaningful topic sequence/return | 2: archive value exceeds live meeting value |

Provisional Q1/Q2/Q5 averages are each 2.33, below the 3.5 guidance. The
decision rests on observed stale current-topic/visible-card behavior, not
the averages alone. Human Q1–Q5 completion remains pending.

### Safety, performance and drain

- Automatic Confirmation 0; Actions 0, no non-null Owner/Due fields observed.
- Final/Evidence/utterance counts 53/53/53. Missing completed-Final Evidence
  0; duplicate Node IDs 0; dangling relation endpoints 0; missing node
  Evidence references 0. These structural checks do not prove perfect STT
  recall or absence of all semantic errors.
- Queue failures 0; STT failures 0; Analyzer failures 0; empty Finals 0.
- Recorded boundary reasons: bounded_fallback 16, speech_started 35,
  server_vad 2. The `speech_started` diagnostic label is retained as-is;
  an exact count of completed server-VAD turns cannot be recovered simply
  by relabeling it. No Final was tagged session_end in this run.
- Maximum reported unfinalized audio 57.3 s includes the silent pre-roll;
  it is not a maximum unfinalized **speech** measurement.
- Drain `ended`, pending/processing/failed 0/0/0, graph/render 72/72;
  duration 4.165 s, no remaining processing items.

| Latency, seconds | p50 | p95 | max |
| --- | ---: | ---: | ---: |
| Queue wait | 0.0036 | 4.403 | 5.541 |
| Analyzer | 4.100 | 6.340 | 6.771 |
| Existing runtime E2E | 6.994 | 39.604 | 72.408 |

The existing E2E figures exceed the Pilot target, especially the tail. They
include bounded-turn accumulation and pre-roll/timing semantics; this is not
a controlled regression comparison against headless p50 11.04 / p95 13.18 s.
Analyzer p95 is close to the previous approximately 6.31 s reference.
Independent speech-end→STT-final latency was not available. Evidence timestamp
minus the application's last audio timestamp is not a trustworthy substitute
for acoustic end-of-speech latency. Tokens and cost were not exposed by the
collected runtime data and remain unavailable, not estimated.

### Decision and artifacts

**C. T1 QUALITY ISSUE — Analyze before T2.** The source/audio/STT/graph/drain
pipeline completed the interval; this was not the previous “one Final in
15 minutes” failure. The live display's topic tracking and selection of
visible issues did not adequately reflect discussion development.

Existing runtime/PVC evaluation artifacts and aggregate diagnostic files are
private. Screenshots and detailed graph-derived data require separate
publication review. This public report includes metadata, aggregates and
short semantic summaries only; no audio, video or full transcript is added.
Prior failed runs are preserved. **T2/T3, Live Pilot and release work were not
started.** No commit, push, merge, tag, deployment or product tuning occurred.

## T1 Topic Focus / Projection Diagnostic

### Scope and evidence limits

Post-run inspection of the frozen candidate `c942de995a232cd878bb51806df3cd86d8cfc0a4`, retained ended-session snapshot, accepted Events, Evidence, 53 queue items, and saved 5/10/15-minute Graph/Projection snapshots. The original run and artifacts were not overwritten; STT and Analyzer were not rerun. Only this report was changed.

The saved artifacts expose **accepted Analyzer-derived Events**, not the original Analyzer response JSON. `RealAnalyzer._finish_trace` keeps raw output in in-memory `run_history`; the live queue retains accepted Events and validation failures, not that response history. Consequently, “Analyzer repeatedly explicitly selected the old topic” is **not established**. A same-current `topic_focus` is suppressed by `_to_candidates`, so absence of a new canonical focus Event cannot distinguish no proposal from repeated same-topic selection or a filtered proposal. This is an important limit on attribution, not grounds for fabricating a model-output timeline.

### Discussion / accepted interpretation timeline

Elapsed seconds below are **Final receipt/Evidence timestamps relative to source Play**, not exact acoustic boundaries or word-level source timecodes. They include recognition/finalization delay. Short labels are reviewer paraphrases, not transcript excerpts. I=Idea, C=Concern, O=Option, T=Topic, —=no new Node. All raw Analyzer Topic interpretations and raw `topic_focus` outputs are unavailable. The accepted interpretation is captured by the Node types and association columns.

Association: `T1` means an explicit `contains` edge from the sole Topic; `lane T1` means layout membership inferred from the last focus Event, **not a canonical parent relation**; `—` means no new association. Canonical current topic is unset for Finals 1–2, then T1 (道の駅を核とした地域づくり) throughout Finals 3–53. Accepted topic proposal/focus: only Final 3 creates T1 and emits `topic_focus_changed`; all other rows have no accepted Topic/focus change.

| Final | Elapsed s | Short semantic label | New types | Association |
|---|---:|---|---|---|
| 1 | 1.5 | Opening fragment | — | — |
| 2 | 13.0 | Broaden perspective in stages | I | Unassigned |
| 3 | 45.0 | Roadside stations, relationships and wider cooperation | T, I | T1 created; I→T1 |
| 4 | 47.6 | Bring external funding into region | I | T1 |
| 5 | 55.3 | Limits of domestic resources | I | T1 |
| 6 | 64.6 | Attractiveness of visiting and experiencing | I | T1 |
| 7 | 71.1 | Personal cycling experience | — | — |
| 8 | 73.9 | Personal hot-spring visit | — | — |
| 9 | 105.3 | Offerings fail to reach intended visitors | C | T1 |
| 10 | 118.9 | Low regional recognition abroad | C | T1 |
| 11 | 121.3 | Landmark known, wider region less known | — | — |
| 12 | 133.9 | Established destination as comparison | I | lane T1 |
| 13 | 146.5 | Qualification about repeat visitors | O | T1 |
| 14 | 178.4 | Joint regional messaging and appeal | I | T1 |
| 15 | 185.4 | Closing suggestion about differentiation | — | — |
| 16 | 216.9 | Moderator transition to organizational silos | C | T1 |
| 17 | 225.8 | Reconsider negative view of silos | I | T1 |
| 18 | 238.9 | Organizational remit limits participation | C | T1 |
| 19 | 270.9 | Consortium and transport-provider cooperation | I | T1 |
| 20 | 271.4 | Continuation fragment | — | — |
| 21 | 294.1 | Bus/taxi data and common service design | I | T1 |
| 22 | 326.3 | Shared goals enable organizational participation | I | T1 |
| 23 | 328.6 | Shared willingness to collaborate | I | T1 |
| 24 | 360.2 | Structure that turns informal ideas into collaboration | I | T1 |
| 25 | 392.0 | Mobility data, tourism and regional revitalization | I | T1 |
| 26 | 420.9 | Transition fragment | — | — |
| 27 | 421.0 | Student perspective and festival research | I | T1 |
| 28 | 446.2 | Festival links between districts | I | T1 |
| 29 | 447.5 | Administrative-area fragment | — | — |
| 30 | 456.1 | Municipal affiliations | I | lane T1 |
| 31 | 475.9 | Festival and everyday inter-regional exchange | I | lane T1 |
| 32 | 492.2 | Cultural-heritage comparison | I | T1 |
| 33 | 494.3 | Local-area fragment | — | — |
| 34 | 498.3 | Raising festival value | I | T1 |
| 35 | 507.0 | Tentative heritage-recognition proposal | I | T1 |
| 36 | 513.9 | Reflection on panel contributions | — | — |
| 37 | 543.2 | Resident participation and local attachment | I | lane T1 |
| 38 | 553.9 | Cycling, photography and childcare connections | I | T1 |
| 39 | 558.1 | Personal family anecdote fragment | — | — |
| 40 | 590.2 | Cross-domain participation opportunities | I | T1 |
| 41 | 595.9 | Closing cross-domain reflection | — | — |
| 42 | 628.9 | Transport modal shift, health and environment | I | T1 |
| 43 | 642.7 | Station-area regional benefits | I | T1 |
| 44 | 652.2 | Cooperation to realize transport benefits | I | T1 |
| 45 | 663.8 | Whole-stakeholder rather than sector-only effort | — | — |
| 46 | 695.6 | Transport closing and moderator transition | — | — |
| 47 | 728.6 | Moderator synthesis: transport, digital and tourism | I | T1 |
| 48 | 761.8 | Data-informed strategy; return to external revenue | — | — |
| 49 | 794.6 | Sustainable income and industry networks | I | T1 |
| 50 | 828.3 | Active population, work and resident participation | I | T1 |
| 51 | 863.0 | Links across regions | I | lane T1 |
| 52 | 896.5 | Everyday links supporting disaster mutual aid | I | T1 |
| 53 | 902.3 | Clipped continuation at interval end | — | — |

Reasonable focus-shift candidates are Finals 16–19 (organizational/transport cooperation), 27–31 (festivals as regional connections), 37–40 (resident participation), 42–44 (return to transport benefits), and 47–52 (cross-panel synthesis and mutual aid). These are diagnostic judgments, not Golden Topics. A broad “regional development through cooperation” Topic could reasonably contain all of them. The specific roadside-station title ceases to describe the immediate discussion, however. More Topics are not automatically the remedy; within-Topic focus is also missing.

### Analyzer and canonical branch

Accepted output recognized later concepts as Ideas/Concerns, but created only one Topic and one focus Event (at Final 3, Event sequence 7). The first clearly material semantic focus mismatch is visible by Finals 16–19, **before Shared selection**: the newly accepted organizational/transport nodes still attach to the roadside-station Topic. Later festival, participation and transport nodes show the same pattern.

The materializer applies the accepted focus Event correctly. No saved Event proposes another current Topic that the materializer then ignores. The canonical model supports multiple Topics and focus transitions; a schema limitation or dropped focus Event is not supported by this run. `_find_duplicate_topic` uses normalized label equality, not fuzzy semantic similarity; “aggressive semantic Topic merging” is not demonstrated. Adapter filtering means rejected/new raw proposals cannot be ruled out without original response traces. The v4 prompt favors durable axes, reuse of existing Topics, and child Ideas rather than Topic proliferation; this is a plausible contributor, **not a proven explanation of the model's private reasoning**.

Later association examples: Finals 19/21/25 (transport), 27/28/32/35 (festival), 38/40 (participation), 42/44 (transport return), 49/50/52 (synthesis) have explicit T1 `contains` edges. Finals 30/31/37/51 have no incoming canonical association edge and enter T1's display lane via focus-at-creation inference. None displaces the first six visible items.

### Exact six-card selection reconstruction

The Live route calls `live_continuous._render_now_locked → layout.map_projection`, **not** `projection.build_presentation_projection`. The latter's importance/recency/compaction ranking is used by other evaluation paths, but not this Live Shared path. A configuration/metadata statement that compaction is enabled does not establish it executed here. This corrects any earlier assumption in this report that the long-session compactor selected the T1 cards.

`shared.html` takes current lane `node_ids`, filters active Idea/Option/Concern, then calls `slice(0, 6)`. StableLayout preserves node insertion order and stable placements. There is no recency ranking, relation-count ranking, activity score, or turnover of old active Ideas. “Other items” communicates a count, not the new discussion content. Recent Flow only consumes Topic focus transitions, so within-one-Topic movement is absent there too.

The saved snapshots reproduce exactly the same six node identities at 5, 10 and 15 minutes:

| Slot / originating Final | Short card summary | Type | Creation elapsed s¹ | Age at 5 / 10 / 15 min, approx s | Selection reason |
|---|---|---|---:|---|---|
| 1 / 3 | Roadside stations and regional relationships | Idea | 45.0 | 255 / 555 / 855 | First eligible T1 node |
| 2 / 4 | External funding | Idea | 47.6 | 252 / 552 / 852 | Second eligible T1 node |
| 3 / 5 | External resources and domestic limits | Idea | 55.3 | 245 / 545 / 845 | Third eligible T1 node |
| 4 / 6 | Desire to visit and experience | Idea | 64.6 | 235 / 535 / 835 | Fourth eligible T1 node |
| 5 / 9 | Intended audience not reached | Concern | 105.3 | 195 / 495 / 795 | Fifth eligible T1 node |
| 6 / 10 | Low regional awareness | Concern | 118.9 | 181 / 481 / 781 | Sixth eligible T1 node |

¹Node `created_at` follows the source Event's Evidence-based timestamp, not actual Analyzer completion. All six have explicit T1 membership. Ages are reviewer diagnostics; **age is not an input to selection**. The six slots are already occupied by about 02:08 when Final 10 has been materialized/rendered. The next new Idea (Final 12) cannot enter the visible six even at that early point. Final 2 remains unassigned and is not a current-lane candidate.

| Snapshot | Discussion context from nearby Finals | Displayed current Topic / cards | Graph / rendered revision |
|---|---|---|---|
| 5 min | Transport-provider cooperation and shared data | Roadside-station Topic; same six above | 32 / 32 |
| 10 min | Resident participation and cross-domain links, after festival discussion | Same Topic and six | 57 / 57 |
| 15 min | Regional cooperation synthesis and disaster mutual aid | Same Topic and six | 72 / 70 before drain; 72 / 72 afterward |

These comparisons are evidence for later Human Review. Q1–Q5 remain **Human Review pending**; earlier assistant scores are provisional only. A reviewer should judge whether the source focus is fairly summarized and whether the visible six help continue that discussion, rather than treating this timeline as authoritative annotation.

### Latency: a separate measurement effect

The reported all-item E2E p95 39.604 s is real under the implementation's timestamp definition, but does not mean new Graph content waited that long. `mark_rendered` stamps every completed unmarked queue item only on a later projection render. The coalescer schedules a render only when graph revision advances. **No-op Analyzer results can therefore wait for another utterance's Graph change**, inflating their measured E2E without withholding any new Node.

| Final | New Events | Queue s | Analyzer s | Graph-updated stamp → render s | Reported E2E s |
|---|---:|---:|---:|---:|---:|
| 45 | 0 | 0.006 | 2.778 | 69.561 | 72.408 |
| 46 | 0 | 0.005 | 2.629 | 37.933 | 40.604 |
| 7 | 0 | 0.001 | 2.731 | 36.773 | 39.604 |
| 48 | 0 | 0.004 | 3.146 | 36.405 | 39.600 |

For the **37 Graph-changing items**, the same E2E definition gives p50 **6.702 s**, p95 **9.202 s**, max **9.809 s**. Across all items, queue wait p95 is 4.403 s and Analyzer p95 6.340 s. This does not replace the original run metrics; it explains their composition. The map-render timestamp is a server projection timestamp, not instrumented browser paint acknowledgment.

Focus-shift correlation (seconds since source Play; revision is after accepted item Events):

| Final / focus | Final receipt | Analyzer completed | Revision | Projection rendered |
|---|---:|---:|---:|---:|
| 19 / transport cooperation | 270.9 | 275.9 | 30 | 278.0 |
| 27 / festivals | 421.0 | 426.8 | 42 | 428.9 |
| 37 / residents | 543.2 | 547.4 | 53 | 549.5 |
| 42 / transport return | 628.9 | 634.0 | 59 | 636.1 |
| 47 / synthesis | 728.6 | 734.1 | 65 | 736.1 |
| 52 / mutual aid | 896.5 | 899.6 | 72 | 901.7 |

Exact acoustic source-shift → Final latency cannot be reconstructed from these records: frame ranges and `audio_end_at` do not independently mark the last spoken word. STT finalization may delay when content becomes available, particularly on bounded turns; no precise acoustic latency is invented here. It cannot explain why cards remain unchanged minutes after their successor Nodes and matching rendered revisions exist.

### Product intent and category safety

The MVP RD requires participants to understand the current discussion. UX RFC 0003 §§4.2–4.3 and §§5.3–5.4 prioritize Current Topic and surrounding Ideas, distinguish important persistent state, and preserve stable Topic lanes. The implementation meets **positional stability**, but stable positions have effectively become permanent ownership of scarce visible slots. The RFC's Topic-only Recent Flow also cannot express within-Topic returns. “Recent active discussion” and “persistent important state” need distinct presentation treatment; `current_topic` identifies a branch, not the latest context inside that branch.

Decision/Open Item/Action = 0 is not independently a defect. The reviewed speech is mostly descriptions, opinions, illustrative examples and general cooperation proposals; there is no clear group decision or concrete execution commitment requiring a Decision/Action. A heritage-recognition suggestion (Final 35) and general “necessary” cooperation do not justify inventing an owner, due date or confirmed decision. Moderator invitations/questions need not become persistent unresolved work. Human semantic review is still needed for completeness. Separately, Final 13's audience qualification becoming an Option deserves boundary review; it is not evidence of a false Decision or the cause of display staleness.

### Ranked root cause and next step

**Decision: E. Combined Issue — with projection as the directly proven primary cause.**

- **Primary, proven:** Live Shared current-lane insertion-order `slice(0,6)` starves later meaningful nodes. The earliest deterministic display-selection mismatch begins once those slots fill; it persists even when canonical and rendered revisions agree. Long-session compaction ranking is not on this execution path.
- **Secondary, observed:** Accepted Topic/focus remains narrowly roadside-station-centered while semantic content changes. This limits the header and Recent Flow. The raw Analyzer-vs-adapter reason for no new focus is unavailable; repeated old-topic output, rejected proposals and intentional broad grouping must not be asserted as established facts.
- **Secondary, diagnostic rather than main UX cause:** No-op render stamping inflates aggregate E2E tails; actual new-node render latency is much lower. Some STT delay remains unquantified.
- **Not supported:** Materializer dropping a correct focus transition, Graph corruption, a one-Topic schema restriction, fuzzy Topic deduplication, or queue/backpressure as the primary cause.

**Exactly one recommended next Spike: frozen-Graph, within-Topic recent-context Shared projection.** Compare the current six-card selector with a small, deterministic recent-activity selection in offline saved snapshots, retaining stable slots/hysteresis and separate protected Decision/Open/Action state. Include generic synthetic meetings with topic returns and quiet-but-important state so this cannot overfit the panel's vocabulary. Do not rerun/tune Analyzer or create additional Topics for this Spike. Its question is whether existing later Nodes can restore “議論の現在地” without slot churn, loss of important state or new semantic claims. The stale Topic title remains an explicitly measured residual limitation, not silently solved by recency.

Acceptance for that single Spike should include reviewer comparison at 5/10/15 minutes (especially Q1/Q2/Q5), visibility of recent meaningful content, retained important state, bounded card movement, unchanged canonical Graph/Evidence, and no new Decisions/Actions. This report implements none of it.

**T2: NOT READY.** Product code, prompts and configuration remain unchanged; no STT/Analyzer rerun, T2/T3, release or Pilot was performed. No new Human Review scores were assigned.

## T1 Shared View Projection Spike

### Scope, reproducibility and decision status

Offline follow-up to the unchanged **C. T1 QUALITY ISSUE** result. `evaluation/tooling/shared_projection_spike.py` consumes the private retained snapshot and saved 5/10/15-minute artifacts. It replays the original accepted Events through the existing materializer **in memory only**, compares the reconstructed final Graph and checkpoint Graphs to the originals, and verifies unchanged input hashes. No STT, Analyzer, LLM ranking, audio replay, runtime API mutation, deployment, or production UI change occurs.

Recommendation for **Human Review**, not automatic adoption: **Projection C — Stable Recency + Persistent; UX B — Minimal active chrome.** These improve the objectively measured freshness and slot stability. Semantic coverage/explanation ratings below are assistant-provisional; adoption remains gated on Human Review and physical display readability. The stale canonical Topic is neither renamed nor replaced.

### Four deterministic comparison rules

| Rule | Ordinary discussion selection | Persistent state | Ordering / stability |
|---|---|---|---|
| Existing | Current lane active Idea/Option/Concern, insertion-order first six | Existing separate status rail | Fixed early cards |
| A: Latest Six | Current lane, last node-related Event first, six | Not specially protected by this comparison selector | Entire list re-sorts |
| B: Recency + Persistent | Current lane plus unassigned meaningful nodes, recent first | Active important state across Topics reserves slots first | Entire list re-sorts |
| C: Stable Recency + Persistent | Recent active ordinary nodes across the discussion, not restricted by a stale Topic label | Same protected state as B | Keep surviving cards in their slots; fill vacated slots with newcomers |

B/C start with **six total slots**, not six ordinary plus unlimited persistent cards. Candidate/confirmed Decision, active Open Item and active Action remain semantically distinct and are not confirmed/closed by selection. Resolved, completed, revoked, archived and parked state is excluded from these candidate slots. Persistent ordering uses creation time/ID for deterministic stability, not a new importance score. **More than six simultaneously important items is an explicit overflow limit** of this Spike; it must not be represented as complete persistent recall or resolved by increasing density. No production adoption is approved for that untested saturation case.

Recency uses the maximum existing node `source_event_ids` sequence, with ID as tie-breaker. A Topic focus Event alone does not refresh every child. C deliberately spans canonical lane boundaries, allowing existing meaningful unassigned labels and recently active discussion to be shown without displaying a bucket. This differs from B and avoids an old lane's mere re-selection resurrecting its oldest Ideas as “recent.” Renewed node-related activity can bring an old node back. No canonical membership is changed.

Stable slots are reconstructed from the canonical Event prefix from session start, never arbitrary browser history. Within the same immutable session/history and selector version, the same Graph revision yields the same result on independent replay. A revision number without its session/history is not a globally unique input. Multi-node changes can still replace more than one card; the rule does not claim a timed hold or one-per-second throttle. It has no clock-driven carousel or complex weighted score.

### Baseline reproduction and snapshot comparison

The original first-six identities reproduce exactly at all three checkpoints: regional relationships through roadside stations, external funds, external resources, visit/experience appeal, audience not reached, and low regional recognition. All six are unchanged across both five-minute transitions. The table in the preceding diagnostic records their types, origin Finals and ages.

The private HTML includes all four variants at each checkpoint, each full card label and age, entrants/leavers and blank Human rating/reason fields. A shorter six-screen artifact compares only Existing versus C. Labels remain the saved generated Graph labels, including recognition mistakes; no new label summary is substituted into the mock screen.

| Checkpoint | A/B/C card membership, short semantic summaries (order differs in C) | Existing transient age median / max | A/B/C transient age median / max |
|---|---|---|---|
| 5 min | Bus/taxi data; MaaS provider cooperation; remit limitations; reconsider silos; negative silo framing; joint regional messaging | 240.0 / 255.0 s | 67.6 / 121.6 s |
| 10 min | Cross-domain participation; cycling/childcare; resident participation; heritage proposal; festival value; heritage comparison | 540.0 / 555.0 s | 74.9 / 107.8 s |
| 15 min | Emergency mutual aid; regional links; active population; sustainable networks; transport/digital/tourism synthesis; transport cooperation | 840.0 / 855.0 s | 88.5 / 247.8 s |

At 10 and 15 minutes, all six candidate cards differ from their respective previous five-minute snapshot; existing retains all six. This is **not six simultaneous replacements at a checkpoint**: event-prefix replay shows gradual replacement between checkpoints. T1 still has exactly one canonical Topic, 38 Nodes and 31 relations. Its movement through transport, festivals, participation, transport return and synthesis becomes visible without new Topics. The six-item budget still retains some prior context: the oldest final card is approximately 4.1 minutes old, not necessarily a failure when it supports the synthesis.

Card age here is source Node `created_at` to checkpoint time, not an invented acoustic time. T1 nodes were not repeatedly edited; for a future updated-node case, selection activity age and creation age must be reported separately. The 15-minute original projection lags the Graph (72/70); baseline uses the saved projection, candidates use saved canonical revision 72. Graph/render becomes 72/72 after drain. This distinction is preserved rather than silently rewriting the original snapshot.

### Churn and persistent-state tests

| Rule | Event-replay replacements over T1 | Approx replacements/min | Surviving-card slot moves |
|---|---:|---:|---:|
| Existing | 0 | 0.00 | 0 |
| A | 29 | 1.93 | 160 |
| B | 31 | 2.07 | 170 |
| C | 31 | 2.07 | 0 |

Replacements exclude initial filling; moves count a surviving card changing slot at each canonical Event prefix. This is deterministic offline churn, not measured browser repaint frequency; production coalescing may combine intermediate updates. B/C additionally admit unassigned content, accounting for their different early history from A. At these three T1 checkpoints the selected membership converges, so C's advantage over B is slot preservation, **not claiming fewer membership replacements**. Roughly two replacements per minute is a reviewable trade-off, not a proven universal usability threshold.

**24 offline checks passed:** 13 existing fixture histories tested for independent deterministic replay, input immutability and persistent retention, a Topic-return fixture assertion, and 10 pressure/activity checks on five copies of existing synthetic fixtures. Pressure variants append ten synthetic Ideas only to in-memory synthetic fixture copies, never the T1 Graph. Coverage includes candidate/confirmed Decision, active Open Item/Action, resolved/revoked exclusion, newest Idea entering, old Idea leaving but remaining in Graph, fixed surviving slots, and renewed node activity re-entering. Important-state recall is 100% for tested prefixes with at most six eligible persistent items. T1 itself has none; persistence was not fabricated into T1.

The existing Topic-return fixture has Topics but no ordinary content, so it verifies no invented cards rather than proving subtheme understanding. Separate synthetic activity/eligibility pressure tests verify that focus alone does not refresh/reintroduce an old card, while an explicit related Event can. The T1 return to transport is reflected by its actual later transport Nodes. Projection cannot infer a semantic return that never produces node-related activity; that remains an explicit limit.

Existing regression suite: **168 tests discovered, 147 passed, 21 skipped under existing excluded-data policy**. The 24 offline checks are additional script assertions, not represented as additions to that unittest count. No provider calls are part of this Spike.

### Generic bucket and active chrome audit

`layout.py` emits internal `Other Discussion Items` for unassigned nodes; `projection.py` uses the same fallback in topic-summary construction. The actual Live Shared page does **not** directly print the unassigned lane heading. It can show canonical labels through current title, past Topics and Recent Flow; a generic canonical Topic label would therefore leak through those paths. In this T1 baseline, visible generic bucket headings are already **0**, not a newly measured reduction. `＋ほかN件` is an overflow count, not a semantic heading; it does not make the hidden discussion understandable.

C presents existing semantic Node labels with no dominant Topic/bucket heading, past-topic generic chips, or synthesized title. Thus the candidate's generic bucket heading exposure is **0**, including the synthetic unassigned eligibility case. This is heading suppression only; meaningful Nodes are still eligible, canonical labels/relations are unchanged, and a meaningless Node label itself is not magically repaired. No synonym classifier or LLM-generated heading is introduced.

| Element | Existing active view | Candidate minimal view |
|---|---|---|
| Product identity | Prominent 論路 plus session goal | Removed from active content; retain identity at Idle/entry if needed |
| Usage instruction | Persistent “普段どおり…” footer | Removed during discussion |
| Current Topic | Dominant heading, stale in T1 | Not dominant; semantic cards carry current context |
| Runtime trust | Header status and auxiliary copy | Subtle listening/state indicator only |
| Empty state rail/history | Repeated empty sections | Omit when empty; preserve actual important state when present |
| Idea/Option/Concern names | Not explicitly printed on original cards; CSS differentiates | No new internal type captions |
| Decision state | Candidate/confirmed distinction | Must remain explicit, never collapse to an undifferentiated “decision” |
| Revision/queue/IDs | Absent from participant surface | Remain absent; diagnostics outside mock screens |

The review artifact keeps six cards on a 16:9 canvas with meaning-first type. It is a **selection-faithful simplified mock**, not a pixel-perfect baseline screenshot. Some existing labels are long and need distance/readability review; no LLM shortening, hidden transcript, or silent semantic edit was used. Browser preview was blocked by the available tool's local-file URL policy, so screenshots and visual-overflow QA are **not claimed complete**, and no workaround was attempted. Human must open the local artifact and assess 3–5m readability, full label fit, movement and explanation cost before adoption.

### Provisional semantic review and handoff

| Variant | Coverage 5 / 10 / 15 min | Explanation Cost 5 / 10 / 15 min | Assistant rationale (not Human score) |
|---|---|---|---|
| Existing | 2 / 1 / 1 | 2 / 2 / 2 | Early cards dominate; header and stale context need explanation |
| A | 4 / 4 / 4 | 4 / 4 / 4 | Current concepts become visible; frequent list reordering remains |
| B | 4 / 4 / 4 | 4 / 4 / 4 | Same T1 membership; important-state protection matters in fixtures |
| C | 4 / 4 / 4 | 4 / 4 / 4 | Same freshness, with surviving slots stable; title removal avoids narrow anchoring |

These are content-based provisional judgments, not display-distance test results, and do not grant C a fabricated higher semantic score simply for stable ordering. Human score/reason fields in the artifact are intentionally blank. Review Existing versus C first at 5/10/15, then consult A/B for the ordering trade-off; specifically ask whether six cards convey one understandable current discussion or still require too much reading.

Recommended **C + minimal active chrome B**, pending Human acceptance. This is not approval to modify Production. Existing long-session compaction supplied the reusable idea of separating important persistent state from ordinary nodes, but its entire ranking/grouping system is not wired into Live. Accumulated-density management and current-discussion selection remain separate problems.

Artifacts are private generated `compare.html`, `review.html` and `metrics.json`; source inputs, full labels and detailed IDs remain outside Public Git. Public source tooling and this aggregate report contain no T1 transcript/audio or private infrastructure identity. The original T1 C decision and all diagnostic history remain intact. **T1 audio was not rerun. T2: NOT READY pending Human Review.**

## T1 Final Shared View Candidate

### Human Review candidate, not Production adoption

**A. READY FOR HUMAN REVIEW.** The final offline candidate is **Stable Recency + separate Persistent Rail + maximum six discussion cards + non-interactive overflow counts + minimal active chrome**. It incorporates the Human decision that the shared surface should select discussion rather than attempt to show the entire Graph. The previous T1 C decision, diagnostic, and initial Projection Spike remain unchanged above.

`evaluation/tooling/final_shared_candidate.py` and its local HTML template implement only the offline comparison. They reuse the previous deterministic selection/replay helpers and existing fixture materialization. No Product modules, Canonical schema, Graph, Analyzer, prompt, audio pipeline, deployment or finalization settings were edited. No LLM/provider calls or audio evaluation took place.

### Exact projection contract

- **Discussion eligibility:** active Idea/Option/Concern across the saved discussion, including meaningful unassigned content. Exclude archived, resolved, completed, revoked and parked content. A stale Topic label does not limit the display pool or become a dominant heading.
- **Recency:** latest existing node-related source Event sequence, with node ID as deterministic tie-breaker. Topic focus alone does not refresh every child. This remains a simple recency policy, not LLM relevance ranking.
- **Six slots:** choose up to six ordinary cards. Preserve the physical slot of each surviving card and fill vacated slots with newcomers. Empty slots remain empty rather than repacking surviving cards. Reconstruct the slot history from the immutable session Event prefix; do not depend on browser visit history or wall-clock rotation.
- **Ordinary overflow:** eligible ordinary nodes minus actually displayed ordinary nodes. It includes older understood discussion that remains in Graph/history; it does not mean miscellaneous, unclassified or lower-quality content. Display only `ほかN件` when N is positive, below the main cards in lighter typography. It is not a button, link, seventh card, page number or automatic carousel.
- **Persistent Rail:** independent of all six ordinary slots. Show active candidate/confirmed Decision, unresolved Open Item and active Action using existing statuses. Group labels proposed for review are `決定・決定候補`, `残っていること`, `次にすること`. Decisions retain an explicit `候補 · まだ確定ではありません` or `確定` badge; no ambiguous collective “decided” label is applied.
- **Rail capacity:** one visible item per nonempty category (maximum three), ordered by creation time then ID. Retain that item while eligible; removal/resolution permits the next one. Each category reports its own additional count. This is an intentionally conservative initial capacity, not a new priority/urgency model. New ordinary Ideas cannot evict rail state. No rail is rendered when all categories are empty.
- **Rail limitation:** important items beyond capacity are represented by a count, not full semantic recall. An older candidate can remain visible while a newer confirmed decision is hidden; this trade-off must be reviewed explicitly. The candidate does not assert that counts alone suffice for every high-stakes meeting or silently shrink text to fit all state.

Graph capacity is independent of both display budgets. No hidden Node is deleted, relabeled, moved between canonical Topics, merged or given a new lifecycle status. No new Focus entity or Topic numbering is introduced. Long-session compaction is not wired into Live.

### T1 saved-revision results

| Snapshot | Recent content surfaced (short diagnostic summary) | Eligible ordinary | Visible | Hidden / displayed count | Median / max card age |
|---|---|---:|---:|---|---|
| 5 min | Transport-provider cooperation, organizational remit and shared data | 15 | 6 | 9 / ほか9件 | 67.7 / 121.6 s |
| 10 min | Festival context, resident participation and cross-domain connections | 29 | 6 | 23 / ほか23件 | 74.9 / 107.8 s |
| 15 min | Regional cooperation synthesis, sustainable networks and mutual aid | 37 | 6 | 31 / ほか31件 | 88.6 / 247.8 s |

T1 contains zero eligible Decision/Open Item/Action, so no persistent content is fabricated. The final candidate has the **same six identities and slots as the previous Stable Recency candidate** at these checkpoints. The substantive T1 changes in this iteration are explicit overflow communication and the complete minimal-chrome review layout. Separate Rail behavior is evaluated on synthetic states, not inferred from T1.

The original current-lane baseline has a slightly smaller pool because an early unassigned Idea is excluded there. Final eligibility is explicit: all active ordinary nodes, not only the current lane. Thus the final `ほか31件` is not an off-by-one error relative to the baseline's lane-only count.

Across the immutable T1 Event replay: **31 replacements, approximately 2.07/minute, zero surviving-card slot moves**. At each five-minute checkpoint transition six cards have entered and six left, with no shared identities; those are accumulated changes between checkpoints, not an instantaneous six-card swap. Initial filling is not counted as replacement. The private metrics retain entrant/leaver IDs. These are event-replay measurements, not actual browser paint measurements.

The original 15-minute saved projection can lag canonical revision 72; the baseline still uses its saved map while the candidate reconstructs the saved Graph. The original run and the 72/70 pre-drain versus 72/72 post-drain distinction remain intact. Ages derive from existing Node creation timestamps; they are not independently measured acoustic ages. No new source transcription was obtained.

### Persistent fixtures and invariants

Offline display-pressure states are explicitly derived from existing public synthetic fixtures; their illustrative labels/states are never inserted into T1 or any runtime session. Each contains nine ordinary Ideas, proving `9 eligible − 6 visible = 3 overflow` independently of rail content.

| Derived case | Persistent content | Visible rail items | Rail overflow | Ordinary area |
|---|---|---:|---|---|
| One | Active Action | 1 | None | Six + ほか3件 |
| Several | Confirmed Decision, Open Item, Action | 3 | None | Six + ほか3件 |
| Many | Three of each type; candidate and confirmed Decisions included | 3 | ほか2件 in each category | Six + ほか3件 |

The comfortable-capacity boundary is therefore more than one item in a category, not a hidden hard limit on Graph content. In the nine-item case, six persistent items remain available canonically but are not readable individually on the shared surface. Human Review must decide whether that trade-off matches the meeting need. The rail does not expand to dominate the discussion area.

**17 grouped offline assertions passed:** three pressure cases, one renewed-activity/Topic-return test, and deterministic replay of all 13 existing fixture histories. Assertions cover exact ordinary/rail overflow arithmetic, rail lifecycle exclusion, six ordinary slots independent of persistent arrival/removal, deterministic replays, immutable input, and unchanged surviving slots. The existing Topic-return fixture has no ordinary cards; the derived activity check verifies an old Node re-enters after actual node-related activity, while a Topic switch alone does not resurrect it. This is not a claim of semantic inference beyond saved Events.

The final reconstructed T1 Graph equals the saved final Graph, each checkpoint equals its saved Graph, and the original input hash remains unchanged. Production regression suite: **168 discovered, 147 passed, 21 existing-policy skips**. Offline assertions are counted separately.

### Review artifact and active chrome

A single private `index.html` provides review-only selectors for **Current**, **Previous Stable Recency**, and **Final Candidate**, at T1 5/10/15 minutes and all three persistent-pressure cases. Review controls, metrics and scoring fields are outside the 1920×1080 participant surface. They are not proposed Shared View controls. A full-screen review button is likewise outside the participant surface.

Inside the final surface:

- No prominent product name, usage tutorial, generic bucket heading, revision, queue, IDs, Event log or internal English Node-type caption.
- Meaning-bearing saved labels remain the largest text. The stale canonical Topic is not made responsible for explaining every card.
- A small runtime indicator is retained. Review controls compare `聞き取り中` with `聞いています`; wording is not finalized. It is clearly labeled outside the mock as a saved-state illustration, not actual microphone activity.
- Ordinary counts appear below cards; rail counts appear under their category. Both are plain non-clickable text, with no arrows or pager styling. No timer, pagination, automatic rotation or hidden-content activation exists.
- Main card text is 40px on the 1920×1080 design canvas; rail text is 30px and counts are secondary. Capacity is not handled by source-dependent font shrinking. Browser viewport scaling fits the whole 16:9 review canvas and is not a density adaptation.

Generic semantic bucket heading exposure is **0 by construction in the final candidate**. T1 baseline also had zero such headings; the improvement is not a fabricated reduction in that metric, but making hidden meaningful discussion explicit without inventing a generic Topic. The counts convey display capacity, not a new semantic classification.

### Visual QA and Human gate

**Visual QA pending.** Local-file rendering through the available browser tool was policy-blocked during the prior Spike; this iteration does not circumvent that restriction or claim new screenshots. The artifact targets 1920×1080, but pixel-level overflow/wrapping/alignment and physical 3–5m readability are not certified. The HTML performs a local element-dimension warning when Human opens it; even “no scroll-size overflow” is not a substitute for visual review. Current/previous comparison views are simplified selection-faithful mocks, not pixel-perfect production captures.

Human coverage and Explanation Cost remain blank, with short-reason fields. The review should check current-discussion coverage, whether `ほかN件` implies an unwanted action, whether the count is read as display overflow rather than “miscellaneous,” candidate/confirmed distinction, rail density, calmness and distance readability. Inputs are not sent anywhere or silently persisted. Existing assistant provisional scores from the previous Spike are not promoted to Human acceptance.

**Next, only after Human approval:** Production Shared View minimal implementation → saved-T1 replay → visual QA → T2 readiness review. None of that implementation is performed in this task. **T2: NOT READY — pending Human Review.** No T1 audio rerun, T2/T3 execution, tag, release or Live Pilot.

### Human feedback follow-up — explicit persistent-state headings

Human accepted the ordinary discussion direction but found the persistent-state distinctions less understandable. This offline revision changes only the Rail grouping/wording and its spacing, retaining six-card Stable Recency, overflow arithmetic and minimal chrome.

The Rail now separates **決定候補 / 確定事項 / 未解決事項 / 次の対応**. Candidate and confirmed Decision are selected into independent presentation groups using their existing canonical status, not combined under one heading with only a small badge. A candidate never becomes confirmed through this grouping. Each nonempty group shows one item with its own overflow count; maximum visible Rail items increases from three to four. No empty groups are added to T1.

The nine-item synthetic example now shows all four headings concurrently: candidate 1, confirmed 2, unresolved 3, actions 3. It displays one per group, with overflow respectively 0 / 1 / 2 / 2. Headings are stronger (28px), item text remains 30px, and redundant final-Rail status badges/empty overflow spacers are removed to accommodate four groups without shrinking text. Color is supplementary; text headings carry the distinction.

The review entry opens on this synthetic example so the changed distinction can be evaluated immediately. T1 5/10/15 comparisons remain available. All 17 grouped offline checks, including independent candidate/confirmed membership and lifecycle filtering, pass. Six ordinary-card IDs/slots, ages, counts and T1 churn remain unchanged. JavaScript syntax and generated-data invariants were checked; pixel-level Visual QA and distance readability remain pending.

Production remains unchanged; no audio or Analyzer rerun. This is a revised Human Review candidate, not final adoption. T2 remains NOT READY pending Human Review.

## Approved Shared View implementation

Human approved the revised four-heading Rail and authorized implementation, including the existing top Topic-flow concept. The earlier Spike conclusions and review history above are preserved; their “not yet implemented” statements describe those earlier stages.

### Local implementation

- `prototype/shared_projection.py` adds a presentation-only six-slot selector and four independent rail groups: candidate Decision, confirmed Decision, unresolved Open Item and active Action. Ordinary recency and overflow follow the approved candidate; rail items do not consume ordinary slots.
- `layout.map_projection` exposes an additive `shared` presentation field for complete runtime snapshots. Existing graph-only compaction callers retain their original contract. Canonical Events, schema, materializer behavior, Graph, Analyzer and STT are unchanged.
- A private projection cache replays skipped accepted Events to reconstruct slot placement. Normal appends process only new Events; session/history changes reset it. Fresh and incremental clients produce the same projection. Canonical input is copied, not modified; no provider calls occur.
- `shared.html` renders fixed ordinary slots, independent **決定候補 / 確定事項 / 未解決事項 / 次の対応**, non-interactive per-area overflow, large meaning-first text and minimal active chrome. Empty Rails disappear. Idle retains an explicit `/session` entry; End retains the final map and says the meeting ended. A fetch failure reports connection checking without deliberately blanking the last displayed map.
- The upper flow uses only existing canonical `topic_focus_changed` / `set_current_topic` history. It is shown for meaningful multi-Topic movement, includes returns, and limits the visible strip to the latest four entries. Only the last matching current occurrence is highlighted. Generic Topic headings are omitted; a single broad Topic does not get fabricated subthemes or pagination.

### Verification and remaining gate

The actual Product projection was replayed against the saved T1 Graph at revisions **32 / 57 / 72**. Card IDs and slots match the approved Stable Recency output, with overflow **9 / 23 / 31**. Independent fresh-layout and incremental-layout projections match. Saved input is unchanged; no audio/STT/Analyzer rerun took place.

Focused tests cover stable slots, exact overflow, candidate/confirmed separation, lifecycle filtering, renewed node activity versus Topic focus, immutable deterministic fixture replay/reset, and actual Topic return. A Node.js DOM-logic smoke covers escaping, four-heading rendering, true-flow return highlighting, single-Topic suppression, Idle entry, active state and retained End content. This is a logic test, not a real browser/CSS rendering claim.

Full regression result: **174 tests discovered, 153 passed, 21 existing-policy skips**. `git diff --check` passed.

Private offline HTML snapshots now use the **implemented Product HTML**, not the earlier mock. They substitute only a saved graph/map response and disable polling; they make no network/provider requests. The entry links 5/10/15-minute views and identifies their status indicators as frozen illustrations.

Visual QA at 1920×1080 and physical 3–5m readability remain pending; the previous local-file browser policy restriction was not bypassed. Multi-Topic strip width and four simultaneous Rail sections should be included in that visual check. Human direction is approved, but **T2 remains NOT READY pending implemented-view visual QA and the T2 readiness review**. No deployment, commit/push, release/tag, T2/T3 or Live Pilot was performed in this implementation task.

## Final Shared View Visual QA — 1920×1080

**Decision: A. VISUAL QA READY — HUMAN DISTANCE REVIEW.** This closes the local pixel/layout check, not the physical 3–5m readability gate. Prior T1 quality findings remain unchanged.

### Actual browser rendering

The existing Product HTTP handler and Shared View were served on loopback with an allowlist of immutable saved graph/map snapshots. No live audio manager, provider calls, arbitrary file-serving endpoint or writable session operations were enabled. Seven actual browser screenshots were captured using existing bundled Playwright/Chromium **151.0.7922.34**, viewport **1920×1080**, device scale factor **1**: T1 5/10/15 minutes, synthetic persistent-state counts 1/3/9, and the dense fixture combined with the existing Topic-return fixture. The last is explicitly a synthetic visual composition, not T1 evidence.

The initial in-app browser screenshot surface returned incorrectly sized/cropped images despite the requested viewport; those captures were excluded. Accepted screenshots have verified PNG dimensions of 1920×1080. Private screenshots and detailed measurement JSON are not part of public packaging.

### One minimal CSS iteration

Initial actual renders exposed a small overflow-count line-box mismatch, an isolated last character in a Rail label, and a current-Topic underline that could resemble tab navigation. A single CSS-only iteration increased the active overflow line height allocation from 32 to 38px, balanced Rail text wrapping, and removed the active Topic underline. No labels, card selection, slots, capacities, lifecycle semantics or canonical data were changed. Card body text remains **40px**, Rail body **30px**, Rail headings **28px**.

All seven states were re-rendered after the iteration. Document size equals viewport; measured text/element bounds show no overflow, card overlap or scrolling. Visual inspection found no text collisions. Ordinary cards retain their two-column, three-row layout. Branding and usage guidance are hidden, generic semantic buckets are absent, counts are secondary non-interactive text, and the flow consists of passive labels/arrows rather than controls. Empty Rail categories consume no section space. The saved-fixture status reads “更新しました”; these captures do not certify a live microphone/listening indicator.

### Temporal comparison and provisional readability

| Saved state | Broad visible discussion | Ordinary cards / overflow | Provisional glance heuristic |
|---|---|---|---|
| 5 min | Transport, MaaS, organizational cooperation | 6 / 9 | B — Quick, approximately five seconds |
| 10 min | Festivals, cultural continuity, resident participation | 6 / 23 | B — Quick, approximately five seconds |
| 15 min | Regional cooperation, transport return, summary | 6 / 31 | C — Requires reading, over five seconds for longer abstract labels |

These are assistant provisional judgments, not measured human comprehension times. Later content is visibly different while layout remains stable. Some long labels, particularly at 15 minutes, remain a content-label quality concern; canonical labels were not rewritten or text shrunk for fit.

The dense synthetic fixture has nine ordinary items and nine persistent items: candidate 1, confirmed 2, unresolved 3, actions 3. It shows six ordinary cards with overflow 3, and one per persistent category with overflow 0/1/2/2. Four Rail sections remain within the viewport, secondary but readable at pixel inspection. This tests bounded visible density, not whether all hidden state can be understood at a glance. Actual distance readability of the narrower Rail remains a Human check.

### Regression and replay

Full suite: **174 discovered, 153 PASS, 21 existing-policy skips**. Saved T1 replay again matches approved selected IDs/slots and overflow at revisions **32/57/72**, with counts **9/23/31**. Fresh and incremental projection agree and input remains immutable. Before/after CSS render labels and counts are unchanged. No STT, Analyzer or T1 audio was rerun.

### Human review handoff

A private single-entry HTML gallery includes original 1920×1080 images, side-by-side 5/10/15 comparison, dense Rail/Topic-return example and smaller persistent fixtures. The comparison thumbnails are for progression only; distance review requires each original image filling the intended meeting-room display. Record display size, resolution/scaling and distance alongside answers:

1. 3mからカード本文を読めるか。
2. 5mから「今の議論」が分かるか。
3. 5/10/15分で議論の変化を感じるか。
4. 「ほかN件」を自然に理解できるか。
5. Railが邪魔にならないか。
6. 操作が必要そうに見えないか。

**Physical 3–5m review is pending. T2 remains NOT READY pending Human distance review and subsequent readiness review.** After approval only: candidate packaging → digest deployment → saved-T1/shared smoke → T2 readiness review. No deployment, commit/push, tag/release or Pilot was performed here.

### Human visual feedback — Rail wrapping and Topic-flow size

Human flagged the confirmed-state label's wrap and small Topic-flow text. The prior balanced wrap separated a modifier from its noun. This presentation-only follow-up removes forced balanced wrapping, gives the Rail 460px instead of 420px, and retains its 30px body. The synthetic confirmed label now fits on one line without modifying canonical text. Ordinary cards alongside a Rail use 14px horizontal padding rather than 24px to preserve readable text width; their 40px font is unchanged. No-Rail T1 layout is unchanged.

Active Topic names increase from 24px to 32px, with the flow band increased from 52px to 64px. Current-topic highlighting remains bold rather than a tab underline. The small structural caption stays secondary. All seven fixtures were re-rendered at 1920×1080 without measured overflow or scroll; the dense Topic-return image was visually checked. Labels, selected cards and overflow are unchanged. The private gallery preserves the prior captures and links a revised entry. Physical distance review is still pending; no deployment or semantic change is included.

### Approved flow order — current at the left edge

Human approved presenting the latest/current Topic first, followed by older transitions to its right. Shared View now reverses a copy of the latest four display entries and uses left-pointing arrows. Only the leftmost current occurrence is emphasized; returning to an earlier Topic does not highlight its older occurrence. Canonical focus and chronological history remain unchanged, as do ordinary cards and Persistent Rails. Single-Topic flow remains hidden.

DOM regression now asserts current-left highlighting, left arrows, reverse order with a non-palindromic history, the four-entry limit and input-history immutability. Seven 1920×1080 renders remain free of measured overflow/scroll; the actual Topic-return screenshot shows the new order without navigation controls. Private review captures are retained separately from prior versions. Physical distance review and T2 readiness remain pending; no deployment or audio rerun occurred.

### Participant reference numbers — fixed display slots

**Superseded / withdrawn:** The following records the temporary prototype, not the current candidate. See the deferral decision below.

Human clarified that numbering is for pointing to a card during discussion, not chronology. The six ordinary display slots now carry static row-major references **①② / ③④ / ⑤⑥**, shown in the upper-left corner at 28px while semantic labels remain 40px. Numbers identify positions, not permanent canonical nodes, importance or utterance sequence. A replaced card inherits its slot's number; an empty slot has no visible number. Persistent Rails and overflow are not numbered or made interactive.

Rendering changes only; selection, canonical labels and recency remain unchanged. DOM tests cover all six numbers and sparse slots (the second slot stays ② even if the first is empty). Seven actual 1920×1080 captures report no overflow, scrolling or number/body collisions. The dense Rail/flow and long-label 15-minute images were visually inspected. Captures remain private; physical-distance review remains pending. No deployment or T1 rerun.

### Reference numbering deferred to RFC

Human identified that “the earlier number 6” becomes ambiguous when a numbered slot receives a different card. Item-stable numbering would avoid reuse, but the requested recall of a hidden item from spoken references is not supported by the current pipeline. Human therefore deferred this feature to [RFC-0006](../rfc/0006-discussion-item-references-and-recall.md).

The temporary slot-number markup/styles were removed; ordinary cards are again unnumbered. Current-left Topic flow, larger typography, Rail wrapping improvements and all projection semantics are retained. Tests now assert absence of reference-number markup, including sparse slots. Numbered screenshots are historical prototypes, not the current review candidate. No reference resolver or recall behavior was implemented, and no deployment or audio rerun occurred.

### Human approval and deployment preflight

Human explicitly approved the current **unnumbered** Shared View for deployment. This approves the presentation direction and candidate; it does not assert that a physical 3–5m distance test was performed. That measurement remains unverified. RFC-0006 stays deferred, with no reference numbering or spoken recall implementation.

The existing container-publish workflow was verified: manual dispatch accepts a source ref, uses the existing GitHub identity with package-write permission, and publishes an immutable image digest. Deployment preflight then failed because the configured cluster access was rejected as unauthenticated. Current deployment identity and rollback state could not be verified, so rollout is blocked pending restoration of authorized cluster access. No credential changes, branch push, workflow dispatch, image publish or rollout were performed in this attempt; the running deployment was not modified. T2 and release/Pilot work remain unstarted.

### Approved unnumbered candidate deployed

Human supplied an authorized kubeconfig and access was restored for this task without changing the default credentials. The prior running image was recorded for rollback and the live session was verified ended before replacement.

Public candidate branch `shared-view-rc1`, commit `b14714a8ce7550b43574b7090ab98b80022642c6`, includes only the approved implementation, related tests, acceptance note and deferred RFC. The accumulated evaluation history and local tooling remain outside that candidate commit; private media, screenshots and runtime metadata were not published. Full regression: **153 PASS / 21 existing-policy skips**. Saved T1 replay still matches revisions 32/57/72 and overflow 9/23/31, without source/audio/Analyzer reruns.

Existing CI [run 35815339241](https://github.com/hakobune8/ronro/actions/runs/35815339241) successfully published `ghcr.io/hakobune8/ronro:shared-view-rc1`, digest `sha256:8c1c0e0bb89796191107974450e13968142f6fbddd8e390c1624a69bddecdf1e`. The Deployment and running container use this digest. Pod Ready 1/1, restart count 0; Service endpoint ready and PVC Bound. All six HTTP checks (`/healthz`, `/readyz`, `/`, `/shared`, `/control`, `/session`) returned 200. HTTPS certificate verification and WSS handshake succeeded; the WSS smoke intentionally received the no-session response without connecting a provider.

Pre/post comparison confirms only the Deployment image changed: other Deployment specification fields, Service, PVC, Ingress and ConfigMap match. The explicit generic STT context, sole keyword `論路`, and `server_vad_bounded` / 30s baseline remain active. The network topology was not altered; no external boundary-bypass test was performed.

Deployed Shared HTML and both Python implementation files match committed source byte-for-byte. Live Idle and existing synthetic basic/Topic-return cases were rendered in Chromium at 1920×1080 with no browser errors or document overflow. Synthetic API projections match the local candidate. Current-left flow and absent numbering are confirmed; the synthetic Topic-return fixture intentionally has no ordinary cards. No real meeting was started; runtime remains idle. The previous image rollback command and cluster-specific observations are saved privately.

**Deployment complete; Human visual direction approved.** Physical 3–5m measurement remains unverified, RFC-0006 is still deferred, and T2/T3, Live Pilot, main merge, final tag and GitHub Release were not performed. This result does not turn the earlier T1 quality decision into a new audio-evaluation PASS.

## T2 — Infrastructure Practice Evaluation

### Phase 0: distance acceptance — Human-reported PASS

The requested frozen baseline is `shared-view-rc1`, commit
`b14714a8ce7550b43574b7090ab98b80022642c6`. Read-only preflight confirms
the Deployment still references the published candidate digest
`sha256:8c1c0e0bb89796191107974450e13968142f6fbddd8e390c1624a69bddecdf1e`
and is Ready 1/1. No product or runtime configuration was changed.

**Distance gate: PASS (Human-reported).** Human answered “PASS” to the
3m/5m active-display acceptance question. Display size, actual resolution and
individual criterion notes were not supplied; these remain unspecified, not
assistant-measured results. This closes the requested Human gate without a
further presentation iteration.

Verified event source: MLIT Kyushu Regional Development Bureau, Infrastructure Maintenance
Kyushu Forum 2025, Part 3 panel “連携と実行～群マネに挑む挑戦者たち～”.
Official page: https://www.qsr.mlit.go.jp/useful/n-shiryo/kikaku/infrastructure_maintenance_r7.html

### Phase 1: official program and playback availability

The [official program](https://www.qsr.mlit.go.jp/content/900014516.pdf)
dates the event to 2025-10-08 and schedules Part 3 for 15:55–17:25 (90 minutes).
This is a program schedule, not verified recording timecodes. Facilitator:
福島邦治. Panelists: 岩舘慶多, 平井武志, 児玉広文 and 木下義昭.
The [official results](https://www.qsr.mlit.go.jp/content/900014517.pdf)
describe an opening AI video and discussion of municipal and technical
collaboration. Internal presentation/exchange timing cannot be established
from these documents alone.

The official page's linked [YouTube video](https://www.youtube.com/watch?v=X6zfzHltRWA),
“【インフラメンテナンス】みんなで”つなぐ”インフラの未来！”, was inspected
in Safari's normal official player. The visible player showed **0:15 / 1:16**
and the official regional bureau channel. This is a short introduction, not
the 90-minute panel archive. It cannot supply a continuous 30-minute interval.
Official page/program/results and focused official-source searches have not
established a full panel playback URL. This does not prove that no archive
exists elsewhere.

### Phase 2: T2 SEGMENT SELECTION — HUMAN INPUT REQUIRED

No interval is selected or guessed. An official full-panel archive URL is
needed before representative segment inspection can continue. Source
replacement is not authorized automatically. The brief source-player inspection
did not start a RONRO provenance session, audio capture or T2 run; no media was
downloaded, extracted or saved. No workload A–E outcome or review score is
assigned to this pre-run source-availability blocker.

Next: obtain/verify the official full-panel URL → freeze a representative
continuous 30-minute interval → Safari playback/Chrome capture provenance
gate → fresh-session T2. Product baseline remains frozen. T1 evidence is
preserved; RFC-0006 remains deferred. T2/T3, Pilot and release work have not run.

### Replacement T2 source selection — provisional recommendation

Original T2: **SOURCE UNAVAILABLE for the requested 30-minute workload**;
the verified 1:16 introduction is excluded. On 2026-09-23 the replacement
inspection used normal Safari official playback only, without RONRO capture,
STT, transcript export, media download or extraction.

Recommended source: 令和6年度国総研講演会, Part 3 panel II,
“インフラ地震防災対策の取組と能登半島地震での知見を踏まえた今後の対応”.
Publisher/organizer: 国土交通省 国土技術政策総合研究所; event date 2024-12-12.
[Official program](https://www.nilim.go.jp/lab/bbg/koen2024-1.html)
directly links the [official video](https://www.youtube.com/watch?v=Y5dHlc8WgL8).
Actual Safari player duration: approximately **01:31:10** (initial AX rounded
to 01:31:11), distinct from the scheduled 85-minute program. The NILIM video
index fetch failed, but provenance is established by the working event page.

Coordinator 宮武晃司 and five panelists represent river, sediment disaster,
road structures, port-related management and airport expertise. These are
government technical experts, not a confirmed mix of municipal officials and
consultants. Technical target-user fit is strong; organizational diversity is
more limited than the originally intended T2.

| Candidate | Official video | Duration evidence | Interaction / feasibility |
| --- | --- | --- | --- |
| NILIM 2024 panel II, infrastructure earthquake response | Y5dHlc8WgL8, linked above | Player approximately 91:10 | Multiple technical speakers observed; substantial slide-led explanations; 30-minute capacity verified, interaction sufficiency pending Human review |
| NILIM 2024 panel I, 住まい・まちの地震災害対策の取組 | https://www.youtube.com/watch?v=vzvSgctSzf4 | Official schedule 75 minutes; actual video duration not inspected | Officially linked alternative with building/housing/urban experts; interaction and 30-minute segment not verified; not selected |

Inspection was sparse normal-player sampling, not full transcript annotation
or continuous viewing of the proposed interval. Observed anchors: about 45:09
port restoration technical support; 52:23 road-network damage; 57:07 road
technical standards and lessons; 60:12 sediment-disaster survey; 75:14 dam
management and future technical directions; 80:00 port-facility rapid reuse;
85-minute vicinity satellite observation; 87:53 coordinator-style request for
later comments. At least three distinct technical speakers are visible in the
proposed range. Returning to earlier slides is observable, but does not by
itself prove conversational Topic Return or replies to previous speakers.

| Proposed interval (not frozen) | Assessment |
| --- | --- |
| 00:45:00–01:15:00 | Includes a longer restoration/presentation portion; less attractive for practical future-response movement |
| **00:57:00–01:27:00** | Sole recommendation for Human review: road lessons through several technical fields and future responses; avoids the final approximately four minutes; begins within an explanation, not a verified turn boundary |
| 01:00:00–01:30:00 | Later start loses road-context material and increases closing/summary risk; not recommended |

These are exact 30-minute proposed windows based on sampled anchors, not
verified chapter boundaries. Interaction density and complete start/end
content are **not yet certified**. The source is presentation-heavy enough
that it must not be described as a verified 30-minute free exchange. Human
review should decide whether this moderated expert-explanation format meets
T2's discussion criterion before freezing source and interval.

Decision: **B. CANDIDATE FOUND — HUMAN REVIEW REQUIRED**. No provenance or
evaluation session was started. Normal Safari playback was available;
Safari → BlackHole → Chrome remains the proposed ingestion route, not a
newly passed audio gate. Long uninterrupted playback is not established by
this short inspection. No redistribution rights are inferred.

If approved, the previously planned T3 NILIM source becomes T2. Future T3
should emphasize actual decision-making with disagreement and repeated Topic
Return rather than merely greater technical vocabulary; no T3 source is
selected here. Frozen product `shared-view-rc1 / b14714a` is unchanged.

## T2 — NILIM Infrastructure Earthquake Panel

### Final segment gate

Human approved the explanation-heavy technical-panel format and subsequently
answered “確認okです” to the request to review the complete 00:57:00–01:27:00
interval for multiple substantive speakers and technical development rather
than a single uninterrupted lecture. This is **Human-reported full-interval
acceptance**, not an assistant claim to have listened to the entire recording.
Decision **A. FREEZE 00:57:00–01:27:00**, exactly 1,800 seconds, before any
RONRO output from the source is inspected. Source and official links are as
recorded in the replacement recommendation above.

Read-only preflight confirms the deployed candidate digest remains unchanged,
Ready 1/1, with `server_vad_bounded`, 30-second bound, `gpt-transcribe`, sole
keyword `論路`, and a prompt matching the generic default. Chrome's old ended
T1 display was refreshed before provenance preparation; backend was idle.
No product/configuration changes or evaluation results are implied by this
preflight. Provenance must PASS before the separate T2 run.

### Provenance gate — PASS (2026-09-23)

Normal official Safari playback → BlackHole → Chrome capture was used, with
one actual BlackHole audio track (48 kHz, mono) and a fresh live session.
Evidence, utterances, queue and graph nodes were empty before playback.
The non-evaluation source window was approximately 00:40:00–00:42:45,
including a pause. No source media was downloaded, extracted or recorded.

Pre-resample RMS was 0 while paused, approximately 0.073–0.081 while playing,
0 during a 44.6-second pause, and 0.083 after resume. Three consecutive
substantive Finals matched visible source captions/context about survey-team
dispatch, vehicles/team leaders, and tsunami survey activity. An initial
fragment was not counted toward the three-Final criterion. New meaningful
Finals stopped during the pause after buffered completion and resumed with
playback. No reset, demo-theme or cross-session contamination was observed.
Each accepted Final retained audio/frame/provider/Evidence correlation.

The provenance-only session ended cleanly: 9 Finals, 741 partials, 9 retained
Evidence items, pending/processing/failed = 0/0/0, graph/render = 20/20.
One place-name error was amplified into a monetary expression; this was a
lexical/semantic observation, not a keyword-tuning intervention or a T2-run
result. The provenance session was not reused for T2.

### T2 run 1 — stopped; not a completed 30-minute evaluation

Frozen baseline: `shared-view-rc1`,
`b14714a8ce7550b43574b7090ab98b80022642c6`, unchanged digest
`sha256:8c1c0e0bb89796191107974450e13968142f6fbddd8e390c1624a69bddecdf1e`.
The generic Japanese STT context, keyword `論路`, `server_vad_bounded` and
30-second fallback remained fixed. No product, deployment or tuning changes.

A new session began with Evidence/utterance/queue/node counts zero. Safari
was paused at the displayed 00:57:00 before capture, then played at 1×.
First non-silent capture was observed at 04:45:19.465 UTC. Capture included
approximately 34 seconds of pre-playback silence. Browser PCM represented
401.5 seconds total (9,636,000 PCM16 samples at 24 kHz), including that silence;
the source-content portion was only approximately **6 minutes 7 seconds**,
not 30 minutes. Aggregate pre-resample RMS was 0.0936. Browser/backend clocks
were not calibrated; a frame-exact terminal source time is not claimed.

The runtime stopped itself with **`empty_final_transcript`** and
**`ended_with_incomplete_processing`**. Its last audio timestamp was
04:51:26.684 UTC. The observer detected the ended state, and Safari was then
paused at 01:04:10.436; this later Player position is **not** the captured
evaluation endpoint. Chrome capture was inactive/disconnected and evaluation
timers were removed. No retry was performed.

Player metadata monitoring from approximately 01:00:26 until manual stop
contained 1,116 samples: no unexpected pause, unready state, backward reset,
mute or playback-rate change. Earlier progress was checked through the UI.
Thus the observed stop was in STT/finalization handling, not an observed
official-Player lifecycle failure.

### Partial-run measurements (not 10/20/30-minute results)

| Measurement | Value at interruption |
| --- | --- |
| Finals / partials | 18 / 1,697 |
| STT failures | 1 (`empty_final_transcript`) |
| Ignored-empty counter | 0; this counter does not count the fatal empty event |
| Recorded Final boundary reasons | bounded_fallback 7; server_vad 1; raw `speech_started` 10 |
| Session-end Final | 0 |
| Max unfinalized audio / remaining buffer | 37.5 s / 30.7 s |
| Topics / nodes / relations | 1 / 12 / 11 (nodes include Topic) |
| Candidate / confirmed Decision / Action | 0 / 0 / 0 |
| Open Item | 1 |
| Nodes / Final; max created nodes / Final | 0.67; 2 |
| Analyzer calls / failures | 18 / 0 |
| Queue max depth; pending / processing / failed | 2; 0 / 0 / 0 |
| Graph / render revision | 26 / 26 |
| Visible discussion / eligible / overflow | 6 / 10 / 4 |

The raw `speech_started` boundary value is preserved as an observability
limitation, not silently relabeled as a completed server-VAD boundary.
Ten graph-changing queue items and eight graph-unchanged items were observed.

| Latency, seconds | p50 | p95 | max |
| --- | ---: | ---: | ---: |
| Queue wait | 0.0013 | 2.576 | 2.576 |
| Analyzer | 3.300 | 5.556 | 5.556 |
| All-item E2E | 6.514 | 39.461 | 39.461 |
| Graph-changing E2E | 6.250 | 7.720 | 7.720 |
| Graph-unchanged E2E | 31.229 | 39.461 | 39.461 |

True speech-end-to-STT-completion latency and token/cost totals are unavailable
from the retained metadata. In particular, the short interval between stored
`audio_end_at` and queue enqueue is not certified as STT recognition latency.

### Safety, Shared View and failure interpretation

All 18 generated Evidence items remain present; all 18 queue items completed.
No duplicate provider item, cross-session node, dangling graph edge,
automatic confirmation, invented Owner/Due or queue failure was found.
However, meaningful pending audio remained at failure. **End-to-end Evidence
loss = 0 is not established for that unfinalized audio.** Queue emptiness and
matching render revision do not make this a clean Drain.

The saved implementation treats automatic VAD empties differently from an
empty completion while an explicit commit is pending. The observed failure
is consistent with the latter path during active capture; it is not a benign
session-end empty. The exact failed provider item/commit and why its content
was empty are not established by the retained backend snapshot. Do not claim
a proven commit race or weaken Drain safety on this evidence alone.

Before interruption, recent sediment-disaster content displaced road-related
cards; the T1 first-six insertion-order staleness did not persist in this short
observation. One Open Item remained in its separate rail. At interruption,
transient-card age was approximately median 80 s / max 192 s. The 3-second
observer saw at least three replacements (approximately 0.49/min) and zero
remaining-card slot movement; these are sampled lower-bound churn metrics,
not an exact event-replay total. One broad Topic and no Topic return were
observed; a full cross-domain Topic-flow assessment was not reached.

A private actual 1920×1080 screenshot was captured at interruption. It shows
long technical labels crowding/overflowing one card vertically. This is a
follow-up presentation/content-density observation, not a mid-run CSS fix.
Overflow remained a secondary `ほか4件` indicator, not a generic semantic bucket.
The unresolved item is a technical preparedness question; whether it merits
persistent Open Item status needs later source-grounded review.

The run ended before the first primary snapshot. **10/20/30-minute screenshots,
Q1–Q6 scores, and a full-run Human/Provisional quality review are not available.**
No substitute scores or reconstructed full-run snapshots are fabricated.
Detailed diagnostic metadata and the interruption screenshot remain private;
no audio, video or complete transcript is added to public Git.

### Decision and next gate

**D. T2 PIPELINE FAILURE.** The frozen segment remains 00:57:00–01:27:00;
this aborted attempt is preserved separately and must not be called a
successful 30-minute run. Next work should correlate the fatal empty provider
completion with its VAD/explicit-commit state before a same-baseline retry.
No product repair or retry was performed in this evaluation task.

RFC-0006: **wait**; this incomplete run is insufficient to finalize it.
T3 is not started; a future workload could stress actual decision-making,
disagreement and repeated Topic Return after T2 succeeds. No Live Pilot,
formal tag, release or deployment was performed.

## T2 Empty Final / VAD-Bounded Diagnostic

### Scope and evidence quality

This follow-up preserves the aborted T2 result and all original artifacts.
No T2 retry, source playback, Provider/Analyzer call, deployment, or product
behavior change was performed. The deployed `live_stt`, `live_transport` and
`live_continuous` file hashes match the inspected local candidate files.
Private 3-second snapshots, Final traces and queue metadata were examined.
Available Pod logs contain no matching raw VAD/commit/error event trace.
The evaluation exporter saves snapshots/metrics, not a complete Provider
event journal. The failing item's ID and commit acknowledgement cannot be
recovered from these snapshots; successful-item IDs remain available privately.

**Incident root-cause category: F. Unknown. Decision: B. MORE INSTRUMENTATION
REQUIRED.** Concrete state-accounting defects/risks are demonstrated below,
but none is asserted to be the proven cause of this particular empty result.

### Exact observable failure window

Times below use the backend timestamp axis, not the observer computer clock.
The observer clock differs by several seconds, so cross-machine timestamps
must not be subtracted as if synchronized. Frame indices are application
receive ranges, **not proven Provider item audio boundaries**.

| Backend time (UTC) | Observable transition | Local pending | Provider state |
| --- | --- | ---: | --- |
| 04:49:54.978 | Successful Final #12, local commit counter 7, recorded `bounded_fallback`; frames 2783–3096 | 31.4 s receive window, then reset | Item/event IDs retained; committed acknowledgement and VAD event order not retained |
| 04:50:54.743 | Final #17, frames 3547–3693, counter still 7 | Reset on arrival | Recorded `speech_started` is latest global state, not an item-specific completion reason |
| 04:50:55.974 | Last successful Final #18; frames 3694–3706, recorded `server_vad`, counter 7 | Reset on arrival | Item/event IDs retained; raw start/stop/committed sequence unknown |
| 04:50:57.061 | Frame 3717; Finals 18; partials 1634 | 1.1 s; meaningful=true | Unknown |
| 04:51:13.059 | Frame 3877; Finals unchanged | 17.1 s; meaningful=true | Unknown |
| 04:51:25.860 | Frame 4005; Finals 18; partials 1634 | 29.9 s; meaningful=true | Unknown |
| 04:51:26.684 | Last accepted frame 4013; subsequent snapshot shows partials 1697 and fatal empty completion | 30.7 s; meaningful=true | Empty completed item and its exact commit correlation not retained |
| After failure | `mark_provider_failure` → finalizing → drained queue → `ended_with_incomplete_processing` | Not successfully resolved | No successful Final #19 |

The final receive range after #18 is 3707–4013 inclusive: 307 × 100 ms =
30.7 seconds of local PCM. Continuous append is the normal code path, but
per-frame Provider acceptance has no retained acknowledgement. Partials
increased by **63** in the terminal sampling interval. Those deltas' item IDs
were not persisted; they cannot be assigned to the empty completed item.

The local duration **did reset after #18**. The evidence does not support
"the timer never resets" or an entirely silent/disconnected terminal window.
Non-silent local signal still does not prove recognizable speech in the
particular Provider item that completed empty.

### What the error does and does not establish

`empty_final_transcript` / `Provider completed a turn without transcript text`
is an **application-generated classification**, emitted by
`adapt_realtime_event` for `conversation.item.input_audio_transcription.completed`
whose transcript is missing, non-string or whitespace/empty. It is not the
Provider rejection code `input_audio_buffer_commit_empty`.

The deployed VAD transport ignores such empties only when its global
`commit_pending` flag is false. Its fatal path therefore establishes, by code
inference, that an explicit commit was pending when this empty completion was
handled. Since this occurred during active capture without a user stop/commit,
a bounded fallback is the supported local explanation. Its exact send time,
sequence number and acknowledgement are absent; do not invent "commit #8".

This establishes **empty transcription completion while explicit commit was
pending**, not that the empty item necessarily belongs to that commit.
The strict requested A/B/C distinction is consequently **C: exact sequence
unresolved**, with a B-like empty-completion event observed. A Provider
empty-buffer rejection is not the recorded terminal error. Raw Provider
error type/code/message for this incident are unavailable; the quoted message
is RONRO's own text, not a verbatim Provider error payload.

### Successful comparison

| Property | T2 successful Final #12 | Terminal failure |
| --- | --- | --- |
| Local receive window | 278.3–309.7 s / 31.4 s | 370.7–401.4 s / 30.7 s |
| Recorded counter/reason | 7 / bounded_fallback | Not retained for failed item |
| Transcript result | Non-empty Final, Evidence retained | Empty completed event, no new Evidence |
| Local reset | Entire current buffer cleared on Final receipt | No successful-Final reset; forced incomplete |
| VAD active/stop/pending-item state | Not retained; active=true/pending-count=0 required at fallback decision by code | Same guard required if fallback sent; actual remote state unknown |
| Provider committed acknowledgement | Not retained | Not retained |

Earlier Condition B remains a successful aggregate reference (117.2 s,
3 fallbacks plus 1 session-end Final, ended). Its reported totals do not
establish an event-level difference from this failure. The same-run #12 is
the stronger available comparison and still lacks the crucial raw ordering.

### State ownership and demonstrated synchronization risks

RONRO owns received PCM duration, the sticky non-silent flag, local commit
intent/counter, and Evidence creation. Provider owns its VAD segmentation,
buffer consumption and transcription item lifecycle. The current adapter
maintains a **parallel approximation** using one active-speech boolean, one
pending-completion integer and one latest-boundary reason.

Seven isolated, offline characterization checks against the unchanged classes
passed. Their provider messages/IDs are synthetic; these are **not a replay
of the actual T2 Provider event order** and make no recognition claim:

1. `input_audio_buffer.committed` is counted but adapted to `ignored`; it
   neither records an item ledger nor reconciles the active-speech flag.
2. A completion for item A decrements a pending count created by item B.
3. A duplicate completed item also decrements that count before duplicate
   handling, although duplicate Final Evidence is suppressed.
4. A new item's `speech_started` overwrites the reason later attached to an
   older item's Final. This explains why `speech_started` is not a reliable
   completed-boundary category; the T2 count 10 is not a VAD-boundary count.
5. An empty item A while another explicit commit is pending is classified
   fatal by the same global flag; no item ownership test distinguishes it.
6. Empty completed events and empty-buffer rejection events map to distinct
   codes, confirming the terminal-error distinction above.
7. A late Final for an earlier region clears **all** locally accumulated PCM.
   A synthetic 32-second receive buffer with an old 10-second item completion
   becomes zero; the trace claims audio_end=32. Later still-unfinalized audio
   is not separately retained in local pending accounting.

The transport also clears global `commit_pending` on **any** non-empty Final,
not only the item associated with the explicit commit. Its reader updates
adapter state before queued events are processed, and Final diagnostics sample
the latest mutable context again. These are real correlation/accounting risks,
not proof that a particular VAD/fallback race occurred in T2.

| Hypothesis | Assessment |
| --- | --- |
| A: explicit commit during active Provider speech | Local active=true is required by the guard; actual Provider state/item at send is unknown |
| B: Provider already consumed buffer | Plausible because committed events are not reconciled; not established for T2 |
| C: local pending differs from Provider state | Demonstrated architectural mismatch; #18 reset itself worked, but it resets at receipt rather than item boundary |
| D: VAD/fallback race | Feasible with global flags and queued events; exact incident ordering missing |
| E: valid committed speech recognized as empty | Possible; 63 deltas were observed but their item association is missing |

### Provider semantics and conditional fix design

Official [Realtime transcription documentation](https://developers.openai.com/api/docs/guides/realtime-transcription)
states that completion ordering across turns is not guaranteed and requires
item-ID reconciliation. [VAD documentation](https://developers.openai.com/api/docs/guides/realtime-vad)
distinguishes speech start/stop events from transcription processing. A newer
model's client-only example must not be substituted for this frozen
`gpt-transcribe` setup. No model/VAD-threshold/timeout tuning is proposed.

The smallest **candidate design**, pending incident-level correlation, is an
item-scoped Provider/transport ledger rather than additional global booleans:

- Separate **uncommitted input** from **committed items awaiting completion**.
  Track sample/frame watermarks and item ownership; a local non-silent flag
  is not a Provider buffer acknowledgement.
- `speech_started`: arm the current speech region; do not clear older items.
- `speech_stopped`: close the indicated speech region and await its committed
  item/completion; do not manufacture Evidence or erase following audio.
- Successful commit **send**: mark an intent in flight, not successful
  transcription. `committed` acknowledgement: correlate the actual item and
  transfer only its covered region to pending completion. Retain newer frames.
  Do not assume the Provider echoes a local commit identifier if it does not.
- `transcription.completed`: reconcile only that item, suppress duplicate
  completion before modifying counters, and release only its resolved region.
  Never reset all pending audio because an unrelated/older item completed.
- `buffer.cleared`: a discard acknowledgement, not successful transcription;
  unresolved meaningful audio must remain a loss/failure, not clean Drain.
- Keep the 30-second uncommitted-speech safety bound. Awaiting-completion
  items need a separate bounded timeout/failure path: new VAD activity must
  not indefinitely mask a stuck transcription. Do not suppress fallback
  merely because some unrelated item is pending.
- Serialize commit decisions with incoming Provider state changes and allow
  at most one explicit commit intent per region. Correlate near-simultaneous
  VAD commit/completion before retrying; text equality is not deduplication.
  Unknown coverage must fail visibly, not be guessed.
- End stops intake, flushes only genuinely uncommitted speech, waits for all
  item completions, then drains. `none` mode still explicitly commits its
  pending region. Do not weaken unsafe empty-Final handling.

These are design constraints, not an implemented or validated repair. The
30.7-second retained buffer is not enough to distinguish all hypotheses.

### Required next instrumentation and tests

One 60–120-second isolated synthetic/human-owned reproduction should journal
allowlisted metadata only, with a monotonic sequence on the same process:
append sequence/sample watermark; raw speech_started/stopped/committed/item
IDs and audio offsets; delta count/length per item (not text); completed
empty/non-empty flag; commit intent/send/ack association; local arm/reset/fire
and pending seconds; guard inputs; error type/code; lifecycle transition.
Capture both receive-time and handling-time state. Do not persist raw audio,
credentials, source transcript or device IDs. The private offline harness
already provides metadata-only wire observation and characterization checks;
production instrumentation/deployment was not added in this task. A new
unobserved long run would not resolve the missing correlation.

After a repair, required tests include normal VAD, successful long-turn
fallback, VAD/fallback interleaving, already-committed buffer, empty explicit
commit vs empty transcription, pending-speech End, benign VAD empty, duplicate
Final prevention **and counter integrity**, out-of-order item completions,
new speech while an old item is pending, and `none`-mode regression.
Existing focused STT/continuous tests: **30 PASS**. Isolated characterization:
**7 PASS** (tests of current behavior, not tests that a fix succeeded).

Shared View's recent-content movement remains positive evidence. Technical
label overflow remains a separate **Presentation / Node-label quality
follow-up**, not the pipeline root cause. No UI/Analyzer/Graph changes.

**T2: RETRY NOT READY; D. PIPELINE FAILURE remains unchanged.** RFC-0006 stays
pending. No T3, Live Pilot, tag, release or source retry.

## Realtime STT Item Correlation Diagnostic

### Scope and decision

Instrumentation-only follow-up. **A. ROOT CAUSE IDENTIFIED — ITEM-SCOPED FIX
READY**, for the failure mechanism reproduced below. Root-cause class **E:
shared pending-state attribution + VAD/explicit-commit interleaving (A/B)**.
The original T2 failure still lacks its failed item ID, so retrospective
identity of the T2 sequence is **not proven**. Its result remains D, not a
successful evaluation. This evidence supports implementing and validating
an item-scoped repair; it does not establish that such a repair already works.

No finalization decisions, Provider configuration, Shared View, Analyzer,
Graph, deployment or saved T2 artifacts were changed. The diagnostic hooks
are disabled by default and use an explicitly scoped in-memory recorder.
No raw audio or transcript text is written by the diagnostic recorder.

### Provider contract checked

The current official [server event reference](https://developers.openai.com/api/reference/resources/realtime/server-events#input_audio_buffer.speech_started)
explicitly allows the speech-start and speech-stop item identities to differ
when a client manually commits during active VAD. A committed event identifies
the resulting item, but has no documented echoed client commit sequence.
The [client commit reference](https://developers.openai.com/api/reference/resources/realtime/client-events#input_audio_buffer.commit)
distinguishes committing an empty buffer (error) from transcription after a
successful commit. The [transcription guide](https://developers.openai.com/api/docs/guides/realtime-transcription)
requires item-ID reconciliation because completion order across turns is
not guaranteed. Its newer-model example was not substituted for the frozen
`gpt-transcribe` configuration.

### Instrumentation and method

- Captured Provider receive-time and application handle-time event order,
  connection ID, frame/sample watermarks, local generation, explicit commit
  sequence/reason, speech start/stop offsets, committed item/predecessor IDs,
  delta count/length, completion length/empty flag, error type/code/IDs, and
  shared pending/active-VAD state. No Provider identifier was fabricated.
- Local append, fallback eligibility/fire, commit request/send and buffer
  reset are separately recorded. The current bound measures buffered audio
  duration, not an independent wall-clock timer. Reset reason is the actual
  `transcription_completed` handler, not a newly assigned semantic boundary.
- Private unified timelines forward-fill the last observed local mutation
  snapshot and explicitly label it as such. Raw receive records and later
  handle records remain separate; latest adapter state is not item identity.
- Commit-to-item links are labelled temporal candidates where there is one
  outstanding intent and no competing preceding VAD stop. They are **not**
  claimed to be an echoed protocol acknowledgement ID. Provider item-to-delta
  and item-to-completion links use actual matching IDs.
- Duplicate completions, completion inversion, completion while an earlier
  committed item is unresolved, and buffer clears extending past known item
  ends are observable without affecting handling. Unknown item ends remain
  unknown rather than being assigned the newest local buffer end.

Controls used generated Japanese speech unrelated to T2, synthesized and
converted to mono PCM16LE/24 kHz in RAM. For continuous/race fixtures only,
low-energy 10 ms blocks were removed during test-audio construction. This is
not a Product preprocessing change or a naturalness/recognition benchmark.
R1 used 8 s speech/2 s silence; R2 70 s continuous fixture/2 s silence;
R3 29.8 s continuous/0.8 s silence near the fallback boundary; R4 repeated
2 s speech/0.7 s silence. No third-party media was used or persisted.

Each control ran a separate fresh session in an isolated process with the
existing runtime credentials/configuration. Instrumented modules were loaded
in that process's memory only, not installed into the serving application.
The existing controller, binary frame parser and Live gateway called the real
Provider. The browser-side connection was an in-memory contract driver, and
Analyzer was a no-op in this isolated manager: these controls prove Provider /
transport state behavior, **not browser routing, Analyzer quality or Graph
safety acceptance**. No production configuration or container files changed.

### Real Provider results

| Control | PCM actually appended | Non-empty Finals | Provider deltas / delivered partials | Empty completions | Explicit commits | Result |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| R1 normal VAD | 60.0 s / 600 frames | 6 | 146 / 146 | 0 | 0 | ended |
| R2 long turn | 72.0 s / 720 frames | 3 | 343 / 343 | 0 | 2 bounded | ended |
| R3 boundary race | 30.9 s / 309 frames | 0 | 48 / 47 | 1 | 1 bounded | ended_with_incomplete_processing |
| R4 nearby turns | 62.1 s / 621 frames | 23 | 182 / 182 | 0 | 1 session-end | ended |

R3 planned input was 63 s but stopped on the real error. One received delta
was not delivered before shutdown; partials are not Evidence. All controls
used the same generic context/keywords, model, Server VAD and 30 s bound.
Diagnostic dropped records: 0. Raw Provider error events: 0 in all controls;
R3's `empty_final_transcript` is generated by the application adapter from a
real empty completion, **not** `input_audio_buffer_commit_empty`.

### R3: exact failing item and local state

The following relative times start at diagnostic recorder creation, not
source playback. A/B/C are report aliases for distinct actual Provider IDs;
full identifiers and every append/delta remain in private evaluation data.

| Time (s) | Observed transition | Item and local consequence |
| ---: | --- | --- |
| 0.704 | speech_started | A, audio_start_ms=0 |
| 30.450 | bounded fallback / explicit commit #1 sent | frames 0–299, pending 30.0 s, meaningful=true, active VAD=true |
| 30.614 | committed | A; only explicit intent #1 outstanding, no VAD stop yet |
| 31.005 | speech_stopped, then committed | **B**, end=30368 ms, previous_item=A; A still awaiting completion |
| 31.301 | speech_started | **C**, start=30292 ms; shared latest boundary becomes speech_started |
| 31.447 | transcription.completed, length=0 | **B**, zero deltas; A has 47 deltas but no completion yet |
| 31.447 | application handles stt_error | shared commit_pending=true from A; local frames 0–308, pending 30.9 s; B rejected as unsafe empty |

One additional A delta was received around error handling (48 total), and
no A completion was observed before the application terminated the session.
There were two committed unresolved items concurrently. B completed while
its predecessor A was unresolved. This is observable overtaking; a completed
pair in reverse order was **not** captured because handling stopped first.
No duplicate completion occurred. No buffer reset occurred in R3 before the
failure because no non-empty Final reached `process_final`.

The decisive defect is **cross-item classification**: an automatic item B's
empty completion is classified using an explicit commit outstanding for A.
The application cannot represent “A awaiting transcript, B empty, C active.”
The changed start/stop identity during explicit commit is allowed by the
Provider contract, not proof of a Provider protocol violation.

The fixture is silent from PCM 29.8 to 30.6 s, and B stops at 30.368 s after
the explicit commit at 30.0 s. A short silent-tail item is a supported
explanation for B's empty recognition, but B has no observed start offset:
exact internal Provider coverage/prefix overlap is **not proven**. Therefore
B must not simply be declared harmless, nor may all automatic empty items
be ignored. The proven issue is assigning A's pending expectation to B and
aborting while A is producing text. Unresolved audio remains unsafe.

### Successful fallback comparison and other observed risks

R2 commit #1 targeted frames 0–299 at pending 30.0 s. Its committed item
arrived at 30.628 s; the **same item** completed non-empty at 32.185 s after
146 deltas. No separate VAD empty item interleaved. Commit #2 also completed
non-empty; the trailing normal VAD item completed before End. This directly
contrasts with R3's B completion while A is still pending.

R2 also demonstrated independent accounting drift: item #1 completion
cleared local frames 0–316 (31.7 s), including 1.7 s appended after its
explicit commit. The next local bound starts at 31.7 s rather than 30.0 s.
The Provider subsequently transcribed more items, so this proves **local
pending-accounting loss**, not permanent Provider audio/Evidence loss.

R4 did not induce two committed unfinished items (maximum one), but it did
overlap next speech with older transcription handling. Its first VAD item
ended at 2.560 s, yet completion cleared through local PCM 3.2 s, after the
next fixture speech began at 2.7 s. This is a real older-item clear of newer
audio accounting. R1's similar trailing-suffix clears were silence and are
not evidence of lost speech. Full R4 drained; no artificial event delays or
reordered Provider events were introduced.

### Current state machine and ownership

| Event | Provider-owned state | Current RONRO-owned mutation |
| --- | --- | --- |
| append | receives PCM into input pipeline | expands one local pending frame range/duration |
| speech_started | identifies speech item/start | sets one global active flag/latest boundary |
| bounded threshold | may still have an active VAD turn | sends explicit commit; sets one commit_pending flag |
| committed | creates a specific item awaiting transcription | counted/ignored; no item-to-intent ledger |
| speech_stopped | closes a specific VAD region | increments shared pending-VAD count |
| any completed | resolves that particular item | decrements shared pending-VAD count regardless of identity |
| non-empty Final handling | other items/new audio may remain | clears entire local buffer and global commit_pending |
| empty completion handling | empty belongs to its item only | checks global commit_pending; may fail another item's session |

Thus accumulating, VAD-active and transcription-pending are concurrent
conditions, not one serial global turn. Neither a single pending flag nor a
global reset accurately models the observed R3 overlap.

### Supported minimal repair design — not implemented

Separate an **uncommitted sample/frame range**, **explicit commit intents**,
and **committed Provider items awaiting completion**. Preserve identifiers and
range confidence through receive, handling and Evidence correlation. A/B/C
must coexist; completing B must not resolve/fail A merely because A has an
explicit intent. Do not infer a Provider commit ID or exact missing offset.

Use `speech_stopped` as boundary evidence, not successful recognition;
`committed` transfers correlated coverage to a pending item; commit send alone
does not resolve audio. A completion changes only its own item's lifecycle.
Retain newer appended audio, use idempotent per-item resolution, and preserve
Provider predecessor ordering where needed for Evidence/queue order. VAD
and explicit commits for overlapping regions require reconciliation before
another intent is sent; unknown coverage remains explicitly unresolved.

Bound uncommitted meaningful audio at 30 s independently from completion
waiting. After a boundary, measure the newer range, not time since the last
arbitrary Final arrival. Add a separate completion timeout/failure path so
waiting items cannot stall indefinitely. Buffer clearing is not proof of
transcription. Empty meaningful/unknown items remain warning/failure states;
only item-specific proven benign empties can resolve without Evidence.

Drain must stop intake, flush truly uncommitted speech, await all committed
items, and then drain Analyzer/render. Preserve `none`-mode explicit commit.
Do not turn the reproduced failed run into success by weakening Drain.

### Tests and next gate

After the repair, require: (1) normal VAD, (2) successful bounded fallback,
(3) real R3-pattern VAD/fallback overlap, (4) two committed pending items,
(5) out-of-order completion, (6) duplicate completion, (7) old completion
with newer uncommitted audio, (8) explicit-item empty, (9) proven benign VAD
empty, (10) End with uncommitted audio, (11) End with committed item pending,
(12) none mode, (13) no duplicate Evidence, (14) no silent audio/accounting
loss. In particular, B-empty must not erase/resolve A; unknown B coverage
must remain visible rather than being silently ignored.

Instrumentation regression: **179 tests, 158 PASS / 21 skip**. Five added
tests cover opt-in scope, metadata privacy, duplicate/order observations,
diagnostic-sink non-interference and unknown-range handling. These tests do
not substitute for the real R3 reproduction. All real controls completed
within their short-run ceilings; no T2 audio was replayed.

Shared View recency improvement and long technical-card density remain
separate observations; neither was changed. **T2 RETRY NOT READY** until an
item-scoped repair and short real-provider validation pass. RFC-0006 remains
pending. No T3, Pilot, release, merge, tag or deployment.

## Realtime STT Item-scoped Repair

The Human authorized implementation after the correlation diagnostic. This
follow-up changes only realtime audio/item accounting, Final handling and
Drain integration. Generic STT context/keywords, model, VAD parameters,
30-second bound, Analyzer, Canonical Graph and Shared View remain unchanged.
The original T2 failure and its incomplete evidence status are not rewritten.

### Repair

`prototype/live_turns.py` now owns a connection-local ledger of sample/frame
ranges, explicit commit intents and Provider items. The ledger keeps only
audio metadata (range and conservative silence flag), not raw audio files.
Existing runtime PCM is retired by committed/reserved coverage rather than
cleared by whichever Final arrives next. An intent remains unresolved until
acknowledged or explicitly rejected/reconciled; send success is not Evidence.

Provider item identity and predecessor links control completion handling.
Younger completions can arrive first but are emitted in committed item order.
Each item is acknowledged only after its application handling. Duplicate
completions cannot create duplicate Evidence. Item-specific range, commit
sequence, boundary reason and boundary event ID survive through normalization
and Evidence metadata; newer speech events cannot overwrite an older Final's
boundary metadata. These are local accounting spans, not a claim that the
Provider's internal prefix overlap was measured exactly.

An empty automatic VAD item is benign only if its accounted range is known
and contains no meaningful local signal. The preceding item must be handled
first. Explicit empty, meaningful empty and unknown-range empty remain unsafe.
Non-empty completion with unknown/overlapping ownership also fails visibly
rather than assigning the newest buffer range to the wrong Evidence.

The bounded timer uses the remaining uncommitted range, independently from
older items awaiting transcription. Existing Provider timeout bounds commit
and item resolution. End flushes uncommitted audio, waits for application
handling of all committed items, and then drains Queue/render. `none` still
uses explicit commit. Fatal Provider errors proceed to incomplete Drain even
if a failed commit intent remains; they cannot leave the session hanging.

### Additional end-of-session race found and repaired

The first implementation passed R1/R2/R3 but R4 exposed a different race:
session-end commit was sent while the Provider was already committing the
last VAD item. The VAD item completed non-empty, followed by a real
`input_audio_buffer_commit_empty` for the redundant explicit request. That
intermediate run is preserved as failed validation, not relabelled success.

The repair sends a client-generated event ID on explicit commit. A rejected
empty commit can be reconciled only when there is one outstanding intent,
the supplied related event ID matches (if present), a known VAD item already
owns its meaningful range, and any uncovered tail is silent. The VAD item
still has to finish; its completion is not fabricated. Missing ownership,
wrong ID or uncovered speech stays fatal. This is distinct from ignoring an
empty transcription. Ambiguous overlapping successful acknowledgements fail
closed rather than duplicating Evidence.

### Real Provider validation

Same short synthetic controls, unchanged `gpt-transcribe`, generic Japanese
context, keywords `["論路"]`, `server_vad_bounded`, 30 s. Each used a fresh
isolated session through the existing controller/gateway/binary frame path
with an in-memory browser connection and real Provider. Analyzer was a
no-op: the results validate item/Evidence/Drain behavior, **not** real
Analyzer/Graph quality, room audio or browser provenance. No deployed app
files/configuration were modified. No T2 source, raw audio file or full
transcript was saved.

| Control | PCM | Non-empty Finals | Partials | Bounded commits | Benign empty completions | Drain |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| R1 natural boundaries | 60.0 s | 6 | 145 | 0 | 0 | ended |
| R2 continuous turn | 72.0 s | 3 | 339 | 2 | 0 | ended |
| R3 boundary race | 63.0 s | 2 | 290 | 2 | 2 | ended |
| R4 nearby turns / End | 62.1 s | 23 | 178 | 0 | 0 | ended |

R3 again produced B-empty before A-non-empty, twice. The application retained
both non-empty Finals, processed the silent automatic items independently,
and continued receiving speech. R4 again received a real commit-empty error;
its related event ID matched the session-end intent, and coverage checks
allowed that redundant intent to resolve without losing any of 23 Finals.
Raw Provider errors therefore were **not zero** in R4; application fatal
STT failures were zero in these completed controls. This distinction matters.

All four completed without harness timeout or dropped diagnostic records.
The source audio for these tests is deliberately synthetic; no claim of
30-minute T2 acceptance, lexical completeness or real Analyzer safety is
made from counts alone. Detailed item/event IDs and timelines remain private.

### Regression and remaining gate

Added 28 focused tests for item lifecycle, R3 interleaving, FIFO completion
ordering, duplicate handling, old Final/new audio isolation, Evidence range
metadata, benign versus unsafe empty, pending-item End, `none`, missing /
overlapping coverage, resolution timeout and rejected-commit correlation.
A gateway-level test verifies that an unmatched commit-empty error terminates
with incomplete Drain instead of hanging. Existing regression cases remain.

Final regression: **207 tests, 186 PASS / 21 skip**; `git diff --check` passed.
Final metadata-inclusive confirmation also passed: R3 63 s / 2 Finals /
289 partials / 2 benign empties / ended; R4 62.1 s / 23 Finals / 180 partials /
ended. R3's first old Final owned PCM 0–30.0 s while the separate silent VAD
item owned 30.0–30.368 s. After handling both, newer meaningful PCM
30.368–31.6 s (**1.232 s**) remained pending rather than being cleared.
Frame boundaries can straddle an item boundary; sample ranges, not shared
frame indices alone, determine local ownership. Item-specific diagnostic
metadata was verified without storing audio/transcript contents.

Production is **not deployed** with this fix, and T2 was **not retried**.
Next operational step is candidate review/packaging and deployment approval,
followed by a short deployed smoke before authorizing a 30-minute T2 retry.
RFC-0006 and the separate long-technical-card issue remain pending. No T3,
Live Pilot, merge, tag or release.

## Shared View Display Label Spike

Offline follow-up, separate from the T2 STT pipeline failure. The immutable
failed-T2 Graph at revision 26 (1 Topic, 12 Nodes, 11 Relations) was used.
No STT/Analyzer/API invocation, T2 retry, deployment or Product change occurred.
The locally completed item-scoped STT fix was not changed.

### Schema and strategies

- **A — existing short field:** unavailable. `label` is the Canonical Node
  representation, not a separate concise title. The existing Node/Analyzer
  schemas supply no independent short semantic field. Relations do not provide
  a ready-made headline; Action attributes carry additional authoritative detail.
- **B — deterministic reduction:** evaluated generic whitespace and terminal
  wording reduction only, without domain-specific rules, clause deletion,
  ellipsis or N-character truncation. Total text fell from 502 to 496 characters
  (1.2%). Visible line counts and the longest-card overflow did not improve.
  This conservative experiment is insufficient; it is not proof that every
  possible deterministic language method is impossible.
- **C — Analyzer-time non-canonical display label:** recommended for the next
  design review, **not implemented or approved for adoption**. Editorial display
  specimens demonstrate a possible target, not a working automatic generator.
  No extra inference or render-time LLM was used to create this Spike.

### All-node review

Review identifiers below are not participant-facing numbering. All original
Canonical strings and candidate strings remain in the private comparison.
Five already concise labels were unchanged; seven received editorial specimens.

| Review node | Type | Original chars | B chars | Editorial chars |
|---|---|---:|---:|---:|
| N01 | Topic | 14 | 14 | 14 |
| N02 | Idea | 42 | 42 | 31 |
| N03 | Idea | 53 | 53 | 44 |
| N04 | Concern | 25 | 25 | 25 |
| N05 | Open Item | 26 | 26 | 26 |
| N06 | Idea | 33 | 33 | 33 |
| N07 | Concern | 29 | 29 | 29 |
| N08 | Idea | 45 | 45 | 33 |
| N09 | Idea | 81 | 81 | 32 |
| N10 | Concern | 56 | 53 | 47 |
| N11 | Idea | 55 | 55 | 44 |
| N12 | Idea | 43 | 40 | 28 |

Editorial total: 386 characters, 76.9% of original. This ratio is diagnostic,
not an optimization target. Assistant provisional meaning review: A (preserved)
for five unchanged labels; B (mostly preserved) for seven shortened specimens.
Human review is pending. N09 omits H/V and parts of the calculation explanation:
if these are material to participant understanding, that specimen must be
classified C (material loss) and rejected, not accepted because it fits.
Technical terms, explicit quantities, negation, tentative status and comparison
directions were checked. The specimen does not add a claim of novelty to a
proposal or turn a Concern into a Decision/Action. It does not correct ambiguous
Canonical terminology by guessing.

### Actual rendering and persistent fixtures

The existing Shared View renderer/CSS was copied into private offline pages;
only display-string lookup was overlaid. Actual Chromium screenshots were
captured at **1920×1080**, DPR 1. The Graph, projection, six selected cards,
positions, overflow count (4), layout and font sizes were unchanged.
The failed snapshot was reconstructed as an active display, not relabelled as
a successful evaluation run.

| Visible card, slot order | Current lines | B lines | Editorial lines |
|---|---:|---:|---:|
| N09 | 6 | 6 | 2 |
| N10 | 4 | 4 | 3 |
| N11 | 4 | 4 | 3 |
| N12 | 3 | 3 | 2 |
| N07 | 2 | 2 | 2 |
| N08 | 3 | 3 | 3 |

At 40px discussion text / 30px Rail text, the original longest card extends
outside its box; the editorial version has zero measured text-outside-box
instances. Documents fit the viewport without scroll. Actual screenshots were
also visually inspected. Technical words/numbers still wrap mid-expression,
and one short final line remains: pixel fit is not the same as effortless
reading. A practical target is 1–3 lines at the existing font/width, not a
universal character limit. Physical **3–5m readability remains a Human Gate**.

Existing fixtures separately exercised candidate/confirmed Decision, Open Item
and Action without fabricating them in T2. Short state labels were retained.
An Action specimen includes its explicitly stored owner/due, making its display
longer rather than optimizing compression. The current renderer shows label
only, omitting these separate Action attributes; this is recorded as a future
representation requirement, not fixed here. All four Rails fit in the synthetic
comparison (Action two lines). This is not an extreme-capacity acceptance test.

### Ownership, replay and safety design

Recommendation **C** separates producer from owner: an eventual Analyzer output
could produce the short representation in the same inference, but a Presentation
auxiliary record should own it; Canonical remains authoritative. This requires
an explicit later contract/schema review, not a hidden new Canonical field.
Store an immutable representation mapping keyed by Node/content hash and Graph
revision with a generation-policy version. Replaying that recorded revision
must reuse the same mapping, never regenerate it. Merely caching mutable output
does not guarantee same-revision determinism. Selection and overflow remain
independent of representation. Missing/invalid labels fall back to full Canonical
text; never hide a Node or silently remove required owner/due.

Mechanical checks can reject empty/oversized labels, mismatched explicit numbers
or unsupported owner/due. They cannot prove entailment, certainty preservation
or negation safety from token presence alone. Semantic sample review and Human
approval are required before adoption. Persistent unresolved questions/action
verbs and state categories must survive shortening.

The private review entry includes original/B/editorial text for all 12 Nodes,
per-node lengths/ratios/measured lines, omission notes, five actual screenshots,
persistent fixtures and a short Human checklist. No screenshots, source audio,
full transcript or runtime identifiers were added to Public Git. Recorded
Product file hashes and the immutable Graph hash were checked; Product behavior,
Canonical content, Evidence and the STT fix are unchanged. No production field
or shortening function was installed. T2 remains un-retried; Human meaning and
distance review must precede any display-label implementation decision.

## Analyzer-time display_label implementation and first real-generation evaluation

Decision: **B. DISPLAY_LABEL QUALITY INSUFFICIENT**. Local plumbing is implemented,
but automatic generation did not meet the acceptance target. Default Live output
schema remains v2; v3 is explicit opt-in. Nothing was deployed and T2 was not
retried. This result must not be conflated with the successful local item-scoped
STT fix or with the earlier manually edited short-label specimens.

### Architecture and safety

See [implementation contract](../implementation/display-label.md). Analyzer v3
adds a nullable, non-Canonical hint in the existing inference. Canonical v2
consumers and domain/event schemas are unchanged. Accepted presentation records
live in a separate ReplayResult/map sidecar, exported with existing projection
artifacts and replayed without generation. Node content hash/sequence/version
checks prevent stale hints from overriding changed Canonical content. Invalid
hints fall back; selection, six slots, overflow, Topic flow and Rail state do
not depend on hints. Action owner/due render separately from explicit attributes.

No STT state-machine behavior was modified. The continuous-session map call alone
passes the new representation sidecar; finalization/drain/item code is untouched.
Source T2 artifact integrity was checked. No audio, full transcript, credentials
or private diagnostic identifiers are added to public documentation.

### Real generation, not editorial substitution

Twelve controlled calls used the existing Analyzer path, model gpt-5.6-luna,
semantic prompt v4 plus presentation instruction, output v3. Each saved Node's
Canonical text was used as one independent evaluation input, with an empty
context. No human-edited labels were sent as Golden answers. All calls completed
successfully. No second summarization call or source-audio replay occurred.

This design can also regenerate different Canonical intents. It is **not** a
replay of original T2 Analyzer inputs. The private review exposes generated
Canonical text as well as the hint, separating upstream regeneration differences
from hint-only errors. N03 yielded only a broad Topic, not a corresponding Idea;
this is a coverage failure, not proof that a label field caused semantic drift.
Other generated candidates were explicitly associated with source Nodes only
for offline diagnostic rendering; no such matching/import occurs in Product.

Case-level Assistant provisional review (not Human Review):

| Rating | Count | Interpretation |
|---|---:|---|
| A | 1 | Good |
| B | 2 | Usable, with contextual limitations |
| C | 7 | Material omission/insufficient coverage; includes N03 above |
| D | 2 | Changed necessity/consideration state |

Failures included subject omission, lost proposal status, missing comparative
scale, loss of a measurement limitation and wording that looked like execution
instead of a need/consideration. Some subject loss had already happened in the
regenerated Canonical candidate; it must not be assigned solely to display_label.
Raw generation nevertheless fails D=0 / safety-relevant C=0 / majority A/B.

Six of twelve source-node diagnostic hints fall back (including the unmatched
case). This removes the two observed D texts from the diagnostic display, but
other material omissions still pass lexical checks. For example retaining a
number does not preserve its comparative meaning; a short phrase can lack its
technical subject. Do not claim these checks establish semantic safety.

Human feedback specifically highlighted “already proposed” versus “will propose”.
The instruction and regression guards were extended for tense, completion,
progress and planned state after this batch. No claim is made that the revised
instruction has passed a second real-provider generation batch; the initial
failure evidence remains unchanged. Future evaluation must inspect these
distinctions, not just the presence of a proposal-related word.

### Actual visual QA

Current and generated-plus-fallback displays were rendered using the actual
Shared View renderer at 1920×1080, unchanged 40px card / 30px Rail typography.
The same saved Graph, six selected cards, positions and overflow=4 were asserted.

| Slot order | Canonical lines | Generated plus fallback lines |
|---|---:|---:|
| 1 | 6 | 6 |
| 2 | 4 | 4 |
| 3 | 4 | 2 |
| 4 | 3 | 2 |
| 5 | 2 | 2 |
| 6 | 3 | 1 |

Document dimensions fit 1920×1080, but one card still extends outside its box
because the unsafe hint correctly fell back to the long original. **Visual
acceptance is not passed.** No font reduction/clipping/ellipsis was used to hide
this. Existing synthetic candidate/confirmed/Open Item/Action fixtures verified
separate Rails and structural owner/due; no Decisions/Actions were fabricated
in the saved T2 Graph. Rail content fits, but physical 3–5m acceptance is pending.

The private review entry contains all 12 original/generated/effective labels,
reasons, provisional ratings and current/generated/persistent screenshots.
Next step is presentation-generation quality work with fixed evaluation criteria,
especially subject, comparison and temporal-state preservation—not deployment
or T2 retry. RFC-0006 remains pending.

Generation usage: 12 calls, 32,239 prompt tokens and 5,096 completion tokens;
no cost claim is made without a verified applicable rate. Final regression
results are recorded below; tests are structural/compatibility evidence and
do not supersede the failed semantic/visual gate.

Final suite: **225 tests, 204 PASS / 21 skip**, including 18 new display-label
tests. `git diff --check` passed. Coverage includes invalid/missing hints,
unchanged v2, explicit v3 opt-in, Canonical equality, exported live-queue sidecar,
replay roundtrip, duplicate/absent-node protection, stale/malformed metadata,
selection invariance, persistent state, owner/due, certainty/negation/numbers
and selected tense/aspect changes. Existing tests were retained.
STT/turn/transport/diagnostic file hashes match the pre-task local candidate;
the continuous-session file differs only in its map-sidecar argument.

### Display-label follow-up: five-line fit and state preservation

This follow-up preserves the original T2 failure and earlier label-generation
findings. No deployment, T2 retry, audio capture or STT modification occurred.

Actual Chromium rendering at 1920×1080 now fits all six saved T2 cards without
clipping or scrollbars. Canonical-only rendering uses 36px for the longest card
(five lines), retaining 40px for the other five. Topic-flow and synthetic dense
Persistent Rail fixtures also fit. Generated-label rendering uses 40px on all
six cards (2–4 lines). Selection, slots and overflow remain unchanged. An extreme
long-text control correctly remains unresolved at the 36px floor rather than
silently hiding content. Physical 3–5m acceptance remains a Human gate.

Presentation instruction/validation policy v2 explicitly preserves past/future,
progress, negation, provisional certainty, comparisons and scope. Existing
persisted hints retain legacy validation for deterministic historical replay.
The model and semantic extraction prompt remain unchanged; the presentation
instruction is part of the same inference, not a second summarization call.

Two real-provider control arms used saved Canonical text, not T2 audio:

- Normal Analyzer generation: 20 inputs. Some outputs were Topic-only/no-op or
  reconstructed Canonical content; these are coverage/semantic limitations,
  not proof that every display-label case passed.
- Frozen-Canonical control: evaluation-only response constraints retained exact
  Canonical content/type while leaving display labels unconstrained. All 20
  requests succeeded. Provisional review of 12 T2 labels: A=10, B=1, C=1, D=0.
  The C case omitted an important source/limitation condition and was rejected
  by scope validation. One additional safe rephrase was conservatively rejected
  by state validation. Both display full Canonical text. Eight state controls
  preserved past/future proposal, negative confirmation, planned confirmation,
  ongoing consideration/action, comparison and provisional numeric scope.

These controls do not establish unrestricted generation quality or Human
semantic approval. Detailed original/generated/effective comparisons and actual
screenshots are private review artifacts. Public Git contains no source media
or transcript. Default Analyzer schema remains v2; v3 stays explicit opt-in.

Regression: **229 tests / 208 PASS / 21 skip**. Separate actual-browser QA checks
five-line fit, font floor, bounds, repeat-render determinism, six slots and
structural Action owner/due. Persistent Rail semantics and STT fix are unchanged.

## T2 Retry — candidate deployment and startup failure

The earlier six-minute failed T2 run remains unchanged. This is a separate
attempt with the approved fixed source interval **00:57:00–01:27:00**.

### Frozen identity and deployment

- Branch: `t2-retry-rc1`.
- Source SHA: `b8d62f3eb7ca320bb2beba135aad4ac47631af64`.
- [Existing publish workflow run](https://github.com/hakobune8/ronro/actions/runs/35829209914).
- Image tag: `ghcr.io/hakobune8/ronro:t2-retry-rc1`.
- Accepted/deployed digest:
  `sha256:97ed1d204616a1542fa71001245793804f245b01b90124e46594a2895e850237`.

Public-safe audit excluded source media, complete transcripts, private runtime
artifacts/identifiers, credentials and local paths. Full suite: **208 PASS /
21 skip**, `git diff --check` clean. Existing CI `GITHUB_TOKEN` with
`packages: write` published the unique candidate; no new credentials, release
tag or main merge. Previous digest is retained privately for rollback.

Digest-pinned rollout reached Ready 1/1, restart 0. `/`, `/shared`, `/control`,
`/session`, `/healthz`, `/readyz` returned 200; `/live` WSS carried real audio.
Infrastructure topology remained unchanged. Runtime explicitly selected
Analyzer output **v3** for display-label evaluation; generic code default stays
v2. `server_vad_bounded`, 30s, Generic Japanese Meeting Context and `["論路"]`
remained unchanged. No rebuild/config adjustment between acceptance and retry.

### Short acceptance and provenance

Synthetic Japanese input through the normal controller/HTTP/WSS contract:
101.854s input, 1,019 accepted chunks, **7 Finals / 397 Partials**. Boundaries:
5 Server VAD, 2 bounded fallback. STT/Analyzer/Queue failures 0; pending,
processing and failed queue counts 0; `ended`; Graph/Render **17/17**. Maximum
uncommitted audio 30.148s. Seven distinct item/Evidence traces were retained;
no known completed-Final Evidence loss or duplicate Evidence. No raw audio saved.

Actual generated display labels and unsafe-label fallback were observed.
Past proposal/non-adoption and provisional state were spot-checked; this is not
general semantic certification. Deployed HTML matched the locally tested bytes.
A deployed basic fixture rendered within a 1920×1080 DOM with 40px cards and
hidden branding. Dense six-card/rail coverage remains the prior local browser
QA of identical HTML, not a newly captured dense live screen. An attempted live
screenshot timed out when no eligible current-discussion cards were present;
this alone is not classified as a Product defect.

Official playback provenance used Safari → BlackHole → Chrome, outside the
evaluation interval. Played capture RMS roughly 0.05–0.10, paused RMS 0, resumed
roughly 0.047–0.087. Three consecutive Finals corresponded to official Player
caption/technical-explanation anchors (interim findings, standards revision,
reliability and strengthening standards). This was caption/visual semantic
verification, not direct auditory review. Pause/Resume and Player progression
passed; no reset or Demo contamination observed. Provenance ended cleanly:
**8 Finals / 655 Partials**, failures 0, Graph/Render **13/13**.

### Retry failure — not the previous empty-transcription failure

A new empty session was prepared, with connected BlackHole track and WSS.
Preparation included approximately 53 seconds of silent capture before the
official source began. At the first incoming source audio, the session failed
within approximately **0.6 seconds of playback**. Backend PCM accounting reached
about 53.1s, mostly pre-roll silence; this must not be described as 53s of source
speech. The official Player continued normally until the failure was observed
and it was stopped at approximately **00:57:20.04**. No 30-minute run completed.

Exact error: **`input_audio_buffer_commit_empty`**, Provider buffer **0.00ms**,
minimum expected **100ms**. This is a rejected commit, **not** an empty
`transcription.completed` and not a recurrence proven to have the same cause as
the original T2 failure. A long silent pre-roll → initial speech transition is
a diagnostic lead, not an established causal explanation. Detailed Provider
item/commit ordering is not available in this web snapshot; do not invent it.

| Retry measurement | Result |
|---|---:|
| Finals / Partials | 0 / 0 |
| STT errors / empty transcription completions | 1 / 0 |
| Analyzer calls / failures | 0 / 0 |
| Queue pending / processing / failed | 0 / 0 / 0 |
| Topics / Nodes / Relations | 0 / 0 / 0 |
| Decision / Open Item / Action | 0 / 0 / 0 |
| Graph / Render revision | 2 / 2 |
| Runtime state | ended_with_incomplete_processing |

Queue drain reported complete, but that does not override the unsafe runtime
state. Completed-Final Evidence loss is zero only trivially (no Finals); loss or
unresolved coverage of incoming source audio cannot be excluded. Overall
**Evidence loss = 0 is not claimed**. No automatic confirmation, invented
owner/due, Graph corruption or Queue silent drop was observed in the empty run.
Unresolved STT item count cannot independently be quantified from retained API
metadata and must not be reported as zero.

No 10/20/30-minute snapshots, label-quality ratings, recency statistics or
Q1–Q7 scores are available. No T2 latency/cost quality conclusion is possible.
Short-control performance is separate: Queue p50/p95/max 0.001/0.266/0.266s;
Analyzer 5.854/10.842/10.842s; E2E 9.027/17.629/17.629s.

**Decision: D. T2 PIPELINE FAILURE — RETRY NOT READY.** Source/capture stopped,
evaluation timers cleared; candidate remains deployed without further tuning
or automatic rollback. Investigate the silent-pre-roll/first-speech commit
transition on the frozen version before another retry. No fix or second retry
was performed. RFC-0006 remains pending; T3, Live Pilot and release not started.

## T2 Retry Silent Pre-roll / First-speech Repair

This follow-up preserves both failed T2 runs. It addresses the retry's
`input_audio_buffer_commit_empty`, not the earlier empty transcription completion.

### Controlled root-cause evidence

An owned synthetic Japanese fixture reproduced the startup failure using the
unchanged candidate's Live gateway and real Provider. After 53 seconds of silent
PCM, frame 530 introduced meaningful input. The application immediately fired
bounded fallback with raw pending duration 53.1s, although only 0.1s of meaningful
input had begun. No Provider speech-start event had arrived. The Provider returned
`invalid_request_error / input_audio_buffer_commit_empty`, explicitly referencing
the local commit's event ID. There were no transcription completions. Runtime
ended incomplete, with zero Finals and Partials. This establishes the premature
commit and rejection sequence; it does not expose Provider-internal buffering.

The original web snapshot lacked this correlation. The controlled reproduction
provides the matching failure pattern without claiming missing historical IDs.
The root cause is the **local bounded clock counting leading silence**, not
Shared View, Analyzer, YouTube restrictions, or an empty completed item.

The [official Realtime client-event contract](https://developers.openai.com/api/reference/resources/realtime/client-events)
distinguishes a rejected empty-buffer commit from a successfully committed item.
The [transcription guide](https://developers.openai.com/api/docs/guides/realtime-transcription)
also requires item-based correlation rather than assuming cross-turn completion
ordering. Neither contract justifies treating this rejection as a safe Final.

### Minimal repair

The bound now measures from the first meaningful frame in the uncommitted range
to the latest appended sample. Leading silence is excluded; pauses after speech
begins are included. The existing silence detector and 30-second configuration
remain unchanged. Audio/range ownership is retained, not truncated. Older item
completion cannot reset the newer range's clock. Raw pending-audio metrics still
include silence and must not be mistaken for meaningful-audio bound age.

`none` mode, explicit end flushing, unsafe empty-item handling and error reporting
are unchanged. No STT model, context, Analyzer, Canonical or Shared View changes.

### Validation scope

Real-Provider controls run in isolated child processes with the existing Live
controller/gateway contract and a Noop Analyzer. They exercise STT/Evidence/queue
handling, not production Analyzer quality or Safari/BlackHole provenance. Audio
is generated and streamed in RAM only; private artifacts retain metadata, not
raw audio or transcript text. The Deployment and image digest remain unchanged.

The six added regression cases cover silent pre-roll, intervening pauses, a new
turn after VAD and a silent gap, partial-frame ownership, out-of-order completion,
and the complete gateway's short-speech/session-end sequence. Full suite:
**214 PASS / 21 skip**; focused STT suite: **56 PASS**.

| Real-Provider control | Input duration | Finals / Partials | Explicit boundaries | Result |
|---|---:|---:|---|---|
| Unchanged baseline: 53s silence then speech | 68s planned; stopped near 53.2s | 0 / 0 | premature fallback at 53.1s raw pending | incomplete; commit rejected |
| Repaired: identical 53s silence then speech | 68s | 1 / 43 | none; normal VAD | ended |
| 40s silence then 36s continuous speech | 79s | 2 / 169 | 1 fallback at 30.0s meaningful age | ended |
| Pure silence | 40s | 0 / 0 | none | ended |
| Normal VAD, six turns | 60s | 6 / 147 | none | ended |
| Near-boundary VAD/fallback race | 63s | 2 / 290 | 2 fallbacks, each at 30.0s | ended |
| Close turns and session end | 62.1s | 23 / 179 | 1 session-end flush | ended |

All repaired controls had zero STT failures, zero duplicate completions and clean
drain. Committed/completed item counts matched (1/1, 2/2, 0/0, 6/6, 4/4,
23/23 respectively). The race control's two additional empty completions were
known silent automatic-VAD ranges, 30.000–30.368s and 60.600–60.960s; the existing
item-specific benign handling applied without weakening error policy. Their
speech-bearing explicit items completed non-empty. No unresolved-item failure
was reported. These controls do not establish exact recognition recall or
production Analyzer/Graph semantic safety; Noop Analyzer timings are not Pilot
performance measurements.

**Fix locally validated — ready for candidate packaging and deployed short
acceptance, not yet T2 retry-ready.** The running image remains the prior failed
candidate. Next: publish a new unique CI candidate, deploy by digest, repeat
silent-pre-roll/first-speech and long-turn smoke with the real Analyzer, then
official Safari → BlackHole → Chrome provenance. Only that accepted same digest
may be used for the frozen 00:57:00–01:27:00 retry. No deploy, T2, T3, Pilot or
release was performed in this repair task. RFC-0006 remains pending.
