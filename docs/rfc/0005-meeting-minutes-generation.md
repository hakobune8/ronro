# RFC-0005: Meeting Minutes Generation

| 項目 | 内容 |
| --- | --- |
| Status | Proposed |
| Target | Discussion Map AI Facilitator MVP |
| Related RD | [Discussion Map AI Facilitator MVP 要件定義書](../requirements/discussion-map-ai-facilitator-mvp.md) |
| Depends on | RFC-0001: Discussion Model / Discussion Graph Architecture |
| Depends on | RFC-0002: Realtime Discussion Analysis Pipeline |
| Depends on | RFC-0003: Discussion Map UX and Layout |
| Depends on | RFC-0004: Visual Artifact Generation and Intervention |
| Last Updated | 2026-09-19 |

本RFCは、Discussion Session終了時に、会議中に蓄積された構造化情報をもとにMeeting Minutesを生成する設計を定義する。

本RFCは実装を開始するものではない。Minutesの役割、Source of Truth、Precedence、構成、Finalization、Review、Validation、Export、Privacy、Traceabilityを設計上の選択肢とともに整理する。

## 1. Problem Statement

### 1.1 MinutesはTranscript要約ではない

Discussion中には、発言、Partial Transcript、Final Transcript、Topic、Idea、Option、Concern、Decision候補、Open Issue、Action Item、Parking Lot、Human Correctionが蓄積される。

Transcript全文を終了時にLLMへ渡して要約するだけでは、次の問題が起こる。

- 発言量の多い内容が重要事項として強調される
- Candidate DecisionがConfirmed Decisionのように要約される
- Human Correction前の古いNode名や誤った分類が再導入される
- Open Issue、Parking Lot、Action Itemの区別が失われる
- 会議の最後に撤回された内容が残る
- Visual Artifactの仮説が正式な決定として扱われる
- OwnerやDue Dateが発言からではなくAIの推測で補われる
- 生成結果を後から根拠確認できない

### 1.2 Minutesの中心的な役割

Minutesは、Discussion中のCurrent Stateを会議後に利用できる文書へ変換するFinalization Stepである。

~~~text
Transcript Evidence
        +
Event Stream History
        +
Final Discussion Graph
        +
Human Corrections
        +
Session Metadata
        ↓
Final Discussion State
        ↓
Minutes Context
        ↓
Validated Minutes Draft
~~~

Minutesは会議中のDiscussion Mapの代替ではない。Mapが会議中のShared Understandingを支え、Minutesは会議後の確認・共有・引き継ぎを支える。

### 1.3 設計上の中心課題

本RFCでは次を決める。

- どの情報源を正式なMinutesの根拠とするか
- 情報源が矛盾した場合の優先順位
- Confirmed DecisionとCandidate Decisionの出力分離
- Topicを中心としたDiscussion Summaryの作り方
- Action Itemの候補・確認・未設定値の扱い
- Parking LotとOpen / Unresolved Itemの区別
- Next TopicとAI Suggestionの区別
- Visual ArtifactをReferenceとして扱う方法
- Human Correctionを最終文書へ反映する方法
- Finalization、Review、Regeneration、Exportの境界
- Deterministic ValidationとLLM Validationの責務

## 2. Goals / Non-goals

### 2.1 Goals

このRFCのGoalsは次のとおりである。

- Discussion Stateを中心にMinutesを生成する
- Confirmed Decisionだけを正式なDecisionとして扱う
- Candidate、未確認、未設定、不明を明示できる
- Human Correction後の最終状態を優先する
- Action ItemのOwnerとDue Dateを推測しない
- Open / Unresolved Item、Parking Lot、Next Topicを区別する
- Visual ArtifactをDiscussion Aidとして参照し、Decisionと混同しない
- 各Sectionの根拠を内部的に追跡できる
- 生成前後にDeterministic Validationを行う
- MarkdownをMVPの主要Export形式とする
- Minutes生成失敗時もSession SummaryやDiscussion Stateを失わない
- 人間が確認・修正・Section単位で再生成できる

### 2.2 Non-goals

以下はこのRFCでは詳細を決めない。

- Audio入力、STT、Realtime Analysisの実装
- Discussion MapのRealtime UX
- LLM、STT、画像生成Providerの選定
- Transcript全文を含む正式な逐語録
- 自動的なDecision確認やAction確定
- PDF、DOCX、メール、チャットへの配信
- 組織の承認Workflowや電子署名
- 高度な共同編集、同時編集、Conflict-free Replicated Data Type
- SessionをまたいだKnowledge Baseや検索
- 法務・セキュリティ・保存期間の最終ポリシー
- Minutesを契約書、議事録証明、正式な設計承認書にすること

## 3. 既存RFCから維持する前提

### 3.1 RFC-0001

次の責務分離を維持する。

> Transcript = Evidence  
> Event Stream = Discussion History  
> Discussion Graph = Current StateのMaterialized View

Minutes生成時には、まずEvent Streamから最終Graphを整合させる。Minutes GeneratorがTranscriptから独自にGraphやDecisionを再構成してはならない。

DecisionはCandidateとConfirmedを区別する。Human Correctionは上書きではなく履歴を持つ変更として扱う。

### 3.2 RFC-0002

- Final Transcriptを基準にDiscussion Analysisする
- Partial Transcriptだけで正規Graphを確定しない
- Event StreamはReplay可能である
- Analysis結果はIncrementalに生成される
- Analysis失敗時も、推測でGraphやMinutesを埋めない
- Session終了時にはFinal Utteranceと保留中のAnalysisを扱うFinalization境界が必要である

### 3.3 RFC-0003

- Confirmed Decisionは人間の明示確認を基本とする
- Candidate DecisionはConfirmed Decisionと異なる表示・状態である
- QuestionとUnresolved ItemはUI上統合可能である
- Human CorrectionはDiscussion中の操作として存在する
- Session終了後はDiscussion MapからSession Summaryへ移れる
- Minutesの詳細な文章構成、Action Item、Parking Lot、Next Topicsは本RFCで扱う

### 3.4 RFC-0004

- Visual Artifactは独立Resourceである
- ArtifactはTopic、Idea、Option等と関連付けられる
- ArtifactはVersion Chainを持つ可能性がある
- ArtifactはDraft / Discussion Aidであり、Decisionそのものではない
- Minutesでは、関連するArtifactをReferenceとして扱える
- queued / generating中のArtifactを完成済みVisualとして扱わない

### 3.5 Change Proposal

既存RFCの責務分離を変更する提案はない。

Action Itemについて、本RFCではDecisionと同じCandidate / Confirmed LifecycleをMVPのGraphへ追加しない。明示的な実行意図があるActionはGraphへ記録し、Owner / DueはEvidenceに明示された値またはHuman update_actionの値だけを使う。曖昧な実行意図はActionではなくOpen / Unresolved Itemへ投影する。

## 4. Product Principles

Minutes生成では、次の原則を優先する。

### Principle 1: StateがProseより先

文章を先に生成し、後からGraphに合わせるのではなく、Final Discussion Stateを先に固定し、そのProjectionとして文章を生成する。

### Principle 2: ConfirmedでないものをConfirmedとして書かない

Candidate、Tentative、Suggestion、推測は、正式なDecisionやNext Topicに昇格させない。Actionは明示的な実行意図がある場合だけ記録し、Owner / DueはEvidenceまたはHuman Correctionに明示された値だけを使う。

### Principle 3: Human CorrectionがAI推論に勝つ

Node rename、Merge、Decision解除、Parking Lot移動などの最新の有効なHuman Correctionを、古いAnalysis結果より優先する。

### Principle 4: 不明は不明のまま残す

Owner、Due Date、数値、合意状態、次回Agendaを根拠なく補完しない。必要な欄は未設定、確認待ち、記録なしとして表現する。

### Principle 5: 簡潔だが追跡可能

MinutesはTranscript全文ではない。一方、重要なDecision、Action、Open IssueがどのStateやEvidenceから出たかは内部的に追跡できるようにする。

### Principle 6: VisualはReference

Visual Artifactは議論を具体化する素材であり、生成されたことや閲覧されたことだけでDecision、採用案、正式設計にはならない。

### Principle 7: Review可能なDraft

MinutesはまずDraftとして生成し、人間が重要箇所を確認してからFinalizedまたはExportする。自動生成結果を無確認で正式文書としない。

## 5. Source of Truth

### 5.1 情報源の役割

Minutes生成に利用する情報源と責務を次のように分ける。

| 情報源 | 主な役割 | Minutesでの扱い |
| --- | --- | --- |
| Human Correction / Finalization Input | 人間が修正・確認した最終的な意図 | 最も強いStateの根拠 |
| Confirmed Discussion State | Confirmed Decision、最終Topic、最終Action等 | 正式なCurrent State |
| Discussion Graph | Session終了時のCurrent State全体 | Minutes Contextの中心 |
| Event Stream | 変更履歴、遷移、Correction、確認経緯 | 履歴・差分・Flowの根拠 |
| Final Transcript Evidence | 発言の根拠、短い引用、Timestamp | 補助Evidence。Stateを独自に昇格しない |
| Visual Artifact | Discussion Aidの参照、Topicとの関係 | Related Visual Reference。Decisionの根拠にしない |
| Session Metadata | Title、Goal、Date、Duration、Session状態 | Meeting Informationの根拠 |

### 5.2 GraphとEvent Streamの関係

