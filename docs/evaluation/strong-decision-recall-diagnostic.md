# Strong Decision Recall Diagnostic

Status: Diagnostic Spike — Completed

Date: 2026-09-19

## Scope and constraint

This diagnostic investigates the two Strong Decision misses in Real Analyzer
Run #4:

- B-u006 (Architecture)
- E-u001 (Topic Return)

No LLM API was called. analyzer-prompt-v4, gpt-5.6-luna, the dataset, Golden
v2, the Canonical Schemas, the Materializer, and the Stable Discussion Map were
not changed.

The Recorded Analyzer baseline remains frozen as:

| Dimension | Frozen value |
| --- | --- |
| Prompt | analyzer-prompt-v4 |
| Golden | golden-v2 |
| Evaluation | analyzer-eval-v2 |
| Model | gpt-5.6-luna |
| Reasoning | medium |
| Run #4 Strong Decision Recall | 0.5000 (2 / 4) |

## 1. Evidence and observability

The following stored artifacts were used:

- Run #4 scenario-results and raw-evaluation.json;
- Run #4 final Graphs;
- the B and E Recorded Transcripts;
- Golden v2 annotations;
- AnalysisContextBuilder and the frozen v4 Prompt implementation.

The Run #4 artifacts store raw_output, context_chars, and token counts, but do
not store the complete provider request payload. Therefore the exact
serialized request body cannot be read back from the Raw Run. The effective
Context below was reconstructed offline with the same deterministic
AnalysisContextBuilder from the stored Transcript and accepted Events.

The reconstruction reproduced the recorded Context sizes:

| Utterance | Recorded context_chars | Reconstructed context_chars | Estimated tokens |
| --- | ---: | ---: | ---: |
| B-u006 | 3,696 | 3,696 | 924 |
| E-u001 | 887 | 887 | 222 |

This is sufficient to audit the Context shape and contents produced by the
current builder, but it is not a byte-level recovery of the original request.
Persisting a redacted request Context in future Evaluation Runs is a separate
observability improvement; it is not performed in this diagnostic.

## 2. B-u006 diagnostic

### Case context

| Item | Value |
| --- | --- |
| Current utterance | 「GraphをMaterializeする処理は決定的にして、LLMはそこから外す方針で進めましょう。」 |
| Previous 1 | B-u005: 「Graph全体を毎回渡す案と、Current Topicの周辺だけ渡す案があります。どちらもTopic Returnは壊したくありません。」 |
| Previous 2 | B-u004: 「ただ、LLMの応答待ちでMap更新が止まると会議には使えないので、失敗しても次の発言へ進めたいです。」 |
| Current Topic | node:real-b-architecture:real:real-b-architecture:real-b-u001:01 — 「Recorded TranscriptからDiscussion Graphへの変換構成」 |
| Context mode | derived |
| Golden v2 | Strong Decision: 「Materializeは決定的にしLLMを外す」 |
| Golden rationale | 明示的なArchitecture policy adoption — 「方針で進めましょう」 |

### Effective Relevant Nodes

Run #4 ContextにはCurrent Topicとその周辺の以下の7 Nodeが含まれていた。

| Type | Label |
| --- | --- |
| topic | Recorded TranscriptからDiscussion Graphへの変換構成 |
| idea | Recorded TranscriptをEvidenceとして残し、その後段にAnalyzerを置く構成 |
| idea | AnalyzerはGraphを直接更新せず、Candidate Eventだけ返してEvent Storeに積む構成 |
| idea | STT誤り時の再解析に備え、EvidenceとEventを分離する構成 |
| idea | LLM応答待ちや失敗でMap更新を止めず、次の発言へ進める構成 |
| option | Graph全体を毎回渡す案 |
| option | Current Topicの周辺だけ渡す案 |

### Effective Recent Events

The last eight Events in the reconstructed Context were sequences 9–16:

| Sequence | Evidence | Event | Meaning |
| ---: | --- | --- | --- |
| 9–10 | B-u003 | idea + contains | Evidence/Eventを分離する構成 |
| 11–12 | B-u004 | idea + contains | LLM失敗・遅延で会議を止めない |
| 13–16 | B-u005 | 2 options + 2 has_option | Graph全体かCurrent Topic周辺か |

