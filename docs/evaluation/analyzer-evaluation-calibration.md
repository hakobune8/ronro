# Analyzer Evaluation Calibration

Status: Proposed calibration

Date: 2026-09-19

## Scope and decision

This calibration uses only the already stored results from Real Analyzer Runs
#2, #3, and #4. No LLM API was called and no historical raw result was
rewritten.

The main conclusion is:

- Run #4 is the better product baseline for the shared Discussion Map.
- The existing `node_explosion_rate` is not a valid product-level Node
  Explosion metric. It is an Event Burst metric with a misleading name.
- E-u005 should not be a **Strong Candidate Decision** under a conservative
  Decision policy. It is better treated as a weak scope signal or an Option
  until a human confirms it.
- The next step is **B. Evaluation Calibration First**, not Prompt v5.

Historical Run #2/#3/#4 artifacts remain authoritative for their original
metric definitions. The recommendations below define a versioned calibration
for subsequent offline rescoring and future runs.

## Existing Metric Audit

### Current Node Explosion definition

The current implementation is in `prototype/real_evaluation.py`:

```text
event_count(u) = number of Canonical Events emitted for utterance u
explosion(u) = event_count(u) > 3
scenario_node_explosion_rate
  = count(explosion(u)) / utterance_count_in_scenario
run_node_explosion_rate
  = arithmetic mean of the five scenario rates
```

`event_count` includes all Event types, not only Node creation:

- `node_detected`
- `relation_detected`
- `topic_focus_changed`

Therefore a single new Node accompanied by a Relation and a Focus change is
counted as three Events, while Relations and Focus changes can also push an
utterance over the threshold. The threshold is `> 3` total Events per
utterance. The denominator is the number of utterances in each scenario; the
run-level result is the unweighted mean of the five scenario rates.

This metric is retained as a historical compatibility metric, but its
recommended name is:

> Legacy Event Burst Rate (`event_count > 3`)

It should not be interpreted as the number of excessive Nodes.

### Offline recalculation

The following table was recalculated from the stored per-utterance results.
The `historical` column is the value already recorded by the existing harness.
The `weighted` column uses all 38 utterances as one denominator and is included
only to make the aggregation choice explicit.

| Run | Prompt | Burst utterances | Total utterances | Weighted rate | Historical macro-scenario rate |
| --- | --- | ---: | ---: | ---: | ---: |
| #2 | v2 | 3 | 38 | 0.0789 | 0.0821 |
| #3 | v3 | 7 | 38 | 0.1842 | 0.1893 |
| #4 | v4 | 6 | 38 | 0.1579 | 0.1643 |

The difference between the two rates is not a defect in the historical run;
it is an aggregation choice. The more important problem is the numerator:
it counts non-Node Events as if they were Nodes.

### Why Run #4 demonstrates the mismatch

Run #4 has all of the following stored Node Economy results:

- accepted new Nodes per utterance: `0.9474`;
- maximum accepted new Nodes from one utterance: `2`;
- utterances generating three or more accepted new Nodes: `0 / 38`;
- proposed duplicate Node rate: `0.0000`;
- accepted duplicate Node rate: `0.0000`.

Nevertheless, the legacy Event Burst Rate is `0.1643`, because six utterances
cross the total-Event threshold. This is exactly the situation in which the
metric says “explosion” while the Map review says “the Map became less dense
and easier to scan.”

The legacy metric is useful for detecting an Analyzer response that emits an
unusually large Event bundle, but it is not sufficient to judge Discussion Map
quality.

## Node Explosion Analysis

### Product meaning

For this product, Node Explosion is not merely “many Nodes from one
utterance.” It is the accumulation of low-value, redundant, overly granular,
or poorly grouped Nodes that makes the shared Map harder to understand.

The product-level failure is therefore:

> The Map gains more visible semantic objects than participants can usefully
> understand during the Discussion.

This definition has at least four causes:

1. Too many new Nodes in one utterance.
2. Redundant Nodes expressing the same idea or Topic.
3. Nodes that are technically faithful but have little Map value.
4. Excessive cross-Relations that make the structure look denser than the
   underlying Discussion.

