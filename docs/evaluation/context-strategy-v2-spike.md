# Context Strategy v2 Spike

Status: Completed — Diagnostic Spike

This spike compared the frozen Context Strategy v1 with a minimal v2 that adds
exactly one previous finalized utterance. It did not change the Prompt, Model,
Golden Annotation, Canonical Schema, Materializer, or the existing five
scenario / 38 utterance baseline.

No STT, Live Audio, or Prompt v5 work was started.

## Frozen Baseline and Run

| Item | Value |
| --- | --- |
| Model | `gpt-5.6-luna` |
| Reasoning | `medium` |
| Prompt | `analyzer-prompt-v4` |
| Golden | `golden-v2` (not used as a source of truth for the separate spike cases) |
| Evaluation | `analyzer-eval-v2` baseline remains unchanged |
| Dataset | `context-strategy-spike-v1` |
| Cases | 13 |
| API calls | 26 (13 × v1, 13 × v2) |
| Run ID | `context-strategy-v2-gpt-5.6-luna-analyzer-prompt-v4-20260919` |

Raw outputs, parsed outputs, Context payloads, and canonical events are stored
under:

`evaluation/runs/context-strategy-v2-gpt-5.6-luna-analyzer-prompt-v4-20260919/`

The stored raw output contains no API key or authorization header.

## Dataset

The spike dataset is intentionally separate from `golden-v2`. It contains
small, targeted cases rather than a replacement evaluation corpus.

| Case | Focus | Expected behavior |
| --- | --- | --- |
| `ctx-001` | Pronoun / omitted scope | Resolve “今回はなし” to the existing smartphone option without inventing a Decision |
| `ctx-002` | Proposal + agreement | Evaluate whether “その案で進めましょう” can form a Candidate without confirmation |
| `ctx-003` | Topic Return | Return to the existing pricing Topic |
| `ctx-004` | Type C | Previous question + “今回は外しましょう” → Strong Candidate |
| `ctx-005` | Type C | Previous leaning + explicit “法人向けで進めましょう” → Strong Candidate |
| `ctx-006` | Type D | Proposal + “それでいきましょう” → Candidate may be formed, never Confirmed |
| `ctx-007` | Weak agreement | Do not create a Strong Decision from “そうですね” |
| `ctx-008` | Multi-turn Action | “私がPrototypeを作ります” → Action detection; Owner policy evaluated separately |
| `ctx-009` | No-op | “なるほど” → no events |
| `ctx-010` | Ambiguous reference | Do not choose between price and sales method without evidence |
| `ctx-011` | Type A control | Explicit Decision should work without a previous utterance |
| `ctx-012` | Relevant Node omission | Parked pricing Topic is not supplied as a Relevant Node |
| `ctx-013` | Mention without focus | Mentioning price must not move Current Topic away from MVP scope |

## Context Variants

### Context v1

The existing provider-facing Context:

- Current Utterance
- Meeting Goal
- Current Topic
- Relevant Nodes
- Recent Events

### Context v2

Context v1 plus one field:

```json
{
  "previous_utterance": {
    "id": "...",
    "sequence": 1,
    "speaker": "A",
    "text": "...",
    "evidence_ids": ["..."]
  }
}
```

When no previous finalized utterance exists, v2 sends
`"previous_utterance": null`. No new Canonical State was introduced. UI
Presentation State is not included in either variant.

## Structural Results

| Metric | v1 | v2 |
| --- | ---: | ---: |
| API success | 13/13 (100%) | 13/13 (100%) |
| Analyzer Output Schema valid | 13/13 (100%) | 13/13 (100%) |
| Canonical conversion / validation success | 13/13 (100%) | 13/13 (100%) |
| Automatic Confirmation | 0 | 0 |

The provider-facing and Canonical Event contracts remained unchanged.

## Primary Comparison

Reference accuracy uses a strict target-ID rule. The expected existing ID must
appear in the provider output. The denominator is seven evaluable reference
cases; `ctx-012` is reported separately because its expected target is parked
and intentionally absent from Relevant Nodes.

