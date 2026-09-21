# 30-minute Recorded Discussion Evaluation

Status: Completed

この評価は、`analyzer-prompt-v4` と既存のDiscussion Mapを、30分相当の連続した日本語Discussionへ適用したProduct-level Evaluationである。目的は、精度だけでなく、Map密度、Decision Candidate密度、Human Confirmation負荷、Current Topic、Parking、共有画面上の可読性を確認することだった。

Prompt v5、STT、Live Audio、Visual Generation、Minutes Generationは開始していない。

## 1. Frozen baseline and method

| Item | Value |
| --- | --- |
| Provider | OpenAI-compatible runtime provider |
| Model | `gpt-5.6-luna` |
| Reasoning | `medium` |
| Prompt | `analyzer-prompt-v4` |
| Context | `v1` |
| Golden benchmark | `golden-v2`（変更なし） |
| Evaluation | `analyzer-eval-v2`の方針を維持 |
| Workload dataset | `recorded-30min-discussion-v1` |
| Workload annotation | `recorded-30min-golden-v1`（既存Goldenとは別） |
| Type D | OFF / ON |

既存の5 Scenario / 38 Utterance用の`golden-v2`は変更していない。30分Workload固有の期待値は、連続Discussionの密度・Type D・Human操作を評価するための派生Annotationとして保存した。

Real Analyzerは120 Utteranceに対して1回だけ実行し、Raw Structured OutputとTraceを保存した。その同じキャッシュを使ってType D OFF / ONをReplayしたため、OFF/ON比較で追加のLLM呼び出しは発生していない。

Artifacts:

- [30分Evaluation artifacts](../../evaluation/30min/README.md)
- [Run directory](../../evaluation/30min/run-gpt-5.6-luna-analyzer-prompt-v4-20260919/)

## 2. Recorded Discussion

実際の会議Transcriptではなく、MVP検討会を題材にしたRealistic Synthetic Transcriptを使用した。相槌、言い直し、Preference、曖昧な「それ」、Topic Drift、Topic Return、Parking、Explicit Action、Type D Proposal + Agreementを含めている。

- Duration: 30分
- Utterances: 120
- 1 Utterance: 15秒相当
- Topic phases: 12
- Final Topic count: 6
- Theme: Discussion Map AI FacilitatorのMVP範囲、Map UX、Visual Artifact、Analyzer、価格、Privacy

## 3. Primary product metrics

Type DはこのWorkloadではCandidateを追加しなかったため、OFF / ONのGraphは完全一致した。

| Metric | Type D OFF | Type D ON |
| --- | ---: | ---: |
| Topic count | 6 | 6 |
| Final node count | 90 | 90 |
| Nodes / Topic | 14.0000 | 14.0000 |
| Accepted new nodes / utterance | 0.7500 | 0.7500 |
| Max nodes / utterance | 2 | 2 |
| 3+ node utterance rate | 0.0000 | 0.0000 |
| Relation count | 85 | 85 |
| Relations / utterance | 0.7083 | 0.7083 |
| Open items | 13 | 13 |
| Actions | 5 | 5 |
| Pending Candidate Decisions at end | 4 | 4 |
| Confirmed Decisions at end | 1 | 1 |
| Revoked Decisions at end | 1 | 1 |
| Total Decision nodes | 6 | 6 |
| Parking count at end | 1 | 1 |
| Topic transitions | 10 | 10 |
| Topic transitions / 10 min | 3.3333 | 3.3333 |
| Final Graph revision | 193 | 193 |

`Total Decision nodes`はCandidate / Confirmed / Revokedを合わせた数である。最終的にMap上で確認を要するPending Candidateは4件だった。

30分で6 Decision nodes、10分あたり2.0件のDecision形成が発生した。これはDecision Railの素材としては利用可能だが、生成直後に毎回Popupで確認を求める密度ではない。

## 4. Type D OFF / ON

Workload Annotationでは、Proposal + AgreementによるType Dの期待ケースを6件定義した。

| Type D metric | OFF | ON |
| --- | ---: | ---: |
| Expected semantic closures | N/A | 6 |
| Candidates added by Type D | N/A | 0 |
| True Type D candidates added | N/A | 0 |
| False Type D candidates | N/A | 0 |
| Ambiguous proposal rejections | N/A | 4 |
| Existing Candidate already present | N/A | 2 |
| Required new additions | N/A | 4 |
| Effective semantic coverage | N/A | 2 / 6 = 0.3333 |
| Duplicate Candidate | N/A | 0 |
| Automatic Confirmation | N/A | 0 |

厳密な「Type Dが新しいEventを追加したか」というRecallは`0 / 6`である。一方、2件は既存CandidateがすでにGraphに存在したため、Dedicated Layerが重複生成せず保持した。したがって、プロダクト状態としての未捕捉は4件であり、必要だった新規追加に対するRecallは`0 / 4`だった。

