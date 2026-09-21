# RFC-0002: Realtime Discussion Analysis Pipeline

| 項目 | 内容 |
| --- | --- |
| Status | Proposed |
| Target | Discussion Map AI Facilitator MVP |
| Depends on | RFC-0001: Discussion Model / Discussion Graph Architecture |
| Related RD | [Discussion Map AI Facilitator MVP 要件定義書](../requirements/discussion-map-ai-facilitator-mvp.md) |
| Last Updated | 2026-09-19 |

本RFCは、Discussion中のAudioを受け取り、STT、Utterance化、Discussion Analysis、Event Streamへの記録、Discussion Graphの更新へつなぐ責務と処理境界を設計する。

本RFCは実装方式や特定Providerを決定するものではない。MVPに必要な処理順序、状態遷移、失敗時の扱い、再処理可能性を整理する。

## 1. Problem Statement

### 1.1 リアルタイム解析に必要な責務分離

RDでは、会話中にDiscussion Mapを更新することが中心価値とされている。一方、AI解析は常に完全ではなく、STTにはPartial結果、誤認識、遅延、再送、順序の入れ替わりが発生し得る。

Audioから直接Graphを更新すると、次の問題が起こる。

- 確定前の発言でNodeやDecisionが一時生成される
- STTの修正によって同じTopicが重複する
- LLMの再試行で同じEventが重複する
- Eventの到着順によってCurrent Topicが不安定になる
- 失敗した解析がMapを部分的に壊す
- どの発言がどのNodeの根拠か追跡できない

したがって、RFC-0001の責務分離を維持する。

> Transcript = Evidence
> Event Stream = 履歴
> Discussion Graph = 現在状態のMaterialized View

### 1.2 Partial TranscriptとFinal Transcriptの違い

STTは、発話途中のPartial Transcriptと、一区間の発話が確定したFinal Transcriptを返すことがある。

Partial Transcriptは低遅延な表示や先読みには有用だが、後から内容が変わる。これをEvent StreamやGraphの正規の入力にすると、Mapが発話の途中で揺れる。

一方、Final Transcriptだけを待つと、Partialを使う方式より反映が遅くなる。

MVPでは、低遅延とMap安定性の間で明確な境界を設ける必要がある。

### 1.3 解析Pipelineの主な課題

本RFCでは、次の課題を扱う。

- Audio、STT、Utterance、Discussion Analysisの責務
- PartialとFinalの扱い
- Utteranceの区切りとAnalysis Windowの区別
- Eventを生成するタイミング
- EventとGraph Projectionの更新タイミング
- Incremental Processing
- Retry、Reprocess、Replay
- Out-of-order Event
- LLMやSTTの失敗
- Context Windowの肥大化
- Current Topicの解析範囲
- 30〜60分のDiscussionでの継続性
- Provider依存の境界
- Evaluationで再現可能な入力と出力

## 2. Goals / Non-goals

### 2.1 Goals

このRFCのGoalsは次のとおりである。

- AudioからDiscussion Event候補までの責務を分離する
- TranscriptをEvidenceとして保ち、Graphへ直接書き込まない
- Partial結果によるMapの不安定化を抑える
- Final Transcriptを基準にIncrementalに解析できるようにする
- Eventの重複、遅延、順序逆転、再試行を扱う
- LLMやSTTが失敗しても会議全体を止めない
- 30〜60分のSessionでContextを肥大化させない
- Current Topicを解析Pipelineがどこまで提案するかを整理する
- Replay、Reprocess、Evaluationに必要な履歴を残す
- Providerを交換可能にする最小限の境界を設ける

### 2.2 Non-goals

以下は本RFCで決定しない。

- STT、LLM、Audio処理の具体的なProvider
- Providerの製品名、モデル名、料金、リージョン
- Streaming transportの具体的な方式
- DB、Queue、Cacheなどの永続化技術
- Graph DBの採否
- Graphの具体的なシリアライズSchema
- LLMのPrompt本文
- 具体的なConfidence Threshold
- Mapの見た目、Layout、Nodeの配置
- Candidateの画面表示方法
- Human Correctionの具体的なUI
- Visual Artifactの生成方式
- Minutesの生成方式
- 音声・Transcriptの保持期間とアクセス制御

## 3. RFC-0001との整合性

### 3.1 維持する決定

RFC-0001の次の決定を変更しない。

- Event Streamを履歴・変更基盤とする
- TranscriptをEvidenceとして保持する
- Discussion GraphをCurrent Materialized Viewとする
- Topic、Idea / Opinion、Option、Question、Concern、Decision、Action Item、Parking Lotを限定Entityとして扱う
- Visual Artifactは別リソースを基本とする
- Discussion Flowは意味構造のRelationと分離する
- DriftをAIが事実として断定しない
- Decisionはcandidate、confirmed、retractedを区別する
- Relationを自由生成せず、MVP用に制限する
- Human Correctionは上書きではなくEventとして記録する

### 3.2 本RFCによる明確化

本RFCでは、上記の責務分離をPipelineの境界に具体化する。

- AI AnalysisはGraphを直接更新しない
- AI AnalysisはFinal Evidenceを根拠に候補Eventを生成する
- Eventの適用とCurrent Graphへの反映は別のProjection責務とする
- Decisionのconfirmedへの遷移を、解析Pipelineだけで自動確定しない
- Topic遷移とCurrent Topicの候補は生成できるが、Drift判定は行わない

これはRFC-0001の変更ではなく、解析PipelineからGraphへの書き込みをEvent経由に限定する明確化である。

## 4. Pipelineの責務と段階

### 4.1 概念的なData Flow

~~~text
Audio Input
    ↓
Audio / STT Boundary
    ↓
Partial Transcript / Final Transcript
    ↓
Transcript Evidence
    ↓
Utterance Finalization
    ↓
Context Assembly
    ↓
Discussion Analysis
    ↓
Candidate Discussion Events
    ↓
