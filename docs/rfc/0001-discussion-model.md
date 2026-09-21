# RFC-0001: Discussion Model / Discussion Graph Architecture

| 項目 | 内容 |
| --- | --- |
| Status | Proposed |
| Target | Discussion Map AI Facilitator MVP |
| Related RD | [Discussion Map AI Facilitator MVP 要件定義書](../requirements/discussion-map-ai-facilitator-mvp.md) |
| Last Updated | 2026-09-19 |

## 1. Problem Statement

### 1.1 なぜDiscussionの内部モデルが必要か

Discussion Map AI Facilitatorの中心価値は、会議終了後に記録を整理することではなく、会議中に参加者がDiscussion Mapを確認しながらDiscussionを進められることである。

そのため、会話をそのまま保存するだけでは不十分である。システムは少なくとも以下を区別して保持する必要がある。

- 何について話しているか
- どのようなIdea / Opinionが出たか
- どのようなOptionがあるか
- どのQuestionが残っているか
- どのConcernがあるか
- 何がDecisionになったか
- 何がUnresolved Itemとして残ったか
- どのAction Itemが発生したか
- どの話題をParking Lotへ移したか
- どのTopicからどのTopicへ話が移ったか
- どの情報がどの発言から得られたか

これらを明示的に表現できなければ、Mapの更新のたびに同一Topicを重複表示したり、未決事項をDecisionとして扱ったり、過去の修正を失ったりする。

### 1.2 Transcriptだけではなぜ不十分か

Transcriptは会話の証拠として重要である。しかしTranscript中心のモデルには次の限界がある。

- 同じ意味を持つ異なる表現を同一Topicとして扱いにくい
- 現在の論点と過去の発言を区別しにくい
- Decision、Unresolved Item、Parking Lotなどの状態を直接表現しにくい
- 議論の構造とTopic遷移を一目で扱いにくい
- 人間によるNode名変更、Merge、Decision解除の履歴を管理しにくい
- 現在のMapを安定して差分更新しにくい

一方で、Transcriptを捨てることもできない。AIの抽出結果の検証、Human Correction、Minutes生成、Debug、評価に必要だからである。

したがって、Transcriptは「意味構造そのもの」ではなく、意味構造を支えるEvidenceとして保持する必要がある。

### 1.3 Discussion Mapとして表現する際の課題

Discussion Mapには、次の相反する要求がある。

1. 会話の変化を速やかに反映すること
2. 画面上のNodeが頻繁に移動・改名・重複しないこと
3. 現在の状態と、これまでのDiscussionの流れを区別すること
4. AIが誤った場合でも会議を止めずに修正できること
5. AIの推定と参加者が確認したDecisionを混同しないこと
6. Mapに表示しない情報も履歴として失わないこと
7. Visual ArtifactをDiscussionの文脈から切り離さないこと

本RFCでは、これらを満たすための内部モデルの責務分担と主要な設計選択肢を整理する。

### 1.4 設計判断の優先順位

RDの補足に従い、本RFCでは次の順で評価する。

1. Discussion Mapの安定性
2. 人間が理解しやすいモデル
3. Human Correctionしやすさ
4. 履歴・Replay可能性
5. AI解析のしやすさ
6. 実装の単純さ
7. 将来拡張性

## 2. Goals / Non-goals

### 2.1 Goals

このRFCで扱うことは次のとおりである。

- Discussionを構成する基本Entityの責務を整理する
- Transcript、Evidence、Event、Graph、現在状態の関係を整理する
- Topic、Idea / Opinion、Option、Question、Concern、Decision、Unresolved Item、Action Item、Parking Lot、Visual Artifactの表現を検討する
- Discussion Flow、Current Topic、Discussion Driftを表現する考え方を定義する
- DecisionをAIが誤って確定しないための状態を検討する
- Node / Entity Stateを必要最小限に整理する
- RelationshipをSchemaで制限するか自由生成するかを比較する
- Mapの更新、Identity、Merge、Versioning、History、Replay、Human Correctionの設計方針を示す
- 複数の代替案を比較し、MVPに対する推奨案を提示する

### 2.2 Non-goals

以下は本RFCでは決定しない。RDのRelationship to RFCに従い、必要に応じて別RFCまたはDesign Documentで扱う。

- 使用するLLM
- 使用するSTT
- Graphの具体的な内部Schema・シリアライズ形式
- DB構成、Graph DBの採否
- API設計
- Streaming方式
- Frontend Framework
- Map描画Library
- Layout Algorithm
- Visual生成Provider
- Agent構成
- 具体的なプロンプト
- 具体的な信頼度の閾値
- 具体的な画面レイアウト
- 組織・ユーザー管理
- データ保持期間、アクセス制御、監査ポリシー

本RFCにおける「Entity」「Event」「Graph」は、まず設計上の概念を指す。これらをどの技術で永続化するかは別途決定する。

## 3. Domain Model候補

### 3.1 Transcript中心モデル

会話を時系列のTranscriptとして保持し、必要なときにTranscriptからMapを生成するモデルである。

#### 長所

- 概念が単純で初期実装に入りやすい
- 会話の原文を失わない
- Minutes生成や検索との相性がよい
- AIが直接扱える入力をそのまま保持できる

#### 短所

- 同一TopicのIdentityを維持しにくい
- MapのNode、Relation、Stateが派生的になりやすい
- 人間による修正を次回生成で失いやすい
- Decision解除やMergeの履歴を扱いにくい
- Map全体を再生成する設計になりやすく、視覚的安定性が低い
- 現在の状態とDiscussionの流れを別々に扱いにくい

### 3.2 Event Stream中心モデル

会話の観測、AIの抽出、参加者の修正、Topic遷移などを時系列Eventとして追加し、現在状態をEventから再構成するモデルである。

#### 長所

- 履歴、Replay、Debug、Evaluationに強い
- AIの提案とHuman Correctionを別Eventとして保持できる
- UndoやDecision解除を逆操作Eventとして表現しやすい
- 「いつ何が起きたか」を失いにくい

#### 短所

- 現在のMapを表示するためのProjectionが別途必要になる
- EntityのIdentityやMergeをProjection側で扱う必要がある
- Eventの種類を増やしすぎるとMVPとして複雑になる
- Eventの並びだけではMapの構造を直接理解しにくい

### 3.3 Graph中心モデル

Topic、Idea、DecisionなどをNode、Node間の関係をEdgeとして保持し、Graphを現在のDiscussion Mapの中心とするモデルである。

#### 長所

- Discussion Mapの構造を直接表現できる
- TopicとIdea、DecisionとActionなどの関係を人間に説明しやすい
- Current TopicやTopicの階層を表現しやすい
- Map描画との概念的な相性がよい

#### 短所

- 時系列の履歴を別途持たなければならない
- なぜそのNodeやRelationが存在するかのEvidenceを失いやすい
- AIの暫定提案と確定情報の区別が曖昧になりやすい
- Merge、削除、Decision解除がGraphの直接更新に見えやすく、Replayしにくい
- Graphをそのまま正とすると、自由なRelation生成によってMapが不安定になりやすい

