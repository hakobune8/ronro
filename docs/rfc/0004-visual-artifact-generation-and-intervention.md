# RFC-0004: Visual Artifact Generation and Intervention

| 項目 | 内容 |
| --- | --- |
| Status | Proposed |
| Target | Discussion Map AI Facilitator MVP |
| Related RD | [Discussion Map AI Facilitator MVP 要件定義書](../requirements/discussion-map-ai-facilitator-mvp.md) |
| Depends on | RFC-0001: Discussion Model / Discussion Graph Architecture |
| Depends on | RFC-0002: Realtime Discussion Analysis Pipeline |
| Depends on | RFC-0003: Discussion Map UX and Layout |
| Last Updated | 2026-09-19 |

本RFCは、Discussion MapとDiscussion Contextをもとに、議論を具体化するVisual Artifactを生成し、会議中へ自然に介入させる設計を定義する。

本RFCは実装を開始するものではない。MVPにおけるArtifactの責務、Context選択、Trigger、非同期処理、表示、Version、Privacy、Cost Control、Validationを整理する。

## 1. Problem Statement

### 1.1 Visual Artifactの役割

Discussion Mapは、会議中のDiscussionの構造と状態を共有するPrimary Artifactである。

一方、次のような内容は、Map上のNodeとRelationだけでは参加者間でイメージを揃えにくい。

- 抽象的なサービスコンセプト
- システム構成
- UIとユーザー体験
- 空間やデバイスの配置
- 複数案の具体的な違い

Visual Artifactは、これらを一時的に具体化するDiscussion Aidである。

### 1.2 Visualを主役にしない理由

生成されたVisualが画面の中心になると、次のリスクがある。

- 参加者がVisualを結論や正解と誤認する
- 生成された見た目に議論が引っ張られる
- MapのCurrent Stateや未決事項が見えなくなる
- 生成待ちでDiscussionが止まる
- 生成物が増えすぎてGalleryになる
- VisualのVersionやPromptの違いが履歴を複雑にする

したがって、Visual ArtifactはMapから参照され、必要なときだけ開かれ、Discussionが続く間に更新可能な仮説として扱う。

### 1.3 設計上の中心問題

本RFCでは、次を設計する。

- どのDiscussion ContextをVisual化するか
- どのようなTriggerで生成するか
- Concept ImageとDiagramを同じPipelineで扱うか
- 生成中もDiscussionを継続する方法
- 生成Request時点のContextをどう固定するか
- ArtifactのVersionとRevisionをどう扱うか
- ArtifactをGraphとResourceのどちらに置くか
- Map上のMarkerとVisual Viewをどう設計するか
- Anchoring、Hallucination、Privacy、Costをどう抑えるか

## 2. Goals / Non-goals

### 2.1 Goals

このRFCで決めることは次のとおりである。

- Visual ArtifactのProduct Role
- MVPで扱うVisual Use CaseとType
- Generation Triggerの比較と推奨Policy
- Visual Contextの選択・確認・編集
- Prompt構成の責務分離
- Diagram RendererとImage Generatorの関係
- 非同期生成とDiscussion Continuity
- Context Snapshot、Version、Revision、Adoptionの考え方
- Discussion Graphとの関係とArtifact Marker
- Visual View、Map + Visual Viewの方式
- CandidateのLabel、Anchoring対策、Variant方針
- Failure、Latency、Automatic Screen Switching
- Voice Intent、Cost Control、Provider Abstraction
- Storage、Privacy、Validation、Success Metrics

### 2.2 Non-goals

以下はこのRFCでは詳細を決めない。

- 特定のImage Generation Provider
- 特定のDiagram LibraryやRenderer
- LLMやImage ModelのPrompt本文
- 画像品質の最終評価基準
- Visual Artifactの長期資産管理
- Design SystemやFrontend Framework
- 組織・ユーザー権限管理
- 大規模なAsset Library
- Mobile UI
- Meeting Minutesの本文構成
- Security Architectureや法務上の最終判断

MinutesにArtifactをどのように引用・要約するかはRFC-0005へDeferredする。

## 3. 既存RFCから維持する前提

### 3.1 RFC-0001との整合

次を維持する。

> Transcript = Evidence  
> Event Stream = History  
> Discussion Graph = Current StateのMaterialized View

Visual Artifactは、Discussion Modelと関係を持つ独立ResourceまたはそのReferenceとして扱う。

Artifactの実体をDiscussion Graphの通常Nodeとして増やし続けない。

### 3.2 RFC-0002との整合

- Visual生成中もSTT、Discussion Analysis、Event Stream、Discussion Mapを継続する
- Artifact生成はRealtime Discussion PipelineをBlockingしない
- Final Transcriptを基準に更新されたDiscussion StateをContextの根拠にする
- Partial TranscriptをVisual Contextの確定根拠にしない
- 生成失敗時もTranscriptとCurrent Graphを失わない

### 3.3 RFC-0003との整合

- Discussion MapがPrimary Viewである
- VisualはMapから遷移して確認する
- Mapへ容易に戻る
- Artifact MarkerをMapへ表示する
- Visualが議論を誘導しすぎない
- Map更新中もVisual表示を理由に全体再配置しない

### 3.4 Change Proposal

既存RFCの決定を変更する必要はない。

本RFCでは、RFC-0003でDeferredされたArtifact Markerの詳細Interactionと、MapからVisualへ遷移する境界を具体化する。ただし、Visual Artifactを独立Resourceとして保持し、MapにはReference / Markerを置くというRFC-0001の方針は維持する。

## 4. Product Principle

### 4.1 Visualは答えではなく仮説

Visual Artifactは、次の性格を持つ。

- Draft
- Concept
- Interpretation
- Discussion Aid
- Disposable
- Revisable

Visualは、「AIが正しい姿を示した」ものではない。

### 4.2 UI上の言葉

MVPでは、Visual ViewやArtifact Cardに次のようなLabelを使う。

- Discussion Visual
- AI Concept Draft
- Discussion Aid
- Generated from current discussion

避ける表現:

- 正解
- 最終案
- 推奨デザイン
- 決定済みの画面

### 4.3 Decisionとの分離

Visual Artifactが生成されたこと、参加者がVisualを見たこと、Visualが気に入られたことは、Decisionとは別である。

- Artifactを自動的にDecisionへ接続しない
- Artifactの存在だけでOptionをConfirmedにしない
- Visual ViewにDecisionの確定操作を置かない
- Confirmed Decisionから生成されたVisualであっても、Visual自体はDiscussion Aidとして表示する

## 5. Primary Use Cases

### 5.1 UC-01 Concept Visualization

抽象的なサービスアイデアや体験をイメージ化する。

例:

> Discussion Mapを使ったAI会議支援サービス

から、参加者が同じ方向を想像するためのConcept Imageを生成する。

#### 価値

- 言葉だけでは共有しにくい概念を具体化できる
- 参加者間の認識差を発見できる
- 別案を考えるきっかけになる

#### リスク

- 画像の具体性が高すぎて、特定のデザインへAnchoringする
- 見た目の品質がDiscussionの価値と誤認される

### 5.2 UC-02 Architecture Sketch

STT、Discussion Analysis、Discussion Mapなどの構成をDiagramとして表現する。

例:

~~~text
STT
 ↓
Discussion Analysis
 ↓
Discussion Graph
 ↓
Discussion Map
~~~

#### 価値

- 構成要素と関係を説明しやすい
- 参加者が同じ構造を参照できる
- Concept Imageよりも検証可能な形に近い

#### リスク

