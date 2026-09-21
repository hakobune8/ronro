# Real Analyzer Evaluation Run #3

Status: **Completed**

Run #3 changed only the semantic prompt. The model, reasoning effort, Native
Structured Output, provider-facing Analyzer Output Schema, Canonical Schemas,
Materializer, Dataset, Golden Annotation, Context Builder, Metrics, and Stable
Discussion Map were kept fixed.

## Configuration

| Item | Value |
| --- | --- |
| Provider | OpenAI via the existing OpenAI-compatible HTTP Adapter |
| Model | `gpt-5.6-luna` |
| Reasoning | `medium` |
| Prompt | `analyzer-prompt-v3` |
| Provider-facing schema | `schemas/analyzer-output-v2.schema.json` |
| Dataset | Same 5 Scenarios / 38 Utterances |
| Context strategy | Unchanged from Run #2 |
| Canonical Contract | Unchanged |
| Run ID | `real-analyzer-run-003-gpt-5.6-luna-analyzer-prompt-v3-20260919` |

The model and Structured Output capability remain supported by the official
OpenAI API documentation: [GPT-5.6 Luna model documentation](https://developers.openai.com/api/docs/models/gpt-5.6-luna)
and [Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs).

## Prompt v3 Changes

Prompt v3 kept the v2 output vocabulary and flat shape, and changed only
semantic guidance:

- Defined Topic as a persistent discussion axis rather than a single opinion,
  feature, or proposal.
- Added the decision order: current Topic, existing Topic return, related
  Topic, then new Topic as the last choice.
- Added implicit Topic detection for a durable axis that is not introduced by
  an explicit “let us discuss” phrase.
- Added Topic Return versus Related Topic examples and semantic duplicate
  prevention.
- Restricted Candidate Decisions to explicit “proceed with this direction”
  proposals; preferences and agreement remain non-decisions.
- Preserved the explicit-execution boundary for Actions and the prohibition on
  inferred Owner/Due values.
- Added the node-economy rule and clarified that one Utterance is not one Node.
- Kept the v2 few-shot output shapes and the Human Confirmation boundary.

No Canonical Schema, Provider-facing Schema, Materializer, Context Builder, or
Golden Annotation was changed for this run.

## Preflight

The five representative Run #2 failure cases were executed before the main
run: missing Topic anchor, mixed Concern/Option, explicit Action, Architecture
intent, and Topic Return with an existing Topic.

| Check | Result |
| --- | ---: |
| Cases | 5 / 5 |
| API success | 5 / 5 |
| JSON parse | 5 / 5 |
| Analyzer Output Schema valid | 5 / 5 |
| Canonical conversion | 5 / 5 |
| Canonical Event Schema valid | 5 / 5 |

The preflight artifact is stored in the Run #3 directory.

## Structural Metrics

| Metric | Run #2 | Run #3 |
| --- | ---: | ---: |
| API success | 38 / 38 | 38 / 38 |
| JSON parse success | 38 / 38 | 38 / 38 |
| Analyzer Output valid | 100% | 100% |
| Canonical conversion without validation error | 100% | 100% |
| Canonical Event Schema valid | 55 / 55 | 86 / 86 |
| Canonical Candidate Events accepted | 55 | 86 |
| Schema validation failures | 0 | 0 |
| Raw intents | 57 | 88 |
| Raw intent acceptance | 96.49% | 97.73% |

The Run #2 Output Contract fix did not regress. The two rejected intents in
Run #3 were handled by existing application safety guards and did not enter
the Graph.

## Semantic Metrics

The values below are the existing evaluator's per-scenario aggregate metrics.
They remain comparable with Run #2, but should be read together with the
scenario and manual-review notes because lexical Golden matching can undercount
a semantically correct rewording.

| Metric | Run #2 | Run #3 | Target |
| --- | ---: | ---: | ---: |
| Topic Precision | 1.0000 | 0.8000 | >= 0.90 |
| Topic Recall | 0.4000 | 0.7000 | >= 0.70 |
| Important Node Recall | 0.4333 | 0.4000 | — |
| Candidate Decision Precision | 0.6000 | 0.4000 | >= 0.85 |
| Action Precision | 1.0000 | 1.0000 | >= 0.95 |
| Topic Return Accuracy | 1.0000 | 1.0000 | >= 0.90 |
| No-op Accuracy | 0.9000 | 0.9000 | >= 0.90 |
| Duplicate Node Rate | 0.6000 | 0.0000 | lower than Run #2 |
| Node Explosion Rate | 0.0821 | 0.1893 | <= Run #2 |
| Label Quality | 0.8548 | 0.8933 | — |

Run #3 achieved the Topic Recall target and eliminated duplicate Topic labels,
but did not meet Topic Precision, Candidate Decision Precision, or the Node
Explosion target.

## Critical Errors and Safety

| Error | Accepted in Graph | Diagnostics / semantic review | Severity |
| --- | ---: | ---: | --- |
| Automatic Confirmation | 0 | 0 | Critical |
| Invented Owner | 0 | 0 | Critical |
| Invented Due Date | 0 | 0 | Critical |
| Duplicate Topic | 0 | 0 | Major |
| Unsupported content | 0 | 0 | Major |
| False Decision | 2 semantic mismatches | B-u006, E-u001 | Major |
| False Action | 0 | 1 rejected at E-u006 | Major |

The False Decision count is a semantic review count, not an automatic
confirmation count. The two candidate nodes were never Confirmed. Scenario A's
candidate was semantically appropriate but its wording did not match the
current Golden aliases exactly; this is reported separately from the two
semantic misclassifications.

The existing application guards also recorded one dependent
`relation_reference_unresolved` diagnostic after rejecting the Action intent at
E-u006. No unsafe event reached the Graph.

## Scenario Review

| Scenario | Result | Review |
| --- | --- | --- |
| A — MVP企画 | Topic anchor formed; no duplicate | Candidate Decision and Action were useful. The final acknowledgement-like utterance was over-classified as an Open Item. The Topic/Decision label matcher undercounted semantically correct wording. |
| B — Architecture | Topic created; no current focus | The architecture Topic and important Ideas were captured, but the response created many relations and incorrectly made the deterministic-materialization proposal a Candidate Decision. This is the weakest scenario for Node Economy. |
| C — Brainstorming | Strong Topic and option structure | Visual Intervention, Options, and Concern were captured; No-op behavior was correct. The Topic was not made Current because the response omitted a focus intent. |
| D — 意見対立 | Best semantic result | 価格モデル, both Options, Concerns, Open Item, and the Candidate Decision were represented; No-op and Topic behavior were correct. |
| E — Topic Return | Existing Topic reused | Topic Return remained correct and no duplicate Topic was created. The initial “中心にしましょう” was over-promoted to a Candidate Decision, while the later “対象外でよさそう” was treated as an Option rather than the expected Candidate Decision. |

## Discussion Map Review

All five scenarios reached the existing Stable Discussion Map pipeline and the
Map grew incrementally. The Map was most useful in D and E, where the Topic
spine and related nodes were clear. A and B gained a Topic anchor compared with
Run #2. C retained a useful Topic and option structure.

Remaining Map issues:

- B generated 23 events from 7 utterances and has a high local density;
  relations and repeated architectural Ideas may overwhelm a shared display.
- B and C contain Topic nodes but do not leave a Current Topic focus in the
  final Graph because the Analyzer did not emit `topic_focus` when creating the
  first Topic.
- E has the correct Topic Return but shows the Decision/Option classification
  error described above.
- Labels are more readable overall, but some labels remain too sentence-like
  for a long-running Map.

No duplicate Topic was observed in the final Graphs, and no Candidate Decision
was automatically Confirmed.

## Run #2 vs Run #3: Latency, Tokens, and Cost

| Measure | Run #2 | Run #3 |
| --- | ---: | ---: |
| p50 latency | 2.149 sec | 2.493 sec |
| p95 latency | 3.994 sec | 4.167 sec |
| max latency | 4.569 sec | 4.455 sec |
| Input tokens | 74,799 | 113,340 |
| Output tokens | 8,199 | 10,362 |
| Reasoning tokens | 4,618 | 4,873 |
| Total tokens | 82,998 | 123,702 |
| Estimated cost | ~$0.02480 | ~$0.03510 |
| Context characters | 842–3,222 | 842–3,655 |

The larger semantic prompt increased input volume and cost. The p95 latency
increased modestly; the max was slightly lower than Run #2. This is not yet a
Realtime readiness result.

## Remaining Failure Classification

| Classification | Finding |
| --- | --- |
| Prompt Semantic Rule | Primary remaining issue: Decision threshold is still too permissive for “中心にしましょう” and “進めましょう” in context; first-Topic focus is not consistently emitted; Open Item and relation generation are too generous in some utterances. |
| Context Selection | Existing Topic Return passed. The lack of Current Topic after creating a new Topic is more directly an output-policy issue than missing context, but should be checked if prompt-only fixes do not stabilize it. |
| Model Capability | The model still struggles with nuanced Japanese distinctions among preference, proposal, agreement, and decision, and with compressing multiple intents into a small set of high-value nodes. |
| Golden Annotation | Scenario A has a semantically reasonable Decision label that does not match the frozen aliases; the Topic definition also makes “Discussion Map” a plausible child Idea rather than a separate Topic. This affects lexical metrics but does not justify changing the Golden during the run series. |
| Domain Model | No Domain Model or Canonical Event limitation was exposed. |

## Recommended Next Step

**Decision: A — Semantic Prompt Iteration.**

Run #3 confirms that prompt-only semantic guidance can improve Topic Recall
from 0.4000 to 0.7000 and reduce Duplicate Node Rate from 0.6000 to 0.0000.
However, the same change increased Node Explosion and reduced Candidate
Decision Precision. A further prompt iteration should narrow the Decision rule,
require a `topic_focus` when a newly created Topic becomes the active axis, and
reduce relation generation. Keep the v2/v3 Structured Output Contract and
Context Strategy fixed for that iteration.

If the Current Topic and existing-node behavior remains unstable after that
prompt correction, evaluate Context Strategy separately in Run #4. Do not start
STT, Live Audio, Visual Generation, Minutes, or Persistence.

## Artifacts

Machine-readable artifacts are under:

`evaluation/runs/real-analyzer-run-003-gpt-5.6-luna-analyzer-prompt-v3-20260919/`

They include `preflight.json`, `metadata.json`, `metrics.json`, per-utterance
`raw/` and `parsed/` records, per-scenario results, and final Graph snapshots.
