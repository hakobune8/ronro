# Type D Multi-turn Decision Spike

Status: Completed

このSpikeは、Proposal + AgreementからSemanticなCandidate Decisionを作る限定的な処理の価値を評価するための、決定的・オフラインの検証である。LLM APIは呼び出していない。Baseline、Prompt、Context v1、Golden v2、Evaluation v2、Canonical Event Schema、Materializerは変更していない。

Run ID: `type-d-multiturn-spike-v1`

## Product Need

通常AnalyzerがAgreement-onlyの発言をNo-opとして扱う場合、次のような会話で、実質的な選択がDiscussion Mapに残らない可能性がある。

```text
A: MVPではスマホを外す案でどうでしょう
B: それでいきましょう
```

ProposalとAgreementが一意に対応している場合、そこからCandidate Decisionを作ると、参加者が後から確認すべき論点をMapへ残せる。一方、誤ったDecisionは「決まった」という印象を与えるため、Missed CandidateよりFalse Candidateのコストが高い。

したがって、Type Dは通常Analyzerを緩める機能ではなく、Agreement-likeな現在発言に限定して起動する安全側の補助層として評価した。

## Dataset

専用Dataset `type-d-multiturn-spike-v1` は18ケースで、Positive 5件、Negative 13件である。ProposalはCanonical Graph上のOption / Ideaとして与え、Agreement発言は現在Utteranceとして与えた。Golden v2や既存5 Scenarioは変更していない。

| Category | Cases | Expected positive |
| --- | ---: | ---: |
| Strong Proposal + Strong Agreement | 5 | 5 |
| Weak Proposal + Strong Agreement | 3 | 0 |
| Strong Proposal + Weak Agreement | 3 | 0 |
| Multiple Proposal / ambiguous | 2 | 0 |
| Existing Candidate + Agreement | 1 | 0 |
| Topic change + Agreement | 1 | 0 |
| No Proposal + Agreement | 2 | 0 |
| Same-speaker substantive utterance | 1 | 0 |
| **Total** | **18** | **5** |

このDatasetはLayerの境界を分離して確認するためのものなので、自然な長時間TranscriptやM5 UIのユーザビリティを代表するものではない。

## Baseline

Baselineは、`analyzer-prompt-v4`のAgreement-only挙動を固定し、通常AnalyzerだけではCandidate Eventを生成しないものとした。

| Metric | Normal Analyzer only |
| --- | ---: |
| Cases | 18 |
| Expected Type D positives | 5 |
| Predicted positives | 0 |
| Type D Precision | N/A |
| Type D Recall | 0.0000 |
| False Candidate | 0 |
| Ambiguous Reference Rejection | 1.0000 |
| Existing Candidate Duplicate Rate | 0.0000 |
| Automatic Confirmation | 0 |

これはLLMの再実行結果ではなく、Agreement-only入力に対する凍結済みBaselineの挙動である。

## Proposed Layer

評価したDedicated Layerは次の処理である。

```text
Current Agreement Utterance
        ↓  (Strong Agreement trigger only)
Current TopicのCanonical Graph
        ↓
Proposal Lookup
        ↓  (unique, strong, non-archived proposal only)
Candidate Decision Event
        ↓
Existing Schema Validation / Materializer
```

LayerはPrevious 1をGlobal Contextへ追加しない。入力はCurrent Utterance、Current Graph、Recent Canonical Eventsだけである。

Layerが生成するのは既存の`node_detected`（`node_type=decision`）と必要な`contains` Relationだけであり、MaterializerがCandidate statusを付与する。`confirm_decision`、`confirmed`、Human Confirmation Eventは生成しない。既存CandidateがあればNo-opとし、複数Proposalや弱いProposalの場合もNo-opとした。

## Reference Resolution

Proposal探索Windowを比較した。

| Proposal Window | Precision | Recall | False Candidate | Ambiguous rejection |
| --- | ---: | ---: | ---: | ---: |
| Last 1 semantic event | 0.8333 | 1.0000 | 1 | 0.5000 |
| Last 2 semantic events | 1.0000 | 1.0000 | 0 | 1.0000 |
| Current Topic latest proposal（推奨） | 1.0000 | 1.0000 | 0 | 1.0000 |

`Last 1`は複数Proposalがあるケースで直近の一方を勝手に選び、誤Candidateを1件生成した。推奨方式はCurrent Topic配下の候補を列挙し、Proposalが一意でない場合は選択しない。これは「それ」が何を指すかを自然言語だけで推測するのではなく、Canonical State上の一意性を利用する安全側の解決である。

## Positive Cases

`td-001`〜`td-005`のStrong Proposal + Strong Agreementをすべて検出した。

例:

```text
Proposal: スマホ対応をMVPから外す案
Agreement: それでいきましょう
Output: decision Candidate（スマホ対応をMVP対象外）
```

ProposalとAgreementのEvidence IDをCandidate Eventの`source_evidence_ids`へ引き継ぎ、後から根拠を追跡できる形にした。

## Negative Cases

