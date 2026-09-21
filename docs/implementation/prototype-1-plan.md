# Prototype 1 Implementation Plan

> Recorded Real Analyzer Spike implementation status: boundary and evaluation harness added; actual Provider run is pending environment configuration. Live Audio / STT has not started.

| 項目 | 内容 |
| --- | --- |
| Status | M1〜M6 implemented and green; Prototype 1 review completed |
| Target | Discussion Map AI Facilitator MVP Prototype 1 |
| Canonical RD | [discussion-map-ai-facilitator-mvp.md](../requirements/discussion-map-ai-facilitator-mvp.md) |
| Architecture Baseline | [mvp-architecture-summary.md](../architecture/mvp-architecture-summary.md) |
| Domain Schema | [discussion-domain.schema.json](../../schemas/discussion-domain.schema.json) |
| Event Schema | [discussion-event.schema.json](../../schemas/discussion-event.schema.json) |
| Event Catalog | [discussion-event-catalog.md](../architecture/discussion-event-catalog.md) |
| Implementation status | M1〜M6完了、Real LLM / STT / Live Audioは未着手 |

本書はPrototype 1の実装順、責務境界、テスト境界を定義する。M1〜M6のコード実装とテストが完了し、Real LLM / STT / Live Audioは未着手である。

## 1. Prototype 1 Goal

Fixed TranscriptをReplayし、Discussion Mapが安定して成長し、Human Confirmation / Correctionを含む同じEvent StreamからDeterministicに同じDiscussion Graphを再現できることを検証する。

Prototype 1の中心的な成功条件は、会議中のDiscussion Mapとして次を追跡できることである。

- Topicが追加される
- 同じTopicへ戻っても同じNodeを再利用する
- Candidate Decisionが自動Confirmedにならない
- Human Confirm / RevokeがEventとして反映される
- Open Item、Action、Parking Lotが区別される
- Current TopicとRecent Flowが変化する
- Human Correction後も既存Nodeの位置関係を維持できる
- 同じOrdered Event StreamをReplayすると同じGraph RevisionとFinal Graphになる

## 2. Canonical Baseline

Prototype 1では次の責務分離を変更しない。

~~~text
Transcript Evidence = 発言の根拠
Event Stream        = Append-onlyな履歴
Discussion Graph    = Event StreamからMaterializeするCurrent State
~~~

AnalyzerはCandidate Eventを生成するが、Graphを直接変更しない。MaterializerはLLM、STT、Clock、Randomnessを呼び出さない。

### 2.1 Canonicalized contracts

今回のCanonicalizationで次を固定した。

1. Action
   - Analyzerは明示的な実行意図があるActionを検出できる。
   - action node_detected Payloadはowner / due_dateを持ち、Transcript Evidenceに明示された値だけを設定する。
   - 明示されない値はnullとする。
   - Analyzer由来の非null値はEvent Envelopeのsource_evidence_idsで追跡する。
   - Human update_actionは後から設定、修正、解除できる。
   - ActionにはDecisionと同じCandidate / Confirmed Lifecycleを追加しない。
2. supports
   - Source: idea、option
   - Target: idea、option、decision
   - Topicとの包含・一般的関連はcontainsまたはrelated_toで表現する。
   - Node Typeの組合せはEvent SchemaだけでなくMaterializerで検証する。
3. Parking Lot / Current Topic
   - Current Topicがparkedになったらprimary_topic_idはnull、modeはderived、confidenceはnullとする。
   - Human Override中でも同じ規則を適用し、Overrideを解除する。
   - restore_from_parking_lotはNodeをactiveへ戻すだけで、Current Topicへ自動復帰させない。
   - 復帰はHuman set_current_topicまたは次の明示的なAnalyzer topic_focus_changedだけで行う。
   - Node追加やConfidence変化だけでは復帰させない。
4. Open Item Lifecycle
   - Open Itemは既存Node statusの`active`をopen、`resolved`を解決済みとして使う。
   - `resolve_open_item` / `reopen_open_item`はHuman Commandから生成する。
   - Analyzerは自動Resolvedへ遷移させない。
   - resolved NodeはEvent Stream / Evidence / Replayに残し、Presentation Projectionの通常Cardからは外す。
