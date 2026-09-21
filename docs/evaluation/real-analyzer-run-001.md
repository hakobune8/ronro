# Real Analyzer Evaluation Run #1

Status: **Baseline completed at the provider-transport level; Analyzer quality baseline failed the Structured Output contract**

## Configuration

| Item | Value |
| --- | --- |
| Provider | OpenAI via the existing OpenAI-compatible HTTP Adapter |
| Model | `gpt-5.6-luna` |
| Reasoning effort | `medium` |
| Timeout | 60 seconds |
| Prompt | `analyzer-prompt-v1` |
| Dataset | Recorded Real Analyzer v1, 5 scenarios / 38 utterances |
| Canonical Contract | Unchanged |
| Materializer / Map | Unchanged |
| Run ID | `real-analyzer-run-001-gpt-5.6-luna-analyzer-prompt-v1-20260919` |

The API key was read from the runtime environment and is not present in this
repository's run artifacts. Authorization headers and secrets were not saved.

The Provider Adapter was minimally updated before this run to pass
`reasoning_effort=medium` for reasoning models and to omit the unsupported
temperature parameter. No Prompt, Dataset, Schema, Analyzer Contract,
Materializer, or Map behavior was changed during Run #1.

## Dataset

| Scenario | Utterances | Primary checks |
| --- | ---: | --- |
| A — MVP企画 | 8 | Candidate Decision, Action, No-op |
| B — Architecture | 7 | Event boundary, context, failure concerns |
| C — Brainstorming | 8 | Node granularity, proposals, false Action |
| D — 意見対立 | 8 | Option, Concern, Candidate Decision, agreement |
| E — Topic Return | 7 | Existing Topic reference, return, duplicate prevention |
| **Total** | **38** |  |

## Run-level Results

| Measure | Result |
| --- | ---: |
| Provider responses | 38 / 38 |
| Provider failures | 0 |
| Structurally valid Analyzer outputs | 6 / 38 |
| Schema-invalid Analyzer outputs | 32 / 38 |
| Valid no-op outputs | 6 |
| Canonical Candidate Events accepted | 0 |
| Final Graph nodes | 0 in every scenario |
| Automatic Confirmation | 0 |

The six valid outputs were `{"events":[]}` no-ops. The remaining 32 responses
were returned by the model but rejected before Candidate Event conversion.
Therefore the real model did not produce a usable Discussion Map in this run.

## Primary Metrics

The following values use a denominator-aware interpretation. `N/A` means the
model produced no predictions of that kind; it must not be treated as a score
of 1.0.

| Metric | Result | Interpretation |
| --- | ---: | --- |
| Topic Precision | N/A | No Topic node was accepted |
| Topic Recall | 0.0000 | No expected Topic was materialized |
| Important Node Recall | 0.0000 | No important node was materialized |
| Candidate Decision Precision | N/A | No Decision node was accepted |
| Action Precision | N/A | No Action node was accepted |
| Topic Return Accuracy | 0.0000 | The one expected return was not materialized |
| No-op Accuracy | 0.7500 (6/8) | Only validated `events: []` counts as a no-op |
| Duplicate Topic Rate | N/A | No Topic node was materialized |
| Node Explosion Rate | 0.0000* | No events were accepted; not a quality signal |
| Label Quality | N/A | No node label reached the Graph |

The existing evaluator reports some vacuous `1.0` values when the predicted
denominator is zero, and counts schema failures as no-op because the Graph did
not change. Those raw Harness values are preserved in `metrics.json`, but they
are not used as quality claims here. The corrected no-op result is 6/8.

## Critical Errors

### Canonical Event / Graph level

| Error | Count | Severity |
| --- | ---: | --- |
| False Decision accepted | 0 | Critical |
| False Action accepted | 0 | Critical |
| Invented Owner | 0 | Critical |
| Invented Due Date | 0 | Critical |
| Automatic Confirmation | 0 | Critical |
| Unsupported Content accepted | 0 | Major |
| Duplicate Topic accepted | 0 | Major |

These zeros mean that no invalid Candidate Event reached the Canonical Graph;
they do not mean that the raw model output was semantically correct. Because
32 outputs failed validation, raw-output semantic findings are reported as
contract failures rather than silently applied to the Graph.

### Raw-output findings

The model produced several semantically questionable intents inside invalid
responses, including a proposal described as a `decision`, a proposal
described as an `action`, and a Topic focus that used a new label instead of an
existing node reference. These are review findings, not applied Canonical
Events. They must be re-evaluated after the structured-output contract is made
unambiguous in a subsequent iteration.

## Scenario Results

| Scenario | Invalid | Valid no-op | Accepted Events | Final Map | Main finding |
| --- | ---: | ---: | ---: | --- | --- |
| A — MVP企画 | 7/8 | 1 | 0 | Empty | Raw output found Topic/Concern/Decision/Action intents, but used unsupported shapes and an unparseable relative due date |
| B — Architecture | 6/7 | 1 | 0 | Empty | Unsupported types such as `evidence`, `component`, `proposal`, and an unsupported relation label |
| C — Brainstorming | 7/8 | 1 | 0 | Empty | Several useful ideas were present semantically, but nested node objects and unsupported `proposal` values failed validation |
| D — 意見対立 | 6/8 | 2 | 0 | Empty | Option/Concern/Decision-like content was detected, but wrapping and relation shapes were invalid |
| E — Topic Return | 6/7 | 1 | 0 | Empty | The model attempted Price and MVP focus changes, but did not produce a valid existing-node reference |