The first cause can be measured deterministically. The other causes require
semantic checks or human review and must not be hidden under one numeric
metric.

### Candidate metric comparison

| Metric | What it detects | Determinism | Product relevance | Recommendation |
| --- | --- | --- | --- | --- |
| Nodes per Utterance | Average Node creation volume | High | Medium | Keep as descriptive economy metric |
| Max Nodes per Utterance | Worst single-utterance burst | High | High | Keep as regression guard |
| 3+ Node Utterance Rate | Structural over-generation | High | High | Adopt as primary automatic burst guard |
| Low-value Node Rate | Nodes that do not improve Map understanding | Low without review | Very high | Add through rubric review |
| Redundant Node Rate | Duplicate or near-duplicate meaning | Medium | Very high | Add; separate from Topic duplicates |
| Nodes per Topic | Local Map density | High after attachment rules | High | Add per scenario and Topic |
| Final Map Node Count | End-state scale | High | Medium/High | Add as scalability signal, not alone |
| Human-rated Map Density | Whether information is usable in context | Review-based | Highest | Use as product-level metric |

### Recommended Node Economy set

The following should be reported together:

1. `accepted_new_nodes_per_utterance_average`
2. `max_accepted_new_nodes_from_one_utterance`
3. `utterances_generating_3_plus_new_nodes / utterance_count`
4. `proposed_duplicate_node_rate`
5. `accepted_duplicate_node_rate`
6. `redundant_node_rate`, after semantic review or a versioned equivalence
   rule
7. `low_value_node_rate`, from the human Map Quality rubric
8. `final_active_node_count` per scenario
9. `nodes_per_topic` per scenario
10. `relations_per_utterance` and `related_to` usage

`node_explosion_rate` must not be deleted because it is part of the historical
Run #2/#3/#4 reports. It should be labelled `legacy_event_burst_rate` in any
new report and must not be used as the sole release gate.

## Map Density: Run #3 vs Run #4

For this table, `child nodes` means active non-Topic Nodes attached to a Topic
through `contains` or `has_option`. Decision counts include Candidate
Decisions because no automatic confirmation occurred in these Runs.

| Scenario | Topics #3→#4 | Child Nodes #3→#4 | Decisions #3→#4 | Open Items #3→#4 | Actions #3→#4 | Relations #3→#4 | Nodes/Topic #3→#4 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A — MVP企画 | 1→1 | 8→6 | 1→1 | 1→0 | 1→1 | 8→6 | 8.0→6.0 |
| B — Architecture | 1→1 | 10→7 | 1→0 | 0→0 | 0→0 | 10→7 | 10.0→7.0 |
| C — Brainstorming | 1→1 | 6→6 | 0→0 | 0→0 | 0→0 | 6→6 | 6.0→6.0 |
| D — 意見対立 | 1→1 | 6→6 | 1→1 | 1→1 | 0→0 | 9→6 | 6.0→6.0 |
| E — Topic Return | 2→2 | 6→5 | 1→0 | 2→1 | 0→0 | 6→5 | 3.0→2.5 |
| **Total** | **6→6** | **36→30** | **4→2** | **4→2** | **1→1** | **39→30** | **6.0→5.0** |

The reduction is concentrated in the previously dense Architecture scenario,
while Brainstorming and Disagreement retain their useful structure. The lower
Decision and Open Item counts are not automatically improvements; they need to
be read together with Decision Safety and Important Node Recall. In the shared
display context, the reduction in cross-Relations and redundant structure is a
clear improvement.

## Decision Golden Policy

### Recommended policy

The Golden Annotation should distinguish two semantic classes without changing
the historical annotation files in place.

#### Strong Candidate Decision

A Strong Candidate requires:

1. A concrete choice, scope boundary, adoption, rejection, or policy target.
2. Explicit commitment or selection language, such as:
   `〜で進める`, `〜にする`, `〜を採用する`, `〜から外す`, or an equally
   assertive statement.
3. The utterance is stronger than a preference, possibility, comparison, or
   agreement.

Examples:

- 「スマホUIはMVPから外しましょう」
- 「法人向けで進めることにしましょう」
- 「この方式を採用する方向で進めます」