- 生成されたDiagramが正式Architectureと誤認される
- Graph上のCandidateを確定構成として描く

### 5.3 UC-03 UX / Interaction Visualization

Discussion Map、Visual View、Mapへの戻りなどのユーザー体験を表現する。

#### 価値

- 画面遷移と体験を共有できる
- 抽象的なUX議論を具体化できる

#### リスク

- Wireframeが細かすぎると、早い段階でUIを固定する
- RFC-0003のMap UXと競合する

### 5.4 UC-04 Spatial / Physical Layout

会議室、店舗、イベント空間、デバイス配置などを表現する。

#### 価値

- 空間関係を言葉より共有しやすい
- 参加者間の想像の違いを確認できる

#### リスク

- 実寸、制約、測定根拠がない画像を正確な配置と誤認する
- 画像生成の自由度が高く、現実制約を落としやすい

### 5.5 UC-05 Comparison

複数案を視覚的に比較する。

例:

~~~text
A案: Map中心
vs
B案: Map + Visual
~~~

#### 価値

- Option間の違いを比較しやすい
- Decision前のDiscussionを具体化できる

#### リスク

- 一つの画像が優れて見えるだけで、選択が誘導される
- 複数生成で待ち時間とCostが増える

### 5.6 MVPの推奨開始範囲

MVPでは、次の2種類から始めることを推奨する。

1. Concept Image
2. Diagram

Diagramは内部的なIntentとしてArchitecture、Flow、簡易UXを含む。細かいArtifact Typeを最初から別々にしない。

理由:

- Concept Imageは抽象的なDiscussionの認識合わせを検証できる
- Diagramは構造化されたDiscussionの理解を検証できる
- 生成方式の違う2種類を比較できる
- Spatial、Comparison、Storyboardは後から追加しやすい

## 6. Artifact Types

### 6.1 Typeを細かくしすぎない

Artifact Typeを増やすと、Prompt、Renderer、UI、EvaluationがTypeごとに分岐する。

MVPでは、意味上の目的と生成方式を分ける。

### 6.2 推奨する最小Type

| MVP Type | 対応候補 | 生成方式 | 例 |
| --- | --- | --- | --- |
| concept_image | Concept Image、Spatial Image、Storyboardの初期版 | Generative Image | サービスの利用イメージ |
| diagram | Architecture Diagram、Flow Diagram、簡易Wireframe | DeterministicまたはStructured Renderer | STTからMapまでの構成 |

### 6.3 将来のType

以下はMVP後の候補とする。

- comparison_visual
- spatial_layout
- storyboard
- 高精度wireframe

MVPで必要になった場合も、まずconcept_imageまたはdiagramのIntentとして表現できるかを確認する。

### 6.4 TypeとRenderer

Typeは「何を共有したいか」を表し、Rendererは「どう生成するか」を表す。

例えば、diagramというTypeでも、Architecture、Flow、簡易UXのRenderer Intentが異なる可能性がある。

この差を初期から別Typeへ分裂させない。

## 7. Generation Trigger Alternatives

### 7.1 Manual Trigger

ユーザーがMap上のActionから明示的にGenerate Visualを実行する。

#### Discussionへの干渉

低い。生成の意図とタイミングを参加者が決められる。

#### 誤生成リスク

比較的低い。ただしContextの選択を誤る可能性はある。

#### UX

理解しやすく、生成開始の責任が明確。

#### 実装複雑性

低い。

#### MVP適性

高い。

### 7.2 Voice Intent

「これを図にしてみて」などの発話から生成意図を検出する。

#### Discussionへの干渉

低〜中。会話の自然さを保てるが、対象とTypeが曖昧になりやすい。

#### 誤生成リスク

中〜高。単なる例示や質問をGenerate requestと誤認する可能性がある。

#### UX

自然だが、対象を確認するUIが必要になる。

#### 実装複雑性

中〜高。Intent検出、対象選択、Confirmationが必要。

#### MVP適性

明示Confirmation付きの限定採用なら中。無確認での採用は低い。

### 7.3 AI Suggestion

AIが「この内容をVisual化できます」と提案するが、生成はユーザーが開始する。

#### Discussionへの干渉

中。提案頻度が高いとAIがDiscussionを誘導する。

#### 誤生成リスク

低〜中。生成しないが、不要な操作を増やす。

#### UX

アイデアを知らない参加者に入口を提供できる。

#### 実装複雑性

中。SuggestionのPriority、Cooldown、Dismissが必要。

#### MVP適性

Manualの検証後に限定的に導入する候補。

### 7.4 Automatic Generation

AIが判断してVisualを生成し、必要なら表示する。

#### Discussionへの干渉

高。生成待ち、通知、画面切替が会議を中断しやすい。

#### 誤生成リスク

高。抽象的な発言を過度に具体化する。

#### UX

うまく動けば魔法のようだが、失敗時の説明が難しい。

#### 実装複雑性

高。Trigger、Context、Cost、Cooldown、Safety、表示Policyが必要。

#### MVP適性

低い。

## 8. Recommended Trigger Policy

### 8.1 MVPの順序

MVPでは次の順序でControlを弱める。

1. Manual Trigger
2. Voice Intent with Confirmation
3. AI Suggestion
4. Automatic Generation

### 8.2 Manual Triggerを基本とする理由

- Discussionの主導権を参加者に残せる
- Context選択を意識的に行える
- Costと生成回数を制御しやすい
- Anchoring発生時に原因を追いやすい
- Static Prototypeで検証しやすい

### 8.3 Voice Intentの扱い

MVPの必須Triggerにはしない。

将来、Voice Intentを入れる場合も、曖昧な対象では短いConfirmationを出す。

例:

> 「今話しているDiscussion Map UIをDiagram化しますか？」

確認なしで生成Requestへ進める条件は定めない。

### 8.4 AI Suggestion

MVPの初期検証では、AI Suggestionを常時出さない。

将来の実験で導入する場合:

- Suggestionのみで生成しない
- Dismiss可能
- 同一TopicのCooldown
- Observationと同時に大量表示しない

### 8.5 Automatic Generation

MVPでは採用しない。

## 9. Artifact Context

### 9.1 Transcript全文を渡さない

Visual生成にTranscript全文を渡すと、次の問題が起こる。

- 生成対象と無関係な発言が混ざる
- Speakerや個人情報を不要に送信する
- 古いDiscussionや撤回済み情報が混ざる
- Promptが長くなり、生成結果の意図が曖昧になる
- Context Snapshotを説明しにくい

### 9.2 Contextの候補

Visual生成時に候補となる情報は次のとおりである。

- Meeting Goal
- Current Topic
- Relevant Topic
- Connected Ideas
- Options
- Confirmed Decisions
- Candidate Decisions
- Concerns
- Open Questions
- Recent Discussion Events
- Existing Artifact

### 9.3 推奨するContext

MVPでは次を基本Contextとする。

1. Meeting Goal
2. Current Topic
3. Visualize対象のRelevant Topic
4. Connected Ideas / Options / Concerns
5. 関連するConfirmed Decision
6. Candidate Decisionは「未確定」と明示して任意で含める
7. RelevantなOpen Question
8. 最近のDiscussion Eventの要約
9. Existing ArtifactのReferenceまたはRevision対象

### 9.4 含めない情報

- Discussion全体のTranscript
- 無関係なTopic
- Speaker名、Speaker評価、発言量
- 撤回済みDecisionを現在のConstraintとして扱うこと
- Partial Transcript
- 根拠のない推測

## 10. Context Selection