Graphだけを読んでMinutesを作ると、最終状態は得られるが、なぜその状態になったか、Topicへ戻ったか、Decisionが変更されたかを説明しにくい。

Event Streamだけを読んでMinutesを作ると、過去の候補や撤回済みStateを誤って含める可能性がある。

したがって、MVPでは次の順序を推奨する。

1. Event Streamを必要範囲でReplayまたは検証する
2. Session終了時のDiscussion GraphをMaterializeする
3. Human CorrectionとConfirmed Stateを適用する
4. GraphをMinutes ContextのCurrent Stateとして使う
5. Event StreamとEvidenceを説明・検証・Flowに限定して参照する

### 5.3 Visual Artifactの位置付け

ArtifactがConfirmed Decisionに関連付けられていても、Artifact自体は正式Decisionではない。Artifactは次の情報を提供する。

- どのTopicに関連するか
- どのGraph Revisionから生成されたか
- どのVersionが最新か
- Draft / Superseded / Rejected等のStatus
- Discussion中にReferenceされたか

画像の見た目から、新しいDecisionやConstraintを推測してはならない。

## 6. Precedence Rules

### 6.1 推奨優先順位

同一の事実について情報源が矛盾する場合、MVPでは次の順序を推奨する。

1. 最新の有効なHuman Correctionまたは明示的なFinalization Input
2. Human ConfirmationによるConfirmed Decision、およびHuman update_actionによるActionの補正
3. Human Correction適用後のLatest Discussion Graph
4. Event Stream上の最新の有効なInterpretation / Candidate Event
5. Final Transcript Evidenceから参照できる発言
6. Visual Artifactの内容や生成結果
7. LLMの一般知識、会議文脈からの推測

最後の項目はMinutesの事実根拠として使用しない。

### 6.2 優先順位の意味

この順序は、すべての文章を上位情報源から生成するという意味ではない。各情報源の責務を分ける。

- Human CorrectionはLabel、State、Merge、Parking Lot移動を決める
- Confirmed Stateは正式Decisionを決める
- GraphはCurrent Topic、Open Issue、Action、Parking Lotの現在状態を決める
- Event Streamは変更経緯と重要なFlowを説明する
- TranscriptはEvidenceの確認と短い引用を提供する
- Artifactは関連するDiscussion Aidを参照するだけである

### 6.3 矛盾時の処理

上位情報源と下位情報源が異なる場合、下位情報源に合わせて上位Stateを戻してはならない。

例:

- DecisionがConfirmedになった後、古いTranscriptに反対意見が残っていても、現在のDecisionをCandidateへ戻さない
- Decision解除のHuman Correctionがある場合、以前のConfirmed Decisionを正式Decisionへ再掲しない
- Node Merge後に古いNode名がEventに残っていても、古い名前をMain Discussionの見出しに使わない
- OwnerがEvidenceにない場合、会話の役割や話者順からOwnerを推測しない

重大な不整合でCurrent Stateを安全に確定できない場合は、MinutesをFinalizedにせず、DraftにNeed Reviewを付ける。

## 7. Minutes Structure

### 7.1 標準構成

MVPの標準構成は次のとおりとする。

1. Meeting Information
2. Executive Summary
3. Decisions
4. Pending Confirmation
5. Main Discussion
6. Open / Unresolved Items
7. Action Items
8. Parking Lot
9. Next Topics
10. Related Visual Artifacts

### 7.2 必須Sectionと条件付きSection

毎回すべての見出しを表示すると、情報がない会議でも空欄が増える。

MVPでは次を推奨する。

- 必須: Meeting Information、Executive Summary
- Decisionがある場合に表示: Decisions
- Candidate Decisionがある場合に表示: Pending Confirmation
- 有意なTopicがある場合に表示: Main Discussion
- Open / Unresolved Itemがある場合に表示: Open / Unresolved Items
- Action Itemがある場合に表示: Action Items
- Parking Lotがある場合に表示: Parking Lot
- Explicit Next Topicまたは明示的なSuggestionがある場合に表示: Next Topics
- Readyな関連Artifactがある場合に表示: Related Visual Artifacts

空のSectionを省略しても、Executive Summary内で「Confirmed Decisionなし」「Action Itemなし」などの重要な不在を必要に応じて明示する。

### 7.3 SectionとSource

| Section | 主なSource |
| --- | --- |
| Meeting Information | Session Metadata |
| Executive Summary | Goal、Final Graph、Confirmed State、重要なOpen Issue |
| Decisions | Confirmed Decision、Human Correction |
| Pending Confirmation | Candidate Decision、Tentative State |
| Main Discussion | Topic、Idea、Option、Concern、重要Event、Evidence |
| Open / Unresolved Items | Question / Unresolved State、関連Evidence |
| Action Items | Action State、Human Correction、明示Evidence |
| Parking Lot | Parking Lot State |
| Next Topics | Explicit Next Topic、Parking Lot、Open Issue、Suggestion |
| Related Visual Artifacts | Artifact ResourceとTopic Reference |

## 8. Executive Summary

### 8.1 Summaryの役割

Executive SummaryはTranscriptの短縮版ではない。Session Goalに対して、何を議論し、何がConfirmedになり、何が残ったかを短く伝える。

含める情報の優先順位:

1. Session Goal
2. Main Topics
3. Key Confirmed Decisions
4. Important Open / Unresolved Items
5. Action Itemの概要

Candidate DecisionやAI Suggestionが重要な場合は、Confirmedと分けた「確認待ち」として短く含める。

### 8.2 推奨長さ

MVPでは次を目標とする。

- 3〜5文程度、または3〜5個の短いBullet
- 通常の30〜60分Sessionで、共有画面またはMarkdown冒頭から短時間で読める長さ
- Decision、Open Issue、Actionの詳細をSummaryへ重複記載しすぎない

厳密な文字数制限は設けず、Main Discussionの詳細をSummaryへ流し込まないことを優先する。

### 8.3 Summaryの書式例

~~~markdown
## Executive Summary

Discussion Mapを中心としたMVPの価値と対象範囲を議論した。
MVPではDiscussion Mapを中心機能とし、スマートフォンUIは対象外とすることを確認した。
Visual ArtifactのPrototype作成が次の作業として記録されている。
Visual生成タイミングの詳細は未解決である。
~~~

上記の文章は、対応するConfirmed State、Action State、Open Stateが存在する場合だけ生成する。

## 9. Decisions

### 9.1 正式Decision

正式なDecisions Sectionには、Final Discussion StateでConfirmedとなっているDecisionのみを出力する。

Decisionの最低限のProjection:

- Decision ID
- Decision内容
- Status: Confirmed
- 必要に応じたRationaleまたはConstraint
- Explicitly RejectedされたOptionがある場合の短い補足
- Internal Source References

AIがTranscriptから「おそらく決まった」と判断しただけの内容は、Decisionsへ入れない。

### 9.2 Tentative / Agreedの扱い

RFC-0003では、AgreedとDecidedをMVPのPrimary Viewで複雑に分けない方向を推奨している。本RFCでも、Minutesの正式DecisionsはConfirmedに統一する。

ただし、会議中に「方向性としては賛成」「いったんこの案で考える」といった表現があり、正式確認がない場合は次のように出力できる。

- Pending Confirmation
- Tentative Direction
- 確認待ち

これらをDecisions Sectionの正式項目として表示してはならない。

### 9.3 Rejected Option

Rejected Optionは、次のいずれかが明示されている場合に限り記録する。

- 参加者が明示的に不採用とした
- Human CorrectionでRejectedにした
- Confirmed Decisionの理由として、採用しないOptionが明示された

単に最終Graphに残っていないOptionを、AIがRejectedと推測してはならない。

表示例:

~~~markdown
### Decision: スマートフォンUIはMVP対象外

- Status: Confirmed
- Related option not selected: スマートフォンUIをMVPに含める案
~~~

### 9.4 Decision変更履歴

通常のMinutesでは、現在のConfirmed Decisionを中心に表示する。過去の変更履歴をすべて列挙しない。

ただし、次の条件を満たす重要な変更は短く記載できる。

- 過去のConfirmed DecisionがHuman Correctionで解除・変更された
- 変更が現在のActionやOpen Issueの理解に影響する
- Event Streamに明示的な変更経緯がある

表示例:

> 以前の「Map + Visualを常時表示する」案は再検討され、現在はMapをPrimary Viewとする方針である。

推測した経緯や、単なる意見の変化をDecision変更履歴として書かない。

### 9.5 Decision Evidence

Decisionには内部的にEvidence ID、Decision Event ID、Graph Revisionを関連付ける。User-visibleな引用はSection 18の方針に従う。

## 10. Candidate Decisions

### 10.1 別Sectionで扱う

Session終了時にCandidate Decisionが残っている場合、Decisionsとは別にPending Confirmation Sectionへ出力する。

~~~markdown
## Pending Confirmation

- Visual生成タイミングを自動化するか
  - Status: Candidate / Confirmation required
  - Note: Discussion中に複数案が出たが、Confirmed Decisionは記録されていない
~~~

Candidateの文言は、Analysis結果をそのまま正式Decisionに昇格させないために、候補・確認待ちであることが視覚的に明らかな表現にする。

### 10.2 Candidateの条件

Candidate Decisionを出力してよい条件:

- Final GraphにCandidateとして存在する
- Candidateが撤回・否定・Mergeによって無効になっていない
- Confirmed Decisionと矛盾する場合、未確認候補として表示する理由がある

Candidateを出力しない条件:

- 既にConfirmedまたはRejectedになっている
- Human Correctionで削除・無効化された
- Transcriptにだけ存在し、Graph上のCandidate Eventがない
- Visual Artifactの内容から逆算しただけである

### 10.3 Finalization時の扱い

FinalizationはCandidateをConfirmedへ自動遷移させない。

人間がReview中にCandidateを確認した場合は、まずHuman Confirmation EventまたはCorrectionとしてStateを更新し、その後にMinutesを再生成する。Minutesの文章上だけでCandidateをConfirmedに変えてはならない。

## 11. Main Discussion

### 11.1 生成単位の比較

| 方式 | 利点 | 欠点 | MVP適性 |
| --- | --- | --- | --- |
| Topic単位 | Discussion Graphと対応し、Open IssueやDecisionと関連付けやすい | Topic間の時間的流れを省略しやすい | 高い |
| Chronological | 会議の流れを再現しやすい | 発言順の要約になり、重要Stateが埋もれやすい | 低い |
| Importance-based | 重要な内容を上位に置ける | 重要度の判定が主観的になりやすい | 条件付き |
| Topic + selected Flow | 構造と重要な経緯を両立できる | Topic選択とFlow抽出が必要 | 高い |

### 11.2 推奨方式

MVPでは、Topic-basedを基本とし、重要なTopic遷移だけを文章へ補足するHybrid方式を推奨する。

Topicの順序は、次の優先順位で決める。

1. Session Goalに直接関係するTopic
2. Confirmed Decisionに接続するTopic
3. Open / Unresolved ItemまたはAction Itemを持つTopic
4. Discussion中に主要なTopicとして扱われた順序

この順序は、単純な発言回数ランキングだけで決めない。

### 11.3 Topic Summaryの内容

各Main Topicは、次の順序で短く記述する。

1. Topicの問いまたは目的
2. 主なIdea / Opinion / Option
3. Concernまたは制約
4. Topicに関連するDecision、Open Issue、Action
5. 必要な場合だけ、Topicへの移動・戻りのFlow

Transcriptの発言順を逐一書かず、最終Graphに残った意味構造を中心にする。

### 11.4 Discussion Flowの反映

全Topic遷移を列挙しない。次のように理解に寄与するFlowだけを文章へ含める。

- 一度保留したTopicへ戻った
- 別Topicを経由した後にDecisionがConfirmedになった
- 元Topicが未決のまま別Topicへ移った
- Visual Artifactを見た後にDiscussionが具体化した

Flowが内容理解に寄与しない場合、Main DiscussionのTopic Summaryだけを出力する。

## 12. Open / Unresolved Items

### 12.1 QuestionとUnresolvedの関係

Discussion MapではQuestionとUnresolved ItemをUI上統合できる。Minutesでは、読者が「何が未解決なのか」を理解しやすいよう、SectionはOpen / Unresolved Itemsへ統合する。

内部的には次の属性を保持してもよい。

- Question: 問いの形式で表現されたもの
- Unresolved Item: 議論したが結論が出ていない状態

ただし、表示を分けることを必須にしない。

### 12.2 推奨出力

~~~markdown
## Open / Unresolved Items

- Visual生成を自動で行うか
  - Type: Open Question
  - Status: Unresolved
  - Related topic: Visual Intervention
  - Next confirmation: 未設定
~~~

「質問が存在する」ことと「結論がない」ことを別々のSectionへ分けるより、MVPでは一つのOpen / Unresolved Itemsにまとめ、必要時だけType Labelを表示する方が読みやすい。

### 12.3 Resolvedとの区別

Final GraphでResolved、Confirmed、RejectedとなったItemをOpen / Unresolved Itemsへ残さない。ただし、Main DiscussionやDecisionの説明に、解決した問いとして短く触れることはできる。

## 13. Action Items

### 13.1 最低限の項目

Action Itemは、最低限次の項目を持つProjectionとする。

| 項目 | 扱い |
| --- | --- |
| Description | 会議後に実行する内容。発言の意図を変えない範囲で短く正規化 |
| Owner | 会話中に明示されたPersonまたはTeam。なければ未設定 |
| Due Date | 明示された期限。なければ未設定 |
| Status | open、completed、cancelled。GraphのAction Stateをそのまま反映 |
| Related Topic | Actionが発生したTopic |
| Evidence Reference | 明示発言、Action Event、Human Correction |

### 13.2 OwnerとDue Date

AIは次を推測してはならない。

- 発言者がOwnerである
- Actionを提案した人が必ず担当者である
- チーム名や役職から担当者が決まる
- 「次回まで」「早めに」から具体的な日付が決まる
- Session DateからDue Dateを自動計算できる

明示されていない場合は、次のように出力する。

~~~markdown
| Action | Owner | Due | Status |
| --- | --- | --- | --- |
| Visual Artifact Prototypeを作成する | 未設定 | 未設定 | open |
~~~

相対的な表現が明示された場合は、その表現を保持してもよい。

> Due: 次回まで（具体日未設定）

SessionのTimezone、基準日、相対表現の意味が不明な場合、具体的な日付へ変換しない。

### 13.3 Completed

会議中に「完了した」「作成済み」と明示された場合のみCompletedを記録する。Minutes生成時点で期限が過ぎていることや、ArtifactがReadyになったことからCompletedを推測しない。

### 13.4 Action Descriptionの正規化

「誰かがやる」「あとで検討する」のような曖昧な発言を、具体的な作業へ拡張しない。

出力は、次を保つ範囲で短くする。

- 動詞
- 対象
- 条件
- 明示されたOwner
- 明示されたDue

不明な部分は未設定とする。

## 13. Action Item Confirmation

### 13.1 方式比較

| 方式 | 内容 | 利点 | 欠点 | MVP適性 |
| --- | --- | --- | --- | --- |
| AIが直接Confirmed Actionにする | 明示的な作業発言を即時正式Actionとして出力 | 操作が少ない | 曖昧な発言や仮案を正式Actionにしやすい | 低い |
| Candidate / Confirmedを分ける | AI抽出はCandidate、人間確認後にConfirmed | Decisionと同じ安全性を持てる | 状態表示が増える | 高い |
| 全Actionを人間が個別確認 | すべてのActionに確認を要求 | 誤登録を抑えやすい | 会議の流れとReview負荷を増やす | 中 |

### 13.2 推奨

MVPでは、Actionの存在にDecisionと同じConfirmed Workflowを設けない。

- 明示的な実行意図があるAction Event: Action Itemsへ出力
- Owner / Due: AnalyzerのEvidence明示値、またはHuman update_actionの値だけを出力
- Owner / Dueが不明: 未設定として出力
- 実行意図が曖昧: Action Itemとして出力せず、Open / Unresolved Itemsへ出力
- 誤抽出の修正: Session中のHuman CorrectionでArchiveまたはupdate_actionし、Final Graphを再生成

これにより、全Actionの個別確認操作を要求せず、Actionの存在を推測で増やさない境界を保つ。

### 13.3 Minutesでの表示

Action Items Sectionでは、Actionの存在とOwner / Dueの未設定を混同しない。Action自体にCandidate / Confirmed Labelを付けず、未設定値は未設定として出力する。

~~~markdown
## Action Items

| Description | Owner | Due | Status |
| --- | --- | --- | --- |
| RFCの初稿を作成する | A | 未設定 | open |
| Visual Artifact Prototypeを作成する | 未設定 | 未設定 | open |
~~~

Owner / Dueを確認・修正する場合は、Minutes本文だけを直接書き換えるのではなく、Human update_actionでFinal Graphを更新してから再生成する。

## 14. Parking Lot

### 14.1 Open Issueとの区別

Parking Lotは、重要性がないという意味ではなく、現在のDiscussionでは扱わないと明示されたTopicである。

Open / Unresolved Itemとの違い:

| 種類 | 意味 | Minutesでの表現 |
| --- | --- | --- |
| Open / Unresolved | 議論した、または今のGoalに関係するが結論がない | Open / Unresolved Items |
| Parking Lot | 現在のSessionでは扱わないと整理した | Parking Lot / Deferred Topics |

AIは、議論されなかったTopicをParking Lotへ推測追加してはならない。

### 14.2 推奨出力

Final GraphでParking LotにあるItemだけを、別Sectionへ出力する。

~~~markdown
## Parking Lot

- 将来的なTeams連携
  - Status: Deferred
  - Note: 今回のMVP Discussionでは扱わない
- スマートフォン用Controller
  - Status: Deferred
~~~

Parking Lotから次回Topicへ自動昇格させない。Explicit Next Topicとして明示された場合だけ、Next Topicsでも参照する。

### 14.3 Parking Lotから戻った場合

Final StateでParking LotからActive TopicまたはOpen Itemへ移動されている場合、Parking Lot Sectionには残さない。必要ならMain DiscussionまたはFlowの中で「後半に議論対象へ戻った」と短く示す。

## 15. Next Topics

### 15.1 入力の優先順位

Next Topicsの候補は、次の順で扱う。

1. 人間が明示した次回Topic、次回Agenda
2. Session中にConfirmedまたは明示されたFollow-up
3. Parking Lotから人間が次回扱うと指定したItem
4. Open / Unresolved Itemからの確認候補
5. AI Suggestion

### 15.2 ExplicitとSuggestionの分離

Minutesでは、Explicit AgreementとAI Suggestionを同じAgendaのように表示しない。

~~~markdown
## Next Topics

### Explicitly Agreed