Event Stream
    ↓
Graph Materializer
    ↓
Current Discussion Graph / Map
~~~

### 4.2 Audio Inputの責務

Audio Inputは、会議用PCとマイクから会話を継続的に取り込む責務を持つ。

Audio Inputが担当する範囲:

- SessionとAudio入力の開始・終了を結び付ける
- 音声入力が継続しているかを検知できる
- STTへ処理可能な音声を渡す
- 入力停止や一時的な欠損を後段へ通知する

Audio Inputが担当しない範囲:

- 話者やTopicの意味理解
- Decisionの確定
- GraphへのNode追加
- Audio入力だけからのDrift判定

Raw Audioをどの期間保持するか、再STTに利用できるかは本RFCでは決定しない。保持されない場合、STT後の再解析はFinal Transcriptからのみ可能になる。

### 4.3 STTの責務

STTはAudioをTranscript Evidenceへ変換する責務を持つ。

最低限、次の概念を後段へ渡せることが望ましい。

- Transcript text
- Session reference
- 発話区間の開始・終了情報
- PartialまたはFinalの状態
- 同一発話の更新を識別できる参照
- STT結果が以前の結果を置き換える場合の関係
- Speaker情報が得られた場合の任意の参照

STTは、Discussionの意味構造を決定しない。

- Topic抽出はDiscussion Analysisの責務
- Decision確定はHuman Confirmationまたは別のDomain Policyの責務
- STTの信頼度をそのままDecisionの確度として扱わない

### 4.4 Transcript Evidenceの責務

Transcript Evidenceは、解析の根拠となる会話テキストを保持する。

Evidenceは、後段で次の用途に使われる。

- Discussion Eventの根拠
- Human Correctionの確認
- STT誤認識後の再解析
- Replay
- Evaluation
- Minutes生成への入力

Evidenceは意味構造のGraphではない。Graphに表示されないTranscriptもEvidenceとして保持できる必要がある。

### 4.5 Utteranceの責務

Utteranceは、解析Pipelineが扱う最小の発話単位である。

ただし、Utteranceと意味解析の単位は同じではない。

- Utterance: 音声・STT上の発話区間
- Analysis Window: 意味理解のためにまとめた複数Utteranceの範囲
- Discussion Entity: Analysis結果として得られるTopic、Idea、Decisionなど

この3つを分けることで、短い相槌や複数人による補足を、必要に応じて一つの意味単位として解析できる。

### 4.6 Discussion Analysisの責務

Discussion Analysisは、Final EvidenceとContextから、Discussion Event候補を生成する。

候補になり得るもの:

- 新しいTopicまたは既存Topicへの参照
- Idea / Opinion
- Option
- Question
- Concern
- Decision candidate
- Unresolved Itemに関する状態変化
- Action Item candidate
- Action ItemのOwner / Due Date。ただしFinal Evidenceに明示された値だけをaction node_detected Payloadへ設定し、明示されない値はnullとする
- Parking Lotに関する参加者操作または提案
- Topic transition candidate
- Current Topic candidate
- 中立的なAI Observation candidate

Discussion Analysisは、候補を生成するが、Graphを直接書き換えない。

ActionのOwner / DueをAnalyzerが設定する場合、該当値を裏付けるEvidence IDをCandidate Eventのsource_evidence_idsへ含める。発言者や会議慣行からの推測は行わず、Humanのupdate_action Eventで後から修正できる。

### 4.7 Event Streamの責務

Event Streamは、解析結果や参加者操作の履歴を保持する。

Pipelineからは、少なくとも次のような意味のEventを追加できる。

- Transcript Evidence reference
- Analysis Proposal
- Entity reference candidate
- Relation candidate
- Topic transition candidate
- Current Topic candidate
- Analysis failed / retryable
- Transcript superseded / reprocess requested

Human Correction EventやDecision confirmed Eventの生成元は、解析PipelineではなくUser ActionまたはDomain Policyである。

### 4.8 Graph Materializerの責務

Graph Materializerは、Event Streamを適用してDiscussion GraphとCurrent Projectionを更新する。

責務:

- Stable Entity IDの再利用
- Eventの順序・重複・Revisionの処理
- Relationの許可リストに基づく適用
- Entity Stateの更新
- Current Topicの確定状態の更新
- EventからのReplay
- 失敗したProjectionの再構成

PipelineはGraph Materializerを呼び出すことはあっても、Graphの内部状態を直接変更しない。

## 5. Partial Transcript / Final Transcript

### 5.1 Partial Transcript

Partial Transcriptは、発話途中の暫定Evidenceである。

推奨する扱い:

- 一時的な入力として保持できる
- 先読みや解析準備に利用できる
- 正規のDiscussion Eventの根拠にはしない
- Event Streamへ確定Eventとして追加しない
- Current GraphをPartialだけで変更しない
- Final Transcriptとの対応を保つ

PartialからCandidateを生成すること自体を完全に禁止する必要はない。しかし、そのCandidateは暫定であり、Finalization前に破棄・置換できる必要がある。

MVPでは、Mapの安定性を優先し、Partialのみを根拠とするGraph更新は行わないことを推奨する。

### 5.2 Final Transcript

Final Transcriptは、解析の正規入力となる確定済みEvidenceである。

Finalになったことは、発話内容の意味が正しいことを意味しない。STTの誤認識は残り得るため、Finalは「入力区間が閉じた」ことを示す状態として扱う。

Final Transcriptを受け取った後に、同じ発話区間についてより正しい結果が届く場合は、元のEvidenceを上書きせず、後続のSupersedeまたはCorrection関係として扱う。

### 5.3 PartialからFinalへのReconciliation

同一発話のPartialとFinalは、同じUtterance候補に関連付ける。

Final到着時:

