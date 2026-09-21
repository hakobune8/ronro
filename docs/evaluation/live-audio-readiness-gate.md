# Live Audio Readiness Gate Review

## 結論

判定は **A. Ready for Limited Live Audio Prototype** です。

ただし、これはRecorded Analyzerの品質をMVP acceptanceとして合格とする判定ではありません。今回の目的は、Recorded Pipelineでは観測できないマイク・部屋・話者重複・finalization・queueing・人間の注意コストを、限定されたLive Prototypeで発見することです。

`Map Quality >= 4.3` は **Live Prototypeの開始条件としては維持しません**。一方で、MVP acceptance / Production Gate向けの品質目標としては維持します。

今回の判定では、次を前提とします。

- Prompt baselineは `analyzer-prompt-v4` に戻す。
- Prompt v5はExperimental Resultとして保持し、採用しない。
- Partial TranscriptはCanonical Graphへ適用しない。
- Candidate DecisionはPendingのまま表示し、Automatic Confirmationは行わない。
- Open Item ResolveはHuman-onlyとする。
- Liveは観測用の限定Prototypeであり、Production利用ではない。

コード、LLM API、STT APIの変更・呼び出しはこのReviewでは行っていない。

## Current Recorded Quality

Baselineは、保存済み `gpt-transcribe + terminology hints` の結果を `Normalization v2`、`analyzer-prompt-v4`、既存Materializer、Presentation Compactionへ通したものとする。

| Metric | Current value | Prototype assessment |
|---|---:|---|
| Clean Map Quality | 4.8 | 良好 |
| STT Map Quality | 4.0 | 読みづらさはあるが、探索的Liveでは許容可能 |
| Critical Information Recall | 1.0 | Pass |
| Category Recall | 0.9048 | Pass |
| Topic Precision / Recall | 1.0 / 1.0 | Pass（主要6 Laneのsemantic評価） |
| Action Precision / Recall | 1.0 / 0.625 | Recallは未達。Secondary quality issue |
| Strong Decision Precision | 0.125 strict / 0.25 semantic | Candidate過多。Pending表示が必須 |
| Critical STT Error | 0 | Pass |
| Automatic Confirmation | 0 | Pass |
| Invented Owner / Due | 0 / 0 | Pass |
| Duplicate Topic | 0 | Pass |
| Analyzer latency | p50 約2.8秒 / p95 約4.2秒 | Live E2Eで再計測が必要 |
| Terminology STT RTF | 0.0570（Recorded batch） | Realtime性能とはみなさない |

Strong Decision Precisionが低いという欠陥は残るが、誤CandidateがConfirmedへ遷移する経路は存在しない。Primary Product Hypothesisの検証に必要なCurrent Topic、Topic Structure、Candidate / Confirmedの区別、Open Itemの可視化は成立している。

## Gateの種類

### Live Prototype Gate

未知のRuntime問題を発見できる最低条件。品質を完成させるGateではなく、壊れず、安全に観測できることを重視する。

### MVP Acceptance Gate

参加者が継続利用しても、誤ったCandidate・抜けたAction・読みにくいMapが許容範囲内であることを確認するGate。今回のBaselineはまだここを満たしたとは判定しない。

### Production Gate

安定運用、Privacy、Persistence、複数ユーザー、障害復旧、監査、SLOを含むGate。今回の対象外であり、Recorded品質から推論しない。

## Liveで初めて検証できること

Recorded Transcriptを追加改善しても、次のRuntime特性は検証できない。

- microphone quality、room acoustics、background noise
- 2〜3人の複数話者とspeaker boundary
- overlapping speech、割り込み、同時発話
- streaming chunk boundaryとend-of-utterance detection
- Finalization delayと遅れて確定する発話
- Network latency、request timeout、再試行
- Incremental STTがFinal Textへ収束する過程
- Analyzer queueing、処理順、backpressure
- Map update cadenceとShared Display上のちらつき
- 参加者がCurrent Topicを追えるか
- Mapを見たことによる注意コスト、議論への介入、Human Correctionの自然さ

このため、Prompt v6やSTTの追加調整だけを続けても、Live開始後に初めて発見できるリスクは減らせない。

## Defect Classification

