# STT Error Attribution + Utterance Normalization v2 Spike

Status: Completed — STT API / Analyzer APIは再実行していない。`analyzer-prompt-v4`、Canonical Schema、Materializer、Presentation Compactionは変更していない。

このSpikeでは、Recorded STT v1の保存済みRaw Segmentと、同じRunのAnalyzer / Graph Artifactを使って、Map QualityがClean `4.8` からSTT `3.8`へ下がった原因を切り分けた。Raw STT Evidenceとv1 Normalized Utteranceは変更せず、v2は別のDerived Artifactとして生成した。

## 1. Frozen Baseline

| Item | Value |
| --- | --- |
| STT | `gpt-4o-transcribe-diarize` |
| Analyzer | `gpt-5.6-luna`, reasoning `medium` |
| Prompt / Context | `analyzer-prompt-v4` / `v1` |
| Golden / Evaluation | `golden-v2` / `analyzer-eval-v2` |
| Type D | OFF |
| Audio | 1,800秒、Raw Segment 129件 |
| STT API calls | 0 |
| Analyzer API calls | 0 |
| Canonical mutation | なし |

主なArtifact:

- [Normalization v2 artifacts](../../evaluation/stt/normalization-v2/)
- [Raw STT result](../../evaluation/stt/full-run-v1/raw/stt-result.json)
- [v1 normalized utterances](../../evaluation/stt/full-run-v1/normalized-utterances.json)
- [v1 STT comparison](../../evaluation/stt/full-run-v1/comparison.json)

## 2. Executive Summary

Map Qualityの低下は、単一のBoundary Bugではない。

1. **Primary: lexical error** — `Discussion Map`、`MVP`、`Visual Artifact`、`Current Topic`などの固有語・技術語が音声認識で崩れ、Labelと一部のNode分類・Relation選択へ波及した。
2. **Primary: Analyzer robustness** — STTで意味が崩れた発言から、CleanにはないOpen Item / non-Strong Decision / Actionを拾った。STT GraphはCleanよりOpen Item `+3`、Action `+2`、non-Strong Decision `+3`の差分になった。
3. **Secondary: segmentation / normalization** — 129 Raw Segmentをv1で121 Utteranceにしており、明らかな短い相槌と後続発言の分離が2箇所あった。v2でこの2箇所を保守的に結合した。
4. **Amplifier: projection sensitivity** — Projection自体はCritical Information Recall `1.0`を維持しているが、余分なOpen Item、弱いDecision、崩れたLabelが同じ共有画面に現れることで、Clarity / Topic Coherenceを下げる。

Normalization v2は安全な前処理として採用候補だが、保存済みイベントを使ったオフラインのNo-event-delta検証ではMap Qualityを`3.8`から回復させなかった。次の改善軸は **STT Terminology / Provider Iteration + Analyzer Noise Robustness** である。

## 3. Clean / STT Graph Difference

| Metric | Clean | STT v1 | STT + Normalization v2* |
| --- | ---: | ---: | ---: |
| Topic | 6 | 6 | 6 |
| Final Nodes | 90 | 94 | 94 |
| Relations | 85 | 90 | 90 |
| Candidate Decisions | 6 | 5 | 5 |
| Confirmed Decisions | 0 | 0 | 0 |
| Actions | 5 | 7 | 7 |
| Open Items | 13 | 16 | 16 |
| Current Topic | semantic match | semantic match | semantic match |
| Nodes / Topic | 15.0 | 15.6667 | 15.6667 |

`*` v2列はAnalyzerを再実行した結果ではない。v2で結合・Skip対象になった入力に対応するv1 Analyzer Outputがすべてno-opだったため、保存済みCanonical Event Streamを再利用した「固定イベント差分なし」のオフライン証明である。v2入力をLLMへ再送した場合の同一性は未測定として残す。

Graph差分のNode Type別内訳は次のとおり。