1. Partial由来の暫定解析を正規状態に昇格させない
2. Final textを正規Evidenceとして登録する
3. Partial由来の候補を破棄またはFinal由来の候補で置換する
4. Finalを入力としてAnalysis Windowを再評価する
5. Event StreamにはFinalを根拠とするEventを追加する

Partialが画面上のTranscriptとして表示されるか、参加者に見せるかはUXの論点であり、RFC-0003へDeferredする。

### 5.4 Finalの後からの修正

STT ProviderがFinal結果を後から修正する場合を想定する。

- 旧Evidenceを消さない
- 新Evidenceが旧Evidenceをsupersedeする関係を保持する
- 影響範囲のAnalysis Eventを再処理対象にする
- 新しいAnalysis RevisionとしてEventを追加する
- 現在Graphは新Revisionを適用したProjectionへ更新する

どの範囲を再処理するかは、単一Utteranceだけでは不十分な場合がある。後述するAnalysis Windowと関連Topicを対象とする。

## 6. Utteranceの区切り方

### 6.1 選択肢

#### 案A: STT Providerの発話区切りをそのまま使う

実装は単純だが、短い区切りや誤った区切りがそのまま意味解析へ伝わる。

#### 案B: 無音時間だけで区切る

Providerに依存しにくいが、考えながら話す発言や相槌で分割されやすい。

#### 案C: STT区切り + 短い発話の結合

STTの区切りを基本とし、短い補足、相槌、連続発話をAnalysis Windowでまとめる。

#### 案D: LLMに意味単位の区切りを任せる

意味的には柔軟だが、最初の解析単位自体をLLMに依存し、遅延と再現性が増える。

### 6.2 推奨

MVPでは、案Cを推奨する。

- UtteranceはSTTが確定した発話区間を基本とする
- 意味解析は複数Utteranceを含む短いAnalysis Windowで行う
- 相槌だけで新しいEntityを作らない
- 複数発言が同じ論点を補足している場合は、既存EntityへのEvidence追加として扱う

具体的な無音時間、Window幅、話者交替の判定はProviderやUXに依存するため、本RFCでは固定しない。

### 6.3 Speaker情報

Speaker IdentificationはMVPの必須要件としてRFC-0001では確定していない。

Pipelineでは、Speaker情報を得られる場合に任意のEvidence metadataとして保持できる境界を用意する。ただし次を前提とする。

- Speaker情報がなくても解析が成立する
- Speaker情報をDecision確定の根拠にしない
- Speaker名の表示や発言者単位のUIはRFC-0003へDeferredする

## 7. Discussion Event生成タイミング

### 7.1 選択肢

#### 案A: Tokenごとに生成する

低遅延だが、Partialの揺れがそのままEventとMapへ伝わる。重複とNode名の揺れが増える。

#### 案B: Utterance Finalごとに生成する

単純で追跡しやすいが、短い相槌や連続した補足が別々に解釈される可能性がある。

#### 案C: 時間固定のBatchで生成する

処理量とコストを管理しやすいが、発話の意味単位とBatch境界がずれる。

#### 案D: Utterance Final + 短いCoalescing Window

Utteranceが閉じた後、関連する短い発話をまとめて意味解析する。発話が連続している場合は一つのAnalysis Windowとして扱う。

### 7.2 推奨

案Dを推奨する。

理由:

- Partialを確定Eventへ入れずに済む
- 相槌や補足による不要なNode生成を抑えられる
- Analysisの入力を再現しやすい
- Map更新を小さなBatchにまとめられる
- RDの発言から画面反映まで数秒〜10秒程度という目標に対応しやすい

Windowの終了条件は、次の組み合わせとして扱う余地を残す。

- UtteranceがFinalになった
- 短い待機または発話の区切りが検出された
- Analysisに必要な最小文脈が揃った
- Session終了が指示された

### 7.3 Event候補の粒度

1回のAnalysis Windowから複数のCandidate Eventが出てもよい。ただし次の原則を置く。

- 同一EntityへのEvidence追加は新Nodeではなく参照Eventにする
- Candidate Eventには根拠Utteranceを付ける
- Decision candidateとconfirmedを同じEventとして扱わない
- Current Topic candidateとTopic transition candidateを区別する
- AI Observationは状態の説明候補であり、Domain Entityを無条件に追加しない

## 8. Graph更新タイミング

### 8.1 Event追加とGraph更新を分ける

Graph更新は、Analysisの途中結果を直接Graphへ反映するのではなく、Event Streamへの追加後に行う。

~~~text
Final Evidence
    ↓
Analysis Window closed
    ↓
Candidate Events appended
    ↓
Event validation / deduplication
    ↓
Graph Materializer applies a batch
    ↓
Current Projection updated
~~~

### 8.2 AtomicなAnalysis Batch

1つのAnalysis Windowから生じる関連Eventは、可能な範囲で一つのBatchとしてGraphへ適用する。

例えば、次の3つを別々の画面更新にしない。

- Questionの追加
- Optionの追加
- Decision candidateの追加

これらを同じAnalysis Batchとして適用すれば、Mapが一時的に不整合になる可能性を下げられる。

### 8.3 Graph更新の失敗

Event Streamへの追加が成功し、Graph Materializerが失敗した場合:

- Eventを失わない
- Current Graphは直前の整合した状態に留める
- Materializerを再実行する
- 画面に中途半端なGraphを反映しない

Graph Projectionの失敗をLLMへ再送する必要はない。入力の意味解析とProjectionは別責務である。

### 8.4 CandidateのGraph反映

CandidateをGraphへ反映するかどうかは、Candidate表示のUXに依存する。

PipelineとしてはCandidateをEvent Streamへ記録する。ただし、Current GraphでどのCandidateをVisibleにするか、Confirmedとどう区別するかはRFC-0003へDeferredする。

この分離により、Candidateを記録することと、参加者に確定情報として見せることを混同しない。

## 9. Incremental Processing

### 9.1 基本方針

Session全体を毎回LLMへ渡すのではなく、確定した新しいAnalysis Windowを中心にIncremental Processingする。

