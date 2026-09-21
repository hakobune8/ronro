# Requirements Document

## Discussion Map AI Facilitator MVP

| 項目 | 内容 |
| --- | --- |
| Status | Draft |
| Document Type | Requirements Document |
| Target | MVP |
| Last Updated | 2026-09-19 |

## 1. Purpose

本ドキュメントは、ディスカッションの内容をリアルタイムに可視化し、参加者がその可視化結果を見ながら議論を進められるAIファシリテーションシステムのMVP要件を定義するものである。

本システムは、一般的な「会議終了後に議事録を生成するAI」とは異なり、

> 会議中の議論そのものを可視化し、参加者が現在の議論状態を共有しながら話せること

を中心価値とする。

会議終了時の議事録生成は必要な機能ではあるが、本プロダクトの主目的ではない。

## 2. Background

会議やディスカッションでは、以下のような問題が頻繁に発生する。

- 議論が脱線する
- 何について議論していたのか分からなくなる
- 同じ内容を繰り返し議論する
- 意見と決定事項が混在する
- 参加者ごとに議論の理解が異なる
- 未決事項が埋もれる
- 新しい論点が増え続ける
- 抽象的な議論では参加者間のイメージが一致しない
- 会議終了時になって初めて「結局何が決まったのか」を整理する必要がある

ホワイトボードや付箋によるファシリテーションでは、これらの問題を軽減できる。

しかし実際には、

- 会話を聞く
- 内容を理解する
- 論点を分類する
- ホワイトボードを更新する
- 議論の進行を把握する

ことを同時に行う必要があり、専任のファシリテーターがいない会議では十分に実施されないことが多い。

そこでAIを利用し、会話内容を自動的に整理・可視化する。

## 3. Product Vision

プロダクトの中心コンセプトを以下とする。

> 話しているだけで、議論の地図がリアルタイムに育っていく。

参加者は共有ディスプレイに表示されたDiscussion Mapを見ながら話す。

Discussion Mapを見ることで、

- 今何について話しているのか
- どのような意見が出ているのか
- 何が決まったのか
- 何がまだ決まっていないのか
- どの論点からどの論点へ移ったのか
- 話が元のテーマから離れていないか

を把握できる状態を目指す。

## 4. Core Value

本プロダクトの中心価値は、

> Discussion Mapを会議の途中で確認できること

である。

Discussion Mapは会議終了後に見る成果物ではない。

会議中に継続的に表示され、参加者自身が、

- 認識の違い
- 脱線
- 議論不足
- 重複
- 未決事項
- 意見の関係

に気付くために使用する。

本プロダクトでは、

> Discussion Mapを「会議中の成果物」

と位置付ける。

一方、

> 議事録を「会議終了後の成果物」

と位置付ける。

## 5. Target Users

MVPでは、以下のような少人数のディスカッションを主な対象とする。

- 社内企画会議
- 新規事業検討
- プロダクト企画
- システム設計会議
- ブレインストーミング
- 要件整理
- 方針検討

想定人数は、おおむね2〜8名程度とする。

## 6. Target Environment

MVPでは以下の利用環境を想定する。

- 同一空間での対面会議
- 共有ディスプレイ1台
- 会議用PC
- マイク入力

スマートフォンや個人端末からの操作はMVPでは必須としない。

## 7. Primary User Journey

### 7.1 Discussion開始

ユーザーがシステムを起動する。

必要に応じて以下を入力する。

- Discussion Title
- Discussion Goal
- Background / Context

例:

**Title:**  
AIファシリテーションサービスのMVP検討

**Goal:**  
MVPで検証する中心価値を決める

ユーザーがDiscussionを開始する。

### 7.2 Discussion中

参加者は通常どおり会話する。

AIはその内容を継続的に理解し、共有画面のDiscussion Mapを更新する。

参加者はDiscussion Mapを見ながら議論を続ける。

### 7.3 Discussion Map確認

参加者はDiscussion Mapを見ることで、

- 現在の論点
- これまでに出た意見
- 議論中の選択肢
- 懸念
- 決定事項
- 未決事項

を把握する。

必要であればDiscussion Mapをきっかけとして、

> 「この論点に戻ろう」

> 「ここはもう決まっている」

> 「この部分だけまだ決まっていない」

など、人間同士で議論を修正する。

### 7.4 Visual Intervention

議論の内容によっては、Discussion Mapだけでは理解しづらい場合がある。