#### Weak Candidate / Directional Signal

A Weak Candidate may contain a useful direction but lacks enough commitment
for the Map to present it as a Decision Candidate by default.

Examples:

- 「Aの方がいいと思います」
- 「Aでもいいかもしれません」
- 「Aが良さそうですね」
- 「対象外でよさそうです」

Weak Candidates are useful for annotation and later analysis, but the MVP Map
should prefer an Idea, Option, or Open Item representation until a human
confirms the direction.

Agreement alone is neither a Strong nor a Weak new Decision:

- 「そうですね」
- 「賛成です」
- 「了解です」
- 「それでいきましょう」 when the current utterance does not restate a
  concrete proposal

These utterances must never create `confirm_decision` events. Human
Confirmation remains an explicit Human Command.

### Conservative asymmetry

The cost of a False Decision is higher than the cost of a Missed Candidate:

- A False Decision can give the room a misleading impression that the group
  has already committed.
- A Missed Candidate can still be surfaced by a participant or confirmed via
  Human Correction.

Therefore the evaluation should weight Strong Decision precision and False
Strong Decision count more heavily than Weak Candidate recall. The current
`candidate_decision_precision` should remain as a historical metric, but it
should not be the only Decision gate.

### Recommended Decision metrics

| Metric | Role |
| --- | --- |
| Strong Decision Precision | Primary safety metric |
| Strong Decision Recall | Measures important explicit commitments that were found |
| False Strong Decision Count | Critical/Major error count |
| Weak Candidate Recall | Secondary coverage signal |
| Confirmable Candidate Recall | Candidates that a human could reasonably confirm |
| Automatic Confirmation Count | Hard safety metric; must remain zero |
| Legacy Candidate Decision Precision | Historical comparability only |

This allows Run #4's conservative behavior to be recognized as safer even if
its legacy Decision Recall is lower.

## E-u005 Review

### Source and context

Original utterance:

> 「さっきのMVP範囲の話に戻ると、スマホUIは対象外でよさそうです。」

The utterance explicitly returns to the existing `MVP範囲` Topic. The relevant
context is that the session had moved to `価格モデル`, had deliberately left
its details unresolved, and then returned to the MVP scope. It also contains a
scope proposal about excluding Smartphone UI.

The current Golden Annotation labels it as:

```json
{"label":"スマホUIはMVP対象外","aliases":["スマホUIは対象外"]}
```

### Run-by-Run classification

| Run | Classification | Topic Return | Assessment |
| --- | --- | --- | --- |
| #2 / v2 | `decision`: 「スマホUIはMVP対象外」 | Correct | Too strong for a conservative Strong Decision policy; it treated the scope content as committed |
| #3 / v3 | `option`: 「スマホUIをMVP対象外とする」 | Correct | Safer classification, but the frozen Golden counted it as a missed Decision |
| #4 / v4 | `option`: 「スマホUIを対象外とする」 | Correct | Same safe semantic choice, with correct `has_option` and Topic Return |

### Calibration judgement

The phrase `対象外` supplies a concrete scope choice, but `よさそうです`
softens it into a tentative judgement. There is no explicit commitment such as
`対象外にしましょう`, `対象外にします`, or `MVPから外して進めます`.

Accordingly:

- Strong Candidate Decision: **No**.
- Weak Candidate / directional scope signal: **Yes**.
- Run #4 Option representation: **Product-appropriate** for the default Map.
- Topic Return: **Correct and independently important**.

The historical Golden should not be edited merely to make Run #4 score better.
Instead, create a versioned calibration annotation in a later offline
rescore, marking E-u005 as Weak Candidate. This preserves historical
comparability and makes the policy explicit.

## Label Evaluation

### Current limitation

The current `label_quality` implementation is a length check for non-Topic
labels: labels between 5 and 40 characters receive credit. It does not test
whether a label is faithful, concise, understandable, or redundant. A long
sentence can therefore pass, while a short but misleading label can also pass.

The Run #4 label quality value of `0.8295` is consequently a weak proxy, not a
semantic quality score.

### Recommended rubric

Evaluate a sample or all Nodes with five 1–5 dimensions:

| Dimension | 1 | 5 |
| --- | --- | --- |
| Faithful | Changes polarity, scope, or commitment | Preserves the meaning and strength of the evidence |
| Concise | Near-verbatim or unnecessarily long | Short phrase suitable for a shared Map |
| Understandable | Requires reopening the transcript | Understandable out of context |
| Non-redundant | Repeats a parent or sibling | Adds a distinct useful contribution |
| Type fit | Label conflicts with Node type | Label clearly fits Topic/Idea/Option/etc. |

The aggregate can be reported as a mean score, but Faithfulness and Type fit
should also have binary safety flags. A label that changes a preference into a
Decision must fail even if it is concise.

### Golden annotation philosophy

Golden data should represent an allowed semantic range, not one exact string.
For example, `価格体系` and `料金モデル` can be equivalent Topic labels when
they preserve the same Discussion axis. Alias lists are a useful beginning,
but future annotations should also record:

- expected Node type;
- semantic intent;
- polarity/scope where relevant;
- whether the item is Strong or Weak;
- allowed equivalent labels or reviewer notes.

Exact string matching remains useful for deterministic IDs and safety checks,
but not for ordinary Japanese label wording.

## Exact vs Semantic Evaluation

### Exact or deterministic checks

- Event type and allowed vocabulary.
- `confirm_decision` never emitted by the Analyzer.
- Decision status transition safety.
- Action safety and explicit Owner/Due evidence.
- Existing Node ID for Topic Return.
- No duplicate Canonical Node when returning to a Topic.
- Relation type and Relation Matrix validity.
- Evidence references.

### Semantic checks

- Topic naming and label wording.
- Summary wording.
- Whether two labels express the same idea.
- Whether a Node is useful enough to remain visible.
- Whether a Topic groups its children coherently.

This separation prevents a harmless wording difference from looking like a
domain failure, while keeping Decision and Action safety exact.

## Human Map Quality Rubric

The following is a provisional reviewer rubric for each final Scenario Map.
It is not a substitute for a participant study. Each dimension is scored
from 1 to 5.

| Dimension | Review question |
| --- | --- |
| Clarity | Can a participant quickly tell what was discussed? |
| Density | Is the amount of visible information appropriate for a shared display? |
| Stability | Can the structure be followed as the Map grows? |
| Decision Safety | Are tentative items prevented from looking decided? |
| Topic Coherence | Are child Nodes grouped under the right Topic? |
| Usefulness | Would participants actually want this Map visible during the meeting? |

Suggested review procedure:

1. Score the final Map without looking at the Analyzer output first.
2. Check the Map against the transcript and record omissions or inventions.
3. Record one sentence explaining any score of 1 or 2.
4. Keep the reviewer score separate from the automatic metrics.

## Run #4 Product Review

The following scores are a provisional artifact review of the stored Run #4
Graphs, not participant ratings.

| Scenario | Clarity | Density | Stability | Decision Safety | Topic Coherence | Usefulness | Mean |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A — MVP企画 | 4 | 4 | 4 | 5 | 3 | 4 | 4.0 |
| B — Architecture | 4 | 4 | 4 | 5 | 4 | 4 | 4.2 |
| C — Brainstorming | 4 | 4 | 4 | 5 | 5 | 4 | 4.3 |
| D — 意見対立 | 5 | 5 | 4 | 5 | 5 | 5 | 4.8 |
| E — Topic Return | 4 | 5 | 5 | 5 | 5 | 4 | 4.7 |
| **Overall provisional mean** |  |  |  |  |  |  | **4.4** |

Observations:

- D is the strongest Map: options, concerns, open item, and Candidate
  Decision form a coherent structure without excessive cross-Relations.
- E demonstrates the most important identity behavior: the existing Topic is
  revisited without a duplicate Topic, and the Flow returns to `MVP範囲`.
- B is materially better than Run #3 because the architecture Map has fewer
  Nodes and no spurious Candidate Decision.
- A remains useful but its Topic label is sentence-like, reducing Topic
  Coherence.
- C retains its useful option structure without additional density.

These scores support Run #4 as a good product baseline, while also showing
that label quality and Strong/Weak Decision annotation remain evaluation work,
not evidence that Prompt v5 is immediately required.