5. Analyzer same-output references
   - Provider-facing `new_node_index`をLocal Referenceとして使い、LLMにCanonical Node IDを生成させない。
   - AdapterはNode intentを先にdeterministic IDへ割り当ててからRelationを解決する。
   - Valid Node + Invalid Relationの場合はNodeを保持し、RelationだけをDiagnostic付きでRejectする。

## 3. Scope

### 3.1 Include

- Fixed Transcript Evidence
- Utterance Replay
- Discussion AnalyzerのAdapter境界
- Candidate Event生成
- Append-only Event Stream
- Graph Materializer
- Graph Revision
- Current Topic
- Candidate Decision
- Human Confirm / Revoke
- Action Item
- Rename
- Merge
- Parking Lot / Restore
- Limited Undo（最新Rename CorrectionのInverse）
- Stable Discussion Map
- Recent Flow Projection
- 13個のEvaluation Fixture Replay
- Golden Graph比較
- Invalid Event検証
- Replay Determinism評価

### 3.2 Non-scope

- Live Audio
- STT
- Partial Transcriptの実時間処理
- Visual Artifact生成
- Image Generation
- Full Meeting Minutes生成・Export
- Online Meeting Integration
- Provider Abstractionの汎用化
- Multi-user Editing
- Production Authentication
- Smartphone UI
- Voting、AI Voice Facilitation、Speaker Evaluation、Emotion / Personality Analysis

Session finalizationのDrain条件はLive STT / Analysis依存のためPrototype 1では実装しない。SchemaとEvent Catalogにあるcreated / active / finalizing / endedの概念Contractは維持するが、Live Drainの完了判定は後続へDeferredする。

## 4. Repository Baseline

実Repositoryを確認した結果、現時点の主な構成は次のとおりである。

~~~text
docs/requirements/       Canonical RD
docs/rfc/                RFC-0001〜0005
docs/architecture/       Architecture Summary / Event Catalog
evaluation/fixtures/     001〜013のGolden Fixtures
schemas/                 Domain Schema / Event Schema
README.md                Repository概要
~~~

Prototype実装に利用できる既存の`src/`、Frontend、Backend、package manifest、テストRunnerはまだ存在しない。したがって、実装開始時に既存構成との互換性を保つ作業はなく、最初に小さなPrototype構成を決める必要がある。

ただし、最初から本番用のWorkspace構成、Provider SDK、認証、DB、Graph DBを導入しない。Prototype 1の評価対象はDomain / Event / Graph / Mapの中心Loopである。

## 5. Recommended Architecture

### 5.1 End-to-end Prototype Flow

~~~text
Fixed Transcript Evidence
        ↓
Utterance Replay
        ↓
Analyzer Adapter
        ↓
Candidate Events
        ↓
Event Store / Ordered Event Stream
        ↓
Pure Graph Materializer
        ↓
Current Discussion Graph
        ↓
Discussion Map Projection
        ↓
Stable Map Canvas
~~~

Human操作はAnalyzerを経由せず、Human Command HandlerからHuman EventとしてEvent Streamへ追加する。

~~~text
Human Command
      ↓
Event Validation + expected_revision
      ↓
Human Correction / Confirmation Event
      ↓
Event Stream
      ↓
Graph Materializer
~~~

### 5.2 Implementation layers

| Layer | 責務 | 所有してはいけないもの |
| --- | --- | --- |
| 1. Domain / Schema | Domain State、Event Envelope、Enum、Validation Contractを表す | UI位置、LLM出力そのもの |
| 2. Fixture Loader | evidence、events、expected graph、snapshotsを読み込む | Eventの意味解釈、Graph直接変更 |
| 3. Event Store | EventをAppendし、Session内sequenceとevent_idを検証する | Current Graphの直接更新 |
| 4. Graph Materializer | Ordered EventをPureに適用し、Graph Revisionを作る | LLM、Clock、Random ID |
| 5. Analyzer Adapter | UtteranceとContextからCandidate Eventを返す | Graphの直接書き込み、Human Confirm |
| 6. Replay Controller | FixtureまたはAnalyzer出力を順序付けてEvent Store / Materializerへ渡す | UI固有の判断 |
| 7. Human Command Handler | Confirm、Revoke、Rename、Merge、Parking、Current Topic等をEvent化する | Eventを削除・書換えすること |
| 8. Discussion Map Projection | GraphとEvent StreamからCurrent Topic、Status、Recent Flowを表示用に作る | Canonical Domain Stateの所有 |
| 9. Frontend / Static Map | 16:9共有ディスプレイ向けの最小Canvasを表示する | Analyzer、Materializer |
| 10. Evaluation Harness | Schema、Golden、Invalid、Replay、Analyzerの別評価を実行する | Fixtureを実装結果に合わせて自動更新すること |