The Context did contain structured prior state, but it did not contain the raw
text of B-u004 or B-u005. It also did not mark any Node as a proposal, policy,
or decision_target; the model received only type, label, status, and Event
payload summaries.

### Run outputs

| Run | Output classification |
| --- | --- |
| #2 / v2 | decision: 「GraphのMaterialize処理は決定的にし、LLMを処理から外す方針」 |
| #3 / v3 | decision + contains: 「GraphをMaterializeする処理を決定的にし、LLMを処理から外す方針で進める」 |
| #4 / v4 | idea + contains: 「GraphのMaterialize処理を決定的にし、LLMを処理から外す方針」 |

The v4 output was structurally valid and safely materialized. It did not
create a false confirmed Decision; it under-classified the candidate as an
Idea.

### Cause assessment

The primary cause is the v4 semantic rule, not a missing Canonical Node:

1. The current utterance already contains a concrete policy target and
   commitment language: 決定的にして, LLMはそこから外す, and 方針で進めましょう.
2. Prompt v4 explicitly says that an architectural principle or general
   direction is usually an Idea unless it clearly resolves an explicit
   competing option. It gives this exact pattern as an Idea example:
   「Graphを決定的にしてLLMを外す方針で進めましょう」.
3. The previous structured Context makes the architecture understandable,
   but the B-u005 options are about Context scope, not the policy selected by
   B-u006. The current Context therefore does not strongly mark the selected
   policy as a choice between named alternatives.
4. The absence of previous raw utterances is a secondary Context limitation.
   It would help explain how the policy was formed, but B-u006 is sufficiently
   explicit to be a Type A decision under Golden v2 even without it.

Golden v2 is defensible here: it treats explicit architecture-policy adoption
as a Strong Candidate. The mismatch is between that product policy and v4's
additional “explicit competing option” guard.

## 3. E-u001 diagnostic

### Case context

| Item | Value |
| --- | --- |
| Current utterance | 「まずMVP範囲を決めたいです。共有ディスプレイのDiscussion Mapを中心にしましょう。」 |
| Previous 1 | なし（セッション最初の発言） |
| Previous 2 | なし |
| Current Topic | primary_topic_id = null |
| Relevant Nodes | なし |
| Recent Events | session-created (sequence 1), session-started (sequence 2) のみ |
| Golden v2 | Strong Decision: 「共有ディスプレイのDiscussion MapをMVPの中心にする」 |
| Golden rationale | 明示的なMVP scope choice — 「中心にしましょう」 |

### Run outputs

| Run | Output classification |
| --- | --- |
| #2 / v2 | Topic 「MVP範囲」 + Open Item 「MVP範囲を決める」 + Idea 「共有ディスプレイのDiscussion MapをMVPの中心にする」 |
| #3 / v3 | Topic 「MVP範囲」 + decision 「共有ディスプレイのDiscussion MapをMVPの中心にする」 |
| #4 / v4 | Topic 「MVP範囲」 + Idea 「共有ディスプレイのDiscussion Mapを中心にする」 + Topic Focus |

### Cause assessment

The primary cause is unambiguously the v4 opening-framing rule:

- v4 says that 「共有画面を中心にしましょう」 at the opening is normally
  an Idea / Topic framing.
- E-u001 is the first utterance, so there is no previous utterance,
  Existing Proposal Node, or Topic Return evidence that could have repaired
  this classification.
- The Analyzer did understand the content: it created the right Topic, the
  right Idea, and the right initial Topic Focus. The missing piece is only the
  decision category.

Thus this is not a Context omission and not a multi-turn formation failure.
It is a deliberate conservative boundary in Prompt v4 that conflicts with
Golden v2's policy of treating explicit scope choices as Strong Candidates.

Golden v2 is not necessarily wrong: a product may decide that opening framing
should remain an Idea until a later confirmation. The frozen baseline,
however, explicitly chooses to measure this scope choice as a Strong
Candidate, so the miss remains real under analyzer-eval-v2.