失敗理由は、現在の`current_topic_latest_proposal`がCurrent Topic配下のIdea / Option / Open Itemを複数候補として列挙し、Agreementの参照先を一意に絞れなかったことだった。Type Dの安全性自体は保たれている。

- False Candidate: 0
- Duplicate Candidate: 0
- Automatic Confirmation: 0
- Type D追加LLM Call: 0

この結果は「Type Dが不要」と断定する結果ではなく、「現在のProposal選択は30分の密なGraphでは保守的すぎて、追加価値を出せない」という結果である。

## 5. Human Confirmation burden and interruption

Human操作のシミュレーションでは、Type D OFF / ONともに以下となった。

- Confirm applied: 2件（明示的なType A Decision）
- Revoke applied: 1件
- Parking: 2件、うち1件をRestore
- Type D候補に対するConfirm: 0件（候補が追加されなかったため）
- Final pending candidates: 4件

暫定Rubricでは、実際に適用されたConfirm操作2件は **Low** である。ただし、Type Dの未捕捉4件が追加され、同じHuman planで確認すると、Confirm操作は2件から6件へ増え **Moderate** になる。Candidateをすべて即時確認させる設計は、候補密度が上がった場合に会議を阻害し得る。

比較結果:

| Policy | 評価 |
| --- | --- |
| Immediate Confirmation | 不採用。候補が出るたびに会議を止める。 |
| Passive Pending | **MVP推奨**。Decision Railへ蓄積し、会話を止めない。 |
| End-of-topic Confirmation | 補助案。Topic切替時にまとめて確認できるが、切替タイミングの定義が増える。 |

Type Dの採用可否と、Humanへいつ確認させるかは別問題である。今回の30分結果では、仮にType Dを将来復活させても、Passive Pendingを前提にすべきである。

## 6. Map growth timeline

以下のQuality値は参加者による実ユーザテストではなく、M5のRubricをSnapshot Projectionへ適用した静的レビューである。`Usefulness`はClarity、Density、Decision Safety、Topic Coherence、Stabilityの平均である。

| Time | Topics | Nodes | Pending | Open | Actions | Parking | Current Topic | Clarity | Density | Decision Safety | Stability | Usefulness |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 5 min | 1 | 16 | 1 | 2 | 1 | 0 | 会議中のDiscussion Map活用MVP | 5 | 2 | 5 | 5 | 4.4 |
| 10 min | 2 | 33 | 2 | 4 | 2 | 0 | Mapのレイアウト | 4 | 2 | 5 | 5 | 4.2 |
| 15 min | 3 | 49 | 2 | 6 | 3 | 0 | Visual Artifactの扱い | 3 | 2 | 5 | 5 | 4.0 |
| 20 min | 4 | 64 | 4 | 8 | 3 | 0 | 会議中のDiscussion Map活用MVP | 2 | 2 | 5 | 5 | 3.8 |
| 25 min | 6 | 77 | 4 | 10 | 4 | 2 | PrivacyとTranscriptの保存 | 2 | 2 | 5 | 4 | 3.6 |
| 30 min | 6 | 90 | 4 | 13 | 5 | 1 | 会議中のDiscussion Map活用MVP | 2 | 2 | 5 | 4 | 3.6 |

### Readability degradation

15分まではCurrent TopicとTopic Laneの追跡可能性が保たれた。20分時点で64 Node / 4 Topicとなり、Clarityが2へ低下した。25〜30分では6 Topic、90 Node、13 Open Itemとなり、Compact OverviewでTopicの存在は把握できるが、Card詳細を同時に読み続けるには密度が高い。

このWorkloadでは、M5.1のCompact Overviewは「全Topicを見失わない」目的には有効だった。しかし、Compact化だけでCard密度の問題は解消していない。Resolved Node折りたたみ、Open Itemの優先表示、Lane内の要約化が次のProduct検証候補になる。

## 7. Current Topic, Recent Flow, and Parking

- Topic transitions: 10
- Topic transitions / 10 minutes: 3.3333
- Topic Return: 20分、30分時点でMVP / Discussion Map系のTopicへ戻った。
- Topic Lane identity: 既存Laneを再利用し、Topic Returnで新しい重複Topicは作られなかった。
- Recent Flow: 最大7件のProjectionが生成され、Topic Returnを追う材料になった。
- Parking: 20分台後半で2件がParkingへ移り、30分時点では1件がRestore済み、1件がParkingに残った。

Current TopicはReplay上追跡できたが、30分全体で3.33回 / 10分の切替は比較的活発である。強いAuto-focusやAuto-panを追加すると注意を奪う可能性があるため、既存の「Current Laneを強調しつつ画面を奪わない」方針を維持する。

## 8. Decision Rail and Action Items