### 5.3 State ownership

| State | Owner |
| --- | --- |
| Transcript Evidence | Evidence Store / Fixture Loader |
| Candidate Event | Analyzer Adapterが生成し、Event Storeが履歴として保持 |
| Human Correction Event | Human Command Handlerが生成し、Event Storeが保持 |
| Event ordering / sequence | Event Store / Replay Controller |
| Discussion Graph | Graph MaterializerのMaterialized View |
| Current Topic canonical state | Graph Materializer |
| Recent Flow | Topic focus Event StreamからのUI Projection |
| Node位置 | Map Projection / UI。Domain Graphへ戻さない |
| Golden expected graph | Evaluation Fixture |

## 6. Analyzer Boundary

### 6.1 Analyzer and Materializer contract

~~~text
Analyzer:
  Transcript / Utterance + Context
      → Candidate Events

Materializer:
  Initial Graph + Ordered Events
      → Canonical Discussion Graph
~~~

MaterializerにLLMを入れない。Analyzerが同じTranscriptから異なるCandidateを返す可能性はAnalyzer Evaluationで扱い、固定されたEventを適用するMaterializer Evaluationは完全Deterministicにする。

### 6.2 Analyzer implementation options

| Option | 内容 | 価値検証速度 | Determinism | Prototype 1での扱い |
| --- | --- | ---: | ---: | --- |
| Fixed Event Replay | 既存events.jsonを直接Materializerへ渡す | 最速 | 完全 | 最初に採用 |
| Fake / Rule-based Analyzer | Fixed UtteranceからFixtureで定義したEventを返す | 速い | 完全または制御可能 | Materializer成立後に採用 |
| Real LLM Analyzer | UtteranceとContextからCandidate Eventを生成 | 遅い | 低い | 最後のAdapter検証として任意実施 |

推奨順序は、Fixed Event Replay → Fake Analyzer → Real LLM Analyzerである。Real LLMから始めると、Node Identity、Relation Matrix、Current Topic、Materializerの問題と、LLMの出力揺れを分離できない。

Prototype 1のAnalyzer Adapterは、最初からProvider抽象化を目的にしない。`FixtureEventSource`と`FakeAnalyzer`の最小インターフェースを用意し、実LLMは同じCandidate Event Contractへ変換する追加経路として後から検討する。

## 7. Recommended Vertical Slice

### Slice A: Fixed Events → Graph → Static Map

~~~text
Fixture 001 events.json
        ↓
Fixture Loader
        ↓
Event Store
        ↓
Graph Materializer
        ↓
Expected Graph比較
        ↓
Static Discussion Map
~~~

最初のSliceではAnalyzerを通さない。これにより、Graph Materializer、Revision、Relation、Current Topic、Node Identity、Map Projectionを先に評価できる。

### Slice B: Fixed Transcript → Fake Analyzer → Graph → Map

~~~text
Fixture evidence.json
        ↓
Utterance Replay
        ↓
Fake Analyzer
        ↓
Candidate Events
        ↓
Event Store / Materializer
        ↓
Discussion Map
~~~

Slice AのGolden比較が成立した後にSlice Bを追加する。Slice BのAnalyzer評価は、MaterializerのGolden Testとは別のRequired Event Presence / Semantic評価とする。

## 8. Implementation Milestones

### M1: Domain Contract and Fixture Loader

**Goal**: 既存Schemaと13 Fixtureを実装入力として安全に読み込めるようにする。

**Deliverables**:

