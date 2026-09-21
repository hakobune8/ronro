# RFC-0003: Discussion Map UX and Layout

| 項目 | 内容 |
| --- | --- |
| Status | Proposed |
| Target | Discussion Map AI Facilitator MVP |
| Related RD | [Discussion Map AI Facilitator MVP 要件定義書](../requirements/discussion-map-ai-facilitator-mvp.md) |
| Depends on | RFC-0001: Discussion Model / Discussion Graph Architecture |
| Depends on | RFC-0002: Realtime Discussion Analysis Pipeline |
| Last Updated | 2026-09-19 |

本RFCは、Discussion Graph、Event Stream、Current Topicなどの内部状態を、会議中に参加者が理解・修正できるDiscussion Mapへ変換するUXとLayoutを設計する。

本RFCは画面実装を開始するものではない。Static MockやPrototypeで検証可能なUX要件と設計判断を定義する。

## 1. Problem Statement

### 1.1 Discussion Mapの役割

Discussion Mapは会議終了後に読む成果物ではなく、会議中に参加者が見ながらDiscussionを修正するための共有画面である。

参加者がMapを見ることで、少なくとも次を理解できる必要がある。

- 現在何について話しているか
- Discussion全体がどのような構造になっているか
- どのIdea、Option、Concernが出ているか
- 何がConfirmed Decisionで、何がまだCandidateか
- 何が未解決か
- Topicがどのように移動したか
- 元のTopicが未解決のまま残っているか
- 会議後に何を実行する必要があるか

### 1.2 Internal StateとShared Understandingの違い

内部のDiscussion Graphは、AIが解析したEntityとRelationを保持する。Event Streamは履歴を保持し、TranscriptはEvidenceである。

これらはそのまま画面に出せば理解できるものではない。

- Eventをすべて表示すると履歴が多すぎる
- Graphをそのまま表示するとRelationが交差する
- CandidateとConfirmedを同じ見た目にすると誤認が生じる
- Current Topicだけを拡大すると全体構造を失う
- Flowを常時表示するとMapの面積が減る
- Evidenceを常時表示すると会話より画面に注意が向く

UXの責務は、内部状態をそのまま公開することではなく、会議中の判断に必要な情報を、安定した共有画面へ変換することである。

### 1.3 設計判断の優先順位

本RFCでは次の優先順位を採用する。

1. 現在何について話しているかが一瞬で分かる
2. Discussion全体の構造を見失わない
3. Map更新で既存の位置関係が大きく変わらない
4. 情報量が増えても読みやすい
5. AIの解析結果を確定事項と誤認させない
6. AIの誤りを会議中に簡単に修正できる
7. Mapを見ること自体がDiscussionを邪魔しない
8. Discussionの流れを把握できる
9. 脱線を断定せず、参加者自身が気付ける
10. 16:9共有ディスプレイで離れた位置から読める

## 2. Goals / Non-goals

### 2.1 Goals

このRFCで決めることは次のとおりである。

- 16:9共有ディスプレイ向けのPrimary Viewの構成
- Current Topic、Discussion Flow、Status情報の役割分担
- Candidate DecisionとConfirmed Decisionの視覚的分離
- Topic、Question、Unresolved Itemなどの表示上の統合方針
- Map Layout候補の比較と推奨案
- Map更新時のVisual Stability要件
- Progressive DisclosureのMVP範囲
- Node TypeとStateを伝えるVisual Language
- Human Correction、Undo、Evidence ReferenceのUX境界
- Partial Transcript、Processing、Observationの控えめな提示方法
- Multiple Active Topicsの表示方針
- Session Start、Normal Discussion、Drift、Large Map、Visual ArtifactのWireframe
- 16:9の画面サイズ差、Accessibility、Static PrototypeによるValidation Plan

### 2.2 Non-goals

以下はこのRFCでは詳細を決めない。

- Graphの内部Schema
- Event Streamの保存方式
- STT、LLM、Visual生成Provider
- Visual Artifactの生成方式・Prompt・画像品質
- Meeting Minutesの詳細フォーマット
- Mobile UI
- 個人端末からの参加
- 投票、発言者評価、感情分析
- 高度なGraph Editor
- ユーザー権限、ユーザー管理
- CSS、Frontend Framework、具体的な実装コード

Visual Artifactの生成とVersion管理はRFC-0004、MinutesはRFC-0005へDeferredする。

## 3. RFC-0001 / RFC-0002から維持する前提

### 3.1 責務分離

次の関係を維持する。

> Transcript = Evidence
> Event Stream = Discussion History
> Discussion Graph = Current StateのMaterialized View

MapはCurrent Graphを中心に描画する。Event StreamやTranscriptを通常画面へ直接流し込まない。

### 3.2 解析結果の確定性

- Partial Transcriptでは正規Graphを更新しない
- Final Utterance / Analysis Windowを基準に更新する
- Discussion AnalysisはCandidate Eventを生成する
- DecisionはPipelineだけでconfirmedにしない
- CandidateとConfirmedをUX上で明確に区別する

### 3.3 FlowとDrift

- Topic transitionは意味構造のcontainsとは別に扱う
- Current TopicはPipelineの候補とGraph Projectionの状態をもとに表示する
- DriftをAIが「悪い脱線」として断定しない
- 未解決Topicと現在のTopicが併存するという事実を中立的に提示する

### 3.4 変更提案

RFC-0001およびRFC-0002の決定を変更しない。

本RFCでは、Candidateを専用の確認待ち領域へ提示し、Current Topicの切替を視覚的に抑制する。これは既存のCandidate Event、Current Topic candidate、Graph Materializerの責務をUXへ具体化するものであり、既存RFCへの変更提案ではない。

## 4. UX Architecture

### 4.1 推奨UXアーキテクチャ

MVPでは、次の4つの表示領域を持つ共有ディスプレイ構成を推奨する。

1. **Header**: Discussion Title、Session Time、Live状態
2. **Map Canvas**: Discussion Graphの主要構造とCurrent Topic
3. **Status Rail**: Current Topicの説明、Decision、Candidate、Open Issues、Actions、Parking Lot
4. **Observation Bar**: 短いAI Observation、Listening / Processing状態

Discussion FlowはMap Canvasの上部にある小さなRecent Flow stripとして扱う。長いTimelineを常時表示しない。

### 4.2 情報の優先階層

共有画面では、次の順に視線を誘導する。

1. Current Topic
2. Current Topic周辺のIdea、Question、Option、Concern
3. Confirmed DecisionとOpen / Unresolved Items
4. Discussion全体のTopic構造
5. Candidate Decision、Action、Parking Lot
6. Observation、Evidence、Processingの補助情報

この順序は、すべての情報を同時に強調するという意味ではない。中心情報と補助情報の視覚的な優先度を分ける。

### 4.3 状態と履歴の表示分離

- Map CanvasはCurrent Graphを表示する
- Recent Flow stripは直近のTopic遷移を表示する
- Status RailはCurrent Graphの重要なStatusを要約する
- Evidence drawerはユーザーが必要なときだけ開く
- Event Stream全体は通常画面に表示しない

### 4.4 Shared Displayを前提にする

Primary Viewは、個人が細かく操作するDashboardではなく、参加者全員が同じ方向を見て会話するための画面とする。

- 常時表示するテキスト量を制限する
- マウス操作がなくても状態が分かる
- 小さなTooltipや多数のタブに依存しない
- 重要な状態は文字、形、アイコン、配置の複数手段で表現する

## 5. Primary View

### 5.1 推奨レイアウト

推奨は、Mapを中心に据えたHybrid Shared Viewである。

概念的な比率:

- Header: 8〜10%
- Recent Flow strip: 6〜8%
- Map Canvas: 62〜70%
- Status Rail: 20〜26%
- Observation Bar: 8〜10%

これは固定Pixel値ではなく、情報の優先順位を示す概念比率である。

### 5.2 Header

Headerには次を置く。

- Discussion Title
- Session Time
- Session状態: Listening、Processing、Paused、Endingなど
- 必要なら小さなMap更新状態