例えば、

- サービスコンセプト
- UIイメージ
- システム構成
- 空間配置
- ユーザー体験
- 複数案の違い

などである。

この場合、Discussion Mapの内容をもとに補助的なイメージを生成し、画面に表示する。

参加者は生成されたイメージを見ながら議論を続ける。

Visualは結論ではなく、

> 議論を具体化するための素材

として扱う。

### 7.5 Discussion終了

ユーザーがDiscussionを終了する。

システムは会議内容から議事録を生成する。

## 8. Discussion Map Requirements

Discussion MapはMVPの中心機能である。

以下を表現できること。

### 8.1 Discussion Topic

現在議論しているテーマや論点。

例:

> MVPの中心機能

### 8.2 Idea / Opinion

参加者から出た意見やアイデア。

例:

> リアルタイム可視化を中心にする

### 8.3 Option

複数の選択肢。

例:

~~~text
表示方式
├─ Mapのみ
├─ Map + Visual
└─ Visualへ画面切替
~~~

### 8.4 Question

まだ答えが出ていない問い。

例:

> Visual生成は自動で行うべきか？

### 8.5 Concern

懸念事項。

例:

> Map更新が頻繁すぎると見づらい

### 8.6 Decision

議論の中で決定した事項。

例:

> ✓ スマートフォンUIはMVP対象外

### 8.7 Unresolved Item

議論したが結論が出ていない事項。

例:

> ? Visual生成タイミング

### 8.8 Action Item

会議終了後に実行すべき項目。

例:

> RFCを作成する

### 8.9 Parking Lot

重要ではあるが、現在のDiscussionでは扱わない事項。

例:

> 将来的なTeams連携

## 9. Discussion Flow Requirements

Discussion Mapは議論の「構造」を示す。

それに加えて、本システムでは議論の「流れ」も扱う。

参加者が、

> どこからどこへ話が移動したか

を把握できることが望ましい。

例えば、

~~~text
MVP機能
 ↓
Discussion Map
 ↓
Visual生成
 ↓
料金モデル
 ↓
Discussion Mapへ戻る
~~~

といった流れである。

## 10. Current Topic

参加者が現在何について話しているかを、画面上で把握できること。

Discussion Map上で現在のTopicを視覚的に強調する。

これにより参加者は、

> 「いま何について話しているのか」

を共有できる。

## 11. Discussion Drift

本システムでは、議論が当初の論点から離れている可能性を参加者に知らせることを検討する。

ただし、AIが、

> これは脱線です

と断定することは避ける。

新しい話題への移行は、必ずしも悪い脱線とは限らないためである。

代わりに、

> 元の論点「MVP範囲」は未決のままです  
> 新しい論点「料金モデル」の議論が続いています

など、参加者自身が判断できる情報を提示する。

## 12. AI Observation

MVPではAIが音声で積極的に会議へ参加することは想定しない。

必要な場合のみ画面上に短いObservationを表示する。

例:

> **AI Observation**  
> 「価格」について2つの案が出ています。

> **AI Observation**  
> 「MVP範囲」はまだ未決です。

Observationは、

- 短い
- 非命令的
- 判断を押し付けない

ことを基本とする。

## 13. Visual Generation Requirements

### 13.1 Purpose

Visual生成の目的は、

> 口頭では共有しづらいイメージを参加者間で共有すること

である。

### 13.2 Possible Visuals

MVPでは以下のようなものを対象候補とする。

- Concept Image
- システム構成イメージ
- UXイメージ
- 空間配置イメージ
- フロー図
- 比較イメージ

### 13.3 Generation Trigger

最低限、ユーザーが明示的にVisual生成を実行できること。

例えば、

> [イメージ生成]

という操作を提供する。

将来的には音声による、

> 「これを図にしてみて」

なども検討する。

### 13.4 AI Proposal

AIがVisual生成を提案することも将来的には考えられる。

例:

> 💡 この内容をイメージ化できます

ただし、MVPではAIが勝手にVisualを大量生成しないことを重視する。

## 14. Display Requirements

MVPは共有ディスプレイで利用する。

16:9画面を基本とする。

主要な表示要素は以下。

~~~text
┌───────────────────────────────┐
│ Discussion Title        Time │
├──────────────────┬────────────┤
│                  │ Decisions  │
│                  │            │
│ Discussion Map   │ Open       │
│                  │ Issues     │
│                  │            │
│                  │ Actions    │
├──────────────────┴────────────┤
│ AI Observation                │
└───────────────────────────────┘
~~~