| Metric | v1 | v2 | Observation |
| --- | ---: | ---: | --- |
| Reference Resolution Accuracy | 2/7 (0.2857) | 1/7 (0.1429) | No improvement; v2 lost the `ctx-001` reference by returning no events |
| Existing Node Reference Accuracy | 2/7 (0.2857) | 1/7 (0.1429) | Same strict target-ID result |
| Relevant target available in Context | 7/7 evaluable | 7/7 evaluable | Previous utterance did not change Relevant Node selection |
| Type C Strong Decision Recall | 2/2 (1.0000) | 2/2 (1.0000) | Already solvable from Current Utterance |
| Type D Strong Decision Recall | 0/2 (0.0000) | 0/2 (0.0000) | Previous 1 did not overcome v4 agreement policy |
| Weak Agreement False Decision | 0/1 | 0/1 | Safety preserved |
| Topic Return Accuracy | 1/1 (1.0000) | 1/1 (1.0000) | Explicit “戻る” case was already solvable |
| Multi-turn Action Accuracy | 1/1 (1.0000) | 1/1 (1.0000) | Detection unchanged |
| No-op Accuracy | 2/2 (1.0000) | 2/2 (1.0000) | `ctx-007`, `ctx-009` remained clean |
| Ambiguous Reference Safety | 1/1 (1.0000) | 1/1 (1.0000) | Both returned the safe no-op |
| False Strong Decision count | 0 | 0 | No safety regression |
| Invented Owner | 0 | 0 | No fabricated Owner |
| Invented Due | 0 | 0 | No fabricated Due Date |

The exact per-case Context, parsed output, and Canonical events are retained in
the run directory. “Existing Node Reference Accuracy” is deliberately stricter
than semantic label agreement: a new Decision whose label names an existing
Option does not count as returning that Option's ID.

## Case Findings

### Pronoun / omitted object: `ctx-001`

The Relevant Nodes already contained `option-smartphone` in both variants.
With v1, the model returned an Idea plus an `opposes` relation to the existing
Option. With v2, it returned `events: []`.

The additional utterance therefore did not improve reference resolution. It
made the result safer with respect to avoiding a speculative Decision, but it
also removed a useful existing-Option reference. This is not evidence that
Previous 1 is generally harmful; it is evidence that adding the field alone
does not define how a weak scope statement should be represented.

### Topic Return: `ctx-003`

Both variants returned the existing `topic-price-3` and emitted the correct
`topic_focus_changed` event. v1 additionally created an Open Item for the
price detail; v2 returned only the focus change. This is a useful reduction in
event noise, but not a Recall improvement attributable to Previous 1: the
Current Utterance explicitly said “さっきの料金の話に戻ると”.

### Type C: `ctx-004`, `ctx-005`

Both variants detected both explicit Strong Candidates. The decisive language
was in the Current Utterance itself:

- “じゃあ今回は外しましょう。”
- “じゃあ法人向けで進めましょう。”

Previous 1 was not needed for these cases. Neither output explicitly returned
the prior Option ID; each produced a new Decision node, with v1 sometimes also
adding a `contains` relation. This is a strict Existing Node Reference miss,
not a failure to understand the selected subject.

### Type D: `ctx-002`, `ctx-006`

Both variants returned no events for:

- “その案で進めましょう。”
- “それでいきましょう。”

The frozen v4 Prompt explicitly treats agreement-only utterances as no-op and
does not form a Candidate from them. Previous 1 made the proposal available,
but no Context-only behavior connected that proposal to a new Candidate. If the
product later chooses to expose Proposal + Agreement as a Candidate, this
requires a narrow multi-turn rule or layer; merely adding Previous 1 is not
sufficient. In either case, a Human `confirm_decision` Event remains
forbidden.

### Multi-turn Action: `ctx-008`

Both variants detected an Action. The model returned Owner `"私"` because the
Current Utterance explicitly said “私がPrototypeを作ります”. This was not
counted as an invented Owner, but it is not a stable person identity. The
Canonical policy still needs a later decision on whether first-person Owner
language is retained as text, mapped through speaker identity, or stored as
null. No change is made in this spike.

### Ambiguous reference: `ctx-010`

Both variants returned no events for “それは後で考えましょう” when both
価格 and 販売方法 were possible antecedents. This is the desired safety-side
behavior: do not resolve an ambiguous reference to one Node merely because it
is available in the Context.

### Relevant Node omission: `ctx-012`

`topic-price-12` was parked and therefore absent from Relevant Nodes in both
variants. Previous 1 did not change that selection. v1 proposed a new pricing
Topic. v2 proposed a new pricing Topic, a Topic focus change, and a raw Action
for “次回に回します”; the Action was rejected by the existing application
safety boundary and did not enter Canonical Graph state.

This is the clearest evidence that Previous 1 is not a substitute for a
Relevant Node selection policy. It also produced one provider-side false
Action proposal in v2, although accepted false Actions remained zero.

### Mention without focus: `ctx-013`

v1 returned no events. v2 added an Open Item under the existing price Topic but
did not change Current Topic. This was not counted as focus pollution because
the Topic focus remained MVP scope and the Open Item was supported by the
utterance. It is nevertheless a qualitative reminder that Previous 1 can
increase semantic structuring even when no focus transition is desired.

