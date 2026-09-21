# Type D Multi-turn Decision Spike

This is a separate, offline evaluation dataset for the optional
Proposal + Agreement behavior. It does not modify `golden-v2`, the frozen
five-scenario Recorded Analyzer dataset, or the Canonical Event Schema.

The Normal Analyzer baseline is the frozen `analyzer-prompt-v4` behavior:
agreement-only utterances return no Analyzer Events. The candidate layer is an
opt-in deterministic step that consumes the current Canonical Graph, recent
semantic Events, and the current agreement utterance.

The dataset intentionally contains more negative than positive cases:

- strong Proposal + strong Agreement;
- weak Proposal + strong Agreement;
- strong Proposal + weak Agreement;
- multiple proposals;
- existing Candidate Decision;
- Topic change;
- no Proposal;
- same-speaker substantive utterance; and
- ambiguity.

Run without an API call:

```bash
uv run --with 'jsonschema>=4.23,<5' python3 -m prototype.type_d_spike
```

The output is written to
`evaluation/runs/type-d-multiturn-spike-v1/`. All emitted Decisions are
`node_detected` events whose materialized status is `candidate`; the layer
never emits `confirm_decision`.

