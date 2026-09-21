# Limited Live Audio Pilot Protocol

## Purpose

このPilotは、2〜3人の日本語Discussionで、`Audio → STT → Analyzer → 論点図` が実時間で動作し、参加者が論点図を見ながら議論できるかを検証する。精度の証明、Production Meeting Assistant、Minutes生成は目的にしない。

## Frozen Configuration

- STT: `gpt-transcribe` + terminology hints
- Normalization: v2
- Analyzer: `gpt-5.6-luna`, reasoning `medium`
- Prompt: `analyzer-prompt-v4`
- Context: v1
- Type D: OFF
- Presentation Compaction: ON
- Open Item Lifecycle: ON
- Map render coalescing: 2 seconds
- Human Command: immediate render
- Partial Transcript: debug display only; Canonical Graphへ投入しない
- Open Item Resolve: Human-only
- Automatic Decision Confirmation: disabled

## Participants and Environment

- 2〜3 participants, Japanese discussion
- 1 room, 1 facilitator/observer
- Laptop or small desktop with an external microphone
- One shared display showing the 論点図
- 10〜15 minutes, one running session
- No production persistence, authentication, online meeting integration, Minutes, or Visual Artifact generation

## Discussion Theme

参加者には次のGoalだけを提示し、発言内容は台本化しない。

> 論路を社内会議で使う場合、どんな機能が必要か。

自然なTopic transition、Idea、Concern、Open Item、Strong Decision、Action、Digressionが発生するよう促してよいが、特定の文言を要求しない。

## Pre-flight Gate

Pilot当日に次をObserverが実機で確認する。いずれかに失敗したらPilotを開始しない。

1. Shared DisplayとFacilitator SmartphoneがNetBird Private Networkへ接続されている。
2. NetBird未接続端末から`ronro.hakobune8.com`へ到達できない。
3. Microphone permissionを明示的Start後に取得できる。
4. Topic発言がFinal Transcriptとして取得される。
5. Candidate Decisionが`candidate`として論点図へ入り、Confirmedにならない。
6. Action発言がEvidenceからActionへ追跡できる。
7. End SessionでFinalizing、STT/Queue/Analyzer/Graph/ProjectionのDrainが完了する。
8. `rendered_revision == graph_revision` を確認できる。
9. 最初にStartしたControllerがActive Controllerとなり、別端末がStart / End / Audio controlを奪えない。
10. Active Controllerの短時間reload / Network interruptionでSessionが即終了せず、同一BrowserがReconnectできる。

L1/L2の実Microphone 3-case AcceptanceがPendingのままの場合は、これをPilot開始の必須Pre-flightとして扱う。

## Procedure

### Before Start

1. 参加者へ、Microphone使用、音声のTranscription、Raw Audio保持、Evaluation Log保持の方針を説明する。
2. Raw Audioは既定で保存しない。保存する場合だけ、明示同意を取得する。
3. `Evaluation Mode`で参加者数とDiscussion Themeを入力する。
4. Observerは、開始時刻、参加者数、環境、Consent状態を確認する。
5. `Start Evaluation`後、Pilot Controller（`/session`）で会議を開始する。Controller未実装の確認時はFacilitatorの`/control`をFallbackとして使用する。
6. Controllerは前面表示し、画面をLockしない。Background AudioはPilotの前提にしない。

### During Discussion

- 参加者はDiscussionを優先し、採点しない。
- Observerだけが一クリックMarkerを使用する。
- `helpful`: 論点図が議論を助けた場面
- `distracting`: 論点図の更新が気を散らした場面
- `wrong`: 明らかな誤り
- `important_miss`: 重要なTopic/Decision/Open Item/Actionの取りこぼし
- `looked_at_map`: 参加者が論点図を見たことを記録できる場合のみ使用
- Human Commandは必要な場合だけ使用し、Rename/Merge/Parking/Topic Override/Decision Confirm/Open Item Resolve/Action Updateの回数を自動記録する。
- Partial TranscriptはDebug表示に限り、PartialをGraphへ反映しない。

### End