### 3.4 Event Stream + Graphのハイブリッド

Event Streamを履歴と変更の基盤とし、GraphをEventから構成される現在のMaterialized Viewとして扱うモデルである。TranscriptはEvidenceとして保持し、AIの抽出結果やHuman CorrectionをEventとして記録する。

#### 長所

- 現在のMapをGraphとして理解しやすい
- Eventによって履歴、Replay、Debug、Human Correctionを保持できる
- AI提案、参加者の確認、修正を区別できる
- Stable Entity ID、Alias、Merge履歴を表現しやすい
- Mapの差分更新と、必要時の再構成の両方を可能にする

#### 短所

- Transcript、Event、Graphの責務を理解する必要がある
- ProjectionとIdentity管理が必要になる
- 4案の中では概念的な複雑性が最も高い
- Event設計を広げすぎるとMVPの実装負荷が増える

### 3.5 比較

| 候補 | MVP実装容易性 | Map安定性 | 履歴・Replay | Human Correction | AIとの相性 | 概念的複雑性 |
| --- | --- | --- | --- | --- | --- | --- |
| Transcript中心 | 高 | 低〜中 | 中 | 低 | 高 | 低 |
| Event Stream中心 | 中 | 中 | 高 | 高 | 中 | 中 |
| Graph中心 | 中 | 中〜高 | 低〜中 | 中 | 中 | 中 |
| Event Stream + Graph | 中〜低 | 高 | 高 | 高 | 高 | 高 |

### 3.6 暫定的な評価

単純さだけを優先するとTranscript中心モデルが有利である。しかし本プロダクトのPrimary Validation Questionは、会議中にMapを見ながらDiscussionを進めやすくなるかである。その検証には、Mapの安定性とHuman Correctionの扱いが重要であり、Transcriptだけでは不足する。

Graph中心モデルは表示構造には適しているが、履歴と根拠をGraph自身に詰め込むと複雑になりやすい。

したがって、MVPの推奨候補は、機能を限定したEvent Stream + Graphのハイブリッドとする。ただし、Eventの種類とRelationの種類は必要最小限に制限する。Graph DBの採用を意味するものではない。

## 4. Discussionの基本要素

### 4.1 共通の概念

Discussionは、次の4つの層に分けて考える。

1. **Evidence**: Transcriptの発言区間やユーザー操作など、根拠となるもの
2. **Event**: Evidenceから抽出された意味、Topic遷移、Human Correctionなどの出来事
3. **Entity / Relation**: Discussionの意味構造として扱うNodeと関係
4. **Current Projection**: 現在のDiscussion Mapとして参加者に見せる状態

同一のEntityは、複数のEvidenceやEventから支持されることがある。逆に、AIが一時的に提案したEntityが最終的にMapへ表示されないこともある。

### 4.2 Session

Sessionは、1回のDiscussionの境界を表す。

最低限、次の文脈を持つ。

- Discussion Title
- Discussion Goal
- Background / Context
- 開始・終了の時点
- Current Topic
- DiscussionのEntity、Relation、Event、Evidenceへの参照

Session自体をMapのNodeとして描画することは必須ではない。Sessionは全Entityのスコープを決めるコンテナとして扱う。

### 4.3 Topic

Topicは、参加者が議論しているテーマまたは論点である。

#### 表現の考え方

- Stable Entity IDを持つ
- 表示名と過去のAliasを分ける
- Topic同士の親子関係は、必要な場合に限りcontainsで表現する
- Current TopicはTopicの属性ではなく、Sessionの現在状態およびTopic遷移履歴から表現する
- 未決かどうかはTopic名ではなく、関連するQuestion、Unresolved Item、Decisionの状態で表現する

Topicを発言ごとに新規生成しない。同一Session内で既存Topicに対応する可能性が高い場合は、まず既存Entityへの参照候補として扱う。

### 4.4 Idea / Opinion

Idea / Opinionは、参加者から出た意見、仮説、提案、観点である。

#### 表現の考え方

- TopicまたはOptionとの関係を持てる
- supports、opposes、depends_onなどの限定されたRelationで関係を表現する
- Idea / Opinion自体をDecisionと同一視しない
- 発言者をMVPでどの程度表示・保持するかはRDでも未確定であり、必須属性とはしない
- 同じ内容の反復発言は、既存IdeaへのEvidence追加として扱うことを基本とする

### 4.5 Option

Optionは、QuestionやTopicに対して検討されている選択肢である。

#### 表現の考え方

- QuestionまたはTopicからhas_optionで参照する
- Optionの採否はDecisionの状態またはDecisionとのRelationで示す
- Optionが採用されなかった場合も、履歴上のOptionとして残せる
- Optionを最初からDecisionとして生成しない

### 4.6 Question

Questionは、まだ答えが出ていない問いである。

#### 表現の考え方

- activeなQuestionはOpen IssueやUnresolved Itemと関連する
- DecisionがQuestionを解消した場合はresolvesで関係付ける
- Questionの文面をAIが更新する場合も、Stable Entity IDを維持し、Aliasまたは名称変更Eventを残す
- Questionが単なる発言上の疑問なのか、会議で扱うOpen Issueなのかは、EvidenceとRelationで区別する

### 4.7 Concern

Concernは、リスク、懸念、制約、否定的な影響の可能性を表す。

#### 表現の考え方

- Idea、Option、Decision、Topicのいずれかに関連付けられる
- Concernは必ずしも反対意見ではないため、opposesと同一視しない
- Concernが解消された場合は、解消に関するDecisionまたはEvidenceを残す
- Concernの重要度を数値化することは本RFCでは必須としない

### 4.8 Decision

Decisionは、Discussionの中で採用または合意された事項である。

DecisionはAIが抽出した候補と、参加者が確認したDecisionを区別できなければならない。

基本的には、Decision EntityとDecision専用のdecision_statusを持たせる。

- candidate: AIがDecision候補として認識したが、確定していない
- confirmed: 参加者の明示的な確認、または別途定める確認条件を満たした
- retracted: 以前confirmedだったが、後のDiscussionまたはHuman Correctionで解除された

tentative、agreed、decidedをすべて独立した状態として持つことは、MVPでは避ける。これらの語の運用上の差がRDで確定していないためである。

- tentativeはcandidateの説明語として扱う
- decidedはconfirmedの説明語として扱う
- agreedをconfirmedと別状態にするかはOpen Questionとして残す

### 4.9 Unresolved Item

Unresolved Itemは、Discussionで扱われたが、結論に到達していない事項である。

Questionと完全に同じ概念にするか、別Entity Typeとして保持するかには選択肢がある。

#### 選択肢

1. QuestionとUnresolved Itemを同一Typeにし、表示上だけ区別する
2. Questionは問い、Unresolved Itemは会議終了時にも未解決である状態として別Typeにする

MVPでは、参加者が「未決事項」を把握する必要があるため、表示上の概念としては区別する。ただし、内部で別Entityに分けるか、Questionにunresolvedという状態を付けるかは、実装Schemaを決めるRFCまたはDesign Documentに委ねる。