最終Decision状態は、Pending Candidate 4、Confirmed 1、Revoked 1だった。Candidate / Confirmed / Revokedの区別は保たれているため、Decision Safetyは5と評価した。一方、Pendingが4件あるため、Decision Railは常時全件を強調するより、未確認件数と選択時の詳細表示が適切である。

Actionは5件がCanonical Graphへ入り、Ownerが設定されたものは1件（「私」）、Due Dateは0件だった。推測されたOwner / DueはCanonical Graphへ入っていない。

一方、4件のRaw Analyzer OutputがActionらしい出力を返したものの、同じOutput内の`contains` Relation参照が解決できず、Canonical Eventとしては受理されなかった。その中には明示的なOwner / Dueを含む発言もあった。これは安全側には動いているが、Action completenessとEvent conversionの残課題であり、Recorded AnalyzerをSTTへ進める前に解消すべき観測事項である。

## 9. 1920×1080 Compact Overview

Projection data上、30分時点で以下を満たした。

- Topic Lane: 6
- Current Topic: 1 Lane Expanded相当
- Non-current Topic: 5 Lane Compact相当
- Parking Lane: 1
- Compact Lane summary: Decision / Open Item / Actionの件数を保持

したがって、M5.1の「全Topicの存在とCurrent Topicを一目で把握する」設計は30分Workloadにも適用可能である。ただし今回のRunではBrowserの実1920×1080 Pixel Screenshotを取得していないため、フォントサイズや物理的な離読性は未検証である。データ密度から見ても、Compact OverviewはOverviewとしては合格、詳細Mapとしては追加のProgressive Disclosureが必要である。

## 10. Type A Decision misses

このWorkloadでGoldenが明示したType A-likeなStrong Decisionは次の2件だった。

- `rec30-u076`: オンライン会議連携はMVPから外しましょう
- `rec30-u096`: Transcript全文は外部Providerへ送らない方針にしましょう

両方ともCandidateとして生成され、Human Confirmまで実行された。したがって、この30分Workloadで観測したType A Decision Missは **0件 / 2件** だった。

B-u006 / E-u001と同一のMissが30分会議全体で頻発しないことは確認できたが、2サンプルだけでPrompt v5不要を一般化はしない。今回のPrompt v5 Gateでは、少なくともこのWorkloadを理由にPrompt v5を開始する必要はないと判断する。

## 11. Overall product assessment

### What worked

- 120 Utteranceを最後までReplayできた。
- 6 Topicを形成し、Topic Returnで重複Topicを作らなかった。
- Current TopicとRecent Flowが連続Discussionで更新された。
- Candidate / Confirmed / RevokedのDecision Safetyは維持された。
- Type D ONでもFalse Candidate、Duplicate Candidate、Automatic Confirmationは0だった。
- Type D OFF / ONのFinal Graphは完全一致し、Deterministic Replayを維持した。
- M5.1 Compact Overviewにより、6 TopicとParkingの存在をProjection上把握できた。

### What did not yet work

- 30分後は90 Node、13 Open Item、85 Relationとなり、Card詳細の同時可読性が不足した。
- Type D Proposal Lookupは候補過多で、4件の新規Type D Candidateを追加できなかった。
- Actionらしい4件のRaw OutputがRelation参照不整合でCanonical化されず、Action completenessに課題が残った。
- 30分相当の物理Browser / 1920×1080 Screenshotによる離読性は未確認である。

## 12. Decisions

| Decision | Result | Reason |
| --- | --- | --- |
| Type D | **Defer** | 安全だが、この密度のGraphでは追加Candidate 0件。Proposal selection改善なしにMVPへ入れても価値が出ない。 |
| Prompt v5 | **Can wait** | このWorkloadのType A-like Strong Decision Missは0件。主な問題はPrompt緩和よりMap density / Proposal selection / Action conversion。 |
| Recorded Analyzer | **Not ready** for the next gate | 120 callの構造面は安定したが、30分後の密度とAction欠落がMVP品質の残課題。 |
| STT | **Not ready for Recorded STT Spike** | Recorded Analyzerの長時間Map品質とAction conversionを先に改善・再評価する必要がある。 |

### Recommended next evaluation work

実装・Prompt v5・STTへ直ちに進まず、次の順で評価課題を解く。

1. Proposalに「Strong Proposal」の意味属性を持たせる、または既存Topic内の候補選択を改善し、Type Dの4件をOfflineで再評価する。
2. Action Eventと`contains` Relationの新規Node参照を分離して、明示的Actionの欠落を測る。
3. Resolved / low-priority NodeとOpen Itemを折りたたむProjectionを30分Snapshotで再評価する。
4. その後、同じ30分Transcriptを再Replayし、Prompt v5が本当に必要か再判断する。

Canonical Contract、Schema、Materializer、Stable Discussion Mapの意味構造は変更していない。