- 次回、Visual Artifact Prototypeを確認する

### Suggested

- Visual生成タイミングを次回の検証項目にする
  - Source: Open / Unresolved Item
  - Status: AI suggestion / Not agreed
~~~

Explicit Next Topicがない場合、AI SuggestionだけでNext Topics Sectionを作らないことを既定とする。Suggestionを表示する場合は、Draft Reviewで明示的にSuggestionと表示する。

### 15.3 AIがAgendaを決めない

AIは、未解決項目から次回Agendaを提案できるが、次回に扱うことを決定しない。Next TopicのPriority、参加者、期限、会議時間も推測しない。

## 16. Visual Artifact References

### 16.1 出力方式の比較

| 方式 | 内容 | 利点 | 欠点 |
| --- | --- | --- | --- |
| 採用されたArtifactのみ | adoptedと明示されたものだけ | 正式成果物との関係が明確 | RFC-0004ではadoptedを必須にしていない |
| 最新Versionのみ | Artifact Familyごとに最新Ready Versionを表示 | 簡潔で現行案を追いやすい | 過去の比較文脈を失う |
| すべて | 生成済みArtifactをすべて表示 | 履歴を残せる | MinutesがGallery化する |
| Topicごとの関連表示 | Final GraphのTopicとReferenceがあるものを表示 | Discussion構造と一致する | Referenceの条件が必要 |

### 16.2 推奨

MVPでは、Topicごとに関連付けられたReady Artifactを表示し、同じArtifact Familyでは最新Versionを基本とする。

次の条件を満たすArtifactをRelated Visual Artifactsへ含める。

- Generation StateがReadyである
- Final Graph上のTopic、Idea、Option等にReferenceがある
- Session中に生成または明示的にReferenceされた
- Failed、Rejected、または無関係なArtifactではない

旧Versionが次のDiscussion理解に重要な場合だけ、最新Versionの補足として表示する。

~~~markdown
## Related Visual Artifacts

### Discussion Map UI

- Discussion Map UI Concept v2
  - Type: concept_image
  - Status: Draft / Current version
  - Generated from: Discussion Graph Revision 151
  - Reference: Artifact A v2

### System Architecture

- Architecture Diagram v1
  - Type: diagram
  - Status: Draft
  - Reference: Artifact B v1
~~~

Artifactの見た目や内容からDecision、採用案、正式なArchitectureを推測しない。

### 16.3 生成中・失敗Artifact

Session終了時にArtifactがqueuedまたはgeneratingの場合、完成済みRelated Visualとして表示しない。

必要であれば、SummaryまたはDraft Reviewに次の情報を示す。

> Visual Artifact generation pending: Discussion Map UI

Failed Artifactは通常のMinutesから除外し、再試行情報はArtifact管理またはReview UIで扱う。

## 17. Artifact Status

### 17.1 MVPで表示するStatus

RFC-0004のArtifact StatusをそのままMinutesの正式採用状態へ変換しない。

| Artifact Status | Minutesでの表示 |
| --- | --- |
| draft | Draft |
| current Version | Current version |
| superseded | Previous version、原則は折りたたみ |
| rejected | 原則非表示。比較の説明に必要な場合だけRejectedと表示 |
| queued / generating | Related Visualには含めずPendingとして扱う |
| failed | Related Visualには含めない |

### 17.2 adoptedを作らない理由

RFC-0004ではArtifactをDiscussion Aidとして扱い、adoptedを正式設計採用の意味にしない方針である。Minutesで採用と表示すると、ArtifactがDecisionへ昇格したように見える。

正式に採用された設計や仕様がある場合は、Confirmed Decisionまたは別の正式成果物として記載し、Artifact Statusから自動生成しない。

## 18. Evidence / Citation

### 18.1 TraceabilityとCitationの分離

すべてのMinutes出力は、内部的にはSource Referenceを持つべきである。一方、読者へTranscriptやEvidenceを常に見せる必要はない。

次を分けて設計する。

- Internal Traceability: Generator、Validator、Review UIが使う必須情報
- User-visible Evidence: 読者が根拠を確認するための任意または限定表示

### 18.2 方式比較

| 方式 | 利点 | 欠点 | MVP適性 |
| --- | --- | --- | --- |
| Transcript snippetを本文に埋め込む | 根拠がその場で読める | 長くなり、Privacyと逐語録化のリスク | 低い |
| Timestampだけ表示 | 短く、確認対象を示せる | AudioやTranscript UIが必要 | 高い |
| Evidence IDのみ | 内部追跡しやすい | 一般読者には意味が薄い | 中 |
| UIのEvidence drawerのみ | 本文が簡潔 | Export後は追跡しにくい | 中 |
| Exportにも短いReferenceを付ける | 文書単体でも追跡できる | TimestampやIDが常にあるとは限らない | 高い |

### 18.3 推奨

MVPでは次を推奨する。

1. Decision、Action、Open / Unresolved ItemごとにInternal Source Referenceを必ず保持する
2. Review UIではEvidence drawerまたは詳細PanelからEvidence ID、Timestamp、短いSnippetを確認できる
3. Markdown Exportでは、可能な場合にEvidence IDまたはTimestampを短く付ける
4. Transcript全文や長い引用は既定Exportに含めない
5. Summaryや一般的なMain Discussion文には、すべての発言のCitationを付けない

例:

~~~markdown
### Decision: スマートフォンUIはMVP対象外

- Status: Confirmed
- Evidence: E-042 / 00:18:20
~~~

Timestamp、Speaker、Evidence IDが利用できない場合は、存在しないReferenceを作らず、内部Graph RevisionまたはEvent IDだけを保持する。

## 19. Transcript Quotes

### 19.1 原則

Minutesは逐語録ではないため、Transcriptからの直接引用は必要な場合だけ行う。

引用する条件:

- DecisionやRationaleの意味が要約だけでは曖昧になる
- 重要なConstraintの表現を保持する必要がある
- Review中に根拠確認のため短いQuoteを残す価値がある

### 19.2 Policy

- 短い一文または一部句に限定する
- Final Transcript Evidenceから取得する
- Speaker名は必要性とPrivacyを確認してから含める
- Citationの代わりに長い発言列を載せない
- CandidateをConfirmedに見せるQuoteを選ばない
- Partial Transcriptを引用しない

通常のMarkdown ExportではQuoteを省略し、Evidence IDまたはTimestampだけを付けることを推奨する。Quoteが必要な場合はReview UIで追加・削除できる。

## 20. Human Corrections

### 20.1 Final Graphへの反映

Session終了時のMinutes Contextは、Human Correctionが適用されたFinal Graphから作成する。

| Correction | Minutesへの反映 |
| --- | --- |
| Node rename | 最新の名前だけを見出しと本文に使う |
| Merge | Canonical Nodeへ統合し、旧Node名を重複表示しない |
| Decision解除 | Decisionsから除外し、CandidateやOpenへ自動復帰させない |
| Decision修正 | 修正後のStateとLabelを使う |
| Parking Lot移動 | Parking Lot Sectionへ移し、Open Issueとして残さない |
| Node削除 | 現在Stateから除外。履歴は内部Traceabilityだけに残す |

### 20.2 古いAnalysisの再導入防止

Event Streamに古いCandidate、旧Node名、撤回済みDecisionが残っていても、最新の有効なCorrectionより下位の情報として扱う。Minutes Generatorが全Eventを単純結合してはいけない。

### 20.3 Draft後のCorrection

Minutes Draft生成後にHuman Correctionが行われた場合、Draftを自動でFinalizedにしない。

次のいずれかを行う。

- DraftをStaleとして表示し、Final Graphから再生成する
- 影響するSectionだけを再生成する
- 人間が修正内容を確認してから再生成する

人間がMinutes本文を直接編集した部分は、再生成時に上書きしない。

## 21. Session Finalization

### 21.1 推奨Flow

~~~text
End Session
    ↓
Stop Audio / Close Input
    ↓
Flush Final STT and Final Utterance
    ↓
Finalize or mark pending Analysis
    ↓
Replay / Materialize Final Discussion Graph
    ↓
Apply Human Corrections and Confirmed State
    ↓
Classify Decisions, Candidates, Open Items, Actions, Parking Lot
    ↓
Build Immutable Minutes Context Snapshot
    ↓
Generate Minutes Draft
    ↓
Deterministic Validation
    ↓
LLM / Semantic Validation
    ↓
Draft Review
    ↓
Confirm / Finalize
    ↓
Export Markdown
~~~

### 21.2 Finalizationでしないこと

Finalizationは、単にSessionを閉じる処理であり、次を自動的に行わない。

- Candidate DecisionをConfirmedにする
- ActionをDecisionと同じConfirmed Stateへ自動昇格する
- Open IssueをResolvedにする
- Parking LotをNext Topicにする
- Visual ArtifactをDecisionにする
- OwnerやDue Dateを補う
- Transcriptから欠落した情報を推測する

### 21.3 Pending Analysis

Session終了時にFinal STTまたはAnalysisがまだ完了していない場合、処理を無制限に待たせない。

最後に整合したGraphをBase Stateとして保持し、未反映の範囲を次のいずれかで示す。

- Analysis pending
- Finalization incomplete
- Review required

欠落区間を推測で埋めず、MinutesをDraftのまま扱う。待機時間や再処理の具体的な閾値はOpen Questionとして残す。

### 21.4 Immutable Minutes Context