### 10.1 Discussion Subgraph

Visual生成時は、Current Graph全体ではなく、Visual化対象となるDiscussion Subgraphを抽出する。

~~~text
Current Graph
    ↓
Selected Topic / Intent
    ↓
Connected Ideas / Options / Concerns
    ↓
Relevant Decisions / Open Questions
    ↓
Context Snapshot
~~~

### 10.2 Subgraph選択の優先順位

1. ユーザーが選択したTopicまたはNode
2. Current Topic
3. 直接のcontains、supports、opposes、has_option、depends_on
4. Related Evidenceの要約
5. 直近のTopic transition
6. Existing ArtifactのRevision関係

Flowの全履歴や無関係なParking Lotは原則含めない。

### 10.3 例

Current Topic:

> Discussion Map UI

Relevant Context:

- 16:9 Display
- Map中心
- Status Rail
- Recent Flow
- Visual Viewへ切替
- Smartphoneなし

このContextから、Discussion Map UIのConcept Imageまたは簡易UX Diagramを生成する。

### 10.4 生成前のContext確認

Context選択をAIだけに任せると、参加者が意図しないTopicや古いDecisionが入る可能性がある。

#### 案A: Contextを自動選択し、確認なしで生成

速いが、誤ContextとPrivacy漏れのリスクが高い。

#### 案B: Context Previewを表示して確認

制御しやすいが、操作が一つ増える。

#### 案C: UserがNodeを選び、AIが周辺Contextを補完

意図と速度のバランスがよい。

### 10.5 推奨

MVPでは案Cを推奨する。

- UserがMap上のTopic、Idea、Optionを選ぶ
- Systemが直接関係するContextを短くPreviewする
- Userは不要なItemを外せる
- 確認後にGenerateする

Previewを毎回大きなModalにしない。小さなContext chipまたは確認Panelにする。

## 11. Artifact Prompt Construction

### 11.1 Promptの責務を分ける

Providerへ渡す入力は、次の部分に分ける。

1. Discussion Context
2. Visual Objective
3. Visual Type
4. Constraints
5. Interpretation / Creative Freedom

### 11.2 Discussion Context

事実として選択されたDiscussion Subgraphの要約。

例:

- Goal: 会議中に議論の状態を共有する
- Topic: Discussion Map UI
- Connected Ideas: Map中心、Status Rail、Recent Flow
- Constraint decisions: Smartphone UIはMVP対象外

### 11.3 Visual Objective

何を共有するために生成するかを明示する。

例:

> 参加者間でDiscussion Map UIの全体イメージを共有する

Objectiveは「最終デザインを決める」ではなく、「議論の素材を作る」とする。

### 11.4 Visual Type

MVPでは次を明示する。

- concept_image
- diagram

Diagramの場合は、architecture、flow、uxなどのIntentを補助情報として扱う。

### 11.5 Constraints

Discussionから確定または明示された制約を列挙する。

例:

- 16:9
- shared display
- map-centered
- no smartphone UI
- status rail
- recent flow

Candidate DecisionはConfirmed Constraintと同じ強さで送らない。

### 11.6 Interpretation / Creative Freedom

生成モデルが補う範囲を明示する。

例:

- layout details are exploratory
- visual style is a draft
- do not imply a final decision
- show alternative interpretations when requested

これにより、生成物が正式仕様に見えることを抑える。

### 11.7 Prompt保存

Promptの扱いを比較する。

#### 保存しない

Privacyに有利だが、再現性とDebugが弱い。

#### 正規化したPrompt構造だけ保存

Context、Objective、Type、Constraintsを保存し、Provider向けの最終文字列は保存しない。

#### 最終Promptも保存

再現性が高いが、Speaker名や機密情報が含まれる可能性がある。

MVPでは、正規化されたPrompt構造とContext Snapshotを保存する。最終Prompt全文やRaw Provider Responseは、Privacy方針が定まるまで必須にしない。

## 12. Diagram vs Image Generation

### 12.1 Deterministic Diagram

対象:

- Architecture Diagram
- Flow Diagram
- Wireframe

特徴:

- Node、Label、Relationを構造化しやすい
- 同じContextから比較的再現性のある結果を作れる
- 誤ったRelationやLabelの検証が必要
- 見た目より構造の正確性が重要

### 12.2 Generative Image

対象:

- Concept Image
- Spatial Image
- Mood / Scene

特徴:

- 抽象的なイメージを共有しやすい
- 解釈の幅が大きい
- Anchoringが強くなりやすい
- 構造や寸法の正確性を保証しにくい

### 12.3 一つのPipelineで扱う案

Discussion Contextから一つのGeneric Visual Requestを作り、Providerだけを切り替える。

#### 長所

- Trigger、Context Snapshot、Status、Storageを共通化できる
- UXの入口を一つにできる

#### 短所

- Diagramの構造検証とImageのSafety・Anchoringが混ざる
- Provider Capabilityが複雑になる

### 12.4 別Rendererとして扱う案

~~~text
Discussion Context
        ↓
Visual Intent
        ↓
Artifact Renderer
   ├─ Diagram Renderer
   └─ Image Generator
~~~

#### 長所

- ContextとArtifact Lifecycleを共有できる
- Rendererごとの品質・Failure・Validationを分離できる
- DiagramとImageの異なる意味を保てる

#### 短所

- Adapter境界が一つ増える
- RendererごとのCapability管理が必要

### 12.5 推奨

Artifact Request、Context Snapshot、Status、Version、Markerは共通化し、生成部分はDiagram RendererとImage Generatorの別Capabilityとして扱う。

MVPの初期Typeはconcept_imageとdiagramの2つに限定する。

## 13. Discussion Continuity

### 13.1 生成状態と議論状態の分離

Artifactの生成状態は、Discussion Graph上のNode状態やArtifactの採用状態とは分離する。

| Generation State | 意味 |
| --- | --- |
| queued | 生成要求を受け付け、処理待ち |
| generating | RendererまたはGeneratorが処理中 |
| ready | 表示可能なArtifactが存在する |
| failed | 生成に失敗した。MapとDiscussionは継続可能 |

この状態はEvent StreamにおけるArtifact関連EventまたはArtifact Resourceの状態として保持する。生成中であることを理由に、Discussion Graphの更新を停止しない。

### 13.2 生成中にDiscussion Stateが変わる場合

生成要求後も、STT、Final Utterance、Discussion Analysis、Event Stream、Graph Materializerは通常どおり動作する。そのため、Artifactが完成した時点のGraphは、要求時点のGraphと異なる可能性がある。

この差異はエラーではなく、Artifactが過去のContextに基づくDiscussion Aidであることの一部である。Artifactには要求時点のContext Snapshotを紐付け、完成時に最新Graphへ暗黙に書き換えない。

Visual Viewでは、必要に応じて次のように控えめに示す。

> Generated from: 「Discussion Map UI」 / request時点のDiscussion Context

「古いから無効」と断定するのではなく、参加者が現在の議論との差分を自分で判断できる情報として扱う。

### 13.3 推奨方針

生成は常に非同期とし、生成中もMapをPrimary Viewとして利用できる状態を保つ。生成完了時は通知またはMarkerの更新だけを行い、画面を自動的に奪わない。

## 14. Context Snapshot

### 14.1 Snapshotの必要性

Artifactの生成元を後から説明・再現できるように、Generate要求時点で入力Contextを不変のSnapshotとして保存する。

最低限、次の関係を保持する。

