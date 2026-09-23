# Limited Live Audio Prototype Implementation Plan

Status: **Plan only — implementation has not started**

## 1. Purpose

このPrototypeの目的は、実際の会議室で次の経路が実時間に近い形で成立するかを検証することである。

```text
Audio → STT → Final Utterance → Analyzer → Discussion Graph → Discussion Map
```

Production Meeting Assistant、Minutes、完全なAction抽出、Live Audioの運用安定性を完成させることは目的にしない。検証対象は、参加者がMapを見ながら議論を理解・修正・前進できるかである。

このPlan作成ではコード、LLM API、STT APIを変更・呼び出ししていない。

## 2. Frozen Baseline

| Layer | Baseline |
|---|---|
| STT | `gpt-transcribe` + meeting context / terminology hints |
| Normalization | v2 |
| Analyzer | `gpt-5.6-luna` |
| Reasoning | `medium` |
| Prompt | `analyzer-prompt-v4` |
| Context | v1 |
| Type D | OFF |
| Presentation Compaction | ON |
| Open Item Lifecycle | ON |
| Noise Guard | OFF。将来のCost Optimization候補としてのみ保持 |
| Canonical Event / Materializer | 既存のまま |
| Human Command | M4のEvent経路を再利用 |

Prompt v5はExperimental Resultとして保存するが、Live Baselineには採用しない。Live Audioを理由にCanonical Schema、Event Store、Materializer、Discussion Graph、Stable Mapの責務を変更しない。

## 3. Initial Live Scope

初回Sessionは次に限定する。

- 1 room
- 2〜3 participants
- Japanese
- 10〜15 minutes
- Laptop + external microphone
- 1 shared display
- 1 running session
- Production persistenceなし
- Authenticationなし
- Minutesなし
- Visual Artifact生成なし
- Online meeting integrationなし
- Multi-room / multi-user editingなし

Live開始・停止はUIから明示的に行う。開始前にMicrophoneを開かない。参加者へ録音・Transcription・Evaluation Artifactの扱いを説明し、同意を得てから開始する。

## 4. Existing Architecture Preservation

既存のCanonical経路は次のまま維持する。

```text
Analyzer
  ↓ Candidate Event
Event Store
  ↓
Materializer
  ↓
Discussion Graph
  ↓
Presentation Projection
  ↓
Stable Discussion Map
```

Live Audioはこの前段にだけ追加する。

```text
Microphone
  ↓
Audio Capture
  ↓
Audio Buffer
  ↓
STT
  ↓ only finalized transcript
Utterance Finalizer / Normalization v2
  ↓
Final Utterance FIFO Queue
  ↓
Analyzer Worker
  ↓
既存Candidate Event → Event Store → Materializer → Projection → Map
```

UIはGraphを直接Mutationしない。Human Commandも既存の `Human Command → Event → Event Store → Materializer` を通す。

## 5. Architecture Decisions

| Question | Decision | Reason |
|---|---|---|
|Audio Capture|Browser Web Audio API + AudioWorklet|既存HTML/JavaScriptを維持し、PCMを明示的に扱える|
|Browser → Python|Local WebSocket|連続Audioを小さいFrameで送れ、HTTP ServerをControl / Command境界として残せる|
|Python → STT|STT AdapterからProvider Realtime WebSocket|Live microphone用のFinalizationとTranscript completionを扱う|
|STT model|`gpt-transcribe` committed-turn transcription|現BaselineのTerminology / Prompt方針を維持する|
|Finalization|ProviderのFinal completionを権威とし、VADまたは明示commitでturnを確定|PartialをCanonicalへ入れない|
|Queue|In-memory FIFO、single Analyzer Worker|sequence順とRevisionを単純に保つ|
|Backpressure|Evidence保持、queue、遅延、UI coalescing、明示的Degraded表示|Semantic Utteranceを黙ってdropしない|
|UI cadence|Canonical Eventは逐次、Renderは2〜5秒coalescing|MapのちらつきとOrderingを分離|
|Session Drain|`active → finalizing → ended` +既存Session Finalization Event|Audio / STT / Utterance / Analyzer / Graphを順にDrainする|
|Raw Audio|通常はSession中の一時保持のみ。明示同意時だけEvaluation Artifactへ保存|Privacyと再処理性のTrade-offを限定する|
|Failure / Retry|Failure itemを保持し、Manual Retry。既存Graphは変更しない|Production Retryへ過剰実装しない|

## 6. Audio Capture

### 比較

|方式|利点|課題|判定|
|---|---|---|---|
|Browser MediaRecorder|既存Browserで簡単。圧縮Chunkを扱える|Codec / Container変換、Chunk境界と意味境界のずれ、Realtime PCM要件との調整|Fallback / Recorded-like test向け|
|Browser Web Audio API / AudioWorklet|PCM Frame、Audio timestamp、Input Levelを扱いやすい。AudioWorkletでUI threadを塞がない|Resampling、権限、Browser差|**採用**|
|Python local capture|Server側で直接音声を読める|OS依存、Browser/shared displayとの分離、会議室実験の再現性が低い|Developer fallbackのみ|