本RFCの推奨は、意味上はQuestionの解決状態として扱い、Map上ではUnresolved Itemとして表示できるようにすることである。これにより、同じ問いを二重に生成しにくくなる。

### 4.10 Action Item

Action Itemは、会議終了後に実行すべき作業である。

#### 表現の考え方

- Decision、Question、Topicなどの結果としてresults_inで関連付ける
- 担当者と期限はRDでは「可能であれば」とされているため、MVPの必須属性とはしない
- AnalyzerがOwner / Dueを設定する場合は、Transcript Evidenceに明示された値だけをaction生成時に設定し、source_evidence_idsで追跡する。明示されない場合はnullとする
- Humanのupdate_actionはOwner / Dueを後から設定・修正できる
- Action Itemを抽出したことと、実行完了したことを混同しない
- completed状態をMVPで扱うかはOpen Questionとして残す

### 4.11 Parking Lot

Parking Lotは、重要ではあるが、現在のDiscussionでは扱わない事項である。

Parking Lotは単なる削除ではない。元のTopicやQuestionとの関係を保ったまま、現在のDiscussionの中心から外す必要がある。

#### 表現の考え方

- Entityの表示状態をparkedにする
- 元の親TopicやEvidenceを保持する
- Parking Lotへの移動をCorrection EventまたはHuman Action Eventとして記録する
- 将来扱う候補であることと、未解決であることを同一視しない

### 4.12 Visual Artifact

Visual Artifactは、Discussion MapのNodeそのものというより、Discussion内容を具体化する補助的な成果物である。

基本方針は次のとおりである。

- Artifactの実体、生成状態、表示情報は別リソースとして扱う
- Discussion ModelにはArtifact EntityまたはArtifact Referenceを置く
- generated_fromで、生成の根拠となったTopic、Idea、Option、Decisionなどに関連付ける
- Artifactを新しいDecisionとして扱わない
- ArtifactがDiscussion Map上で見える必要がある場合は、通常の意味NodeではなくArtifactカードまたは参照Nodeとして表示する

この分離により、VisualがMapの意味構造を不必要に膨らませることを避けられる。

### 4.13 概念的なモデル

~~~text
Discussion Session
├─ Evidence
│  └─ Transcript segment / User correction / User action
├─ Topic
│  ├─ Idea / Opinion
│  ├─ Question / Unresolved Item
│  ├─ Concern
│  ├─ Option
│  ├─ Decision
│  ├─ Action Item
│  └─ Parking Lot item
├─ Topic transition history
└─ Visual Artifact reference
~~~

これは具体的なデータベースSchemaではなく、MVPで保持すべき概念の境界を示す。

## 5. Discussion Flow

### 5.1 現在の状態と議論の履歴を分離する

現在の状態と履歴を同じ属性だけで表現すると、次の問題が起きる。

- 過去に話していたTopicが消える
- Current Topicの変更で、元のTopicへ戻った事実が失われる
- Decision解除などの修正理由が分からなくなる
- Mapを再表示するたびに過去の順序が変わる

したがって、次の2つを分離する。

1. **Current Projection**: 現在参加者に見せるTopic、Decision、Open Issue、Action Itemなど
2. **Flow / Event History**: Topicへの入出、戻り、Decisionの変化、Correctionの履歴

### 5.2 Topic遷移

Topic遷移は、Topic Entityの親子関係とは別のFlow情報である。

例えば、次のような関係を持つ。

~~~text
MVP機能 ──transitioned_to──> Visual生成
Visual生成 ──transitioned_to──> 料金モデル
料金モデル ──transitioned_to──> MVP機能
~~~

遷移には、少なくとも次の概念を関連付けられるようにする。

- from Topic
- to Topic
- 遷移を示すEvidence
- 遷移した時点
- 遷移時にfrom Topicが未解決だったかどうか

正確な時刻の粒度や遷移の検出方式は本RFCでは決定しない。

### 5.3 Current Topic

Current Topicは、Map上で現在のTopicを強調するためのSession-levelな状態である。

Topic Entity自体にdiscussingという永続的な状態を持たせるより、次のように扱う方が単純である。

- Sessionがcurrent_topic_idを持つ
- Topic遷移EventがCurrent Topicの変化を記録する
- 現在のTopicに関連する最近のEvidenceを参照できる
- Current Topicから離れたTopicはactiveのまま残り得る

Prototype 1では、Humanのset_current_topicがmode=human_correctedのOverrideを作る。Override中はNode追加やConfidence変化だけではFocusを変更しない。対象Topicがparkedになった場合はprimary_topic_idをnull相当へ解除し、Overrideも解除する。restore_from_parking_lotは自動復帰させず、次の明示的なset_current_topicまたはtopic_focus_changedでのみ再Focusする。

これにより、「過去に議論したが未解決のTopic」と「現在議論しているTopic」を同じEntityの状態だけで無理に表現しなくて済む。

### 5.4 一度離れたTopicへ戻るケース

既存Topicへ戻った場合は、原則として新しいTopicを作らず、既存Topicへの遷移として扱う。

ただし、戻った後の論点が明確に別の内容になっている場合は、AIが新しいTopic候補を提案してもよい。自動的に統合するのではなく、既存Topicとの関係またはMerge候補として扱う。

この判断は、次の優先順位で安定性を守る。

1. 既存Topicへの再参照を優先
2. 新しい意味がEvidenceで十分に支持される場合だけ新Topic候補を作る
3. 類似しているだけでは自動Mergeしない
4. Map表示上は、同一TopicのNodeを再利用する

## 6. Discussion Drift

### 6.1 「脱線」を事実として保存しない

RDでは、AIが「これは脱線です」と断定することを避けるとしている。新しいTopicへの移行は、良い発散や必要な探索である可能性があるためである。

そのため、内部モデルに必須の事実としてis_driftを持たせることは推奨しない。

代わりに、次の観測可能な事実を保持する。

- 元のTopicが未解決である
- Current Topicが別のTopicへ移動した
- 新しいTopicにDiscussionが続いている
- 元のTopicと新しいTopicの間に明示的な関係があるか
- 参加者がParking Lot、戻る、続けるなどの修正を行ったか

### 6.2 Drift Awarenessの表現

MapまたはAI Observationで必要になった場合、次のような中立的な派生表示を生成できる。

> 元の論点「MVP範囲」は未決のままです。現在は「料金モデル」を議論しています。

この表示は、元TopicとCurrent Topicの状態から導出される。新しいTopicが「悪い脱線」であるという分類ではない。

### 6.3 良い発散と無駄な脱線

MVPでは、内部モデル上で良い発散と無駄な脱線を自動的に区別しない。

#### 区別しない理由

- RDが求めているのは参加者が判断できる情報であり、AIの最終判断ではない
- 良い発散かどうかは会議の目的や参加者の意図に依存する
- 誤分類はDiscussionを不必要に誘導する
- 評価に必要な分類基準がRDでまだ定義されていない