~~~text
Artifact A
  ├─ generated_from → Discussion Session
  ├─ source_revision → Graph / Discussion Revision 145
  ├─ source_topic → Topic: Discussion Map UI
  └─ context_snapshot → 選択されたSubgraphと生成条件
~~~

Snapshotがない場合、同じDiscussionから再生成しても対象Topic、Decision、Constraintが変わってしまい、Artifactの説明・比較・Replayが困難になる。

### 14.2 Snapshotに含める候補

| 項目 | MVPでの扱い |
| --- | --- |
| Session ID / Graph Revision | 必須 |
| Source Topic ID | 必須 |
| Current Topic | 可能なら含める。Source Topicと一致しない場合は明示 |
| Relevant Subgraph | 必須 |
| Confirmed Decision | 参照されたものだけ含める |
| Candidate Decision | candidateであることを保持して含める |
| Option / Concern / Open Question | 対象Subgraphに含まれるものだけ |
| Recent Events | Contextを説明する短い要約として必要最小限 |
| Transcript全文 | 含めない |
| Speaker名 | 原則含めない |
| Objective / Constraints | 必須 |
| Existing Artifact | Revision時だけ参照 |

CandidateをConfirmedのようにSnapshotへ保存してはならない。Visual生成用の入力でも、確度・状態を失わない。

### 14.3 Snapshotの編集

生成前のContext Previewで、ユーザーが対象Topicや含める要素を確認・除外できる案を比較する。

| 方式 | 利点 | 欠点 |
| --- | --- | --- |
| AIが自動選択 | 速い。操作が少ない | 意図しないTopicを含めやすい |
| 常に詳細編集 | 制御しやすい | 会議の流れを止める |
| Summary Preview + 任意編集 | 速さと制御のバランス | Preview UIが必要 |

MVPでは、デフォルトで短いSummary Previewを表示し、必要時だけ対象Topic、Options、Constraintsを編集できる方式を推奨する。Previewを確認せず即時生成する設定は将来の高速操作として残す。

## 15. Artifact Versioning

### 15.1 方式比較

| 方式 | 利点 | 欠点 | MVP適性 |
| --- | --- | --- | --- |
| Replacement | UIとStorageが単純 | 以前の案、Context、差分が失われる | 低い |
| Version Chain | 変更理由と元Artifactを追跡できる | 一覧表示が少し複雑 | 高い |
| Independent Artifact | 案を自由に並べられる | 改訂と別案の区別が難しい | 中 |
| Branch | 探索的な比較に強い | 状態・UI・操作が複雑 | 低い |

### 15.2 推奨Versionモデル

MVPではArtifact Familyごとの線形Version Chainを採用する。

~~~text
Artifact A v1
    └─ revised_from → Artifact A v2
                              └─ revised_from → Artifact A v3
~~~

各Versionは独自のContext Snapshotと生成状態を持つ。以前のVersionは削除せず、通常Viewでは折りたたむ。最新版にはcurrent、以前のVersionにはsuperseded相当の表示を付ける。

次のルールを置く。

* 同じ目的・同じArtifact Familyの修正は新Versionとする
* 新しい目的、別Topic、別の比較対象は新しいArtifact Familyとする
* MVPではVersion ChainのBranchを作らない
* Version番号だけで「正解度」や「正式度」を表現しない
* Versionの生成元Snapshotは後から変更しない

Replacementは、ユーザーが「この案を置き換えて見せたい」と明示した場合の表示上のショートカットとしては検討できるが、内部履歴を消す方式としては採用しない。

## 16. Artifact Revision

ユーザーが「この部分だけ変えて」「共有ディスプレイを大きくして」と指示した場合、既存Artifactを直接上書きせず、同じArtifact Familyの新Versionを生成する。

Revision Requestには次を含める。

* revised_from: 元Artifact ID
* 変更指示
* 元VersionのContext Snapshot
* 追加・変更されたConstraint
* 新しいContext SnapshotのGraph Revision

Providerが画像の部分編集に対応していなくても、MVPでは元ArtifactのContextと変更指示から再生成する方式で成立させる。部分編集能力を必須Capabilityにすると、Provider依存とFailure Modeが増えるためである。

## 17. Artifact Adoption

### 17.1 生成状態とDiscussion上の意味

Artifactの生成に成功したことと、参加者がそのArtifactを議論に役立つと感じたこと、正式な設計として採用したことは異なる。

MVPでは、次を別概念として扱う。

* Generation State: queued / generating / ready / failed
* Visibility: Mapから参照可能か
* Discussion Status: draft / superseded / rejected の最小集合

reviewed、useful、adoptedを必須状態にすると、会議中に評価操作を要求し、ArtifactをDecisionと誤認させる可能性がある。MVPではArtifactを常にDiscussion Aidとして扱い、adoptedは正式な設計採用を意味しない。

### 17.2 推奨方針

新しいArtifactはdraftから始める。新Version生成時に旧Versionをsupersededとして表示できる。ユーザーが不要と判断した場合はrejectedまたは非表示にできるが、その操作は元のDiscussion Decisionを変更しない。

将来、Artifactを正式成果物として扱う場合は、Artifact採用とDecision確認を結ぶ別RFCが必要である。

## 18. ArtifactとDiscussion Graphの関係

### 18.1 選択肢

| 案 | 内容 | 長所 | 短所 |
| --- | --- | --- | --- |
| A: ArtifactをNodeにする | TopicやIdeaと同じGraph Nodeとして扱う | Map上で関係を表しやすい | Graphが視覚資産の管理で膨らむ。VersionもNode化しやすい |
| B: 独立Resourceにする | Artifactを独立Resourceとして保持し、Graphから参照する | Version、Storage、Privacyの責務を分離できる | Mapに参照表示の設計が必要 |
| C: Markerのみ置く | Graphには小さなMarkerだけを置き、実体は別管理 | Mapが最も簡潔 | 関係・検索・履歴が弱くなりやすい |

### 18.2 推奨案

ArtifactはBの独立Resourceとして扱い、CのMarkerをDiscussion Mapの表示モデルとして用いる。

Graph上にはArtifactの実体やPromptを通常Nodeとして混在させず、対象Topicや関連IdeaからArtifact Resourceへの参照を持つ。Event Streamには生成要求、生成完了、Revision、非表示などの履歴を記録する。

概念的には次のようになる。

~~~text
Discussion Graph
  Topic: Discussion Map UI
      └─ artifact_marker → Artifact A v2

Artifact Resource
  Artifact A v2
      ├─ generated_from → Graph Revision 145
      ├─ source_topic → Topic: Discussion Map UI
      ├─ revised_from → Artifact A v1
      └─ asset → image / diagram
~~~

この分離により、Mapの安定性を保ちながら、ArtifactのVersionとEvidence関係を保持できる。

## 19. Artifact Marker

### 19.1 目的

Markerの目的は「このTopicには参照できるVisualがある」と知らせることであり、Visual GalleryをMap内に作ることではない。

### 19.2 表示案

候補を比較する。

* Topic内に小さなPaperclip / Image Iconと件数を表示
* Status RailにArtifact一覧を表示
* Map上にサムネイルを常時表示

サムネイル常時表示は視覚的な重みと情報量が大きく、MapをVisual中心に変えてしまう。MVPでは、Topic Cardの端にアイコン、短いLabel、必要なら件数を表示し、Status RailまたはクリックでArtifact一覧を開く。

~~~text
┌──────────────────────────────┐
│ Topic: Discussion Map UI  📎 2 │
│ Map中心 / 16:9 / Status Rail   │
└──────────────────────────────┘
~~~