Minutes生成前に、Session Metadata、Final Graph Revision、Human CorrectionのRevision、参照Event、Evidence、Artifact ReferenceをContext Snapshotとして固定する。

Minutesの再生成はこのSnapshotを基準に行う。新しいCorrectionや再解析結果が入った場合は、新しいMinutes Context Revisionを作る。

## 22. Review Before Final

### 22.1 Reviewの必要性

Minutesは会議後に共有される文書であり、Hallucinated Decision、誤Owner、誤Due Dateが残る影響が大きい。そのため、MVPでもDraft Reviewを必須の設計要素とする。

ただし、すべての文を参加者が一行ずつ承認するWorkflowは、MVPの単純さを損なう。

### 22.2 MVPの最低限Review機能

- Draftとして表示する
- Decisions、Pending Confirmation、Action Items、Open Itemsを構造化表示する
- Owner、Due Date、Statusを個別に修正できる
- 不要なItemを除外できる
- Section単位でRegenerateできる
- Manual EditしたSectionを保護できる
- Evidence Referenceを確認できる
- Confirm / Finalizeを明示操作できる

### 22.3 Review UIの優先順

高リスクな情報を先に確認する。

1. Decisions
2. Action ItemsのOwner、Due、Status
3. Pending Confirmation
4. Open / Unresolved Items
5. Summary
6. Main Discussionの文章

確認操作が行われていない情報を、確認済みと表示しない。

### 22.4 Confirm Minutes

Confirm Minutesは、文章の完全な真実を保証する操作ではなく、参加者がDraftを共有可能なMinutesとして確認したことを示す。

Confirm時には、次を保存する。

- Minutes Revision
- Final Discussion State Revision
- Reviewerまたは確認主体が利用可能な場合の識別子
- Confirmed At
- 未解決のWarning

## 23. Minutes State

### 23.1 候補状態

| State | 意味 |
| --- | --- |
| draft | Generatorが作成し、まだFinalizedされていない |
| finalized | 人間が確認し、共有・Export可能とした |
| stale | Source StateまたはHuman Correctionが変わり、再確認が必要 |
| generation_failed | Draft本文の生成に失敗した |

### 23.2 reviewedを必須Stateにしない

reviewedを独立したStateにすると、どの範囲をレビューしたか、再生成後にReviewが無効になる条件が複雑になる。

MVPでは、reviewedをStateにせず、Review操作とRevision Metadataとして保持する案を推奨する。必要になった場合に、Section単位のReview履歴を追加する。

### 23.3 Finalizedの条件

最低限、次を満たしてからFinalizedにする。

- Deterministic Validationを通過している
- Decisionsに未ConfirmedのItemが混ざっていない
- ActionのOwner / Dueが未設定なら未設定と表示されている
- Human Correction後のGraph Revisionを参照している
- 重大なWarningがReviewで確認されている
- 人間がConfirm操作を行った

## 24. Regeneration

### 24.1 Section単位を基本とする

MVPでは、Summary、Decisions、Main Discussion、ActionsなどをSection単位で再生成できるようにする。全体再生成は明示操作に限定する。

### 24.2 Human Editの保護

人間が編集したSectionまたはFieldは、再生成時に自動上書きしない。

次の方式を推奨する。

- SectionにManual Edit Lockを付ける
- Regenerate前に影響範囲を表示する
- Locked Sectionを再生成する場合は、別Draft Revisionを作る
- 元のManual Editを破棄するには明示確認を求める

### 24.3 再生成のSource

再生成は同じMinutes Context Snapshotを使うか、新しいFinal Graph Revisionを使うかを明示する。

- 文章表現だけを直す: 同じSnapshot
- Human CorrectionやDecision確認を反映する: 新しいSnapshot
- Promptや長さを変える: 新しいMinutes Draft Revision

再生成したSectionが、以前はなかったDecisionやOwnerを追加する場合、Deterministic Validationで拒否またはReview Warningとする。

## 25. Export Formats

### 25.1 比較

| Format | 利点 | 欠点 | MVP適性 |
| --- | --- | --- | --- |
| Markdown | 構造化、差分確認、Repositoryやツールとの相性がよい | レイアウトは表示環境に依存 | 高い |
| Plain Text | 単純で移植しやすい | 表やLink、構造を保ちにくい | 中 |
| PDF | 共有・印刷しやすい | Renderer、Layout、再生成が必要 | 低い |
| DOCX | Office利用者に便利 | 生成と編集互換性が複雑 | 低い |

### 25.2 推奨

MVPの正式ExportはMarkdownとする。

- DraftまたはFinalizedの状態を冒頭に明示する
- Related ArtifactとEvidence Referenceは、利用可能ならLinkまたはIDで参照する
- Export時にTranscript全文を自動添付しない
- PDF、DOCX、Plain TextはMarkdownからの変換または後続RFCで扱う

Finalized前にExportする場合、ファイル先頭にDraft、Review required、未確認Candidateなどの状態を明示する。

### 25.3 Markdownの安定性

同じMinutes Contextと同じGenerator設定から、意味上不要な差分が増えないようにする。表の列、Section順、Labelを固定し、文章のみを再生成しても構造が崩れないようにする。

## 26. Session Summary View

### 26.1 方式比較

| 方式 | 内容 | 利点 | 欠点 |
| --- | --- | --- | --- |
| 直接Minutes | End Session直後に本文Minutesを表示 | 画面遷移が少ない | 生成待ちとDraft確認が混ざる |
| Summaryのみ | 構造化Stateだけを表示 | 即時性が高い | 詳細な文書が別操作になる |
| Summary → Minutes | Summaryを先に表示し、Minutes Draftへ進む | 即時確認と文書生成を分離できる | Viewが一つ増える |

### 26.2 推奨

MVPでは、Discussion MapからSession Summaryへ移り、Summaryを先に表示し、その後にMinutes Draftを生成・表示する流れを推奨する。

~~~text
Discussion Map
      ↓ End Session
Session Summary
      ↓ Generate / Review
Minutes Draft
      ↓ Confirm
Finalized Minutes
~~~

Session SummaryはMinutesとは別のSource of Truthではない。Final Graphと同じFinalization Snapshotから作る即時Projectionである。

### 26.3 Summary生成失敗時

Minutesの文章生成に失敗しても、Final GraphからDeterministicに作れるSession Summaryは表示できるようにする。

Summaryには、少なくとも次を含める。

- Confirmed Decisions
- Pending Confirmation
- Open / Unresolved Items
- Action Items（Owner / Dueの未設定を含む）
- Main Topics

このSummaryをMinutes完成と誤認させず、Minutes Draft generation failedなどの状態を表示する。

## 27. Session Summary

### 27.1 役割

Session Summaryは、会議終了直後に参加者が「何が決まり、何が残ったか」を確認するための短いState Viewである。

Minutesは、後から共有・保存・編集する文書であり、Main Discussion、Evidence、Artifact Referenceなどを含む。SummaryはMinutesの要約結果ではなく、同じFinalization Snapshotから先に作る簡潔なProjectionである。

### 27.2 推奨内容

~~~text
Session Summary

Confirmed Decisions
  - Discussion MapをMVPの中心とする

Pending Confirmation
  - Visual生成タイミング

Open / Unresolved
  - Visualを自動生成するか

Actions
  - Visual Artifact Prototypeを作成する
    Owner: 未設定 / Due: 未設定

Main Topics
  - MVP範囲
  - Discussion Map UI
  - Visual Intervention
~~~

### 27.3 SummaryのReview利用

SummaryはMinutes本文の生成前に、Final Stateの欠落や誤りを発見するためにも利用する。

例えば、Summaryに本来あるべきDecisionがない場合、Minutesを再生成する前にDiscussion GraphまたはHuman Correctionを修正する。Summaryに直接Decisionを書き足しても、正式なSource Stateは変わらない。

## 28. Discussion Flow in Minutes

### 28.1 全遷移を出力しない

Discussion FlowはEvent Streamに履歴として保持されるが、Minutesに全遷移をそのまま出力しない。

全遷移を出力すると、次の問題が生じる。

- Minutesが時系列Logになる
- 重要なDecisionやOpen Issueが埋もれる
- Topicへ戻ることの意味が、単なる画面遷移に見える
- Sessionの長さに比例して文章量が増える

### 28.2 重要なFlowのみ記載

次のいずれかに該当するFlowだけをMain Discussionに短く含める。

- Topicを保留して別Topicへ移り、後で戻った
- 元Topicが未解決のまま別Topicの議論が進んだ
- 別Topicでの議論が、後のDecisionやActionに直接つながった
- Visual Artifactを見た後に同じTopicの理解が具体化した

表示例:

> MVP範囲を一度保留してVisual Interventionを検討した後、MVPの対象外項目を再確認した。

「脱線」とは断定せず、EventとFinal Stateから確認できる事実だけを書く。

### 28.3 Flowの内部Reference

Flow文には、内部的にTopic Transition EventまたはGraph Revisionを紐付ける。通常のMarkdown本文に全Event IDを表示する必要はない。

## 29. Chronology vs Topic Structure

### 29.1 比較

| 方式 | 内容 | 利点 | 欠点 |
| --- | --- | --- | --- |
| Chronological Minutes | 発言・Topicの時間順に記載 | 会議の経緯を追いやすい | 逐語録に近づき、Stateが埋もれる |
| Topic-based Minutes | Topicごとに整理 | Decision、Open、Actionと結び付きやすい | 時間的な流れを失いやすい |
| Hybrid | Topic別を基本に、重要Flowだけ追記 | Current Stateと経緯を両立 | 何を重要Flowとするかの判断が必要 |