| Type | STT - Clean |
| --- | ---: |
| topic | 0 |
| idea | +2 |
| option | -3 |
| concern | +1 |
| open_item | +3 |
| decision | -1 |
| action | +2 |

Six Topic Axisはすべて維持され、Topic Returnの指定ケースは `1.0`、Current Topicの意味一致も成立した。一方、Relationは単純な差分が `+5`に見えるだけで、Reference-aligned topologyではSTT側に追加 `44`、Clean側に欠落 `39`があり、Node分類差がRelation構造へ広がっている。

## 4. Map Quality Delta Attribution

厳密な因果分解ではなく、Product Reviewに基づく説明用の概算である。

| Cause | Estimated contribution | Evidence |
| --- | ---: | --- |
| Lexical / Label degradation | -0.35 | `MVP`, `Map`, `Visual`, `Topic`等の表記崩れ。CER `0.2834` |
| Extra Open Items | -0.25 | `13 → 16`。未解決一覧のNoiseが増加 |
| Extra weak / non-Strong Decisions | -0.20 | Cleanにはない候補が3件増加 |
| Topic / Relation coherence | -0.10 | 追加・欠落Relation各44 / 39、Option / Decision分類の差 |
| Projection sensitivity | -0.10 | Critical stateは保持したが、LabelとCard内容の読解コストを増幅 |
| **Total** | **-1.00** | Clean `4.8` → STT `3.8` |

Projectionを原因と断定する証拠はない。Clean / STTともに主要StateのProjection Recallは`1.0`であり、Projectionは根本原因というより、Lexical / Analyzer差分を共有画面上の読みづらさへ増幅する層と判断した。

## 5. Full Error Attribution

全Node差分58件とRelation topology差分83件を、[error-attribution.json](../../evaluation/stt/normalization-v2/error-attribution.json)へ保存した。Node traceには次の全項目を含めている。

`Clean utterance → Raw STT → Normalized utterance → Analyzer raw output → Canonical Events → Graph Node`

Relation traceには、追加・欠落の方向、Relation type、Source / Target Node、Analyzer Output、Canonical Relation Event、Graph結果を含めている。欠落RelationではSTT側のRaw / Analyzer欄は`null`になる。

### Node attribution summary

| Primary classification | Count | Interpretation |
| --- | ---: | --- |
| lexical | 5 | STT固有語・技術語の置換がLabel / 分類差へ直結したもの |
| segmentation | 20 | Reference alignmentまたは複数Segment境界とCleanの対応がずれ、Analyzer結果が別Utteranceに対応したもの |
| analyzer | 33 | STT文字列は一定読めるが、AnalyzerのNode粒度・カテゴリ・内容選択がCleanと異なったもの |

このCountは自動突合によるDiagnostic分類で、Human Goldenの正解ラベルではない。特に `segmentation` には、実際の音声境界だけでなくSTTによる欠落・置換後の単調alignment差も含まれる。したがって、20件すべてをNormalizationだけで直せるとは解釈しない。

### Representative traces

| Ref | Clean | Raw STT / Result | Primary |
| ---: | --- | --- | --- |
| 1 | Discussion Mapを見ながらMVPの形を決める | `ディスカッションマップ` / `M_V_P_` | lexical |
| 14 | Mapの状態を追える | `MATの表材が終われば` | analyzer + lexical |
| 35 | 最初の論点を見つけられるか | `名前と d h i s i o n...` | segmentation / lexical |
| 39 | レイアウト試作を作り位置を確認 | `アニメーションは控えめ` | analyzer / alignment差 |
| 59 | Visual ViewのStatic Mockを作る | `t-r-o-t-o-t-y-p-eで見てみましょう` | analyzer / lexical |
| 102 | Discussion MapにPrivacy表示を追加 | `ふりばしいの表示` | lexical / analyzer |
| 112 | Visual ArtifactのPrototypeを作る | `Visual ARTIFACTSのTROTOYP` | lexical / analyzer |

## 6. Proper Noun Audit

[proper-noun-audit.json](../../evaluation/stt/normalization-v2/proper-noun-audit.json)に全監査項目を保存した。