各Windowでは次を参照する。

- 新しいFinal Utterance
- Current Graphの関連部分
- Current Topic候補
- 直近のTopic遷移
- 未解決のQuestion、Concern、Open Issue
- 最近のDecision candidateとconfirmed Decision
- Session Goal、Title、Background
- 必要な過去Evidence

### 9.2 既存Entityの再利用

新しい発言が既存Topicに関するものなら、新しいTopicを毎回作らず、既存Topicへの参照候補を生成する。

次の情報をAnalysis入力に含める。

- 既存Entityの表示名
- Alias
- 関係する直近Evidence
- 既存Relation
- 既存EntityのState

Identityの最終ルールはRFC-0001に従い、自由な自動Mergeを行わない。

### 9.3 Incrementalの再計算範囲

通常は新しいAnalysis Windowと関連Entityだけを処理する。

次の場合は局所的な再計算を行う。

- Final Transcriptが修正された
- 既存Evidenceがsupersedeされた
- Decision candidateの根拠が変わった
- Current Topic候補に影響する遅延Eventが届いた
- Human Correctionが関連Entityの意味を変更した

全Sessionの再計算は、明示的なReplayまたは大きな解析Revisionのときに限定する。

## 10. Retry / Reprocess

### 10.1 RetryとReprocessの違い

- Retry: 同じ入力、同じ解析Revisionで一時的な失敗を再試行する
- Reprocess: Evidenceまたは解析方針の変更を受け、異なるRevisionとして再解析する

RetryとReprocessを混同すると、同じEventの重複や履歴の上書きが起こる。

### 10.2 Retryの原則

- 入力Evidenceを同一参照で再利用する
- 同じ処理単位を識別できる
- 成功済みEventを二重追加しない
- Retry回数を超えてもTranscriptと過去Graphを失わない
- Retry失敗をAnalysis Failure Eventとして追跡できる

Retryの回数、待機時間、Circuit Breakerなどは実装設計にDeferredする。

### 10.3 Reprocessの原則

Reprocessは、既存Eventを破壊せず、新しいAnalysis Revisionとして行う。

~~~text
Evidence revision 1
        ↓
Analysis revision 1
        ↓
Graph projection revision 1

Evidence correction
        ↓
Analysis revision 2
        ↓
Graph projection revision 2
~~~

現在のMapには採用されたRevisionを反映し、過去RevisionはReplayとEvaluationのために残す。

### 10.4 Session終了後の再処理

会議中に解析が失敗した場合でも、Session終了後にFinal Transcriptから再処理できる。

ただし、会議中のMapが後から完全に変わると参加者の記憶と一致しない可能性がある。再処理結果を現在Mapへ反映する際の表示・通知ルールはUXの論点としてRFC-0003へDeferredする。

## 11. Out-of-order Event

### 11.1 発生要因

- STTのPartialとFinalの到着順が入れ替わる
- 遅いFinalが先に処理されたWindowの後で届く
- LLMのRetry結果が元の処理より遅れて返る
- 複数のAnalysis Windowが非同期に完了する
- Graph Projectionの処理順とEventの生成順が異なる

### 11.2 Event TimeとProcessing Time

少なくとも次の時間を区別する。

- Event time: 発話または操作が発生した時点
- Processing time: Pipelineが処理した時点
- Commit time: Event Streamに採用された時点

Mapの表示順やTopicの移動をProcessing timeだけで決めない。

### 11.3 推奨方針

MVPでは、Session単位で次の順序制御を行う考え方を推奨する。

1. 同一UtteranceのPartialをFinalへ収束させる
2. Final化されたEvidenceに対するAnalysis Windowを閉じる
3. Window内のEventをまとめてEvent Streamへ追加する
4. 遅れて届いたEventは、元のEvidenceと因果関係を持つ遅延Eventとして記録する
5. 影響範囲を局所Reprocessする
6. Graph Projectionを新しいRevisionで更新する

複数Sessionを跨いだ分散順序制御はMVPの前提にしない。

### 11.4 遅延Eventで過去を上書きしない

遅延Eventが届いた場合、直前のEventを削除・改変しない。

- Late Eventとして履歴を保持する
- どのEvidenceの後に関係するかを記録する
- 必要なら新RevisionのProjectionを作る
- 現在Mapの差分はStable Entity IDに基づいて適用する

## 12. LLM / STT失敗時の挙動

### 12.1 STT失敗

STTが一時的に失敗した場合:

- Audio Inputを可能な限り継続する
- 失敗した区間を意味Entityとして推測しない
- 既存TranscriptとGraphを壊さない
- 再STT可能な場合は同じAudio区間を再処理する
- 再STTできない場合は解析Gapとして履歴に残す

音声を保持しない構成では、STT失敗区間を後から復元できない。その可否はデータ保持方針のOpen Questionである。

### 12.2 LLM / Discussion Analysis失敗

LLMまたはDiscussion Analysisが失敗した場合:

- Final Transcriptを失わない
- 既存のCurrent Graphを変更しない
- Candidate Eventを中途半端に追加しない
- Retry対象として記録する
- Retryが失敗しても、次のAnalysis Windowの入力を受け付ける
- 後から局所Reprocessできるようにする

解析失敗を補うために、LLMが推測でNodeを追加してはならない。

### 12.3 Event Validation失敗

Analysis結果が期待する意味構造に変換できない場合:

- 生のAnalysis結果をそのままGraphへ渡さない
- Candidate Eventを無効として記録できる
- EvidenceとAnalysis Revisionを保持する
- Event Streamの整合性を壊さない

具体的なSchema Validationの方式は実装設計にDeferredする。

### 12.4 Discussion継続性

AI処理の失敗で会議全体を止めない。

- AudioとSTTの継続を優先する
- Mapは最後に整合した状態を表示し続ける
- 失敗したAnalysisは後から補完可能にする
- Visual生成やMinutes生成は別の非同期処理として、Live Analysisをブロックしない