Headerに長いTranscriptやAIの詳細ログを置かない。

### 5.3 Recent Flow strip

Map Canvasの上部に、最近のTopic遷移を短く表示する。

例:

~~~text
[MVP範囲] → [Discussion Map] → [料金モデル] → [MVP範囲へ戻る]
~~~

常時表示するのは直近の少数Topicとし、古いFlowは折りたたむ。

### 5.4 Map Canvas

Map Canvasは、Topicを安定したレーンまたはセクションとして保持し、その内部にIdea、Option、Question、Concern、Decisionなどを配置する。

Map Canvasの要件:

- Current Topicを一目で識別できる
- 全体のRoot / Goalと主要Topicが見える
- New Node追加で既存Nodeの位置を大きく変えない
- 交差するRelationを必要以上に増やさない
- Current Topicの周辺だけ詳細を見せられる
- 画面全体を頻繁にZoomしない

### 5.5 Status Rail

Status Railは、Mapの代替ではなく、会議中に確認頻度の高い状態へのショートカットである。

推奨順序:

1. Current Topic card
2. 確認待ち Candidate Decisions
3. Confirmed Decisions
4. Open / Unresolved Items
5. Action Items
6. Parking Lot

すべてを常時展開せず、各セクションは件数と代表項目を表示する。項目を選ぶとMap上の関連Nodeを弱く強調できる。

### 5.6 Observation Bar

Observation Barは、AIが会議の主役にならないよう、画面下部に控えめに置く。

- 同時に1件まで
- 短い文章
- 非命令的な表現
- Dismiss可能
- Current Graphの更新をブロックしない

## 6. UX Alternatives / Primary View Alternatives

### 6.1 案A: Graph-centric

Mapを画面の大部分に表示し、Statusを周辺に小さく置く。

#### 長所

- Discussion Graphの全体構造を理解しやすい
- Node間の関係を見せやすい
- Mapを会議中の中心成果物として扱える

#### 短所

- Current Topic、Decision、Actionの確認場所が分かりにくくなりやすい
- Mapが大きくなるとStatus情報が埋もれる
- Candidate Decisionの確認UIが弱くなる

### 6.2 案B: Focus-centric

Current Topicを中央に大きく表示し、全体Mapを縮小して周辺に置く。

#### 長所

- 現在何を話しているかが分かりやすい
- Current Topic周辺の議論に集中しやすい
- Topic切替の意味を示しやすい

#### 短所

- 全体構造を失いやすい
- 過去Topicや未解決Topicが見えにくくなる
- Focusの切替が頻繁だと画面が落ち着かない

### 6.3 案C: Split View

Map、Status Panel、Timelineを明確に分割する。

#### 長所

- 情報の責務が分かりやすい
- Decision、Open Issue、Flowを常時表示しやすい
- 各領域を個別に検証しやすい

#### 短所

- Mapの面積が減る
- 16:9共有画面では文字が小さくなりやすい
- 参加者の視線が複数領域に分散する

### 6.4 案D: 推奨Hybrid Shared View

Mapを主役にしつつ、Current TopicとStatusをRight Rail、FlowをCompact strip、Observationを下部に配置する。

#### 評価

- Shared Understanding: 高
- Current Topic clarity: 高
- Flow understanding: 中〜高
- Map stability: 高
- Scalability: 中〜高
- Correction ease: 中〜高
- Information density: 制御しやすい
- MVP complexity: 中

案Dを推奨する。Mapの中心価値を保ちながら、Status情報を常に探し回らなくて済むためである。

## 7. Current Topic UX

### 7.1 Current Topicの二重表示

Current Topicは、次の2か所で同じ意味を異なる粒度で表示する。

1. Map上の対象Topicを強調する
2. Status Rail上部にCurrent Topic cardを表示する

Map上だけにCurrent Topicを置くと、Mapが大きくなったときに見失う。Status Railだけに置くと、Graph全体との関係が失われる。

### 7.2 推奨する強調方法

色だけに依存せず、次を組み合わせる。

- Topic laneの二重または太めのBorder
- NOWまたは現在というテキストBadge
- Current Topic icon
- 周辺Nodeの軽い背景差
- Topic headerのTypography強調
- Status RailのCurrent Topic card

強調は局所的に行い、Map全体へ強い色や光を広げない。

### 7.3 Current Topic周辺の強調

Current Topicの直接の子Node、関連Option、Question、Concernは一段階だけ強調する。

それより遠いNodeは全体構造を保つため、淡く表示する。ただし完全に非表示にはしない。

### 7.4 Topic切替時の安定性

Current Topicが切り替わっても、次を行わない。

- Map全体の再配置
- 全画面のZoom
- 自動的な大きなPan
- 既存Nodeの別Topicへの移動

代わりに次を行う。

- Current TopicのBadgeを切り替える
- 対象Topic laneのBorderを変える
- Status RailのCurrent Topic cardを更新する
- Recent Flow stripへ遷移を追加する
- 必要なら対象Topicの局所的なDetailsだけ展開する

### 7.5 一度離れたTopicへ戻る場合

既存Topicへ戻った場合は、新しいTopicを作らず、元のlaneとNode位置を再利用する。

- Flow stripには戻ったことを追加する
- Current Topic強調を元のlaneへ戻す
- 過去の未解決Itemを再び見える状態にする
- Topic名や構造を自動で作り直さない

Current TopicがParking Lotへ移動した場合は、Map上のCurrent Topic強調とStatus RailのCurrent Topic cardを解除する。Graphのprimary_topic_id=null相当を「現在のFocusなし」として表示し、restore_from_parking_lotだけでは元のFocusを復帰させない。復帰はHumanの明示操作または次の明示的なtopic_focus_changedを受けた場合だけ行う。

### 7.6 Current Topicの確信度が低い場合

低確信度のCandidateを、確定したCurrent Topicとして強調しない。

推奨表示:

- 現在の安定したCurrent Topicは維持
- Status Railに「次の論点を整理中」などの控えめな状態を表示
- 新Topic候補は点線の候補Markerとして扱う
- Candidateが一定の継続性を得るまでFlow stripを確定更新しない

具体的な切替条件はRFC-0002 OQ-2004として残り、Static Prototypeで検証する。

### 7.7 複数Topicを並行して話す場合

内部Graphが複数のActive Topicを持つことは許容する。

UXでは次の役割に分ける。

- Primary Current Topic: 現在の視線を置く1つのTopic
- Secondary Active Topic: 関連しているが主焦点ではないTopic

Secondary Active Topicは、Map上で細いOutlineまたは小さなRelated badgeだけを表示する。複数Topicを同じ強さで強調しない。

## 8. Topic Transition / Discussion Flow

### 8.1 方式比較

#### 案A: Map上にFlowを統合

Topic間に矢印や時系列Edgeを描く。

長所:

- MapとFlowを同時に見られる
- 戻ったことを同じ画面で理解できる

短所:

- Edgeが増えて構造が読みにくくなる
- Topicの意味構造と時間的な移動が混ざる
- 更新時に線の交差が増えやすい

#### 案B: 別Timeline

Mapとは別のTimeline領域を常時表示する。

長所:

- 構造と流れを分離できる
- 時系列を説明しやすい

短所:

- Mapの面積を使う
- 30〜60分ではTimelineが長くなる

#### 案C: Breadcrumb

直近のTopicだけを横並びに表示する。

長所:

- 面積が小さい
- いまどこから来たかを理解しやすい
- Shared Displayに適する

短所:

- 長期のFlowを見返せない
- 分岐や並行Topicを表現しにくい

#### 案D: Recent Topic History

直近数件を履歴として表示し、古いものは折りたたむ。

長所:

- 最近の移動と戻りを把握できる
- UIが比較的単純

短所:

- 明確な全体Timelineではない
- 古いTopicの関係は別操作が必要

### 8.2 推奨

Breadcrumbに近いCompact Recent Flow stripを推奨する。

