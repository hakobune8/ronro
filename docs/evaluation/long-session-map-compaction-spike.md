# Long-session Map Compaction / Semantic Consolidation Spike

Status: Completed

このSpikeは、30分Recorded DiscussionのCanonical Graphを削除・変更せず、共有画面へ出すPresentation Projectionだけを圧縮できるかを検証した。Prompt v5、STT、Live Audio、Visual Generation、Minutes Generationは開始していない。

## 1. Frozen baseline and source

| Item | Value |
| --- | --- |
| Model | `gpt-5.6-luna` |
| Reasoning | `medium` |
| Prompt | `analyzer-prompt-v4` |
| Context | `v1` |
| Golden | `golden-v2` |
| Evaluation | `analyzer-eval-v2` |
| Type D | OFF |
| Source workload | 30分 / 120 Utterance / `recorded-30min-discussion-v1` |
| LLM calls | 0（保存済みRun ArtifactをReplay） |
| Canonical Graph mutation | なし |

Projection実装は[prototype/projection.py](../../prototype/projection.py)、Replayと比較は[prototype/long_session_compaction.py](../../prototype/long_session_compaction.py)に置いた。成果物は[compaction-spike-v1](../../evaluation/30min/compaction-spike-v1/)に保存した。

## 2. Compaction policy

今回の推奨Projectionは、次の3層を組み合わせた。

### Layer 1 — UI Collapse

M5.1の既存方針。Current TopicはExpanded、Non-current TopicはCompact Summary、Parkingは別Laneとする。Canonical Nodeはすべて残る。

### Layer 2 — Conservative Semantic Grouping

同一Topic・同一Node Typeで、正規化後のラベルがほぼ包含関係にある場合だけ、Presentation上のRelated Group候補にする決定的ヒューリスティックを試した。今回の30分Graphでは安全に確定できるGroupは0件だった。

意味が近いというだけで別のIdea / Concern / Optionをまとめると、Evidenceの意味を誤って変える可能性がある。したがって、Layer 2は候補として保持するが、今回のDefault Projectionには実質的なConsolidationを適用しない。

### Layer 3 — Topic Summary Projection

- Current Topic: 直近の低優先Nodeを最大8枚まで表示。
- Decision / Action / Open Item / Active Concern: RecencyよりImportanceを優先し、Current TopicではBudgetを超えても隠さない。
- Non-current Topic: 1つのDeterministic Summary Cardへ圧縮。
- Non-currentのCritical State: Status Railの個別Entryとして表示。
- Parking: 専用Summary Laneへ分離。
- SummaryはNode Label、Status、件数、直近の重要Labelから構成し、LLMは呼ばない。
- Projectionには`source_revision`を付け、Graph更新時に再計算する。

#### Summary generation alternatives

|方式|評価|今回の判断|
|---|---|---|
|Deterministic|Node label、status、件数、直近の重要項目だけで構成でき、追加LLM Call・幻覚・stalenessを避けられる。抽象的な要約力は限定的。|**今回採用**|
|LLM-generated|自然な短文要約は期待できるが、遅延・コスト・再現性・誤要約の検証が増える。|MVPでは未採用|
|Hybrid|構造化FactsをDeterministicに固定し、短い説明文だけLLM化できる。品質は上がり得るが、Summary専用評価が必要。|将来候補|

今回のSummaryはCanonical Factではなく、`source_revision`付きのDerived Projectionとして扱う。Node追加時には保存済みSummaryを更新するのではなく、同じRevisionのGraphから再計算する。

Current TopicにはM5.1のManual Expand / Compactを再利用できるよう、Projectionに`grouped_node_ids`を保持する。30分時点ではCurrent Detailの予算外Nodeを`+14 earlier items`として示し、ユーザーが必要なときだけ展開できる。Expand / Compact、selected node、scroll、zoomはPresentation Stateであり、Canonical Graphへ書き込まない。

### Layer 4 — Canonical Graph Consolidation

