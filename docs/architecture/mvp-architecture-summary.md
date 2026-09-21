# MVP Architecture Summary

| 項目 | 内容 |
| --- | --- |
| Status | Proposed Architecture Baseline |
| Scope | Discussion Map AI Facilitator MVP |
| Canonical RD | [discussion-map-ai-facilitator-mvp.md](../requirements/discussion-map-ai-facilitator-mvp.md) |
| Inputs | RFC-0001〜RFC-0005 |
| Last Updated | 2026-09-19 |

本書は、RDおよびRFC-0001〜RFC-0005を実装開始前に横断整理したArchitecture Baselineである。

新しい大規模設計を追加するのではなく、既存設計から次を明確にする。

- 実装開始時点で採用する責務境界
- Source of TruthとState Ownership
- RFC間で既に整合している設計
- まだ決める必要がある事項
- Prototypeで検証できる事項
- MVP後へDeferredできる事項

Canonical Pathは docs/requirements/discussion-map-ai-facilitator-mvp.md とする。既存RFCのMarkdownリンクはこの実在するPathへ整合済みであり、本書では設計内容を変更しない。

## 1. Product Goal

このシステムの中心価値は、会議中にDiscussion Mapを共有し、それを見ながら参加者自身が議論を理解・修正・前進できることである。

~~~text
Conversation
    ↓
Discussion Map
    ↓
Shared Understanding
    ↓
Better Discussion
~~~

Meeting Minutesは会議後のFinalization Step、Visual Artifactは議論を具体化するDiscussion Aidである。どちらも重要だが、Discussion Mapを会議中に利用できることがPrimary Valueである。

## 2. Architecture Review Result

### 2.1 結論

RDとRFC-0001〜RFC-0005は、次の中心方針において矛盾なく統合可能である。

- TranscriptはEvidenceであり、Current Stateそのものではない
- Event StreamはDiscussionの履歴と変更の基盤である
- Discussion GraphはEvent StreamからMaterializeされるCurrent Stateである
- Partial Transcriptは正規Graphを更新しない
- Candidate DecisionとConfirmed Decisionを分ける
- Human CorrectionはEventとして履歴に残し、Replay可能にする
- Discussion MapをPrimary Viewとして安定的に表示する
- Visual Artifactは独立Resourceとして非同期生成する
- MinutesはStructured Stateを中心に生成し、Evidenceで補強する

### 2.2 Canonicalization後の実装前状態

Prototype 1に必要な次のContractは、Domain / Event Schema、Event Catalog、Evaluation Fixturesで固定済みである。

1. Decision Confirmationは明示的なHuman Commandで行う
2. Actionは明示的な実行意図で生成し、Owner / DueはEvidence明示値またはnullとする
3. Human CorrectionはEventとしてReplayする
4. Current TopicはHuman Override、Parking時の解除、明示Focusによる復帰を持つ
5. supportsのNode Type Matrixを固定する
6. Prototype 1のCanonical Domain / Event最小集合を固定する

Session End後のFinal STT / Analysis DrainだけはLive Audio / STT依存のため、Prototype 1ではDeferredとする。Hysteresis、Cooldown、表示密度、Layout間隔などはValidation ParameterとしてPrototypeで調整する。

## 3. End-to-End Architecture

### 3.1 Live Discussion

既存RFCを統合した概念Flowは次のとおりである。

~~~text
Audio
  ↓
STT
  ↓
Transcript Evidence
  ↓
Final Utterance / Analysis Window
  ↓
Discussion Analysis
  ↓
Candidate Events
  ↓
Event Stream
  ↓
Graph Materializer
  ↓
Discussion Graph
  ↓
Discussion Map
~~~

各責務は次のように分かれる。

- Audio / STT: 音声をFinal Transcriptへ変換する
- Transcript Evidence: 発言内容、Timestamp、Provider MetadataをEvidenceとして保持する
- Utterance / Analysis Window: Final Utteranceを解析単位へまとめる
- Discussion Analysis: Topic、Idea、Option、Concern、Candidate Decision、Action候補、Topic Transition候補を生成する
- Event Stream: Candidate、Human Correction、Confirmation、Transition等を履歴としてAppendする
- Graph Materializer: Event StreamからCurrent Discussion Graphを構成する
- Discussion Map: GraphとUX Projectionを共有画面へ表示する

### 3.2 Partial Transcriptの扱い

Partial Transcriptは、Listening状態や処理中表示のために利用できるが、Canonical Discussion Graphを更新しない。

正規Graphの更新は、Final Transcriptに基づくFinal Utterance、Analysis Window、Candidate Event、Event Streamの順で行う。

### 3.3 Visual Artifact

Visual生成はLive AnalysisをBlockingしない。

~~~text
Discussion Graph
    +
Relevant Discussion Subgraph
    ↓
Context Snapshot
    ↓
Visual Intent
    ↓
Async Artifact Request
    ↓
Artifact Generator
    ├─ Diagram Renderer
    └─ Image Generator
    ↓
Visual Artifact Resource
    ↓
Discussion Map Marker / Visual View
~~~

生成開始後にDiscussion Stateが変化しても、ArtifactのContext Snapshotは要求時点のものを保持する。完成時にMapを自動更新したり、画面をVisualへ強制切替したりしない。

### 3.4 Session終了とMinutes

~~~text
End Session
    ↓
Finalization / Drain
    ↓
Final Discussion State
    +
Event Stream
    +
Human Correction
    +
Relevant Evidence
    +
Artifact References
    ↓
Minutes Context Snapshot
    ↓
Structured Minutes Projection
    ↓
Draft Minutes
    ↓
Deterministic / Semantic Validation
    ↓
Human Review
    ↓
Confirm / Finalize
    ↓
Markdown Export
~~~

### 3.5 既存RFCとの差分

上記Flowは、ユーザーが想定したFlowおよびRFC-0001〜RFC-0005と一致する。

追加の明確化は次のとおりである。

- Candidate EventはGraphを直接更新せず、必ずEvent Streamを経由する
- GraphはCurrent State、Event StreamはHistoryとして同じ情報を二重所有しない
- Visual生成はSession Finalizationを待たせない
- MinutesはGraphを中心に構造化し、TranscriptはEvidenceに限定する
- Session終了時には、最終数十秒のAudio / STT / Analysisを扱うfinalizing境界が必要である

## 4. Canonical Domain Model

JSON Schemaや具体的なDatabase Schemaは本書では作成しない。以下はMVPの概念モデルと責務である。

### 4.1 SessionとEvidence

| 概念 | 役割 | Source of Truth | Mutableか | Human Correction対象 |
| --- | --- | --- | --- | --- |
| Session | Discussionのライフサイクル、Title、Goal、開始・終了、状態を持つ | Session Metadata / Session Events | Session中は変化。Finalization後はRevision | 終了状態、Title、Goalの訂正 |
| Audio Buffer | STT前の音声区間。Finalization時のDrain対象 | Audio / Ingestion Boundary | 一時的。保持方針は別途 | 原則対象外 |
| Transcript Evidence | Final Transcript、Timestamp、必要なProvider Metadataを保持するEvidence | Evidence Store | Finalは不変。訂正は新Revision | Transcript Correction / 再解析の起点 |
| Utterance | Final TranscriptをDiscussion Analysisの単位に区切ったもの | Utterance Evidence Projection | Final後は不変。再分割は新Revision | 直接上書きせず再処理 |
| Discussion Event | Analysis、Confirmation、Correction、Transitionなどの履歴単位 | Event Stream | Append-only | 新しいCorrection Eventで変更 |

### 4.2 Discussion GraphのEntity