## 4. Decision Formation Types

| Case | Classification | Reason |
| --- | --- | --- |
| B-u006 | Type A — Single-Utterance Explicit Decision; context improves confidence | The utterance itself names the policy and says 方針で進めましょう. Prior architecture context helps determine its scope, but a prior agreement is not required. |
| E-u001 | Type A — Single-Utterance Explicit Decision | The utterance explicitly selects the MVP center with 中心にしましょう; it is not an agreement-only closure. |

Neither target is Type D. No confirm_decision is justified by either case.
The semantic Analyzer may detect a Candidate Decision, but only a Human
Command may transition it to confirmed.

Type C and Type D remain important general cases for Japanese Discussion, but
they do not explain these two particular Run #4 misses. They should be tested
in a later Decision Formation experiment rather than used as a post-hoc
explanation for E-u001.

## 5. Context Builder findings

The current Real Analyzer Context contract is:

- Current Utterance;
- Meeting Goal;
- Current Topic ID and mode;
- bounded Relevant Node summaries;
- last eight structured Events;
- output safety contract.

The following are not included:

- Previous finalized utterance text;
- a recent raw-utterance window;
- explicit proposal / policy / decision-target roles;
- the evidence text for prior Nodes;
- a separate reference-resolution signal.

| Context component | B-u006 | E-u001 | Diagnostic conclusion |
| --- | --- | --- | --- |
| Current Utterance | Present | Present | Sufficient to see commitment language in both cases |
| Meeting Goal | Present | Present | Helpful, not decisive |
| Current Topic | Architecture Topic | null | Correct for each point in the session |
| Relevant Nodes | 7 active Nodes | Empty, correctly | B has structured context; E cannot use prior context |
| Recent Events | 8 structured Events | 2 system Events | B has history summaries; E is at session start |
| Previous raw utterance | Missing | Not applicable | General recall gap, not E-u001's cause |
| Proposal semantics | Not explicit | Not applicable | Could help B, but v4 still overrides it |
| Presentation State | Excluded | Excluded | Correct; no UI leakage |

The most important finding is that the system currently has an
utterance-boundary mismatch: Analysis is invoked per Current Utterance, while
some Decision meaning is formed across a short conversational window. This
matters for agreement and ellipsis cases, but it does not turn B-u006 or
E-u001 into multi-turn decisions.

## 6. Japanese ellipsis and reference resolution

Japanese Discussion frequently omits the subject or the selected object:

- 「それでいきましょう」
- 「今回はそれで」
- 「じゃあ外す方向で」
- 「この方向で進めましょう」

Current-Utterance-only analysis has a safety advantage: it will not invent a
target when the target is absent. It also has a recall limitation: an
agreement may close an existing proposal without repeating its label.

B-u006 is less elliptical than those examples. そこから refers to the
Materialize processing in the same sentence, and the commitment is explicit.
The missing raw previous window is therefore a secondary robustness issue,
not the primary cause of the miss.

E-u001 contains no material ellipsis. Its target and scope are explicit. The
failure is the opening-framing rule.

## 7. Event Context vs Utterance Context

| Approach | Recall potential | False Decision risk | Assessment |
| --- | --- | --- | --- |
| Recent Events only | Low–medium | Low | Good for current Graph state, weak for omitted Japanese references |
| Previous 1 utterance | Medium–high | Medium | Best first addition for short proposal → closure sequences |
| Previous 2 utterances | High | Medium | Useful for Type C, but increases context and anchoring risk |
| Relevant proposal Nodes | Medium | Low–medium | Helps reference resolution without sending the full Transcript |
| Both previous utterances and proposal Nodes | High | Medium | Recommended experiment, with strict decision safety rules |

The evidence does not support lowering the Decision threshold blindly. For
E-u001, more context cannot solve the miss. For B-u006, additional context may
help, but the primary rule still has to recognize explicit policy adoption.

## 8. Recall versus safety trade-off