- Domain State / Event Envelopeの内部型または同等のContract表現
- Domain Schema / Event Schemaを参照するValidation入口
- Fixture Loader
- FixtureごとのSession、Evidence、Event、Expected Graph、Revision Snapshotの読み込み
- Canonical Action / supports / Parking Current TopicのContractチェック

**Acceptance Criteria**:

- 全13 Fixtureを読み込める
- session_id、Evidence参照、Event sequenceを検証できる
- Action node_detectedのaction.owner / due_dateを受け取れる
- 不正なEventをMaterializerへ渡す前に識別できる

**Dependencies**: 既存Schema、Event Catalog、Evaluation Fixtures

### M2: Event Store and Pure Graph Materializer

**Goal**: Ordered EventからCanonical Discussion GraphをDeterministicにMaterializeする。

**Deliverables**:

- Append-only Event StoreまたはIn-memory Event Stream
- total order（sequence）検証
- `apply(state, event) -> state'`相当のPure Materializer
- Node / Edge IDのDeterministic生成
- Graph Revision更新
- Decision、Action、Parking、Current Topic、RelationのDomain Rule

**Acceptance Criteria**:

- Fixture 001、002、003、004、005、007、008、012のValid Event Streamを期待Stateへ適用できる
- Candidate DecisionがAnalyzer Eventだけでconfirmedにならない
- supportsのMatrix外Eventを拒否する
- parked Current Topicをnullにし、restoreだけでは復帰させない
- Invalid EventではStateを部分更新しない

**Dependencies**: M1

### M3: Replay, Golden Output, and Determinism Evaluation

**Goal**: FixtureをRegression Testとして実行し、Replayの再現性を固定する。

**Deliverables**:

- 全Valid FixtureのGolden Graph比較
- Revision Snapshot比較（Fixture 003、004、006、007、008、009）
- Fixture 010のInvalid Event判定
- Fixture 011の二重Replay比較
- Node ID、Edge ID、Revision、Current Topicの比較
- Fixture変更を仕様変更としてレビューする仕組み

**Acceptance Criteria**:

- 13 FixtureをReplayできる
- Invalid EventはREJECT_EVENT / STATE_UNCHANGED相当で扱える
- 同一Initial State + 同一Ordered Event StreamでGraphが一致する
- Random ID、Clock、Event到着順に依存しない

**Dependencies**: M2

### M4: Human Command Handler and Correction Loop

**Goal**: Human操作が必ずEventとして履歴に残り、Replay可能になる。

**Deliverables**:

- confirm_decision
- revoke_decision
- rename_node
- merge_nodes
- archive_node
- move_to_parking_lot / restore_from_parking_lot
- set_current_topic
- update_action
- undo_last_correction（renameのみ）

**Acceptance Criteria**:

- Human Eventにexpected_revisionを付与できる
- Decisionのcandidate → confirmed → revokedを再現できる
- Merge元Nodeを物理削除せずarchivedとして保持できる
- RenameのUndoがInverse EventとしてReplayできる
- Human Override中のParkingでCurrent Topicが解除される

**Dependencies**: M2、M3

### M5: Stable Discussion Map UI Projection

**Goal**: Graphを16:9共有ディスプレイで会議中に理解できる最小Mapへ投影する。

**Deliverables**:

- Map Canvas
- Current Topic表示
- Topic、Idea、Option、Concern、Open Item、Decision、Actionの最小表示
- Candidate DecisionとConfirmed Decisionの視覚的分離
- Recent Flow strip
- Parking / Open / Actionの最小Status表示
- Human Commandの最小操作入口

**Acceptance Criteria**:

- Current Topicが一目で分かる
- CandidateとConfirmedを混同しない
- Topic Returnで元Node位置を再利用できる
- 新Node追加で既存Nodeを大きく再配置しない
- Rename、Merge、Parkingで既存Layoutが不必要に崩れない
- Replayの各RevisionをUIで確認できる

**Dependencies**: M3、M4

**M5実装結果**: 追加FrameworkなしのHTML/JavaScript UIを継続採用し、Python `StableLayout`でCanonical Node ID単位のTopic Lane / Card Stack位置を保持する。Replayは既存の`sequence`読込APIを利用し、M4 CommandはNode Detailから同じEvent経路へ送る。Auto pan / zoom、全体再配置、M6 Analyzerは実装していない。