| 概念 | 役割 | Source of Truth | Mutableか | Human Correction対象 |
| --- | --- | --- | --- | --- |
| Topic | 議論のテーマ・論点 | Materialized Discussion Graph | Eventにより状態変化 | Rename、Merge、Archive、再分類 |
| Idea / Opinion | 参加者から出た意見・アイデア | Materialized Discussion Graph | Eventにより追加・整理 | Rename、Merge、Delete / Archive |
| Option | 選択肢・案 | Materialized Discussion Graph | Eventにより追加・選択・不採用 | Rename、Merge、Reject、関連変更 |
| Concern | 懸念・リスク | Materialized Discussion Graph | Eventにより追加・解消・再開 | Rename、解消状態、関連変更 |
| Open / Unresolved Item | Questionまたは結論がない事項 | Materialized Discussion Graph | EventによりActive / Resolved等へ変化 | Rename、Resolve、Parking Lot移動 |
| Candidate Decision | AIが決定の可能性を抽出した状態 | Event Stream + Graph Projection | Candidate、撤回、Confirmedへの遷移候補 | Confirm、Revoke、修正 |
| Confirmed Decision | 人間が確認した正式なDecision | Human Confirmation Eventを反映したGraph | Revoke / Reviseは可能。履歴は保持 | Confirm、Revoke、修正 |
| Action Item | 会議後に実行する作業 | Graph Projection + Action Events | Owner、Due、Statusが変化 | Description、Owner、Due、Status |
| Parking Lot | 今回は扱わないTopic | Materialized Discussion Graph | ParkedからActiveへ戻り得る | Move、Rename、Restore |

### 4.3 Derived Projection

| 概念 | 役割 | Source of Truth | Mutableか | Human Correction対象 |
| --- | --- | --- | --- | --- |
| Current Topic | 現在話しているPrimary Topicの表示対象 | Topic Transition Events + Graph Projection | 新しいTransitionで変化 | 手動Overrideを採用する場合はEvent |
| Discussion Flow | Topicが移動した履歴 | Topic Transition Event Stream | Append-only | 直接編集せずCorrection / 再解析で修正 |
| Recent Flow | UX上の直近Flow表示 | Discussion FlowからのUX Projection | 表示窓が変化 | 直接編集対象ではない |
| Drift Awareness | 未解決Topicと別Current Topicが併存する事実の表示 | Graph + Flow + Observation Policy | 事実ではなくDerived Signal | Topicや状態のCorrectionで変化 |

### 4.4 External / Finalized Resource

| 概念 | 役割 | Source of Truth | Mutableか | Human Correction対象 |
| --- | --- | --- | --- | --- |
| Human Correction | AI結果を人間が修正した履歴 | Event Stream | Append-only。UndoはInverse Event | Rename、Merge、Confirm、Revoke等 |
| Visual Artifact | Discussion Aidとして生成された画像・Diagram | Artifact Resource Store | 同じFamilyはLinear Version Chain | Revise、Hide、Reject、Version選択 |
| Artifact Marker | Map上でArtifactの存在を示す表示 | Artifact Reference + UX Projection | Artifact状態に追随 | 直接編集せずArtifact操作で変化 |
| Session Summary | Session終了直後のStateの短いProjection | Final Graph Snapshot | Draft View | Source StateをCorrection |
| Minutes | Final Stateを会議後文書へProjectionしたもの | Minutes Context Snapshot + Minutes Store | Draftは編集可。Finalizedは新Revision | Review、Manual Edit、再生成 |

### 4.5 用語上の注意

QuestionとUnresolved Itemは、Domain上で分けて保持してもよいが、RFC-0003およびRFC-0005のPrimary UX / Minutes表示ではOpen / Unresolved Itemsへ統合できる。

Candidate DecisionとConfirmed Decisionは、誤認防止のためDomain上も表示上も分離する。

ArtifactのDraft / Superseded / Rejectedは、Formal DecisionのAdoption Stateではない。

## 5. State Ownership

### 5.1 ProducerとOwnerの区別

「誰がStateを生成したか」と「どこがそのStateを正として保持するか」を分ける。

例:

- STT ProviderはTranscript候補を生成する
- Evidence StoreがFinal Transcript Evidenceを保持する
- Discussion AnalyzerはCandidate Eventを生成する
- Event Streamが履歴の正となる
- Graph MaterializerがCurrent Graphを構成する

### 5.2 Ownership Matrix

| Information | Producer | State Owner / System of Record | Downstream Consumer |
| --- | --- | --- | --- |
| Audio | Audio Ingestion | Audio Boundary / Session Ingestion | STT |
| Partial Transcript | STT | Ephemeral STT State | Listening UI、STT correction preparation |
| Final Transcript Evidence | STT + Evidence Normalizer | Transcript Evidence Store | Utterance Builder、Analysis、Evidence UI、Minutes |
| Utterance | Utterance Builder | Final Utterance Evidence Projection | Discussion Analyzer |
| Candidate Event | Discussion Analyzer | Event Stream | Graph Materializer、Evaluation |
| Human Correction Event | Human UI / Command Handler | Event Stream | Graph Materializer、Minutes Finalizer |
| Discussion Graph | Graph Materializer | Materialized Graph Revision | Map UX、Context Builder、Minutes |
| Candidate Decision | Discussion Analyzerが候補生成 | Event Stream + Graph Projection | Map UX、Minutes Pending Confirmation |
| Confirmed Decision | Human Confirmation | Confirmation Event + Graph Projection | Map、Minutes、Evaluation |
| Current Topic Candidate | Discussion Analyzer | Event Stream | Graph / UX Topic Policy |
| Visible Current Topic | UX Presentation | UI Session View | Shared Display |
| Discussion Flow | Analyzer Transition Event | Event Stream | Graph Recent Flow、Minutes |
| Visual Artifact | Artifact System | Artifact Resource Store | Map Marker、Visual View、Minutes |
| Minutes Draft | Minutes Generator | Minutes Store | Review UI、Export |
| Finalized Minutes | Human Review / Finalization | Minutes Store | Markdown Export、利用者 |

### 5.3 Ownership上の重要な結論

複数サービスが同じCurrent Stateを直接所有しない。

- AnalyzerはGraphを直接書き換えない
- UXはTopicのSemantic Stateを所有しない
- MinutesはGraphを更新しない
- ArtifactはDecisionを所有しない
- STTはConfirmed Decisionを生成しない

## 6. Decision Lifecycle

### 6.1 Baseline Lifecycle

~~~text
Final Utterance / Analysis Window
    ↓
Discussion Analyzer
    ↓
Candidate Decision Event
    ↓
Event Stream
    ↓
Graph Materialization
    ↓
Candidate DecisionをMapへ表示
    ↓
Human Confirmation Command
    ↓
Decision Confirmed Event
    ↓
Graph Materialization
    ↓
Confirmed Decision
    ↓
Minutes Decisionsへ反映
~~~

### 6.2 各責務

| Lifecycle Step | Owner | 内容 |
| --- | --- | --- |
| Candidate生成 | Discussion Analyzer | Final UtteranceとContextから可能性を抽出 |
| Candidate保存 | Event Stream | Candidate Eventを履歴として追加 |
| Candidate表示 | Discussion Map UX | Confirmedと視覚的に区別して表示 |
| Confirm操作 | Human Command / Review UI | ユーザーが明示的にConfirmする |
| Confirmed State | Graph Materializer | Confirmed EventをCurrent Graphへ反映 |
| Decision解除 | Human Command | Decision Revoke / Unconfirm Eventを追加 |
| Decision修正 | Human Command | Correction Eventまたは新Decision Revisionを追加 |
| Minutes反映 | Minutes Finalizer | 最終GraphのConfirmedのみDecisionsへ出力 |

### 6.3 Confirm操作の最小Contract

具体的なWidgetは本書で決めないが、実装には次のCommand境界が必要である。

- 対象Candidate Decision ID
- 実行時点のGraph Revision
- Confirmationを実行したHuman Action
- 必要に応じた修正後Label
- EventとしてのTimestamp

「了解」「それでいきましょう」などの発話を自動的にConfirmedへ遷移させるかは、MVPでは採用せず、明示的なConfirm Commandを基準とする。発話によるConfirmationは、別のValidation対象にする。

### 6.4 Revoke / Revise

Decision解除は、既存Decisionを削除するのではなく、Decision RevokeまたはCorrection Eventを追加する。