生成中は小さなProgressまたはGenerating表示、失敗時は再試行可能な状態を示す。Version数や過去Artifactの一覧を常時表示しない。

### 19.3 Interaction

Markerを選ぶとArtifactのSummaryまたはArtifact Viewを開く。Marker選択だけで生成済みVisualへ自動切替するかは、ユーザーが明示的に選択できるようにする。

## 20. Visual View

### 20.1 画面の責務

Visual ViewはArtifactを大きく見せ、Discussion Mapとの関係を保ちながら短時間確認するための画面である。Artifactを正式な設計承認画面やDecision画面にしない。

最低限、次を表示する。

* ArtifactのTitleまたは短い目的
* Type
* AI Concept DraftまたはDiscussion VisualのLabel
* Source Topic
* Generated fromの時点またはRevision
* Back to Map
* 必要時のRevise / Regenerate

Contextの全文、Transcript全文、Providerの内部情報は通常画面に出さない。必要なら「Contextを表示」からSummaryを開く。

### 20.2 16:9での表示

共有ディスプレイではVisual本体を中央に大きく置き、上下または右上に短いContext Headerを配置する。画像やDiagramを無理に画面全体へ引き伸ばさず、アスペクト比を保持する。

Back to Mapは常時見える位置に置く。Revise、Regenerate、Version一覧は主操作を奪わない二次操作領域に置く。

## 21. Map + Visual View

### 21.1 表示方式比較

| 方式 | 利点 | 欠点 | MVP適性 |
| --- | --- | --- | --- |
| Full Visual | Visualを共有しやすい。理解に集中できる | 全体Mapを一時的に見失う | 高い |
| Split View | MapとVisualの関係を同時に見られる | どちらも小さくなり、共有距離で読みにくい | 条件付き |
| Overlay | Mapを残したまま大きく見せられる | 背景との競合、操作が複雑 | 低い |
| Side Panel | Mapを維持しやすい | Visualの面積が限られる | 中 |

### 21.2 推奨

MVPの既定表示は、Context Header付きのFull Visual Viewとする。Map全体を常時縮小して同時表示することは、16:9共有ディスプレイ上では情報密度を上げやすい。

Split Viewは、DiagramをMapと比較する明確なユースケースがある場合の明示的な補助表示としてPrototypeで検証する。完成時に自動でSplit Viewへ切り替えない。通常はFull VisualからBack to Mapで戻る。

## 22. Generated Visual Labeling

Artifactの上部または隅に、短く一貫したLabelを表示する。

推奨例:

* AI Concept Draft
* Discussion Visual
* Draft · Generated from: Discussion Map UI

Labelは警告文で画面を埋めるのではなく、Visualが「解答」や「Confirmed Decision」ではないことを自然に示す。Confirmed Decisionや正式なAction Itemと同じCheckmark、Solid Decision Badge、確定色を使用しない。

## 23. Bias / Anchoring Risk

### 23.1 リスク

具体的で完成度の高いVisualは、参加者が意識せずにその色、構成、製品イメージを前提にしてしまう。特にConcept ImageやSpatial Imageは、意見の一例を「あるべき姿」に見せやすい。

### 23.2 MVPでの対策

次の対策を必須または推奨とする。

* ArtifactをDraft / Discussion Visualとして表示する
* Source Topicと生成Objectiveを表示する
* Candidate DecisionをConfirmed DecisionとしてPromptに変換しない
* Visual生成時にDecisionへ自動接続しない
* 生成完了時に自動表示しない
* Visual ViewからMapへ一操作で戻れるようにする
* ユーザーが目的を変更して再生成できるようにする

複数VariantはAnchoringを軽減し得るが、待ち時間・Cost・認知負荷を増やす。MVPでは自動複数生成を行わず、別案が必要な場合に参加者が明示的に再生成を要求する。

## 24. Single vs Multiple Variants

| 方式 | 利点 | 欠点 |
| --- | --- | --- |
| Single | 待ち時間、Cost、比較負荷が小さい | 最初の案へのAnchoringが強くなり得る |
| Multiple | 一つの案を正解と誤認しにくい | 生成時間・Cost・画面情報量が増える |

MVPはSingleを既定とする。生成前に「比較用の別案」を明示した場合だけ、複数生成を将来拡張として検討する。複数案を実装する場合も、同じContextの単なるバリエーションか、異なるOptionごとの比較かをUI上で区別する必要がある。

## 25. Failure UX

Visual生成の失敗はDiscussion Mapの失敗ではない。失敗時もMap、STT、Discussion Analysis、Event Streamを継続する。

| 状態 | 表示・操作 |
| --- | --- |
| Generation Failed | 理由を過度に技術化せず、再試行、Contextを編集、Mapへ戻るを提供 |
| Timeout | 生成に時間がかかっていることを示す。再送ではなく状態確認または再試行 |
| Unsupported / Unsafe | 生成できない旨と、Contextまたは目的を変更する案を提示 |
| Empty Context | 対象Topicや目的の入力を求め、空の画像を生成しない |
| Low Confidence Context | 自動生成せず、Context Previewで確認を求める |

エラー表示はStatus Railまたは通知に置き、Map中央を置き換えない。失敗したRequestのContext Snapshotと理由は、Replay・Evaluationに必要な範囲で保持する。

## 26. Generation LatencyとAutomatic Screen Switching

### 26.1 Latency中のUX

Generationは秒単位から長時間まで変動し得るため、固定時間を前提に画面をロックしない。queued、generating、経過状態、Ready通知を用いて、参加者がDiscussionを継続できるようにする。

生成要求から完成までの間に新しい発言が追加されても、要求済みArtifactのSnapshotは変えない。新しい議論を反映したい場合は、明示的なRevisionまたは新規生成とする。

### 26.2 切替方式比較

| 方式 | 利点 | 欠点 | MVP適性 |
| --- | --- | --- | --- |
| Automatic Switch | Visualを見逃さない | 会話、視線、共有画面を突然奪う | 低い |
| Suggested Switch | 発見しやすく、主導権を保てる | 参加者が選択する必要がある | 高い |
| Manual Switch | 最も予測可能 | 完成に気付かない可能性 | 中 |

### 26.3 推奨

MVPはSuggested Switchを採用する。

~~~text
┌─────────────────────────────────────────┐
│ Visual ready: Discussion Map UI          │
│ [Visualを表示]  [後で]                    │
└─────────────────────────────────────────┘
~~~

通知が消えた後もTopic Markerから開ける。Visual完成時の自動切替、音声の自動読み上げ、Overlayの強制表示は採用しない。

## 27. Voice Interaction

### 27.1 位置付け

Voice Intentは、Manual Triggerを置き換える必須機能ではなく、将来の補助的な入力経路とする。MVPで採用する場合も、音声から直接生成を開始するのではなく、Generate Requestの候補を作るところまでに限定する。

例:

* 「この話を図にして」
* 「今の構成を絵にして」
* 「さっきの案を比較して」

### 27.2 対象が曖昧な場合

「この話」「さっきの案」が複数Topicに対応する場合、AIが黙って一つを選んで生成してはならない。次の順序で扱う。

1. Current Topicを第一候補にする
2. 関連Topicを最大数件の候補として提示する
3. 目的とTypeを短く確認する
4. ユーザーが確認した後にContext Snapshotを作成する

曖昧さが小さく、発話に明示的な対象と「生成して」という意図がある場合でも、既定ではReady通知までとし、画面切替は行わない。

### 27.3 MVP適性