採用方式はBrowser Web Audio API + AudioWorkletとする。Mono PCMを小さいFrameへ分け、Session-relative audio offsetを付与する。Browserが提供するSample Rateが異なる場合は、Capture AdapterでProviderが要求する形式へ変換する。Audio CaptureはTranscriptやGraphを生成しない。

`Start Live Session`のクリック後にのみ `getUserMedia` を呼ぶ。Stop時にはAudioWorkletを停止し、最後のBufferを明示的にFlushする。

## 7. Audio Transport

既存Repositoryは標準Python `ThreadingHTTPServer` とHTML/JavaScript UIである。大規模なFrontend Frameworkへの移行は行わない。

### 採用案

```text
Browser AudioWorklet
  ⇄ local WebSocket ⇄
Python Live Session Transport
  ⇄ provider WebSocket ⇄
STT Realtime Adapter
```

既存HTTPは次のControl用途に残す。

- Session Start / Stop
- Runtime Snapshot
- Human Commands
- Evaluation Markers
- Participant Feedback

WebSocketはAudioと軽量なRuntime Statusだけに使う。実装時に必要なら、既存HTTP Serverを置き換えず、小さいWebSocket依存またはLocal WebSocket bridgeを1つだけ追加する。React / Next.js / WebSocket基盤の導入はしない。

### HTTP Chunk Uploadを初回採用しない理由

Periodic HTTP uploadはDependencyを増やさないが、file-oriented transcriptionではChunk境界がSemantic Boundaryと一致しない。Upload遅延、重複、再送、VAD、FinalizationをApplication側で再実装する必要があり、最初のLive検証が「Chunking実装の検証」に寄りやすい。Fallbackとしては保持するが、初回の主経路にはしない。

## 8. STT Strategy

OpenAI公式仕様上、Transcriptions APIには `gpt-transcribe`、`keywords`、`prompt`、`stream` が存在するが、File transcriptionのstreamは完成済みRecordingの処理結果をStreamする用途である。ongoing microphoneにはRealtime transcription経路を使う設計とする。

初回はBaselineを変えず、Realtime Session内で `gpt-transcribe` を使い、`prompt` と `keywords` に既存のMeeting Context / 実際に登場するTerminologyを渡す。`gpt-live-transcribe` へのModel変更、Diarization追加、Model比較はこのPlanのNon-goalとする。

Provider仕様上、Realtime transcriptionではAudio BufferへChunkを送り、明示的なcommitまたはVADでturnを確定し、Transcript deltaとcompletionを受け取れる。異なるTurnのcompletion順は保証されないため、Provider `item_id` とCapture Commit順を対応付け、completion到着順をCanonical Orderに使わない。

参照:

- [OpenAI Create transcription API reference](https://developers.openai.com/api/reference/resources/audio/subresources/transcriptions/methods/create)
- [OpenAI Speech-to-text guide](https://developers.openai.com/api/docs/guides/speech-to-text)
- [OpenAI Realtime transcription guide](https://developers.openai.com/api/docs/guides/realtime-transcription)

## 9. Terminology Context

STTへ渡すContextはMeeting内容の短い説明と、実際のSessionで登場する用語だけに限定する。

例:

```text
Discussion Map AI FacilitatorのMVPについて、Discussion Map、MVP、Visual Artifact、Current Topic、STT、AI Analyzer、Open Item、Action Item、Parking Lotを使って議論する日本語の技術会議。
```

`keywords`には実際の会議で使われるTermだけを渡す。Golden Transcript全文、将来のEvent、既知の回答、Canonical Node一覧をSTTへ渡さない。STTのTerm Hintは候補を強制するものではなく、Evidenceの意味を補完するものでもない。

## 10. Partial / Finalization Policy

### Partial Transcript

- Partialは内部BufferまたはDeveloper UIのDiagnosticsにだけ保持可能。
- PartialからCandidate Eventを生成しない。
- PartialからGraph、Revision、Current Topic、Map Projectionを変更しない。
- PartialをFinal Transcriptへ単純連結せず、Provider completionで置換する。

### Final Transcript Segment

次のすべてを満たしたものをFinal inputとする。

1. ProviderからTranscript completionを受信している。
2. 対応するProvider `item_id` / capture commitが特定できる。
3. Raw textが空でない、または明示的なEmpty / Silenceとして記録されている。
4. Audio start / endのTraceがある。
5. 同じSTT itemを二重にFinal扱いしていない。

FinalizationはProvider completionを第一候補とする。Turn BoundaryはServer VADを基本とし、Stop時にはClient / Backendが残りBufferを明示commitする。VAD閾値は実装後の2〜3分Preflightで調整する。VADやProviderが利用できない場合も、Audio chunk boundaryだけをSemantic Utteranceとみなさない。

## 11. Utterance Finalizer / Normalization v2

```text
STT final segment(s)
  ↓
Utterance Finalizer
  ↓
Normalization v2
  ↓
Normalized Final Utterance
```

STT SegmentとAnalyzer Utteranceは別オブジェクトで保持する。

- Raw Segmentを変更しない。
- Normalization v2の同一Speaker / Fragment / Boundary Policyを再利用する。
- Speakerが取れない場合は `speaker = null` とし、Speakerを推測しない。
- Filler / Agreement-onlyもEvidenceには残す。
- Noise GuardはOFF。Analyzerへ送るかどうかを意味Ruleで追加判断しない。
- 同じRaw Segment / Provider itemの再送はDeduplicateし、Diagnosticを保存する。
- Normalized Utteranceには `raw_segment_ids` とAudio rangeを残す。

## 12. Evidence and Sequence

### Evidence Trace

Liveでも次をSidecar / Runtime Evidenceへ保存する。Domain Schemaを変更する必要はない。

- `evidence_id`
- `session_id`
- `audio_start`
- `audio_end`
- `raw_stt_text`
- `normalized_text`
- `stt_provider_item_id`
- `stt_attempt_id`
- `speaker`（取得できる場合のみ）
- `utterance_sequence`

Analyzer / Canonical Eventの`source_evidence_ids`はこのEvidence IDを参照する。Raw AudioはEvidence textの代わりにならない。

### Sequenceの分離

|Sequence|意味|Orderingに使うもの|
|---|---|---|
|Audio chunk sequence|Capture Frameの順序|Capture append順|
|STT turn sequence|Commitされた発話の順序|Audio commit順 / item_id対応|
|Utterance sequence|Normalization後の発話順|STT turn sequence|
|Event sequence|Canonical Event Storeの順序|Event Storeが付与|

Timestamp、Provider completion到着順、Analyzer終了順、Event IDをCanonical Event Orderingに使わない。

## 13. Queue and Analyzer Worker

### Queue State

Runtime-only stateとして次を持つ。

- `pending`
- `processing`
- `completed`
- `failed`

Canonical DomainへQueue Stateを追加しない。

### Worker

初回はAnalyzer Workerを1つに固定する。

1. Final UtteranceをFIFOへ追加。
2. `pending → processing` として一件取り出す。
3. Current Canonical Graph / Recent EventsでAnalyzerを実行。
4. Candidate Eventを既存Schemaで検証。
5. Event StoreへAppendし、MaterializerでApply。
6. Projectionを更新し、`completed`へ移す。
7. 失敗時はEvidenceを保持して`failed`へ移し、次Utteranceへ進む。

Human Commandが先にAppendされた場合、Analyzerが古いRevisionを前提にしたCandidateをそのまま適用しない。Revision mismatchならCandidateを保留し、最新GraphからManual Retry対象にする。Human EventをAI Eventで打ち消さない。

## 14. Backpressure

優先順位は次のとおりとする。

1. FIFO Queueで保持。
2. UI Renderだけを2〜5秒coalesce。
3. Analyzer処理を遅延させる。
4. UIへ `Delayed` を明示。
5. 終了時にDrainを待つ。

初回PrototypeではSemantic Utteranceを黙ってdropしない。Noise GuardをBackpressureの隠れたDrop機構として使わない。Queue depthが5を超えた場合、または連続して増加する場合はDeveloper UIへ警告を出す。

次をBackpressureと呼び、Silent Dropとは区別する。

- `queued`: Evidenceを保持し、まだAnalyzerへ送っていない。
- `delayed`: Analyzer / Provider待ちでMap更新が遅れている。
- `failed`: EvidenceとFailure reasonを保持し、Manual Retry可能。
- `coalesced`: Canonical Eventではなく、UI Render通知だけをまとめた。

## 15. Live Map and UI

MapをPrimary Viewとし、Live Diagnosticsは補助領域に置く。

最低限表示するもの:

- `Listening`
- `Transcribing`
- `Analyzing`
- `Updated`
- `Delayed`
- Current finalized utterance
- Queue depth
- Current processing sequence
- Last completed sequence
- Failed count

Current UtteranceはDeveloper / Evaluation用に表示するが、PartialをMap Cardにしない。Candidate DecisionはPending badgeとともにPassive Decision Railへ表示する。Human操作は既存M4 Commandへ接続する。

Live中に使用可能なCommand:

- Confirm / Revoke Decision
- Rename
- Merge
- Parking / Restore
- Set Current Topic
- Resolve / Reopen Open Item
- Update Action

すべて `expected_revision` を必須とし、Conflict時は明示表示する。自動Mergeや自動Conflict Resolutionは行わない。

## 16. Latency Instrumentation

Utterance単位で次を計測する。

- `audio_end_at`
- `stt_final_at`
- `analyzer_start_at`
- `analyzer_end_at`
- `graph_updated_at`
- `map_rendered_at`

算出値:

```text
STT Finalization Latency = stt_final_at - audio_end_at
Analyzer Latency         = analyzer_end_at - analyzer_start_at
Queue Wait               = analyzer_start_at - stt_final_at
Graph Latency            = graph_updated_at - analyzer_end_at
Map Render Latency       = map_rendered_at - graph_updated_at
End-to-End               = map_rendered_at - audio_end_at
```

### Acceptance Budget

|Level|Budget|
|---|---:|
|Target|Median End-to-End ≤ 5 sec|
|Acceptable|p95 End-to-End ≤ 10 sec|
|Degraded|単発の10 sec超。UIに遅延を表示|
|Stop / investigate|20 sec超が継続、または30 sec以上Mapが追いつかない|

Analyzerが遅いのかQueueが詰まっているのかを分離するため、Queue Waitを必須にする。Recorded BatchのRTFはこのRealtime Budgetへ直接変換しない。

## 17. Failure Handling and Retry

### STT Failure

- Audio chunkとCapture sequenceを失わない。
- STT failure recordをRuntime Artifactへ保存する。
- Canonical Graphは変更しない。
- Manual Retryで同じAudio rangeを再送できる。
- Retryが成功した場合も、元のAttemptを消さず、Attempt IDを分ける。

### Analyzer Failure

- Final Transcript Evidenceを保持する。
- Queue itemを`failed`へ移す。
- Candidate Event / Graph / Revisionは追加しない。
- 次のUtterance処理は継続する。
- Manual Retryは同じUtterance sequenceに対する別Attemptとして扱う。

Production-grade exponential backoffは実装しない。初回はManual Retryと、短い単発Retryのどちらかに限定する。

### Invalid / Duplicate Result

- Provider item_id、utterance sequence、attempt IDで重複を検出する。
- 同じCanonical Eventを二重Appendしない。
- Invalid CandidateはGraphへ適用せず、Failure reasonを保存する。
- Validな後続Utteranceは止めない。

## 18. Session Lifecycle and Drain

### Start

1. Userが`Start Live Session`を明示。
2. Runtime Sessionを`active`で作成。
3. Microphone permissionを要求。
4. Provider STT sessionを確立。
5. Audio Captureを開始。

開始前にAudio Capture、STT、Analyzerを起動しない。

### Stop / Finalization

`End Session`後は次の順序で処理する。

1. Audio Capture停止。
2. AudioWorklet / BufferをFlush。
3. 残りAudioをProviderへCommit。
4. STT Final completionを待つ。
5. 最後のFinal UtteranceをNormalization v2へ送る。
6. Final Utterance FIFO QueueをDrain。
7. Analyzer WorkerをDrain。
8. Event Appendを完了。
9. Graphを最後のEventまでMaterialize。
10. Presentation Projectionを更新。
11. `session_ended`を記録。

既存Contractの `active → finalizing → ended` をRuntime / Canonical Session Stateで再利用する。Session endとMinutes generationは別問題であり、Minutesは生成しない。

### Drain Complete

以下をすべて満たすことをDrain Completeとする。

- Audio buffer empty
- Pending STT = 0
- Final Utterance Queue = 0
- Analyzer processing = none
- Event append complete
- Graph materialized through last accepted Event
- Projection rendered through last Graph revision

### Timeout

Drain開始から30秒をPrototype Timeoutとする。Timeout時は無限待機せず、次を記録したうえでSessionを終了可能にする。

- `drain_status = partial` または `failed`
- 未処理Audio / STT / Utterance / Analyzer item ID
- 最終Graph revision
- 最後に完了したsequence
- Retry可能なFailure

Timeoutで未処理内容を推測してEvent化しない。Partial / Failed Sessionは完全なMeeting Resultとして表示しない。

## 19. Raw Audio Retention and Privacy

### Policy Decision

Defaultは **Session中の一時保持のみ** とする。

- AudioはSTTが完了し、Retry windowを過ぎたら削除。
- Raw AudioをCanonical Event、Graph、通常Logへ入れない。
- Evaluation Artifactとしての保存は、Session開始前に明示Opt-inされた場合だけ。
- Opt-in ArtifactにはSession ID、Retention期限、Consent markerを付ける。
- API key、Authorization header、Raw AudioをGitへ保存しない。
- UIへMicrophone、Recording、Transcribing状態を常時表示。

Failure時にRetryが必要なChunkだけは一時的に残す。Session終了後の持続保存はDefaultにしない。

## 20. Evaluation Markers and Feedback

ObserverがDeveloper UIから次のMarkerを付けられるように計画する。MarkerはCanonical Graphへ入れない。

- `helpful`
- `distracting`
- `wrong`
- `important_miss`
- `latency_notice`
- `correction_needed`

Markerにはwall-clock time、current utterance sequence、optional noteだけを付ける。Map Stateを変更するEventにはしない。

Session終了後、5段階で次を収集する。

- MapはDiscussion理解に役立ったか。
- Current Topicは分かったか。
- Map更新は邪魔だったか。
- 誤った情報が気になったか。
- 会議後もMapを見たいと思うか。

## 21. Live Metrics

### System

- audio duration
- STT request / session count
- STT failure / retry count
- finalization latency p50 / p95 / max
- utterance count
- Analyzer call / failure count
- analyzer latency p50 / p95 / max
- queue max depth
- queue wait p50 / p95
- delayed / failed / coalesced count
- map update count
- end-to-end latency p50 / p95 / max

### Semantic / Canonical

- Current Topic transition / return
- Topic continuity
- Candidate Decision count
- Human Confirm / Revoke count
- Open Item / Resolve / Reopen count
- Action candidate / Update count
- Automatic Confirmation
- Invented Owner / Due
- Critical Information Recall
- Graph revision and Replay result

### Human

- Map view / self-reported glance count
- Helpful / Distracting / Wrong / Important Miss markers
- Human Correction count
- Current Topic understood rating
- Overall usefulness rating

## 22. Initial Implementation Milestones

### L1 — Audio Capture / Transport

**Goal**

Start / Stopから、音声FrameがSessionへ安全に到着することを確認する。

**Deliverables**

- Browser AudioWorklet capture
- Local WebSocket transport
- Runtime Session `active`
- Audio chunk sequence / offset
- Listening indicator

**Acceptance Criteria**

- Start前にMicrophoneを開かない。
- StopでAudio bufferがFlushされる。
- Frame orderとtimestampが再現可能。
- Graph / Event Storeへ変更がない。
- Raw AudioはDefaultで永続保存されない。

**Dependencies**

- Existing HTML/JavaScript UI
- Existing Python HTTP control server
- One small WebSocket transport dependency or local bridge decision

### L2 — STT / Finalization

**Goal**

AudioからFinal Transcript Segmentを取得し、PartialをGraphへ漏らさない。

**Deliverables**

- `gpt-transcribe` Realtime Adapter
- Japanese prompt / keywords configuration
- Provider item mapping
- VAD / explicit commit handling
- Final completion handler
- Raw / normalized Evidence trace

**Acceptance Criteria**

- Deltaは内部Bufferに留まる。
- CompletionだけがFinalizerへ入る。
- `item_id`とCapture orderでout-of-order completionを安全に扱う。
- Normalization v2を通過する。
- STT failureでGraphが変わらない。

**Dependencies**

- L1
- Runtime Provider configuration
- 2〜3分の実環境Preflight

### L3 — FIFO Queue / Analyzer Worker

**Goal**

Final Utteranceを既存AnalyzerからGraphまで1件ずつ流す。

**Deliverables**

- Final Utterance FIFO Queue
- Queue state / observability
- Single Analyzer Worker
- Candidate Event validation
- Queue wait / Analyzer latency metrics

**Acceptance Criteria**

- sequence順で処理される。
- Analyzerのcompletion順でEvent orderが変わらない。
- Human EventとのRevision Conflictを検出する。
- Failure itemが次のUtteranceを止めない。
- Replayで同じFinal Event Streamから同じGraphを得る。

**Dependencies**

- L2
- Existing Event Store / Materializer / Analyzer Contract

### L4 — Live Map / Human Command Integration

**Goal**

MapをPrimary Viewとして更新し、既存Human CommandをLive中にも使用できるようにする。

**Deliverables**

- Processing indicator
- Current finalized utterance panel
- Queue status rail
- Candidate Pending display
- Existing Confirm / Rename / Parking / Current Topic / Resolve controls
- 2〜5秒のUI Render coalescing

**Acceptance Criteria**

- PartialでMapが変わらない。
- CandidateとConfirmedが混同されない。
- Human CorrectionがAnalyzerで上書きされない。
- UI StateがCanonical Graphへ混入しない。
- Existing Node position / Topic Laneが安定する。

**Dependencies**

- L3
- Existing M4 / M5 UI and commands

### L5 — Session Drain / Failure Handling

**Goal**

End Session後にAudio、STT、Utterance、Analyzer、Graphを安全にDrainする。

**Deliverables**

- `active / finalizing / ended`
- Drain Complete判定
- 30秒Timeout
- Partial / Failed終了状態
- STT / Analyzer Manual Retry
- Privacy / retention cleanup

**Acceptance Criteria**

- Stop後に残りAudioを取りこぼさない。
- Drain Completeの条件をDeveloper UIで確認できる。
- Timeoutで無限待機しない。
- 未処理Evidence IDを失わない。
- Final Graph revisionとlast completed sequenceが記録される。

**Dependencies**

- L2〜L4
- Existing `session_finalizing` / `session_ended` contract

### L6 — Live Evaluation Harness

**Goal**

10〜15分のLimited Liveを評価可能なSessionとして記録する。

**Deliverables**

- System / semantic / human metrics
- Evaluation Markers
- Participant feedback form
- Session evaluation artifact
- Replay / failure report

**Acceptance Criteria**

- API key、Authorization、不要なRaw AudioがArtifactに入らない。
- Latency / queue / failures / correctionsを再集計できる。
- Critical Safety ErrorとCritical Information Recallを判定できる。
- Participant feedbackと自動Metricsを分離して保存できる。

**Dependencies**

- L1〜L5
- Participant consent and room script

## 23. First Vertical Slice

最初に通すのは15分Sessionではなく、1つの明示的な発話である。

```text
Start Live Session
  → one participant speaks one short Japanese sentence
  → AudioWorklet frame
  → Local WebSocket
  → STT committed/final completion
  → Final Utterance / Normalization v2
  → FIFO Queue
  → analyzer-prompt-v4
  → Candidate Event
  → Event Store
  → Materializer
  → Projection
  → Map update
  → evidence / latency trace
```

このVertical Sliceでは、Partial、Human Command、Minutes、Persistenceを同時に扱わない。Graphへ入るのはFinal Utteranceだけである。

## 24. Development Steps

### Step 1 — One Utterance Manual Test

- **前提**: L1〜L2が完了。
- **作成対象**: Start / Stop、1 Audio turn、Final Evidence。
- **テスト方法**: 1発話を録音し、Partial / Final / timestampを確認。
- **完了条件**: Final completion 1件、Graph更新はAnalyzer成功後だけ、Evidence traceあり。

### Step 2 — 2〜3 Utterance Sequential

- **前提**: Step 1のFinalizationが安定。
- **作成対象**: FIFO、single Analyzer Worker、Map update。
- **テスト方法**: Topic → Idea → No-opまたはActionの順で話す。
- **完了条件**: sequence順、No-opでGraph不変、Mapが逐次成長。

### Step 3 — Queue Stress Simulation

- **前提**: L3が完了。
- **作成対象**: Artificial Analyzer delay、failure injection、retry。
- **テスト方法**: 発話をAnalyzer処理より速く送り、Queue / Backpressureを観察。
- **完了条件**: Evidence dropなし、out-of-orderなし、queue depth / delayed表示あり。

### Step 4 — 2〜3 Minute Live

- **前提**: L4、L5の基本Failure / Drainが完了。
- **作成対象**: Room audio、2〜3 participants、Shared Map。
- **テスト方法**: Topic transition、Topic Return、Candidate、Human Correctionを含む短Session。
- **完了条件**: Crash 0、Auto Confirm 0、E2E / queue metricsが収集可能。

### Step 5 — 10〜15 Minute Limited Live

- **前提**: Step 4のStop Conditionsを満たす。
- **作成対象**: Full Limited Live Session and Evaluation Artifact。
- **テスト方法**: 同意を取得した会議をSession Scriptに沿って実施。
- **完了条件**: Live Prototype Success Criteriaを判定し、参加者FeedbackとMarkersを含むReviewを作成。

## 25. Automated Tests

最低限、次を追加する。L1/L2の既存112 TestsとL3追加Testsは全件Greenを維持する。

- Audio chunk lifecycle: start / append / flush / stop
- Microphone permission boundary
- Audio sequence and timestamp monotonicity
- STT response parsing
- Partial does not mutate Graph
- Final completion enters Finalizer exactly once
- Normalization v2 trace retention
- FIFO ordering
- Analyzer single-worker ordering
- Queue state transitions
- Retry idempotency
- STT failure isolation
- Analyzer failure isolation
- Queue depth and delayed state
- Session finalization drain
- Drain timeout and partial end
- Human Command interleave
- Revision mismatch / Human priority
- No automatic Decision confirmation
- Replay after Live final Event stream
- Raw Audio retention cleanup
- No secret in logs / artifacts

## 26. Existing Regression and Non-goals

既存M1〜M6、Recorded Analyzer、STT、Normalization、CompactionのContractを変更しない。初回Liveでは実装しないものは次のとおり。

- Production persistence
- Authentication
- Multi-room / multi-user collaboration
- Online meeting integration
- Minutes generation
- Visual Artifact generation
- Type D Multi-turn layer
- Prompt v5
- Automatic Decision confirmation
- Partial Transcript Graph update
- Semantic Drop / Noise Guard as quality logic
- Parallel Analyzer Workers

## 27. Remaining Operational Follow-up

Canonical Contract上の新しいMust Resolveはない。L1〜L5で実装判断した項目と、実室内評価までに残るOperational Decisionsを分けて記録する。

**L1〜L5で確定済み**

1. Audioだけを隣接Local WebSocketへ送り、既存HTTP Control APIは維持する。
2. BackendからRealtime transcription WebSocketへ接続し、`gpt-transcribe`のexplicit commit / Final eventを使う。
3. Browserの入力レートを明示的に24 kHz mono PCM16LEへ変換する。
4. ContinuousはFIFO QueueとSingle Analyzer Workerを使い、Renderだけをcoalesceする。
5. End Sessionは`finalizing`でSTT / Queue / Analyzer / Materializer / Projectionをdrainする。

**実室内評価までの残項目**

1. Raw AudioのEvaluation保存に対する参加者ConsentとRetention期限。
2. 初回SessionのObserver、Room、External Microphone、Session Script。
3. macOS microphone permission、室内音響、Input Level / clipping対策。

これらは設計上の確認事項であり、Prompt、Schema、Materializerを変更するBlockerではない。

## 28. Implementation Readiness

**Plan Ready / L1-L2 + First Vertical Slice + L3 + L4/L5 Implemented**。

L1〜L2とStep 1の1発話Vertical Slice、L3のQueue / Analyzer Worker、L4 Continuous Live Map、L5 Session Drain / Failure Handlingを実装し、自動テストと短時間の実Provider接続確認を完了した。L6 Live Evaluation Harness、10〜15分の参加者評価、Live Microphone 3-case Manual Acceptanceには進んでいない。

## 29. L1-L2 Implementation Record

- **Audio Capture**: Browser Web Audio API + AudioWorklet。AudioWorkletはmono Float32 PCMの取得・フレーム転送だけを担当し、Main Threadで入力サンプルレートから24 kHzへ明示的にresampleする。
- **Transport**: 既存HTTP Control APIを維持し、AudioのみをPython隣接WebSocketへ送る。依存は最小の`websockets`ライブラリ。
- **Realtime STT**: BackendからOpenAI dedicated Realtime transcription WebSocketへ接続し、`gpt-transcribe`、24 kHz mono PCM16 little-endian、runtime prompt / keywordsを使用する。1発話Sliceでは明示Stopから`input_audio_buffer.commit`を送り、providerのFinal completionを待つ。
- **Analyzer boundary**: PartialはRuntime Debug表示だけ、FinalだけをNormalization v2 → 既存Real Analyzer（`analyzer-prompt-v4` / provider output schema v2）へ渡す。Canonical Event / Materializer / ProjectionはRecorded Pipelineと同じものを使う。
- **Evidence**: Canonical Evidenceは変更せず、Runtime traceに`evidence_id`、audio start/end、raw STT、normalized text、utterance sequenceを保持する。
- **One-Utterance UI**: 明示的なStart後にMicrophoneを取得し、Stop / Commitで1発話をFinal化する。Mic / WebSocket / STT / Analyzer / Graph revision / Map更新 / Partial / Finalを表示する。
- **Raw Audio**: Runtime bufferのみ。永続保存しない。

自動テストはL1/L2の112件にL3の8件を加えた120件がGreen。実Providerでは3種類のTTS音声をRealtime STTへ送り、Topic / Candidate Decision / ActionのFinal → Analyzer → Graph → Map経路を確認した。Browserのマイク権限・室内音響を含む実マイク評価は、macOS permission制約により引き続きPendingである。

## 30. L3 Queue / Analyzer Worker Implementation Record

- **Runtime boundary**: `prototype/live_queue.py` にCanonical Domainとは分離したIn-memory FIFO QueueとSingle Analyzer Workerを追加した。Queue itemは`queue_item_id`、utterance sequence、evidence ID、normalized text、enqueue時刻、state、retry count、処理時刻・Latencyを保持する。
- **Ordering**: Queueは`utterance_sequence`でFIFO処理し、Audio Chunk Sequence / Utterance Sequence / Canonical Event Sequenceを相互流用しない。Canonical Eventのtotal orderとsequence採番は従来どおりEvent Store / Materializer側に残した。
- **Context**: Analyzer開始時に最新のCanonical Graph / Recent Eventsを読み込む。enqueue時のGraph Snapshotは固定しないため、前ItemのMaterializer結果とHuman Commandを後続Itemが参照できる。
- **Failure / Retry**: Analyzer failureは`failed`としてEvidenceを保持し、後続Itemは継続する。Manual Retryは同じEvidence ID / Utterance Sequenceを維持し、L3では現在Graphへ末尾Appendする。既存後続Eventを過去位置へ黙って挿入しない。
- **Revision conflict**: Analyzer処理中にHuman CommandでGraph revisionが変わった場合は最新Graphへ一度だけ再解析する。再解析中にもrevisionが変わった場合はstale candidateを適用せず`revision_conflict`として失敗させる。
- **Backpressure / metrics**: EvidenceやUtteranceはdropせず、pendingを保持して`normal` / `delayed` / `critical`を表示する。Queue depth、max depth、processing / last completed sequence、failed count、queue wait、Analyzer / E2E latencyをsnapshotへ公開した。
- **Developer UI**: 既存Live panelへQueue depth、processing sequence、last completed sequence、failed count、queue wait p50/p95、delayed stateを追加した。Shared MapのデザインとL4のRender Coalescingは変更していない。
- **Tests**: 3 / 10 / 20 utterance burst、failure isolation、retry、latest Graph Context、Human Command interleave、one-time re-analysis、second revision conflict、Replay Determinismを追加し、L1〜L3の120 TestsがGreen。

## 31. L4 Continuous Live Map Implementation Record

- **Runtime state**: `LiveContinuousSession`を追加し、`starting → active → finalizing → ended`をRuntime-onlyで管理した。既存One-Utterance Sessionとはmodeを分離し、Startはactive中に冪等である。
- **Continuous input**: Final STTだけをNormalization v2へ渡し、Evidence / Utterance sequenceを採番して既存L3 FIFOへ非同期投入する。Partial Transcriptはdebug表示だけで、Analyzer / Graphへは渡さない。
- **Canonical path**: Final Utteranceは既存Analyzer → Candidate Event → Event Store / ReplayRunner → Materializer → Graphをそのまま通る。Canonical Contract、Analyzer Contract、Materializerは変更していない。
- **Render coalescing**: Canonical GraphはItemごとに更新し、通常のMap / Status / Recent Flowだけを2秒間隔のRuntime coalescerへ渡す。Human Command、Failure、Final Projectionは即時Renderする。`graph_revision`と`rendered_revision`を公開し、差分がある場合は`Updating`を表示する。
- **Human Command**: Active中は既存Human Commandを使用可能。Command成功時はcoalescingを待たずProjectionを即時更新する。Finalizing後の新規MutationとRetryは無効化した。

## 32. L5 Session Drain / Failure Handling Implementation Record

- **Drain Contract**: End Sessionは直ちにendedへ遷移せず、`finalizing`でCapture停止、STT finalization、Queue pending / processing、Analyzer、Event append、Materializer、最終Projectionを順に待つ。完了後のみ`ended`へ遷移し、`rendered_revision == graph_revision`を確認できる。
- **Timeout**: Runtime timeoutは30秒を既定値とし、テストでは短縮可能。Timeout時は`ended_with_incomplete_processing`、`drain_timeout`、incomplete / failed queue item、last completed sequence、last graph revisionを保持する。Evidenceは削除しない。
- **Failure isolation**: STT / Browser / Transport failureは受信済みEvidenceとGraphを保持し、Queue failureは`failed`として後続Itemを継続する。Failed Itemが残っていてもpending / processingが空ならDrain Completeとした。
- **Shutdown / reconnect scope**: Production persistence、自動Reconnect、Live中のSemantic Dropは未実装。WorkerはIn-memoryで、次Session開始時またはDeveloper shutdown時に閉じる。

## 33. L4/L5 Verification Record

- **Automated tests**: L4/L5用10件を追加し、既存120件と合わせて130件がGreen。Render coalescing、Human immediate render、Continuous start idempotency、Stop During Queue、Drain Timeout、Failure continuation、Finalizing mutation boundary、Replay Determinism、UI control surface、Continuous WebSocket Gateway routingを確認した。
- **Synthetic simulation**: `evaluation/live/l4-l5-continuous-simulation.json`にNormal 10件、Burst 20件、Analyzer Failure、Human Command interleave、Stop During Queue、Drain Timeoutを保存した。Normal / Burst / StopはEvidence loss 0、FIFO、Drain Complete、Replay可能。Failureでは後続Itemが継続しFailed Itemを保持した。
- **Real Provider short check**: `evaluation/live/l4-l5-real-provider-short.json`に、既存60秒PCMを高速投入した短時間確認を保存した。`gpt-transcribe` Final 4件、Partial 108件、Analyzer / Graph update 4件、Map render 5件、Drain Complete、Final revision一致を確認した。Queue wait p50/p95は0.001595/0.002987秒、Analyzer p50/p95は2.762092/3.204281秒、Map E2E p50/p95/maxは4.753729/5.936411/5.936411秒、Drainは0.000182秒だった。高速投入のためlatencyはBurst相当であり、実室内のRealtime acceptance値とは分離する。

L1/L2の実Microphone 3-case Manual Acceptanceは、macOS microphone permission制約により引き続きPendingである。L4/L5完了後はここで停止し、L6 Live Evaluation Harness、10〜15分のHuman Session、Participant Feedback、Minutes、Visual Artifact、Production Persistenceへは進まない。

## 34. Item-scoped Realtime Finalization Repair

T2のfollow-upでは、Provider item Aの明示commit待ちと別のVAD item Bの空完了が
混同される競合を実Providerで再現した。`live_turns.py` の接続単位ledgerで以下を分離する。

- 未commitのsample範囲、明示commit intent、Provider item、受信済み完了の処理待ち。
- 各appendのsample範囲と無音判定だけをledgerへ記録。音声の永続保存はしない。
- commit送信は予約であり成功ではない。`committed` のitem ID、VAD end offset、
  ローカル送信watermarkで担当範囲を対応付ける。範囲はローカルの音声管理範囲であり、
  Provider内部のprefix paddingまで含む厳密な認識範囲とは区別する。
- `previous_item_id` に従って完了の順序を整え、Finalだけを従来のNormalization / Queueへ渡す。
  重複itemは再登録しない。古いitemの完了で新しい未commit音声をクリアしない。
- 無音と確認できた自動VAD itemの空完了のみbenign。明示item、意味のある音声、
  範囲不明のemptyは失敗を維持する。非空Finalでも対応範囲不明・重複範囲は失敗を明示。
- VADが先に処理した終了時commitが `input_audio_buffer_commit_empty` になった場合は、
  単一intentの対象音声をVAD itemが既に担当し、未担当の末尾が無音と確認できる場合だけ
  intentを解消する。VAD item自体の完了待ちは解除しない。これはempty transcriptionの無視ではない。
  送信event IDを付け、Providerが返す関連IDが異なる場合は解消しない。
- 30秒boundは未commit範囲に適用。古いitemの完了待ちで新しい音声のboundを止めない。
  commit/item未解決には既存Provider timeout設定を適用し、期限切れは不完全終了。
- Endは未commit音声をflushし、全itemのアプリ側処理とQueue/Analyzer/renderの完了を待つ。
  Provider failureで残ったintentがDrainを永久に妨げないよう、失敗時は不完全終了へ進める。

generic default `none`、Pilotの `server_vad_bounded` / 30秒、モデル、Context、keywords、
Analyzer、Canonical、Shared Viewは変更しない。これはローカル実装であり、自動デプロイしない。
実Provider検証は隔離process・synthetic入力・Noop Analyzerなので、T2本番や実会議の品質評価を
代替しない。詳細はReal-world Evaluation文書のitem-scoped repair記録を参照。