~~~text
Decision D1: Confirmed
    ↓ Human Revoke Event
Decision D1: Revoked in Current Graph
    ↓
Minutes Decisionsから除外
~~~

解除されたDecisionを自動的にCandidateやOpen Issueへ戻さない。再び議論対象にする場合は、別のCandidateまたはHuman Correctionとして明示する。

### 6.5 Minutesへの反映

Minutes Finalizerは、次のルールを使う。

- Confirmed Decisionのみ正式Decisionsへ出力
- Candidate DecisionはPending Confirmationへ分離
- Revoked Decisionは正式Decisionsへ再導入しない
- Decisionの現在LabelはHuman Correction後のものを使う
- Event Streamの過去状態は、重要な変更履歴の補足に限定する

## 7. Action Item Lifecycle

### 7.1 代替案

| 案 | 内容 | 安全性 | 複雑性 | 評価 |
| --- | --- | --- | --- | --- |
| A | 抽出時点で正式Action | 単純だが曖昧な発言を登録しやすい | 低 | 速いがHallucinationに弱い |
| B | Candidate ActionからConfirmed Actionへ遷移 | Decisionと同じ安全性 | 中〜高 | 安全だが全Action確認が重い |
| C | Actionは記録し、Owner / Dueを確認対象とする | Actionの存在を保ちつつ担当情報を推測しない | 中 | MVPのバランスがよい |

### 7.2 MVP推奨

MVPではCを基本とする。ただし、ActionのDescription自体が曖昧な場合はActionを生成せず、Candidate Eventとしてopen_itemまたはideaへ置く。Action Node自体にDecisionのようなCandidate / Confirmed Stateは追加しない。

Baselineとして次を採用候補とする。

1. 明示的な実行意図がある場合、Action ItemをGraphへ記録する
2. Analyzerはaction.owner / action.due_dateをEvidenceに明示された場合だけ設定し、非明示値はnullにする
3. Analyzer由来のOwner / Dueはsource_evidence_idsで根拠を追跡する
4. Humanのupdate_actionはOwner / Dueを後から設定、修正、解除でき、Final GraphではAnalyzer値に優先する
5. 「検討する」「誰かがやる」など実行主体や作業が不明な発言はActionにせず、open_itemまたはideaに留める
6. 全Actionを会議中にConfirmする専用操作はMVP必須にしない

これはRFC-0005初稿にあったCandidate / Confirmed Action案を、Decisionと同じ重いLifecycleとして機械的に適用しないためのCanonical解釈である。Minutesでは未設定のOwner / Dueを明示するが、GraphにAction Confirmation Stateを追加しない。

### 7.3 Owner / DueのState

Owner / Dueは次のように扱う。

- Explicit: Transcript EvidenceまたはHuman Correctionに明示される
- Unset: 情報がない。Analyzerはnullを設定する
- Invalid: Human Correctionで撤回・無効化された

AIは発言者、Topic Owner、役割、会議慣行からOwnerを推測しない。相対期限を具体日へ変換する場合も、基準日とTimezoneが明示されていなければ変換しない。

## 8. Session Finalization Boundary

### 8.1 Session State候補

Sessionには、少なくとも次の状態を設けることを推奨する。

~~~text
active
  ↓ End Session
finalizing
  ↓ final input drained and graph materialized
state_ready
  ↓ Minutes Draft generated
minutes_review
  ↓ Human Confirm
completed
~~~

MinutesのDraft / Finalized StateとSessionのactive / finalizing / completedは別Stateである。

### 8.2 End Session時の処理

| 対象 | End Session時の扱い | 理由 |
| --- | --- | --- |
| New Audio | 新規受付を停止 | 境界時刻を固定する |
| Audio Buffer | 既に受付済みのBufferをDrain | 最後の発言を落とさない |
| Pending Final Transcript | Final化を待つ | PartialをMinutes根拠にしない |
| Pending Analysis Window | 受付済みFinal Utteranceを処理 | 最後の数十秒をStateへ反映する |
| Candidate Events | 生成済みをEvent StreamへAppend | Graphの入力を確定する |
| Graph Materialization | Final Graph Revisionを作る | Minutesの基準を固定する |
| Human Correction | Session中のCorrectionを適用 | 古いAI Stateを再導入しない |
| Artifact Generation | 待たずに継続 | Minutes FinalizationをBlockしない |

### 8.3 MVP Finalization Policy

MVPでは、End Sessionを押した瞬間にMinutes生成を開始しない。

推奨手順:

1. Sessionをfinalizingへ遷移する
2. Audio入力の新規受付を停止する
3. 受付済みAudio BufferをFinal STTへ送る
4. Final Transcriptが得られたUtteranceをAnalysisへ送る
5. 受付済みのAnalysis Windowを処理し、Candidate EventをAppendする
6. Graph Materializerを実行してFinal Graph Revisionを作る
7. Session Summaryを表示可能にする
8. Minutes Context Snapshotを作り、Draft生成へ進む

### 8.4 待機とTimeout

最後の数十秒のDiscussionを欠落させないことを優先する。ただし、Provider障害で無期限に待機しない。

実装上は次の条件を持つ必要がある。

- 受付済みAudioのDrain完了または明示的なFailure
- Final Transcriptの欠落区間が識別できる
- Pending Analysisの範囲が識別できる
- Last Consistent Graph Revisionが保存される
- Timeout時はSessionをstate_readyにできても、MinutesをFinalizedにしない
- DraftにAnalysis pendingまたはReview requiredを表示する

具体的な秒数、Percentile、ProviderごとのTimeoutはImplementation Parameterとして後で決める。finalizing StateとDrain Contractは実装前に必要である。

### 8.5 Artifactとの境界

Visual Artifactがqueued / generatingであっても、Session Finalizationは完了できる。Artifact完成後にMinutesへ追加する場合は、新しいMinutes Draft Revisionとする。

## 9. Visual Artifact Adoption

### 9.1 代替案

| 案 | 内容 | Map / Minutesへの影響 | 複雑性 | MVP評価 |
| --- | --- | --- | --- | --- |
| A | Adoption Statusを持たない | Artifactは常にDiscussion Aid | 最小 | 推奨 |
| B | Useful / Rejectedのみ持つ | 役立ったかを記録できる | 低〜中 | 将来候補 |
| C | Adopted / Rejected / Supersededを持つ | 正式採用Workflowに近い | 高 | MVPでは不要 |

### 9.2 推奨

MVPでは、Artifact Adoptionを正式なDomain Stateとして持たない。

Visual Artifactは次の情報だけで十分である。

- Generation State: queued / generating / ready / failed
- Resource Status: draft / superseded / rejected
- Version関係: revised_from / supersedes
- Source Topic / Graph Revision
- Map Markerの表示可否

Draft、Superseded、RejectedはArtifactの生成・表示・Version管理であり、正式な設計採用を意味しない。

### 9.3 Adoption削除候補

RFC-0004に記載されたadoptedという概念は、MVPでは実装対象から外す候補とする。Artifactを採用したい場合は、別途Confirmed Decisionまたは正式成果物を作る。

Usefulの記録も、MVPの中心検証である「VisualがDiscussionを良くしたか」を測る評価Metricで代替できる。会議中にUseful操作を要求しない。

## 10. Current Topic

### 10.1 責務境界

Current Topicは、Semanticな判定とVisualな表示を分離する。

| 責務 | Owner | 内容 |
| --- | --- | --- |
| Topic意味の解釈 | Discussion Analyzer | Final Utterance / WindowからCurrent Topic候補を生成 |
| Topic遷移の履歴 | Event Stream | Topic Transition Candidate / EventをAppend |
| Current GraphへのMaterialize | Graph Materializer | EventとPolicyに基づくCurrent Topic Projection |
| 強調、Animation、視線誘導 | UX Layer | GraphのCurrent Topicを安定的に表示 |
| Recent Flowの件数・表示 | UX Layer | Canonical Flowから表示窓を作る |
| 手動Topic変更 | Human Command | 採用する場合はCorrection / Override Event |