### M6: Fake Analyzer and Evaluation Loop

**Goal**: Fixed TranscriptからCandidate Eventを生成する解析境界を追加し、Analyzer評価とMaterializer評価を分離する。

**Deliverables**:

- Utterance Replay
- Fake / Rule-based Analyzer Adapter
- Required Event Presence評価
- Semantic Event評価の入口
- `evidence → events → graph → map`のReplay UI
- UI ReplayとFixture Testを同じEvaluation Loopから起動する仕組み

**Acceptance Criteria**:

- Fixture 001、002、005、008のTranscriptから必要なCandidate Eventを生成できる
- Analyzerが生成するEventはEvent SchemaとEvidence Linkに適合する
- Analyzerの誤差がMaterializer Golden Testの結果を隠さない
- 同じFake Analyzer入力で同じEvent Streamを生成できる

**Dependencies**: M3、M4、M5

Real LLMの接続はM6の必須完了条件ではない。接続する場合も、Candidate Eventを出すAdapterの検証に限定し、Provider固有の設計をPrototype 1のCanonical Domainへ持ち込まない。

**M6実装結果**: `prototype/analyzer.py` にHybrid Fake AnalyzerとTranscriptReplaySessionを追加した。既知FixtureはAnalyzer Event TemplateをEvidenceへ紐付けてExact Mappingし、未知入力には限定的なRule-based fallbackを適用する。Candidate EventにはDeterministicなproducer event_idだけを持たせ、Canonical sequenceはReplay / Event Store境界で付与する。AnalyzerはGraph、Event Store、Materializer、Human Eventを直接操作しない。

M5 UIへ`Transcript + Fake Analyzer`モード、Final Utterance表示、Analyzing / Updated / Complete Indicator、Transcript Step / Play / Reset APIを追加した。M6専用の`evaluation/scenarios/m6-e2e.json`では、Candidate DecisionのHuman ConfirmとTopicのParkingをTranscript Replay途中に混在させ、Replay後のDeterministic Graph一致を確認する。

## 9. Testing Strategy

### 9.1 Unit tests

最低限、次をMaterializer単位で検証する。

- Event Envelopeのrequired / enum / actor / expected_revision
- sequence gap、duplicate sequence、duplicate event_id
- Node生成とDeterministic ID
- Edgeの存在検証とRelation Matrix
- Decision candidate → confirmed → revoked
- Actionのowner / due_date null、Evidence由来値、Human update_action
- Rename、Archive、Merge
- Parking / Restore / Current Topic解除
- Human Overrideと明示Focus復帰
- Graph Revisionとlast_event_sequence
- Undo Rename

### 9.2 Golden Fixture tests

Fixed `events.json`を入力し、`expected-final-graph.json`の`graph`をGolden Outputとして比較する。Expected Graphに合わせて実装を調整しない。仕様変更がある場合は、先にRD / RFC / Schema / Catalogを変更し、その後にFixtureを更新する。

### 9.3 Revision Snapshot tests

Fixture 003、004、006、007、008、009は各Revision Snapshotを比較する。

- revision
- last_event_sequence
- nodes
- edges
- current_topic

特にFixture 007では、Parking時の`primary_topic_id=null`と、Restore直後もFocusがnullであることを比較する。

### 9.4 Replay Determinism

同じInitial Stateと同じOrdered Event Streamを少なくとも2回適用し、次を比較する。

- Node ID
- Edge ID
- Node Label / Type / Status
- Action Details
- Current Topic
- Graph Revision
- Last Event Sequence

比較はまずCanonical JSONのbyte-level一致を目標とし、将来の並び順変更がある場合もsemantic comparatorで差分理由を明示する。

### 9.5 Analyzer Evaluation

Analyzer評価はMaterializer評価から分離する。

- Exact: Event Type、Node Type、Evidence Linkが一致
- Semantic: Labelの意味と対象Evidenceが一致
- Required Event Presence: 必須Candidate Eventが存在

Analyzerの出力揺れを理由にGolden Graphを更新しない。Materializerへ渡すEventを固定したときは、完全Deterministicな結果を要求する。

### 9.6 UI Replay / Layout evaluation