- 直近の少数Topicを表示
- Current Topicを明確に示す
- 戻ったTopicは同一Labelの再出現またはReturn markerで示す
- 古いFlowはHistory affordanceから参照可能にする
- Map内部の構造Relationと時系列Flowを混ぜない

### 8.3 「どこから話が逸れたか」

「脱線」という語を使わず、次の事実を組み合わせて示す。

- From Topic
- To Topic
- From Topicが未解決か
- To Topicでどの程度Discussionが続いたか
- From Topicへ戻ったか

参加者が判断できるよう、Flow stripとObservationで補助する。

## 9. Drift Awareness UX

### 9.1 表示文の原則

AIは「脱線です」「戻るべきです」と断定しない。

推奨する表現:

> 元の論点「MVP範囲」は未決のままです。現在は「料金モデル」を議論しています。

避ける表現:

> 脱線しています。MVP範囲に戻ってください。

### 9.2 表示場所

Drift Awarenessは、次の順で表示する。

1. Observation Barの短いObservation
2. From Topic laneの控えめな未解決Badge
3. Recent Flow stripの未解決Marker

Map全体を赤くしたり、Current Topicを警告色だけで囲んだりしない。

### 9.3 表示頻度

MVPでは、同じ状態のObservationを繰り返し出さない。

- 一つの未解決Topicと移動先の組み合わせにつき、一度を基本とする
- 状態が変化するまでCooldownする
- 参加者がDismissできる
- 新たなEvidence、Return、Decision、Parking Lot移動があれば再評価する

Cooldownの具体的な秒数はStatic PrototypeとPoCで決める。

### 9.4 表示時間と強調度

暫定のUX案:

- Observation Barに短時間表示
- Dismissされるまで完全には消さないが、一定時間後は低い優先度にする
- Current TopicやDecisionより強く目立たせない
- 文章は1〜2行に収める

表示の恒久性は、議論を邪魔しないことと、見逃さないことのトレードオフであり、検証対象とする。

### 9.5 Observationとの関係

Drift AwarenessはObservationの一種として扱う。ただしすべてのObservationを同じ優先度で表示しない。

優先度の例:

1. Decision candidateの確認待ち
2. 未解決Topicと新Topicの併存
3. 複数Optionの存在
4. 一般的な整理情報

同時表示は1件までとし、候補をキューに溜めて一度に大量表示しない。

## 10. Decision UX

### 10.1 Candidate DecisionとConfirmed Decision

MVPでは、Candidate DecisionとConfirmed Decisionを別の表示領域・別のVisual Languageで扱う。

#### Candidate Decision

- 「確認待ち」「Candidate」と明記
- 点線Border
- ?または時計・確認待ちIcon
- 背景はConfirmedより弱い
- Status Railの専用領域へ表示
- Confirm操作を提供

#### Confirmed Decision

- 「Confirmed」「確定」と明記
- 実線Border
- Check icon
- 決定済みのTopic・OptionとRelationを表示
- Candidate領域には置かない

色を使う場合も、Border、Icon、Label、Typographyを併用する。

### 10.2 CandidateをMap上に表示する案

#### 長所

- どのTopicからCandidateが出たか分かる
- Discussion構造との関係を把握しやすい

#### 短所

- 確定事項と誤認される危険がある
- 未確定情報がMapを増やす
- Candidateが頻繁に変わるとMapが落ち着かない

### 10.3 Candidate専用領域

CandidateをStatus Railの「確認待ち」にまとめる。

#### 長所

- Confirmed Decisionと混同しにくい
- 会議中に確認すべき項目が分かる
- Map Canvasの構造を安定させやすい

#### 短所

- Candidateと元Topicの関係が薄く見える
- Candidateが多いとRailが膨らむ

### 10.4 推奨表示

Candidateは専用の「確認待ち」領域を正規の表示場所とする。

Map上の関連Topicには、Candidateの本文を複製せず、小さな「確認待ちあり」Markerだけを表示する。Markerを選ぶとCandidateの詳細と関連Topicが分かる。

これにより、同じCandidateをMapとRailで二重表示せず、関係と確定性を両立する。

### 10.5 Confirmation UI

MVPでは、明示操作によるConfirmを基本とする。

操作の概念:

- Confirm: このCandidateをConfirmed Decisionにする
- Edit then Confirm: 文言を修正してConfirmedにする
- Keep Open: Candidateを未確定のまま残す
- Dismiss / Remove from Map: 現在のMapから隠すが履歴は保持する

操作は会議を停止するモーダルではなく、Candidate cardの短い操作として提供する。

### 10.6 暗黙確定

一定条件による暗黙確定はMVPでは採用しない。

理由:

- 相槌や暫定同意と正式Decisionを区別しにくい
- 誤確定がMinutesにも影響する
- 会議中の信頼性を損なう

RFC-0002の「Pipelineはconfirmedを自動生成しない」という前提を維持する。

## 11. Agreed vs Decided

### 11.1 表示を分ける案

Agreedを「方向性として合意」、Decidedを「正式に決定」とする。

#### 利点

- 合意と正式Decisionの違いを表現できる
- 探索段階の会議で柔軟な状態を持てる

#### 欠点

- 参加者が2つの意味を理解する必要がある
- AIが同意・相槌・決定を誤分類しやすい
- Candidate、Agreed、Decidedの3段階以上になり、誤認が増える
- MapとMinutesで異なる意味を説明する必要がある

### 11.2 MVPの推奨

MVPではAgreedとDecidedをUI上で分けない。

- 未確定の方向性: Candidate DecisionまたはIdea / Opinion
- 人間が確定したもの: Confirmed Decision

「Agreed」という表現は内部の説明やEvidenceに残る可能性があるが、独立したMap Node Stateとしては扱わない。

正式な合意と方向性を分ける必要が検証で明らかになった場合は、RFC-0001のDecision Modelを改訂する提案を行う。

## 12. Question / Unresolved Item

### 12.1 表示上の課題

QuestionとUnresolved Itemを別Nodeとして並べると、参加者には重複に見える可能性がある。

例:

- Question: Visual生成は自動にする？
- Unresolved Item: Visual生成タイミング

### 12.2 推奨する表示モデル

内部GraphではRFC-0001の概念を保持できるが、Primary Viewでは一つの「Open / Unresolved Items」領域へ統合する。

各Itemには、必要に応じてSubtype badgeを付ける。

- 問い
- 未決
- 懸念

同じ意味を持つQuestionとUnresolved Itemを同時に別Nodeとして表示しない。

### 12.3 解消時の表示

DecisionがQuestionを解消した場合:

- Open / Unresolved Itemsから外す
- 関連Decisionへのresolved markerを残す
- Flowまたは履歴から過去に存在したことを確認できる

現在のMapから外すことと、履歴から削除することを分ける。

## 13. Map Layout Alternatives

### 13.1 Tree型

Root Topicから子Topic、Idea、Questionを階層で配置する。

| 評価軸 | 評価 |
| --- | --- |
| 一目で理解 | 高 |
| Update安定性 | 高 |
| Topic増加 | 中 |
| Decisionとの関係 | 中 |
| Current Topic強調 | 高 |
| Human Correction | 高 |

#### 課題

- Topic間の横断Relationが表現しにくい
- Flowと構造を混同しやすい
- 深い階層になると横幅または縦幅が増える

### 13.2 Mind Map型

中心Topicから放射状にIdea、Option、Decisionを配置する。

| 評価軸 | 評価 |
| --- | --- |
| 一目で理解 | 高 |
| Update安定性 | 中〜低 |
| Topic増加 | 中 |
| Decisionとの関係 | 高 |
| Current Topic強調 | 高 |
| Human Correction | 中 |

#### 課題

- 新Node追加で全体が再配置されやすい
- 画面端のNodeが読みにくくなる
- 30〜60分で密度が上がる

### 13.3 Free Graph型

NodeとRelationを自由に配置する。

| 評価軸 | 評価 |
| --- | --- |
| 一目で理解 | 低〜中 |
| Update安定性 | 低 |
| Topic増加 | 低 |
| Decisionとの関係 | 高 |
| Current Topic強調 | 中 |
| Human Correction | 低〜中 |