将来、参加者の操作やPoC評価から有用なシグナルが得られた場合は、ObservationまたはUXレベルで扱う余地を残す。

## 7. Decision Model

### 7.1 Decisionを特別扱いする理由

誤ったDecisionの表示は、誤ったIdeaの表示よりも会議への影響が大きい。

- 決まっていないことを再度議論しなくなる
- 参加者間の認識差を隠す
- Minutesに誤った決定が残る
- AIへの過信を生む

したがって、Decisionは抽出できることと、確定したことを分離する。

### 7.2 Decision確定条件の選択肢

#### 案A: AIが発言から自動確定する

明確な合意表現を検出した場合にDecisionをconfirmedにする。

長所:

- 会議の操作負荷が低い
- 会話の流れを止めにくい

短所:

- 同意、相槌、仮定、皮肉などを誤認しやすい
- 少数の発言から過剰に確定しやすい
- 誤った確定を人間が見逃す可能性がある

#### 案B: 人間の明示確認だけで確定する

AIはcandidateを作り、参加者の操作または明示的な確認でconfirmedにする。

長所:

- Decisionの誤確定を抑えやすい
- Human Correctionと整合する
- MVPの検証結果を解釈しやすい

短所:

- 会議中の操作が増える
- 確認されない候補が増えやすい
- 会話のテンポを損なう可能性がある

#### 案C: AI候補 + 明示的な確認を基本とするハイブリッド

AIはDecision候補を提示するが、confirmedへの遷移は人間の確認または別途合意した明確な条件に限定する。

長所:

- AIの整理能力を活かしつつ、最終判断を人間に残せる
- CandidateとConfirmedをMap上で区別できる
- 誤認時に修正しやすい

短所:

- Candidateの表示方法を設計する必要がある
- 人間が確認しない場合のMinutes生成ルールが必要になる

### 7.3 推奨するDecision状態

MVPでは、Decision専用の状態を次の3つに限定する。

| 状態 | 意味 | Map上の扱い |
| --- | --- | --- |
| candidate | AIまたは参加者がDecision候補として提示したが、未確定 | 確定Decisionと区別できる形で扱う。具体的な表示方法はUXで決める |
| confirmed | 参加者が確認した、または別途合意した確認条件を満たした | Decisionとして表示する |
| retracted | 以前confirmedだったが、撤回・修正された | 現在の確定Decisionから外し、履歴には残す |

tentative、agreed、decidedのすべてを別状態にする必要は、MVP時点では認めない。

- tentativeはcandidateと同義の説明語
- decidedはconfirmedと同義の説明語
- agreedを別にする必要があるかは、合意と決定を分けるプロダクト要件が出た時点で再検討する

### 7.4 Decision修正・撤回

Decisionを直接上書き・削除するのではなく、次のような新しいCorrection Eventを記録する。

- Decisionを別の内容へ修正する
- Decisionをretractedにする
- Decision候補をUnresolved Itemへ戻す
- Decisionの根拠となるEvidenceを追加する

このとき、過去にconfirmedだった事実は履歴に残る。現在のMapにはretractedのDecisionを表示しない、または履歴領域にのみ表示する。

### 7.5 AI誤認時のHuman Correction

AIがDecisionを誤認した場合、参加者は少なくとも次を行える必要がある。

- Decisionの文言を変更する
- Candidateへ戻す
- Decisionを解除する
- 別のTopic、Option、Questionへ関連付け直す
- 不要なDecisionをMapから隠す

操作の具体的なUIは本RFCの範囲外だが、モデルは上記をEventとして保存できる必要がある。

## 8. Node / Entity State

### 8.1 状態を増やしすぎない方針

Stateを増やすほど意味は細かくなるが、AIの判定、Map表示、Human Correction、Replayのすべてが複雑になる。

MVPでは、一般Entityに共通する状態と、Decisionだけが持つ状態を分ける。

### 8.2 共通のLifecycle State候補

| State | 意味 | MVPでの扱い |
| --- | --- | --- |
| active | 現在のDiscussion文脈に存在し、Mapまたは履歴上で有効 | 採用候補 |
| parked | Parking Lotへ移動され、現在の中心Discussionから外れている | 採用候補 |
| resolved | Decisionや別の結果により、現在の問い・Issueが解消された | 採用候補。ただし全Entityに適用しない |
| rejected | OptionやIdeaが採用されなかった | 採用候補。ただし現在Mapでの表示はUXで決める |
| removed | Human Correctionで現在のMapから除外された | 内部のTombstoneまたはCorrection結果として必要 |
| discussing | 現在話している | 永続Stateにはしない |
| tentative | 確定前 | Decisionのcandidateで表現する |
| decided | 確定済み | Decisionのconfirmedで表現する |
| completed | Action Itemなどが完了した | MVPで必須か未確定 |

### 8.3 推奨する最小構成

MVPで一般Entityに常に持たせる状態は、active、parked、resolvedを基本とする。

rejectedはOptionやIdeaで必要な場合だけ使う。removedは物理削除の代わりに履歴保持のために必要だが、参加者に見せる通常のStateと同一視しない。

次の状態は導出またはType-specificにする。

- discussing: Session.current_topic_idから導出
- tentative / decided: Decisionのdecision_statusから導出
- completed: Action Itemに対する追加要件が定まった場合のみ導入

### 8.4 StateとTypeを混同しない

Unresolved Item、Parking Lot、Decisionは、すべて同じLifecycle Stateではない。

- Unresolved Itemは「未解決であること」を示す意味上のTypeまたはView
- Parking Lotは「現在の中心から外して保留する」という状態
- Decisionは「決定に関するEntity」で、candidate / confirmed / retractedを持つ

この分離により、QuestionをParking Lotへ移動したり、Candidate DecisionをUnresolved Itemとして表示したりする際に、状態の組み合わせが過剰にならない。

## 9. Relationship Model

### 9.1 必要なRelation候補

MVPでは、自由なRelationを大量に生成するより、意味が明確な少数のRelationをSchemaとして制限する方が適している。

| Relation | 主な向き | 意味 | 区分 |
| --- | --- | --- | --- |
| contains | Topic → Topic / Entity | Topicが下位の論点を含む | 構造 |
| has_option | Topic / Question → Option | TopicまたはQuestionに対する選択肢 | 構造 |
| supports | Idea / Option → Idea / Option / Decision | IdeaやOptionが別のIdea、Option、Decisionを支持する | 議論 |
| opposes | Idea / Evidence → Option / Decision | IdeaやEvidenceが選択肢・Decisionに反対する | 議論 |
| depends_on | Entity → Entity | 成立条件や依存関係 | 議論 |
| resolves | Decision → Question / Unresolved Item | Decisionが問い・未決事項を解消する | 結果 |
| results_in | Decision / Topic → Action Item | Discussion結果からActionが生じる | 結果 |
| generated_from | Visual Artifact → Entity / Evidence | Visualの生成根拠 | Lineage |
| transitioned_to | Topic → Topic | Discussion Flow上の移動 | Flow |
| duplicate_of | Entity → Entity | 同一候補・Merge候補の関係 | Identity |
| merged_into | Entity → Entity | Human Correctionまたは確定処理による統合先 | Identity |