各FixtureのEventまたはRevision Snapshotを順にMapへ再生し、次を確認する。

- Current Topicの認識
- Candidate / Confirmedの区別
- Recent Flowの更新
- Topic Return時のNode再利用
- 既存Node位置の維持
- Parking時のCurrent Topic解除
- Human Correction後の局所更新

## 10. UI Prototype Boundary

### 10.1 Minimum UI

Prototype 1は、RFC-0003の全Status Railを完成させるのではなく、Discussion Mapの中心価値を検証する最小UIに絞る。

- Map Canvas
- Header: Title、Revision、Replay / Live-like status
- Current Topic cardまたはMap上のFocus badge
- Topic、Idea、Option、Concern、Open Item、Decision、Action Node
- Candidate DecisionとConfirmed Decision
- Recent Flow strip
- 最小のOpen Item / Action / Parking summary
- Confirm、Revoke、Rename、Merge、Parking、Restore、Set Current Topic、Undo Renameの操作入口

Evidence本文、Visual Artifact、Minutes本文、Speaker常時表示はPrimary Viewへ常時出さない。必要ならDetailまたはFixture検証用の補助表示に留める。

### 10.2 Stable Layout contract

Domain GraphへUI座標を保存しない。Map ProjectionがNode IDをKeyにして表示位置を保持する。

- Existing Nodeは既存位置を維持する
- New Nodeは空きSlotまたは新しいTopic Laneへ追加する
- 全体再配置、Fit-to-screen、Zoom変更を自動で行わない
- Topic Returnは同じNode IDの元位置を再利用する
- Renameは位置を変えない
- Mergeはtarget位置を維持し、sourceを非表示またはArchived表示にする
- Parkingは対象NodeをParking領域へ移すが、他のNodeを全面再配置しない
- Current Topic切替はFocus表示だけを移動し、Map全体を動かさない

初期Prototypeでは、固定Topic Lane + 局所Tree / Card StackのDeterministic Layoutを推奨する。既存RepositoryにFrontendやLayout Libraryがないため、最初から自由Graph Layout Libraryを導入しない。必要になった場合の候補は、軽量なSVG / HTMLレイアウト、React Flow系のInteractive Graph、制約付きLayout Engineであるが、選定はValidation Parameterとする。

### 10.3 Human Command UI

操作はNodeのDetailまたは小さなContext Actionに限定し、自由なGraph Editorにしない。

| 操作 | Prototypeの最小挙動 |
| --- | --- |
| Confirm Decision | candidate decisionをconfirm_decision Eventにする |
| Revoke Decision | confirmed decisionをrevoke_decision Eventにする |
| Rename Node | rename_node EventをAppendする |
| Merge Node | sourceをarchived、targetをCanonicalにする |
| Move to Parking Lot | statusをparkedにし、Current Topicなら解除する |
| Restore | parkedをactiveに戻す。Focusは戻さない |
| Set Current Topic | set_current_topic EventをAppendする |
| Undo Rename | 最新renameのInverse EventをAppendする |

## 11. Evaluation Loop

Prototype実装後の各変更は次の順で評価できるようにする。

1. Schema / Event Validation
2. Unit Tests
3. Fixture Golden Test
4. Replay Determinism Test
5. UI Replay
6. Analyzer Evaluation
7. Static Map / Human Evaluation

失敗時は、まずContract、Event Stream、Materializer、Projection、Analyzer、UIのどの層かを分離して報告する。

## 12. Definition of Done

Prototype 1は、次をすべて満たした時点で完了とする。

- 13個のEvaluation FixtureをReplayできる
- Valid Fixtureが期待Graphに到達する
- Invalid Eventを拒否し、Stateを部分更新しない
- Replay Determinismが成立する
- Candidate Decisionが自動Confirmedされない
- Human Confirm / Revokeが機能する
- Topic Returnで重複Nodeを作らない
- Current Topic OverrideがCanonical Policyどおり動く
- Parking時にCurrent Topicが解除される
- RestoreだけではCurrent Topicへ復帰しない
- Human CorrectionがReplay可能である
- ActionのOwner / Dueが推測されず、Evidence明示値またはnullになる
- supports Matrix外のRelationを拒否する
- Mapの既存Node位置が大きく変わらない
- UI上でDiscussionの現在状態を理解できる