| Improvement | Expected Recall | False Decision risk | Recommendation |
| --- | --- | --- | --- |
| Relax v4 Decision rule immediately | High | High | Do not do as an isolated change |
| Add previous finalized utterance | High for Type C/D | Medium | First Context experiment |
| Add relevant proposal / option references | Medium | Low–medium | Pair with previous utterance |
| Add a bounded multi-turn Decision layer | High | Medium | Recommended after Context ablation |
| Human-only Candidate creation | Low | Very low | Too conservative for the Analyzer goal |

The asymmetric product risk remains: a False Strong Decision is more harmful
than a missed Candidate. Any recall improvement must preserve:

- Automatic Confirmation = 0;
- Invented Owner = 0;
- Invented Due Date = 0;
- no Candidate Decision from agreement alone;
- no duplicate Candidate for the same proposal.

## 9. Recommended Strong Decision Context Contract

This is a proposal for the next experiment, not an implementation change.

Minimum Context:

    Current Utterance
    Previous 1 finalized Utterance
    Current Topic {id, label, status, mode}
    Relevant Proposal Nodes {id, type, label, status}
    Recent structured Events (bounded, last N)
    Meeting Goal

Recommended bounded extension:

- include a second previous utterance only when the current utterance has an
  anaphoric / elliptical marker (それ, この, その方向, そこ, 戻る) or the
  immediately previous utterance is an acknowledgement;
- retain only active, non-parked proposal-relevant Nodes;
- keep Presentation State out of the Context;
- do not pass the whole Transcript by default.

The Context should make it possible to identify an existing proposal, but it
must not tell the LLM that the proposal is already confirmed.

### Multi-turn window

Start with a fixed one-utterance lookback and an adaptive maximum of two
utterances. A 30-second window is not justified by this diagnostic and would
make Context growth and attribution harder to control.

## 10. Agreement handling and Candidate deduplication

The following distinction must remain explicit:

    Proposal / Option + Agreement evidence
        -> at most a Candidate Decision (semantic detection)

    Candidate Decision + Agreement evidence
        -X-> Confirmed Decision

The second transition is always a Human Command.

For MVP safety, an agreement-only Current Utterance should remain events: []
unless a later, dedicated multi-turn layer can prove all of the following:

1. a concrete proposal exists in the bounded Context;
2. the agreement is attached to that proposal;
3. the resulting Event is a Candidate Decision, never a Human Event; and
4. the Event carries evidence references for both the proposal and the
   agreement.

If such a layer emits a Candidate, it must first search for an existing
Candidate with the same semantic target and policy. It should reference the
existing Candidate rather than create a second Node. Exact label matching is
not sufficient; the identity key must use the existing proposal / target and
the normalized decision meaning.

## 11. Counterfactual offline analysis

No counterfactual Model Call was made. The stored data is sufficient to state
what additional information would have been available.

### B-u006

Current effective Context already had the Topic, seven Relevant Nodes, and the
last eight Events. A counterfactual Context that adds B-u005 and B-u004 raw text
would make the discussion sequence clearer:

    Previous 2: LLM failure/latency must not stop the meeting
    Previous 1: Graph-wide Context vs Current Topic neighborhood are options
    Current: make Materialization deterministic and keep LLM out of it
    Current Topic: architecture pipeline
    Relevant Nodes: existing Topic, prior Ideas, two Context options
    Recent Events: last eight structured Events

This would improve reference and formation analysis, but it does not remove
the v4 rule that classifies an architectural policy as an Idea unless an
explicit competing option is resolved. Therefore it is a useful robustness
experiment, not a sufficient explanation of the Run #4 miss.

### E-u001

There is no previous utterance or prior proposal to add. The only useful
counterfactual change would be a semantic instruction that distinguishes
“opening scope choice” from “opening framing.” That is a Prompt / product
policy change, not a Context fix. It is intentionally not made here.

## 12. Decision diagnostic set

The following small set prevents overfitting the diagnosis to B-u006 and
E-u001. It should be evaluated with the frozen analyzer-prompt-v4 in a future
controlled experiment; this document does not run the API.

