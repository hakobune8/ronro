# Analyzer Prompt v5 — STT Robustness Evaluation

## 結論

`analyzer-prompt-v5` は構造的には実行可能でしたが、今回のBaselineには採用しません。

STT側ではDecision数・Open Item数・Canonical Node数が減少した一方、Strong Decision Precisionは目標に届かず、Action Recallも改善しませんでした。さらにClean Transcript側でDecisionの過剰生成とNode増加が発生したため、v4のClean品質を守るという前提を満たしていません。

判定は **C. Keep Prompt v4** です。Recorded STT + Analyzerは、Critical Information Recallは維持しているものの、Strong Decision Precision / Action Recall / Map QualityがMVP目標未達のため、Live Audio Prototypeへは進みません。

## Frozen Configuration

|項目|設定|
|---|---|
|STT|保存済み `gpt-transcribe + terminology hints` 結果|
|Analyzer|`gpt-5.6-luna`|
|Reasoning|`medium`|
|Prompt|v4 baseline vs `analyzer-prompt-v5`|
|Context|v1|
|Normalization|v2|
|Golden|`golden-v2`（30分Workloadは既存の不変派生Annotation）|
|Evaluation|`analyzer-eval-v2`|
|Type D|OFF|
|Noise Guard|OFF|
|Materializer / Projection|既存実装|

STT APIは再実行していません。Run artifactにはRaw LLM output、Parsed output、Canonical replay結果を保存し、API keyやAuthorization headerは保存していません。

## Prompt v5 Changes

v4のStructured Output Contract、Vocabulary、Node / Relation Economyをそのまま保持し、末尾にSTT向けの意味安全規則を追加しました。

- Transcriptは不完全な音声認識Evidenceとして扱い、明示された意味より強く補完しない。
- Preference → Decision、Suggestion → Action、Question → Decision、Fragment → Open Item、Agreement → Decision / Confirmationの昇格を禁止。
- Decisionは、現在発言内の対象・Commitment・Preferenceより強い表現の3条件を満たす場合だけ許可。
- `〜にする`、`〜で進める`、`〜を採用する`、`〜を外す` 等を強いEvidenceとして提示。
- 短い明示的Action（`確認します`、`整理します`、`私がやります` 等）は短さだけで捨てない。
- Owner / Dueは現在Evidenceに明示される場合だけ設定。
- 不完全Fragment、対象不明の発言、STT誤認らしい断片は `events: []` を優先。
- 軽微なTechnical Term揺れはRelevant Existing Topicを参照できる場合だけ吸収し、自由な意味修復はしない。

Canonical Schema、Analyzer Output Schema、Context Builder、Materializerは変更していません。

## Preflight

Run開始前に、v4で問題となったSTTのNon-Strong Decision 6件、Missed Action、Extra Open Item、Clean Strong Decision / Action / No-opを含む11件を実行しました。

|チェック|結果|
|---|---:|
|API success|11 / 11|
|JSON parse|11 / 11|
|Analyzer Output Schema|11 / 11|
|Canonical conversion path|11 / 11|
|Canonical Event Schema|11 / 11|
|Semantic anchor pass|5 / 11|

構造的なFailureはありませんでしたが、Semantic Anchorは通過しませんでした。具体的には、STTの sequence 34 / 63 / 80 / 113 が依然としてDecisionへ昇格し、sequence 119の明示的ActionはActionとして返りませんでした。sequence 114も不完全な意味をOpen Itemへ変換しました。

この結果を確認したうえで、Prompt v5を固定し、120 Clean Utterancesと120 STT Utterancesを本Runしました。

## Structural Results

### Full Run

|Track|Calls|API|JSON / Output Schema|Canonical Event Schema|Safety / conversion diagnostic|
|---|---:|---:|---:|---:|---|
|Clean v5|120|120 / 120|120 / 120|発行Eventは全件valid|Critical diagnostic 0|
|STT v5|120|120 / 120|120 / 120|発行Eventは全件valid|1 batch rejected、`inferred_action_metadata_rejected` + `relation_reference_unresolved`|

STT sequence 119のLLM出力自体はStructured Schemaに適合していましたが、保存されたSTT Evidenceに対するAction metadata / Relation referenceの安全検証で適用されませんでした。これはFalse Actionを許すより安全ですが、実運用上はAction Recallを失うAdapter / Reference Resolution課題として残ります。

## Clean Track: v4 vs v5

|Metric|v4|v5|差分|
|---|---:|---:|---:|
|Topic Precision|1.000|1.000|0|
|Topic Recall|1.000|1.000|0|
|Strong Decision Precision（strict）|0.333|0.286|悪化|
|Strong Decision Recall（strict）|1.000|1.000|維持|
|Action Precision|1.000|1.000|維持|
|Action Recall|0.625|0.750|改善|
|No-op Accuracy|0.600|0.650|改善|
|Candidate Decision数|6|7|+1|
|Non-Strong Decision数|4|5|+1|
|Open Item数|13|10|-3|
|Node数|90|96|+6|
|Relation数|85|90|+5|
|Nodes / Utterance|0.750|0.800|悪化|
|Max Nodes / Utterance|2|1|改善|
|Critical Information Recall|1.000|1.000|維持|