## 13. Implementation Order

以下は実装開始後の順序である。本書作成時点では、どのStepも未着手である。

### Step 1: Contract-driven Fixture Loader

**前提**: Domain Schema、Event Schema、Event Catalog、Fixtureが存在する。

**作成対象**:

- Fixture Directoryの発見
- evidence / events / expected graph / snapshotsの読込
- Event EnvelopeとDomain StateのValidation入口
- Session参照、Evidence参照、sequence検証

**テスト方法**: 13 Fixtureの読込、Action Payload、Open Item Lifecycle、supports invalid case、Parking Snapshotの検証。

**完了条件**: すべてのFixtureを検証可能な入力オブジェクトへ変換でき、Invalid Fixtureを意図的に識別できる。

### Step 2: Ordered Event Store

**前提**: Step 1でValidated Eventを取得できる。

**作成対象**: Append、event_id重複検出、sequence Total Order、Session一致、Human expected_revisionの受付。

**テスト方法**: Fixture 010のduplicate、gap、out-of-order、revision mismatch。

**完了条件**: Canonical Ordered Event StreamだけをMaterializerへ渡せる。

### Step 3: Pure Graph Materializer

**前提**: Step 2のOrdered Event Stream。

**作成対象**: State transition、Node / Edge ID、Revision、Current Topic、Decision、Action、Relation、Parking、Merge、Undo。

**テスト方法**: Fixture 001〜009、012〜013のGolden GraphとRevision Snapshot。

**完了条件**: Fixed Events → Expected Graphが一致し、Materializer内部にLLM / Clock / Randomnessがない。

### Step 4: Replay and Determinism Harness

**前提**: Step 3でMaterializeできる。

**作成対象**: Initial StateからのReplay、2回比較、Golden comparator、Invalid Event report。

**テスト方法**: Fixture 011、全Valid Fixture、Revision Snapshot。

**完了条件**: 同じEvent Streamから同じID、Revision、Current Topic、Graphを再現できる。

### Step 5: Human Command Handler

**前提**: Step 3のEvent適用とRevision検証。

**作成対象**: Confirm、Revoke、Rename、Merge、Archive、Parking、Restore、Set Current Topic、Update Action、Undo Rename。

**テスト方法**: Human EventをAppendしてStep 4のReplayを再実行する。Fixture 003、004、006、007、008、009を使用する。

**完了条件**: Human操作がGraph直接変更ではなくEventとして履歴に残り、同じReplay結果になる。

### Step 6: Static Discussion Map Projection

**前提**: Step 4とStep 5のGraph / Flowが安定している。

**作成対象**: 16:9 Map Canvas、Current Topic、Candidate / Confirmed、Open Item、Action、Recent Flow、最小Correction UI。

**テスト方法**: Fixture 002、003、007、008、009をRevision順に再生し、既存位置・Focus・状態表示を比較する。

**完了条件**: Static Replayだけで、参加者がCurrent Topic、Decision状態、Open Item、Topic Return、Parkingを説明できる。

### Step 7: Fixed Transcript / Fake Analyzer Adapter

**前提**: Step 3〜6でFixed EventsとMapが安定している。

**作成対象**: Evidence → Utterance、Fake Analyzer、Candidate Event出力、Required Event Presence evaluator。

**テスト方法**: Fixture 001、002、005、008のTranscriptからEventを生成し、Event Schema、Evidence Link、Golden Materializerへ接続する。

**完了条件**: AnalyzerとMaterializerの評価結果を別々に出力できる。同じFake Analyzer入力が同じCandidate Eventsになる。

### Step 8: Evaluation and Prototype Review

**前提**: Step 7までの全自動評価。

**作成対象**: Regression command、UI Replay report、Layout stability report、Prototype evaluation notes。

**テスト方法**: Definition of Done、Prototype Success Criteria、Shared DisplayのStatic Evaluation。

**完了条件**: Implementation変更ごとにFixture、Replay、UI、Analyzerの4つの評価を再実行できる。

## 14. Prototype Success Criteria

Prototype 1の最低限の評価項目は次のとおりである。