#### 課題

- Layout Algorithmに依存しやすい
- Edgeが交差する
- Stable Positionを保ちにくい
- Shared Displayで読み手が構造を再構成する必要がある

### 13.4 Topic Column型

主要Topicを固定したColumnまたはLaneにし、その内部に関連Entityを配置する。

| 評価軸 | 評価 |
| --- | --- |
| 一目で理解 | 高 |
| Update安定性 | 高 |
| Topic増加 | 中〜高 |
| Decisionとの関係 | 中〜高 |
| Current Topic強調 | 高 |
| Human Correction | 高 |

#### 課題

- Topic間の複雑なRelationが弱く見える
- Column数が増えると横幅を消費する
- 新Topicをどの位置へ追加するかが必要

### 13.5 Hybrid型

Topic Columnを骨格にし、各Column内部を局所TreeまたはCard Stackで表現する。

| 評価軸 | 評価 |
| --- | --- |
| 一目で理解 | 高 |
| Update安定性 | 高 |
| Topic増加 | 高 |
| Decisionとの関係 | 高 |
| Current Topic強調 | 高 |
| Human Correction | 高 |

#### 課題

- Topic Columnと内部Treeの責務を定義する必要がある
- Relationをすべて表示できるわけではない
- 折りたたみ方の設計が必要

### 13.6 推奨

MVPではHybrid型、具体的には「固定Topic Lane + 局所Tree / Card Stack」を推奨する。

美しい自由配置より、既存Nodeの位置を守り、Current Topicの周囲だけ詳細を見せることを優先する。

## 14. Chosen Map Presentation Model

### 14.1 骨格

Map Canvasは次の骨格を持つ。

~~~text
┌────────────────────────────────────────────┐
│ Root / Goal                                 │
├───────────────┬────────────────────────────┤
│ Topic Lane A  │ Topic Lane B                │
│               │ [Current Topic]             │
│  Ideas        │  Ideas / Options            │
│  Questions    │  Questions / Concerns       │
│  Decisions    │  Decisions                  │
├───────────────┴────────────────────────────┤
│ Related / Collapsed Topics                  │
└────────────────────────────────────────────┘
~~~

Rootと主要Topicの位置を固定し、Lane内部でだけ局所更新を行う。

### 14.2 Topic Lane

Topic Laneは、次の要素を持つ。

- Topic header
- Topic state badge
- Current / Secondary marker
- 直下のIdea、Option、Question、Concern、Decision
- 折りたたみ状態
- 関連ActionまたはArtifactへの参照

Laneの順序は、Map更新のたびに自動ソートしない。新Topicは末尾または専用のNew Topic areaに追加し、参加者が追跡できる位置関係を守る。

### 14.3 Lane内部

Lane内部では、すべてのRelationを線で描かず、次の優先順で表現する。

1. Topicと直接関係するEntity
2. OptionとDecisionの関係
3. Questionとresolved Decisionの関係
4. Actionの結果関係
5. その他のRelationは詳細表示またはEvidenceで参照

### 14.4 MapとStatus Railの重複

Status Railは、Map内のNodeを別の意味で複製するのではなく、確認しやすいSummaryとして扱う。

- Stable Entity IDでMap Nodeと関連付ける
- Summaryを変更してもGraph Entityを増やさない
- Status RailのItemを選択するとMap上の対応位置を弱く示す

## 15. Visual Stability

### 15.1 Existing Node position

既存NodeのPositionは、原則として維持する。

- Node Label変更では位置を変えない
- Decision confirmedへの変更でも位置を変えない
- Current Topic変更でも別Laneへ移動しない
- Relation追加だけで全体Layoutを再計算しない

### 15.2 New Node appearance

New Nodeは、関係する既存Topic Laneの決められた追加領域へ出現する。

- 既存Nodeを押し出しすぎない
- Lane内部の余白または折りたたみ領域を利用する
- New markerを短時間だけ表示する
- 新Node追加後も全体のScaleを変えない

### 15.3 Topic Merge

Mergeは即時に全体Layoutを組み直さない。

- Merge先Nodeを維持する
- Merge元は履歴上に残す
- Map上ではMerge元の表示を短時間の移動表示または「統合済み」Markerにする
- 既存の子Nodeは可能な限りMerge先Laneの同じ位置関係に保つ

Mergeのアニメーションは、参加者が追跡できる短い控えめな表示に留める。

### 15.4 Node removal

削除操作は、通常の物理削除ではなくMapから隠す操作として扱う。

- 隠したNodeの位置を他Nodeが急に埋めない
- 必要なら空き領域を後から控えめに整理する
- UndoまたはHistoryから復元できる

### 15.5 Node rename

名前変更はLabelだけを変更し、次を維持する。

- Stable Entity ID
- Lane
- 関連Relation
- Evidence参照
- Flow履歴

### 15.6 Current Topic transition

Current Topicの移動は、カメラ移動ではなくFocus移動として表現する。

- BorderとBadgeを切り替える
- Status Railを更新する
- Flow stripへ追加する
- 全体をAuto panしない

### 15.7 Auto pan / zoom

MVPでは通常の解析更新による自動Pan / Zoomを行わない。

例外として、ユーザーがStatus RailからNodeを選択した場合に、限定的なFocus移動を提供する可能性はある。ただし、共有画面で全員の視線を突然移動させないよう、Prototypeで検証する。

### 15.8 Fit-to-screen

Fit-to-screenは初期表示または明示操作に限定する。

Map更新ごとに自動Fit-to-screenを行わない。

「Mapは描き直すのではなく育つ」という体験を優先する。

## 16. Progressive Disclosure

### 16.1 目的

30〜60分のDiscussionでは、すべてのEntityを同じ大きさで表示し続けると読めなくなる。

Progressive Disclosureでは情報を失うのではなく、現在の目的に応じて表示密度を変える。

### 16.2 MVPで採用するもの

- Current Topic Laneの詳細表示
- 非Current Topic LaneのCompact表示
- Resolved Topicの折りたたみ
- Confirmed Decisionの要約表示
- Parking Lotの折りたたみ
- Open Issueの代表項目表示と件数
- 隠れているEntity数の表示
- 手動Expand / Collapse

M5.1では、この方針を16:9共有ディスプレイの初期Presentation Policyとして具体化する。Current Topic LaneはExpanded、非Current Topic LaneはTopic名・状態・Decision / Open Item / Action件数を持つCompact表示とする。Parking Lot / ArchivedはさらにCompact表示にする。Expand / Compact、Scroll、Zoom、Selected NodeはUI Presentation Stateとして扱い、Discussion GraphやEvent Streamへ保存せず、Auto pan / zoomや全体再配置も行わない。

### 16.3 Summary Node

AIが新しい意味Nodeを作るSummary NodeをMVPの正規Entityとして増やすことは避ける。

代わりに、View上のCollapsed Topic Cardに次を表示する。

- Topic名
- 状態
- Decision / Open Issueの件数
- 最終更新の相対的な表示

これにより、Summaryの誤りがGraph Entityとして固定されることを防ぐ。

### 16.4 古いTopicの非表示

古いTopicを完全に消すのではなく、CompactまたはCollapsedにする。

- Current Topicへの関係は残す
- 未解決ItemがあるTopicは完全に隠さない
- Resolvedで参照頻度が低いTopicは折りたためる
- Parking Lotは専用領域へ移す

### 16.5 Zoom level

ZoomはMap全体の情報量を調整するための補助であり、解析更新で自動変更しない。

共有ディスプレイでは、参加者が手動操作しなくても主要情報が読めるDefault levelを優先する。

## 17. Node Visual Language

### 17.1 基本方針

色だけでNode TypeやStateを区別しない。

最低でも次のうち3つ以上を組み合わせる。

- Shape
- Icon
- Label
- Border style
- Typography
- Badge
- State indicator

### 17.2 Node Typeの候補