## 13. STT誤認識時の再解析

### 13.1 誤認識の扱い

Final Transcriptであっても、次のような誤認識があり得る。

- 固有名詞の誤り
- 否定表現の欠落
- 話者の混同
- 数字や期限の誤り
- 発言区間の結合・分割の誤り

STTの誤りは、AIが意味解釈で勝手に修正したことにしない。Evidenceの修正とDiscussion Analysisの再処理を分ける。

### 13.2 再解析範囲

影響範囲は最小限から始める。

1. 修正されたUtterance
2. 同じAnalysis Window
3. 直前後の関連Utterance
4. 関連するTopic、Question、Decision candidate

Session全体への影響が明らかな場合だけ、Session全体Replayを検討する。

### 13.3 Decisionへの影響

STT修正でDecision候補の意味が変わる場合:

- 旧Decision candidateの根拠が古いことを保持する
- 新しいAnalysis Revisionで候補を再生成する
- confirmed Decisionを解析Pipelineだけで自動撤回しない
- Human CorrectionまたはDomain Policyによる確認を必要とする

これは、STTの訂正と人間のDecision変更を混同しないためである。

## 14. Context Windowの構成

### 14.1 全Transcriptを毎回渡す方式の問題

30〜60分のDiscussionでは、全Transcriptを毎回Contextへ含めると次の問題が起こる。

- Contextが増え続ける
- 解析遅延とコストが増える
- 直近の発言が埋もれる
- 古い表現の揺れが新しいNode生成を誘発する
- ProviderごとのContext制限に依存する

### 14.2 推奨するContextの層

Contextは、次の層から構成する。

#### Layer 1: Session Context

- Discussion Title
- Discussion Goal
- Background / Context

#### Layer 2: Current Graph Context

- Current Topicの候補または確定状態
- Active Topic
- Open Question / Unresolved Item
- Concern
- Decision candidate / confirmed Decision
- Action Item candidate
- Parking Lot reference

#### Layer 3: Recent Final Utterances

直近のFinal Utteranceと、現在のAnalysis Windowに属する発言。

#### Layer 4: Relevant Historical Evidence

Current Topicや新しい発言に関係する過去Evidence。全Transcriptではなく、既存EntityやRelationに基づいて選択する。

#### Layer 5: Derived Running Summary

長いDiscussionの圧縮された要約。SummaryはEvidenceやEventの代替ではなく、再構成可能な派生情報とする。

#### Layer 6: Recent Flow

直近のTopic遷移、未解決Topicから離れた状態、戻った状態などのFlow情報。

### 14.3 Summaryの扱い

SummaryをSource of Truthにしない。

- Summaryの根拠Evidenceを参照できる
- Summaryが壊れてもEvent Streamから再生成できる
- Summaryから新しいDecisionを直接確定しない
- Summaryを更新するEventまたはRevisionを保持する

### 14.4 Context肥大化対策

MVPでは次の組み合わせを推奨する。

- Recent UtteranceのSliding Window
- Current Graphの小さな状態
- 関連EntityのEvidence参照
- 定期的なDerived Summary
- Session Goal / Backgroundの常時保持

Summaryの更新頻度、Windowの長さ、関連Evidenceの検索方法はProviderとEvaluationに依存するため、本RFCでは数値を確定しない。

## 15. Current Topicを解析Pipelineでどこまで扱うか

### 15.1 Pipelineが担当する範囲

Discussion Analysisは、次を候補として生成する。

- 発言が関係しそうな既存Topic
- 新しいTopic候補
- Topic transition candidate
- Current Topic candidate
- 元のTopicが未解決のまま残っているという観測

候補には根拠UtteranceとAnalysis Revisionを関連付ける。

### 15.2 Pipelineが担当しない範囲

次はPipelineだけで確定しない。

- その移動が「悪い脱線」であるという判定
- Current Topicの画面上の強調方法
- 複数Topicのどれを主Topicと呼ぶかのUX
- 参加者に戻ることを促す命令
- TopicのHuman Merge

### 15.3 Current Topicの推奨境界

Current Topicは、次の二段階で扱う。

1. PipelineがCurrent Topic candidateを生成する
2. Event StreamとGraph Projectionが、定められたPolicyに従ってCurrent Topicの状態を更新する

単一のPartialや曖昧な一発言だけでCurrent Topicを変更しない。Final Utteranceを含むAnalysis Window、既存Topicとの整合性、直近の遷移などを根拠とする。

どの程度の継続をもってCurrent Topicを確定するかは、Mapの視覚表現と密接に関係するため、RFC-0003へDeferredする。

Prototype 1のState Contractは次のとおりである。Humanのset_current_topicはhuman_corrected Overrideとして優先し、Node追加、Relation追加、Confidence変化だけでは解除しない。次の明示的topic_focus_changedまたはset_current_topicでFocusを更新する。対象Topicがparkedになった場合は、Override中であってもCurrent TopicをnullにしてOverrideを解除する。restore_from_parking_lotはFocusを自動復帰させず、次の明示Focus Eventだけが復帰させる。

### 15.4 Drift Awareness

Pipelineは、次の組み合わせをEventとして出せる。

- from Topicが未解決
- to Topicが現在の候補
- 遷移を示すEvidence

このEventを「Drift」と命名して悪い意味を付けない。Drift Awarenessの文章や表示は、RFC-0003のUXで設計する。

## 16. Latency目標

### 16.1 RDとの整合

RDのNFR-01では、発言から画面反映まで数秒〜10秒程度を目標としている。

このRFCでは、次のように分解して評価する。

1. AudioからSTT FinalまたはUtterance closeまで
2. Utterance closeからAnalysis Event候補生成まで
3. Event追加からGraph Projection更新まで
4. Graph Projectionから画面反映まで

### 16.2 MVPの目標