具体的なUIレイアウトは本RDでは規定しない。

## 15. Visual Display Modes

Visualを生成した場合、以下の体験を満たすこと。

- Discussion MapからVisualへ移動できる
- Visual表示中でも会議を継続できる
- Discussion Mapへ容易に戻れる
- 必要であればMapとVisualを同時確認できる

具体的な画面方式はRFCまたはDesign Documentで決定する。

## 16. Human Correction

AIの解析結果が常に正しいとは限らない。

そのため、参加者がDiscussion Mapを簡単に修正できることが望ましい。

最低限、以下を検討する。

- Node名の変更
- 不要Nodeの削除
- Decisionの修正
- 論点の統合
- Parking Lotへの移動

MVPでは高度なMap編集機能を目指さない。

目的は、

> AIが少し間違えても会議を止めずに済むこと

である。

## 17. Meeting Minutes

Discussion終了時に議事録を生成する。

最低限以下を含む。

### Meeting Information

- Discussion Title
- Date
- Duration

### Summary

Discussion全体の簡潔なまとめ。

### Decisions

決定事項。

### Main Discussion

主要な論点ごとの議論概要。

### Open Issues

未決事項。

### Action Items

会議後に必要な作業。

可能であれば、

- 担当者
- 期限

も含める。

### Parking Lot

今回扱わなかった事項。

### Next Topics

次回Discussionで扱う候補。

## 18. Functional Requirements

### FR-01 Session Start

ユーザーがDiscussion Sessionを開始できること。

### FR-02 Session End

ユーザーがDiscussion Sessionを終了できること。

### FR-03 Audio Input

会議中の音声を入力できること。

### FR-04 Speech Recognition

会話内容をテキストとして認識できること。

### FR-05 Discussion Understanding

会話内容から議論の意味を理解できること。

### FR-06 Topic Extraction

Discussion Topicを抽出できること。

### FR-07 Idea Extraction

主要な意見やアイデアを抽出できること。

### FR-08 Question Extraction

未解決のQuestionを抽出できること。

### FR-09 Concern Extraction

懸念事項を抽出できること。

### FR-10 Decision Extraction

決定事項を抽出できること。

### FR-11 Open Issue Extraction

未決事項を抽出できること。

### FR-12 Action Extraction

Action Itemを抽出できること。

### FR-13 Parking Lot

現在扱わない論点を管理できること。

### FR-14 Discussion Map

抽出した情報をDiscussion Mapとして表示できること。

### FR-15 Realtime Update

会話の進行に応じてDiscussion Mapを更新できること。

### FR-16 Current Topic

現在議論しているTopicを把握できること。

### FR-17 Discussion Flow

議論のTopic遷移を把握できること。

### FR-18 Drift Awareness

元の論点が未解決のまま他の話題へ移動した場合などに、その状態を参加者が認識できること。

### FR-19 AI Observation

議論状態に関する短い補助情報を表示できること。

### FR-20 Visual Generation

Discussion内容をもとにVisualを生成できること。

### FR-21 Visual Presentation

生成したVisualを参加者が確認できること。

### FR-22 Return to Map

Visual確認後、容易にDiscussion Mapへ戻れること。

### FR-23 Minutes Generation

Discussion終了時に議事録を生成できること。

## 19. Non-functional Requirements

### NFR-01 Realtime Experience

Discussion Mapの更新が、会議中の利用に耐える速度で行われること。

目標として、発言から画面反映まで数秒〜10秒程度を想定する。

### NFR-02 Session Duration

30〜60分程度のDiscussionで継続利用できること。

### NFR-03 Visual Stability

Discussion Mapの更新によって画面全体が頻繁に大きく変化しないこと。

参加者が、

> 「さっき見ていた論点がどこに行ったか分からない」

状態を避ける。

### NFR-04 Japanese First

MVPでは日本語Discussionを第一優先とする。

### NFR-05 Display Readability

共有ディスプレイから参加者が読めること。

小さすぎるテキストや過剰な情報表示を避ける。

### NFR-06 Continuous Discussion

Visual生成やAI処理によって会議そのものが停止しないこと。

### NFR-07 Recoverability

一部のAI処理が失敗しても、Discussion全体が失われないこと。

## 20. MVP Scope