| Canonical term | Observed STT forms | Impact | Assessment |
| --- | --- | --- | --- |
| Discussion Map | `ディスカッションマップ`, `MAP`, `MAT`, `MFD`, `2 isqsio nmp` | Label / Topic identity | Existing Topic matchingが多くを吸収。Labelは不自然 |
| MVP | `M_V_P_`, `m-v-b`, `m-v-p`, `m v p` | Label / Decision | 否定・Scopeの極性は反転しなかったが、Label品質が低下 |
| Visual Artifact | `Visual ARTAFACT`, `Visual ARTIFACTS`, `藍の画像` | Label / Topic / Action | Visual Laneは維持。Action Labelは崩れた |
| STT / Discussion Analysis | `STT`, `B-I-S-K-U-S-S-I-O-Nアナビシス` | Label / Idea | Critical stateの反転はなし |
| Transcript / Provider | `TRANSRIPT`, `pr ansrit`, `...PRANS...`, `prvid` | Label / Decision / Action | Privacy / Providerの大枠は残った |
| Current Topic / Topic Lane | `カレン`, `TOPIC`, `レイン`, `スパンディット` | Label / Relation | Analyzer ContextによりTopic identityは維持 |
| Luna | 該当なし | なし | Transcript内の語ではないため監査対象なし |

CriticalなSTT Errorは全て0件だった。

- Negation inversion: `0`
- Decision meaning reversal: `0`
- Action meaning reversal: `0`
- Owner misrecognition: `0`
- Due Date misrecognition: `0`

## 7. Utterance Boundary Audit

129 Raw Segmentの隣接関係は、Speaker Change `117/128`、同一Speaker `11/128`だった。同一SpeakerのGap `<=0.8秒`は10件で、Provider Segmentはすでにかなり細かく分割されていた。

### v1 / v2 normalization metrics

| Metric | v1 | v2 |
| --- | ---: | ---: |
| Raw Segment | 129 | 129 |
| Normalized Utterance | 121 | 119 |
| Avg chars / Utterance | 26.4463 | 26.8908 |
| Short Fragment (`<=8`文字) | 11 | 9 |
| Incomplete Fragment | 0 | 0 |
| Filler-only | 12 | 10 |
| Agreement-only | 9 | 7 |
| Analyzer skip candidate | 12 | 10 |
| Multi-intent merge | 0 | 0 |

v1/v2の境界カテゴリは次のとおり。カテゴリは重複し得るDiagnostic項目であり、`good-boundary`はSemantic Goldを意味しない。

| Category | v1 | v2 |
| --- | ---: | ---: |
| Good boundary | 109 (90.1%) | 109 (91.6%) |
| Filler-only | 12 (9.9%) | 10 (8.4%) |
| Too short | 11 (9.1%, overlapping) | 9 (7.6%, overlapping) |
| Incomplete fragment | 0 | 0 |
| Agreement-only | 9 (7.4%) | 7 (5.9%) |
| Split semantic candidates in raw stream | 2 | 2 |
| Merged independent utterances | 0 | 0 |

Raw上のSplit候補は次の2件だった。

1. `そうですね。` + `そこはあとで戻りましょう。`
2. `そうですね。` + `名前と d h i s i o n, ...`

v2では同一Speaker・Gap `<=1.0秒`・後続テキストありのTerminal Fillerだけを後続発言へ結合した。これによりFiller-follow merge `2`、既存の同一Speaker Fragment merge `8`となった。Speaker Changeを跨ぐ結合、長いGapの結合、意味的に独立した発言の結合は行っていない。

`boundary-audit.json`には121/119件の個別分類、Raw Segment ID、Speaker、全文を保存している。

## 8. Normalization v2 Policy

採用したDerived Policyは次のとおり。