Physical Merge / Supersedeは実施しなかった。History、Evidence、Event Stream、Replayを守るため、MVPの長時間表示問題に対する第一手段にはしない。

## 3. Snapshot comparison

`Visible Card`はMap Canvas上のDetail CardとSummary Cardを数える。Status RailのCritical Entryは別集計し、Canvas Compression Ratioを不当に大きくしないようにした。

| Time | Canonical Nodes | Existing Canvas Cards | Compacted Cards | Existing Ratio | Compacted Ratio | Hidden / Grouped | Visible Current Nodes | Visible Open | Visible Decisions | Visible Actions | Critical Recall | Quality before → after |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 5 min | 16 | 16 | 8 | 1.0000 | 0.5000 | 8 | 8 | 2 | 1 | 1 | 1.0 | 4.4 → 5.0 |
| 10 min | 33 | 18 | 9 | 0.5455 | 0.2727 | 19 | 8 | 4 | 2 | 2 | 1.0 | 4.2 → 5.0 |
| 15 min | 49 | 17 | 10 | 0.3469 | 0.2041 | 29 | 8 | 6 | 2 | 3 | 1.0 | 4.0 → 5.0 |
| 20 min | 64 | 26 | 12 | 0.4062 | 0.1875 | 39 | 9 | 8 | 5 | 3 | 1.0 | 3.8 → 5.0 |
| 25 min | 77 | 12 | 12 | 0.1558 | 0.1558 | 44 | 6 | 10 | 6 | 4 | 1.0 | 3.6 → 4.8 |
| 30 min | 90 | 31 | 17 | 0.3444 | 0.1889 | 54 | 11 | 13 | 6 | 5 | 1.0 | 3.6 → 4.8 |

QualityはM5の6項目Rubricに対する静的Projection Reviewであり、参加者によるユーザテストのスコアではない。30分時点のCanvas Cardは31から17へ減少し、Compression Ratioは`0.3444`から`0.1889`になった。一方、Candidate / Confirmed / Revoked Decision、Action、Open ItemはすべてRailまたはCurrent Detailで追跡可能だった。

### 30分時点のProjection内訳

- Current Topic: 11 Detail Cards（Critical NodeはBudget例外）
- Non-current Topic Summary: 5
- Parking Summary: 1
- Canvas total: 17
- Status Rail Critical Entries: 17
- Grouped / hidden from Canvas: 54
- Critical Information Recall: 1.0

Current Detail Budgetは8を基本値としたが、Critical Stateを隠さないため、30分時点では11枚になった。この例外は意図した安全側の挙動であり、Decision / Action / Open Itemをさらに縮める場合はSummaryではなくRail設計の検証が必要になる。

## 4. Critical Information Recall

30分時点でも次をすべて1.0で検出できた。

- Current Topic
- Candidate Decision
- Confirmed Decision
- Revoked Decision
- Action
- Important Open Item

DecisionやActionを単純に「古いNode」として隠さず、Current DetailまたはStatus Railへ移したことが効いている。Compression Ratioを小さくすること自体を目的にしてはいけないという方針を確認できた。

## 5. Open Item audit

Final Graphの13 Open Itemを個別に分類した。ClassificationはPresentation判断であり、Canonical statusを変更していない。