この一覧は最終Schemaではなく、MVPで検討する概念的な許可リストである。

### 9.2 Relationを自由生成する案

#### 長所

- AIが多様な関係を表現できる
- 将来の拡張に柔軟
- 初期のSchema設計を省略できる

#### 短所

- 表示する意味が揺れる
- 同じ関係に複数のラベルが付く
- Mapの視覚的・認知的な負荷が高くなる
- AIの誤ったRelationを人間が発見しにくい
- Evaluationの基準を作りにくい

### 9.3 Schemaで制限する案

#### 長所

- Relationの意味を参加者に説明しやすい
- Map描画とObservationの扱いを安定させやすい
- AIの出力を検証しやすい
- 同じTopicの重複や無関係なEdgeを抑えやすい

#### 短所

- 表現できない関係が発生する
- 初期Schemaの設計が必要
- 将来拡張時に追加設計が必要

### 9.4 推奨方針

MVPではRelationをSchemaで制限する。未知のRelationを無理に既存Relationへ割り当てず、Evidenceまたは未分類のObservationとして保持する。

ただし、汎用のrelated_toを大量に生成することは避ける。関係が明確でないこと自体を、関係があるという情報に変換しないためである。

Flowのtransitioned_toと意味構造のcontainsは別Relationとして扱う。これにより、Topicの階層と会話の移動が混同されない。

## 10. Update Model

### 10.1 案A: 毎回Map全体を再生成

最新Transcriptまたは最新の会話要約から、Map全体を毎回生成する。

#### 長所

- 実装の入口が単純
- AIに全体文脈を渡しやすい
- Mapの整合性を一度に考えられる

#### 短所

- Node位置、名前、構造が頻繁に変わる
- 同一Topicが重複しやすい
- Human Correctionが次の再生成で失われやすい
- Undo / Replay / Debugが難しい
- 以前のMapと何が変わったかを説明しにくい

MVPのVisual StabilityとHuman Correctionに反するため、主方式にはしない。

### 10.2 案B: 差分更新

新しい会話区間から変更点だけを抽出し、現在のMapへNodeやRelationを追加・更新する。

#### 長所

- Mapの安定性が高い
- 画面反映の差分を小さくしやすい
- 同一Nodeの再利用を中心にできる

#### 短所

- Identity、Merge、Conflictの扱いが必要
- 長いSessionでProjectionの不整合が蓄積する可能性がある
- 過去の更新を十分に記録しないとReplayできない

### 10.3 案C: Event Append + Materialized View

Transcriptの区間、AIの抽出候補、Topic遷移、Human CorrectionなどをEventとして追加し、Eventを適用した結果を現在のGraph / Mapとして保持する。

#### 長所

- Mapの現在状態と履歴を分離できる
- 同じEventから現在Mapを再構成できる
- Undo / Replay / Debug / Evaluationに強い
- AI提案とHuman Correctionを混同しにくい
- 差分更新と必要時の再計算を両立できる

#### 短所

- Event設計とProjectionが必要
- Eventの順序・重複・競合を扱う必要がある
- 直接Graphを書き換えるより実装概念が多い

### 10.4 案D: CRDTなどの共同編集モデル

複数ユーザーが同時にMapを編集することを前提に、競合解決可能なデータ構造を採用する。

#### 長所

- 将来の個人端末編集やオンライン参加へ拡張しやすい
- 同時編集をモデル化できる

#### 短所

- MVPの対面・共有ディスプレイ環境には過剰
- AIの意味更新と人間の編集競合が複雑になる
- Mapの安定性より同期モデルの複雑性が前面に出る

MVPの主方式としては採用しない。

### 10.5 比較

| 方式 | Map安定性 | 重複防止 | Node名の揺れ | Undo / Replay | Debug / Evaluation | MVPの複雑性 |
| --- | --- | --- | --- | --- | --- | --- |
| 全体再生成 | 低 | 低 | 弱い | 弱い | 弱い | 低 |
| 差分更新 | 高 | 中〜高 | 中 | 中 | 中 | 中 |
| Event Append + Materialized View | 高 | 高 | 高 | 高 | 高 | 中〜高 |
| CRDT等 | 中 | 中 | 中 | 高 | 中 | 高 |

### 10.6 推奨更新方針

MVPでは、Event Append + Materialized Viewを基盤とし、AIの新しい解析単位ごとに小さな差分を適用する。

概念的には次の流れである。

~~~text
Transcript / User Action
          ↓
Evidence Event
          ↓
AI Analysis Proposal
          ↓
Identity / Relation / Decision policy
          ↓
Current Graph Projection
          ↓
Stable Discussion Map
~~~

ここで、全Mapを毎回生成するのではなく、既存Entityの再利用を第一とする。

### 10.7 Mapの視覚的安定性に関する原則

- Stable Entity IDを表示上のNodeの識別子として維持する
- 表示名が変わっても同一Nodeとして扱う
- 新しいEvidenceだけでは既存Nodeを別Nodeにしない
- Nodeの並び替えは、必要な理由がない限り行わない
- Mapに表示しないEventも履歴に残す
- Updateはバッチ単位で適用し、中間的な揺れを必要以上に表示しない
- Decision、Open Issue、Action Itemなど参加者が確認した情報を勝手に再分類しない

バッチの時間幅、再計算頻度、画面アニメーションはUXおよびRealtime PipelineのRFCで決定する。

## 11. Identity / Merge

### 11.1 同じTopicを識別する必要性

会話では、同じTopicが異なる表現で繰り返される。

- 「MVPの中心価値」
- 「MVPで何を検証するか」
- 「最初に作るべき機能」

これらが同一Topicかどうかを毎回新規判定すると、Mapが増殖する。

したがって、TopicのIdentityは表示名とは別に持つ。Identityの判定は、次の情報を組み合わせた候補判定として考える。

- Entity Type
- 表示名とAlias
- 直近のEvidence
- 親Topicまたは関連Question
- 既存のRelation
- 会話上の継続性

具体的な類似度計算や閾値は本RFCでは決めない。

### 11.2 Node名の揺れ

Entityには次を分けて持たせる考え方を推奨する。

- Stable Entity ID
- Current Display Label
- 過去に使われたAlias
- Label変更の根拠Event

AIが言い換えを検出しただけで、Display Labelを毎回変更しない。人間が理解しやすい既存Labelを優先し、明確な改善またはHuman Correctionがある場合に変更する。

### 11.3 Mergeの選択肢

#### 案A: 高い類似度なら自動Mergeする

Mapを小さく保てるが、異なるTopicを一つにまとめる危険が大きい。

#### 案B: AIはMerge候補だけ提示し、人間がMergeする

Mapの安定性とHuman Correctionの責務を保ちやすいが、重複が一時的に残る。

#### 案C: 完全に別Entityとして保持する