Voice Intentは誤認識、話者重複、音声STTとの責務競合を増やす。MVPのPrimary TriggerはButtonまたは明示的な画面操作とし、Voice Intentの採否はRFC-0002のSTT能力とPrototype検証の結果で決める。

## 28. Cost Control

Visual生成は通常のDiscussion Analysisより高コストまたは高遅延になる可能性がある。MVPでは、次を最低限の制御とする。

* 自動生成を行わず、ユーザー起点のManual Triggerに限定する
* 同じSession、同じSource Topic、同じType、同じObjective、同じContext Revisionの重複Requestを検出する
* 同一の生成中Requestに対する再クリックで新しいJobを作らない
* 既存Artifactが目的とContextを満たす場合は、再利用またはVersion表示を優先する
* 失敗時の自動無限Retryを行わず、Retryはユーザー操作とする
* Revisionは明示的な変更指示を伴うユーザー操作に限定する
* セッション単位の生成回数制限または利用量の可視化を設定可能にする

生成回数の具体的な上限値は、Providerの費用とPoCでの利用パターンに依存するため本RFCでは固定しない。

## 29. Provider Abstraction

### 29.1 抽象化の範囲

MVPでは、特定ProviderのAPI仕様をDiscussion ModelやUIに直接露出させない。一方、将来のProvider交換を前提に大きな汎用フレームワークを作ることも避ける。

最低限、次の境界を置く。

~~~text
Artifact Request
  ├─ artifact type
  ├─ objective
  ├─ context snapshot
  ├─ constraints
  └─ revision instruction
          ↓
Renderer Adapter
  ├─ Diagram Renderer capability
  └─ Image Generator capability
          ↓
Artifact Result / Failure
~~~

Adapterの責務は、Provider固有のRequest、非同期Job、Status、Asset取得、Errorを共通Artifact Resultへ変換することとする。Provider固有のPromptやResponse全体をGraphへ持ち込まない。

### 29.2 DiagramとImageの境界

Diagramは構造と関係を再現する必要があるため、構造化データから決定的に描画できる方が誤解と再現性を抑えやすい。Imageは抽象概念や空間イメージの具体化に向くが、意味の正確さを保証しにくい。

したがって、共通のArtifact Lifecycleを使いながら、Renderer Capabilityは分ける。

* Diagram Renderer: Graph、Node、Edge、Layout、Labelなどを入力し、再現性を重視する
* Image Generator: Objective、Context、Constraints、Creative Freedomを入力し、Draft Imageを生成する

同じProviderに両方のCapabilityがあっても、内部では別Adapterとして扱う。これにより、Diagramの正確性要件とImageの解釈性を混同しない。

## 30. Provider Capability Requirements

### 30.1 MVPの最小要件

Concept ImageとDiagramの両方を必須にするのではなく、採用する初期Typeに対応するCapabilityだけを満たせばよい。

| Capability | 必須度 | 理由 |
| --- | --- | --- |
| Text-to-image | Concept Imageを採用する場合に必須 | 抽象イメージを生成する |
| Structured diagram rendering | Diagramを採用する場合に必須 | 構造を安定して表現する |
| 非同期Jobまたは生成中Status | 必須 | DiscussionをBlockしない |
| Assetの取得と安定した参照 | 必須 | Ready後に共有表示する |
| 16:9または指定Aspect Ratio | 推奨 | 共有ディスプレイに合わせる |
| 日本語Contextの処理、またはPrompt正規化 | 必須 | Japanese Firstに対応する |
| 明示的なFailure / Timeout | 必須 | Failure UXを成立させる |
| Image revision API | 不要 | MVPは再生成でRevisionを実現する |
| 複数Variantの一括生成 | 不要 | MVPはSingleを既定とする |
| Local Model対応 | 不要 | Provider境界の将来候補に留める |

Latency、品質、Costの具体的な閾値は、Prototypeと実Provider評価で決める。Capabilityがあっても、Discussion中に利用できる速度と安定性を満たさない場合はMVPの対象Typeから外すことがある。

## 31. Storage

### 31.1 Artifact Resourceに保持する項目

永続化技術は本RFCで決めず、Artifact Resourceとして最低限必要な情報を定義する。

| 項目 | 目的 |
| --- | --- |
| Artifact ID | 参照、Marker、Eventの識別 |
| Artifact Family ID / Version | Revision Chainの管理 |
| Type | concept_imageまたはdiagramなど |
| Generation State | queued / generating / ready / failed |
| Discussion Status | draft / superseded / rejected |
| Session ID | Discussionとの境界 |
| Source Graph Revision | Snapshotの基点 |
| Source Topic ID | Map上のMarker位置 |
| Context Snapshot | 生成元のSubgraphと状態 |
| Objective / Constraints | 何のためのVisualかを説明 |
| Prompt Structure | 再生成・Evaluation用の構造化入力 |
| Asset Reference | ImageまたはDiagramの取得先 |
| Created At / Updated At | 時系列と表示 |
| revised_from / supersedes | Version関係 |
| Failure Metadata | RetryとEvaluationに必要な最小情報 |

### 31.2 PromptとProvider Response

完成ArtifactのPrompt Structureは、再生成の再現性とEvaluationのために保存する価値がある。ただし、秘密情報や不要なTranscriptを含めない。

ProviderのRaw Response全体はMVPのDomain Modelに必須ではない。運用Debugに必要なProvider Job ID、Capability、Error Codeなどを別のProvider Metadataとして保持する案を推奨する。Raw Responseを保存するか、保存期間、アクセス制御はPrivacy・運用設計の後続課題とする。

## 32. Privacy

### 32.1 外部Providerへ送るContext

Visual生成時は、Discussion全体ではなくContext Snapshotに含まれる最小Subgraphだけを送る。

送信候補:

* Meeting Goal
* Source Topic
* 関連するIdea、Option、Concern
* 必要なConfirmed Decision
* Candidateであることが明示されたCandidate Decision
* ObjectiveとConstraints

原則として送信しないもの:

* Transcript全文
* 無関係なTopic、Parking Lot
* Speaker名、発言者ごとの評価情報
* Source Subgraphに含まれない会話
* Providerの処理に不要な内部識別子

### 32.2 User ControlとPrivacyの関係

Context Previewで送信内容のSummaryを確認できるようにする。必要ならSpeaker名や固有名詞を除外、置換する。Previewでの明示的な編集を毎回必須にするとDiscussionを止めるため、MVPでは自動最小化を基本とし、編集可能なPreviewを提供する。

外部ProviderへContextが送信される可能性があること、保存・削除の扱い、セッション終了後のRetentionは、製品のPrivacy PolicyとSecurity Architectureで確定する。本RFCでは、最小Context送信をMVPのDomain要件とする。

## 33. UX Alternatives

| 案 | 概要 | Discussion interruption | User control | Anchoring risk | Cost / Latency | MVP complexity | 評価 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A. Manual Artifact Tool | ユーザーが目的・Type・生成をすべて操作 | 低〜中 | 高 | 低〜中 | 予測しやすい | 低 | 安定するがContext選択を手作業に寄せる |
| B. Assisted Visualization | AIがContext候補とPreviewを作り、ユーザーが生成 | 低 | 高 | 中 | 制御しやすい | 中 | MVPに適する |
| C. Autonomous Visual Facilitator | AIが判断して生成・表示 | 高 | 低 | 高 | 不定、増えやすい | 高 | 将来探索。MVPには不適 |

推奨はBである。ただしTriggerはManualを起点とし、AIはSubgraph候補とContext Summaryを支援する。これにより、MVPの差別化であるContext-based Visualを残しながら、AIがDiscussionの主導権を取ることを避けられる。