UX Layerが意味上のCurrent Topicを直接書き換えてはならない。表示を一時的に安定化することと、Graph Stateを変更することを分ける。

### 10.2 Current Topicの最小State

MVPでは、次の二つを区別する。

- Current Topic Candidate: Analysisが提案したTopic
- Current Topic Projection: GraphとTopic Policyを通じて、Mapが表示対象とするTopic

Current Topic Projectionが切り替わらない間も、新しいCandidateやTransitionはEvent Streamに残す。

### 10.3 Parameter分類

| Parameter | 種類 | 扱い |
| --- | --- | --- |
| Current Topic Candidateの生成条件 | Implementation Contract | AnalyzerがCandidate Eventを生成できること |
| Current TopicをGraphへ反映する条件 | Implementation Contract | Canonical EventとParking / Override規則をMaterializerが適用する |
| Topic切替のHysteresis / Cooldown | Validation Parameter | Prototypeで頻繁な切替と遅延を比較する |
| Current Topicの強調方法 | Validation Parameter | RFC-0003のUX Prototypeで検証 |
| 複数Active Topicの表示 | Can Decide During Prototype | Primary / Secondaryの認識性を評価 |

具体的な秒数、Window数、Confidence閾値はPrototypeで調整できる。ただし、CandidateとProjectionを別概念にするContractは実装前に固定する。

Prototype 1のCanonical State Policyは次のとおりである。

- Humanのset_current_topicはmode=human_correctedとして優先する
- Override中はNode追加、Relation追加、Confidence変化だけではCurrent Topicを変更しない
- 次の明示的topic_focus_changedまたはset_current_topicでFocusを更新する
- Current Topicがparkedになったらprimary_topic_id=null、mode=derived、confidence=nullとし、Human Overrideも解除する
- restore_from_parking_lotはactiveへ戻すだけで、Current Topicへ自動復帰しない
- 復帰は新しいset_current_topicまたは明示的topic_focus_changedだけで行う

### 10.4 Current Topicの戻り

一度離れたTopicへ戻る場合、Topicを新規生成せず、既存Topic IDへのTopic Transitionとして記録する。

これにより、次を同時に実現できる。

- 同一Topicの重複生成を抑える
- Flowで戻りを表示する
- Map上のNode位置を維持する
- Minutesで重要な戻りだけを説明する

## 11. Discussion Flow

### 11.1 Single Canonical Flow

Discussion Flowは、別のサービスが独自に持つStateではなく、Event Streamに記録されたTopic TransitionをCanonical Historyとする。

~~~text
Topic Transition Event Stream
        ↓
Current Topic / Recent Flow Projection
        ├─ Discussion Map Recent Flow strip
        ├─ Drift Awareness signal
        └─ Minutesの重要Flow要約
~~~

### 11.2 各利用者

| 利用先 | 使う情報 | 表現 |
| --- | --- | --- |
| Graph Materializer | 最新TransitionとTopic State | Current Topic Projection |
| Discussion Map UX | 直近のTransition | Recent Flow strip / Breadcrumb相当 |
| Drift Awareness | 未解決TopicとCurrent Topicの差 | 中立的なObservation |
| Minutes | 重要なTransitionのみ | Topic Summaryの補足文 |
| Replay / Evaluation | 全Transition | Event Streamの履歴 |

同じFlowを、Graph、UX、Minutesがそれぞれ別に保存しない。各層は同じCanonical EventからProjectionを作る。

### 11.3 Drift Awareness

Driftは新しいCanonical Entityとして保存しない。

次の事実からDerived Signalを作る。

- 元Topicが未解決である
- Current Topicが別Topicである
- 一定のTransitionまたは経過がある

表示は「脱線」と断定せず、次のような情報にする。

> 元の論点「MVP範囲」は未決のままです。現在は「料金モデル」を議論しています。

ObservationのCooldownや表示時間はUXのValidation Parameterであり、Graph Stateではない。

## 12. Human Correction

### 12.1 Correctionの基本方針

Human CorrectionはGraphを直接上書きする操作ではなく、Event Streamへ追加するCorrection Eventである。

~~~text
AI / Current Graph
      ↓
Human Correction Command
      ↓
Correction Event
      ↓
Graph Materializer
      ↓
Corrected Current Graph
      ↓
Map / Minutes / Artifact Context
~~~

### 12.2 操作ごとの表現

| UI上の操作 | Eventとしての意味 | Current Graphへの反映 |
| --- | --- | --- |
| Rename | Entity Rename / Label Correction | 表示名とCanonical Labelを更新 |
| Delete | Archive / Tombstone Correction | Current Projectionから除外。履歴は保持 |
| Merge | Merge Correction with Canonical Entity | 旧IDをCanonical IDへ関連付け |
| Decision Confirm | Decision Confirmed Event | CandidateをConfirmedへ変更 |
| Decision Revoke | Decision Revoked Event | ConfirmedをCurrent Stateから除外 |
| Parking Lot Move | Topic State / Relation Correction | Parking Lot Projectionへ移動 |
| Undo | 直前CorrectionのInverse Event | 破壊的Deleteではなく再適用可能にする |

### 12.3 DeleteとArchive

MVPのDelete操作は物理削除ではなくArchiveまたはTombstoneとして扱う。過去のEvent、Evidence、Minutes Traceabilityを壊さない。

Archived EntityをCurrent Discussion Graphや通常のMinutesへ出力しない。必要な場合だけHistoryまたはEvidence Viewで参照する。

### 12.4 Merge

自動Mergeは行わない。Analyzerが類似候補を出すことはできるが、MergeはHuman Correctionで確定する。

Merge後は次を満たす。

- Canonical Entity IDが一つになる
- 旧Entity IDは履歴上参照可能
- Map上に重複Nodeを残さない
- MinutesではCanonical Labelだけを使う
- Replayで同じMerge結果を再現できる

### 12.5 Undo

RFC-0003のMVP方針に合わせ、User-facing Undoは最新Human Correctionに限定する案をBaseline候補とする。

Undoは過去Eventを削除せず、Inverse Correction EventをAppendする。任意のAI Eventを無制限にUndoする機能はMVPのScope外とする。

### 12.6 Minutesへの反映

MinutesはCorrection後のFinal Graphを優先する。Correction前のAI Stateは、現在Stateの本文へ再導入しない。

CorrectionがDraft生成後に発生した場合、MinutesをStaleにして再生成またはReviewを要求する。

## 13. Visual Artifact Architecture

### 13.1 Baseline

RFC-0004から、次をMVPのBaselineとする。

- ArtifactはDiscussion Graphの通常Nodeではなく独立Resource
- MapにはArtifact MarkerまたはReferenceだけを置く
- 生成Request時点のContext Snapshotを不変保持する
- Generationは非同期で、Realtime AnalysisとSession FinalizationをBlockしない
- Diagram RendererとImage Generatorは別Capabilityとして扱う
- Visual完成時はSuggested Switchとし、自動画面切替をしない
- 同じArtifact Familyの改訂はLinear Version Chainとする
- Automatic GenerationはMVP対象外
- VisualはDraft / Discussion Aidとして表示する
- ArtifactからDecisionを自動生成しない

### 13.2 ArtifactとGraphの境界

~~~text
Discussion Graph
  Topic
    └─ Artifact Reference / Marker

Artifact Resource
  Artifact Family
    ├─ v1
    └─ v2 revised_from v1
~~~

GraphはArtifactの画像、Prompt全文、Provider Responseを所有しない。Artifact SystemがAsset、Version、Generation Stateを所有する。

### 13.3 MVP初期Type

RFC-0004の推奨に従い、初期候補は次の二つである。

- concept_image
- diagram

どちらをPrototype 1に含めるかは、Prototype 1ではVisualを除外するため、MVP Phase 2のValidation Parameterとする。

### 13.4 Open Questions