## Context Pollution

The spike uses a conservative pollution definition for five safety-oriented
cases (`ctx-007`, `ctx-009`, `ctx-010`, `ctx-012`, `ctx-013`): wrong focus,
invalid reference, false Strong Decision, or provider-side false Action.

| Metric | v1 | v2 |
| --- | ---: | ---: |
| Polluted cases | 0/5 | 1/5 |
| Pollution rate | 0.0000 | 0.2000 |
| Accepted false Actions | 0 | 0 |

The v2 pollution case is `ctx-012`. Canonical conversion rejected the false
Action, so Graph safety was preserved, but the provider output itself became
less economical. `ctx-013` generated two accepted events without moving focus;
it is recorded as a qualitative economy concern rather than a strict safety
violation.

## Cost, Context Size, and Latency

| Metric | v1 | v2 | Change |
| --- | ---: | ---: | ---: |
| Average serialized Context | 811.23 chars | 931.62 chars | +14.8% |
| Average estimated Context tokens | 203.15 | 233.31 | +14.8% |
| Input tokens | 32,263 | 32,950 | +687 (+2.1%) |
| Output tokens | 2,012 | 2,412 | +400 (+19.9%) |
| Total tokens | 34,275 | 35,362 | +1,087 (+3.2%) |
| Estimated cost | $0.008867 | $0.009484 | +$0.000617 (+7.0%) |
| p50 latency | 1.883 s | 1.362 s | lower in this sample |
| p95 latency | 4.220 s | 4.215 s | effectively unchanged |
| max latency | 5.335 s | 4.512 s | lower in this sample |

The latency numbers are from two short sequential samples and should not be
interpreted as a performance improvement. The measurable cost effect is the
Context and output-token increase; the spike did not show a latency increase.

## Safety and Contract Findings

- No automatic Confirmation Event was generated.
- No invented Owner or Due Date was observed.
- No false Strong Decision was accepted.
- One provider-side false Action proposal occurred in v2 (`ctx-012`); the
  existing conversion guard rejected it, so no false Action entered Graph state.
- No Canonical Schema, Event Schema, Materializer, Decision lifecycle, or
  Human Confirmation boundary changed.
- Existing unit/regression suite: **54 tests, all green**.

## Context-only vs Dedicated Multi-turn Layer

| Approach | Finding in this spike |
| --- | --- |
| Context-only, v1 | Sufficient for explicit Type C decisions, explicit Topic Return, Action, no-op, and ambiguity safety in this dataset |
| Context-only, v2 | Did not improve Type D; reduced strict reference score and increased Context cost |
| Dedicated bounded Multi-turn layer | Justified only for the optional Proposal + Agreement → Candidate behavior; it must never produce Human Confirmation |

Previous 1 is useful information, but there is no evidence here that it should
be added globally to every Analyzer call. A dedicated layer, if adopted, should
be narrow and explicit:

```text
Proposal / Option Event
        +
Agreement Utterance
        -> Candidate Decision intent (optional)
        -> Human Confirmation remains a separate command
```

It should also deduplicate against an existing Candidate Decision and refuse
ambiguous antecedents. It should not add hidden Canonical State.

## Recommendation

### Decision: **B + D (限定的)**

1. **Keep Context v1 as the default global Context.** Previous 1 did not
   improve the target metrics, increased token/cost usage, reduced strict
   reference resolution from 2/7 to 1/7, and produced one provider-side false
   Action proposal in the parked-Topic case.
2. **A dedicated Multi-turn Decision layer is needed only if the product
   explicitly requires Type D Proposal + Agreement to surface as a Candidate.**
   Context v2 alone did not achieve this. This is a targeted future experiment,
   not a request to change the Canonical Contract now.
3. **Do not create Prompt v5 from this spike.** The current result does not
   isolate a Prompt-only improvement opportunity for the Context experiment.
   The previously identified Type A suppression issue remains a separate
   Prompt diagnostic.
4. **Investigate Relevant Node selection separately.** Parked Topics are not
   available to the Analyzer, so adding conversational context cannot resolve
   those references. Any change must preserve the rule that a parked Topic is
   not automatically restored as Current Topic.

## Next Step

Before STT or Live Audio, the next focused experiment should be one of:

- a no-API offline design/test for a bounded Proposal + Agreement detector and
  Candidate deduplication; or
- a small Context-selection experiment for parked / recently referenced Topics,
  without changing the Canonical Graph or Current Topic policy.

The five-scenario baseline remains frozen at `gpt-5.6-luna` + `medium` +
`analyzer-prompt-v4` + `golden-v2` + `analyzer-eval-v2`.

