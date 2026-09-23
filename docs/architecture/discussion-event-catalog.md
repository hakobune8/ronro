# Discussion Event Catalog

| 項目 | 内容 |
| --- | --- |
| Status | Proposed for Prototype 1 |
| Domain Schema | [discussion-domain.schema.json](../../schemas/discussion-domain.schema.json) |
| Event Schema | [discussion-event.schema.json](../../schemas/discussion-event.schema.json) |
| Canonical RD | [discussion-map-ai-facilitator-mvp.md](../requirements/discussion-map-ai-facilitator-mvp.md) |
| Last Updated | 2026-09-19 |

本書は、Prototype 1で使用するDiscussion Eventの最小Catalogである。

> 2026-09-23追記: `discussion_provenance` は[最小意味Graph仮説実装](../evaluation/minimal-semantic-graph-hypothesis.md)で追加された、Evidence必須のNode間Relationである。議論上の派生のみを表し、物理的因果・決定の確定・未解決事項の解決・Actionの実行を表さない。現行Prompt/本番画面へは未適用で、分類はHuman Review待ちの作業仮説である。

目的は、Fixed Transcriptを同じ順序でReplayしたとき、同じEvent Streamから同じDiscussion Graphを再現できるようにすることである。

本書では次を維持する。

- Transcript = Evidence
- Event Stream = History
- Discussion Graph = Current State
- Human Correction = Event
- Candidate DecisionはHuman ConfirmationなしにConfirmedにならない
- MaterializerはLLM、Clock、Randomnessに依存しない
- Prototype 1ではLive Audio、STT、Visual Generation、Full Minutesを実装しない

## 1. Prototype 1 Domain Decision

### 1.1 Decision Nodeの表現

Prototype 1では、Candidate DecisionとConfirmed Decisionを別Node Typeにしない。

~~~text
Node Type: decision
  status: candidate → confirmed → revoked
~~~

理由:

- CandidateからConfirmedへのNode IDを維持できる
- Confirm / Revokeが同じNodeのState Transitionになる
- Event ReplayとEvidence参照が単純になる
- Mapで表示Labelだけを変えられる
- Minutesでstatusを検証しやすい

Schema上のNode Typeはdecision一つとし、candidate_decision / confirmed_decisionはUIおよびMinutes上の表示概念とする。

### 1.2 Parking Lotの表現

Parking Lotは独立Node Typeにしない。

~~~text
Topic Node
  status: active → parked → active
~~~

Parking LotはNodeのstatus parkedと、Map / Minutesでのグループ表示から導出する。これによりTopicのIDと関係を保ったまま、後でRestoreできる。

### 1.3 QuestionとUnresolved

Prototype 1ではNode Typeをopen_itemへ統合する。

QuestionかUnresolvedかの表示上の差が必要になった場合は、後続のDomain拡張で別属性を検討する。Prototype 1では同じNode IDとStateを使う。

### 1.4 Open Item Lifecycle Amendment

Prototype 1では、Open ItemのCanonical Node `status`をLifecycleに使う。専用の
`open_item_status`属性は追加しない。

~~~text
open_item.status: active (open) → resolved
                         ↑         ↓
                         └─ reopen ┘
~~~

- `resolve_open_item` と `reopen_open_item` はHuman Eventだけとする。
- Analyzerは自動でresolvedへ遷移させない。Resolution Candidateの検出は将来検討する。
- `archive_node`、Parking、Mergeは「質問に回答した」ことを表さない。
- resolved Node、Evidence、Creation Event、Resolve / Reopen Eventは物理削除しない。
- Reopenはresolvedからactiveへ戻すだけで、Current Topicを変更しない。

## 2. Canonical Domain Entities

### 2.1 Session

SessionはDiscussionのライフサイクルとGraph Revisionの境界を持つ。

必須の概念:

- id
- title
- goal
- status
- created_at
- started_at
- ended_at
- graph_revision

Session status:

- created
- active
- finalizing
- ended

Session statusとMinutes statusは別である。Sessionがendedでも、Minutesはdraftまたはgeneration_failedであり得る。

### 2.2 Transcript Evidence

Transcript Evidenceは発言の根拠であり、NodeやDecisionのCurrent Stateではない。

必須の概念:

- id
- session_id
- sequence
- timestamp
- speaker
- text

Prototype 1ではFixed Transcriptから作成する。speakerは不明ならnullを許可する。

Partial TranscriptはDomain SchemaのTranscript Evidenceに含めない。PartialはSTT / UIのEphemeral Stateとして扱う。

### 2.3 Utterance

UtteranceはFinal Transcript EvidenceをAnalysis単位へまとめたProjectionである。

Prototype 1では、1つまたは複数のTranscript Evidence ID、sequence、text、started_at、ended_atを持つ。

UtteranceはEvent StreamのEventではない。UtteranceからDiscussion AnalyzerがEventを生成する。

### 2.4 Discussion Node

Prototype 1のNode Typeは次の7種類に限定する。

| Type | 役割 |
| --- | --- |
| topic | 議論のテーマ・論点 |
| idea | 意見・アイデア |
| option | 選択肢・案 |
| concern | 懸念 |
| open_item | Questionまたは未解決事項 |
| decision | Candidate / Confirmed / RevokedのDecision |
| action | 会議後に実行する作業 |

Parking LotはNode Typeではなくstatus parkedで表す。

### 2.5 Node Status

共通Node statusは次の最小集合とする。

- active
- candidate
- confirmed
- revoked
- resolved
- parked
- completed
- archived

すべてのTypeがすべてのStatusを利用するわけではない。

| Node Type | Prototypeで許可する主なStatus |
| --- | --- |
| topic | active、parked、archived |
| idea | active、archived |
| option | active、resolved、archived |
| concern | active、resolved、archived |
| open_item | active、resolved、parked、archived |
| decision | candidate、confirmed、revoked、archived |
| action | active、archived。詳細Statusはaction.status |

JSON Schemaでは簡潔さのため共通Enumを定義し、MaterializerがTypeとStatusの組合せを検証する。

### 2.6 Edge

Prototype 1で許可するEdge Typeは次の5種類とする。

- contains
- has_option
- supports
- opposes
- related_to

次はPrototype 1のSchemaへ含めない。

- depends_on
- results_in
- 自由文字列Relation

Edgeはsource_node_idからtarget_node_idへの有向Relationである。sourceとtargetの意味はRelation Typeで固定する。

| Edge Type | 用途 |
| --- | --- |
| contains | TopicがIdea、Concern、Open Item、Decision、Action等を含む |
| has_option | TopicがOptionを持つ |
| supports | Idea / Optionが別Nodeを支持する |
| opposes | Idea / Optionが別Nodeと対立する |
| related_to | その他の明示的な関連 |