## Fake vs Real

The Fake Analyzer baseline remains the previously recorded structural
baseline:

| Metric | Fake baseline | Real Run #1 |
| --- | ---: | ---: |
| Topic Precision | 0.9333 | N/A; no Topic prediction accepted |
| Topic Recall | 0.7000 | 0.0000 |
| Candidate Decision Precision | 1.0000 | N/A; no Decision prediction accepted |
| Action Precision | 0.8000 | N/A; no Action prediction accepted |
| Topic Return Accuracy | 1.0000 | 0.0000 |
| No-op Accuracy | 0.4000 | 0.7500 validated-only |

Fake is not treated as ground truth. Human Golden Annotation remains the
primary reference. The comparison shows that the current gap is first a
Structured Output contract/adherence problem; it is not yet a meaningful
comparison of Map quality.

## Latency, Tokens, and Cost

| Measure | Result |
| --- | ---: |
| Latency p50 | 2,139 ms |
| Latency p95 | 3,137 ms |
| Latency max | 3,605 ms |
| Input tokens | 20,023 |
| Output tokens | 6,566 |
| Reasoning tokens | 4,487 |
| Total tokens | 26,589 |
| Estimated cost | USD 0.01188380 |
| Context size | 805–931 characters, average 865.95 |

The run is within the broad future 3–10 second observation target at the
transport level, but latency is not yet a product-quality result because the
outputs were not usable. Node count and recent-event count were not persisted
by this Run Record and are therefore marked unavailable in `metrics.json`.

## Discussion Map Review

The existing Stable Discussion Map and Materializer were not changed. All five
real final graphs are empty because the Analyzer rejected every non-no-op
response. Consequently:

- the Map did not grow from the Recorded Transcript;
- Current Topic and Topic Return could not be observed in the Map;
- no visual comparison with the Fake final Map is meaningful yet;
- the empty result is correctly safer than applying invalid events.

The strongest positive result is the safety boundary: invalid LLM output did
not corrupt the Graph and agreement-like utterances did not create
`confirm_decision` events.

## Good Examples

- Agreement and acknowledgement utterances such as `それでいきましょう`,
  `了解です`, and `そうですね` returned valid `events: []` in six cases.
- No `confirm_decision`, `revoke_decision`, or other Human Command was emitted.
- Provider usage, reasoning-token usage, latency, raw output, and validation
  errors were captured without storing credentials.

## Failure Examples

The prompt/schema boundary was not followed consistently:

```json
{"events":[{"node_type":"concern","label":"スマホ側の追加対応が必要","source_evidence_ids":["real-a-003"]}]}
```

The provider-facing schema requires `kind: "node"` on this intent. Similar
failures used nested `{"node": {...}}`, `topic_focus` without a `kind`,
unsupported node types such as `proposal`, and unsupported relation names.

An Action output also used a relative value (`次回まで`) where the canonical
provider schema requires an ISO date. It was safely rejected rather than
silently normalized.

## Failure Classification

| Classification | Count | Assessment |
| --- | ---: | --- |
| Transport / Provider failure | 0 | New key and project configuration allowed all 38 calls to return |
| Structured Output contract mismatch | 32 | Primary failure; invalid shape, missing `kind`, unsupported types/relations, or invalid date format |
| Valid no-op | 6 | Positive safety signal, but 2 expected no-ops were malformed instead of valid no-ops |
| Materializer / Domain Model issue | 0 observed | Materializer was not changed and rejected invalid input correctly |
| Dataset / Golden issue | Not established | Do not change Dataset or Golden before fixing the output contract and rerunning |

## Recommended Next Step

**Decision: A — Prompt / Context Iteration.**

The Provider is usable and the latency/usage loop works, but `analyzer-prompt-v1`
does not reliably make the provider emit the already-defined intent schema.
The next change should be isolated to the Provider-facing prompt/adapter
conversion and tested against the same frozen Dataset and Golden Annotation.
Do not proceed to STT or Live Audio yet.

Before the next run, make the required intent envelope explicit with concrete
examples (`kind: "node"`, `kind: "relation"`, `kind: "topic_focus"`), keep
Canonical IDs/application fields outside the LLM, and preserve the existing
validation boundary. Then rerun the same 38 utterances under a new Run ID.

## Artifacts

The machine-readable Run #1 artifacts are under:

`evaluation/runs/real-analyzer-run-001-gpt-5.6-luna-analyzer-prompt-v1-20260919/`

They include `metadata.json`, `metrics.json`, per-utterance `raw/` and
`parsed/` records, per-scenario results, and final Graph snapshots. The
original unmodified evaluator output is retained as
`raw-evaluation-after-key-rotation.json`.
