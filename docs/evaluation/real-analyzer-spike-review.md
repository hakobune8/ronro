# Recorded Real Analyzer Spike Review

Status: **A — Ready for Recorded Real Analyzer Iteration**

このSpikeでは、M6のFake AnalyzerをReal LLMへ差し替える境界を実装した。実際のProvider品質を測るにはAPI認証情報とモデル設定が必要だが、このRepository環境にはLLM SDK、API Key、Model設定が存在しなかった。そのため、構造検証・失敗処理・評価Harnessは実行し、Real ModelのSemantic Scoreは未取得として扱う。

## Provider / Model

- Adapter: `OpenAICompatibleProvider`
- 接続方式: Python標準ライブラリによるJSON-only HTTP Adapter
- 設定: `REAL_ANALYZER_ENDPOINT` / `REAL_ANALYZER_API_KEY` / `REAL_ANALYZER_MODEL`。OpenAI互換の既定環境変数も利用可能
- Model: 未設定
- 実Provider呼び出し: 未実行（環境に認証情報・モデル設定なし）
- Provider未設定時は`provider_not_configured`をRun Recordへ記録し、Graphを変更せずReplayを継続する

特定Provider SDKや大規模Adapter層は追加していない。将来Providerを変更しても、`Provider.complete_json()`と`RealAnalyzer.analyze()`の境界を維持する。

## Prompt / Context Strategy

- Prompt Version: `analyzer-prompt-v1`
- LLM出力: `node`、`relation`、`topic_focus` IntentのJSONのみ
- Application所有: `event_id`、`session_id`、`sequence`、`occurred_at`、Canonical Event化、Schema Validation
- Context: Current Utterance、Meeting Goal、Current Topic、Active Topic一覧、Current Topic周辺のNode、直近8 Event
- Context計測: serialized character countと4文字/token近似値をRun Recordへ保存
- 除外: Transcript全文、Lane expanded、Zoom、Selected Node、Scroll Position
- Existing Topic Return: Contextに提示した既存Topicの`id/type/label/status`を`existing_node_id`で参照

## Dataset

`evaluation/real-analyzer/`に5 Scenario、合計38 Utteranceを追加した。

| Scenario | 内容 | 主な評価 |
| --- | --- | --- |
| A | MVP企画会議 | Candidate Decision、Action、No-op |
| B | 技術Architecture議論 | Event境界、Concern、Option、遅延懸念 |
| C | Brainstorming | Idea / Optionの粒度、発散、Action False Positive |
| D | 意見対立 | Supports / Opposes、Candidate Decision、合意表現 |
| E | 脱線 → 元Topicへ復帰 | Existing Topic Reference、Topic Return、重複防止 |

各ScenarioにHuman Golden Annotationを付け、完全文字列一致ではなくSemantic / Required Event Presenceで評価する。

## Evaluation Metrics

`prototype/real_evaluation.py`で以下を記録する。

- Topic Precision / Recall
- Important Node Recall
- Duplicate Node Rate
- Candidate Decision Precision
- Action Precision
- Topic Return Accuracy
- No-op Accuracy
- Node Explosion Rate
- Label Quality
- Validation Failure、Critical Error、Latency、Token Usage

重大エラーは、False Decision、False Action、Owner / Due捏造、既存Topicの重複、Human Event生成、Evidence外参照として別集計する。

## Results

### Contract / Regression

- 既存M1〜M6の38テスト: Green
- Real Analyzer追加テスト: 11テスト、Green
- 合計: **49 tests、Green**
- Real Analyzer Structured Output Schema検証: Green
- Canonical Event Schema変換: Green
- Provider Failure / Invalid Output / No-op / Decision Safety / Action Safety: Green
- Existing Materializer経路を使ったRecorded Replay: Green

### Real Model

実Providerが未設定のため、Real ModelのSemantic結果は未取得である。評価HarnessをProvider未設定状態で実行した場合、38 Utteranceすべてで`provider_not_configured`が記録され、Candidate EventはGraphへ適用されない。この値はAnalyzer品質のScoreとして扱わない。

### Fake Baseline

同じDatasetをM6 Fake Analyzerで実行した構造的なBaselineは以下である。これは限定Ruleの挙動確認であり、Real Modelとの品質比較値ではない。