v5は短いActionのRecallを改善しましたが、Decisionの安全性は改善していません。v5のDecision出力7件のうち、strictなStrong Decisionは2件で、残る5件はWeak / False相当でした。

主なNon-Strong例は、`Current TopicをStatus Railにも表示する`、`名前とDecision・Open Item・Actionの件数を残す`、`AnalyzerはGraphを直接変更しない`、`料金モデルの比較をいったん保留する` です。いずれも会議上のIdea・設計方針・保留であり、Candidate Decisionとして表示するとDecision Safetyを損ないます。

## STT Track: v4 vs v5

|Metric|v4|v5|差分|
|---|---:|---:|---:|
|Topic Precision|1.000|1.000|維持|
|Topic Recall|1.000|1.000|維持|
|Strong Decision Precision（strict）|0.125|0.167|小幅改善|
|Strong Decision Recall（strict）|0.500|0.500|維持|
|Action Precision|1.000|1.000|維持|
|Action Recall|0.625|0.625|変化なし|
|No-op Accuracy|0.650|0.650|変化なし|
|Candidate Decision数|8|6|-2|
|Non-Strong Decision数|7|5|-2|
|Open Item数|12|10|-2|
|Node数|95|93|-2|
|Relation数|89|87|-2|
|Nodes / Utterance|0.792|0.775|改善|
|Max Nodes / Utterance|2|1|改善|
|Relations / Utterance|0.742|0.725|改善|
|Critical Information Recall|1.000|1.000|維持|

STT側のCandidate Decisionは減少しましたが、6件中strict Strongは1件で、Precisionは0.167に留まりました。目標の0.75には大きく届きません。Actionは7件が提案され、正確性は維持したものの、意味的に一致したActionは5件でRecall 0.625のままでした。

## Decision / Action Review

### Decision

全Candidate DecisionをReviewした結果は次のとおりです。

- Clean v5: Strong 2、Weak / False 5
- STT v5: Strong 1、Weak / False 5
- Automatic Confirmation: 0
- Invented Owner: 0
- Invented Due Date: 0

STT v5で改善した点は、v4にあった `スマホコントローラーは今回はパーキングとする` のような弱いDecisionをIdeaへ下げたことです。一方、`料金モデルの比較は急がずワーキングに置いておく` は、保留・方針SignalであってStrong Decisionではありませんが、なおDecisionになりました。

### Action

Clean v5ではAction Recallが0.625から0.750へ改善しました。短い明示Actionの回収は有効でした。

STT v5ではRecallは0.625のままでした。sequence 119では、LLMはAction、Owner、DueをStructured Outputとして返しましたが、Application側がAction metadataをEvidenceから安全に確定できず、Relation参照も解決できなかったためGraphへ適用しませんでした。Raw Evidence上のOwner / Dueを推測して追加したわけではなく、安全側にRejectされたものです。

## Graph / Map Review

### Graph

- Topicは両Trackとも6 laneを維持し、Topic ReturnとCurrent Topicの意味的整合性は維持。
- Clean v5はNode 90→96、Relation 85→90となり、Decision / Actionの追加でMapの入力密度が増加。
- STT v5はNode 95→93、Relation 89→87となり、STT由来の弱いDecisionとOpen Itemを一部抑制。
- Critical Information RecallはClean / STTとも1.0で、Current Topic、Decision、Action、Open ItemのProjection上の参照可能性は維持。

### Map Quality

v4の4.8（Clean）/ 4.0（STT）は既存30分評価の履歴値です。v5は今回の6項目Rubricを新たに適用し、Decision Safetyを25%、他のClarity / Density / Topic Coherence / Stability / Usefulnessを各15%として算出しました。これは参加者実験ではなく、保存Projectionに対する評価者Rubricです。

|Track|v4 historical Map Quality|v5 six-factor score|v5 Usefulness|所見|
|---|---:|---:|---:|---|
|Clean|4.8|4.1|4.5|Topicは追えるが、Weak / False DecisionがDecision Railを汚す|
|STT|4.0|4.1|4.1|Node / Open Itemは減ったが、用語崩れとDecision誤分類が残る|

v5のMapはSTT側で少し整理されましたが、Clean側のRegressionを許容してまで採用する改善ではありません。STT側も目標4.3に未達です。

### Label Quality

- Clean v5: Labelsは概ね短く理解可能でしたが、弱い内容をDecision labelとして表示したためNon-redundant / Decision-safe評価が下がりました。
- STT v5: `ディスカッションマップ` など一部のTopic Identityは維持できましたが、`MAT`、`ER`、`ASCRIT`、`TROTOTYPE` などのLexical noiseが残りました。
- v5は不確かな用語を勝手に修復しなかった点では安全ですが、Terminology correctnessを改善するPromptではありません。ここはSTT側の語彙認識または既存Node参照の課題です。