MVPに含める。

- Session Start / End
- Audio Input
- Speech Recognition
- Discussion Understanding
- Discussion Map
- Current Topic
- Decision
- Open Issue
- Action Item
- Parking Lot
- Discussion Flow
- 基本的なDrift Awareness
- AI Observation
- Manual Visual Generation
- Visual Presentation
- Minutes Generation

## 21. Out of Scope

MVPでは以下を対象外とする。

- スマートフォンUI
- 個人端末からの参加
- 投票
- AIによる音声ファシリテーション
- 発言者評価
- 発言量ランキング
- 感情分析
- 性格分析
- 完全自動の議論進行
- AIによる最終判断
- オンライン会議サービスとの完全統合
- 高度なユーザー管理
- 大規模会議
- 多言語最適化

## 22. User Stories

### US-01

参加者として、現在何について議論しているかを一目で確認したい。

それにより、議論の方向を見失わないようにしたい。

### US-02

参加者として、これまでに出た主要な意見を確認したい。

それにより、同じ話を繰り返すことを減らしたい。

### US-03

参加者として、決定済みの内容を確認したい。

それにより、決まった話を再度議論することを減らしたい。

### US-04

参加者として、まだ決まっていない論点を確認したい。

それにより、議論漏れを減らしたい。

### US-05

参加者として、元の論点が未決のまま別の話題に移っていることに気付きたい。

それにより、無意識の脱線を減らしたい。

### US-06

参加者として、Discussion Mapだけでは理解しづらい内容をVisualとして確認したい。

それにより、参加者間のイメージを揃えたい。

### US-07

参加者として、AIが誤って整理した内容を簡単に修正したい。

それにより、AIの誤りによって会議を止めたくない。

### US-08

参加者として、会議終了時に議事録を自動生成したい。

それにより、会議後の整理作業を減らしたい。

## 23. Acceptance Criteria

MVPとして最低限以下を満たす。

### AC-01

ユーザーがDiscussion Sessionを開始・終了できる。

### AC-02

音声会話が継続的に認識される。

### AC-03

会話内容からDiscussion Mapが生成される。

### AC-04

会話の進行に合わせてDiscussion Mapが更新される。

### AC-05

主要なTopicがMap上に表示される。

### AC-06

現在議論しているTopicが把握できる。

### AC-07

Decisionが表示される。

### AC-08

Unresolved Itemが表示される。

### AC-09

Action Itemが表示される。

### AC-10

Parking Lotを扱える。

### AC-11

議論が別Topicへ移ったことを把握できる。

### AC-12

元のTopicが未決のまま残っている場合、それを認識できる。

### AC-13

Discussion Mapを見ながら30分以上Discussionを継続できる。

### AC-14

Discussion Mapに基づいたVisualを少なくとも1種類生成できる。

### AC-15

Visual確認後、Discussion Mapへ戻れる。

### AC-16

会議終了時にMinutesを生成できる。

## 24. Success Metrics

本MVPでは、文字起こし精度やAI精度だけで成功を判断しない。

最も重要なのは、

> Discussion Mapが存在することで、参加者のDiscussion体験が改善されるか

である。

PoC後に参加者へ以下を評価してもらう。

### SM-01

現在何を議論しているか分かりやすかった。

### SM-02

議論全体の構造を理解しやすかった。

### SM-03

話が逸れたことに気付きやすかった。

### SM-04

同じ話を繰り返すことが減った。

### SM-05

決定事項が分かりやすかった。

### SM-06

未決事項が分かりやすかった。

### SM-07

Visual生成が議論の理解に役立った。

### SM-08

Discussion Mapを見ながら話すことに価値を感じた。

## 25. Primary Validation Question

MVPで最も重要な検証項目を以下とする。

> Discussion Mapをリアルタイムに共有することで、人間同士のDiscussionは実際に進めやすくなるか？

この問いにYesと言えるかどうかを最優先する。

## 26. Secondary Validation Questions

以下も評価する。

### Q1

Discussion Mapによって脱線への自己認識が増えるか。

### Q2

同じ議論の繰り返しが減るか。

### Q3

決定事項の認識差が減るか。

### Q4

未決事項の取りこぼしが減るか。

### Q5

Visual生成によって抽象的な議論が具体化されるか。

### Q6

AIによる可視化が議論の邪魔にならないか。

## 27. Product Principles

今後の仕様判断では以下を優先する。

