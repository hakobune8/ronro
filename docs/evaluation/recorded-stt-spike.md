# Recorded STT Spike

Status: Completed — Recorded STT is not yet ready for the Live Audio gate.

このSpikeでは、同じ30分相当のDiscussionについて、Clean Transcriptを入力したBaselineと、実際に録音音声をSTTへ通したExperimentを比較した。Partial TranscriptはCanonical Graphへ適用していない。STT結果はFinal SegmentだけをUtteranceへ変換し、既存のAnalyzer / Event Store / Materializer / Presentation Projectionをそのまま通している。

今回の録音は、既存のRealistic Synthetic TranscriptからmacOS音声で生成したSynthetic Recorded Audioである。人間の会議録音ではないため、話者間の重なり・実環境ノイズ・マイク品質の評価は未実施である。一方、`Audio -> STT -> Final Segment -> Utterance -> Analyzer -> Graph -> Map` の実処理は行っている。

## 1. Frozen Baseline

| Item | Value |
| --- | --- |
| Analyzer model | `gpt-5.6-luna` |
| Analyzer reasoning | `medium` |
| Analyzer prompt | `analyzer-prompt-v4` |
| Analyzer context | `v1` |
| Golden | `golden-v2`（30分Workload固有の参照には既存 `recorded-30min-golden-v1` を使用） |
| Evaluation | `analyzer-eval-v2` + Recorded STT evaluation v1 |
| Type D | OFF |
| Open Item Lifecycle | enabled（本RunではResolve操作を追加していない） |
| Presentation Compaction | enabled |
| Stable Discussion Map | enabled |
| Canonical Contract | unchanged |

Analyzer Prompt、Model、Context、Materializer、Map UIはこのSpikeのために変更していない。

## 2. Provider / Model selection

選択したProvider / ModelはOpenAIの `gpt-4o-transcribe-diarize` である。日本語の録音を処理でき、Final Segment、開始・終了時刻、Speaker Labelを返すため、今回の目的であるEvidence TraceabilityとUtterance Boundaryの検証に適している。Speaker Attributionの品質自体はPrimary Metricにしていない。