### Critical

Recorded Baselineで確認されたCritical Defectはない。

- Automatic Confirmation: 0
- Negation / Decision / Action meaning reversal: 0
- Invented Owner / Due: 0
- Duplicate Topic: 0
- Canonical Graph corruption: 0
- Replay Determinism failure: 0

ただし、Liveでこれらが発生した場合は品質問題ではなく即時Stop Conditionとする。

### Tolerable Prototype Defect

- STT Map Quality 4.0
- Strong Decision Candidateの過検出
- Action Recall 0.625
- Technical Termの表記崩れ
- Open Itemの余分な候補
- Speaker Attributionが未検証
- Recorded batchでは得られないFinalization / queue latency

これらはLive中に計測・観測できる。CandidateはPendingとして明示し、Actionは完全抽出を主張せずHuman Updateを利用する。

### Cosmetic / Quality

- Labelの言い換え・表記揺れ
- Cardの細かな密度調整
- Recent Flowの表示件数
- Status Railの要約文
- Compactionの見た目

## Weak DecisionのSafety評価

Weak Decision過検出は無視できないが、現行のDecision Lifecycleでは次の安全境界がある。

1. AnalyzerはCandidateまでしか生成できない。
2. CandidateはPending / CandidateとしてConfirmedと視覚的に区別する。
3. ConfirmはHuman Commandだけで行う。
4. Revoke / Rename / Merge等のHuman CorrectionはEventとしてReplay可能。

したがって、Limited Liveで「候補がどの程度ノイズになるか」を測定することは可能である。ただし、候補をPopupで即時Confirmさせると議論を誘導するため、初回LiveではDecision RailへのPassive Pending表示を採用する。

以下は許容しない。

- CandidateをConfirmedと表示する。
- Candidate生成時にConfirmを促す強い割り込みを出す。
- AgreementやSTTの曖昧さだけでConfirmedへ遷移する。

## Action Recallの評価

Action Recall 0.625はMVP acceptanceでは改善対象だが、Live PrototypeをBlockするCritical Defectとはしない。

理由は次のとおり。

- Primary HypothesisはMinutesの完全なAction抽出ではなく、Discussion Structure / Current Topic / Decision / Open Itemを共有画面で理解できること。
- Action Precisionは1.0で、誤Actionを大量に確定している状態ではない。
- Human `update_action` で修正できる。
- LiveではActionのMissを実会議で計測し、録音・STT・Analyzer・UIのどこで失われるか確認できる。

ただし、Actionを完全に扱えると説明してはならない。初回Liveの説明文では「Actionは補助的な候補抽出」と明示する。

## Opportunity Cost

|追加でRecorded改善|限定Liveへ進む|
|---|---|
|Prompt v6でDecision分類をさらに調整できる|実マイク・部屋・重複発話を初めて検証できる|
|STT terminology / Providerを比較できる|Finalization delayとStreaming boundaryを測れる|
|Analyzer Ruleを増やせる|Queueing / Backpressure / Map cadenceを測れる|
|OfflineのPrecision / Recallを上げられる|参加者がMapを見続けられるか測れる|
|既知の問題を減らす情報が得られる|現状のMapが議論を助けるか、邪魔するかの情報が得られる|

今回のPrimary Product Hypothesisは後者を含む。したがって、RecordedのQuality Scoreだけを理由にLiveを延期するOpportunity Costが大きい。

## Map Quality 4.3 Gateの再評価

**回答: No。Live Prototype開始条件としては維持しない。**

4.3は、MVP acceptance / Productionに向けた品質目標としては有効である。しかしLive Prototypeに同じ閾値を適用すると、Live固有の未知問題を一切測らないままOffline改善を続けることになる。

代わりに、Live Prototypeでは次の複合Gateを使う。

- Critical Information Recall >= 0.85
- Automatic Confirmation = 0
- Critical Safety Error = 0
- Graph corruption = 0
- Median finalization-to-map update <= 5秒
- p95 finalization-to-map update <= 10秒
- Map Quality >= 3.5
- 参加者がCurrent Topicを理解できる割合 >= 80%

Map Quality 4.0はこの探索Gateを満たすが、MVP acceptanceの4.3を満たしたことにはならない。