### 29.2 MVP推奨

Topic-basedを基本とし、重要なDiscussion Flowだけを補足するHybridを採用する。

Main DiscussionのTopic順は、Goalへの関連、Confirmed Decision、Open / Unresolved、Actionの有無を優先する。単純な時刻順や発言量順だけでは決めない。

Chronological情報が必要な場合は、Meeting Informationの時刻、Evidence Timestamp、または短いFlow文で補う。

## 30. Speaker Attribution

### 30.1 基本方針

Discussion Mapと同様に、Minutesでも「誰が多く話したか」より「何が議論されたか」を優先する。

デフォルトでは、Main DiscussionやExecutive SummaryにSpeaker名を常時挿入しない。

### 30.2 Speaker名を含める場合

次の条件を満たす場合だけ、Speaker名を含めることを検討する。

- Action Ownerとして明示された
- DecisionやCorrectionの実行主体を区別する必要がある
- ユーザーがSpeaker Attributionを有効にした
- Evidence確認に不可欠である

Speaker IdentificationがOptionalまたは不確かな場合、名前を推測・補完しない。

### 30.3 発言者評価の禁止

Minutesに次を含めない。

- 発言量ランキング
- 発言者別の貢献度
- 性格・感情・評価
- Speakerから推測したOwner

Action Ownerは、明示的な割当てがある場合の責務情報としてのみ扱う。

## 31. Privacy

### 31.1 MVPの最小方針

Minutesは、会議後に共有される可能性があるため、Transcriptより情報を絞る。

既定で含めないもの:

- Transcript全文
- 全発言のSpeaker名
- Speakerごとの発言量や評価
- Visual Providerへ送信されたPrompt全文
- 無関係なTopicやParking Lot
- 機密情報を含む長いQuote

### 31.2 含める可能性があるもの

- Discussion Title、Date、Duration
- 明示されたAction Owner
- Decision、Open Issue、Actionに必要なEvidence ID / Timestamp
- Userが確認した短いQuote
- Related Visual ArtifactのID、Type、Status、Link

### 31.3 Export時のPrivacy

Markdown Exportは、Draft Reviewで確認した範囲の情報だけを出力する。Speaker名やEvidence snippetを追加する場合、ユーザーが共有範囲を理解できるようにする。

Retention、削除、組織外共有、Providerの保存はSecurity ArchitectureおよびPrivacy Policyで決める。Minutes RFCでは、最小化、明示性、推測禁止を必須とする。

## 32. Hallucination Prevention

### 32.1 禁止事項

Minutes Generatorは次を生成してはならない。

- 存在しないDecision
- CandidateをConfirmedとしたDecision
- 推測したOwner
- 推測したDue Date
- TranscriptやStateにない数値
- AIが勝手に作ったNext Step
- Visualから推測したDecision、Requirement、Architecture
- 発言者順から推測した責任者
- Parking Lotを自動的に次回Agendaへ昇格すること
- 不明な情報を自然な文章で埋めること

### 32.2 Closed-world原則

構造化Fieldは、Final Minutes Contextに存在するValueだけから生成する。Contextに存在しないValueが必要な場合は、次のいずれかにする。

- 未設定
- 不明
- 確認待ち
- Sectionから除外

文章を自然にする目的で、空欄を一般常識や会議慣行で補ってはならない。

### 32.3 矛盾とWarning

GeneratorまたはValidatorが次を検出した場合、FinalizedにせずDraft ReviewでWarningを示す。

- DecisionsにConfirmed Stateにない内容がある
- Action Ownerに根拠がない
- Due DateがEvidenceにない
- CandidateがConfirmedと同じLabelで出力されている
- Artifactの画像説明がDecisionとして書かれている
- Human Correction前のNode名が残っている

## 33. Traceability

### 33.1 Internal Traceability

Minutesの各Structured ItemとSectionは、次のSource Referenceを内部的に保持する。

| Output | 参照候補 |
| --- | --- |
| Decision | Decision Node ID、Confirmation Event、Correction Event、Evidence ID |
| Candidate Decision | Candidate Node ID、Analysis Event、Evidence ID |
| Main Topic | Topic Node ID、関連Idea / Option / Concern、Topic Flow Event |
| Open Item | Question / Unresolved Node ID、最新State Event、Evidence ID |
| Action | Action Node ID、Action Event、Owner / DueのEvidence |
| Parking Lot | Parking Lot Node ID、Move / Correction Event |
| Next Topic | Explicit Next Topic Event、またはSuggestionのSource |
| Artifact | Artifact ID、Source Topic ID、Artifact Version、Graph Revision |

### 33.2 Snapshot

Minutes Contextには、少なくとも次を保存する。

- Session ID
- Final Graph Revision
- Event Streamの対象範囲またはReplay Revision
- Human Correction Revision
- Session Metadata Revision
- Generator設定の識別情報
- Validation結果

このSnapshotにより、同じSessionを再解析・再生成した場合も、当時のMinutesを説明できる。

### 33.3 User-visible Citationとの境界

Internal Traceabilityは必須である。User-visible Citationは、読みやすさ、Privacy、利用環境に応じて縮約できる。

Citationを非表示にしても、内部Referenceを削除してはならない。

## 34. Minutes Generation Pipeline

### 34.1 推奨Pipeline

~~~text
Session Metadata
        +
Final Discussion Graph
        +
Human Corrections
        +
Confirmed / Candidate State
        +
Relevant Event Stream
        +
Final Transcript Evidence
        +
Related Artifact References
        ↓
Minutes Context Builder
        ↓
Structured Minutes Projection
        ↓
Minutes Generator
        ↓
Deterministic Validation
        ↓
Semantic / Consistency Validation
        ↓
Minutes Draft
        ↓
Human Review
        ↓
Finalized Markdown
~~~

### 34.2 Structured Minutes Projection

LLMへ直接、全文TranscriptとGraphを渡してMarkdownを書かせるのではなく、先に構造化されたMinutes Projectionを作る。

Projectionの概念的な内容:

~~~text
Minutes Projection
  ├─ meeting_information
  ├─ confirmed_decisions[]
  ├─ pending_confirmations[]
  ├─ topics[]
  ├─ open_items[]
  ├─ confirmed_actions[]
  ├─ candidate_actions[]
  ├─ parking_lot[]
  ├─ explicit_next_topics[]
  ├─ suggested_next_topics[]
  ├─ related_artifacts[]
  └─ source_references[]
~~~

Projectionに存在しない項目は、文章生成で追加できない。

### 34.3 Contextの圧縮

30〜60分のSessionでも、全TranscriptをMinutes GeneratorのContextに常時含めない。

- Current Final Graphを中心にする
- Topicごとに必要なRelevant Evidenceだけ選ぶ
- Event Streamは重要なChange、Confirmation、Correction、Flowに絞る
- Summaryは補助的な説明として使い、Source of Truthにはしない
- 未確認Candidateを明示的に分離する

## 35. Validation Layer

### 35.1 Deterministic Validation

ルールで検証できるものは、LLMに任せない。

最低限、次を検証する。

- Decisionsの各ItemがConfirmed Decision集合に存在する
- Candidate DecisionがDecisionsへ混入していない
- Human Correctionで削除・解除されたItemが再出力されていない
- Action Ownerが許可されたEvidenceまたはHuman Inputに存在する
- Due Dateが明示EvidenceまたはHuman Inputに存在する
- Artifact IDが実在し、StatusとVersionが一致する
- Parking Lot ItemがOpen Issueへ重複出力されていない
- Explicit Next TopicとAI SuggestionのLabelが区別されている
- Required Metadataが存在する
- Manual Edit LockされたSectionが上書きされていない

### 35.2 LLM / Semantic Validation

LLMによる検証は、事実の追加を許可するためではなく、次を検出するために使う。

- Stateに対する文章の意味ずれ
- 文章内でのDecisionとCandidateの矛盾
- Summaryと詳細Sectionの矛盾
- Topicの重複・読みづらい要約
- 人間にとって不自然な欠落

LLM Validatorが「このDecisionはおそらく正しい」と判断しても、Confirmed集合へ追加してはならない。

### 35.3 Validation失敗時

Validation失敗時は、次のいずれかにする。

- DraftにWarningを付けてReviewへ送る
- 該当Sectionだけ生成失敗として保持する
- 重大なHallucinationがある場合、Finalizedを拒否する

Validatorが自動修正する場合も、修正後にDeterministic Validationを再実行する。

## 36. Alternatives

### 36.1 比較

| 案 | 内容 | Accuracy | Hallucination risk | Context quality | Implementation complexity | Replay | Traceability | Human Correctionとの整合 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A. Transcript Summarization | Transcript全文をLLMで要約 | 低〜中 | 高 | 文脈は広いがNoiseが多い | 低 | 弱い | 弱い | 低い |
| B. Graph-first Minutes | Final GraphだけでTemplate生成 | 高いState整合 | 低い | Flowや理由が弱い | 低〜中 | 強い | 強い | 高い |
| C. Structured State + Evidence Hybrid | State中心、必要時だけEvent / Evidence参照 | 高い | 低い | 構造と根拠を両立 | 中 | 強い | 強い | 高い |
| D. Full Event Reconstruction | Event Streamを全Replayし全文を再構成 | 条件付き | 中 | Flowは豊富 | 高い | 強い | 中〜強 | 中 |

### 36.2 Transcript Summarizationの問題

