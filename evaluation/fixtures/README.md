# Prototype 1 Evaluation Fixtures

Prototype 1の期待挙動を固定するGolden Fixture集である。

## Fixture contract

各Fixtureは、次の3ファイルを基本とする。

- evidence.json: Transcript Evidenceの配列
- events.json: Event Schemaに対して各要素を検証するOrdered Event Stream
- expected-final-graph.json: Domain Schemaに適合するFinal Domain State。Golden比較対象は内部のgraph

expected-final-graph.jsonは、GraphだけでなくSession、Evidence、Utteranceも含む。これにより既存のdiscussion-domain.schema.jsonでFixture全体を検証できる。

expected-revisions/以下のSnapshotは、GraphのMaterialized Viewだけを記録する。各Snapshotはrevision、last_event_sequence、nodes、edges、current_topicを持つ。

## AnalyzerとMaterializerの分離

Analyzer評価は、evidenceからExpected Candidate Eventsが生成されるかを評価する。LLMを含む実装では、将来的に次の評価方式を使い分ける。

- Exact: Event Type、Node Type、Label、Evidence Linkまで一致
- Semantic: Labelの意味とEvidenceの対応を比較
- Required Event Presence: 必須のCandidate Eventが存在することを確認

Materializer評価は、固定されたevents.jsonからexpected-final-graph.jsonのgraphを完全一致または意味的一致で比較する。MaterializerはLLM、Clock、Randomnessに依存してはならない。

## Fixture一覧

| ID | Fixture | 主な検証 |
| --- | --- | --- |
| 001 | Basic Discussion | Topic、Idea、Current Topic、Relation |
| 002 | Topic Return | Stable Node ID、Topic再訪、Flowの導出 |
| 003 | Decision Confirm | CandidateからHuman Confirmedへの遷移 |
| 004 | Decision Revoke | ConfirmedからRevokedへの遷移と履歴保持 |
| 005 | Action Item | Action境界、Owner / Dueの非推測 |
| 006 | Human Correction | Rename、Archive、Merge |
| 007 | Parking Lot | ParkedとRestore、Node ID維持 |
| 008 | Current Topic Override | Human OverrideのDeterministic Policy |
| 009 | Undo | Renameに対する最新CorrectionのInverse |
| 010 | Invalid Events | Materializer拒否条件 |
| 011 | Replay Determinism | 同一Event StreamのReplay一致 |
| 012 | Relation Constraints | Relation TypeとNode Typeの最小Matrix |
| 013 | Open Item Lifecycle | Open ItemのResolve / Reopen / Replay / Projection |

## Prototype前に固定したPolicy

### Action boundary

- 明示的な実行意図がある発言はaction Nodeにする
- 「作った方がいいかもしれない」のような提案・可能性はopen_itemまたはideaにする
- OwnerとDue Dateは推測しない
- Analyzerのaction node_detectedはowner / due_dateを必ず持ち、Evidenceに明示された値だけを設定する。明示されない場合はnullにする
- Analyzer由来の非null値はEvent Envelopeのsource_evidence_idsで追跡する
- Humanのupdate_actionは、後からOwner / Dueを設定・修正・解除でき、最終StateではAnalyzer値に優先する

### Open Item Lifecycle

- `open_item`の`status=active`をOpen、`status=resolved`を解決済みとして扱う
- `resolve_open_item` / `reopen_open_item`はHuman Commandからのみ生成する
- Resolved ItemはCanonical Graph、Evidence、Event Streamから削除しない
- Presentation ProjectionではResolved Itemを通常のVisible Card Budgetから外す
- Duplicate / Similar、Superseded、ParkingはLifecycleの状態へ追加せず、Merge / Presentation / Parkingで別に扱う

### Same-output Action relation references

Analyzer Output v2の`new_node_index`をProvider-facing Local Referenceとして使用する。ApplicationがNode intentを先にCanonical IDへ割り当て、後段の`contains` Relationを解決する。Valid Action NodeとInvalid Relationが同じOutputにある場合、Action Nodeは保持し、RelationだけをDiagnostic付きでRejectする。

### Current Topic Human Override

Fixture 008では、Policy Aを採用する。

Humanのset_current_topicは、次に明示的なtopic_focus_changedまたはset_current_topicが適用されるまで優先する。Confidenceの大小やEvent数では自動解除しない。単にPricingに関するIdeaが検出されただけではCurrent Topicを変更しない。Override対象がparkedになった場合はprimary_topic_idをnullにしてOverrideを解除し、restoreだけでは復帰しない。

### Undo

Prototype 1のFixtureではrename_nodeだけをUndo対象とする。Undoは過去Eventを削除せず、最新Human CorrectionのInverse EventをAppendする。

Merge、Parking Lot、Decision ConfirmのUndoは、逆操作の意味とUI検証が未確定のためDeferredする。

### Relation Matrix

Fixture 012で使用する最小Matrixは次のとおりである。

| Relation | Allowed source | Allowed target |
| --- | --- | --- |
| contains | topic | idea、option、concern、open_item、decision、action |
| has_option | topic | option |
| supports | idea、option | idea、option、decision |
| opposes | idea、option、concern | idea、option、decision |
| related_to | 任意の非Archived Node | 任意の非Archived Node |

Self relation、Missing Node、Matrix外の組合せはMaterializerが拒否する。

## Canonicalization後のDeferred事項

- Session FinalizationのDrain条件はLive STT / Analysis依存のためPrototype 1後へDeferredする。Prototype 1のCanonical Contractに残るMust Resolveはない

Action Owner / Due、supports Relation Matrix、ParkingされたCurrent Topicの解除規則は、Schema、Event Catalog、Architecture Summary、FixturesでCanonical化済みである。

## Golden Fixture Policy

expected-final-graph.jsonはGolden Outputである。実装結果に合わせてFixtureを変更してはならない。変更が必要な場合は、先にRD / RFCの仕様変更として理由と影響を記録し、その変更後にGoldenを更新する。

Session FinalizationのDrain条件はLive STT / Analysisに依存するため、Prototype 1ではDeferredとする。固定TranscriptのFixtureはactive SessionのGraph Materializationを検証する。