## 34. Recommended MVP Experience

MVPでの一連の体験を次のように定義する。

~~~text
Discussion中
    ↓
Topicと関連Subgraphが十分形成される
    ↓
UserがTopicのGenerate Visualを選択
    ↓
Context PreviewでObjective / Type / Constraintsを確認
    ↓
Context Snapshotを保存
    ↓
Artifactがqueued / generatingになる
    ↓
STT / Analysis / Event Stream / Mapは継続
    ↓
Visualがreadyになり、通知とMarkerを更新
    ↓
UserがVisualを開く
    ↓
DraftとしてVisualを見ながらDiscussion
    ↓
必要ならRevise / Regenerate
    ↓
Back to Map
    ↓
その後の発言が通常どおりMapへ反映
~~~

Visualはこの流れの一時的な介入であり、Discussionの主画面を置き換える永続的なモードではない。

## 35. Wireframes

### 35.1 Generate Visual入口

~~~text
┌──────────────────────────────────────────────────────────────┐
│ Discussion Title                                  18:24       │
├──────────────────────────────────────────────┬───────────────┤
│ Current Topic: Discussion Map UI             │ Decisions     │
│                                              │ Open Issues   │
│  Topic card  📎 1                             │ Actions       │
│   ├─ 16:9 shared display                     │ Artifacts     │
│   └─ Map-centered                             │               │
│                                              │               │
│ [Generate Visual]                             │               │
├──────────────────────────────────────────────┴───────────────┤
│ AI Observation: Map中心のUI案が議論されています               │
└──────────────────────────────────────────────────────────────┘
~~~

### 35.2 Generating状態

~~~text
┌──────────────────────────────────────────────────────────────┐
│ Visual request: Discussion Map UI                  [Cancel]   │
│ Type: Diagram   Objective: 参加者間でUI構成を共有する          │
│ Context: 3 topics / 4 ideas / 1 concern                       │
│ Status: Generating...                                         │
│                                                              │
│              Discussionは継続できます                         │
├──────────────────────────────────────────────────────────────┤
│ Mapは通常どおり更新中                         [Back to Map] │
└──────────────────────────────────────────────────────────────┘
~~~

### 35.3 Ready通知

~~~text
┌──────────────────────────────────────────────┐
│ Visual ready: Discussion Map UI               │
│ AI Concept Draft · 1 new artifact             │
│ [Visualを表示]                    [後で]      │
└──────────────────────────────────────────────┘
~~~

### 35.4 Visual View

~~~text
┌──────────────────────────────────────────────────────────────┐
│ [← Back to Map]  Discussion Visual   AI Concept Draft         │
│ Source: Discussion Map UI   Generated from: Revision 145      │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│                  ┌──────────────────────┐                    │
│                  │                      │                    │
│                  │      Visual          │                    │
│                  │                      │                    │
│                  └──────────────────────┘                    │
│                                                              │
│ Objective: 参加者間でUI構成のイメージを共有する                │
│ [Contextを表示]       [Revise] [Regenerate]                  │
└──────────────────────────────────────────────────────────────┘
~~~

### 35.5 Map + Visual

~~~text
┌──────────────────────────────┬───────────────────────────────┐
│ Discussion Map               │ Discussion Visual             │
│ Current Topic highlighted    │ AI Concept Draft               │
│ Topic cards / decisions      │ Source: Discussion Map UI       │
│                              │                               │
│                              │        diagram / image         │
│                              │                               │
│ [Close Visual]               │ [Full View]                    │
└──────────────────────────────┴───────────────────────────────┘
~~~

これは既定画面ではなく、Prototypeで価値が確認された場合の明示的な補助Viewとする。

### 35.6 Multiple Artifact / Version

~~~text
┌──────────────────────────────────────────────────────────────┐
│ Topic: Discussion Map UI                         📎 2         │
├──────────────────────────────────────────────────────────────┤
│ Artifact Family: UI concept                                  │
│  v2  AI Concept Draft   current    [Open] [Revise]            │
│  v1  superseded                    [Compare]                  │
│                                                              │
│ Generated from: Revision 145 / Revision 151                  │
│ [Back to Map]                                                │
└──────────────────────────────────────────────────────────────┘
~~~

通常のMapではこの一覧を常時展開せず、Marker選択後に表示する。

## 36. Validation Plan

### 36.1 Prototype

実装前に、Static Mockまたはクリック可能なPrototypeで次の状態を再現する。

* Generate入口
* Context Preview
* queued / generating / ready / failed
* Full Visual View
* Back to Map
* MarkerとVersion一覧
* Map更新中にVisualがReadyになる場面

実際の画像生成品質を評価する前に、同じ内容の固定画像または固定Diagramを用いて、介入方法と画面遷移を検証する。

### 36.2 検証シナリオ

少人数の参加者に30分相当のDiscussionを提示し、通常Map、生成中、Ready通知、Visual閲覧、Map復帰を順に体験してもらう。

確認する項目:

1. Visual生成の目的と対象Topicを誤解しないか
2. Context Previewの情報量でDiscussionが止まらないか
3. Visual待ちの間にDiscussionを継続できるか
4. VisualがDraft / Discussion Aidと理解されるか
5. Visualを見た後に、具体的なDiscussionが増えるか
6. Mapへ自然に戻れるか
7. Mapへ戻った後、元のCurrent Topicと新しいArtifactの関係を追えるか
8. VisualがなくてもDiscussionを継続できるか

### 36.3 Anchoring検証

同一のDiscussion Contextに対して、単一Visualを見せる条件、Visualを見せない条件、説明文を添えて見せる条件を比較する。参加者が元のOptions以外の可能性を挙げられるか、Visualの具体的な意匠をDecisionと誤認しないかを確認する。

### 36.4 成功判断

「Visualがきれいだったか」ではなく、次を主な観察結果とする。

* 参加者間のイメージの認識差が減ったか
* Visual後の発言が具体化したか
* Discussionの停止・逸脱・待ち時間が増えなかったか
* Visualを見た後にMapへ戻り、Stateを追跡できたか

## 37. Success Metrics

PoCで次を評価候補とする。

* VisualがDiscussion理解に役立ったという参加者評価
* 参加者間の認識差の減少
* Visual後に具体的なOption、Concern、Decision候補が増えた割合
* Visual生成待ちによるDiscussion停止の有無
* Visualを見た後にMapへ戻れた割合
* 同じArtifactを再生成したいと感じたケース
* Visualが不要、または混乱を招いたケース
* VisualをDecisionと誤認したケース

生成回数やReady率だけでは成功と判断しない。Visualを使ったことでDiscussionが改善したかを優先する。

## 38. Risks / Trade-offs

| Risk / Trade-off | 影響 | 緩和策 |
| --- | --- | --- |
| Anchoring | 最初のVisualが議論を一方向へ誘導する | Draft表示、Objective表示、自動表示なし、再検討を促す |
| Hallucination | 画像・Diagramに存在しない意味や構造が入る | Discussion Aid扱い、Context表示、DiagramとImageのRenderer分離 |
| Visual overspecification | 未決事項まで具体化され、Decisionに見える | Candidate状態を維持、未決を勝手に確定しない |
| Latency | 生成待ちでDiscussionが停滞する | 非同期、Map継続、Ready通知 |
| Cost | 生成回数が増える | Manual Trigger、重複排除、明示Retry、利用量制御 |
| Privacy | Contextが外部Providerへ送信される | 最小Subgraph、Speaker除外、Preview、Retentionを別途設計 |
| Discussion interruption | 自動切替や通知が会話を遮る | Suggested Switch、控えめな通知、Back to Map |
| Context staleness | 完成Visualが現在の議論とずれる | Immutable Snapshot、Generated from表示、必要時Revision |
| Too many artifacts | MapがMarkerや一覧で埋まる | Topic単位の小さなMarker、Version折りたたみ |
| ArtifactをDecisionと誤認 | 仮説が正式案として扱われる | Draft Label、Decisionへの自動接続なし |
| Diagramの偽の正確さ | 構造図が確定アーキテクチャに見える | Draft表示、未確定要素の状態維持、正式設計は別成果物 |