- Weak Proposal + Strong AgreementはCandidate化しなかった。
- Strong Proposal + `そうですね` / `まあいいと思います` / `ありですね`はCandidate化しなかった。
- 複数ProposalのAgreementは曖昧として拒否した。
- 既存Candidateがある場合は新Candidateを作らなかった。
- Current TopicがProposalのTopicと異なる場合は作らなかった。
- ProposalなしのAgreementはNo-opとした。
- 同一Speakerの内容豊富な発言はType Dでは処理せず、通常Analyzerの責務として残した。

## Metrics

### Default Layer

| Metric | Result |
| --- | ---: |
| Type D Precision | **1.0000** |
| Type D Recall | **1.0000** |
| False Candidate Count | **0** |
| Ambiguous Reference Rejection Accuracy | **1.0000**（2/2） |
| Existing Candidate Duplicate Rate | **0.0000**（0/1） |
| Automatic Confirmation | **0** |
| Determinism Failures | **0** |

同じ入力を2回処理した結果は全ケースで一致し、追加EventのSchema Validationも通過した。

### Baselineとの差分

Dedicated Layerは18ケース中5ケースでCandidateを追加した。Baselineからの増加は、Candidate Decision 5件、Potential Human Confirmation Target 5件である。誤Candidateは増えていない。

## Map Impact

Projection上は、通常Analyzerの0件からCandidate Decision 5件へ増えるため、Decision RailやTopic内のPending Decisionを有用に埋められる可能性がある。CandidateはConfirmedではないため、MapのDecision Safetyは維持される。

ただし今回のHarnessは18個の分離ケースを検証するもので、30分相当のMapを実際に連続ReplayしたUI評価ではない。したがって、Mapがうるさくなるか、Current TopicやRecent Flowを圧迫するかは未確定である。Type Dは発言ごとではなく、明確なProposal + 一意なAgreementごとに最大1件を追加する。

## Human Confirmation Burden

このDatasetではHuman Confirmation対象が0件から5件へ増えた。したがって、Type Dを有効にすると、検出したCandidate 1件につき原則1回の人間確認機会が増える。

30分会議あたりの候補数は、この18ケースからは統計的に推定できない。現時点で安全に言えるのは、30分内の「一意なStrong Proposal + Strong Agreement」の数を`k`とすると、追加Confirmation候補は最大`k`件ということだけである。次の検証では、30分相当Recorded Transcriptで`Candidates / 30 minutes`と、参加者が確認を負担に感じるかを測る必要がある。

## Architecture Cost

| Area | Assessment |
| --- | --- |
| Canonical State | 新しいState不要。既存Candidate Decisionを利用 |
| Event Schema / Materializer | 変更不要 |
| Replay | 決定的。入力GraphとEventsが同じなら同じCandidate Events |
| Evaluation | Agreement、Proposal強度、曖昧性、重複の専用Fixtureが必要 |
| Latency | 追加LLM Callなし。Graph/Event lookupのみで軽量 |
| Debugging | Agreement trigger、Proposal選択理由、曖昧拒否理由のTraceが必要 |
| LLM Call | **0** |

このため、実装複雑性は小さい。ただし通常AnalyzerとDedicated Layerが同じDecisionを生成しないよう、Candidateの重複排除と責務境界を維持する必要がある。

## Product Gate

安全性と構造面のSpike基準は満たしたが、Product Gateはまだ判定できない。Candidateを増やすこと自体は価値があり得る一方、会議中の確認負荷とDecision Railの密度を実会議相当で測っていないためである。

特に、Precision 1.0はこの専用Dataset上の結果であり、Real Analyzerが生成するProposal Nodeの品質や、長いDiscussionでのTopic誤所属を保証しない。

## Recommendation

現時点では、Type Dを通常Analyzerへ常時組み込むMVP機能としては採用しない。次の限定実験へ進める。

推奨する候補仕様は以下である。

1. Agreement-likeな現在発言だけをTriggerにする。
2. Current Topic配下にStrong Proposalが一意に存在する場合だけCandidate化する。
3. 複数Proposal、弱いAgreement、既存Candidate、Topic不一致はNo-opにする。
4. `confirm_decision`は絶対に生成しない。
5. 追加LLM Callは行わず、Canonical GraphとRecent Eventsから決定的に処理する。

次の実験では、30分相当のRecorded Transcriptを使い、Type D Candidate数、False Candidate、既存Candidateとの重複、Human Confirmation操作数、MapのDecision Rail密度を評価する。Prompt v5、Global Context変更、STT、Live AudioはこのSpikeの結果からは開始しない。

## Decision

**D. Needs Further Experiment**

理由は、限定DatasetではType D Precision / Recallとも1.0で、追加LLM Callなしの低コストな構成も確認できた一方、MVP採用を決めるための30分会議でのCandidate密度とHuman Confirmation負荷が未測定だからである。

現時点のMVP方針は「Type Dを標準採用しないが、決定的なOpt-in Layerとして実験継続」である。Canonical Contractの変更はない。