- Topicが追加される
- 同一Topicに戻れる
- Candidate Decisionが出る
- Human Confirmできる
- Confirmed DecisionがMapへ反映される
- DecisionをRevokeできる
- Open Itemが残る
- Current Topicが切り替わる
- Human Override中にNode追加だけでは切り替わらない
- Recent Flowが更新される
- Parking時にCurrent Topicが解除される
- RestoreだけではCurrent Topicへ戻らない
- Mapの既存位置が大きく変わらない
- Replayして同じStateを再現できる
- Human CorrectionをReplayできる
- Action Owner / Dueの非推測とEvidence追跡を確認できる
- supports Matrix外のRelationが拒否される

## 15. Validation Parameters and Deferred Items

### 15.1 Can Decide During Prototype

- Current TopicのHysteresis / Cooldown
- Analyzerがtopic_focus_changedを出す継続条件
- Recent Flowの表示件数
- Candidate Decisionの強調度
- Map Laneの幅、Node間隔、文字サイズ
- Merge / Parking後の最小Animation
- Evidence Detailの開き方
- Current Topicがnullのときの共有画面表示
- Fake AnalyzerのRequired Event Presence評価基準

これらはCanonical StateやEvent Schemaを変更せず、Prototype FixtureとStatic Mapで比較する。

### 15.2 Deferred After Prototype 1

- Live Audio、STT、Partial Transcript、Finalization Drainの実測値
- Real LLM Providerの選定とProvider Capability
- Visual Artifact生成
- Full Meeting Minutes生成・Markdown Export
- Online Meeting Integration
- Multi-user Editing、Authentication、Persistence Operations
- Speaker Identificationの高度なUX
- Large Map、Multiple Primary Topic、Session横断Action管理

## 16. First Implementation Recommendation

最初に実装すべきコードStepは、**Step 1: Contract-driven Fixture Loader**である。既存のSchemaとGolden Fixtureを入力契約として固定し、実装がFixtureを都合よく解釈しない入口を先に作る。

最初のユーザー価値に近いVertical Sliceは、その直後の**Step 2 → Step 3 → Step 4 → Step 6**である。

~~~text
Fixture 001 Fixed Events
        ↓
Event Store
        ↓
Pure Graph Materializer
        ↓
Golden / Replay Check
        ↓
Stable Discussion Map
~~~

このSliceが成立するまで、Live Audio、STT、Real LLM、Visual、Minutes、Provider Abstractionを開始しない。

## 17. Implementation Readiness

Prototype 1のDomain / Event / Relation / Current Topic Contractに、M1〜M3を妨げるCriticalな未解決事項は残っていない。

Session Finalization DrainはLive実装の前提であり、Prototype 1のFixed Replayを妨げないためDeferredとする。

したがって、Repositoryは**M1〜M6完了・Prototype 1 Reviewへ進める状態**にある。次段階はReal LLM / STT / Live Audioではなく、`docs/evaluation/prototype-1-review.md` に記録したTechnical Debtと、実Analyzerへ差し替える前のProvider非依存Contract検証である。

## 18. Recorded Real Analyzer Spike

Recorded Real Analyzer Spikeの実装境界は追加済みである。

- `prototype/real_analyzer.py`: Provider、Context Builder、Prompt Version、Structured Output変換、安全検証、Run Record
- `prototype/real_evaluation.py`: 5 ScenarioのSemantic / Safety / Latency / Usage評価Harness
- `prototype/recorded.py`: Recorded TranscriptとHuman Golden AnnotationのLoader
- `schemas/real-analyzer-output.schema.json`: Provider-facing Intent Schema（Canonical Event Schemaとは分離）
- `prototype/app.py` / `prototype/server.py` / `prototype/web/index.html`: Fake / Real Analyzer Replay Mode
- `docs/evaluation/real-analyzer-spike-review.md`: Spike判定とProvider未設定時の評価結果

ProviderがCandidate Intentだけを返し、ApplicationがCanonical Eventへ変換した後に既存のEvent Store / Graph Materializer / Stable Mapを通る。Provider未設定・Output不正・安全違反はGraphへ適用せず、Evidenceを保持してRun Recordへ記録する。実ModelのSemantic評価はProvider設定後に同じDatasetで再実行する。