| Sequence | Open Item | Classification | Presentation判断 |
| ---: | --- | --- | --- |
| 5 | スマホ側にも必要な機能があるか | Superseded / Low priority | MVP scope候補であり、Main Detailから外しSummary/Railへ。 |
| 9 | 会議中の利用価値をどう測るか | Still Open | 重要な未解決事項。Railに残す。 |
| 30 | A案とB案のどちらが追いやすいか | Still Open | 明示確認がないため未解決。 |
| 35 | 30分後でも最初の論点を見つけられるか | Resolved but state not updated | このSpikeで検証したがCanonical Nodeはactiveのまま。 |
| 44 | 生成したVisualを正式な答えとして扱うのか | Still Open | Product Principleに関わるため保持。 |
| 57 | MVPで複数案にするタイミング | Still Open | Future policyとして未決。 |
| 68 | 実際の遅延がまだ不明 | Duplicate / Similar | seq69とLatency論点としてPresentation grouping候補。 |
| 69 | 会議を邪魔しない遅延の上限 | Duplicate / Similar | seq68とは別の測定項目なのでCanonical Mergeはしない。 |
| 84 | 初期顧客に説明しやすい料金 | Still Open | Pricingの重要な未決。 |
| 95 | Discussion Contextをどこまで小さくできるか | Still Open | Privacy / Costに関わる未決。 |
| 111 | Privacy草案の担当者 | Still Open | Owner不明。Actionへ推測変換しない。 |
| 113 | 料金モデルの比較を後で検討する | Parking candidate / Low priority | 明示的に後回し。Parking候補として縮退。 |
| 118 | 次のPrototypeで30分Mapが読めるか | Resolved but state not updated | このSpikeの対象だが、Canonical close Eventはない。 |

集計すると、7件はStill Open、2件はこのSpikeで事実上評価済みだがactiveのまま、2件は類似表示候補、1件はSuperseded / Low priority、1件はParking candidateとして扱える。複数分類があるため合計は重複する。

### Open Item Lifecycle finding

これはPresentationだけの問題ではない。Domain Schemaには`resolved` statusが存在するが、Prototype Event Catalog / MaterializerにはOpen Itemを明示的に解決するCanonical Eventがない。`archive_node`は履歴を残すが、質問に答えたという意味を表さない。

したがって、13件をすべてactiveのまま保つと、どれだけProjectionを圧縮しても「未解決の山」は増え続ける。今回のDecisionは、まずPresentation Compactionを採用しつつ、次の設計課題として **Open Item Lifecycle Amendment** を提案することである。Schema変更は今回行っていない。

## 6. Topic Summary and Topic Return UX

Deterministic Topic Summaryは、件数だけでなく、直近のDecision / Open / Action Labelを2件まで含めた。例えば非Currentの`Mapのレイアウト`は、次のように表示できる。

```text
Mapのレイアウト
1 Decision / 2 Open / 1 Action
レイアウトの試作を作成…、30分後でも最初の論点を見つけられるか
```

これにより、Non-current Laneを再Expandしなくても「何を話したTopicか」を想起できる。Summaryは`source_revision`を持つDerived Projectionであり、Node追加時に同じGraph Revisionから再計算するため、古いSummaryをCanonical Factとして保存しない。

Topic Return時は、既存Topic IDのLaneをCurrentに戻し、SummaryではなくCurrent Detailへ再展開する。Current Topic、Recent Important Nodes、Open Item、Decisionは同じGraphから再び表示されるため、「別のMapに置き換わった」印象を抑えられる。

## 7. Map Quality and 1920×1080 review

### Static rubric result

30分時点の静的評価は次の通り。

| Metric | Existing M5.1 | Compacted Projection |
| --- | ---: | ---: |
| Clarity | 2 | 5 |
| Density | 2 | 4 |
| Decision Safety | 5 | 5 |
| Topic Coherence | 5 | 5 |
| Stability | 4 | 5 |
| Usefulness | 3.6 | **4.8** |

Targetの`Map Quality >= 4.0`と`Critical Information Recall = 1.0`を、静的Projection評価では満たした。

### Browser review

生成した[compacted-overview.html](../../evaluation/30min/compaction-spike-v1/compacted-overview.html)をローカルブラウザで確認した。30分Snapshotでは、Current TopicのExpanded Lane、5つのNon-current Summary、Parking Lane、Decision 6件、Open Item 13件、Action 5件のRail表示が存在した。SummaryにはDecision / Open / Action件数と短いTopic要約が出る。

本環境のIn-app Browserでは実viewportを物理的に1920×1080へ固定するCapabilityが利用できなかった。そのため、Projectionデータと1920×1080想定のCSSレイアウトは確認したが、実画面のPixel-level離読性を完全に証明するScreenshotは保存していない。少なくともLane-level Overviewは成立し、残るリスクはStatus Railの文字量と11枚のCurrent Detail Cardである。