### Principle 1

議事録よりDiscussion中の価値を優先する。

### Principle 2

AIがDiscussionの主役にならない。

### Principle 3

参加者がDiscussion Mapを自然に確認できることを優先する。

### Principle 4

情報量より理解しやすさを優先する。

### Principle 5

AIの完全な正確性を前提にしない。

### Principle 6

AIの間違いを人間が簡単に修正できるようにする。

### Principle 7

Visualは答えではなく、議論するための素材として扱う。

## 28. Key Product Risks

### Risk 1 — 情報量過多

すべての発言をMapに表示すると、Mapが読めなくなる可能性がある。

必要なのはTranscriptの可視化ではなく、

> Discussionの意味構造の可視化

である。

### Risk 2 — Mapが気になりすぎる

参加者が画面更新ばかりを見て、Discussionそのものに集中できなくなる可能性がある。

### Risk 3 — AIの誤認

AIが発言の意味を誤り、

- 決まっていないことをDecisionにする
- 異なる意見をまとめる
- 重要な意見を落とす

可能性がある。

### Risk 4 — 過剰なAI介入

ObservationやVisual生成が頻繁すぎると、AIがDiscussionを妨害する可能性がある。

### Risk 5 — Visualへの誘導

生成されたイメージが具体的すぎると、参加者がそれに引っ張られ、他の可能性を考えにくくなる可能性がある。

## 29. Open Product Questions

以下はRD時点では確定しない。

### PQ-01

Discussion Mapでは、発言者をどの程度表示するか。

### PQ-02

DecisionをAIが自動確定するか、人間が確認するか。

### PQ-03

Discussion FlowをMap内で表現するか、別UIにするか。

### PQ-04

AI Observationをどの程度の頻度で表示するか。

### PQ-05

Visual生成をどのタイミングで提案するか。

### PQ-06

Visual表示時にDiscussion Mapを残すか。

### PQ-07

Mapが大きくなった場合、どの情報を省略するか。

### PQ-08

Speaker IdentificationをMVPへ含めるか。

これらはRFCおよびUX検証で決定する。

## 30. Suggested Validation Scenario

最初のPoCでは、実際の社内Discussionを利用する。

例:

> 「新規AIサービスのMVPをどうするか」

30〜45分程度Discussionする。

**条件A:**  
通常の会議

**条件B:**  
Discussion Mapあり

可能であれば比較する。

終了後に、

- 議論のしやすさ
- 脱線
- 決定事項理解
- 未決事項理解
- Discussion Mapの有用性

について評価する。

## 31. MVP Definition of Done

MVPは、

> AIが高精度な議事録を作れること

ではなく、

参加者が実際の会議で、

> 「このMapがあると話しやすい」

と感じられるところまで到達した状態をDefinition of Doneとする。

具体的には、

1. Discussionを開始する
2. 普通に会話する
3. Discussion Mapが徐々に形成される
4. Mapを見ながらDiscussionを続ける
5. Topicの移動や未決事項に気付く
6. 必要に応じてVisualを生成する
7. Visualを見ながらDiscussionする
8. Discussion Mapへ戻る
9. Decisionが蓄積される
10. Discussion終了
11. Minutesが生成される

という一連の体験が成立すること。

## 32. Relationship to RFC

本RDでは、

> 何を作るか

を定義する。

以下は本RDでは決定しない。

- 使用するLLM
- 使用するSTT
- Graphの内部Schema
- Graph更新方式
- DB構成
- API設計
- Streaming方式
- Frontend Framework
- Map描画Library
- Layout Algorithm
- Visual生成Provider
- Agent構成

これらについては、本RDを入力としてRFCで設計する。

想定するRFC例:

- RFC-0001: Discussion Model / Discussion Graph Architecture
- RFC-0002: Realtime Discussion Analysis Pipeline
- RFC-0003: Discussion Map UX and Layout
- RFC-0004: Visual Artifact Generation and Intervention
- RFC-0005: Meeting Minutes Generation

## 33. Final Product Statement

本プロダクトは、

> AIに会議を任せるためのシステムではない。

AIによって人間同士のDiscussionを可視化し、

> 自分たちが何を話しているのかを、自分たち自身が理解しやすくするためのシステム

である。

最終的に目指す体験は、

~~~text
Conversation
    ↓
Discussion Map
    ↓
Shared Understanding
    ↓
Better Discussion
~~~