| Node Type | 推奨Visual | 表示上の補助 |
| --- | --- | --- |
| Topic | 角丸のHeader Card | Topicラベル、Current marker |
| Idea / Opinion | 丸みのあるCard | Ideaまたは吹き出しIcon |
| Option | 分岐を示すCard | Option label、選択状態 |
| Question | 点線BorderのCard | ? Icon、「問い」Label |
| Concern | 注意形状を含むCard | ! Icon、「懸念」Label |
| Candidate Decision | 点線Borderと軽い背景 | 「確認待ち」Badge、? Icon |
| Confirmed Decision | 実線Border | Check Icon、「確定」Label |
| Action Item | Task Card | CheckboxまたはAction Icon |
| Parking Lot | 低強調のCard | Parking Icon、「保留」Label |
| Artifact | 画像FrameのCard | Image Icon、「Visual」Label |

### 17.3 Stateの表現

- active: 通常の実線または標準Border
- parked: 低彩度、Parking Icon、保留Label
- resolved: CheckまたはResolved Badge、折りたたみ可能
- rejected: Strikeではなく、非採用Labelまたは履歴表示
- candidate: 点線、確認待ちLabel
- confirmed: 実線、確定Label

色を使う場合:

- CandidateとConfirmedの色差だけで意味を伝えない
- 赤をDriftやConcernの断定表示に使いすぎない
- 色覚差があってもIconとLabelで識別できる

### 17.4 Typography

- Topic headerは本文より大きくする
- Node Typeを小さな上部LabelまたはIcon付近に表示する
- Candidate / Confirmedの状態を本文の長い説明に埋め込まない
- 長いLabelは要約せず、表示上の省略と詳細表示を分ける

## 18. Speaker Information

### 18.1 常時表示しない

Discussion Mapの目的は人物評価ではなく、Discussion理解である。

そのため、SpeakerをMap Nodeに常時表示しない。

### 18.2 表示する場所の比較

#### Mapへ常時表示

情報源が分かりやすいが、Mapが発言者中心になり、Nodeが煩雑になる。

#### Node詳細時だけ表示

理解と根拠のバランスがよい。共有画面でも通常状態を保ちやすい。

#### Evidence表示時のみ表示

通常Mapを最も簡潔にできるが、Nodeの由来を確認する操作が必要になる。

### 18.3 推奨

MVPでは、Speaker情報はEvidence drawerまたはNode detailでのみ表示する。

- Speaker metadataが存在する場合だけ表示
- Speaker不明でもMapは成立する
- 発言量、評価、ランキングへつなげない

## 19. Evidence Reference

### 19.1 目的

参加者が「なぜAIはこのNodeを作ったのか」を確認できることは、AIへの過信を抑え、Human Correctionを助ける。

ただし、Evidenceを常時表示すると会議がTranscript確認に変わる。

### 19.2 推奨UI

Nodeを選択したときだけ、Evidence drawerまたはDetail overlayを開く。

最低限の内容:

- Node名とType
- 根拠となった短いTranscript snippet
- おおよそのTimestamp
- Speaker情報がある場合の任意表示
- Candidate / Confirmedなどの状態

### 19.3 表示量

- 通常画面ではEvidenceを表示しない
- 1つのNodeに対して代表的な少数Snippetを表示する
- 全Transcriptを自動展開しない
- Timestampから詳細Transcriptへ進むかは後続設計に委ねる

### 19.4 EvidenceとCorrection

CorrectionでLabelを変えても、元Evidenceを消さない。

Detailでは次を必要に応じて確認できる。

- AIが最初に参照したEvidence
- Human Correctionの内容
- 最新の関連Evidence

## 20. Human Correction

### 20.1 原則

Correctionは、会議を止めるGraph Editorではなく、現在のMapを整える短い操作として提供する。

- 変更対象を限定する
- 変更後の影響を局所的にする
- 変更をすぐ反映する
- Event履歴を残す
- 失敗した操作をUndoできる

### 20.2 Node名変更

NodeのContext menuまたはDetail overlayから変更する。

- Labelだけを編集
- Stable IDを維持
- AliasとCorrection履歴を残す
- Map位置は維持

### 20.3 Node削除

「削除」より「Mapから隠す」を基本ラベルとする。

- 現在表示から外す
- Event履歴は保持
- 再生成防止の情報を残す
- UndoまたはHistoryから復元可能にする

### 20.4 Topic Merge

Merge UIは、次の2つのNodeを明示して選択する。

- 残すTopic
- 統合するTopic

Merge後:

- 残すTopicの位置を維持
- 統合元の子NodeやRelationを確認可能にする
- 自動的に全体再配置しない

### 20.5 Candidate Decision確認

Candidate cardのConfirm操作を用意する。

- そのままConfirm
- Labelを修正してConfirm
- ConfirmせずOpen Issueとして残す
- Mapから隠す

Confirm操作は、Confirmed Decision領域へ移ることを明示する。

### 20.6 Decision解除

Confirmed DecisionのDetailから「決定を解除」する。

- Decisionをretractedとして履歴に残す
- 関連Questionが未解決へ戻る可能性を示す
- 自動的に無関係なQuestionを復元しない
- Map上の状態変化を局所的に表示する

### 20.7 Parking Lot移動

TopicまたはIssueのActionから「Parking Lotへ移動」を選ぶ。

- 現在の中心Mapから外す
- Parking Lot countを更新
- 元のTopicへのRelationを保持
- 後で戻せるようにする
- Current Topicだった場合はCurrent Topic表示とHuman Overrideを解除する
- Restore後は自動的にCurrent Topicへ戻さず、明示的なFocus操作を待つ

### 20.8 Topic状態変更

MVPでは、参加者が任意のGraph Stateを自由に編集しない。

提供候補:

- Parking Lotへ移動
- 解決済みとして扱う
- Openへ戻す

細かいStateの直接編集は避け、意味のある操作へ絞る。

## 21. Undo

### 21.1 方式比較

#### 案A: User-facing Undoなし

履歴だけ残し、UI操作を減らす。

短所は、会議中に誤Correctionを戻しにくいこと。

#### 案B: 最新のHuman CorrectionだけUndo

操作直後に一つだけ戻す。

実装・説明が比較的単純で、誤操作の救済になる。

#### 案C: Human Correctionの履歴から任意Undo

強力だが、過去Eventとの依存関係や再Projectionが複雑になる。

#### 案D: AI更新も含む汎用Undo

会議の現在状態を広く戻せるが、AIの後続Event、Transcript訂正、他のCorrectionとの整合が難しい。

### 21.2 推奨

MVPでは、案Bを採用候補とする。

- 最新のHuman Correction一件をUndoできる
- UndoはHuman Correctionに限定する
- AIの自動解析履歴を一般Undoで戻さない
- Event履歴は削除せず、逆操作Eventを追加する
- Undoの失敗時は現在Mapを壊さない

任意RevisionへのTime TravelはMVPのUser-facing機能にしない。

## 22. Partial Transcript / Candidate Information

### 22.1 Partial TranscriptをMapに表示しない

RFC-0002のとおり、Partial Transcriptは正規Graphを更新しない。

Map上にPartialの文字列や未確定Nodeを大量に出すと、参加者がそれを事実として扱う可能性がある。

### 22.2 Processing feedback

完全に無反応にすると、システムが停止したように見える。

推奨する控えめなFeedback:

- Headerの小さなListening indicator
- Processingの短いStatus
- Observation Barの「整理中」状態
- 最終更新時点のMapをそのまま保持

Current Mapの外側にTransientなCurrent Speech previewを置く案は、情報量が増えるためMVPでは主表示にしない。

### 22.3 Candidate情報

Candidateは、確認待ち領域とMap上の関連Markerで示す。

- 未確定本文をConfirmed領域へ置かない
- Partial由来のCandidateを通常表示しない
- Final Analysis Window由来のCandidateだけを正規の確認待ち対象にする

## 23. Multiple Active Topics

### 23.1 選択肢

#### Current Topicを常に1つ

視線が明確で、表示が単純。ただし並行議論を表現しにくい。

#### Primary / Secondary Topic

主焦点と関連Topicを分ける。Shared Displayでも扱いやすい。

