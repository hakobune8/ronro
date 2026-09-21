# Recorded Analyzer Readiness Repair

Date: 2026-09-19

This document records the minimal repair for the two blockers identified by
the Long-session Map Compaction Spike. It uses the frozen Recorded Analyzer
baseline:

- Model: `gpt-5.6-luna`
- Reasoning: `medium`
- Prompt: `analyzer-prompt-v4`
- Golden: `golden-v2`
- Evaluation: `analyzer-eval-v2`
- Type D: `OFF`

No LLM API was called. Run #4 raw output, parsed output, metrics, and final
graphs were not modified. The artifacts in
`evaluation/30min/compaction-spike-v1/` are derived simulations.

## Part A — Open Item Lifecycle

The existing Node `status` field is reused; no second Open Item status field
was added.

```text
active (open) --resolve_open_item--> resolved
resolved      --reopen_open_item--> active
```

Both transitions are Human Events. The Event payload contains the target Node
and `expected_status`, so stale or repeated transitions are rejected by the
Materializer. Analyzer output cannot directly resolve or reopen an Open Item.
The UI uses the existing Human Command boundary:

```text
Resolve/Reopen command
  -> Human Event
  -> Event Store validation
  -> Graph Materializer
  -> Presentation Projection
```

Resolved Open Items remain in the canonical Graph, Evidence links, and Event
history. They leave the normal visible-card budget but remain available from a
history/detail surface. Reopening makes the item visible again. Resolving an
item does not change Current Topic.

The new `013-open-item-lifecycle` fixture covers:

```text
create -> resolve -> reopen -> resolve
```

including revision snapshots and invalid-transition coverage.

## Part B — Action Relation Reference Resolution

The provider-facing Analyzer Output already had the required local reference
representation:

- `existing_node_id`: an ID shown in the Analyzer context;
- `new_node_index`: a zero-based reference to a Node intent in the same
  response.

No `local_ref` field was added to the Canonical Event or Domain Schema. The
adapter resolves same-output references in two passes:

1. allocate deterministic Canonical IDs for valid new Node intents;
2. resolve `existing_node_id` / `new_node_index`, validate the Relation Matrix,
   and emit Canonical Relation Events.

An unknown reference or invalid relation is rejected before Canonical Event
conversion. A valid Node is retained when only its Relation is invalid; the
Relation is skipped with a diagnostic. This prevents a bad Relation from
discarding an otherwise valid Action.

### Failure trace

| Utterance | Cached output | Run #4 failure | Repair result |
| --- | --- | --- | --- |
| `rec30-u058` 「その判断はまずPrototypeで見てみましょう。」 | Action + `topic -> new_node_index=0` | Explicit execution gate rejects a suggestion; the dependent Relation becomes unresolved | Correctly remains non-Action; no Node is invented |
| `rec30-u077` 「次回までにEvent Catalogの不足がないか整理します。」 | Action + `contains` | `整理します` was missing from the adapter’s explicit-action markers; Relation failed secondarily | Action Node and `contains` Relation accepted |
| `rec30-u087` 「候補の比較表を次回までに整理します。」 | Action + `contains` | Same adapter gate omission | Action Node and `contains` Relation accepted |
| `rec30-u119` 「田中さん、2026-09-26までにEvaluation結果を確認してください。」 | Action with explicit Owner/Due + `contains` | `確認してください` was missing from the adapter’s explicit-action markers | Action Node, Relation, Owner, and Due accepted |

The primary fault was the deterministic Action classification gate, not a
failure to understand `new_node_index`. Once a valid Action Node is allocated,
the existing two-pass resolver resolves the Relation deterministically.

## Offline re-score

### Open Item lifecycle simulation

Two Human `resolve_open_item` Events were appended to a derived copy of the
30-minute final state, for the two items classified as “resolved but State not
updated” (`rec30-u035` and `rec30-u118`).

| Measure | Before | After |
| --- | ---: | ---: |
| Canonical revision | 193 | 195 |
| Open Items in projection | 13 | 11 |
| Visible cards | 17 | 16 |
| Map quality | 4.8 | 4.8 |
| Critical Information Recall | 1.0 | 1.0 |

The two Resolve Events are Human Events in the derived stream. Duplicate or
similar Open Items were not merged or silently removed.

### Cached Action reconversion

The four saved Structured Outputs were reconverted without an API call:

- 3 explicit Actions recovered as 3 Action Nodes plus 3 `contains` Relations;
- the suggestion at `rec30-u058` remained rejected;
- the explicit Owner `田中さん` and Due Date `2026-09-26` were preserved from
  Evidence;
- no Canonical Graph Event from the historical Run was overwritten.

The combined derived projection (two Resolves plus the three recovered
Actions) is:

| Measure | Derived result |
| --- | ---: |
| Canonical Nodes | 93 |
| Actions | 8 |
| Open Items | 11 |
| Visible cards | 19 |
| Map quality | 4.6 |
| Critical Information Recall | 1.0 |

The combined result is a tail-append simulation for evaluation only; it is not
a chronological rewrite of Run #4.

## Contract changes

The changes are limited to the two blockers:

- Event Schema: `resolve_open_item` and `reopen_open_item` Human Events with
  `expected_status`.
- Materializer and Human Command Handler: deterministic state transitions and
  invalid-transition rejection.
- Presentation Projection: resolved Open Items are outside the normal visible
  card budget.
- Analyzer adapter: explicit Action markers now include `整理します` and
  `確認してください`.
- Event Catalog, Architecture Summary, Implementation Plan, Fixture index,
  and Fixture 013 document the contracts.

The Domain Schema, Canonical ID policy, Event ordering, Materializer contract,
Prompt v4, and Golden Annotation were not otherwise changed. Provider-local
`new_node_index` does not leak into Canonical Events.

## Verification

The targeted lifecycle, projection, and reference-resolution tests pass. The
full suite is green (`74` tests). The derived checks show structural
validation remains 100%, the suggestion is not promoted to an Action,
explicit Actions are not lost to Relation conversion, Owner/Due remain
evidence-backed, Critical Information Recall remains 1.0, and the derived
repair replay is deterministic (`derived_replay_deterministic=true`).