## Recorded vs Live Gates

|Criterion|Recorded current|Required for Limited Live|Status|
|---|---:|---:|---|
|Critical Information Recall|1.0|>= 0.85|Pass|
|Map Quality|4.0|>= 3.5 exploratory|Pass（要観測）|
|Decision Safety|Auto Confirm 0、Critical 0|0|Pass|
|Action Recall|0.625|Hard gateにしない。Baselineとして記録|Conditional|
|Topic P / R|1.0 / 1.0|>= 0.85 / 0.85|Pass（主要Lane評価）|
|Latency|Analyzer p50 2.8秒 / p95 4.2秒。Live E2E未計測|median <= 5秒、p95 <= 10秒|Unknown / Liveで計測|
|Replay|Deterministic|Final Event固定後も再現可能|Pass|
|Evidence traceability|Raw / normalized traceあり|Final evidenceを失わない|Pass|
|Failure isolation|既存Graphを壊さない|STT / Analyzer failureでGraphを壊さない|Pass（Liveで再確認）|

LatencyだけはRecordedからPass判定できない。これはBlockerではなく、Live Prototypeの主要測定項目である。

## Proposed Live Latency Budget

`Finalized Utterance`確定からMap反映までを計測する。

|Level|Target|
|---|---:|
|Target|median <= 5秒|
|Acceptable|p95 <= 10秒|
|Degraded|単発で10秒超。表示は遅延状態を示す|
|Stop / investigate|20秒超が連続、またはMapが追いつかない状態が30秒以上|

初回の実装計画では、Analyzer p50 2.8秒を基準に、Finalization・Network・Projectionの余裕を残す。STTのRecorded RTF 0.057はBatch値であり、このBudgetの根拠として直接使用しない。

## Update Cadence

初回Liveでは次の分離を推奨する。

- Canonical Event: Finalized Utteranceごとに順序どおり処理。
- Analyzer入力: Finalized Utteranceだけ。PartialはEvidence bufferに保持。
- UI render: 2秒程度のcoalescingを許可し、Canonical Eventの順序は変えない。
- Candidate Decision: 即時PopupではなくPassive Pending。
- Map projection: Current TopicとCritical Railは次のrender tickで更新。

常時Semantic Batchにすると遅延原因が分かりにくくなるため、初回はPer-Utterance Event + 軽いUI coalescingを基準にする。

## Queue / Backpressure Policy

初回Liveの最小方針は次のとおり。

1. Finalized Utteranceをsequence付きFIFO Queueへ入れる。
2. Analyzer workerは1本とし、Event適用はsequence順に限定する。
3. 処理中に次の発話が来てもEvidenceは保持する。
4. 低価値な発話を勝手に捨てない。Noise GuardはBaselineの品質測定から切り離した任意のCost Optimizationとする。
5. UIだけを2〜5秒coalesceし、Canonical Eventはcoalesceしない。
6. Queueが増えた場合は遅延表示を出し、最初のPrototypeではDelayed Processingを優先する。
7. Queue depthが5を超える、または連続20秒以上増加する場合はBackpressure状態として記録する。

Analyzerが追いつかない場合の優先順位は、`queue → delayed processing → 明示的な実験用coalesce` である。Semantic Utteranceを無言でdropする方針は採用しない。どうしても終了時に未処理が残る場合は、未処理Evidence IDを明示し、Graphへ適用しない。

## Initial Live Prototype Scope

- 1 room
- Japanese
- 2〜3 participants
- 10〜15分
- Laptop + external microphoneを基本とする
- 1つのShared Display
- Manual Start / Stop
- Finalized Utterance only
- Production persistenceなし
- Authentication / multi-userなし
- Minutesなし
- Visual Artifactなし
- Type D OFF
- Open Item ResolveはHuman-only
- Candidate ConfirmはPauseまたは人間の明示操作時だけ

目的は精度の証明ではなく、`Audio → STT → Analyzer → Map` が会話を壊さず、人間がMapを見ながら議論できるかを確認することである。

## Live Metrics

### System / Pipeline