#### Active Topic Set

複数Topicを同じレベルでActiveにする。表現力は高いが、Currentの意味が弱くなる。

### 23.2 推奨

内部Graphでは複数Active Topicを許容し、Primary / Secondaryの表示に変換する。

- Map上でStrong focusはPrimaryだけ
- Secondaryは関連Markerまたは薄いOutline
- Status RailのCurrent Topic cardはPrimaryを表示
- Flow stripにはSecondaryへの移動も必要に応じて短く表示

複数Topicを同時に強調しすぎない。

## 24. Observation UX

### 24.1 Observationの役割

ObservationはAIによる命令ではなく、参加者が見落としやすい事実の短い提示である。

例:

- 「MVP範囲」はまだ未決です
- 「価格」について2つの案があります
- Candidate Decisionが1件あります

### 24.2 表示場所

Observation Barを基本とする。

- Map Canvasの中心にToastを出さない
- Current Topic cardを上書きしない
- Candidate確認が必要な場合はStatus Railへリンクする

### 24.3 頻度とCooldown

MVPの暫定方針:

- 同時表示は1件
- 同じTopic・同じ内容は状態変化まで再表示しない
- 新しいObservationは現在のObservationを置き換える場合だけ表示
- Dismiss可能
- 重要度の低いObservationはキューに溜めない

具体的な秒数、Priority、CooldownはStatic Prototypeで検証する。

### 24.4 消える条件

Observationは次のいずれかで低い表示優先度へ移す。

- 関連する状態が解消された
- DecisionがConfirmedされた
- Topicへ戻った
- ユーザーがDismissした
- 新しい重要Observationが表示された

## 25. Empty / Early Session

### 25.1 Session Startの目的

開始直後の空のCanvasは、参加者に「何をすればよいか」を伝えにくい。

Start Viewでは、次を表示する。

- Discussion Title
- Discussion Goal
- Background / Contextの短い表示
- Listening準備状態
- 最初のTopicを待っている状態
- Session開始操作

### 25.2 Root Topicの扱い

Goalが入力されている場合は、Root / GoalをMapの骨格として表示する。

まだTopicが抽出されていない場合:

- Root / Goalを残す
- 「最初の論点を整理中」と表示する
- 空のGraphだけを見せない
- Partial Transcript本文をMap Nodeとして表示しない

### 25.3 最初のTopic生成

最初のFinal Analysis WindowでTopic候補が生成されたら、Rootの下にTopic Laneを追加する。

既存Rootの位置を動かさない。

## 26. End of Discussion

### 26.1 UX境界

Session終了時のPrimary Viewは、Live状態からSummary準備状態へ移る。

概念的には次の遷移とする。

~~~text
Live Discussion Map
        ↓
Session Summary View
        ↓
Minutes
~~~

### 26.2 Summary Viewの範囲

RFC-0005を侵食しない範囲で、Summary Viewは次を参照できる。

- Discussion Title
- Duration
- Confirmed Decisions
- Open / Unresolved Items
- Action Items
- Parking Lot
- Current Graphの最終状態

Minutesの文章構成、詳細なSummary生成、出力形式はRFC-0005へDeferredする。

## 27. Visual Artifact Integration Boundary

### 27.1 UXで定義する範囲

RFC-0004に先立ち、Map UXでは次を定義する。

- Generate Visualの入口
- Visualが存在することの表示
- MapからVisual Viewへの遷移
- Visual ViewからMapへの戻り
- Visualが現在のTopicやIdeaに関連することの表示

### 27.2 Generate Visualの入口

Map上のTopic、Idea、Option、比較対象などに、控えめな「イメージ生成」Actionを提供する。

- AIが勝手に大量生成しない
- 現在のContextを入力として使うことが分かる
- 生成中はLive Discussionを止めない
- 生成結果は結論ではなく議論素材であることを示す

### 27.3 Visualの存在表示

Artifactが存在する場合、関連NodeにImage Iconと「Visualあり」Badgeを表示する。

画像そのものをMap Nodeの背景にしない。

### 27.4 MapとVisualの往復

Visual Viewへ遷移しても:

- Discussion MapのCurrent Stateを保持する
- SessionのAudio / Analysisを継続できる
- Mapへ戻るActionを常に見える位置に置く
- 戻ったときにMap全体を再配置しない

Visualの生成方式、ArtifactのVersion、比較UIはRFC-0004へDeferredする。

## 28. 16:9 Shared Display

### 28.1 基本方針

MVPは同一空間の共有ディスプレイ1台を前提とする。

- 参加者全員が同じ状態を見る
- 離れた位置からCurrent TopicとDecisionが読める
- 小さい文字や密集したBadgeを増やさない
- 個人Dashboardのような細かい操作を前提にしない

### 28.2 1920x1080

1920x1080では、推奨Hybrid Shared Viewを標準状態とする。

- Map Canvasの幅を優先
- Status Railの各セクションは少数項目だけ表示
- 長い文章を折り返しすぎない
- 詳細Evidenceはdrawerへ送る

### 28.3 2560x1440

2560x1440では、同じ情報密度を保ったまま余白と文字サイズを拡大できる。

- 画面が広くなった分だけNode数を増やさない
- 参加者の距離に応じた読みやすさを優先
- Mapの全体再配置を行わない

### 28.4 Mouse操作への依存

通常状態は操作なしで理解できることを目指す。

操作は次の補助に限定する。

- CandidateのConfirm
- Node Detail / Evidenceの表示
- Expand / Collapse
- Human Correction
- Visualへの遷移

## 29. Responsive Behavior

### 29.1 対象範囲

MVPの主対象は16:9のDesktop共有ディスプレイである。

- 1920x1080を基本検証サイズとする
- 2560x1440で余白と文字サイズが破綻しない
- 16:9内でStatus RailがMapを圧迫しすぎない

### 29.2 対象外

- Mobile layout
- 縦長画面
- 個人スマートフォン操作
- 小さなBrowser viewportへの最適化

### 29.3 縮退の方針

表示領域が狭い場合は、次の順で情報量を減らす。

1. Evidenceの詳細
2. 古いFlow
3. Parking Lotの詳細
4. Resolved Topicの子Node
5. Secondary Topicの詳細

Current Topic、Confirmed Decision、Open / Unresolved Itemは最後まで残す。

## 30. Accessibility

### 30.1 色だけに依存しない

状態ごとに次を組み合わせる。

- Icon
- Border style
- Label
- Shape
- Badge
- Typography

### 30.2 Contrast

- 背景と本文のContrastを確保する
- Candidateの点線が薄すぎないようにする
- Parking Lotを背景と同化させない
- Focus状態が色覚差で失われないようにする

具体的なContrast値はPrototypeで検証する。

### 30.3 文字サイズ

共有ディスプレイで離れた位置から読めることを基準とし、情報量を減らしてでも本文を小さくしすぎない。

具体的なPixel値は画面サイズとViewing distanceを用いたPrototype検証で決める。

### 30.4 Animation

- Topic切替の過度な移動を避ける
- Node追加は短い控えめな変化にする
- Auto pan / zoomを通常更新で行わない
- Reduced motion相当の表示を考慮する
- Animationがなくても状態が理解できる

## 31. Wireframe

以下は設計検討用の概念Wireframeであり、精密なデザインではない。

### 31.1 Session Start

~~~text
┌────────────────────────────────────────────────────────────┐
│ Discussion Map AI Facilitator                 Not Started   │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  Title: AIサービスのMVP検討                                │
│  Goal : MVPで検証する中心価値を決める                      │
│                                                            │
│  Background / Context                                      │
│  会議中にDiscussion Mapを見ながら議論する                  │
│                                                            │
│                 [Discussionを開始]                         │
│                                                            │
│  Microphone: Ready       最初の論点を待っています          │
└────────────────────────────────────────────────────────────┘
~~~

### 31.2 Normal Discussion