| Question | Classification | 決め方 |
| --- | --- | --- |
| Concept ImageとDiagramの開始順 | Can Decide During Prototype / Phase 2 | Static PrototypeとDiscussion理解評価 |
| Context Previewの必須性 | Can Decide During Prototype | 操作時間と誤Context選択を比較 |
| Single / Multiple Variant | Can Defer After MVP | Anchoring、Cost、待ち時間の評価 |
| Full Visual / Split View | Can Decide During Prototype | 16:9共有DisplayでPrototype検証 |
| Voice Intent | Can Defer After MVP | STT精度と誤Triggerが許容できるか検証 |
| Raw Provider Response保持 | Can Defer After MVP | Privacy / Operations RFC |
| Artifact Marker件数 | Can Decide During Prototype | Map情報量と発見性を比較 |

## 14. Minutes Architecture

### 14.1 Baseline

RFC-0005から、次をMVPのBaselineとする。

- Structured State + Evidence Hybrid
- Final Discussion Graphを中心にする
- Event StreamはHistory、Flow、Correction、Replayの根拠にする
- Final TranscriptはEvidenceと短いCitationに限定する
- Candidate DecisionとConfirmed DecisionをMinutes上で分離する
- Human Correction後のStateを優先する
- Deterministic ValidationをLLM生成後に行う
- Draft → Review → Confirm / Finalizeの順で進む
- MarkdownをMVPのExport形式とする
- Owner、Due Date、数値、Next Topicを推測しない
- Visual ArtifactはRelated Referenceとして扱う

### 14.2 MinutesのSource Boundary

Minutes Generatorは次をしない。

- Discussion GraphのState変更
- CandidateのConfirmed化
- Action Ownerの決定
- ArtifactのAdoption
- Transcriptの独自再解析
- Event StreamのDeleteまたはRewrite

必要なState変更は、Human Command、Correction Event、Finalization、または別のAnalysis Revisionで先に行う。

### 14.3 Session Summary

Session SummaryはFinal Graphから作る即時Projectionであり、Minutesの別Source of Truthではない。

~~~text
Final Graph Snapshot
    ├─ Session Summary: 即時・構造化・短い
    └─ Minutes Draft: 詳細・文章化・Review可能
~~~

## 15. Source of Truth Matrix

| Information | Primary Source | Secondary Source | Human Editable | Used by |
| --- | --- | --- | --- | --- |
| Session Metadata | Session Metadata / Session Events | User Input | Yes, via Correction / Revision | UI、Finalization、Minutes |
| Audio | Audio Ingestion Boundary | Provider Metadata | No direct edit | STT、Finalization |
| Transcript | Final Transcript Evidence Store | STT Provider output、Correction Revision | Limited; new Evidence Revision | Utterance、Analysis、Evidence UI、Minutes |
| Partial Transcript | Ephemeral STT State | Audio Buffer | No | Listening Indicator、STT preparation |
| Utterance | Final Utterance Projection | Transcript Evidence | No direct edit; reprocess | Discussion Analysis、Replay |
| Discussion Event | Event Stream | Analysis / Human Command payload | Append-only; correction by new Event | Graph Materializer、Replay、Evaluation |
| Topic | Materialized Discussion Graph | Topic Candidate Event、Human Correction | Yes, via Correction | Map、Context、Minutes |
| Idea / Option / Concern | Materialized Discussion Graph | Candidate Events、Evidence | Yes, via Correction | Map、Minutes、Artifact Context |
| Candidate Decision | Event Stream + Graph Projection | Final Transcript Evidence | Confirm / Revoke via Human Event | Map、Minutes Pending |
| Confirmed Decision | Human Confirmation Event + Graph Projection | Related Evidence | Revoke / Revise via Human Event | Map、Minutes Decisions |
| Action Item | Graph Projection from action node_detected / update_action | Explicit Evidence、Human Correction | Description / Owner / Due / Status | Map、Summary、Minutes |
| Current Topic | Topic Transition Events + Graph Projection | Analysis Candidate | Optional Manual Override via Event | Map UX、Observation |
| Discussion Flow | Topic Transition Event Stream | Graph Recent Flow Projection | Indirectly via Correction / Reprocess | Map、Minutes、Replay |
| Human Correction | Event Stream | Command Handler payload | Created by Human | Materializer、Minutes、Audit |
| Parking Lot | Materialized Graph State | Parking Lot Move Event | Yes, via Move / Restore Event | Map、Minutes |
| Artifact | Artifact Resource Store | Source Topic Reference、Artifact Events | Revise / Hide / Reject / Version | Visual View、Map Marker、Minutes |
| Artifact Marker | UX Projection from Artifact Reference | Graph Topic | Indirectly via Artifact operation | Discussion Map |
| Session Summary | Final Graph Snapshot | Event Stream / Evidence | Correct Source State, not Summary directly | End Session UX |
| Minutes Draft | Minutes Store | Minutes Context Snapshot | Yes, Human Edit / Section Regenerate | Review、Export |
| Finalized Minutes | Minutes Store | Final Graph / Evidence Snapshot | New Revision only | Markdown Export、共有 |

このMatrixにより、同じCurrent StateをAnalyzer、UX、Minutes、Artifactが直接所有しないことを確認する。

## 16. RFC Dependency Map

### 16.1 Primary Dependency

~~~text
Canonical RD
    ↓
RFC-0001 Discussion Model / Graph Architecture
    ↓
RFC-0002 Realtime Discussion Analysis Pipeline
    ↓
RFC-0003 Discussion Map UX and Layout
    ↓
RFC-0004 Visual Artifact Generation and Intervention
    ↓
RFC-0005 Meeting Minutes Generation
~~~

### 16.2 More Accurate Cross Dependencies

~~~text
RFC-0001
  ├─ defines Domain Entity / Event / Graph / Correction
  ├──────────────→ RFC-0002 Analysis Events
  ├──────────────→ RFC-0003 Graph Presentation
  ├──────────────→ RFC-0004 Artifact Reference
  └──────────────→ RFC-0005 Final State Projection

RFC-0002
  ├──────────────→ RFC-0003 Current Topic / Flow UI inputs
  ├──────────────→ RFC-0005 Finalization input boundary
  └──────────────→ RFC-0004 Context freshness / Evidence

RFC-0003
  ├──────────────→ RFC-0004 Map ↔ Visual transition
  └──────────────→ RFC-0005 Session Summary transition

RFC-0004
  └──────────────→ RFC-0005 Related Artifact References
~~~

### 16.3 Dependency Interpretation

RFC-0005はすべてのRFCの最終Stateを読むが、他のDomain Stateを所有しない。

RFC-0004はRFC-0003のMapをPrimary Viewとして前提にするが、Artifactの画像内容をMapの意味構造へ戻さない。

RFC-0003はRFC-0002のSemantic Candidateを受け取るが、Analysisの意味を独自再解釈してCanonical Eventを作らない。

## 17. Cross-RFC Contradiction Audit

### 17.1 Audit Result

Architecture-levelで「Graphを正とするRFC」と「Transcriptを正とするRFC」が混在するような致命的矛盾はない。中心方針は整合している。

一方、以下は同じ実装境界を複数RFCが異なる粒度で扱っており、Contractを固定しないと実装時に解釈が分かれる。

### 17.2 Critical

| ID | Issue | 関係するRFC | 影響 | 判定 |
| --- | --- | --- | --- | --- |
| C-001 | Session End後のAudio / Final STT / Pending AnalysisのDrain境界が未確定 | RFC-0002、RFC-0005 | 最後の数十秒がMinutesとGraphから欠落する可能性 | Live MVP前にResolve。Prototype 1ではDeferred |
| C-002 | ~~Candidate DecisionをConfirmedへ遷移させる最小Human Command~~ | RFC-0001、RFC-0003、RFC-0005 | confirm_decision / revoke_decisionとexpected_revisionをSchema / Catalogで固定済み | Resolved |
| C-003 | ~~Action Itemの正式性とCandidate / Confirmedの適用範囲~~ | RFC-0001、RFC-0005 | Canonical Action policy CとSchema / Fixtureで解消済み | Resolved |

