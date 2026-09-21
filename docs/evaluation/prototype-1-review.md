# Prototype 1 Completion Review

## Review status

- Review date: 2026-09-19
- Prototype: Discussion Map AI Facilitator MVP — Prototype 1
- Scope: M1〜M6（Fixed Transcript、Fake Analyzer、Canonical Event、Graph、Stable Map、Human Command）
- Real LLM / STT / Live Audio: 未着手
- Canonical Contract: 変更なし

## What Works

- Fixed Transcript EvidenceをFinal Utterance単位で順番にReplayできる。
- 既知Fixtureでは、Transcript Evidenceに紐付いたFake Analyzer Event TemplateからCandidate Eventを生成できる。
- 新しいCandidate EventはEvent Schemaを検証してからEvent Store / Replay / Materializerへ渡される。
- Graph MaterializerはM1〜M5と同じ純粋なEvent適用経路を使い、Analyzerから直接Graphを変更しない。
- Topic、Idea、Open Item、Candidate Decision、ActionをTranscriptから段階的にMapへ追加できる。
- 既存TopicへのFocus復帰で重複Topicを作らない。
- Candidate DecisionはTranscript上の同意表現だけではConfirmedにならず、Human CommandでのみConfirmedになる。
- Human Confirm、Parking、Current Topic OverrideをTranscript Replay途中に挿入し、その後のReplayを継続できる。
- Actionは明示的な実行意図だけを抽出し、Owner / Due DateはEvidenceに明示された値だけを設定する。
- 同じTranscript、同じGraph Context、同じHuman Event列をReplayすると同じGraph Revision、Node ID、Edge、Current Topicを再現できる。
- M5 Stable Discussion MapはTranscript ReplayでもPrimary Viewとして維持され、Final Utteranceは補助Stripに表示される。

## What Does Not Yet Work

- Fake Analyzerは自然言語理解ではなく、Fixture Exact Mappingと限定的なRule-based fallbackである。表現揺れ、複雑な文脈、複数Topicの並行議論は十分に扱わない。
- Analyzer処理はHTTPリクエスト内で同期的に実行される。実LLMの遅延、Retry、再解析、Out-of-order処理は未実装である。
- Transcript ReplayはFinal Utteranceのみを扱い、Partial Transcript、Audio、STT、Session Finalization Drainは対象外である。
- Fake Analyzerが出すTopic Focusは限定ルールであり、Current Topicの頻繁な切替に対するHysteresis / Cooldownは未検証である。
- Transcript起点のE2EはDeveloper Prototypeであり、会議参加者による実Discussionの改善を直接測定したものではない。

## Product Hypothesis Status

仮説「話しているだけでDiscussion Mapが育ち、参加者が現在の議論を理解しやすくなる」のうち、TranscriptからMapへ変換される体験の骨格は成立した。

M5のFixed Event Replayでは事前に作られたEventを表示していたが、M6ではFinal UtteranceをStep / Playすると、Fake AnalyzerがCandidate Eventを生成し、Topic・Idea・Decision・Actionが順にMapへ現れる。この差によって、「入力された会話を解析結果としてMapへ変換する」という因果関係をPrototype上で確認できる。

ただし、以下はまだ未検証である。

- 実際の会議中に参加者がMapを見続けるか
- Analyzerの誤りがあってもDiscussionが前進するか
- Live latencyが許容範囲か
- 実LLMのTopic Identity / Decision境界が安定するか

したがって、Product Hypothesisは **Transcript起点の技術的な成立を確認、会議体験としては未検証** と評価する。

## Architecture Validation

Baselineの責務分離は維持できた。

```text
Fixed Transcript Evidence
        ↓
Final Utterance Replay
        ↓
Fake Analyzer（Candidate Eventのみ）
        ↓
Canonical sequence付与 + Schema Validation
        ↓
Event Stream
        ↓
Graph Materializer
        ↓
Discussion Graph
        ↓
Stable Discussion Map
```

- Transcript = Evidence: 既存Domain Stateに保持。
- Event Stream = History: Analyzer EventとHuman Eventを同じ順序付き列に追加。
- Discussion Graph = Current State: Materializerのみが更新。
- Human Correction: M4と同じCommand → Event → Materializer経路。
- Presentation State: LaneのCompact / Expanded等はGraphへ保存しない。
- Decision Lifecycle: AnalyzerはCandidateまで、Confirmed / RevokedはHuman Eventのみ。

Analyzer候補のsequenceはFake Analyzerが管理せず、Replay SessionがEvent Store境界で付与する。Event Schemaの`sequence`必須契約を変更せず、Global Ordering責務もAnalyzerへ移していない。

## UX Validation

ブラウザで以下を確認した。