~~~text
┌────────────────────────────────────────────────────────────┐
│ AIサービスのMVP検討                         12:34  Listening │
├────────────────────────────────────────────────────────────┤
│ [MVP範囲] → [Discussion Map] → [料金モデル]                │
├───────────────────────────────┬────────────────────────────┤
│                               │ CURRENT TOPIC              │
│  ROOT / GOAL                  │ Discussion Mapの中心機能   │
│    └─ MVP範囲                 │                            │
│       ├─ [NOW] Discussion Map│ 確認待ち (1)               │
│       │   ├─ Idea            │ 価格についての候補          │
│       │   ├─ Question        │                            │
│       │   └─ Concern         │ CONFIRMED DECISIONS        │
│       └─ 料金モデル           │ スマホUIはMVP対象外         │
│                               │                            │
│  [折りたたまれたTopic 2件]   │ OPEN / UNRESOLVED (2)      │
│                               │ ACTIONS (1)  PARKING (2)   │
├───────────────────────────────┴────────────────────────────┤
│ AI Observation: 「MVP範囲」は未決のままです。               │
└────────────────────────────────────────────────────────────┘
~~~

### 31.3 Candidate Decision

~~~text
┌────────────────────────────────────────────────────────────┐
│ Mapは維持されたまま                                      │
├───────────────────────────────┬────────────────────────────┤
│  [MVP範囲]                    │ 確認待ち Candidate (1)    │
│    └─ [確認待ちあり]          │                            │
│       └─ ? スマホUIはMVP対象外│ ? スマホUIはMVP対象外     │
│                               │ [確認] [修正して確認]      │
│                               │ [未決のまま] [Mapから隠す] │
│                               │                            │
│  Confirmed Decisionとは       │ CONFIRMED DECISIONS        │
│  異なる点線とBadgeで表示      │ まだ追加されていない       │
├───────────────────────────────┴────────────────────────────┤
│ AI Observation: 決定候補があります。確認は任意の操作です。│
└────────────────────────────────────────────────────────────┘
~~~

### 31.4 Discussion Drift

~~~text
┌────────────────────────────────────────────────────────────┐
│ [MVP範囲] → [料金モデル]  ← Current Topic                │
├───────────────────────────────┬────────────────────────────┤
│ [MVP範囲]                     │ CURRENT TOPIC              │
│  └─ Open: 中心価値の確認      │ 料金モデル                 │
│                               │                            │
│ [料金モデル]                  │ OPEN / UNRESOLVED          │
│  ├─ Option A                  │ MVP範囲: 1件               │
│  └─ Option B                  │                            │
│                               │ [Dismiss]                  │
├───────────────────────────────┴────────────────────────────┤
│ Observation: 元の論点「MVP範囲」は未決のままです。          │
│ 現在は「料金モデル」を議論しています。                    │
└────────────────────────────────────────────────────────────┘
~~~

### 31.5 Large Map

~~~text
┌────────────────────────────────────────────────────────────┐
│ AIサービスのMVP検討                         31:08  Listening │
├────────────────────────────────────────────────────────────┤
│ [MVP範囲] [料金] [UX] [Visual] [次回Topic]                 │
├───────────────────────────────┬────────────────────────────┤
│ ROOT / GOAL                   │ CURRENT TOPIC              │
│ ┌─────────────┐ ┌───────────┐ │ Visual生成                │
│ │ MVP範囲      │ │ 料金      │ │                            │
│ │ 3 Decisions │ │ 2 Open    │ │ CONFIRMED (3)             │
│ │ 1 Open      │ │           │ │ OPEN / UNRESOLVED (2)     │
│ │ [Compact]   │ │ [Compact] │ │ ACTIONS (2)               │
│ └─────────────┘ └───────────┘ │ PARKING LOT (4)            │
│ ┌───────────────────────────┐ │                            │
│ │ [NOW] Visual生成          │ │ [展開] [すべてのTopic]      │
│ │ Idea / Option / Concern   │ │                            │
│ └───────────────────────────┘ │                            │
├───────────────────────────────┴────────────────────────────┤
│ AI Observation: 1件                                         │
└────────────────────────────────────────────────────────────┘
~~~

### 31.6 Visual Artifact available

~~~text
┌────────────────────────────────────────────────────────────┐
│ Current Topic: サービスコンセプト                           │
├───────────────────────────────┬────────────────────────────┤
│ [サービスコンセプト]          │ CURRENT TOPIC              │
│  ├─ Idea: 会議中に可視化       │ サービスコンセプト          │
│  ├─ [Visualあり]               │                            │
│  └─ Option: Map + Visual       │ VISUAL ARTIFACT             │
│                               │ concept-v1                  │
│ Mapは背後で保持され、Visual   │ [Visualを表示]              │
│表示中もDiscussionを継続できる │                            │
│                               │ [Mapへ戻る]                 │
├───────────────────────────────┴────────────────────────────┤
│ Visualは議論の素材であり、Decisionではありません。         │
└────────────────────────────────────────────────────────────┘
~~~

## 32. Validation Plan

### 32.1 Static Prototypeで検証できること

実装前に、Static Mockまたはクリック可能なPrototypeで次を検証できる。

- Current Topicが一瞬で見つかるか
- CandidateとConfirmedを誤認しないか
- Node追加後も既存の位置関係を追えるか
- Drift AwarenessをAIの命令と誤認しないか
- Large MapでOpen IssueとDecisionを見つけられるか
- Evidenceを必要時に確認できるか
- Correction操作がGraph Editorに見えないか
- VisualからMapへ戻れるか

### 32.2 Prototype状態

最低限、次の6状態を用意する。

1. Session Start
2. Normal Discussion
3. Candidate Decision
4. Discussion Drift
5. Large Map
6. Visual Artifact available

同じMapの状態を保ったまま、Update前後の画面を比較できるようにする。

### 32.3 Validation Scenario

30〜45分相当のDiscussionを、Staticな状態遷移として再生する。

例:

1. Session Goalを表示
2. Topicを追加
3. IdeaとQuestionを追加
4. Topicを料金へ移動
5. 元Topicを未解決のまま保持
6. Candidate Decisionを追加
7. CandidateをConfirm
8. MapをLarge状態へ拡張
9. Visual Artifactを表示
10. Mapへ戻る

### 32.4 Participant Task

参加者には次の問いを与える。

- 今は何について話していますか
- 直前は何について話していましたか
- Confirmed Decisionは何ですか
- Candidate Decisionは確定していますか
- 未決のTopicはありますか
- 話が移ったことを自分で把握できますか
- Node名を修正できますか
- VisualからMapへ戻れますか

### 32.5 評価指標

定量・定性の両方を使う。

- Current Topicを回答するまでの時間
- Candidate / Confirmedの誤回答率
- Update前後で同じNodeを追跡できた割合
- Open / Unresolved Itemの発見率
- Drift Awareness後に参加者が元Topicを言及した割合
- Correction操作の完了率
- Mapを見続けることによる会話中断の自己申告
- 情報量、安心感、理解しやすさの主観評価

### 32.6 Layout比較

少なくとも次を同じScenarioで比較する。

- Graph-centric
- Focus-centric
- 推奨Hybrid Shared View

Primary Validation Questionに最も寄与するLayoutを確認する。見た目の好みだけで選ばない。

### 32.7 Stability検証

同じMapについてUpdate前後のStatic画像を比較し、次を記録する。

- 既存Nodeの位置変化
- Zoom変化
- Current Topicの視線移動
- 新Nodeの発見しやすさ
- Collapseによって隠れた情報の把握

## 33. Risks / Trade-offs

### 33.1 情報を増やすほど理解しにくくなる

Decision、Candidate、Flow、Evidence、Observationをすべて常時表示すると、Shared Understandingではなく画面読解作業になる。

Map、Status Rail、Flow、Evidenceを層に分け、常時表示する情報を少数に抑える。

### 33.2 Current Topic強調が強すぎる

Current Topicを強く強調すると、Discussion全体の構造や未解決Topicを失う可能性がある。

Current Topicは二重Border、Badge、Status Railで示し、全体Mapを縮小・非表示にしない。

### 33.3 Timelineを出すと画面が狭くなる