誤Mergeは避けられるが、同じTopicの重複が増える。

### 11.4 推奨方針

MVPでは、AIによる自動Mergeを原則として行わない。

- 既存Entityへの参照候補を優先する
- 同一性が明確でない場合はduplicate_of候補として履歴に保持する
- Mergeは人間の明示操作を基本とする
- Merge後も元Entityの履歴とEvidenceは保持する
- Map上ではmerged_into先を表示する

これはMapの安定性を優先するためである。重複を多少残すコストより、異なる論点を誤統合して参加者の理解を壊すコストの方がMVPでは大きい。

## 12. Versioning / History

### 12.1 履歴を保持する必要性

Discussion Mapは会議中の成果物であるため、現在のMapだけでなく、次の問いに答えられる必要がある。

- いつこのTopicが追加されたか
- どの発言からDecision候補が生まれたか
- 誰または何がLabelを変更したか
- なぜDecisionが解除されたか
- いつTopicがParking Lotへ移動したか
- 過去のMapと現在のMapは何が違うか

さらに、RDのNFR-07 Recoverability、Product Risk、PoC評価を考えると、解析失敗や誤認を後から調べられることが必要である。

### 12.2 Revisionの考え方

MVPでは、少なくとも次の識別情報を概念上保持する。

- Event ID
- Session ID
- Entity ID
- Event発生時点
- Eventの種類
- 根拠Evidence
- 変更前後の関係、または変更内容
- ProjectionのRevision

具体的なVersion番号の採番方式は実装設計に委ねる。

### 12.3 Replay

Replayは、次の目的のために必要である。

- AIの抽出結果の再評価
- Map更新のDebug
- Human Correction前後の比較
- PoC時の評価
- Recoverability

ただし、参加者がMVPの画面から任意の過去時点へ自由に移動する機能は必須ではない。

推奨は次のとおりである。

- 履歴としてはReplay可能な構造を持つ
- UIとしての過去Map閲覧はMVPの必須Scopeにしない
- SnapshotはProjection再構築を速くするための最適化として扱い、Source of Truthにしない

### 12.4 Undo

Human CorrectionのUndoは、過去Eventを削除・書き換えず、逆操作または新たなCorrection Eventとして表現する。

ユーザー向けのUndoボタンをMVPで提供するかはUI設計のOpen Questionだが、内部モデルはUndo可能な履歴を壊さないことを前提とする。

## 13. Visual Artifactとの関係

### 13.1 ArtifactをDiscussion Modelに置く理由

Visualは結論ではなく議論を具体化する素材である。したがって、生成されたVisualを独立したファイルとして保存するだけでは、次の文脈が失われる。

- 何を元に生成されたか
- どのTopicを議論していたか
- どのIdea / Option / Decisionと関係するか
- どの時点のMapから生成されたか
- 参加者がどのような目的で生成したか

### 13.2 推奨する扱い

Visual Artifactは、Discussion Model上では次の2つに分ける。

1. **Artifact Resource**: 画像、図、メタデータ、生成状態などの実体
2. **Artifact Reference / Entity**: Mapや履歴からArtifactを参照する意味上のリンク

Artifact Referenceは次を保持できるようにする。

- Artifact ID
- 生成の根拠となったEntityまたはEvidence
- 生成を開始した時点
- 生成状態
- 現在表示中かどうか
- 人間が付けた説明または修正履歴

### 13.3 Artifactを通常Nodeにする案との比較

#### 通常Nodeとして扱う

Map上で扱いやすい一方、VisualがTopicやDecisionと同じ意味階層に入り、Mapが膨らみやすい。

#### 別リソースとして扱う

意味構造を汚しにくく、生成・表示の失敗をDiscussion全体から分離しやすい。一方、Mapからの参照UIが必要になる。

MVPでは、別リソースを基本とし、必要な場合だけMap上に参照カードまたは参照Nodeを表示する。

## 14. Human Correction

RDのHuman Correction要件を、内部モデル上では直接の上書きではなく、すべてCorrection Eventとして扱う。

### 14.1 名前変更

- 対象EntityのStable IDを維持する
- Current Display Labelを変更する
- 旧LabelをAliasとして残す
- 変更者、変更時点、変更理由または根拠を履歴に残せるようにする

次のAI解析で旧Labelに戻らないよう、既存LabelとCorrectionをProjectionへ反映する必要がある。

### 14.2 削除

物理削除は行わない。

- 現在のMapからはremovedまたは非表示として除外する
- 元のEvidenceとEventは保持する
- 以後のAI解析で同一Entityを不用意に再生成しないための除外情報を残す

削除が「誤認の取消し」なのか「Mapに表示しないだけ」なのかは、UIとUXで明確にする必要がある。

### 14.3 Merge

- Merge先のStable IDを決める
- Merge元からMerge先へのmerged_into Eventを記録する
- Merge元のEvidence、Relations、Label履歴を失わない
- ProjectionではMerge先を表示する
- 後で分離する可能性を考え、Merge元を物理削除しない

自動Mergeではなく、Human Correctionを基本とする。

### 14.4 Decision解除

- Decisionのdecision_statusをretractedへ変更するCorrection Eventを記録する
- 解除されたDecisionの根拠と解除理由を保持できるようにする
- 関連するQuestionを必要に応じてactiveまたはunresolvedへ戻す
- Minutes生成時に、現在のDecisionと過去に撤回されたDecisionを区別する

Questionを必ず自動で復元するかは、DecisionとQuestionのRelationによって判断する。無関係なQuestionを自動復元しない。

### 14.5 Parking Lotへの移動

- 対象Entityの表示状態をparkedへ変更する
- 元のTopicとのcontainsや関連Relationを保持する
- Parking Lotへ移動したEventを記録する
- 後でDiscussionへ戻す操作を可能にできる構造を残す

Parking Lot移動は削除でも解決でもない。

## 15. Alternatives Considered

### 15.1 比較対象

以下の4案を比較する。

1. Transcript中心 + Map都度生成
2. Graph中心 + 直接更新
3. Event Stream中心 + Projection
4. Event Stream + Graph Materialized View

### 15.2 比較表

評価はMVPにおける相対評価である。

| 案 | MVP実装容易性 | AIとの相性 | Map安定性 | 履歴保持 | Human Correction | 将来拡張 | 複雑性 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Transcript中心 + 都度生成 | 高 | 高 | 低 | 中 | 低 | 中 | 低 |
| Graph中心 + 直接更新 | 中 | 中 | 中〜高 | 低〜中 | 中 | 高 | 中 |
| Event Stream中心 + Projection | 中 | 中 | 高 | 高 | 高 | 高 | 中〜高 |
| Event Stream + Graph View | 中〜低 | 高 | 高 | 高 | 高 | 高 | 高 |

### 15.3 案1: Transcript中心 + Map都度生成

#### 適する場合

- 会議終了後のMinutesが中心価値である
- Mapのリアルタイム安定性を求めない
- Human Correctionが限定的である

#### 本プロダクトでの評価