## 3. Node Identity

### 3.1 基本方針

LLMまたはDiscussion Analyzerに、ランダムなCanonical Node IDを生成させない。

Node IDの責務はGraph Materializerに置く。

### 3.2 New Node ID

新しいNodeを作るnode_detected Eventのevent_idから、MaterializerがDeterministicにNode IDを作る。

概念式:

~~~text
node_id = stable_node_id(session_id, creation_event_id)
~~~

Prototype 1での推奨実装上の表現は次のようなNamespace付きIDである。

~~~text
node:<session_id>:<creation_event_id>
~~~

実際の文字列表現はSchemaでPattern制約を設けない。重要なのは、同じsession_idとcreation_event_idから同じIDが得られることである。

### 3.3 Existing Node Reference

Analyzerが既存Nodeへ言及する場合、LLMがLabelからIDを発明しない。

Analyzerへ渡したGraph Contextに存在するIDを、次のEvent Payloadでそのまま参照する。

- topic_focus_changed.payload.topic_id
- topic_focus_changed.payload.previous_topic_id
- relation_detected.payload.source_node_id
- relation_detected.payload.target_node_id

指定されたIDが存在しない場合、MaterializerはEventをInvalid Referenceとして拒否する。

既存Topicかどうか判断できない場合、Analyzerは既存IDを推測せず、新しいnode_detectedを出す。類似Nodeの統合はHuman merge_nodesで行う。

### 3.4 Node Return

同じTopicへ戻るときは、新しいnode_detectedを出さず、既存Topic IDをtopic_focus_changedで参照する。

これにより、次を保証する。

- TopicのNode IDが変わらない
- Graph上の位置を維持できる
- Discussion Flowで戻りを記録できる
- Duplicate Topic生成を減らせる

## 4. Event Envelope

すべてのEventは、Event Type固有Payloadの外側に共通Envelopeを持つ。

| Field | Required | 意味 |
| --- | --- | --- |
| event_id | Yes | Eventを一意に識別する。LLMは生成しない |
| session_id | Yes | Eventが属するSession |
| sequence | Yes | Session内のCanonical Total Order |
| event_type | Yes | Event Catalogに定義されたEnum |
| occurred_at | Yes | Eventが生成された時刻。順序には使わない |
| actor | Yes | analyzer、human、system |
| source_evidence_ids | Yes | 根拠Evidence ID。ない場合は空配列 |
| causation_id | No | 直接の原因Event ID |
| correlation_id | No | 同じ処理・Commandに属するEvent群のID |
| expected_revision | HumanでRequired | Commandが期待するGraph Revision |
| payload | Yes | Event Type固有のObject |

### 4.1 event_id

event_idはEvent ProducerまたはFixtureが一度だけ割り当て、Event Streamに保存する。

- LLMはevent_idを生成しない
- Replay時に新しいevent_idを作らない
- 同一session内で重複させない
- Event IDの文字列形式はSchemaで過剰制約しない

### 4.2 sequence

sequenceはSession内で1から始まる整数のTotal Orderである。

- Event Streamが割り当てる
- Fixed Fixtureでは明示的に固定する
- timestamp、event_id、配列の到着順をCanonical Orderにしない
- 同じtimestampのEventもsequenceで順序付ける

### 4.3 occurred_at

occurred_atは表示、Evidence、Latency分析のために保持する。Replayの適用順序には使用しない。

Clockを使ったMaterializer分岐は禁止する。

### 4.4 actor

Prototype 1では次の3種類だけを許可する。

- analyzer: Discussion Analyzerが生成したCandidate Event
- human: ユーザーのConfirm、Correction、Command
- system: Session Lifecycle Event

具体的なuser_id、model_id、provider_idはPrototype 1のEnvelopeへ含めない。

## 5. Event Ordering

### 5.1 Canonical Order

Event StreamのCanonical Orderはsequenceの昇順とする。

~~~text
sequence 1 → sequence 2 → sequence 3 → ...
~~~

### 5.2 Out-of-order Event

Prototype 1では、Materializerへ渡すEventはTotal Order済みでなければならない。

- 次に期待するsequence以外を受け付けない
- 先行EventがないsequenceはMissing Sequenceとして停止する
- 後着EventはEvent Stream側でBufferまたはRejectする
- Materializerがtimestampで並べ替えない

Live実装でのBuffer時間、再順序化、遅延EventのReprocessはRFC-0002の後続実装Parameterである。

### 5.3 Duplicate Event

同一event_idまたは同一sequenceの重複EventはCanonical Streamへ二重Appendしない。

Prototype 1のMaterializerでは、既に適用済みのsequenceが再入力された場合、Input Contract違反として拒否する。RetryのIdempotencyはEvent StoreまたはReplay Runnerが重複排除してからMaterializerへ渡す。

## 6. Graph Revision

### 6.1 定義

graph.revisionは、Ordered Event Streamを何Event適用したかを示すMaterialized State Versionである。

Prototype 1では、次の単純な規則を採用する。

- Initial State: revision 0、last_event_sequence 0
- Valid Eventを1件適用するたびにrevisionを1増やす
- Eventのsequenceをlast_event_sequenceへ記録する
- Invalid Eventはrevisionもlast_event_sequenceも増やさない
- system Eventを含むすべてのValid Eventを順序付きState Checkpointとして扱う

したがって、連続したEvent Streamでは次が成立する。

~~~text
graph.revision == graph.last_event_sequence
~~~

将来、Graphに影響するEventだけでrevisionを増やす最適化は可能だが、Prototype 1ではTotal OrderとState Checkpointを同じ進み方にしてDebugしやすくする。

### 6.2 expected_revision

Human Eventはexpected_revisionを必須とする。

Materializerは、Event適用前のgraph.revisionとexpected_revisionが一致することを確認する。

- 一致: 適用する
- 不一致: revision_mismatchとして拒否する
- 自動Mergeや自動Retryで別Revisionへ適用し直さない

人間は最新Graphを確認して、必要なら新しいEventを再発行する。

## 7. Replay Determinism

### 7.1 保証

同じInitial Stateと同じOrdered Event Streamを入力した場合、同じDiscussion Graphを再現する。

~~~text
materialize(initial_state, [event_1, event_2, ... event_n])
  ==
materialize(initial_state, [event_1, event_2, ... event_n])
~~~

比較対象には次を含める。

- Node ID
- Node Type、Label、Status
- Action Details
- Edge ID、Source、Target、Type
- Current Topic
- Graph Revision
- Last Event Sequence

### 7.2 Materializerで禁止する依存