## Run #3 vs Run #4: Product comparison

| Scenario | Shared-display choice | Reason |
| --- | --- | --- |
| A — MVP企画 | Run #4 | 7 vs 9 Nodes, fewer Relations, and a usable Decision/Action spine; sentence-like Topic label remains a minor issue |
| B — Architecture | Run #4 clearly | 8 vs 11 Nodes, 7 vs 10 Relations, and the false Candidate Decision is removed |
| C — Brainstorming | Run #4 | Same Node count, but Topic Focus is clearer and the structure is not denser |
| D — 意見対立 | Run #4, narrowly | Same child density, fewer Relations, and the useful Decision/Concern/Open Item structure remains |
| E — Topic Return | Run #4 | 7 vs 8 Nodes, correct Topic Return, no duplicate, and the tentative scope statement is not overstated as a Decision |

For a meeting-room display, Run #4 is preferable in all five Scenarios. The
trade-off is intentional: it sacrifices a weak Decision recall signal in E in
exchange for a safer and less misleading Map.

## Evaluation Changes Recommended

### Keep for historical compatibility

- Existing Topic Precision / Recall.
- Existing Candidate Decision Precision.
- Existing Action Precision.
- Topic Return Accuracy.
- No-op Accuracy.
- Existing `node_explosion_rate`, renamed in new reports to Legacy Event Burst
  Rate.

### Add for calibrated reports

- Strong Decision Precision and Recall.
- False Strong Decision Count.
- Weak Candidate Recall.
- Accepted New Nodes per Utterance.
- Maximum New Nodes per Utterance.
- 3+ New Node Utterance Rate.
- Proposed and Accepted Redundant Node Rate.
- Final Active Nodes and Nodes per Topic.
- Relations per Utterance and `related_to` usage.
- Human Map Quality Rubric score.
- Label rubric score, replacing length-only `label_quality` as the product
  measure while retaining the old value for comparison.

### Offline recalibration policy

Do not alter the existing Run #2/#3/#4 raw outputs or their original reports.
The next evaluation maintenance step should:

1. Create a versioned annotation, for example
   `evaluation-calibration-v1`, with Strong/Weak Decision labels.
2. Add an offline rescorer that reads existing raw/final artifacts.
3. Recalculate Run #2/#3/#4 under the calibrated definitions.
4. Publish both the historical and calibrated views.
5. Use the calibrated result to decide whether a new semantic Prompt is
   justified.

This keeps evaluation changes separate from model or Prompt changes.

## Prompt v5 Necessity

Decision: **B. Evaluation Calibration First**.

Prompt v5 should not be created yet. The evidence for this decision is:

- Run #4 already improved Decision Precision from `0.4000` to `0.8000` while
  preserving Topic Recall at `0.7000`.
- Action Precision, Topic Return, and safety counts remain strong.
- Proposed and accepted duplicate rates are zero.
- No utterance created three or more accepted new Nodes.
- The Map is less dense than Run #3 in four of five Scenarios and no worse in
  the remaining Brainstorming Scenario.
- The apparent Node Explosion failure is primarily a metric-definition
  mismatch.
- E-u005 is primarily a Golden-policy ambiguity: the current Golden treats a
  tentative scope statement as a Strong Decision, while Run #4's Option is
  safer for the product.
- The current label metric is a length proxy rather than a semantic label
  evaluation.

After offline calibration, a new Prompt is justified only if a clearly
defined Strong Decision, Topic, or label failure remains in the product-level
review. The calibration must not be used to hide a real semantic failure; it
must make the product priority explicit.

## Next recommended step

1. Freeze the policy in this document as `evaluation-calibration-v1`.
2. Add versioned Strong/Weak fields to a new annotation view without editing
   the historical annotation in place.
3. Implement an offline rescore over the stored Run #2/#3/#4 artifacts.
4. Review the calibrated Run #4 Map with at least two reviewers using the
   six-dimension rubric.
5. Decide between Prompt iteration and Model/Context investigation only after
   that rescore.

No STT, Live Audio, Prompt v5, or new LLM evaluation was started as part of
this calibration.