MVPでは、通常状態においてFinal UtteranceまたはAnalysis Windowの確定からCurrent Graph更新までを、数秒〜10秒程度の範囲に収めることを目標とする。

ただし、正確なp50、p95、最大値、ProviderごとのSLOは本RFCでは固定しない。

### 16.3 速度と安定性の優先順位

Partialを使って数百ミリ秒でMapを変えるより、Final Evidenceに基づき数秒遅れて安定したMapを更新する方が、MVPの検証目的に適している。

Live Analysisが一時的に遅れても、AudioとTranscriptの取り込みを継続できることを優先する。

### 16.4 非同期処理

次の処理はLive Discussion Analysisをブロックしない。

- Visual Artifact生成
- Meeting Minutes生成
- 長期Replay
- 全Session再解析
- 低優先度の統計処理

## 17. 30〜60分Sessionでの継続性

### 17.1 継続利用上の課題

- Transcriptが増え続ける
- TopicやRelationが増え続ける
- Current Topicの候補が履歴に埋もれる
- LLMのContextに過去の情報が過剰に入る
- Graph ProjectionとSummaryがずれる

### 17.2 推奨する運用

- Transcriptは全体として保持し、Analysis入力はWindow化する
- Event StreamはSession全体の履歴として保持する
- Current Graphは現在必要なProjectionとして扱う
- Summaryは派生情報として定期的に更新する
- 既存Entityの再利用を優先する
- Mapに表示しない古いEvidenceも削除しない
- 大きなMapの省略・折りたたみはUXで決める

### 17.3 Session終了時

Session終了操作は、Audioの取り込みとLive Analysis Windowの閉鎖を開始する。

未処理のFinal Transcriptがあれば、可能な範囲で最後のAnalysis Batchを作成する。

Minutes生成は別Pipelineで行い、Live Graphの最後のProjectionとTranscript Evidenceを入力として利用する。Minutes固有の設計はRFC-0005へDeferredする。

## 18. Replay / Evaluation

### 18.1 Replayの目的

Replayは、単に過去を再生するためだけではない。

- STT誤認識の影響を調査する
- LLM解析の変更を比較する
- Node重複率を測定する
- Current Topicの安定性を評価する
- Decision誤確定を測定する
- Map更新遅延を測定する
- Human Correction前後を比較する

### 18.2 Replayの入力

Replayには、少なくとも次を利用できるようにする。

- Final Transcript Evidence
- PartialとFinalの関係が必要な場合のTranscript履歴
- Event StreamのRevision
- Session Context
- Analysis Policyまたはモデルの識別情報

Raw AudioからのFull ReplayをMVPに必須とするかは、Audio保持方針に依存する。

### 18.3 Replayの出力

Replay結果は、既存Eventを上書きせず、別Analysis Revisionとして記録する。

比較対象:

- Event差分
- Entity追加・再利用・重複
- Relation差分
- Current Topicの遷移
- Decision candidate / confirmedへの影響
- ProjectionのMap Churn

### 18.4 Evaluation指標候補

最終的なSuccess MetricsはRDに従うが、Pipelineの診断には次を利用できる。

- Final UtteranceからEventまでのLatency
- EventからGraph更新までのLatency
- 同一Topicの重複生成率
- Label変更回数
- Late Eventによる再処理率
- Analysis Failure率
- Decision candidateの誤確定率
- Current Topicの不必要な切替回数
- Replay時の再現性

これらはプロダクト成功の代替ではなく、原因分析用の指標である。

## 19. Provider依存の抽象化

### 19.1 抽象化の原則

Providerを交換可能にするために、すべてを抽象化する必要はない。MVPでは、ドメインに影響する境界だけを抽象化する。

### 19.2 STT Boundary

STT Adapterは、Provider固有の結果を次の概念へ変換する。

- Partial / Final
- Utterance reference
- Text
- Time range
- Supersedes relation
- Optional speaker reference
- Provider metadataの参照

Provider固有のstatus名やIDは、Discussion GraphやDomain Eventへ直接漏らさない。

### 19.3 Analysis Boundary

Analysis Adapterは、LLMや別の解析器の出力を、MVP用の候補へ変換する。

- Entity candidate
- Relation candidate
- Topic transition candidate
- Current Topic candidate
- Decision candidate
- Observation candidate
- Evidence references
- Analysis revision

Provider固有のTool Call、Prompt、Response形式は境界の外に置く。

### 19.4 抽象化しすぎない

次のような過度な汎用化はMVPでは避ける。

- 任意のGraph操作を許すUniversal Agent API
- すべてのProviderの機能を一つのLowest Common Denominatorへ潰す
- 将来の多言語・多会議方式まで含む巨大なEvent Schema
- Provider固有機能をDomain Stateへ早期に取り込む

MVPの日本語対面Discussionに必要な最小能力だけを契約として定義する。

## 20. Alternatives / Trade-offs

### 20.1 Pipeline方式の比較

| 方式 | 低遅延 | Map安定性 | 実装容易性 | Retry / Replay | Context肥大化 | MVP適合性 |
| --- | --- | --- | --- | --- | --- | --- |
| Token単位End-to-End Streaming | 高 | 低 | 中 | 低 | 高 | 低 |
| FinalのみSession終了後Batch | 低 | 高 | 高 | 高 | 中 | 低 |
| Final Utterance単位Incremental | 中 | 高 | 中 | 中〜高 | 中 | 中 |
| Final Utterance + Coalescing Window | 中〜高 | 高 | 中 | 高 | 低〜中 | 高 |

### 20.2 Token単位Streaming

#### 利点

- 解析開始が早い
- Partial Transcriptを積極的に活用できる

#### トレードオフ

- Mapの揺れが大きい
- LLM出力の中間状態を扱う必要がある
- Retryと重複除去が難しい
- 人間の視線を頻繁に動かす可能性がある

### 20.3 Session終了後Batch

#### 利点