RDの中心価値と合わない。Mapの差分、Decisionの確定状態、Merge、Replayを後から付け足すことになり、結果として内部モデルの責務が曖昧になりやすい。

### 15.4 案2: Graph中心 + 直接更新

#### 適する場合

- まず構造化されたMapを表示したい
- 履歴やTranscriptの再処理を重視しない

#### 本プロダクトでの評価

初期のMap表示は分かりやすいが、直接更新でAIと人間の変更を同じGraphへ混ぜると、誤認の原因と修正履歴を追いにくい。Graph DBを採用してもこの問題自体は解決しない。

### 15.5 案3: Event Stream中心 + Projection

#### 適する場合

- 履歴・Replay・評価を最重視する
- UI向けのGraph表現を別のProjectionとして許容できる

#### 本プロダクトでの評価

堅牢だが、EventだけではDiscussion Mapの基本構造を直接説明しにくい。Projectionは結局Graph的な構造になるため、Graphの概念を明示した方が人間にも設計にも分かりやすい。

### 15.6 案4: Event Stream + Graph Materialized View

#### 適する場合

- 会議中のMap安定性と履歴の両方を必要とする
- Human CorrectionとAI提案を分離したい
- 将来の再評価・Replayも考慮する

#### 本プロダクトでの評価

4案の中では最も複雑だが、RDが重視する順序に最も整合する。EventとRelationを最小限に絞ることで、MVPとしての複雑性を制御できる。

## 16. Recommended Approach

### 16.1 推奨案

MVPでは、**Event Stream + Graph Materialized Viewのハイブリッド**を推奨する。

役割を次のように分ける。

| 構成要素 | 役割 |
| --- | --- |
| Transcript | 会話の原文。意味構造を支えるEvidence |
| Evidence | 発言区間、ユーザー操作、生成結果などの根拠 |
| Event Stream | AI提案、Topic遷移、Human Correction、Decision変更などの履歴 |
| Discussion Graph | Topic、Idea、OptionなどのEntityと限定されたRelation |
| Current Projection | 現在のDiscussion Mapに必要な状態 |
| Visual Artifact Resource | 生成された画像・図などの実体 |

### 16.2 推奨案の更新原則

1. 新しい会話をEvidenceとして取り込む
2. AIは既存Entityの再利用を優先して候補Eventを生成する
3. CandidateとConfirmedを区別する
4. Candidate Eventを適用してCurrent Projectionを差分更新する
5. Human Correctionは新たなEventとして記録する
6. ProjectionはEventから再構成可能にする
7. Mapに表示されない情報もEvidenceとEventに残す

### 16.3 なぜMVPに適しているか

#### Mapの安定性を第一にできる

Stable Entity IDと既存Entityの再利用を中心にできるため、会話のたびにMap全体が別物になることを抑えられる。

#### 人間に説明しやすい

参加者が見るのはTopic、Idea、Question、DecisionなどのGraphであり、開発者や評価者はその変化をEventとEvidenceで追える。

#### Human Correctionが自然に入る

名前変更、削除、Merge、Decision解除、Parking Lot移動を「上書き」ではなく「変更の履歴」として扱える。

#### ReplayとEvaluationが可能になる

同じEvent列から異なるProjectionを比較できるため、PoCでMapがDiscussionに役立ったかを検証しやすい。

#### 実装を限定できる

Graph DB、自由Relation、完全なEvent Sourcing基盤、CRDTを必須にしない。MVPでは、概念としてのEventとGraphを小さく実装することを目指す。

### 16.4 この推奨案が決めないこと

このRFCは次を決めない。

- Eventをどのストレージへ保存するか
- Graph Projectionをどのライブラリで実装するか
- AI提案を何秒ごとに作るか
- CandidateをMapへどの視覚形式で表示するか
- 具体的なConfidence Threshold
- GraphのJSONやSQLなどの形式
- Visual Artifactのファイル保存方式

これらは、Realtime Pipeline、Map UX、Visual Artifactなどの後続RFCで扱う。

## 17. Data Examples

### 17.1 Discussion例

対象とする発言は次のとおりである。

| 時点 | 発言 |
| --- | --- |
| t1 | A: 「MVPはDiscussion Mapを中心にしたい」 |
| t2 | B: 「スマホも必要では？」 |
| t3 | A: 「将来的には欲しいけどMVPでは不要」 |
| t4 | B: 「それでいきましょう」 |

### 17.2 内部表現の変化

#### t1: 中心価値のIdeaが出る

Evidence:

- 発言区間 t1

Entity候補:

- Topic T1: MVPの中心価値 / MVP範囲
- Idea I1: Discussion Mapを中心にする

Relation候補:

- T1 contains I1

状態:

- T1 active
- I1 active
- Decisionはまだ存在しない
- Current TopicはT1

この時点で「MVPの中心機能が確定した」とは扱わない。

#### t2: 新しいQuestionが出る

Evidence:

- 発言区間 t2

Entity候補:

- Question Q1: スマホUIをMVPに含めるか

Relation候補:

- T1 contains Q1

状態:

- Q1 active
- T1はactive
- Current TopicはT1の下位論点Q1へ移ったと表現できる

「スマホも必要では？」だけから、スマホUIをMVPに含めるDecisionやOptionを自動確定しない。

#### t3: 対象外のIdeaとDecision候補が出る

Evidence:

- 発言区間 t3

Entity候補:

- Option O1: スマホUIをMVPに含める
- Option O2: スマホUIをMVP対象外とする
- Decision D1: スマホUIはMVP対象外

Relation候補:

- Q1 has_option O1
- Q1 has_option O2
- O2 supports D1
- D1 resolves Q1

状態:

- D1 decision_status = candidate
- Q1はまだconfirmedな解決状態ではない
- O1はactiveまたは未確定
- O2はcandidateと関連する

t3だけでは、Aの発言が明確な提案であっても、会議として確定したとは限らない。そのためD1はcandidateに留める。

#### t4: 明示的な同意が出る

Evidence:

- 発言区間 t4

状態変化の候補:

- D1 decision_status: candidate → confirmed
- Q1: active → resolved
- O2: active → resolvedまたは採用Optionとして表示
- O1: rejected、または不採用Optionとして履歴に残す
- T1へCurrent Topicが戻る

ここでのconfirmedへの遷移は、MVPで定める確認操作または明確な合意ルールに基づく。単に「それでいきましょう」という表現をAIが必ず自動確定するかは、本RFCでは未決定である。

### 17.3 概念的なCurrent Map

~~~text
MVPの中心価値 / MVP範囲  [Current Topic]
├─ Idea: Discussion Mapを中心にする
├─ Question: スマホUIをMVPに含めるか [Resolved]
└─ Decision: スマホUIはMVP対象外 [Confirmed]
   └─ Option: スマホUIをMVP対象外とする [Selected]
~~~

Topic遷移履歴には、T1内の中心価値からQ1へ移り、Decision確認後にT1へ戻ったことを別に保持する。

## 18. Risks / Trade-offs

### 18.1 EventとGraphの二重性