- `Transcript + Fake Analyzer`モードへの切替。
- Basic DiscussionのFinal Utterance表示と、Step後のTopic / Idea追加。
- Candidate DecisionがCompact SummaryからLane Expandで確認できること。
- ReplayをPauseしてHuman Confirmし、Confirmed表示へ更新されること。
- Confirm後に次のAgreement UtteranceをReplayしてもDecisionが二重生成・自動Confirmされないこと。
- M5.1のCurrent Topic Expanded / Non-current Compact / Stable PositionがTranscript起点でも維持されること。

Transcript表示はMap下部の補助領域に留め、MapをPrimary Viewとした。Processing IndicatorはReady / Updated / Completeを表示する。Prototypeでは同期処理のためAnalyzing状態は短時間の状態表現に限定される。

## Analyzer Boundary Validation

採用方式はHybridである。

1. **Exact Mapping**: 001、002、003、005、008の既存Analyzer EventをEvidenceのsource_evidence_idsでUtteranceへ紐付ける。
2. **Rule-based fallback**: M6専用Scenarioの限定的な日本語パターンからTopic、Idea、Open Item、Decision、Actionを生成する。
3. **Canonicalization**: Candidateのproducer event_idはDeterministicにし、Global sequenceはReplay側で付与する。

Fake Analyzerは次のHuman Eventを生成しない。

- confirm_decision
- revoke_decision
- rename_node
- merge_nodes
- update_action
- move_to_parking_lot

これによりAnalyzer BoundaryとHuman Command Boundaryを分離できた。

## Test Results

Python `unittest discover -v`で、既存M1〜M5 29件とM6追加9件の計38件がGreenになった。

M6追加テストは次を含む。

- Fake AnalyzerのDeterministic出力とEvent Schema適合
- Basic Transcript → Events → Golden Graph
- Topic ReturnとNode重複防止
- Candidate DecisionとHuman Confirm
- Action境界、Owner / Due非推測
- Human Current Topic Overrideの維持
- Transcript Replay API / Reset
- M6専用E2E Scenario、Human Command混在Replay、最終Replay一致

## Technical Debt

- Fake AnalyzerのExact TemplateとRuleは評価用であり、Analyzer品質の代表値ではない。
- Analyzer Candidateの失敗記録はSnapshot内に保持するが、永続Error StoreやRetry UIはない。
- Fake Delay、非同期Queue、Retry / Reprocess、Out-of-order Eventの運用実装はない。
- HTTP RuntimeはIn-memoryで、複数Session、再起動後の復元、認証、Concurrencyを扱わない。
- M6専用ScenarioはGolden Fixture Loaderとは分離しているため、Scenario専用の詳細Schemaはまだない。
- Action Owner / Due抽出のRuleは限定的で、現実の言い回しを網羅しない。
- UIのTranscriptモードは既存Fixtureを選択するDeveloper Prototypeであり、Scenario編集や分析結果の比較画面はない。

## Risks Before Real LLM

- LLMが同一Topicを別Labelで再生成するIdentity / Mergeリスク。
- 「賛成」「了解」等をDecision Confirmと誤認するリスク。
- Action、Owner、Dueの推測混入。
- Human Override中のFocus Event、Parking済みTopicの再浮上。
- Candidate Eventが多すぎる場合のMap密度とCurrent Topicの揺れ。
- Provider遅延・失敗時のEvidenceとEventの対応、再解析範囲。

Real LLMへ進む前に、これらを固定入力のAnalyzer Evaluation FixtureとRequired Event Presence評価で測れるようにする必要がある。

## Recommended Next Phase

次段階は、いきなりLive Audioへ進まず、Fake Analyzerと同じCandidate Event Interfaceを使う **Recorded Real Analyzer Spike** を推奨する。

1. M6のAnalyzer Fixtureを拡張し、表現揺れ・曖昧な同意・Owner / Due欠落・Topic Returnを追加する。
2. Provider非依存のReal Analyzer Adapterを実験用に追加する。Canonical Graph / Event Storeへ直接接続しない。
3. Analyzer出力をCandidate Eventとして記録し、Exact / Semantic / Required Event Presenceを分離評価する。
4. Latency、Retry、Reprocess、Context Windowを固定Transcriptで測定する。
5. その後にLive STT / Audioとの接続可否を判断する。

Visual ArtifactとMeeting Minutesは、Discussion MapのTranscript / Analyzer評価が成立した後に、既存RFC-0004 / 0005の境界で進める。

## Prototype 1 Definition of Done

- Fixed Transcript Replay: 達成
- Fake Analyzer Candidate Event生成: 達成
- Event Schema Validation: 達成
- Graph自動更新とStable Map: 達成
- Topic Return / Decision Candidate / Action境界: 達成
- Human Confirm / Current Topic Override / Parking: 達成
- Replay Determinism: 達成
- Real LLM / STT / Live Audio: Prototype 1の対象外として未着手

Prototype 1は、固定入力によるEnd-to-End Architecture Boundaryの検証を完了した。実会議のProduct ValidationとReal Analyzerの品質検証は次フェーズで行う。