最大の設計上のTrade-offは、生成を控えめにして主導権と安定性を守るほど、「AIが先回りして議論を豊かにする」体験の即時性が低くなることである。MVPでは中心価値である会議中のShared Understandingを優先する。

## 39. Open Questions

### OQ-4001: MVP初期TypeをConcept ImageとDiagramのどちらから始めるか

* 未決理由: Conceptは理解共有に強いが解釈の幅が大きく、Diagramは再現性が高いが対象Topicを構造化できている必要がある
* 検証: 同じ社内Discussionシナリオで両TypeのPrototypeを比較し、認識差の減少と再生成率を測る

### OQ-4002: Context Previewを常に表示するか

* 未決理由: Privacyと誤生成防止には有効だが、毎回の確認は会議を止める可能性がある
* 検証: Preview必須、Summary表示、Previewなしの3条件で生成までの時間と誤ったContext選択を比較する

### OQ-4003: 複数VariantをMVPに含めるか

* 未決理由: Anchoringを軽減する一方、待ち時間・Cost・比較負荷を増やす
* 検証: Singleと複数案を用いたDiscussionで、代替案の発話数と認知負荷を評価する

### OQ-4004: Full VisualとSplit Viewの適切な使い分け

* 未決理由: Full Visualは共有しやすいがMapを一時的に隠し、Split Viewは関係を保つが文字が小さくなる
* 検証: 1920x1080と2560x1440の距離別Prototypeで、Visual内容とMapの双方を追えるか確認する

### OQ-4005: Voice IntentをMVPに含めるか

* 未決理由: 入力が自然になるが、STT誤認識と対象Topicの曖昧さが増える
* 検証: 実際の対面会話で意図検出、対象選択、誤生成、会話中断の割合を測る

### OQ-4006: ArtifactのDiscussion Statusをどこまで表示するか

* 未決理由: draft / superseded / rejectedだけでも理解に役立つが、状態表示が増えるほど複雑になる
* 検証: Labelを段階的に減らしたPrototypeで、Artifactを正式Decisionと誤認する割合を調べる

### OQ-4007: Diagram Rendererの構造化入力範囲

* 未決理由: Graphを忠実に描くほど未整理のGraphも露出し、自由なImage生成との境界が曖昧になる
* 検証: Architecture、Flow、UXの3種類を固定データで描画し、参加者が関係と未確定状態を読めるか検証する

### OQ-4008: Provider Raw ResponseとPromptの保持期間

* 未決理由: DebugとEvaluationには有用だが、Privacyと保存コストが増える
* 検証: 失敗再現に必要な最小Metadataを定義し、Raw Responseなしで調査できるか運用リハーサルする

### OQ-4009: Context Stalenessを通知する条件

* 未決理由: Revision番号だけでは参加者が差分の重要性を判断しにくく、強い警告は介入になる
* 検証: 時間経過、Topic変更、Decision変更の各条件で表示文を比較し、不要な混乱と見逃しを測る

### OQ-4010: セッションあたりのGeneration Limit

* 未決理由: Cost制御に必要だが、Discussionの長さとProvider価格に依存する
* 検証: PoCのセッション別生成回数、重複率、再生成理由を収集して閾値を決める

### OQ-4011: Artifact Markerの件数とVersion表示

* 未決理由: 件数は発見性を上げるが、数字が多いとMapの視覚負荷や重要度の誤認につながる
* 検証: 0〜数件のMarkerを用いたStatic Prototypeで、存在の発見とMap理解を比較する

### OQ-4012: MinutesへのArtifact参照

* 未決理由: ArtifactはDiscussion Aidであり、Minutesに含めると正式成果物に見える可能性がある
* 検証: RFC-0005でMinutesの読者・利用目的を整理し、Artifactをリンク、一覧、または除外する条件を決める

## 40. Decision

Status: Proposed

### Recommended Visual Architecture

Artifact Requestを起点に、Discussion Graphから対象Subgraphを抽出し、Context Snapshotを不変保存する。生成は非同期とし、Diagram RendererとImage GeneratorをCapabilityとして分離する。完成物は独立Artifact Resourceとして保持し、Discussion GraphにはTopicへの参照と小さなArtifact MarkerだけをMaterializeする。

~~~text
Discussion Graph / Event Stream
          ↓
Context Selector
          ↓
Immutable Context Snapshot
          ↓
Async Artifact Request
      ┌───┴───┐
      ↓       ↓
Diagram     Image
Renderer    Generator
      └───┬───┘
          ↓
Artifact Resource
          ↓
Map Marker / Visual View
~~~

### Recommended Trigger Policy

MVPはManual Triggerを基本とする。AIはContext候補とPreviewを支援するが、生成・Version作成・画面切替を自動で行わない。Voice Intentは、対象確認を含む補助経路として検証後に追加する。

### Recommended Artifact Model

ArtifactはTopicやDecisionと同じGraph Nodeにはせず、独立Resourceとして管理する。Generation StateとDiscussion Statusを分離し、生成物はDraftとして扱う。Source Topic、Graph Revision、Context Snapshot、Prompt Structure、Version関係を保持する。

### Recommended Display / Screen Switching Model

MapはPrimary Viewのまま維持する。完成時は控えめなReady通知とMarkerで知らせ、ユーザーがVisual Viewを開くSuggested Switchを採用する。既定のVisual ViewはContext Header付きFull Visualとし、Back to Mapを常時提供する。Automatic Switchは採用しない。

### Recommended Versioning Policy

同じArtifact Familyの修正は線形Version Chainとして保持する。v2はv1のrevised_fromを持ち、各Versionは独自Snapshotを保持する。Branchと直接上書きはMVPでは採用しない。

### Key Trade-off

Control、視覚的安定性、Privacy、Discussion継続性を優先するため、AIが自律的に次々とVisualを生成・提示する即時性を犠牲にする。これはVisual Artifactを主役ではなくDiscussion Aidに留めるための意図的な選択である。

### Deferred to RFC-0005

* MinutesにArtifactをどの程度含めるか
* MinutesからArtifactを参照する形式
* ArtifactをAction Item、Decision、Next Topicとどう関連づけるか
* Session終了後のArtifactとMinutesの表示

### Deferred to Future RFC

* Voice Intentの詳細認識と自然言語によるContext選択
* 複数Variant、Artifact Branch、複雑な比較Workspace
* Artifactの正式採用、設計成果物化、承認Workflow
* Provider固有の品質評価、運用、Retry Policy、Cost Dashboard
* 外部ProviderのRetention、Security Architecture、組織単位のPrivacy Policy
* Artifact Gallery、Session横断検索、長期保存

### Explicitly Not Adopted for MVP

* Autonomous Visual Generation
* Visual完成時のAutomatic Screen Switching
* ArtifactをConfirmed Decisionとして扱うこと
* Artifactを通常のDiscussion Graph Nodeとして大量に追加すること