これらは設計思想の矛盾というより、実装Contractの欠落である。Prototype 1では固定入力で境界を代替できるが、Live MVPへ進む前に決める必要がある。

### 17.3 Should Resolve

| ID | Issue | 関係するRFC | 対応 |
| --- | --- | --- | --- |
| S-001 | Current Topic Candidate、Graph Projection、Visible Topicの関係 | RFC-0002、RFC-0003 | 本書のOwnershipをBaselineとし、閾値はPrototypeで検証 |
| S-002 | Question、Unresolved、Open IssueのCanonical名 | RFC-0001、RFC-0003、RFC-0005 | Domainと表示のMappingをEvent Schemaで固定 |
| S-003 | Human CorrectionのRename、Merge、Archive、UndoのEvent名とPayload | RFC-0001、RFC-0003 | 最小Event CatalogをPrototype前に作る |
| S-004 | Artifactのdraft / superseded / rejectedとAdoptionの境界 | RFC-0004、RFC-0005 | adoptedはMVP対象外としてBaseline化 |
| S-005 | MinutesのFinalized条件とPending AnalysisのWarning | RFC-0002、RFC-0005 | Finalization ContractとReview状態を固定 |
| S-006 | ~~Action Owner / DueのEvidence表現~~ | RFC-0001、RFC-0005、Event Schema | Analyzerのaction Payloadとsource_evidence_ids、Human update_actionで解消済み | Resolved |
| S-007 | Recent Flow、Drift Awareness、Minutes Flowが参照するTransition範囲 | RFC-0001、RFC-0003、RFC-0005 | Canonical Transition Eventから各Projectionを作る |

### 17.4 Can Defer

| ID | Issue | 関係するRFC | Deferred先 |
| --- | --- | --- | --- |
| D-001 | Voice IntentによるVisual生成 | RFC-0004 | MVP後 |
| D-002 | Multiple Visual VariantsとBranch | RFC-0004 | MVP後 |
| D-003 | PDF / DOCX / 外部配信 | RFC-0005 | Future RFC |
| D-004 | Speaker常時表示と話者別Minutes | RFC-0003、RFC-0005 | MVP後 |
| D-005 | Artifact正式採用・承認Workflow | RFC-0004、RFC-0005 | Future RFC |
| D-006 | Provider Raw Response、Retention、Operations | RFC-0002、RFC-0004、RFC-0005 | Operations / Security RFC |
| D-007 | 大規模Map、複数Primary Topic、Session横断Action管理 | RD、RFC-0003、RFC-0005 | MVP後 |

### 17.5 矛盾ではないが明示が必要な関係

#### GraphとEvent Stream

GraphとEvent Streamは同じ情報を二重に所有しているのではない。Event Streamは履歴、GraphはMaterialized Current Stateである。

#### QuestionとUnresolved

内部Entityを分ける可能性と、UX / Minutesで統合表示する方針は両立する。

#### ArtifactとDecision

Artifact ReferenceとDecision Referenceは別である。Artifactの生成、閲覧、Revision、StatusはDecision Confirmationを発生させない。

#### MinutesとGraph

MinutesはGraphのCopyではなく、Final GraphをInputにした文章Projectionである。Minutes本文のManual EditはGraph Stateを変更しない。

#### Session SummaryとMinutes

SummaryはFinal Graphの即時Projection、MinutesはEvidenceとHistoryを補ったFinalized Documentであり、Source of Truthは別々に増えない。

## 18. Open Question Classification

### 18.1 A. Must Resolve Before Prototype

Prototype 1のReplay、Materializer、Fixture、Current Topic、Action、RelationのCanonical Contractは、Domain / Event Schema、Event Catalog、Fixturesで固定済みである。したがって、Prototype 1開始前のMust Resolveは残っていない。

Session FinalizationのDrain条件はLive Audio / STT / Analysisに依存するため、Prototype 1ではDeferredとする。Live MVPへ進む前に、RFC-0002 / RFC-0005のFinalization Contractとして解消する。

### 18.2 B. Can Decide During Prototype

Prototypeの観察・Static Mock・Replayで調整できる。

| ID | Question | 検証対象 |
| --- | --- | --- |
| B-001 | Current TopicのHysteresis / Cooldown | 切替頻度と遅延 |
| B-002 | Recent Flowの表示件数 | Shared Displayでの理解 |
| B-003 | Candidate Decisionの強調方法 | Confirmedとの誤認率 |
| B-004 | Map LayoutのNode間隔とStable Position | 既存位置の維持 |
| B-005 | Multiple Active TopicのSecondary表示 | Primary Topicの明瞭性 |
| B-006 | Question / UnresolvedのLabel表示 | 1 Section統合の理解性 |
| B-007 | Human Correctionを誰が操作するか | Operatorと参加者全員の比較 |
| B-008 | Evidence Drawerの表示方式 | 確認時間と会話中断 |
| B-009 | Session Summaryの情報量 | 即時確認の有用性 |
| B-010 | MinutesのSummary長とMain Discussionの粒度 | Review時間と理解度 |
| B-011 | MarkdownのCitation表示 | Traceabilityと読みやすさ |
| B-012 | Artifact Marker / Full Visual / Split View | VisualがDiscussionを妨げないか |

### 18.3 C. Can Defer After MVP

MVPの中心価値を検証した後でよい。

- Voice IntentによるVisual生成
- Automatic Visual Generation
- Artifact Adoption / Useful Workflow
- Multiple Variant、Branch、比較Workspace
- PDF / DOCX / 外部配信
- Speaker常時表示と話者別要約
- Online Meeting Integration
- Voting、Participant評価、Emotion / Personality Analysis
- Session横断Action通知とDue Date管理
- 大規模会議、Mobile UI、多言語最適化
- Providerの詳細選定、Raw Response保持、Cost Dashboard

### 18.4 既存RFC Open Questionsとの対応

既存RFCのOpen Questionsは、次のように分類する。分類は「今すぐ全仕様を確定する」という意味ではなく、どの段階で判断が必要かを示す。

| Source | Must Resolve Before Prototype / Live Contract | Can Decide During Prototype | Can Defer After MVP / Resolved |
| --- | --- | --- | --- |
| RFC-0001 | なし。Action、Relation、Parking / Current TopicのPrototype Contractは本Canonicalizationで解消 | OQ-02 Candidate表示、OQ-03 Agreed / Decided表示、OQ-08 Map容量、OQ-09 Flow表示、OQ-10 Undo UX、OQ-14 Multiple Topic | OQ-01の発話Confirm運用、OQ-06 Speaker、OQ-11の高度なArtifact運用、OQ-15の全Session再解析運用 |
| RFC-0002 | Live Finalization / Analysis境界（Prototype 1ではDeferred） | OQ-2002 Latency計測、OQ-2003 Partial UI、OQ-2004 Topic切替閾値、OQ-2006 Summary更新 | OQ-2005 Reprocess運用、OQ-2007 Raw Audio保持、Provider固有の運用 |
| RFC-0003 | Current TopicのState Contractは解消済み | OQ-3001〜OQ-3008、OQ-3009、OQ-3010の表示・操作検証 | 大規模Map、Speaker常時表示、複雑なMulti-topic UX |
| RFC-0004 | Artifact ReferenceとStatusの最小Contract | OQ-4001、OQ-4002、OQ-4004、OQ-4006、OQ-4007、OQ-4011 | OQ-4003 Variant、OQ-4005 Voice、OQ-4008 Raw Response、OQ-4009 Staleness高度化、OQ-4010 Cost上限の運用化。OQ-4012はRFC-0005で基本方針を定義 |
| RFC-0005 | Minutes Source Snapshot。Action policyはCanonical化済み、Finalization境界はPrototype 1ではDeferred | OQ-5001 Review主体、OQ-5003 Citation、OQ-5005 Summary長、OQ-5007 Agreed / Decided、OQ-5009 Artifact選択、OQ-5010 Pending Analysisの表示 | OQ-5002の高度なAction Review、OQ-5006 Speaker、OQ-5008高度なRevision、OQ-5011 Retention、OQ-5012期限正規化、OQ-5013高度なFallback |