長いTimelineはFlow理解に役立つが、MapとStatusの面積を奪う。

MVPではRecent Flow stripを採用し、詳細履歴は明示操作で見る。

### 33.4 Correction UIが強すぎるとGraph Editorになる

自由なNode移動やRelation編集を許すと、会議中の修正負荷が高くなる。

MVPはRename、Hide、Merge、Confirm、Retract、Parking Lot、最新Correction Undoに絞る。

### 33.5 Candidate表示が会議を誘導する

Candidateが目立ちすぎると、参加者がAI案に引っ張られる。

点線、確認待ちLabel、専用領域、明示Confirmを使い、Confirmedと同じ見た目にしない。

### 33.6 AI Observationが発言者より目立つ

Observationを中央Toastや音声で出すと、AIがDiscussionの主役になる。

Observation Barへ限定し、同時1件、短文、Dismiss可能とする。

### 33.7 固定Laneによる表現力の制限

Hybrid Layoutは安定する一方、複雑な横断Relationを完全には表現しない。

Relationの全量表示より、Topic、Decision、Open Issueの理解を優先する。詳細RelationはEvidenceまたはDetail Viewへ送る。

### 33.8 Collapseによる見落とし

古いTopicやResolved Topicを折りたたむと、必要な情報を見落とす可能性がある。

件数、状態、未解決の有無をCollapsed Cardに残し、完全に消さない。

## 34. Open Questions

### OQ-3001: Current Topic切替の具体的な閾値

なぜ未決か:

RFC-0002ではCandidateとTransitionの生成までを決めたが、何回のEvidenceやどの継続性で画面Focusを切り替えるかはUXと解析性能の両方に依存する。

検証方法:

同じ会話Replayに対し、即時切替、Window継続、Human confirmの3条件をStatic Prototypeで比較する。

### OQ-3002: Candidateの表示密度

なぜ未決か:

Candidateを見せないとAIの整理が見えず、見せすぎると会議を誘導する。

検証方法:

Candidate専用Rail、Map Markerのみ、非表示の3案で誤認率と確認操作率を比較する。

### OQ-3003: Recent Flowの表示件数

なぜ未決か:

表示件数が少ないと経路が分からず、多いとMap面積を奪う。

検証方法:

3件、5件、7件のFlow stripを30分相当Scenarioで比較する。

### OQ-3004: Mapの標準表示容量

なぜ未決か:

共有Displayの距離、文字サイズ、Node密度の組み合わせが未検証である。

検証方法:

1920x1080と2560x1440のStatic Mockを異なるViewing distanceで評価する。

### OQ-3005: Multiple Active TopicsのSecondary表示

なぜ未決か:

Secondary Topicを表示しすぎるとCurrent Topicが曖昧になり、表示しないと並行議論が失われる。

検証方法:

Primaryのみ、Primary + 1 Secondary、Active Setの3案でTopic理解を比較する。

### OQ-3006: ObservationのCooldownと表示時間

なぜ未決か:

長すぎると邪魔になり、短すぎると見逃される。

検証方法:

Observation発生頻度を固定したReplayで、Dismiss率、見逃し率、会話中断を測定する。

### OQ-3007: Evidence drawerの操作方法

なぜ未決か:

共有画面では詳細を開く人と全員の視線を分ける必要がある。

検証方法:

右Drawer、中央Overlay、別Viewの3案で、Evidence確認時間とDiscussion中断を比較する。

### OQ-3008: Human Correctionを操作する主体

なぜ未決か:

会議参加者全員が操作するのか、進行役が操作するのかはRDで確定していない。

検証方法:

参加者全員操作と一人のOperator操作をStatic Prototypeで比較し、Correctionの遅延と会話中断を確認する。

### OQ-3009: AgreedとDecidedの追加需要

なぜ未決か:

MVPでは統合を推奨するが、PoCで「方向性の合意」と「正式決定」の区別が必要になる可能性がある。

検証方法:

Decision理解のインタビューとMinutesの確認で、2状態の混同が発生するかを見る。

### OQ-3010: Large MapでのManual Navigation

なぜ未決か:

Auto pan / zoomを避けると、参加者が古いTopicへ移動しにくくなる可能性がある。

検証方法:

Collapsed CardからのFocus移動、手動Scroll、Overview選択を比較する。

### OQ-3011: Visual ArtifactのMap内Marker

なぜ未決か:

Artifactを表示すると具体化に役立つが、生成物が議論の答えに見える可能性がある。

検証方法:

Artifact Marker、Status Railのみ、Artifactなしの3案をRFC-0004のPrototypeで比較する。

## 35. Deferred to RFC-0004

以下はVisual Artifactの詳細設計としてRFC-0004へ引き継ぐ。

- Visual生成Providerと生成Pipeline
- Artifact ResourceのVersion管理
- 同じTopicから複数Artifactを生成した場合の比較
- Artifactの採用・破棄・差し替え
- Artifact生成中・失敗時の詳細UX
- Visual Viewの具体的なLayout
- Visualが議論を誘導しすぎないための表示ルール
- Map上のArtifact Markerの具体的なInteraction

本RFCで決めたのは、MapからVisualへの入口、存在表示、遷移、戻りの境界までである。

## 36. Deferred to RFC-0005

以下はMeeting Minutesの詳細設計としてRFC-0005へ引き継ぐ。

- Session SummaryからMinutesへの具体的な遷移
- Minutesの文章構成
- Decision、Open Issue、Action Itemの最終出力
- Action Itemの担当者、期限、完了状態
- Parking LotとNext TopicsのMinutes表現
- Transcript EvidenceをMinutesへどの程度引用するか

本RFCでは、End Session後にSummary Viewへ移れる概念だけを定義した。

## 37. Decision

### Status

Proposed

### Recommended UX Architecture

Mapを中心にしたHybrid Shared Viewを推奨する。

- Header: Discussion Title、Session Time、Live状態
- Recent Flow strip: 直近のTopic遷移
- Map Canvas: 固定Topic Lane + 局所Tree / Card Stack
- Status Rail: Current Topic、Candidate、Confirmed、Open Issues、Actions、Parking Lot
- Observation Bar: 同時1件の控えめなAI Observation

### Chosen Map Presentation

固定Topic Laneを骨格にし、各Lane内を局所TreeまたはCard Stackで表現するHybrid型を採用候補とする。

- Current TopicはMapとStatus Railの両方で強調
- Candidate Decisionは専用確認待ち領域と関連Marker
- Confirmed Decisionは実線とCheck、Candidateは点線と確認待ちLabel
- QuestionとUnresolved ItemはPrimary ViewのOpen / Unresolved Itemsへ統合
- FlowはMap内のRelationと分離したRecent Flow strip

### Key Product Trade-off

自由なGraphや全面的なFocus表示より、固定Laneと限定的なProgressive Disclosureを選ぶことで、複雑なRelation表現と即時的な画面変化を抑える。

その代わり、Mapの視覚的安定性、遠くからの理解、Current Topicと全体構造の両立を優先する。

### Deferred to RFC-0004

Visual Artifactの生成方式、Artifact Version、比較、採用、Visual Viewの詳細、生成失敗時のUX。

### Deferred to RFC-0005

Session SummaryからMinutesへの詳細遷移、Minutesの文章構成、Action Itemの担当者・期限・完了状態、Parking LotとNext Topicsの出力。

### Accepted

なし。初稿のため、承認済みの項目はない。

### Rejected

MVPの推奨UXとしては、以下を採用しない。

- Map全体を毎回自動再配置するFree Graph中心表示
- Current Topicだけを全画面表示するFocus-only表示
- TokenやPartial TranscriptをMap Nodeとして常時表示する方式
- Candidate DecisionをConfirmed Decisionと同じVisualで表示する方式
- AIによる暗黙Decision確定を画面上のConfirmedとして扱う方式
- Driftを赤い警告や命令文で断定する方式
- Event Stream全体やTranscript全文を通常画面へ常時表示する方式
- 高度な自由編集を行うGraph Editor

**RFC Status: Proposed**