- Raw STT Evidenceは不変。
- v1 Normalized Utteranceは不変。
- v2は別ID (`stt-v2-utt-*`)で出力。
- 同一Speakerの短いFragmentは既存v1ルールで結合。
- `そうですね。`のようなTerminal Fillerは、同一Speaker・1.0秒以内・後続テキストありの場合だけ結合。
- Speaker ChangeはHard Boundary。
- 長すぎる発言を意味解析で分割しない。
- `えー`、`あの`、単純な相槌・Agreement-onlyはEvidenceへ残し、Analyzer送信候補から除外できるSidecar Policyを持つ。
- `はい、それで進めましょう`のように内容がある発言はFiller-onlyとは判定しない。

これはTranscriptをLLMで書き直すNormalizationではない。Evidence Traceabilityを優先し、`raw_segment_ids`とAudio timestampをv2にも保持した。

## 9. Analyzer Comparison

Normalization v2ではLLMを再実行していないため、意味評価は保存済みCanonical Eventの固定Replay値で比較した。v2の結合対象2箇所に対応するv1 Analyzer Outputはどちらも`events: []`であり、固定Event Streamに差分がないことを確認した。

| Metric | Clean | STT v1 | STT v2 offline fixed-event |
| --- | ---: | ---: | ---: |
| Topic Precision | 1.0000 | 1.0000 | 1.0000 |
| Topic Recall | 1.0000 | 1.0000 | 1.0000 |
| Strong Decision Precision | 0.3333* | 0.4000 | 0.4000 |
| Strong Decision Recall | 1.0000 | 1.0000 | 1.0000 |
| Action Precision | 1.0000 | 1.0000 | 1.0000 |
| Action Recall | 0.6250 | 0.8750 | 0.8750 |
| Topic Return Accuracy | — | 1.0000 | 1.0000 |
| Focus event recall | — | 0.9000 | 0.9000 |
| Strict No-op Accuracy | 0.6000 | 0.5000 | 0.5000 |
| Accepted Nodes / Utterance | 0.7500 | 0.7769 | fixed-event value |
| Max Nodes / Utterance | 2 | 2 | 2 |
| 3+ Node Utterance Rate | 0 | 0 | 0 |
| Weak / non-Strong Decision count | — | 3 | 3 |

`*` Cleanの全Decision Nodeを分母にした既存30分Workload diagnostic。Strong Decisionだけを分母にする指標ではない。

結論として、Boundary v2だけではExtra Open Item / Weak Decision / Label Noiseを除去できない。Analyzer前段のFiller Skipは有効なNoise Guard候補だが、Lexical Errorを解決しない。

## 10. Map Quality

| Map | Quality | Critical Information Recall |
| --- | ---: | ---: |
| Clean | 4.8 | 1.0 |
| STT v1 | 3.8 | 1.0 (Projection), 0.9048 (cross-run category) |
| STT v2 | 3.8 | 1.0 (fixed-event Projection), 0.9048 (fixed-event category) |

STT v1でStrong Decision `2/2`、Current Topic `1/1`は保持された。Actionは`7/8`、Important Open Itemは`9/10`で、Category Recallは`0.9048`。したがって「決定を逆転させる」危険ではなく、**重要状態は残るが、弱い候補・余分なOpen Item・固有語崩れで会議中の読みやすさが落ちる**ことが主問題である。

## 11. Label Quality

| Dimension | STT v1 assessment | v2 effect |
| --- | --- | --- |
| Faithful | 大枠のTopicは保つが、`MAT`、`MFD`、`藍の画像`などで局所的に低下 | 変化なし |
| Concise | Analyzerが要約するため概ね維持 | 変化なし |
| Understandable | 固有語誤認したCardで低下 | 変化なし |
| Non-redundant | Node数差により一部Noiseが増える | 変化なし |

既存NodeのSemantic Matchは、`ディスカッションマップ`、`MAP`、`TOPIC`、`レイン`などの表記ゆれをAnalyzer Contextと既存Graphが吸収し、Topic identityを保った。これはAnalyzerのRobustnessとして評価できる。一方、既存Labelを根拠なくRaw Evidenceへ逆補正する処理はまだ導入していない。