## 19. MVP Architecture Decisions

以下は、RFC群から既に確定した、またはArchitecture Baselineとして採用する設計判断である。正式なADRファイルではなく、本書内の参照用IDである。

| ID | Decision |
| --- | --- |
| AD-001 | Discussion Mapを会議中のPrimary Value / Primary Viewとする |
| AD-002 | TranscriptはEvidenceであり、Current Graphの直接Source of Truthにしない |
| AD-003 | Event StreamはDiscussion HistoryとCorrection HistoryをAppend-onlyで保持する |
| AD-004 | Discussion GraphはEvent StreamからMaterializeされるCurrent Stateである |
| AD-005 | Partial TranscriptではCanonical Graphを更新しない |
| AD-006 | Final Utterance / Analysis Windowを基準にIncremental Analysisする |
| AD-007 | Discussion AnalyzerはCandidate Eventを生成し、Graphを直接変更しない |
| AD-008 | Candidate DecisionはHuman ConfirmationなしにConfirmedへ遷移しない |
| AD-009 | Confirmed DecisionはHuman Confirmation Eventを通じてCurrent Graphへ反映する |
| AD-010 | Human CorrectionはGraphの直接上書きではなくCorrection Eventとして記録する |
| AD-011 | 自動Mergeは行わず、MergeはHuman Correctionで確定する |
| AD-012 | Current TopicのSemantic判定とUX上の表示安定化を分離する |
| AD-013 | Discussion FlowはTopic Transition EventをCanonical Historyとする |
| AD-014 | Driftは断定的なLabelではなく、未解決TopicとCurrent Topicの併存からDerived表示する |
| AD-015 | Mapは固定Lane / Hybrid Presentationを基本とし、既存Node位置を大きく変えない |
| AD-016 | Visual Artifactは独立Resource、MapにはMarker / Referenceだけを置く |
| AD-017 | Visual GenerationはAsync、Suggested Switch、自動画面奪取なしとする |
| AD-018 | ArtifactはDraft / Discussion Aidであり、Decisionではない |
| AD-019 | Artifactの同一Family改訂はLinear Version Chainとする |
| AD-020 | MinutesはStructured State + Evidence Hybridで生成する |
| AD-021 | Minutesの正式DecisionsはConfirmed Decisionだけとする |
| AD-022 | MinutesはDraft → Review → Confirm / Finalizeを経る |
| AD-023 | Owner、Due、数値、Next Topicを推測しない |
| AD-024 | MinutesのMVP ExportはMarkdownとする |
| AD-025 | Graph、Artifact、Minutes、UXは互いのCurrent Stateを直接所有しない |
| AD-026 | Actionは明示的な実行意図で生成し、AnalyzerのOwner / DueはEvidence明示値またはnullに限定する |
| AD-027 | supportsはsource idea / option、target idea / option / decisionに限定する |
| AD-028 | Current Topic対象がparkedになったらprimary_topic_idをnullにし、Human Overrideを解除する |
| AD-029 | restore_from_parking_lotはFocusを自動復帰させず、明示的なFocus Eventだけが復帰させる |
| AD-030 | Open Itemは既存Node statusのactive（open）/ resolvedでLifecycleを表し、Resolve / ReopenはHuman Eventだけにする |
| AD-031 | Analyzer Outputの同一応答内参照はnew_node_indexをLocal Referenceとして使い、Adapterがdeterministic Canonical IDへ解決する |

Session Finalization DrainはLive STT / AnalysisのImplementation Contractとして、Prototype 1の後に確定する。

## 20. MVP Non-goals Confirmation

RDのOut of ScopeとRFC群の設計は、次の点で矛盾しない。

| RD Non-goal | RFC / Baselineでの扱い | MVP混入 |
| --- | --- | --- |
| Smartphone UI | 16:9 Shared DisplayをPrimaryとし、Mobileを対象外 | なし |
| 個人端末からの参加 | Shared View中心。個人参加操作を定義しない | なし |
| Voting | OptionとDecisionは扱うが、投票機能は定義しない | なし |
| AIによる音声ファシリテーション | AI Observationは画面上の短い補助。音声介入はしない | なし |
| 発言者評価 / 発言量ランキング | Speakerは必要時のみ、評価は扱わない | なし |
| Emotion / Personality Analysis | Domain、Graph、Minutesに含めない | なし |
| 完全自動の議論進行 | AIはCandidate / Observation / Suggestion。進行・判断を所有しない | なし |
| AIによる最終判断 | Confirmed DecisionはHuman Confirmation | なし |
| Online Meeting完全統合 | Audio Boundaryのみ。Meeting Service統合はない | なし |
| 高度なUser Management | Scope外 | なし |
| 大規模会議 | 2〜8名程度、30〜60分を前提 | なし |
| 多言語最適化 | Japanese First | なし |

RFC-0004のVoice Intentは将来の補助入力候補であり、AI Voice Facilitationではない。Prototype 1では除外する。

## 21. First Prototype Boundary

### 21.1 評価

Fixed Transcript Replayから開始する境界は妥当である。

理由:

- STT誤認識とDiscussion Modelの評価を分離できる
- 同じ入力でEvent、Graph、Mapを繰り返し評価できる
- Candidate / Confirmed Lifecycleを安定して検証できる
- ReplayとMaterializerのDeterminismを早期に確認できる
- Live Audio、Provider、Latencyの問題がDomain設計を隠さない

### 21.2 Prototype 1 Scope

~~~text
Fixed Final Transcript Fixture
    ↓
Utterance Builder
    ↓
Discussion Analysis
    ↓
Candidate Events
    ↓
Event Stream
    ↓
Graph Materialization
    ↓
Discussion Graph
    ↓
Static / Interactive Discussion Map
~~~

Prototype 1には、次を含める。

- 固定されたFinal Utterance Fixture
- Utterance ID、Timestamp、発言テキスト
- Topic、Idea、Option、Concern、Open / Unresolvedの最小抽出
- Candidate Decisionの生成
- 明示的なHuman Confirm Command
- Confirmed DecisionのGraph反映
- Decision Revokeの最小Command
- Topic TransitionとRecent Flow
- Current TopicのCandidate / Projection
- 既存Topicへ戻るケース
- Node RenameまたはParking Lot Moveの少なくとも一つ
- Event Replay
- Graph MaterializationのDeterministic Evaluation
- Existing Node位置を維持するStatic Map

### 21.3 Prototype 1 Non-scope

- Live Audio
- STT Provider
- Partial Transcriptの実時間UI
- Visual Image Generation
- Diagram / Image Provider
- Artifact Version UI
- Full Minutes Export
- PDF / DOCX
- Provider Abstractionの汎用化
- Online Meeting Integration
- Voting、Speaker Evaluation、Emotion Analysis
- 大規模会議対応

Minutesについては、Prototype 1ではFull Minutesを生成しない。ただし、Final GraphからCandidate / Confirmed / Open Itemを取り出せることが、後続RFC-0005を実装できる前提になる。

### 21.4 Human Confirmationを含める理由

Candidate DecisionがMapに表示されるだけでは、RFCの重要な安全性を検証できない。Prototype 1では、簡易なConfirm / Revoke Commandを含める。

Widgetの見た目は最小でよいが、Command、Event、Graph Projection、Map表示の一連の状態変化は実際に再現する。

## 22. Prototype Success Criteria

Prototype 1は、次を満たすことを成功条件とする。

### 22.1 State and Event

- Fixed TranscriptからUtteranceを再現できる
- Candidate EventがEvent StreamへAppendされる
- AnalyzerがGraphを直接変更していない
- 同一Event StreamをReplayして同じGraph Revisionを再現できる
- Event IDとEntity IDの関連が追跡できる

### 22.2 Discussion Map