- 入力が確定してから解析できる
- Contextを一括で整理できる
- Graphの一貫性を保ちやすい

#### トレードオフ

- RDの会議中のMap価値を満たさない
- Current TopicやDrift Awarenessが会議中に使えない

### 20.4 Final Utterance単位Incremental

#### 利点

- Mapの更新を会話中に行える
- EvidenceとEventを対応付けやすい
- Partialの揺れを抑えられる

#### トレードオフ

- 短い発言の文脈が不足する
- 相槌や補足が過剰なEventを生む可能性がある

### 20.5 Final Utterance + Coalescing Window

#### 利点

- Finalベースの安定性とリアルタイム性を両立しやすい
- 複数発言を一つの意味単位として扱える
- EventをBatch化しやすい
- 30〜60分のContext管理に適する

#### トレードオフ

- 反映に短い待ち時間が発生する
- Window終了条件の設計が必要
- 参加者が即時反映を期待すると遅く見える可能性がある

### 20.6 推奨

MVPでは、Final Utterance + Coalescing Windowを採用候補とする。

## 21. 推奨アーキテクチャ

### 21.1 概要

推奨するPipelineは次のとおりである。

1. Audio InputはSession中のAudioを継続的にSTT Boundaryへ渡す
2. STTはPartialとFinalを区別してTranscript Evidenceを生成する
3. Partialは暫定入力として扱い、Graphの正規更新には使わない
4. Final UtteranceをAnalysis Windowへまとめる
5. Context AssemblerがSession Context、Current Graph、Recent Evidence、Relevant Historyを組み立てる
6. Discussion AnalysisがTyped Candidate Eventを生成する
7. Candidate EventをEvent Streamへ追加する
8. Graph MaterializerがEvent Batchを適用する
9. Current Discussion GraphをMapへ渡す
10. 失敗・遅延・修正はEventとRevisionを通じて再処理する

### 21.2 推奨案の責務境界

~~~text
Audio Layer
  音声を運ぶ。意味を決めない。

STT Layer
  音声をTranscript Evidenceへ変換する。

Utterance Layer
  Final Evidenceを解析単位へまとめる。

Analysis Layer
  EvidenceとContextからCandidate Eventを生成する。

Event Layer
  Candidate、Correction、Failure、Revisionの履歴を保持する。

Graph Materializer
  Eventから現在のDiscussion Graphを構成する。

UX Layer
  Graph、Current Topic、Candidate、Observation、Flowをどう見せるか決める。
~~~

### 21.3 Current Topicの境界

PipelineはCurrent Topic candidateとTopic transition candidateまでを生成する。ParkされたTopicを再びCurrent Topicへ戻す意図は、通常のNode検出やConfidence変化ではなく、明示的なTopic focus changeとして表現する。

Graph Materializerは、Eventの適用結果としてCurrent Topicを保持する。ただし、どのCandidateを参加者にCurrent Topicとして見せるか、何回のEvidenceで切り替えるか、複数Topicをどう見せるかはRFC-0003へDeferredする。

### 21.4 Decisionの境界

PipelineはDecision candidateを生成できる。

Pipelineはconfirmed Decisionを自動生成しない。Confirmedへの遷移は、Human Confirmationまたは別途合意されたDomain Policyから生じるEventとして扱う。

この方針により、AIの解析能力と参加者の最終判断を分離する。

## 22. Risks / Trade-offs

### 22.1 Final待ちによる遅延

PartialをGraph更新に使わないため、Token単位Streamingより遅く見える可能性がある。

ただし、MVPではMapの安定性を優先し、数秒〜10秒程度の反映目標とのバランスを取る。

### 22.2 Coalescingによる誤結合

別Topicの発言を一つのAnalysis Windowにまとめると、誤った関係が生成される可能性がある。

Windowを過度に長くせず、既存Topic・Evidence・Flowを参照しながら、関係が不明な場合は無理に結合しない。

### 22.3 再処理によるMap変更

STT訂正やLLM再解析で過去のCandidateが変わると、現在Mapも変わる可能性がある。

RevisionとEvidenceを残し、変更理由を追跡できるようにする。変更を画面でどう知らせるかはRFC-0003へDeferredする。

### 22.4 Context Summaryの誤り

Summaryが間違うと、後続Analysisが誤った文脈を参照する可能性がある。

SummaryをSource of Truthにせず、重要なDecisionやQuestionにはFinal Evidenceを再参照できるようにする。

### 22.5 Provider差

Partial、Final、Speaker、Timestamp、Correctionの能力がProviderごとに異なる。

最小のCapability Boundaryを定義し、利用できない能力はOptionalとして扱う。Provider固有の差をGraphのDomain Stateへ直接持ち込まない。

### 22.6 Failure Gap

解析失敗が続くと、Current Graphが一時的に古いままになる。

最後に整合したGraphを表示しながら、Transcript取り込みを継続し、後から補完する。失敗を理由に推測Nodeを追加しない。

## 23. Open Questions

本RFCで新たに残る主なOpen Questionsは次のとおりである。

### OQ-2001: Analysis Windowの終了条件

無音、STT Final、時間、Topic変化などをどの組み合わせでWindow終了とするか。

### OQ-2002: Latency目標の具体化

RDの数秒〜10秒程度という目標を、どの区間、分位点、負荷条件で測定するか。

### OQ-2003: Partial TranscriptのUI利用

Partialを画面上に表示するか、解析準備だけに使うか。これはRFC-0003で決定する。

### OQ-2004: Current Topic CandidateのEmission / 表示閾値

Prototype 1のMaterializer Contract（Human Override、parked時の解除、明示Focusでの復帰）は確定した。残るのは、Analyzerが何回のFinal Evidence、どの程度の継続性でtopic_focus_changedを生成するか、UXがそれを何秒・何Window遅延して表示するかであり、RFC-0003のValidation Parameterとして検証する。

### OQ-2005: 遅延EventのReprocess範囲

