# Real Analyzer Evaluation Run #4

Status: **Completed**

Run #4 kept the Run #3 Topic detection policy and changed only semantic prompt
guidance for conservative Decisions, Node Economy, Relation Economy, and
Topic Focus. The Model, Reasoning Effort, Native Structured Output,
Analyzer Output Schema, Canonical Schemas, Materializer, Dataset, Context
Strategy, Golden Annotation, and Stable Discussion Map were frozen.

## Configuration

| Item | Value |
| --- | --- |
| Provider | OpenAI via the existing OpenAI-compatible HTTP Adapter |
| Model | `gpt-5.6-luna` |
| Reasoning | `medium` |
| Prompt | `analyzer-prompt-v4` |
| Provider-facing schema | `schemas/analyzer-output-v2.schema.json` |
| Dataset | Same 5 Scenarios / 38 Utterances |
| Context strategy | Unchanged |
| Canonical Contract | Unchanged |
| Run ID | `real-analyzer-run-004-gpt-5.6-luna-analyzer-prompt-v4-20260919` |

## Prompt v4 Changes

- Kept implicit Topic detection and Existing Topic First from v3.
- Required a conservative three-part Decision test: concrete subject,
  commitment language, and stronger-than-preference evidence.
- Treated opening framing, general architecture principles, and agreement as
  non-Decisions unless a concrete alternative is selected.
- Added a strong default of 0–2 new Nodes per Utterance.
- Added a strong default of 0–2 new Relations per Utterance.
- Preferred `contains` / `has_option` and discouraged `related_to` fallback
  usage.
- Required `topic_focus` when a newly created Topic is the active subject of
  the same Utterance.
- Preserved the Run #3 Action and No-op policies without adding new Action
  examples.

The v4 prompt did not change any Schema, Materializer, Context Builder, or
Golden Annotation.

## Preflight

Five Run #3 problem cases were checked before the main run:

- false Decision in Architecture;
- false Decision in the opening Topic Return scenario;
- Node/Relation-heavy Architecture utterance;
- Relation-heavy disagreement utterance;
- New Topic creation without a focus transition.

| Check | Result |
| --- | ---: |
| Cases | 5 / 5 |
| API success | 5 / 5 |
| JSON parse | 5 / 5 |
| Analyzer Output Schema valid | 5 / 5 |
| Canonical conversion | 5 / 5 |
| Canonical Event Schema valid | 5 / 5 |

The preflight output is stored in the Run #4 directory.

## Structural Validity

| Metric | Result |
| --- | ---: |
| API success | 38 / 38 |
| Analyzer Output valid | 38 / 38 (100%) |
| Canonical conversion | 38 / 38 (100%) |
| Canonical Event Schema valid | 73 / 73 (100%) |
| Schema validation failures | 0 |
| Raw intents | 75 |
| Accepted Candidate Events | 73 |

The two rejected intents were handled by the existing application safety
guards. No Canonical Contract regression occurred.

## Semantic Metrics

| Metric | Run #3 | Run #4 | Target |
| --- | ---: | ---: | ---: |
| Topic Precision | 0.8000 | 0.8000 | >= 0.80 |
| Topic Recall | 0.7000 | 0.7000 | >= 0.65 |
| Important Node Recall | 0.4000 | 0.4333 | — |
| Candidate Decision Precision | 0.4000 | 0.8000 | >= 0.75 |
| Action Precision | 1.0000 | 1.0000 | >= 0.95 |
| Topic Return Accuracy | 1.0000 | 1.0000 | >= 0.90 |
| No-op Accuracy | 0.9000 | 0.9000 | >= 0.90 |
| Duplicate Node Rate | 0.0000 | 0.0000 | 0 |
| Node Explosion Rate* | 0.1893 | 0.1643 | < 0.10 |
| Label Quality | 0.8933 | 0.8295 | — |

*The existing Harness metric counts Utterances with more than three total
Events, including Relations and Focus changes. The dedicated Node Economy
metrics below show the number of new Nodes separately.

Candidate Decision Precision improved substantially, while Topic Recall and
Topic Return were preserved. The Node Explosion target was not reached under
the existing event-based metric.

## Duplicate Metrics

Duplicate rates are split into Analyzer proposals and Canonical Graph output.
The supplementary calculation compares normalized labels within the same Node
type and excludes archived Nodes.

| Metric | Run #3 | Run #4 |
| --- | ---: | ---: |
| Proposed Duplicate Rate | 0.0000 | 0.0000 |
| Accepted Duplicate Rate | 0.0000 | 0.0000 |
| Proposed New Nodes | 43 | 37 |
| Accepted Active Nodes | 42 | 36 |

The existing Topic duplicate rate was already zero in Run #3; Run #4 preserved
that result while reducing the total number of Node proposals.

## Node Economy

| Metric | Run #3 | Run #4 |
| --- | ---: | ---: |
| Accepted New Nodes / Utterance | 1.1053 | 0.9474 |
| Maximum New Nodes from One Utterance | 3 | 2 |
| Utterances with 3+ New Nodes | 3 | 0 |
| Final Nodes: Scenario A | 9 | 7 |
| Final Nodes: Scenario B | 11 | 8 |
| Final Nodes: Scenario C | 7 | 7 |
| Final Nodes: Scenario D | 7 | 7 |
| Final Nodes: Scenario E | 8 | 7 |