## 12. Terminology Hint Capability

現在のSTT Adapterは `model`、`language`、`response_format`、Diarization時の`chunking_strategy`を送っている。ProviderのTranscription APIには、録音の固有語・文脈を補助するPrompt / Terminology相当の入力を追加できる余地がある。導入すれば、`MVP`、`Discussion Map`、`Visual Artifact`、`Current Topic`、`Open Item`などの表記安定化に効果が見込める。

ただし今回はBaseline Freezeのため有効化していない。次回は同じ音声を使い、Terminology Hintあり / なしのSTT-only比較に分けるべきで、Analyzer Prompt変更と混ぜない。

## 13. Analyzer Noise Guard

Normalization v2のAnalyzer eligibility sidecarは、次の軽量Guardとして有効である。

- Filler-only / Agreement-onlyをAnalyzerへ送らない。
- Raw Evidenceは保持する。
- `内容 + 相槌`はSkipしない。
- Incomplete Fragmentは、v2の境界結合後にのみ判定する。

ただし、Extra Open Item `+3`、non-Strong Decision `+3`、Action `+2`は、単純Filler Skipだけでは解決しない。STT本文が意味ありげな誤文になるため、次の段階ではAnalyzer側で「低信頼な固有語置換・不完全な参照・弱い疑問文」を安全側へ倒す評価が必要である。意味判定を大量のRule Engineへ移すことは避ける。

## 14. Normalization Latency / Determinism

v2のローカル処理時間は、129 Raw Segmentに対して今回の実行で約`0.95 ms`、Raw Segmentあたり約`0.0074 ms`だった。File I/O、Graph Replay、LLMは含まない。Recorded / Realtimeのいずれでも無視できる規模である。

- `normalize_segments_v2`は同じRaw Segmentから同じUtterance、ID、Boundaryを生成。
- Replay ArtifactはGraph / Revisionを変更しない。
- Raw STT、v1 Normalized、v2 Normalizedを別Artifactとして保持。
- Existing STT replay determinismは維持。

## 15. Tests

追加した [tests/test_stt_normalization_v2.py](../../tests/test_stt_normalization_v2.py) で次を検証した。

- Incomplete Fragment merge
- Terminal Filler + continuation merge
- Speaker boundary preservation
- Filler / Agreement Evidence retention and Analyzer skip policy
- Deterministic normalization
- Boundary audit
- Canonical Graphを変更しないDerived処理

既存STT / Analyzer / Materializerのテストも再実行する。全体結果は完了報告に記載する。

## 16. Decision

**D — Combination B + C** を採用する。

- Normalization v2は低コスト・低リスクなDerived Policyとして採用候補。ただしこれだけでRecorded Analyzer readinessを回復したとはしない。
- **B: STT Provider / Terminology Iteration** — CER `0.2834`と固有語置換がLabel / Node分類へ波及しているため必要。
- **C: Analyzer Noise Robustness Iteration** — Boundaryを直してもExtra Open / Weak Decisionが残るため必要。
- **Aのみ**（Normalization v2単独）は不十分。
- **E: Ready for Live Audio Prototype** ではない。Live Microphone / Streaming STTへは進まない。

Recorded Analyzerは「重要Stateを保持する」点では強いが、Map Quality `3.8`であり、現時点ではRecorded STT品質をMVP水準としてReadyとは判定しない。

## 17. Next Step

次に行うべきは、Prompt v5ではなく、以下を分離したRecorded STT Iterationである。

1. Terminology HintのSTT-only A/B（同一Raw Audio、同一Analyzer）。
2. Normalization v2 + Noise Guardの固定評価。
3. 追加Open Item / non-Strong Decision / Actionだけを対象に、AnalyzerのSafety評価。
4. Clean / STT / STT-v2のMap Quality再評価。

Live Microphone、Streaming STT、Prompt v5、Visual Generation、Minutes Generationは本Spikeの対象外として維持する。