| Utterance | Expected class | Formation type | Purpose |
| --- | --- | --- | --- |
| B-u006 | Strong Candidate | A | Architecture policy adoption; known target miss |
| E-u001 | Strong Candidate | A | Opening scope choice; known target miss |
| A-u005 | Strong Candidate | A | Concrete exclusion; known positive control |
| D-u006 | Strong Candidate | A | Explicit pricing choice; known positive control |
| E-u005 | Weak Signal / Option | B-like return context | Scope signal with よさそうです; must not become Strong |
| A-u003 | Weak Signal / Idea | B-like context | Preference and possibility; precision control |
| A-u006 | No new Decision | D-shaped agreement | Agreement must not confirm or invent a Decision |
| D-u005 | Option / Open Item | B | Question about comparison; not commitment |
| C-u008 | No-op | — | Filler / deferment control |

The two target cases are both Type A, while the diagnostic set still covers
the Type B/C/D risks that a future Context change may introduce.

## 13. Prompt change necessity

Prompt v5 was not created and is not needed to complete this diagnostic.

The evidence does show that a future semantic Prompt change will eventually
be needed if Golden v2 remains the product policy:

- E-u001 cannot be recovered by Context enrichment because it is the first
  utterance.
- B-u006 is explicitly called out by v4 as an Idea pattern even though
  Golden v2 treats policy adoption as Strong.

However, Prompt v5 should not be the first unmeasured change. First establish
the Context / formation experiment below, because it addresses the broader
Type C/D class and avoids attributing all recall failures to wording rules.

Golden v2 should remain frozen. The only open product-policy question is
whether an opening scope framing such as E-u001 should be shown as a Candidate
Decision immediately or as an Idea until a later human confirmation. Changing
that policy would change the evaluation target and must not be hidden as a
Prompt optimization.

## 14. Recommended next experiment

No implementation is requested in this spike. The next controlled experiment
should be:

1. Persist a redacted Context snapshot for each Analyzer call so the request
   is auditable without storing secrets.
2. Run an offline Context ablation design over the diagnostic set:
   - C0: current v4 Context;
   - C1: C0 + previous 1 finalized utterance;
   - C2: C1 + adaptive second utterance + explicit proposal Node summaries.
3. Keep Prompt v4, Model, Golden v2, and Materializer fixed during the
   Context comparison.
4. Measure Strong Decision Precision/Recall, Weak Signal Recall, False Strong
   Decision count, Candidate duplication, No-op Accuracy, and Context size.
5. Only after C0/C1/C2 results decide whether to create a future Prompt v5.

For E-u001, add a separate policy label to the report: “opening scope choice
under framing rule.” Do not use C1/C2 success on B-u006 to claim that E-u001's
policy boundary has been solved.

## 15. Final decision

### Primary diagnosis

**A — Prompt semantic rule is the direct cause for these two misses.**

The current v4 Prompt deliberately under-classifies both an explicit
architecture-policy adoption and an opening scope choice. B-u006 also reveals
a secondary Context observability / utterance-boundary limitation, but E-u001
rules out Context as the common root cause.

### Recommended architecture direction

**B + C as the next supporting direction:** add a bounded Previous-Utterance
Context and evaluate a small Multi-turn Decision Formation layer before
loosening the semantic threshold. This is for future experimentation only; it
does not alter the frozen baseline.

### Not selected

- **D — Golden reconsideration:** not selected now. Golden v2 is a coherent,
  explicitly frozen product policy, although the opening-framing boundary must
  remain visible.
- **E — Current baseline sufficient:** not selected. Strong Decision Recall
  0.50 is safe but not sufficient for the frozen Strong Candidate policy.

## Conclusion

- B-u006: Type A; missed primarily by v4's architecture-policy guard, with a
  secondary benefit available from previous-utterance / proposal Context.
- E-u001: Type A; missed primarily by v4's opening-framing guard; Context is
  not the cause.
- Previous utterances are needed for robust future Type C/D and Japanese
  ellipsis handling, but are not required to explain E-u001.
- A multi-turn layer is justified for general recall, but must never turn
  Agreement into Human Confirmation.
- Prompt v5 is not created in this task. The next measured experiment is
  Context C0/C1/C2, followed by a decision on a future semantic Prompt change.