1. 10〜15分で`End Session`を押す。
2. Runtimeが`finalizing`へ遷移し、最後のFinal TranscriptとQueueをDrainすることを待つ。
3. `ended`、最終Graph Revision、Rendered Revision、failed countを確認する。
4. 参加者は短い5段階Feedback（4〜6問）に回答する。
5. Observerは論点図の品質Rubric、Helpful/Distracting/Wrong/Missingの要約を入力する。
6. ObserverはPost-session GoldenとしてMain Topics、Strong Decisions、Important Open Items、Actionsを記録する。

## Observer Responsibilities

- Discussionを誘導しすぎない。
- Errorや遅延を発見した時だけMarkerを残す。
- Session後に論点図の品質を1〜5で評価する。
- 特にDecision Safety、Current Topic、Open Itemの可視性を確認する。
- most helpful moment / most distracting moment / most important wrong item / most important missing itemを記録する。

## Feedback Questions

各項目を1〜5で回答する。Q4は高いほど邪魔だったことを示す。

1. 論点図は議論の全体像を理解するのに役立った。
2. 今何について話しているか把握しやすかった。
3. 決定候補や未解決事項の表示は役立った。
4. 論点図の更新が議論の邪魔になった。
5. この論点図を実際の会議でも使いたい。

任意コメントは1件だけ入力する。

## Automatic Metrics

`evaluation/live/sessions/<session-id>/`へ以下を保存する。

- audio duration、Final/Partial count、STT/Analyzer failures
- queue max depth、queue wait p50/p95/max
- Analyzer latency p50/p95/max
- End-to-End latency p50/p95/max
- Graph update count、Map render count、Final Graph/Rendered revision
- Topic、transition、Candidate/Confirmed/Revoked Decision、Open/Resolved Open Item、Action、Parking
- Human Command type別回数、Correction Rate、Candidate Confirmation Rate

## Pilot Success Criteria

Production Gateとは分け、初回Prototypeの暫定基準とする。

- Pipeline crash = 0
- Graph corruption = 0
- Automatic Confirmation = 0
- Evidence loss = 0
- Critical Information Recall >= 0.85
- Map Quality >= 3.5
- Median E2E <= 5 seconds
- p95 E2E <= 10 seconds
- Queue runaway = 0
- 参考値: Q1 usefulness >= 4、Q2 current topic >= 4、Q4 distraction <= 2.5

## Abort Criteria

次のいずれかが発生したら、その場で新しい発話の取り込みを止め、EvidenceとGraphを保持してSessionを終了する。

- Graph corruption
- Automaticまたは誤ったConfirmed状態の反復
- Evidence loss
- 20秒を超える遅延が継続する
- Queueが収束せずrunawayになる
- Microphone/TranscriptionのPrivacy説明と実際の保持方針が一致しない
- Browser/Backend障害でSession状態が観測不能になる

## Privacy and Retention

- Microphone active / TranscribingをUIに表示する。
- Raw Audioはデフォルトで永続保存しない。
- Evaluation ArtifactはSession metadata、metrics、markers、Graph/Projection、Feedback、Observer Review、Post-session Goldenを保存する。
- 個人名や参加者のPIIはmetadataへ入れない。
- Raw Audioを保存する場合は、開始前に明示同意を取り、同意のないSessionへAudio Artifactを作らない。

## Artifact and Report

Session終了後に次を生成する。

```text
evaluation/live/sessions/<session-id>/
├── metadata.json
├── runtime-metrics.json
├── markers.json
├── graph-final.json
├── projection-final.json
├── snapshots/05min.json
├── snapshots/10min.json
├── snapshots/15min.json
├── participant-feedback.json
├── observer-review.json
├── post-session-golden.json
└── comparison.json
```

Reportは`docs/evaluation/live-session-<session-id>.md`へ生成する。Raw Audioは明示的なConsentがない限り、この構造へ含めない。

## Stop Point

このProtocolの準備完了はPilotの実施完了を意味しない。Pre-flightを通過し、参加者への説明とConsentが完了した時点で初めて、別途Pilot開始を判断する。