- microphone input level / dropout
- STT finalization latency: p50 / p95 / max
- Analyzer latency: p50 / p95 / max
- finalization-to-map update end-to-end latency
- queue depth over time
- timeout / retry / provider failure
- dropped / coalesced / delayed utterance count
- Canonical Event / Graph revision
- Map update count and cadence

### Semantic / Safety

- Topic continuity and Topic Return
- Current Topic correctness
- Candidate Decision count、Strong / Weak / False review
- Automatic Confirmation count
- Invented Owner / Due count
- Critical Information Recall
- Action candidate count and sampled Action Recall
- Open Item count、Resolve / Reopen count
- Duplicate Topic / Graph corruption

### Human Interaction

- Mapを見た回数、または視線確認の自己申告
- Human Correction回数
- Candidate Confirm / Leave Pending / Revoke回数
- Mapが議論を助けた場面
- Mapが邪魔だった場面
- Current Topicを理解できたか
- 会議後のUsefulness rating

## Success Criteria

初回Limited LiveのSuccess CriteriaはProduction基準より低く設定する。

- Pipeline crash: 0
- Graph corruption: 0
- Automatic Confirmation: 0
- Negation / Decision / Action reversal: 0
- Evidence loss: 0
- Critical Information Recall: >= 0.85
- Median finalization-to-map update: <= 5秒
- p95 finalization-to-map update: <= 10秒
- Map Quality: >= 3.5
- Current Topic理解: 参加者の80%以上
- Map usefulness: 5段階で平均3以上
- 終了時に未処理Utteranceがある場合、全件をEvidence ID付きで報告可能

Action Recall 0.625を初回LiveのHard Failureにはしないが、Baseline値として必ず記録する。MVP acceptanceへ進むには、Action RecallとStrong Decision Precisionを別途改善する。

## Stop Conditions

次のいずれかが起きた場合、Live Testを停止または即時Pauseする。

- Confirmed表示がHuman Confirmなしに発生する
- Decision / Actionの意味が反転する
- Graphが壊れる、Revision順序が不整合になる、Replay不能になる
- EvidenceまたはAudio timestampが失われる
- Queueが5を超えたまま増え続ける、または20秒超遅延が連続する
- Finalization-to-map updateが30秒以上停滞する
- Privacy / 録音同意 / 音声保存範囲に不明点が出る
- Partial TranscriptがCanonical Graphへ混入する
- CandidateがPopupで議論を繰り返し中断する

## Human Safety Net

初回LiveではHuman Correctionを品質補正だけでなく、観測データとして扱う。

- Confirm Decision: Candidateが本当に有用だったか
- Revoke: 誤Candidateがどれだけ出たか
- Rename / Merge: Label / Duplicateの補正量
- Parking / Current Topic: Topic Focusの自然さ
- Resolve Open Item: Open Item蓄積とLifecycleの妥当性
- Update Action: Action Recallの実用上の補正量

Correctionが多すぎる場合は、Safety Netがあるから成功とはみなさない。Mapが人間の修正作業を増やしている兆候として評価する。

## Decision

**A. Ready for Limited Live Audio Prototype**

限定Liveへ進む条件は満たしている。ただし、次段階はProduction実装ではなく、上記Scope・Metrics・Stop Conditionsを備えた実験である。

次に作成すべき成果物は、実装そのものではなく、次の計画書である。

`docs/implementation/live-audio-prototype-plan.md`

このPlanには、Runtime Configuration、録音同意・Privacy境界、Finalization-only pipeline、Queue / Backpressure、Instrumentation、10〜15分のSession Script、Stop / Rollback手順を含める。Planレビューが完了するまでLive実装は開始しない。

## Gate Summary

- 4.3 Gate: **Live PrototypeではNo。MVP acceptance / Production targetとしてKeep。**
- Current Recorded Quality: **限定探索には十分、実利用品質には未達。**
- Critical Defect: **Recordedでは0件。**
- Tolerable Defect: **Weak Decision、Action Recall、STT Label noise、Map Quality 4.0。**
- Queue / Backpressure: **FIFO、sequence順、Evidence保持、UI coalescing、silent drop禁止。**
- Initial Scope: **1 room / 2〜3人 / 日本語 / 10〜15分 / Shared Display / Finalized only。**
- Decision: **A. Ready for Limited Live Audio Prototype**