- Topicが追加される
- 同一Topicへ戻ると新規Duplicate Topicを作らない
- Candidate Decisionが出る
- Human Confirmできる
- Confirmed DecisionがMapへ反映される
- Decision Revoke後にConfirmed表示が消える
- Open / Unresolved Itemが残る
- Current Topicが切り替わる
- Recent Flowが更新される
- Driftを断定的な赤警告として表示しない
- Map更新時に既存Nodeの位置が大きく変わらない

### 22.3 Correction and Replay

- Rename、MergeまたはParking Lot Moveの少なくとも一つをCorrection Eventとして再現できる
- Correction後のReplayで同じCurrent Graphになる
- 古いAI StateがCorrection後のMapへ再導入されない
- 最新CorrectionをUndoまたはInverse Eventで戻せる

### 22.4 Evaluation

- Golden Fixtureに対してExpected Entity、Event、Stateを比較できる
- CandidateとConfirmedの混同を検出できる
- 同一入力のReplay結果が安定している
- MapのStability、Current Topic認識、Flow理解を人間が評価できる

## 23. Recommended Implementation Order

以下はコードを書くための実装順の提案であり、本書では実装を開始しない。

### Phase 0: Contract Fixing

1. Canonical Domain Termsを確定する
2. Prototype 1のEntity / Event最小集合を確定する
3. Event ID、Entity ID、Graph Revisionの方針を確定する
4. Decision Confirm / Revoke Commandを確定する
5. Action Item方針を確定する
6. Finalization Boundaryの概念Contractを確定する

### Phase 1: Replayable Domain Core

7. Fixed Transcript / Utterance Fixtureを作る
8. Discussion EventのFixture形式を作る
9. Append-only Event Streamを作る
10. Graph Materializerを作る
11. ReplayとDeterminism評価を作る
12. Human Correction Eventを作る

### Phase 2: Fixed Analysis and Map

13. Fixed Transcript AnalyzerまたはFixture-driven Analyzerを作る
14. Candidate Topic、Decision、Open Item、TransitionをEvent化する
15. Candidate / Confirmed DecisionのProjectionを作る
16. Current Topic Candidate / Projectionを作る
17. Recent Flow Projectionを作る
18. Static / Interactive Discussion Mapを作る
19. Stable LayoutとExisting Node Position維持を検証する

### Phase 3: Evaluation

20. Golden Fixtureを増やす
21. Candidate / Confirmed、Correction、Replayの評価を行う
22. Current Topic、Flow、Map StabilityのPrototype評価を行う
23. Must Resolve項目を更新し、Architecture BaselineをRevisionする

### Phase 4: MVP拡張

24. Live Audio / STT Boundary
25. Finalization DrainとSession State
26. Visual Artifact Async Pipeline
27. Minutes Context、Draft、Validation、Review、Markdown Export
28. Provider CapabilityとOperations

Live Audio、Visual、Minutesを最初から同時に実装しない。Prototype 1でDomain、Event、Graph、Mapの中心価値を先に評価する。

## 24. Implementation Boundary Summary

### 24.1 最初の実装単位

最初に実装対象とするのは、次の小さな閉じたLoopである。

~~~text
Fixed Transcript
    ↓
Final Utterance
    ↓
Candidate Event
    ↓
Event Stream
    ↓
Graph Materializer
    ↓
Current Discussion Graph
    ↓
Human Confirmation / Correction
    ↓
Stable Discussion Map
    ↓
Replay / Evaluation
~~~

### 24.2 最初に実装しない境界

次の要素は、Prototype 1の結果とContract確定後に進める。

- STT、Audio Buffer、Partial Transcript
- Provider固有の非同期処理
- Visual Artifactの生成・Storage・Revision
- Minutesの文章生成とMarkdown Export
- Online Meeting、Mobile、Speaker分析

## 25. Architecture Baseline

### 25.1 確定事項

- Canonical RDは docs/requirements/discussion-map-ai-facilitator-mvp.md
- Discussion MapがPrimary Valueである
- TranscriptはEvidenceである
- Event StreamはHistoryとCorrectionのCanonical Storeである
- Discussion GraphはEvent StreamからMaterializeするCurrent Stateである
- Partial TranscriptではCanonical Graphを更新しない
- Discussion AnalysisはCandidate Eventを生成し、Graphを直接書き換えない
- Candidate DecisionはHuman ConfirmationなしにConfirmedにならない
- Confirmed DecisionはHuman Confirmation Eventで生成する
- Human CorrectionはEventとしてReplay可能にする
- Open ItemはNode statusのactive（open）/ resolvedで表し、Resolve / ReopenはHuman Eventだけにする
- Analyzer同一応答内の新規Node参照はprovider-localなnew_node_indexを使い、Applicationがdeterministic IDへ解決する
- Current TopicのSemantic判定とUX上の表示安定化を分離する
- Discussion FlowはTopic Transition EventをCanonical Historyとする
- Driftは断定的なDecisionやErrorではなくDerived Signalとして扱う
- MapはStable Hybrid Presentationを基本とする
- Visual Artifactは独立Resource、MapにはMarker / Referenceを置く
- Visual GenerationはAsync、Suggested Switch、自動画面切替なし
- ArtifactはDiscussion Aidであり、MVPにFormal Adoption Stateを持たせない
- MinutesはStructured State + Evidence Hybridで生成する
- MinutesのDecisionsはConfirmedのみ
- Owner / Due / Next Topicを推測しない
- MinutesはDraft → Review → Confirm / Finalize → Markdown Export
- Prototype 1はFixed Transcript Replayを起点とする

### 25.2 Must Resolve Before Prototype

なし。Action Owner / Due、supports Relation Matrix、Parking時のCurrent Topic解除を含むPrototype 1のCanonical Contractは確定済みである。

Session finalizing / Drain ContractはLive STT依存のため、Prototype 1ではDeferredとする。

### 25.3 Validation Parameters

- Current TopicのHysteresis / Cooldown
- Current Topicの切替速度とConfidence
- Recent Flowの件数と表示方法
- Map Layout、Node間隔、Collapse、Stable Position
- Candidate Decisionの強調表示
- Question / UnresolvedのLabel
- Multiple Active Topicの表示
- Human Correctionの操作主体
- Evidence DrawerとCitation表示
- Session Summaryの情報量
- Visual Marker、Full Visual、Split View
- Minutes Summaryの長さとTopic Summaryの粒度

### 25.4 Deferred

- Live Audio / STT Providerの詳細
- Voice Intent、Automatic Visual Generation
- Artifact Adoption、Multiple Variant、Branch
- Speaker常時表示、話者別Minutes
- PDF / DOCX、外部配信
- Online Meeting Integration、Mobile UI
- Voting、Emotion / Personality Analysis、Speaker Evaluation
- Session横断Action通知、Due Date管理
- Provider Operations、Raw Response、Retention、Security Architecture
- 大規模会議、多言語最適化

### 25.5 Prototype 1 Scope

- Fixed Final Transcript Fixture
- Utterance Builder
- Fixture-drivenまたはDeterministic Discussion Analysis
- Candidate Event
- Event Stream
- Graph Materializer
- Topic、Idea、Option、Concern、Open Item
- Candidate / Confirmed Decision
- Human Confirm / Revoke
- Human Correctionの最小操作
- Current Topic
- Discussion Flow / Recent Flow
- Stable Discussion Map
- Replay / Deterministic Evaluation

### 25.6 Prototype 1 Non-scope

- Live Audio
- STT
- Partial Transcript
- Visual Image / Diagram Generation
- Full Minutes Generation / Export
- Provider Abstraction
- Online Meeting Integration
- Smartphone UI
- Voting
- AI Voice Facilitation
- Speaker Evaluation
- Emotion / Personality Analysis

## 26. Recommended Next Deliverables

実装開始前に、次の順で成果物を作ることを推奨する。

1. Discussion Domain Schema
2. Event Schema / Event Catalog
3. Evaluation Fixtures / Golden Outputs
4. Prototype Implementation Plan

最初の成果物は、Discussion Domain SchemaとEvent Schemaを別々に作るか、一つのDomain and Event Contract Documentとしてまとめる。これがPrototype 1の実装境界とReplay評価の基盤になる。