Transcript Summarizationは実装の入口が簡単だが、Product Principleと一致しない。

- CandidateとConfirmedの区別を失いやすい
- Human Correctionを自然に反映しにくい
- Parking LotとOpen Issueの分類が不安定
- OwnerやDue Dateを補完しやすい
- 生成結果の再現性と検証が弱い

### 36.3 Graph-firstの限界

Graph-firstはHallucinationを抑えやすいが、次の情報が不足する場合がある。

- Decisionに至った重要な理由
- Topicを保留して戻ったFlow
- OwnerやDueが明示された発言の正確な表現
- Evidence Timestamp

必要な場合だけEvent StreamとFinal Transcript Evidenceを参照する設計が必要である。

## 37. Recommended Architecture

### 37.1 推奨方式

MVPでは、Structured State + Evidence Hybridを採用する。

具体的には次の構造とする。

1. Finalizationで最終GraphをMaterializeする
2. Human CorrectionとConfirmed Stateを適用する
3. GraphからStructured Minutes Projectionを作る
4. Event Streamから重要なFlow、変更履歴、確認経緯だけを追加する
5. Final Transcript Evidenceから必要なCitationと短い根拠を取得する
6. ArtifactはReferenceとして追加し、内容を事実として取り込まない
7. Projectionを閉じた入力としてMinutes本文を生成する
8. Deterministic ValidationとSemantic Validationを行う
9. Draft Review後にFinalizedし、MarkdownへExportする

### 37.2 推奨責務境界

~~~text
Session Finalizer
  ├─ Final STT / Analysis completion state
  ├─ Graph materialization
  └─ Human correction application
          ↓
Minutes Context Builder
  ├─ Structured state projection
  ├─ Relevant event selection
  ├─ Evidence references
  └─ Artifact references
          ↓
Minutes Generator
  └─ Prose / Markdown rendering
          ↓
Validation Layer
  ├─ Deterministic checks
  └─ Semantic consistency checks
          ↓
Review / Finalize / Export
~~~

### 37.3 変更しない境界

Minutes Generatorは次を直接行わない。

- Discussion Graphの状態変更
- DecisionのConfirmed遷移
- Action Ownerの決定
- Artifactの採用状態変更
- Transcriptの再解析
- Event Streamの削除・書換え

必要な変更は、Human Correction、Finalization、または再解析の別操作として先に行う。

## 38. Example

### 38.1 Discussion

~~~text
A: 「MVPはDiscussion Mapを中心にしましょう」
B: 「スマホも入れますか？」
A: 「スマホは今回は外しましょう」
B: 「了解です」
A: 「次回までにVisual ArtifactのPrototypeを作ります」
~~~

### 38.2 Stateの解釈

この例だけでは、DecisionのConfirmed条件が人間の明示Confirmationを要求するRFC-0001 / RFC-0003の方針と、発話上の同意をどう結び付けるかに注意が必要である。

以下は、Session中またはReview中に人間の確認操作が記録された場合のMinutes例である。

~~~text
Confirmed Decision
  D1: MVPはDiscussion Mapを中心とする
  D2: Smartphone UIはMVP対象外

Action Item
  A1: Visual ArtifactのPrototypeを作成する
  Owner: 未設定
  Due: 次回まで（具体日未設定）
~~~

ActionのOwnerは発言者Aと推測しない。Aが自分をOwnerとして明示した場合だけOwnerをAとする。

### 38.3 期待されるMinutes

~~~markdown
# Meeting Minutes: AIファシリテーションサービスのMVP検討

## Meeting Information

- Date: 未設定
- Duration: 未設定
- Goal: MVPで検証する中心価値を決める
- Status: Draft

## Executive Summary

MVPの中心価値をDiscussion Mapに置く方向を確認した。
スマートフォンUIは今回のMVP対象外とした。
Visual ArtifactのPrototype作成が次の作業候補として記録されているが、担当者と具体的な期限は未設定である。

## Decisions

- MVPはDiscussion Mapを中心とする
  - Status: Confirmed
- Smartphone UIはMVP対象外
  - Status: Confirmed

## Action Items

| Description | Owner | Due | Status |
| --- | --- | --- | --- |
| Visual ArtifactのPrototypeを作成する | 未設定 | 次回まで（具体日未設定） | open |

## Open / Unresolved Items

- Visual Artifact Prototypeの具体的な仕様と生成タイミング
  - Status: Unresolved
  - 根拠がないため、次回Topicへの自動昇格は行わない
~~~

「B: 了解です」だけを根拠に自動確認を許可しないPolicyの場合、D1とD2はDecisionsではなくPending Confirmationへ出力される。その場合も、Minutes Generatorが独自にDecisionsへ昇格してはならない。

## 39. Failure Cases

### 39.1 Session途中で終了

Sessionが予定より早く終了しても、最後に整合したFinal GraphからSummaryとMinutes Draftを生成する。

- Durationは実測値を使う
- 未完了のFinal STT / AnalysisはPendingとして示す
- 未確認CandidateをConfirmedにしない
- Main Discussionの欠落を推測で補わない
- DraftにSession incompleteまたはReview requiredを付ける

### 39.2 Candidate Decisionのみ残る

Decisions Sectionには出力しない。Pending Confirmationへ出力し、Confirmed Decisionが存在しないことを明示する。

### 39.3 Action Owner不明

Ownerを未設定とする。Speaker、提案者、最も関係が深いTopicの担当者を推測しない。

### 39.4 Minutes生成失敗

次の順でRecoveryする。

1. Session SummaryをFinal Graphから表示する
2. Structured Minutes Projectionを保存する
3. 失敗したSectionまたは全体をRetry可能にする
4. Draftが不完全ならFinalizedを禁止する
5. 必要ならProjectionをMarkdownの表形式でExport候補にする

失敗中に新しいDecision、Action、Ownerを作らない。

### 39.5 Transcript欠落

GraphとEvent Streamに存在するStateを優先し、欠落Transcriptから内容を再構成しない。

Evidenceが必要なSectionでは、Evidence unavailableまたはCitation unavailableと表示できる。Evidenceがないことだけを理由に、既にConfirmedのStateをCandidateへ戻さない。

### 39.6 Event / Graph不整合

Event StreamとGraphのRevisionが一致しない場合、最新に見える方を無条件に採用しない。

- 最後に整合したGraph RevisionをBaseにする
- 不整合範囲を記録する
- DraftにNeed Reviewを付ける
- Event ReplayまたはMaterializer再実行を行う
- 解消前にFinalizedしない

### 39.7 Artifact生成中にSession終了

queued / generatingのArtifactはRelated Visual Artifactsの完成項目に含めない。必要ならPendingとして別表示する。

Artifactの完成を待つためにMinutes Finalizationを無期限に停止しない。完成後にMinutesへ追加する場合は、新しいMinutes Draft Revisionとして扱う。

### 39.8 Human Correction後に生成

Correction前に作成されたDraftはStaleとする。Correction適用後のFinal Graph Revisionから再生成し、旧Draftを自動Finalizedしない。

## 40. Open Questions

### OQ-5001: Minutes Reviewを誰が行うか

* 未決理由: RDは参加者によるHuman Correctionを求めるが、全員がReviewするか、OperatorがReviewするかを定めていない
* 検証: 参加者全員Reviewと代表者ReviewのPrototypeで、誤Decision、Review時間、会議後の負担を比較する

### OQ-5002: Action ItemのReview操作

* 未決理由: Action自体は明示的実行意図で記録するCanonical方針だが、Owner / Dueの補正や誤抽出のArchiveをどのReview画面で行うかは未定義
* 検証: Session中のupdate_action、Session Summary、Minutes Reviewでの補正操作を比較する

### OQ-5003: Evidence CitationのExport形式

* 未決理由: Timestampは簡潔だが、外部Export先で参照できない場合があり、SnippetはPrivacyと長文化のリスクがある
* 検証: Citationなし、ID / Timestamp、短いSnippetの3案で、読者の根拠確認率とMinutesの読みやすさを測る

### OQ-5004: SummaryからMinutes Draftまでの許容時間

* 未決理由: Session終了直後の即時性と、最終Analysis・Validationの精度にトレードオフがある
* 検証: 30〜60分のReplayで、Summary表示、Draft生成、Review開始までの時間と欠落率を測る

### OQ-5005: Executive Summaryの適切な長さ

* 未決理由: 短すぎるとOpen Issueが見えず、長すぎるとMain Discussionと重複する
* 検証: 3文、5文、Bullet中心のPrototypeを比較し、理解度とReview時間を確認する

### OQ-5006: Speaker Attributionの既定値

* 未決理由: Speaker名はAction確認に有用だが、PrivacyとDiscussion理解の単純さを損なう可能性がある
* 検証: Speakerなし、Actionのみ、Decisionにも表示の3案で、誤帰属とPrivacy評価を比較する

### OQ-5007: AgreedとDecidedのMinutes上の区別

* 未決理由: RFC-0003ではMVP統合を推奨しているが、会議後に方向性と正式決定の差が重要になる可能性がある
* 検証: Pending Confirmationを含むMinutesを読んだ参加者が、正式Decisionを正しく識別できるか確認する

### OQ-5008: Minutes Revisionの保存粒度

* 未決理由: Section単位の再生成とManual Edit保護にはRevisionが必要だが、全履歴保存は複雑になる
* 検証: 全体Revision、Section Revision、最新のみの3案で、誤編集からの復元とStorage負荷を評価する