## Latency / Tokens / Cost

|Track|Version|p50 (s)|p95 (s)|max (s)|total tokens|estimated cost|
|---|---|---:|---:|---:|---:|---:|
|Clean|v4|2.143|3.435|4.468|509,686|$0.127706|
|Clean|v5|2.375|4.514|5.778|633,465|$0.152352|
|STT|v4|2.805|4.230|5.187|589,957|$0.151246|
|STT|v5|2.375|4.514|5.778|726,534|$0.180614|

v5の追加ポリシーによりPrompt token / costは増加しました。概算でCleanはtoken +24%、cost +19%、STTはtoken +23%、cost +19%です。p95 / maxも改善していません。Recorded評価のためRealtime要件との直接比較はしませんが、品質未達のままコストだけ増える状態です。

## Good / Failure Examples

### Good

- Clean `オンライン会議連携はMVPから外しましょう` → Candidate Decision。対象とScope choiceが明示されている。
- Clean `次回までに画面のたたき台を作ります` → Action。Explicit execution intentを維持。
- STT `スマホコントローラーも今回はパーキングのままで良いです` → Idea。弱い方針をDecisionへ昇格しなかった。
- STTのTopic lane / Topic Returnは6 laneを維持し、Current TopicのCritical Information Recallは1.0。

### Failure

- Clean `Current TopicをStatus Railにも表示する` → Decision。仕様Idea / UI方針の過剰昇格。
- STT `名前とDECISION、オープンアイテム、ACTIONの数は残しましょう` → Decision。表示仕様でありStrong Decisionではない。
- STT `料金モデルの比較は急がず、ワーキングに置いておきましょう` → Decision。保留SignalをDecision化。
- STT sequence 119 → Explicit ActionをLLMは出力したが、Action metadata / Relation reference検証でReject。Action Recallが回復しない。
- STTのMalformed technical termは、v5でもLabel品質を下げるが、誤った意味へ修復しなかった。

## Failure Classification

|Failure|分類|説明|
|---|---|---|
|Weak / False Decisionの残存|Prompt Semantic Rule + Model Capability|Commitmentルールを明示しても、方針・保留・仕様文をDecisionへ昇格する|
|STT Action Recall 0.625|Canonical Conversion / Reference Resolution + STT lexical noise|sequence 119のように、Action intentはあるが安全検証で適用されない|
|Technical-term label崩れ|STT lexical error|`ER` / `ASCRIT` / `TROTOTYPE`等。v5の意味昇格防止では解決しない|
|Clean Node増加|Prompt Semantic Rule|v5追加規則がTopic / Actionの境界を局所的に広げた|
|Topic Recall|問題なし|粗い6 lane評価ではClean / STTとも1.0。より細かいLabel品質は別途残る|

## Regression / Decision

v5はSTTのCandidate Decisionを8→6、Open Itemを12→10、Nodeを95→93へ減らしました。しかし、以下の理由で採用しません。

1. Clean Map Qualityは履歴4.8からv5 Rubric 4.1相当へ下がり、Decision Precisionは0.286で目標0.90から遠い。
2. STT Strong Decision Precisionは0.167で目標0.75未達。
3. STT Action Recallは0.625のままで、目標0.80未達。
4. Prompt token / costが約19〜24%増えた。
5. Critical Information Recall 1.0、Action Precision 1.0、Automatic Confirmation 0は維持したが、安全性の最低条件を満たすだけで十分なMap品質には達していない。

したがって、今回のPrompt変更は **C. Keep Prompt v4** とします。v5は削除せず、失敗したPreflight / Full RunをRegression Setとして保持します。Prompt v5を採用したまま追加STT作業へ進む判定（B）にはしません。

## Live Audio Gate

**Not ready.**

Recorded STTでCritical Information Recall 1.0、Automatic Confirmation 0、Action Precision 1.0は確認できました。しかし、STT Map Quality 4.1、Strong Decision Precision 0.167、Action Recall 0.625は今回の目安を満たしません。Live Audioへ進む前に、少なくとも次のどちらかを別Spikeとして解決する必要があります。

- DecisionのSemantic Classificationをv4 Baselineを壊さず改善すること。
- STT Evidence上の明示Actionを安全なOwner / Due / Relation変換まで失わないこと。

今回の範囲ではPrompt v6、Noise Guard再導入、STT再実行、Live Audio実装は開始していません。

## Artifacts

- [Prompt v5 run artifacts](../../evaluation/stt/prompt-v5/)
- [Preflight](../../evaluation/stt/prompt-v5/preflight.json)
- [Comparison](../../evaluation/stt/prompt-v5/comparison.json)
- [Quality review](../../evaluation/stt/prompt-v5/quality-review.json)
- [Clean run](../../evaluation/stt/prompt-v5/clean/analyzer/run.json)
- [STT run](../../evaluation/stt/prompt-v5/stt/analyzer/run.json)