比較候補として `gpt-4o-transcribe` と `whisper-1` も確認したが、今回はモデル比較を行わず、1 Provider / 1 Modelに固定した。APIのresponse format、利用可能な形式、timestamp / diarizationの仕様は[OpenAI Audio Transcriptions API documentation](https://developers.openai.com/api/reference/resources/audio/subresources/transcriptions/methods/create)を参照した。

Runtime Configurationは環境変数からのみ読み込み、API Key / Authorization HeaderはRepository、Log、Artifactへ保存していない。

## 3. Audio dataset and preflight

### Dataset

- Audio: `evaluation/stt/source/recorded-30min-synthetic-v1.m4a`
- Clean reference: `evaluation/stt/source/clean-reference-transcript.json`
- Duration: 1,800秒（30分）
- Reference Transcript: 120 Utterances
- Speaker: Synthetic A/B

### Preflight

先に4分相当AudioでEnd-to-Endを実行した。

| Metric | Preflight |
| --- | ---: |
| Audio duration | 240秒 |
| Raw STT segments | 17 |
| Normalized utterances | 16 |
| STT processing time | 54.686秒 |
| RTF | 0.228 |
| Analyzer validation failures | 0 |
| Analyzer provider failures | 0 |
| Accepted nodes | 13 |
| Replay / Map | succeeded |

Preflightは成功したため、30分Runへ進めた。

### Long audio upload constraint

1,800秒を単一Requestで送ったところ、ProviderのModel最大音声長制限により拒否された。このFailureでGraphは変更されていない。600秒単位の3 Chunkへ分割し、各SegmentへChunk Offsetを戻してから統合することで同一録音のRunを完走した。

これはApplicationのCanonical Contractではなく、Recorded STT AdapterのUpload制約として記録する。将来の実装でも、長時間音声のChunking / RetryはSTT層の責務とする。

## 4. STT result and normalization

| Metric | Value |
| --- | ---: |
| Audio duration | 1,800.000秒 |
| Raw final segments | 129 |
| Normalized utterances | 121 |
| Speaker labels | A: 64 / B: 65 segments |
| Normalization diagnostics | 0 |
| Canonical Events | 195 total（System 2 + Analyzer 193） |
| Final Graph revision | 195 |

Normalization Policyは次のとおりである。

- 同一Speakerの連続Segmentを結合。
- Silence gap 0.8秒以下を結合候補とする。
- 終端句読点、Speaker Change、最大20秒をBoundaryとして扱う。
- 同一 timestamp / text の重複Segmentは除去し、Diagnosticを残す。
- Raw Segmentを捨てず、Normalized UtteranceからRaw Segment IDへ戻れるようにした。

Provider SegmentをそのままAnalyzer Utteranceにしなかったことで、129 Segmentを121 Utteranceへ縮約できた。一方、Cleanの120 Utteranceとは一致しないため、STT BoundaryはSemantic Boundaryの代理であり、Canonical Orderingの代替ではない。

## 5. Evidence traceability

既存のDomain Schemaに`audio_start` / `audio_end`を追加していない。Canonical `Transcript Evidence`は既存形を維持し、以下をSidecarへ保持した。

- Raw Segment ID
- Raw Segment Text
- Normalized Text
- Audio Start / End
- Speaker
- Evidence ID / Utterance ID

主なArtifactは次のとおり。

- [Raw STT result](../../evaluation/stt/full-run-v1/raw/stt-result.json)
- [Normalized Utterances](../../evaluation/stt/full-run-v1/normalized-utterances.json)
- [Evidence audio trace](../../evaluation/stt/full-run-v1/evidence-audio-trace.json)
- [Canonical input](../../evaluation/stt/full-run-v1/canonical-input.json)

したがって、Map NodeからEvidenceを辿り、将来的に音声の該当時刻へ戻れる。Canonical Contract変更は不要だった。

## 6. Lexical and semantic STT quality

### Lexical

| Metric | Value |
| --- | ---: |
| CER | 0.2834 |
| WER | N/A |
| Whitespace WER diagnostic | 2.7941 |

日本語ReferenceはWhitespace Tokenizationを持たないため、WERは正式値として報告しない。CERをPrimary Lexical Metricとした。Whitespace診断値は単語評価ではなく、Tokenizerなしで比較した参考値である。

### Semantic STT errors

| Category | Count | Observation |
| --- | ---: | --- |
| Topic Keyword Error | 10 | `Map` / `Visual` / `MVP` 等の表記揺れ・音写が中心 |
| Negation Error | 0 | 否定反転は観測されなかった |
| Decision Phrase Error | 1 | Commitment phraseと別発話のBoundaryがずれたケース |
| Action Phrase Error | 2 | Action phraseと別発話のBoundaryがずれたケース |
| Reference Error | 1 | 「それ」等の参照範囲がSegment統合でずれたケース |

Critical STT Errorは次のとおり。

| Critical Error | Count |
| --- | ---: |
| Negation inversion | 0 |
| Decision meaning reversal | 0 |
| Action meaning reversal | 0 |
| Owner misrecognition | 0 |
| Due Date misrecognition | 0 |

主な品質劣化は、意味を逆転するものではなく、固有語・略語の認識とSegment / Utterance Boundaryのずれだった。ただし、意味反転が0件だったことはSynthetic Audio 1件での結果であり、実環境への一般化はしない。

詳細は [STT error analysis](../../evaluation/stt/full-run-v1/stt-error-analysis.json) に保存した。

## 7. Clean vs STT Analyzer metrics

Clean側は同じ120 Utteranceの保存済みAnalyzer Recordingを再利用し、STT側は121 Normalized UtteranceをReal Analyzerへ送った。追加のClean API Runは行っていない。

| Metric | Clean Transcript | STT Transcript | Comment |
| --- | ---: | ---: | --- |
| Topic Precision | 1.0000 | 1.0000 | 6 lane axesのsemantic match |
| Topic Recall | 1.0000 | 1.0000 | 6 lane axesのsemantic match |
| Strong Decision Precision | 0.3333 | 0.4000 | Strong reference 2件。STT側は非Strong候補も3件 |
| Strong Decision Recall | 1.0000 | 1.0000 | 2 / 2 |
| Action Precision | 1.0000 | 1.0000 | Golden action vocabulary内で評価 |
| Action Recall | 0.6250 | 0.8750 | Clean 5 / 8、STT 7 / 8 |
| Topic Return Accuracy | 1.0000 | 1.0000 | 指定Returnで既存laneを再利用 |
| Focus event recall vs Clean | 1.0000 | 0.9000 | Clean 10、STT 9 focus events |
| Accepted nodes / Utterance | 0.7500 | 0.7769 | STT +3.6% |
| Max nodes / Utterance | 2 | 2 | Regressionなし |
| 3+ node utterance rate | 0.0000 | 0.0000 | Regressionなし |
| Analyzer-reported no-op rate | 25.0% | 23.1% | Clean 30 / 120、STT 28 / 121 |
| Strict workload no-op accuracy | 0.6000 | 0.5000 | `recorded-30min-golden-v1`の20件を厳密評価した診断値 |
| Accepted duplicate Topic | 0 | 0 | 6 semantic axes、重複Laneなし |

Topic Precision / Recallは、30分Annotationのalias / child axisをそのままNode数の分母にせず、Product Map上の6つの主要Laneをsemantic keyへ正規化して評価した。これにより、`Discussion Map` と `ディスカッションマップ` の表記差をFalse Failureにしていない。

No-opについては、`analyzer-eval-v2`の5 Scenarioで使う0.90系の指標と、30分Workloadの厳密な20件リストを混同しない。30分ではSTT側で相槌・分割発話の一部がNode化され、No-opに関するAnalyzer Robustness課題が残った。

## 8. Graph comparison

### Final Graph summary

| Metric | Clean | STT |
| --- | ---: | ---: |
| Topic count | 6 | 6 |
| Final node count | 90 | 94 |
| Nodes / Topic | 15.0000 | 15.6667 |
| Relation count | 85 | 90 |
| Decision nodes | 6 candidate | 5 candidate |
| Action nodes | 5 | 7 |
| Open Items | 13 | 16 |
| Current Topic | semantic match | semantic match |
| Parking | 0 | 0 |

### Difference classification

- Missing Topic: 0 major lane axis
- Extra Topic: 0 major lane axis
- Missing Strong Decision: 0 / 2
- Extra non-Strong Decision: 3
- Missing Action relative to Clean: 0 of Clean's five accepted action categories
- Additional Action relative to Clean: 3 categories（Event Catalog、比較表、Privacy草案）。このうちAction Golden上は有効なものを含む。
- Missing Important Open Item: 1 category-level miss in the conservative 10-item set
- Extra Open Item relative to Clean: 3
- Relation count delta: +5。Schema-invalid Relationではなく、STT側で増えたNodeとHierarchyの差分。
- Wrong Current Topic: 0（IDはSessionごとに異なるためsemantic topic keyで比較）

STT GraphはClean Graphと同じ6 Laneを形成し、Topic Returnで重複Topicを作らなかった。一方、文字認識の影響でラベルの信頼性が落ち、非Strong Decision CandidateとOpen Itemが増えた。

## 9. Critical Information Recall and Map quality

Projection自体は、STT Graphに生成されたCandidate Decision、Action、Open Item、Current TopicをすべてRailまたはCurrent Detailへ残した。

- Projection generated critical state recall: **1.0000**
- Strong Decisions: 2 / 2 = 1.0000
- Important Actions: 7 / 8 = 0.8750
- Important Open Items: 9 / 10 = 0.9000
- Current Topic: 1 / 1 = 1.0000
- Category-level cross-run Critical Information Recall: **19 / 21 = 0.9048**

この0.9048は、STTが作った全Nodeを隠さなかったという意味ではなく、Clean / Workload Reference上の重要な意味情報がSTT Mapへ残ったかをカテゴリ単位で評価した値である。Projection上のRecall 1.0と区別する。

### Map Quality rubric

以下は参加者調査ではなく、同じ6項目Rubricによる静的Content Reviewである。

| Dimension | Clean | STT | Observation |
| --- | ---: | ---: | --- |
| Clarity | 5 | 3 | STT側は略語・固有語の音写でLabelが読みづらい |
| Density | 5 | 4 | Card数は同じだがOpen / Decisionが増えた |
| Decision Safety | 5 | 4 | 自動Confirm・否定反転はないが非Strong候補が増えた |
| Topic Coherence | 5 | 3 | Laneは一致、子Node Labelに誤認識が残る |
| Stability | 5 | 5 | Map Projectionと既存位置は維持 |
| Usefulness | 4.8 | 3.8 | Content noiseを含む共有画面評価 |
| Map Quality Delta | — | **-1.0** | STT 3.8 - Clean 4.8 |

M5.1のCompaction自体は機能している。両方とも最終Canvasは16 Visible Cards、STT側のCompression Ratioは`16 / 94 = 0.1702`である。ただし、Compactionは誤認識されたLabelを修正しないため、STTのMap Quality Deltaは目安`-0.5`を下回った。

Artifacts:

- [Clean / STT comparison](../../evaluation/stt/full-run-v1/comparison.json)
- [STT Presentation Projection](../../evaluation/stt/full-run-v1/projection.json)
- [Projection replay snapshots](../../evaluation/stt/full-run-v1/comparison.json) の `snapshots`

Parkingについては、このAnalyzer-only比較でHuman Parking Eventを注入していないため、両Branchとも0である。Parking / RestoreのCanonical処理と既存M4 Testsは維持されており、次回は同一Human Command Planを両Branchへ適用して評価する。

## 10. Latency, token, and cost

### STT

| Metric | Value |
| --- | ---: |
| Audio duration | 1,800秒 |
| STT processing time | 390.471秒 |
| RTF | 0.2169 |
| STT token usage | Provider responseで取得不可 |
| STT cost | Runtimeで取得不可 |

RTFは`processing_time / audio_duration`であり、Recorded Batchの値である。Realtime性能を意味しない。

### Analyzer after STT

| Metric | Value |
| --- | ---: |
| p50 | 3.240秒 |
| p95 | 6.237秒 |
| max | 7.876秒 |
| Input / prompt tokens | 563,956 |
| Output / completion tokens | 33,905 |
| Reasoning tokens | 14,477 |
| Total tokens | 597,861 |
| Estimated Analyzer cost | ~$0.153477 |

Final Utteranceが確定した後のMap更新は、今回のAnalyzer測定だけならp50約3.24秒、p95約6.24秒である。Normalization / Projectionはこの測定値に対して支配的ではない。STT Batch処理390秒を加えた値はRealtime latencyではなく、Recorded Batch所要時間である。

## 11. Failure behavior and reprocessability

次のFailureケースを実装・テスト・Artifact化した。

| Failure | Behavior |
| --- | --- |
| STT request failure | Evidence / Graphを変更せず、Chunk retry可能 |
| Empty transcript | `empty_transcript` Diagnostic、Canonical Utteranceなし |
| Very short segment | Final Evidenceとして保持、AnalyzerはNo-op可 |
| Repeated segment | `duplicate_segment` Diagnostic、正規化時に重複除去 |
| Malformed timestamp | `malformed_timestamp` Diagnostic、Graphへ投入しない |
| Missing speaker | `speaker: null`を許容し、Audio traceは保持 |
| Analyzer failure after STT | Accepted Eventを保持し、失敗Diagnosticを記録してReplay可能 |

今回のFull RunではAnalyzer側に以下の3 Diagnosticがあった。

- `invalid_topic_focus_rejected`
- `inferred_action_metadata_rejected`
- `relation_reference_unresolved`

いずれもGraphを壊さず、最終Domain StateとAccepted EventsはSchema Validationを通過した。特に最後の2つは、STTで発話のBoundary / Labelが変わった際のAnalyzer / Adapter耐性として、次のIterationで再評価する。

[Failure case artifact](../../evaluation/stt/failure-cases.json) に、Provider長時間Upload Failureを含む全ケースを保存した。保存済みSTT結果から再Analyzerでき、Canonical Event Streamを破壊的に書き換える処理はない。

## 12. Determinism and tests

- Final Domain State: Schema valid
- 195 Events: Event Schema valid
- Fixed STT Event Streamを2回Replay: 同一Canonical State
- Revision: 195 / 195
- Node / Edge IDs: 同一
- Current Topic: 同一
- Presentation Projection: Canonical GraphをMutationしない
- Existing M1〜M5 + STT tests: **85 tests, all green**

追加した主なコード / Test:

- `prototype/stt.py`: Provider adapter、Response parse、Normalization、Traceability、CER
- `prototype/recorded_stt.py`: Recorded STT E2E runner
- `prototype/recorded_stt_compare.py`: Clean / STT offline comparison and snapshots
- `tests/test_stt.py`: STT parsing / normalization / failure tests
- `tests/test_recorded_stt.py`: Raw trace、Projection non-mutation、Replay determinism

## 13. Conclusion and next gate

| Gate | Result |
| --- | --- |
| STT pipeline成立 | Pass |
| Final Transcript only | Pass |
| Raw Evidence / Audio timestamp trace | Pass |
| Analyzer pipeline成立 | Pass |
| Decision Safety | Pass for observed critical errors |
| Action Safety | Owner / Due inference 0。Action completenessは要改善 |
| Critical Information Recall >= 0.90 | Pass: 0.9048（category-level） |
| Map Quality Delta >= -0.5 | **Fail: -1.0** |
| Replay Determinism | Pass |
| Ready for Live Audio | **No** |

### Next Decision

**A. STT / Segmentation Iteration（primary） + B. Analyzer Robustness Iteration（secondary）** を推奨する。

理由は、PipelineとCanonical境界は成立し、否定反転・Decision意味反転・Action意味反転・Owner / Due誤認も観測されなかった一方、CER 0.2834、Topic Keyword Error 10件、Boundary由来のReference / Decision / Action Error、Map Quality Delta -1.0が残ったためである。次に変更すべき対象は、まず固有語・略語のSTT / Utterance Normalizationと、STT由来の発話境界に対するAnalyzer / Action Relation Referenceの耐性である。

- Prompt v5: 今回は作成しない。
- Live Microphone / Live Audio Streaming: 開始しない。
- Partial Transcript Graph Update: 開始しない。
- Visual Generation / Minutes: 開始しない。
- Architecture Revision: 現時点では不要。Canonical Event / Materializer / Evidence境界は維持できている。