EventとCurrent Graphを両方持つため、単一のデータ構造より複雑になる。

一方、履歴をGraphだけに埋め込むとReplayとHuman Correctionが難しくなる。MVPでは、この複雑性をEvent種別とRelation種別の制限で抑える。

### 18.2 Candidateの表示が参加者を混乱させる可能性

Candidateを見せると、参加者がDecisionと誤認する可能性がある。見せないと、AIが何を整理しているか分かりにくい。

Candidateの視覚表現はUXで検証する必要がある。少なくともConfirmedと同じ見た目にしないことを前提とする。

### 18.3 Mergeを抑制すると重複が残る

自動Mergeを避けると、Map上に類似Topicが一時的に残る。これはMapの情報量を増やす。

しかし、誤Mergeによって異なる論点を失う方がMVPの検証を歪める可能性が高い。Human Correctionと後続のMerge候補表示で扱う。

### 18.4 Relationを制限すると表現力が下がる

自由Relationを許可しないため、初期Schemaで表せない関係が出る可能性がある。

これは意図的なトレードオフである。MVPでは、表現力より理解しやすさと評価可能性を優先する。

### 18.5 Flowを保存してもUIで活かせない可能性

Topic遷移履歴を保持しても、Mapに常時表示すると画面が複雑になる。

Flowはまず履歴として保持し、表示方法はMap UX RFCで検証する。保存することと常時表示することを分ける。

### 18.6 Decision確認操作がDiscussionを止める可能性

Human Confirmationを要求しすぎると、会話の自然さが失われる。

Decisionだけを慎重に扱い、IdeaやTopicまで同じ確認操作を要求しないことがMVPでは妥当である。具体的な確認頻度はPoCで検証する。

### 18.7 Visual Artifactが別管理になる複雑性

Artifactを別リソースにすると参照の仕組みが必要になる。

しかしArtifactを通常Nodeとして扱うと、Discussionの意味構造に生成物が混ざり、Mapが不安定になる。別管理を推奨する。

### 18.8 Eventの再適用とAIモデル変更

AIモデルやExtractionルールが変わると、同じTranscriptから異なるEventが生成される可能性がある。

元のEvidenceと当時のEventを残し、再解析結果を別Revisionとして比較できるようにすることが望ましい。再解析の運用は別RFCで扱う。

## 19. Open Questions

本RFCでは、以下を未解決として残す。

### OQ-01: DecisionのConfirmed入力経路

Prototype 1では、AnalyzerはCandidateまでを生成し、Confirmedへの遷移は明示的なHuman confirm_decision Eventだけで行うことをCanonicalとする。残る論点は、将来Voice Intentなど別のHuman Command入力を許すかであり、Prototype 1のMaterializer Contractには含めない。

### OQ-02: CandidateのMap表示

AIが抽出したcandidateをMap上に表示するか。表示する場合、Confirmedとどのように区別するか。

### OQ-03: AgreedとDecidedの区別

参加者間の合意と、正式なDecisionをプロダクト上で別概念として扱う必要があるか。

### OQ-04: QuestionとUnresolved Itemの内部統合

内部Entity Typeを同一にするか、別にするか。Map上の表示だけを分けるか。

### OQ-05: Action Itemの完了状態

担当者、期限、completed状態をMVPに含めるか。

### OQ-06: Speaker Identification

Speaker IdentificationをMVPに含めるか。含める場合、IdeaやDecisionの根拠としてどの程度表示するか。

### OQ-07: Topic Mergeの操作タイミング

Human Correctionで即時Mergeするか、Merge候補を一時的に提示してから確定するか。

### OQ-08: Mapの上限と要約

Mapが大きくなった場合、どのEntityを省略、折りたたみ、要約するか。

### OQ-09: Flowの表示方法

Topic遷移をMap内に表示するか、別のFlow表示にするか。Mapと同時に見せる情報量をどうするか。

### OQ-10: User-facing Undo

内部的にCorrection Eventを保持するだけでなく、参加者向けのUndo操作をMVPに含めるか。

### OQ-11: Visual ArtifactのVersion

同じTopicから複数のVisualを生成した場合、比較・差し替え・採用状態をどこまで管理するか。

### OQ-12: Current Topicの解析・表示閾値

Prototype 1のState Contract（Human Override、parked時の解除、明示Focusでの復帰）は確定した。残る論点は、Analysisがいつtopic_focus_changedを生成するか、UXがどの程度のHysteresis / Cooldownで表示を安定化するかである。

### OQ-13: Evidenceの表示範囲

Map上で各Nodeの根拠発言をどの程度参照可能にするか。これは信頼性と画面情報量のトレードオフになる。

### OQ-14: 複数の主Topic

Discussion Goalの下に複数の同時進行Topicを許すか。MVPでCurrent Topicを常に1つとするか。

### OQ-15: 再解析Revision

AIモデルや抽出ルール変更後に、既存Sessionを再解析する運用をMVPで必要とするか。

## 20. Decision

### Proposed

本RFCの初稿として、以下を提案する。

- Event StreamをDiscussionの履歴・変更基盤とする
- TranscriptはEvidenceとして保持する
- Discussion GraphはEventから構成されるCurrent Materialized Viewとする
- Topic、Idea / Opinion、Option、Question、Concern、Decision、Action Item、Parking Lotを限定されたEntityとして扱う
- Visual Artifactは別リソースを基本とし、Discussion Modelからgenerated_fromで参照する
- Discussion Flowは意味構造のRelationと分離したTopic遷移履歴として扱う
- Driftを事実として断定せず、未解決TopicとCurrent Topicの併存を中立的に表現する
- Decisionはcandidate、confirmed、retractedを基本とし、AIの候補と人間が確認したDecisionを区別する
- Prototype 1では、Confirmedへの遷移を明示的なHuman confirm_decision Eventに限定する
- Actionは明示的実行意図で生成し、Owner / DueはEvidence明示値またはnull、Human update_actionで修正可能とする
- supportsはIdea / Option → Idea / Option / DecisionのNode Type Matrixに限定する
- Current Topic対象がparkedになったらFocusを解除し、restoreで自動復帰させない
- Relationは自由生成せず、MVP用の限定Schemaを設ける
- Entity ID、Label、Alias、Correction、Merge履歴を分離する
- Human Correctionは上書きではなくCorrection Eventとして記録する
- Graph DBや特定の永続化技術はこのRFCでは決定しない

### Accepted

なし。初稿のため、承認済みの項目はない。

### Rejected

本RFCのMVP推奨案としては、以下を採用しない。

- Transcriptだけを正とし、Mapを毎回全体再生成する方式
- Graphを直接上書きし、履歴を別途十分に保持しない方式
- AIがDecisionを常に自動確定する方式
- AIが類似Topicを無条件に自動Mergeする方式
- 自由なRelationを無制限に生成する方式
- CRDTなどの共同編集モデルをMVPの前提にする方式

これらは一般に利用不可能という意味ではなく、RDの優先順位とMVPの検証目的には適さないという意味でRejectedとする。

**RFC Status: Proposed**