This is a meaningful improvement in Map density. Scenario B, the previous
worst case, fell from 11 to 8 Nodes.

## Relation Metrics

| Metric | Run #3 | Run #4 |
| --- | ---: | ---: |
| Relations proposed | 40 | 31 |
| Relations accepted | 39 | 30 |
| Relations rejected | 1 | 1 |
| Relations / Utterance | 1.0526 | 0.8158 |
| `related_to` proposed | 0 | 0 |
| `related_to` accepted | 0 | 0 |

Relation volume decreased by 22.5%. The remaining rejected Relation is the
same dependent relation after the existing Action safety guard rejects the
ambiguous E-u006 Action intent.

## Critical Errors and Safety

| Error | Accepted in Graph | Diagnostics / review | Severity |
| --- | ---: | ---: | --- |
| Automatic Confirmation | 0 | 0 | Critical |
| Invented Owner | 0 | 0 | Critical |
| Invented Due Date | 0 | 0 | Critical |
| False Decision | 0 manual false candidates | One expected Decision was conservatively omitted | Major |
| False Action | 0 | 1 rejected at E-u006 | Major |
| Accepted Duplicate Topic | 0 | 0 | Major |
| Unsupported content accepted | 0 | 0 | Major |

Run #4 did not accept the Run #3 false Decisions in B-u006 or E-u001. It also
did not automatically confirm any Decision. The main trade-off is
under-classification: E-u005's expected Candidate Decision was treated as an
Option because the utterance uses weak “よさそうです” language.

## Scenario Review

| Scenario | Review |
| --- | --- |
| A — MVP企画 | Topic Focus, Decision, Action, and Open/Idea content remained readable with 7 Nodes. The opening Topic label is somewhat sentence-like, but the Map is less dense than Run #3. |
| B — Architecture | Topic Focus was fixed, the false Decision became an Idea, and the Map fell from 11 to 8 Nodes. It is substantially easier to scan. |
| C — Brainstorming | New Topic Focus is now present. Options and Concern remain visible with no 3+ Node Utterance. |
| D — 意見対立 | The stable Run #3 structure was preserved: Topic, Options, Concerns, Open Item, and Candidate Decision. Relations were reduced without losing the main structure. |
| E — Topic Return | Existing Topic Return and duplicate prevention remain correct. Current Topic returns to MVP範囲. The expected Candidate Decision at E-u005 is conservatively omitted. |

## Discussion Map Review

The Run #4 Map is preferable to Run #3 for a shared-display discussion:

- all five scenarios have a visible Current Topic after new Topic creation;
- Scenario B is materially less crowded;
- Scenario C retains its Topic and options without extra relations;
- Scenario D remains stable;
- Scenario E preserves Topic Return without duplicate Topics;
- Candidate Decisions are less likely to be created from general framing or
  architecture principles.

The cost is that a weak but potentially useful Decision such as E-u005 is
shown as an Option. This is safer for the Map because a Candidate Decision is
more semantically consequential than an Option and still requires Human
Confirmation.

## Run #3 vs Run #4: Latency, Tokens, and Cost

| Measure | Run #3 | Run #4 |
| --- | ---: | ---: |
| p50 latency | 2.493 sec | 2.236 sec |
| p95 latency | 4.167 sec | 3.067 sec |
| max latency | 4.455 sec | 3.627 sec |
| Input tokens | 113,340 | 119,187 |
| Output tokens | 10,362 | 8,536 |
| Reasoning tokens | 4,873 | 3,849 |
| Total tokens | 123,702 | 127,723 |
| Estimated cost | ~$0.03510 | ~$0.03408 |

Despite a slightly larger input prompt, output and reasoning tokens decreased.
Latency and estimated cost also improved modestly.

## Failure Classification

| Classification | Finding |
| --- | --- |
| Semantic Prompt | Remaining issues are conservative under-classification of some Decisions, sentence-like Topic labels, and the event-based Node Explosion metric still exceeding 0.10. |
| Context Strategy | No new Context failure. Topic Return and new Topic Focus worked in all five scenarios. |
| Model Capability | The model still has difficulty deciding when a weak Japanese proposal should become a Candidate Decision; v4 correctly preferred abstention in most ambiguous cases. |
| Golden Annotation | E-u005 expects a Candidate Decision despite weak “よさそう” wording. Scenario A label matching also remains lexically brittle. |
| Domain Model | No Domain Model or Canonical Event limitation was exposed. |

## Recommended Next Step

**Decision: A — Semantic Prompt Iteration.**

Run #4 achieved the primary goal: Candidate Decision Precision rose from 0.40
to 0.80 while Topic Recall remained 0.70, Topic Return remained 1.00, and
Action Precision remained 1.00. Node and Relation density also decreased.

One more small semantic iteration may improve label concision and the
Decision/Option boundary, but changes should not loosen the conservative
Decision policy without explicit evidence. Context Strategy does not yet need
to change. The system is not ready for STT based on these Recorded Analyzer
metrics alone.

## Artifacts

Machine-readable artifacts are under:

`evaluation/runs/real-analyzer-run-004-gpt-5.6-luna-analyzer-prompt-v4-20260919/`

They include `preflight.json`, `metadata.json`, `metrics.json`, per-utterance
`raw/` and `parsed/` records, per-scenario results, and final Graph snapshots.