| Metric | Fake baseline |
| --- | ---: |
| Topic Precision | 0.9333 |
| Topic Recall | 0.7000 |
| Important Node Recall | 0.1333 |
| Duplicate Node Rate | 0.2000 |
| Candidate Decision Precision | 1.0000 |
| Action Precision | 0.8000 |
| Topic Return Accuracy | 1.0000 |
| No-op Accuracy | 0.4000 |
| Node Explosion Rate | 0.1607 |
| Label Quality heuristic | 0.5833 |

Fake baselineには、Datasetの表現揺れを十分に扱えないことによる未検出が含まれる。実LLMを同じHarnessで測定するまで、改善・劣化の判断材料にはしない。

## Critical Errors

- Real Model由来のCritical Analyzer Error: **未測定**（Provider未実行）
- Provider Configuration Failure: 38件（Operational Failure。Analyzer Semantic Errorとは別集計）
- 構造テストでは、Human Confirmation生成、False Action、Owner / Due推測、無効Relation、Evidence外参照をGraphへ適用しないことを確認した

## Fake vs Real Comparison

最終Graphの実測比較はProvider設定後に実行する。比較対象は同一ScenarioについてのFinal Graph、Topic構造、Decision、Action、Open Item、Topic Return、Node数である。

現時点で確認できるのは、Fake / Realが以下の同じPipelineを共有することだけである。

`Transcript → Analyzer → CandidateEvent → Schema Validation → Event Store → Graph Materializer → Map`

Real Analyzer専用のGraph生成経路やUI分岐は存在しない。

## Example Good / Failure Cases

### Contract-level good cases

- `events: []`をNo-opとして受理し、Mapを変更しない
- Decision Intentはcandidate Nodeへ変換するが、`confirm_decision`を生成しない
- 明示された「山田さん、2026-09-25までに…」だけOwner / Dueを設定する
- Contextにある既存Topicを`existing_node_id`で参照し、重複Topicを抑止する
- Human Topic Override中はAnalyzer FocusをGraphへ発行しない

### Failure cases

- Provider未設定: `provider_not_configured`を記録し、Evidenceを保持して継続
- Structured Output違反: Candidateを全件破棄し、Validation ErrorとRaw Outputを保持
- SuggestionをActionとして返した場合: `false_action_rejected`
- EvidenceにないOwner / Dueを返した場合: `inferred_action_metadata_rejected`
- Human Event形式を返した場合: Schema変換前に拒否

## Latency / Cost / Token Usage

OpenAI-compatible AdapterはProvider応答のLatencyと`usage.prompt_tokens` / `completion_tokens` / `total_tokens`をRun Recordへ保存する。`cost_usd`はProvider価格表に依存するため自動推定せず、現時点はnullである。

実Provider未実行のため、Real Latency / Token Usage / Costは未測定。Static ProviderのテストLatencyは0ms相当であり、性能値として扱わない。

## Product Impact

今回の実装で、Real LLMがCanonical Graphを直接生成しない境界、Candidate Decisionの安全境界、Evidence Traceability、失敗時のGraph保全、Fake / Real共通Replay、定量評価の器は成立した。

一方、Real LLMによって「会話を理解し、Mapが自然に育つ」こと、False Decision / False ActionがMVP許容範囲に収まること、Latencyが会議中に耐えることはまだ証明されていない。

## Recommended Improvements

1. ProviderとModelを設定し、5 Scenarioを同じPrompt Versionで実行する。
2. Raw Output、Context Snapshot、Validation ErrorをRun単位で保存し、ScenarioごとにCritical Errorをレビューする。
3. Topic Return、No-op、Action境界、Candidate Decisionを優先してPrompt / Contextを反復する。
4. Real Modelの出力が安定した後に、Provider Retry / Timeout / Reprocessの実測を追加する。
5. Real品質がMVP検証に十分か確認するまではSTT / Live Audioへ進めない。

## Decision

判定は **A. Ready for Recorded Real Analyzer Iteration** とする。

Canonical Model / Event Boundaryの根本問題は見つかっていない。しかし、Provider未設定のためB（Ready for STT Integration）には進めない。次はProvider設定後のRecorded Real Analyzer Iterationであり、Real ModelのFalse Decision / False Action / Topic Return / No-op / Latencyを測定する。