## 8. Action Event conversion audit

30分Evaluationで観測したAction問題は、Compactionとは別の問題として分離する。

- Analyzer Output: `rec30-u058`、`u077`、`u087`、`u119`でAction-like Structured Outputが返った。
- Canonical Conversion: 同じOutputに含まれる`contains` Relationの参照解決に失敗し、Canonical Eventとして受理されなかった。
- Owner / Due: `u119`のRaw Outputには明示的な`田中さん` / `2026-09-26`があったが、Graphには入らなかった。推測値が混入したわけではない。
- Map Projection: 受理済みActionの位置・表示には問題は見つからなかった。
- Event Ordering: Replayは193 Revisionまで決定的に完了した。

したがって、原因はMap CompactionやEvent Orderingではなく、Analyzer Outputから複数のCanonical Eventへ変換するAdapterの参照解決である。次のAction評価で別途扱う。

## 9. Layer decision

| Layer | Result |
| --- | --- |
| Layer 1 UI Collapse | 既存M5.1として有効。ただしCurrent Topicの詳細が増え続ける。 |
| Layer 2 Semantic Grouping | 安全な決定的Heuristicでは今回0 Group。自動意味統合は採用しない。 |
| Layer 3 Topic Summary Projection | **採用候補**。Canvasを17 Cardsへ抑え、Critical Recall 1.0を維持した。 |
| Layer 4 Canonical Graph Consolidation | 不採用。Physical Merge / Supersedeは将来検討。 |

## 10. Decision

### **B. Presentation + Open Item Lifecycle**

Presentation-only Compactionは、長時間Mapの可読性を十分改善した。30分時点でCanvas Cardは31→17、Qualityは3.6→4.8、Critical Information Recallは1.0だったため、Layer 3をPresentation ProjectionのSpike Baselineとして採用する。

ただし、Open Itemを解決するCanonical Eventがないため、長時間会議の未解決情報の蓄積はPresentationだけでは根治できない。次段階では、Open Item Lifecycleを別途設計し、Schemaを変更する前にEvent / Human Correctionの意味を決めるべきである。

## 11. Readiness gates at the end of this spike

- Recorded Analyzer: **Not Ready**
  - Compactionは有効だが、Action Event conversionの欠落とOpen Item Lifecycle未解決が残る。
- Recorded STT Spike: **Not Ready**
  - Recorded Analyzerの長時間Map品質とAction / Open Itemの意味状態を先に安定させる。

この時点ではCanonical Contract、Schema、Materializer、Prompt、Model、Type D baselineは変更していない。今回のSpike自体で追加したのはPresentation Projection、Offline Snapshot評価、Preview、Testsだけである。

## 12. Follow-up blocker resolution

上記2つのBlockerは、後続の最小修正で解消した。

- Open Itemは既存Node statusの`active` / `resolved`を使い、Human-onlyの`resolve_open_item` / `reopen_open_item`を追加した。13件のうち、事実上解決済みだった2件をDerived SimulationでResolveすると、Projection上のOpen Itemは13→11件となり、Critical Information Recallは1.0を維持した。
- ActionはProvider-facing `new_node_index`をLocal Referenceとして二段階解決する既存境界をテストで固定した。Run #4の保存済みOutputを再変換し、明示的なAction 3件をNode＋`contains` Relationとして回復した。提案表現は安全側でAction化しなかった。

詳細とDerived Artifactsは[`recorded-analyzer-readiness-repair.md`](recorded-analyzer-readiness-repair.md)および`evaluation/30min/compaction-spike-v1/`を参照する。Run #4の履歴は変更していない。

修正後のDerived Readinessは、Recorded Analyzer **Ready**、Recorded STT Spike **Ready**（Recorded Audio → STTの検証のみ。Live Audioではない）と判定する。