### OQ-5009: Related Visual Artifactの選択範囲

* 未決理由: 最新Versionだけでは比較文脈が失われ、すべて表示するとMinutesがGallery化する
* 検証: 最新のみ、Topic関連、明示Referenceのみの3案で、Minutes読者が必要なArtifactを見つけられるか比較する

### OQ-5010: Pending Analysisの待機条件

* 未決理由: 長く待てば欠落を減らせるが、Session終了後のFinalizationが停止する
* 検証: 実際のSTT / Analysis遅延をReplayし、待機時間と未確定Sectionの発生率を測る

### OQ-5011: MinutesのPrivacy / Retention

* 未決理由: Speaker名、Evidence、Artifact Linkの保持期間は、利用組織と外部ProviderのPolicyに依存する
* 検証: 共有先、削除要求、外部Exportの代表シナリオを用いたPrivacy Reviewで決める

### OQ-5012: Relative Due Dateの正規化

* 未決理由: 「次回まで」「今週中」を具体日へ変換すると誤りやTimezone問題が発生する
* 検証: 原文保持、基準日付き正規化、未設定の3案で、利用者の誤解と修正率を比較する

### OQ-5013: Minutes生成失敗時のFallback Export

* 未決理由: Projectionを表形式で出せば情報を失わないが、通常Minutesとの境界が曖昧になる
* 検証: Summaryのみ、Projection Export、Retry待ちの3案で、失敗時の回復可能性と誤認率を評価する

## 41. Validation Plan

### 41.1 Static Fixture

実装前に、Event Stream、Final Graph、Human Correction、Evidence、Artifactを固定したReplay Fixtureを作る。

最低限、次のFixtureを用意する。

- Confirmed DecisionとCandidate Decisionが混在するSession
- Decision解除とNode MergeがあるSession
- Owner / Due Dateが明示されないAction
- Parking LotとOpen Issueが両方あるSession
- Visual Artifactのv1、v2、supersededがあるSession
- Final Transcriptが一部欠落するSession
- Event / Graph Revisionが不整合なSession

### 41.2 Prototypeで確認する項目

1. Confirmed Decisionが正しくDecisionsへ出る
2. Candidate Decisionが正式Decisionに誤表示されない
3. Human Correction後の名前、Merge、Decision解除、Parking Lot移動が反映される
4. Owner / Due Dateを捏造しない
5. Open / Unresolved Itemが漏れない
6. Parking LotとOpen Issueが混同されない
7. Explicit Next TopicとAI Suggestionが区別される
8. Visual ArtifactがDecisionに見えない
9. Minutesを読めば会議結果を把握できる
10. Transcript要約だけの案より有用である
11. Reviewで高リスク項目を短時間に発見できる
12. Manual Editが再生成で上書きされない

### 41.3 比較実験

同じFixtureで、次の3方式を比較する。

- Transcript Summarization
- Graph-first
- Structured State + Evidence Hybrid

参加者または評価者には、どのDecisionがConfirmedか、どのActionが未設定か、どのOpen Issueが残っているかをMinutesから回答してもらう。

### 41.4 Golden Output

最初から文章の完全一致を正解としない。次をStructured Golden Outputとして定義する。

- Confirmed Decisionの集合
- Candidate / Pendingの集合
- Open / Unresolvedの集合
- ActionのDescription、Owner、Due、Status
- Parking Lotの集合
- Explicit Next Topicの集合
- Artifact Referenceの集合

文章表現の評価は、このGolden Outputと人間による有用性評価の後に行う。

## 42. Success Metrics

### 42.1 Accuracy

- Decision Accuracy: Confirmed Decisionが正しく出力される割合
- Candidate Separation Accuracy: Candidateが正式Decisionへ混入しない割合
- Action Item Accuracy: DescriptionとStatusの正確性
- Owner Accuracy: 明示Ownerを正しく保持する割合
- Due Date Accuracy: 明示Dueを正しく保持する割合
- Open Issue Recall: Final Graphの重要Open Itemを漏らさない割合
- Parking Lot Separation: Parking LotとOpen Issueを混同しない割合
- Artifact Reference Accuracy: 実在するRelevant Artifactだけを参照する割合

### 42.2 Safety

Hallucinated Decisionは重大エラーとして扱う。

- Hallucinated Decision Count
- 推測Owner Count
- 推測Due Date Count
- Visualから推測されたDecision Count
- Human Correction前の状態が再導入された件数

これらは平均品質で相殺せず、個別にReview阻止または重大Warningの対象とする。特にHallucinated Decisionは、MVPでゼロを目標に検証する。

### 42.3 User Experience

- Minutes Review Time
- Manual Edit Count
- Regeneration Count
- Finalizedまでの時間
- User-rated usefulness
- 会議結果を正しく回答できた割合
- Transcript Summarizationとの差分に対する評価

Manual Edit Countが少ないことだけを成功とみなさない。誤りが見逃されている可能性があるため、Accuracyと同時に評価する。

## 43. Decision

Status: Proposed

### Recommended Minutes Architecture

Structured State + Evidence Hybridを推奨する。

- Final Discussion GraphをCurrent Stateの中心にする
- Event StreamはReplay、Change、Flow、Correctionの根拠として使う
- Final Transcriptは必要なEvidenceと短いCitationだけに使う
- Visual Artifactは関連Referenceとして扱い、Decisionを生成する根拠にしない
- Structured Minutes Projectionを先に作り、閉じた入力として文章を生成する
- Deterministic Validation後にSemantic ValidationとHuman Reviewを行う

### Recommended Source Precedence

1. 最新の有効なHuman Correction / Finalization Input
2. Human-confirmed Decision / Action
3. Human Correction適用後のLatest Discussion Graph
4. Event Stream上の有効なCandidate / Interpretation
5. Final Transcript Evidence
6. Visual ArtifactのReference情報
7. 推測は禁止

### Recommended Minutes Structure

必須はMeeting InformationとExecutive Summaryとし、Decision、Pending Confirmation、Main Discussion、Open / Unresolved Items、Action Items、Parking Lot、Next Topics、Related Visual Artifactsは内容がある場合に表示する。

Main DiscussionはTopic-basedを基本とし、重要なDiscussion Flowだけを補足する。QuestionとUnresolvedはOpen / Unresolved Itemsへ統合し、内部Typeは必要に応じて保持する。

### Recommended Finalization Flow

End Session後にFinal STT / AnalysisをFlushし、Event StreamからGraphをMaterializeし、Human CorrectionとConfirmed Stateを適用する。Candidateを自動Confirmedにせず、Minutes Context Snapshot、Structured Projection、Draft、Validation、Review、Confirm、Markdown Exportの順に進める。

### Recommended Export Format

MVPではMarkdownを正式Export形式とする。Plain Text、PDF、DOCX、外部サービス連携は後続RFCで扱う。

### Key Trade-off

Transcriptを全文要約するだけの簡便さを捨て、State、Evidence、Validation、Reviewを組み合わせることで、実装と生成Pipelineは複雑になる。

一方で、Confirmed Decisionの誤生成、Human Correctionの再導入、Owner / Due Dateの捏造を抑え、会議後に信頼できる文書を作りやすくなる。MinutesがDiscussion MapのFinal Projectionである以上、この複雑性はMVPの中心価値を守るために必要な範囲と判断する。

### Deferred to Future RFC

- PDF、DOCX、Plain Textの正式Export
- Email、Chat、Knowledge Baseへの配信
- 組織単位のRetention、Access Control、Privacy Policy
- Minutesの共同編集、承認Workflow、電子署名
- Speaker Attributionの高度な表示と話者別検索
- Minutesの多言語生成と翻訳
- Session横断のAction追跡、Due Date通知、完了管理
- Minutesと正式な設計文書、Issue Tracker、Calendarの同期
- Minutes Revisionの高度な差分・Merge

### Coordination Notes Across RFC-0001〜0004

本RFCの作成時点で、次の要調整点を明示する。

- RFC-0001 / RFC-0003のDecision Confirmation: MinutesはConfirmedのみを正式Decisionとする。Confirmationの具体的なUI・発話Policyは既存RFCのOpen Questionとして残る。
- RFC-0001のAction Item State: ActionはDecisionと同じCandidate / Confirmed Stateを持たない。明示的な実行意図で生成し、Owner / DueはEvidence明示値またはHuman update_actionで補正する。
- RFC-0002のPending Analysis: Session終了時にFinal STT / Analysisをどこまで待つかは未確定である。本RFCは最後の整合GraphとReview Warningを使う案を示したが、待機閾値はRFC-0002と要調整である。
- RFC-0003のSession Summary: SummaryはFinal Graphから作る即時Projectionとし、Minutesとは別のSource of Truthにしない。
- RFC-0004のArtifact Status: adoptedを正式Decisionとして使わず、Readyな関連ArtifactをTopic単位でReferenceする。MinutesへのArtifactの最終表示条件は本RFCで定めたが、Artifactの正式採用WorkflowはFuture RFCである。
### Explicitly Not Adopted for MVP

- Transcript全文の単純なLLM要約を唯一のSource of Truthにする方式
- Candidate Decisionの自動Confirmed化
- Action Owner、Due Date、Next Topicの推測補完
- Visual ArtifactからDecisionを生成する方式
- Human EditされたSectionを無警告で再生成上書きする方式
- Minutes生成失敗時に、推測で欠落情報を埋める方式
- PDF / DOCXをMVPの必須Exportにすること