単一Utterance、Analysis Window、関連Topic、Session全体のどこまで再解析するか。

### OQ-2006: Summaryの更新頻度

Summaryをいつ作成・更新し、どのEvidenceを必ず再参照するか。

### OQ-2007: STT失敗時のAudio保持

STT失敗区間をRaw Audioから再処理できるようにするか。保持期間とアクセス制御は別途決定する。

### OQ-2008: Provider Capabilityの最小集合

Timestamp、Speaker、Final correction、Partialなどのうち、MVPで必須とするProvider能力は何か。

### OQ-2009: Analysis結果の保存粒度

Providerの生出力、正規化後のCandidate、失敗情報をどの範囲で保持するか。

### OQ-2010: Decision Confirmationの入力経路

Prototype 1ではUI等からの明示的なHuman confirm_decision CommandだけをConfirmed Eventの入力とする。Voice Intentや明示発話を同じCommandへ変換する将来の入力経路はRFC-0003または後続RFCで検証する。Pipeline自体はCandidateまでに留める。

## 24. RFC-0001 Open Questionsの扱い

### 24.1 RFC-0002で部分的に扱ったもの

#### OQ-01: DecisionのConfirmed条件

解析Pipelineの決定として、AI AnalysisはDecision candidateまでを生成し、confirmedを直接生成しないことを明確化した。

ただし、最終的な確認操作、明示発話、UI表現のどれを採用するかは未決であり、RFC-0003へDeferredする。

#### OQ-02: CandidateのMap表示

PipelineはCandidate EventをEvent Streamへ記録する。CandidateをCurrent Graphでどのように見せるかはRFC-0003へDeferredする。

#### OQ-06: Speaker Identification

PipelineはSpeaker metadataをOptionalに保持できるが、MVPの解析成立条件にはしない。表示とUXはRFC-0003へDeferredする。

#### OQ-07: Topic Mergeの操作タイミング

Pipelineはduplicate_ofまたはMerge候補を生成しても、自動Mergeを実行しない。Human操作のタイミングとUIはRFC-0003へDeferredする。

#### OQ-12: Current Topicの変更条件

PipelineはCurrent Topic candidateとTopic transition candidateを生成する。切替の閾値、継続条件、画面上の扱いはRFC-0003へDeferredする。

#### OQ-15: 再解析Revision

Evidence修正や解析方針変更は、既存Eventを上書きせず、新しいAnalysis RevisionとしてReprocessする方針を定めた。再解析の運用UIや通知は後続RFCへDeferredする。

### 24.2 RFC-0003へDeferred

- OQ-02のCandidateの表示方法
- OQ-03: AgreedとDecidedの区別のUX
- OQ-04: QuestionとUnresolved Itemの表示・操作
- OQ-06のSpeaker表示
- OQ-07のHuman Merge操作
- OQ-08: Mapの上限、折りたたみ、要約表示
- OQ-09: Flowの表示方法
- OQ-10: User-facing Undo
- OQ-12のCurrent Topic切替表示
- OQ-13: Evidenceの参照表示
- OQ-14: 複数の主Topicの表示

### 24.3 RFC-0004へDeferred

- OQ-11: Visual ArtifactのVersion、比較、差し替え、採用状態

### 24.4 RFC-0005へDeferred

- OQ-05: Action Itemの担当者、期限、完了状態をMinutesとどう扱うか
- Decision、Unresolved Item、Action Itemの最終的なMinutes出力表現

### 24.5 本RFCの範囲外として残すもの

- データ保持期間、Raw Audio保持、アクセス制御
- Providerごとの料金・リージョン・製品選定
- 具体的なDB、Queue、Streaming実装

これらは必要に応じて別のArchitectureまたはOperations RFCで扱う。

## 25. Decision

### Proposed

本RFCの初稿として、以下を提案する。

- Audio、STT、Transcript Evidence、Utterance、Discussion Analysis、Event Stream、Graph Materializerの責務を分離する
- TranscriptはEvidenceとして扱い、AIがGraphを直接更新しない
- Partial Transcriptは暫定入力に留め、Partialだけで正規のGraph更新を行わない
- Final Utteranceを短いCoalescing WindowにまとめてIncremental Analysisする
- Discussion AnalysisはTyped Candidate Eventを生成し、Event Streamへ追加する
- GraphはEvent BatchをMaterializeして更新する
- DecisionはcandidateまでをPipelineの出力とし、confirmedを解析Pipelineだけで自動確定しない
- Current Topicは候補と遷移をPipelineで扱う。Human Override、parked時の解除、明示Focusでの復帰はCanonical Contractとし、Emission閾値とUX上のHysteresisはRFC-0003へDeferredする
- STT修正、LLM失敗、Out-of-order EventはEvidenceとRevisionを保持して局所Reprocessする
- Summaryは派生情報とし、EvidenceやEvent Streamの代替にしない
- 30〜60分のSessionでは、Recent Utterance、Current Graph、関連Evidence、Derived Summaryを組み合わせてContextを構成する
- Provider依存はSTT BoundaryとAnalysis Boundaryに限定し、Provider固有情報をDomain Modelへ直接漏らさない
- Visual生成、Minutes生成、Replay、全Session再解析はLive Analysisをブロックしない

### Accepted

なし。初稿のため、承認済みの項目はない。

### Rejected

MVPの推奨案としては、以下を採用しない。

- Partial Transcriptだけで正規のGraphを更新する方式
- TokenごとにDiscussion Eventを確定する方式
- Session全体を毎回LLMへ渡す方式
- LLMやSTT失敗時に推測でNodeやDecisionを追加する方式
- AI AnalysisがGraphを直接上書きする方式
- AI AnalysisだけでDecisionをconfirmedにする方式
- 遅延Eventで過去Eventを削除・書き換える方式
- Provider固有のStatusやIDをDiscussion GraphのDomain Stateにする方式

**RFC Status: Proposed**