- LLM呼び出し
- STT呼び出し
- 現在時刻
- Random UUID生成
- Random choice
- OS、Locale、Timezoneに依存する暗黙の分岐
- Event配列の到着順
- Map Layout結果をDomain Stateへ戻すこと

### 7.3 Confidenceの扱い

Confidenceは意味を持つ場所に限定する。

- Prototype 1ではtopic_focus_changedのconfidenceだけ許可する
- 値は0.0〜1.0
- Current Topicの表示・切替Policyで使う候補値
- Decision、Idea、Actionに一律confidenceを追加しない
- ConfidenceだけでDecisionをConfirmedにしない

同じConfidence値でも、Materializerの分岐は固定Policyでなければならない。Prototype 1ではFixture側でTopic Transitionを明示し、閾値の実験はUX / Validation層へ分離する。

## 8. Materializer Contract

### 8.1 Pure Function

Materializerは概念上、次のPure Functionとして扱う。

~~~text
apply(state, event) -> state'
~~~

実装がErrorを返す場合:

~~~text
apply(state, event) -> { state: state', error: null }
apply(state, invalid_event) -> { state: state, error: deterministic_error }
~~~

Invalid EventではStateを部分更新しない。

### 8.2 適用前Validation

各Eventについて、次を順に検証する。

1. Event Schemaに適合する
2. session_idがStateのSessionと一致する
3. sequenceがlast_event_sequence + 1である
4. Human Eventならexpected_revisionがgraph.revisionと一致する
5. Payloadが参照するNode、Edge、Evidenceが存在する
6. Event TypeとactorがCatalogの組合せに一致する
7. Type / Statusの遷移が許可されている
8. 自己Merge、重複Edge、無効なParking Lot移動などのDomain Ruleを満たす

### 8.3 Invalid Event

Invalid Eventの種類を最低限次のように分ける。

- schema_invalid
- session_mismatch
- sequence_gap
- duplicate_sequence
- duplicate_event_id
- missing_reference
- invalid_transition
- revision_mismatch
- unsupported_relation
- unsupported_correction

Prototype 1ではInvalid Eventを黙ってSkipしない。Replay結果を評価するため、Materializerを停止してErrorを返す。

### 8.4 Missing Node

Missing Nodeを参照するEventは拒否する。

例:

- 存在しないtopic_idへのtopic_focus_changed
- 存在しないdecision_node_idへのconfirm_decision
- 存在しないsource_node_idへのrelation_detected

AnalyzerがNode生成とRelation生成の順序を誤った場合、Event Streamの順序を修正するか、Analyzer Event生成を修正する。Materializerが将来Eventを先読みして補完しない。

### 8.5 Duplicate Semantic Relation

同じsource、target、relation_typeのRelationが別Eventで届いた場合:

- Graph上のEdgeは一つだけ保持する
- 同じEdgeのsource_event_idsへ新しいEvent IDを追加するかはTraceability Policyで固定する
- Prototype 1ではEdgeの意味構造を増やさず、同じEdgeの重複適用をNo-opとする
- Event自体はHistoryとして残る

Prototype 1の比較を単純にするため、Graph SemanticはNo-op、Event Streamは全履歴保持とする。

## 9. Domain EventとGraph Stateの分離

Eventは状態の命令・観測・Correctionであり、Graph Nodeそのものではない。

例:

~~~text
node_detected
    ↓ Materializer
Discussion Nodeが作られる

confirm_decision
    ↓ Materializer
同じDecision Nodeのstatusがcandidateからconfirmedへ変わる
~~~

GraphにEvent全体をNodeとして追加しない。EvidenceやEvent IDはNodeのsource_event_ids / evidence_idsへTraceabilityとして参照する。

## 10. Analyzer Event Catalog

Prototype 1では、Analyzer用のEvent TypeをNode Typeごとに増やさず、次の3種類へ集約する。

| Event Type | 用途 | Graphへの効果 | Evidence |
| --- | --- | --- | --- |
| node_detected | Topic、Idea、Option、Concern、Open Item、Decision、Actionの新規候補 | MaterializerがDeterministicなNodeを作る | 1件以上必須 |
| relation_detected | 既存Node間のRelation候補 | Materializerが許可されたEdgeを追加する | 1件以上必須 |
| topic_focus_changed | 既存Topic間の意味上のFocus遷移候補 | Current Topic Projectionを更新する | 1件以上必須 |

### 10.1 Semantic Event名との対応

RDやRFCで使われるtopic_detected、idea_detected、option_detected、concern_detected、open_item_detected、decision_candidate_detected、action_detectedは、Prototype 1では独立したCanonical Event Typeにしない。

~~~text
topic_detected             -> node_detected { node_type: topic }
idea_detected               -> node_detected { node_type: idea }
option_detected             -> node_detected { node_type: option }
concern_detected            -> node_detected { node_type: concern }
open_item_detected          -> node_detected { node_type: open_item }
decision_candidate_detected -> node_detected { node_type: decision }
action_detected             -> node_detected { node_type: action }
~~~

この集約を採用する理由は、Event Schema、Materializer、Replay Fixtureの分岐を最小化し、Node Typeの追加とEvent Typeの追加を独立させるためである。

parking_lot_detectedはCanonical Eventにしない。Parking Lotへの移動は、既存Nodeを対象とするHuman Correctionのmove_to_parking_lotで確定する。Analyzerが「後で扱う候補」を示す必要がある場合は、まずopen_itemまたはtopicのCandidateを生成し、人間がParking Lotへ移動する。

### 10.2 node_detected

node_detectedは既存Nodeを更新しない。Eventのevent_idから新しいNode IDをMaterializerが作成する。

- topic、idea、option、concern、open_item、actionはstatus activeで作成する
- decisionは常にstatus candidateで作成する
- actionは明示的な実行意図がある場合だけ作成する
- actionのdescriptionはlabelから初期化し、action.statusはopenとする
- actionのnode_detected Payloadはaction.ownerとaction.due_dateを必ず明示する。Transcript Evidenceに明示された値だけを設定し、明示されない場合はnullとする
- Analyzerが設定したowner / due_dateの非null値は、Event Envelopeのsource_evidence_idsで根拠Evidenceを追跡できなければならない
- speaker、発言者の役割、会議慣行、相対表現からOwner / Due Dateを推測しない
- Analyzerが既存NodeのIDを推測して上書きすることはできない
- 同じTopicへ戻る場合はnode_detectedではなくtopic_focus_changedを使う

### 10.3 relation_detected

relation_detectedは、既存のsource_node_idとtarget_node_idを参照する。Relation TypeはEvent SchemaのEnumで制限し、自由文字列を許可しない。

対象Nodeが存在しない、別Sessionに属する、または許可されない組合せである場合、MaterializerはEventをInvalid Referenceとして拒否する。意味的に同一のEdgeが既に存在する場合は、HistoryとしてEventを保持するが、Graphには重複Edgeを作らない。

#### Provider-facing same-output references

Analyzer Output v2では、Canonical Node IDをLLMに生成させない。既存Nodeは
`existing_node_id`、同じProvider Output内で新しく作るNodeは既存の
`new_node_index`をLocal Referenceとして使う。

`new_node_index`はNode intent配列内の0-based indexであり、Canonical Eventへは漏らさない。Application Adapterは次の2 passで変換する。

1. 全Node intentを検証し、Event IDから決定的な予備Canonical IDを割り当てる
2. Relation / Focus intentの`existing_node_id`または`new_node_index`を解決し、Canonical Eventを生成する

Unknown Local Reference、Unknown Existing Node、Relation Matrix違反はCanonical Event化前に拒否する。Node intent自体が有効でRelationだけが無効な場合は、MVPでは有効なNode Eventを保持し、RelationだけをDiagnostic付きで破棄する。これによりActionが壊れたRelationのために失われない。最終的なEvent Store / Materializerは、生成されたCanonical Eventを通常どおり検証する。

### 10.4 topic_focus_changed

topic_focus_changedは既存Topicへの意味上のFocus遷移を表す。topic_idは既存のtopic Nodeを参照し、Focus Event自体は新しいTopicを作らない。

Prototype 1ではGraphのcurrent_topic.primary_topic_idを更新し、modeをderivedにする。ただし、表示上の切替を安定化するHysteresisやCooldownはMaterializerの責務ではなく、後続のImplementation / Validation Parameterである。

Humanのset_current_topicを適用するとmodeはhuman_correctedになる。Human Override中はnode_detected、relation_detected、confidenceの変化だけではCurrent Topicを変更しない。次に明示的なtopic_focus_changedまたはset_current_topicが適用された時点で、そのFocusを採用し、topic_focus_changedならmodeをderived、set_current_topicならhuman_correctedにする。

Current Topicの対象Nodeがmove_to_parking_lotでparkedになった場合は、Human Override中かどうかに関係なく、current_topic.primary_topic_idをnull、modeをderived、confidenceをnullにする。Parking Eventはcurrent_topic.source_event_idsへ記録する。restore_from_parking_lotはNodeをactiveへ戻すだけで、Current Topicを自動復帰させない。復帰には新しいset_current_topicまたは明示的なtopic_focus_changedが必要である。

confidenceはtopic_focus_changedだけに任意で持たせる。これは解析候補の補助情報であり、Decisionの自動ConfirmやNodeの自動Mergeには使わない。

## 11. Human Correction Event Catalog

Human CorrectionはGraphを直接変更せず、必ずEvent StreamへAppendする。

| Event Type | 対象 | 前提 | Graphへの効果 |
| --- | --- | --- | --- |
| confirm_decision | decision Node | statusがcandidate | 同じNodeをconfirmedへ遷移 |
| revoke_decision | decision Node | statusがconfirmed | 同じNodeをrevokedへ遷移 |
| resolve_open_item | open_item Node | statusがactive | 同じNodeをresolvedへ遷移 |
| reopen_open_item | open_item Node | statusがresolved | 同じNodeをactiveへ戻す |
| rename_node | 任意のNode | 対象が存在し未Archive | labelを更新 |
| archive_node | 任意のNode | 対象が存在 | statusをarchivedへ変更 |
| merge_nodes | 同一Sessionの2 Node | sourceとtargetが異なる | sourceをarchivedにし、関係をtargetへ寄せる |
| move_to_parking_lot | 任意のNode | 対象が存在 | statusをparkedへ変更 |
| restore_from_parking_lot | parked Node | statusがparked | statusをactiveへ戻す |
| update_action | action Node | 対象がaction | description、owner、due_date、statusを明示部分だけ更新 |
| set_current_topic | topic Node | 対象がtopic | current_topicをhuman_correctedへ変更 |
| correct_relation | semantic Relation | old/new Relationの片方以上、Human revision一致 | 線の削除・追加・向き先または型の変更を1 Eventで適用 |
| undo_last_correction | 直前Correction | 対象が最新の可逆Human Correction | 逆操作を新しいEventとして適用 |

### 11.0 Correctable Working Graph — provisional candidate

`correct_relation` は現在の作業仮説を会議中に訂正するHuman-origin Eventである。`old_relation` / `new_relation` はそれぞれ nullable な source/target/type の組で、片方だけなら削除・追加、両方なら原子的な付け替えを表す。対象は `discussion_provenance`、`supports`、`opposes` に限定する。Eventには発話による訂正ならそのEvidence IDを保持し、当初のAnalyzer Eventも残す。Decision確認、Open Item解決、Action/Owner/Dueには一切作用しない。訂正時点のEvidence sequence watermark以前の古いEvidenceだけから同じ線を再提案しても拒否し、その後の新しいEvidenceなら再提案可能にする。曖昧な発話からは対象IDを推測せず、Graphを変えない。`undo_last_correction` の現行対象はrenameのみであり、Relationの差し戻しは新しい `correct_relation` Eventで表す。この機能はローカル候補で、発話訂正の実運用精度は未承認である。

### 11.1 Decision Correction

edit_decisionという独立EventはPrototype 1では作らない。Decisionの表示名修正はrename_node、Decisionの状態変更はconfirm_decisionまたはrevoke_decisionで表現する。

Analyzer Eventがdecisionをconfirmedとして発行することはできない。confirm_decisionはactorがhumanで、expected_revisionが現在のGraph Revisionと一致する場合だけ適用する。

### 11.2 Open Item Correction

`resolve_open_item` と `reopen_open_item` は、Decisionと同じく
`expected_revision`を要求するHuman Eventである。

- ResolveのPayloadは`open_item_node_id`と`expected_status: active`
- ReopenのPayloadは`open_item_node_id`と`expected_status: resolved`
- 対象がopen_itemでない、または期待Statusと現在Statusが一致しない場合は拒否
- Analyzer Eventからの直接Resolved遷移は許可しない
- Projectionはresolved Open Itemを通常のVisible Card Budgetから外し、History / Detailでは追跡可能にする

### 11.3 Undo

undo_last_correctionはSchemaに含めるが、Prototype 1の最初のFixtureで必須とするのは最新Human Correction 1件のInverse Eventまでとする。

- 過去Eventを削除・書き換えない
- Analyzer Eventを任意にUndoしない
- Undo対象が最新の可逆Correctionでなければ拒否する
- 逆操作の詳細は対象Eventの種別ごとにMaterializerで固定する

Undo UXの見た目、複数段Undo、Correction以外の巻き戻しはPrototype 1のSchema範囲外である。

## 12. System Session Lifecycle Events

SessionライフサイクルもEvent Streamへ記録する。

| Event Type | 前の状態 | 次の状態 | Payload |
| --- | --- | --- | --- |
| session_created | なし | created | title、goal |
| session_started | created | active | なし |
| session_finalizing | active | finalizing | last_evidence_sequence |
| session_ended | finalizing | ended | drain_status、final_graph_revision、pending_analysis |

Prototype 1のFixed Transcriptでは一連のEventをFixtureへ含める。Live AudioのDrain実装はしないが、End Session後に最後のEvidenceとAnalysisを取りこぼさない境界を表すContractとして保持する。

session_ended.payload.final_graph_revisionは、そのsession_ended Eventを適用した直後のGraph Revisionと一致する必要がある。したがって、Event sequenceが連続しGraph Revisionも1イベントごとに増える場合、通常はsession_ended Eventのsequenceと同じ値になる。

session_endedのdrain_statusがpartialまたはfailedの場合、SessionはendedになってもMinutes生成側は未完了情報を明示し、完全な会議結果として扱わない。これはGraphを推測で補完するための状態ではない。

## 13. Decision Lifecycle

DecisionはNode Typeであり、candidate、confirmed、revokedは同じNodeの意味上のStatusである。archivedは削除代替のVisibility Stateであり、DecisionのLifecycle上の遷移ではない。

~~~text
node_detected(decision)
        ↓
candidate
        ↓ human confirm_decision
confirmed
        ↓ human revoke_decision
revoked
~~~

ルール:

1. Analyzerはdecision Nodeをcandidateとしてのみ作成できる。
2. CandidateからConfirmedへの遷移はHuman Eventだけが行う。
3. Confirm EventはNode IDとexpected_status=candidateを持つ。
4. Revoke EventはNode IDとexpected_status=confirmedを持つ。
5. Revoke後に自動でcandidateやopen_itemへ戻さない。
6. 再び議論する場合は、新しいCandidate Nodeまたは別のHuman Correctionを作る。
7. Minutesはconfirmedだけを正式Decisionとして出力し、candidateはPending Confirmation、revokedは通常のDecisionから除外する。

「それでいきましょう」という発言は、Prototype 1では自動Confirmの根拠にしない。発言をEvidenceとして残し、明示的なHuman CommandでConfirmする。発話によるConfirm検出は別のValidation対象である。

## 14. Action Lifecycle

Prototype 1では、ActionについてDecisionと同じConfirm Workflowを導入しない。C案を採用する。

1. 明示的な実行意図が解析された時点でaction Nodeを作る。
2. Analyzerのnode_detected Payloadには、action.ownerとaction.due_dateを必ず含める。Transcript Evidenceに明示された値だけを設定し、明示されない場合はnullにする。
3. AnalyzerがOwner / Dueを非nullで設定する場合、Event Envelopeのsource_evidence_idsにその値を裏付けるEvidenceを含める。Materializerは値を推測・補完しない。
4. owner、due_date、statusはHumanのupdate_actionで後から設定、修正、解除できる。Human更新はAnalyzerのEvidence由来値を上書きできるが、操作Eventを履歴に残す。
5. 実行意図が曖昧な「検討する」などはactionにせず、必要ならopen_itemとして記録する。

このSchemaにはcandidate_actionというNode Statusを設けない。Actionの存在自体が曖昧な場合に、曖昧なActionを正式記録してしまうことを避けるためである。Minutes上で確認が必要なActionを表示する場合は、Evidence不足を別のValidation結果として扱い、DecisionのようなConfirmed Stateを新設しない。

Actionのstatusは、open、completed、cancelledのいずれかである。これはAction Nodeの共通statusとは別の作業進行状態であり、Graph上のNode statusはPrototypeではactiveまたはarchivedを基本とする。

## 15. Current Topic and Discussion Flow

### 15.1 Current Topic

責務を次のように分ける。

| 責務 | Owner | Canonical情報 |
| --- | --- | --- |
| Topicの意味上の遷移候補 | Discussion Analyzer | topic_focus_changed Event |
| Current TopicのStateへの反映 | Graph Materializer | graph.current_topic |
| 強調、切替の安定化、Animation | UX Layer | GraphのProjection |
| Human Override | Human Command | set_current_topic Event |

GraphはPrototype 1ではPrimary Topicだけを保持する。secondary_topic_idsやActive Topic Setは追加しない。複数Topicを同時に扱う必要は、Event Streamには遷移として残すが、表示モデルの拡張課題とする。

set_current_topicを適用した場合、current_topic.modeはhuman_correctedになる。Human Override中はNode追加、Relation追加、Confidence変化だけではCurrent Topicを変更しない。次の明示的topic_focus_changedまたはset_current_topicでProjectionを更新する。対象Nodeがparkedになった場合はprimary_topic_idをnullにしてOverrideを解除し、restore_from_parking_lotでは自動復帰しない。

### 15.2 Recent Flow

Recent FlowはCanonical Graphに保存しない。

- Event Streamのtopic_focus_changedとset_current_topicが履歴のSource
- UIはそのEvent Streamから直近N件をProjectionする
- N、時間幅、重複除去、表示LabelはUXのValidation Parameter
- Minutesは全遷移を列挙せず、Topic単位のSummaryに必要な重要な戻りだけを文章化する
- Drift Awarenessは、未解決Nodeが残ることとCurrent Topicが別Topicであることから導出する

同じFlowをGraph、Event Stream、Recent Flowの3箇所へ独立保存しない。

## 16. Edge and Relation Rules

Edge TypeはSchema Enumで制限する。Prototype 1での方向規則は次のとおりとする。

| Relation | 推奨Source | 推奨Target |
| --- | --- | --- |
| contains | topic | idea、option、concern、open_item、decision、action |
| has_option | topic | option |
| supports | idea、option | idea、option、decision |
| opposes | idea、option、concern | idea、option、decision |
| related_to | 任意の非Archive Node | 任意の非Archive Node |

Materializerは少なくとも次を検証する。

- source_node_idとtarget_node_idが同一でない
- 両Nodeが同一Sessionに属する
- EventのRelation TypeがSchema Enumにある
- sourceとtargetが存在する
- semantic key type + source + targetの重複Edgeを作らない

Edge IDはNodeと同様にMaterializerがDeterministicに作る。推奨表現は次のとおりである。

~~~text
edge:<session_id>:<relation_type>:<source_node_id>:<target_node_id>
~~~

depends_on、results_inは将来のRelation拡張としてDeferredする。

## 17. Merge, Archive, and Parking Lot Semantics

### 17.1 Merge

Prototype 1では自動Mergeを行わない。Humanのmerge_nodesをCanonical Mergeとする。

推奨はB + Cの組合せである。

- source Nodeは物理削除せずarchivedにする
- target NodeをCanonical Nodeとして残す
- source NodeのEvidenceとEvent履歴は保持する
- sourceに接続したEdgeは、重複を除きtargetへ再接続する
- source IDを過去Eventから参照できる状態にする
- MapとMinutesのCurrent Projectionではsourceを通常表示しない

同一SessionでないNode、同一Node同士、または既にArchiveされたsourceをMergeするEventは拒否する。Mergeの再接続でRelationの意味が失われる場合は、Eventを適用せずHumanに再選択を求める。

### 17.2 Archive / Delete

archive_nodeは物理DeleteではなくTombstoneである。Node、Evidence、Creation Event、Correction Eventを削除しない。

Archived NodeはCurrent Mapと通常Minutesから除外するが、ReplayとEvidence Viewでは参照できる。削除操作後のGraph Revisionも通常のEventと同様に増加する。

### 17.3 Parking Lot

move_to_parking_lotは対象Nodeのstatusをparkedへ変更する。Node Type、ID、Evidence、Edgesは維持する。

対象NodeがCurrent Topicの場合、同じEventの適用でcurrent_topic.primary_topic_idをnullにし、Human Overrideも解除する。これはTopicが未解決かどうかとは別の、現在Focusを安全に解除するProjection規則である。

restore_from_parking_lotはparkedからactiveへ戻すだけで、Current Topicを自動復帰させない。Decision Nodeにはこの操作を適用せず、DecisionのLifecycleをParking Lot状態で上書きしない。Parking Lotの表示はstatus parkedのNode集合から導出する。

## 18. Evidence Link, Actor, and Confidence

### 18.1 Evidence

Event Envelopeのsource_evidence_idsがEventとTranscript EvidenceのPrimary Linkである。

| Event | Evidence要件 |
| --- | --- |
| Analyzer Event | 1件以上。存在するEvidenceへ参照解決できること |
| Human Correction | 0件可。操作の根拠はHuman Command自体 |
| System Lifecycle Event | 0件可 |

Materializerは、EventのEvidence IDが同一SessionのEvidenceに存在することを検証する。Nodeのevidence_idsは、そのNodeを作成・更新したEventのsource_evidence_idsから導出・更新する。Nodeのsource_event_idsは、そのNodeに影響したEvent IDの履歴である。

### 18.2 Actor

Prototype 1ではactorを次の3値に固定する。

- analyzer: Discussion Analysisが生成した観測・候補
- human: Human CorrectionまたはHuman Command
- system: Session LifecycleなどのシステムEvent

具体的なUser ID、Speaker ID、権限モデルは持たない。

### 18.3 Confidence

汎用confidence Fieldは追加しない。topic_focus_changedのconfidenceだけを任意で許可し、0.0以上1.0以下とする。

confidenceは表示や検証の補助であり、次の自動分岐には使わない。

- DecisionのConfirm
- Node Merge
- Node Archive
- Evidenceの削除

## 19. Event Examples

以下はEvent Schemaに適合する最小例である。日時は説明用であり、Event Orderingはsequenceだけで決まる。

### 19.1 Topic Detection

~~~json
{
  "event_id": "evt-003",
  "session_id": "s-001",
  "sequence": 3,
  "event_type": "node_detected",
  "occurred_at": "2026-09-19T10:00:03Z",
  "actor": "analyzer",
  "source_evidence_ids": ["evd-001"],
  "payload": {
    "node_type": "topic",
    "label": "MVPはDiscussion Mapを中心にしたい"
  }
}
~~~

Materializerはevent_id evt-003から、例えばnode:s-001:evt-003を作る。AnalyzerはこのIDをPayloadへ含めない。

### 19.2 Decision Candidate

~~~json
{
  "event_id": "evt-005",
  "session_id": "s-001",
  "sequence": 5,
  "event_type": "node_detected",
  "occurred_at": "2026-09-19T10:00:05Z",
  "actor": "analyzer",
  "source_evidence_ids": ["evd-003"],
  "payload": {
    "node_type": "decision",
    "label": "スマホはMVPでは外す"
  }
}
~~~

作成されるNodeのstatusはcandidateで固定される。

### 19.3 Decision Confirm

~~~json
{
  "event_id": "evt-009",
  "session_id": "s-001",
  "sequence": 9,
  "event_type": "confirm_decision",
  "occurred_at": "2026-09-19T10:01:09Z",
  "actor": "human",
  "source_evidence_ids": [],
  "expected_revision": 8,
  "payload": {
    "decision_node_id": "node:s-001:evt-005",
    "expected_status": "candidate"
  }
}
~~~

「それでいきましょう」という発言があっても、Prototype 1では明示Confirm Commandを発行してからConfirmedにする。

### 19.4 Topic Return

~~~json
{
  "event_id": "evt-008",
  "session_id": "s-001",
  "sequence": 8,
  "event_type": "topic_focus_changed",
  "occurred_at": "2026-09-19T10:01:08Z",
  "actor": "analyzer",
  "source_evidence_ids": ["evd-004"],
  "payload": {
    "topic_id": "node:s-001:evt-003",
    "previous_topic_id": "node:s-001:evt-006",
    "confidence": 0.91
  }
}
~~~

### 19.5 Human Rename

~~~json
{
  "event_id": "corr-rename-001",
  "session_id": "s-001",
  "sequence": 10,
  "event_type": "rename_node",
  "occurred_at": "2026-09-19T10:01:10Z",
  "actor": "human",
  "source_evidence_ids": [],
  "expected_revision": 9,
  "payload": {
    "node_id": "node:s-001:evt-003",
    "label": "MVPの中心価値: Discussion Map"
  }
}
~~~

### 19.6 Node Merge

~~~json
{
  "event_id": "corr-merge-001",
  "session_id": "s-001",
  "sequence": 11,
  "event_type": "merge_nodes",
  "occurred_at": "2026-09-19T10:01:11Z",
  "actor": "human",
  "source_evidence_ids": [],
  "expected_revision": 10,
  "payload": {
    "source_node_id": "node:s-001:evt-006",
    "target_node_id": "node:s-001:evt-003"
  }
}
~~~

source Nodeはarchivedとして残り、target NodeがCurrent GraphのCanonical Nodeになる。

### 19.7 Parking Lot

~~~json
{
  "event_id": "corr-park-001",
  "session_id": "s-001",
  "sequence": 12,
  "event_type": "move_to_parking_lot",
  "occurred_at": "2026-09-19T10:01:12Z",
  "actor": "human",
  "source_evidence_ids": [],
  "expected_revision": 11,
  "payload": {
    "node_id": "node:s-001:evt-006"
  }
}
~~~

### 19.8 Action

~~~json
{
  "event_id": "evt-action-001",
  "session_id": "s-001",
  "sequence": 13,
  "event_type": "node_detected",
  "occurred_at": "2026-09-19T10:01:13Z",
  "actor": "analyzer",
  "source_evidence_ids": ["evd-005"],
  "payload": {
    "node_type": "action",
    "label": "次回までにVisual Prototypeを作成する",
    "action": {
      "owner": null,
      "due_date": null
    }
  }
}
~~~

Materializerはaction.descriptionをlabelから初期化し、action Payloadのownerとdue_dateを保持する。nullはTranscript Evidenceに明示されていないことを意味し、MaterializerやMinutes Generatorは推測で補完しない。Humanのupdate_actionでは後から設定・修正・解除できる。

## 20. Full Replay Example

### 20.1 Transcript Evidence

~~~json
[
  {
    "id": "evd-001",
    "session_id": "s-001",
    "sequence": 1,
    "timestamp": "2026-09-19T10:00:01Z",
    "speaker": "A",
    "text": "MVPはDiscussion Mapを中心にしたい"
  },
  {
    "id": "evd-002",
    "session_id": "s-001",
    "sequence": 2,
    "timestamp": "2026-09-19T10:00:02Z",
    "speaker": "B",
    "text": "スマホも必要ですか？"
  },
  {
    "id": "evd-003",
    "session_id": "s-001",
    "sequence": 3,
    "timestamp": "2026-09-19T10:00:03Z",
    "speaker": "A",
    "text": "今回は外しましょう"
  },
  {
    "id": "evd-004",
    "session_id": "s-001",
    "sequence": 4,
    "timestamp": "2026-09-19T10:00:04Z",
    "speaker": "B",
    "text": "それでいきましょう"
  },
  {
    "id": "evd-005",
    "session_id": "s-001",
    "sequence": 5,
    "timestamp": "2026-09-19T10:00:05Z",
    "speaker": "A",
    "text": "次回までにVisualのPrototypeを作ります"
  }
]
~~~

### 20.2 Ordered Events and Revisions

| Seq | Event | Graph effect | Revision after apply |
| ---: | --- | --- | ---: |
| 1 | session_created | Sessionをcreatedで作成 | 1 |
| 2 | session_started | Sessionをactiveへ | 2 |
| 3 | node_detected(topic) | MVP Discussion Map Topicを作成 | 3 |
| 4 | topic_focus_changed | Primary Topicを設定 | 4 |
| 5 | node_detected(decision) | Smartphone除外Decisionをcandidateで作成 | 5 |
| 6 | node_detected(topic) | Smartphone UI Topicを作成 | 6 |
| 7 | topic_focus_changed | Smartphone UIへ移動 | 7 |
| 8 | topic_focus_changed | MVP Topicへ戻る | 8 |
| 9 | confirm_decision | 同じDecisionをconfirmedへ | 9 |
| 10 | node_detected(action) | Visual Prototype Actionを作成 | 10 |
| 11 | relation_detected(contains) | MVP TopicからDecisionへEdgeを作成 | 11 |
| 12 | relation_detected(contains) | MVP TopicからActionへEdgeを作成 | 12 |
| 13 | session_finalizing | Sessionをfinalizingへ | 13 |
| 14 | session_ended | Sessionをendedへ、Drain完了 | 14 |

Event sequence 1から14を同じ順序で適用すると、Initial Graph Revision 0からFinal Graph Revision 14になる。Human Confirmはsequence 9かつexpected_revision 8であるため、Candidate以外の状態を誤ってConfirmしない。

### 20.3 Final Graph Excerpt

~~~json
{
  "session": {
    "id": "s-001",
    "title": "MVP Discussion",
    "goal": "MVPの中心価値を決める",
    "status": "ended",
    "created_at": "2026-09-19T10:00:00Z",
    "started_at": "2026-09-19T10:00:00Z",
    "ended_at": "2026-09-19T10:01:14Z",
    "graph_revision": 14
  },
  "graph": {
    "session_id": "s-001",
    "revision": 14,
    "last_event_sequence": 14,
    "nodes": [
      {
        "id": "node:s-001:evt-003",
        "session_id": "s-001",
        "type": "topic",
        "label": "MVPはDiscussion Mapを中心にしたい",
        "status": "active",
        "created_at": "2026-09-19T10:00:03Z",
        "updated_at": "2026-09-19T10:00:03Z",
        "source_event_ids": ["evt-003"],
        "evidence_ids": ["evd-001"]
      },
      {
        "id": "node:s-001:evt-005",
        "session_id": "s-001",
        "type": "decision",
        "label": "スマホはMVPでは外す",
        "status": "confirmed",
        "created_at": "2026-09-19T10:00:05Z",
        "updated_at": "2026-09-19T10:00:09Z",
        "source_event_ids": ["evt-005", "evt-009"],
        "evidence_ids": ["evd-003"]
      },
      {
        "id": "node:s-001:evt-006",
        "session_id": "s-001",
        "type": "topic",
        "label": "スマートフォンUI",
        "status": "active",
        "created_at": "2026-09-19T10:00:06Z",
        "updated_at": "2026-09-19T10:00:06Z",
        "source_event_ids": ["evt-006"],
        "evidence_ids": ["evd-002"]
      },
      {
        "id": "node:s-001:evt-010",
        "session_id": "s-001",
        "type": "action",
        "label": "次回までにVisualのPrototypeを作ります",
        "status": "active",
        "created_at": "2026-09-19T10:01:10Z",
        "updated_at": "2026-09-19T10:01:10Z",
        "source_event_ids": ["evt-010"],
        "evidence_ids": ["evd-005"],
        "action": {
          "description": "次回までにVisualのPrototypeを作ります",
          "owner": null,
          "due_date": null,
          "status": "open"
        }
      }
    ],
    "edges": [
      {
        "id": "edge:s-001:contains:node:s-001:evt-003:node:s-001:evt-005",
        "source_node_id": "node:s-001:evt-003",
        "target_node_id": "node:s-001:evt-005",
        "type": "contains",
        "source_event_ids": ["evt-011"]
      },
      {
        "id": "edge:s-001:contains:node:s-001:evt-003:node:s-001:evt-010",
        "source_node_id": "node:s-001:evt-003",
        "target_node_id": "node:s-001:evt-010",
        "type": "contains",
        "source_event_ids": ["evt-012"]
      }
    ],
    "current_topic": {
      "primary_topic_id": "node:s-001:evt-003",
      "mode": "derived",
      "confidence": 0.91,
      "source_event_ids": ["evt-008"]
    }
  }
}
~~~

上記のFinal Graphは、同じInitial StateとEvent sequenceを別Replayで適用しても同じNode ID、Status、Edge、Current Topic、Revisionになる。実装時は、時刻の再計算、LLM再呼び出し、Node IDの再生成を行わない。

## 21. Schema Validation and Materializer Validation

JSON Schemaは、構造上の契約を定義する。Prototype 1では次を採用する。

- SchemaはJSON Schema Draft 2020-12を使用する
- 未定義Fieldは原則禁止するため、定義済みの各Domain ObjectとEvent PayloadにadditionalProperties: falseを設定する
- Timestampはdate-time、Due Dateはdateで統一する
- Nullable Fieldはtypeにnullを明示する
- IDは空でない文字列とし、ProviderやUUID形式に過剰依存しない
- RequiredはReplayに必要な最小項目に限定する

JSON Schemaだけでは、次のSession横断・履歴依存制約を表せない。これらはMaterializer ContractとしてDeterministicに検証する。

1. Event.session_idとEvidence、Node、GraphのSessionが一致すること
2. Event.sequenceが1から連続し、Event IDが重複しないこと
3. Human Eventのexpected_revisionがCurrent Graph Revisionと一致すること
4. source_evidence_idsが既存Evidenceへ解決できること
5. Relation、Focus、Correctionの対象Nodeが存在すること
6. DecisionのCandidate / Confirmed / Revoked遷移が許可されていること
7. Graph RevisionがEvent適用後のsequenceと一致すること

Event Catalog内のJSON例は、Event Schemaの構造要件を満たす形で記載している。実装着手前には、これらの例をFixtureとして機械検証し、さらにMaterializerの状態遷移検証を別途行う。

## 22. Prototype 1 Resolution Status

### M6 Fake Analyzer sequencing boundary

M6のFake Analyzerは、Global Event sequenceを管理しないCandidate Event Intentを返す。CandidateにはDeterministicなproducer `event_id`、Event Type、occurred_at、source_evidence_ids、Payloadを含めるが、Session全体の`sequence`は含めない。Transcript Replay / Event Store境界が次のsequenceを割り当て、Canonical Event Schemaを検証してからEvent StreamへAppendする。

この実装上の段階化はCanonical Event Schemaを変更しない。Materializerが受け取るEventは常に`sequence`を持つ完全なCanonical Eventであり、AnalyzerはGraph、Event Store、Human Eventを直接変更しない。

### Recorded Real Analyzer Spike boundary

Recorded Real AnalyzerもM6のCandidate境界を共有する。ProviderへはCanonical Event Envelope全体を渡さず、Node / Relation / Topic FocusのIntentだけをStructured Outputとして要求する。ApplicationがProvider出力を`CandidateEvent`へ変換し、`discussion-event.schema.json`で検証した後、Transcript Replay / Event Store境界でCanonical `sequence`を付与する。

- Providerが生成してよいのはAnalyzer相当の`node_detected`、`relation_detected`、`topic_focus_changed`だけである
- `event_id`、`session_id`、`sequence`、`occurred_at`のCanonical化はApplicationが担当する
- 新規Nodeへの参照は同一Response内の`new_node_index`に限定し、Canonical Node IDはApplicationが決定する
- `existing_node_id`はContextに提示された既存Nodeだけを参照できる
- Decisionはcandidate Nodeまでで、Human Eventは生成しない
- Owner / Dueの非null値は現在Utteranceに明示され、source Evidenceで追跡できる場合だけ許可する
- UI Presentation StateはContextに含めない

Provider未設定、Provider出力のSchema違反、Unsafe Action / RelationはAnalyzer Run Recordへ記録し、そのUtteranceの候補をGraphへ適用しない。Transcript Evidenceと既存Event Streamは保持され、Replayは次のUtteranceへ継続できる。このSpikeはCanonical Schema、Materializer、Human CorrectionのContractを変更しない。

今回のSchema、Event Catalog、Evaluation FixtureでPrototype 1の最小契約は固定した。Prototype 1開始前に残るMust Resolveはない。

| ID | Must Resolve | 推奨方針 | 未確定理由 |
| --- | --- | --- | --- |
| M-001 | ~~Actionの曖昧な発言をactionとして出す条件~~ | 明示的実行意図のみaction。Owner / DueはEvidence明示値またはnull | Canonical化済み |
| M-002 | ~~Current TopicのHuman Override後にAnalyzer Focusを再開する条件~~ | 次の明示的topic_focus_changedまたはset_current_topicで更新。parked時は解除 | Canonical化済み |
| M-003 | session_finalizingからendedへ進むDrain判定 | Prototype 1ではDeferred。Liveでは未処理Evidence / AnalysisのDrainを待つ | Realtime実測が未確定 |
| M-004 | ~~Prototype 1でUndoを必須とするCorrection種別~~ | 最新Human rename correction 1件のInverse Event | Fixture 009で固定済み |
| M-005 | ~~Relation Typeごとの厳密なNode Type制約~~ | supportsはidea / option → idea / option / decision | Relation FixtureとSchemaコメントで固定済み |

M-001、M-002、M-004、M-005はResolvedであり、M-003だけはLive STT / Analysis依存のためPrototype 1後へDeferredする。別のMUST_RESOLVE.mdは追加しない。

## 23. Deferred Event and Domain Extensions

次の事項はPrototype 1のCanonical Schemaへ含めない。

- Partial Transcript、STT correction、再解析を表すEvent
- Visual Artifactの生成・Version・Adoption Event
- Minutes Draft、Review、Export Event
- speaker identity、権限、複数User
- secondary topic、Active Topic Set、複数Primary Topic
- depends_on、results_in等の追加Relation
- 自動Merge、自動Decision Confirm、自律的Parking Lot移動
- 任意段数のUndo、任意の過去時点へのUser-facing Replay
- Candidate Action / Confirmed Actionの独立Lifecycle

これらは、それぞれRealtime Pipeline、UX、Visual Artifact、Minutes、またはMVP後の拡張で再評価する。

## 24. Status

Status: Proposed

本Catalogと2つのJSON Schemaは、Prototype 1のDomain / Event Contract案である。ここで定義したEvent Streamを入力に、LLMを呼ばないDeterministic MaterializerがDiscussion Graphを再現することを、次のEvaluation Fixtureで検証する。
