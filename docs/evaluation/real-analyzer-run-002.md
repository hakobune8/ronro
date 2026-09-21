# Real Analyzer Evaluation Run #2

Status: **Completed**

Run #2 tested whether the Run #1 failure was primarily an output-contract
problem. The Model, Dataset, Golden Annotation, Context Strategy, Canonical
Schemas, Materializer, Map, and metrics were kept fixed.

## Run #1 Problem Summary

Run #1 reached the provider successfully, but only 6/38 responses passed the
provider-facing schema. The remaining responses used missing `kind` fields,
nested objects, unsupported node types, and unsupported relation names. No
Canonical Candidate Event was accepted.

## Configuration

| Item | Value |
| --- | --- |
| Provider | OpenAI via the existing OpenAI-compatible HTTP Adapter |
| Model | `gpt-5.6-luna` |
| Reasoning | `medium` |
| Prompt | `analyzer-prompt-v2` |
| Provider-facing schema | `schemas/analyzer-output-v2.schema.json` |
| Dataset | Same 5 Scenarios / 38 Utterances |
| Run ID | `real-analyzer-run-002-gpt-5.6-luna-analyzer-prompt-v2-20260919` |
| Canonical Contract | Unchanged |

The selected model officially supports Structured Outputs and the
`json_schema` response format. See the [GPT-5.6 Luna model documentation](https://developers.openai.com/api/docs/models/gpt-5.6-luna)
and the [Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs).

## Prompt v2 Changes

Prompt v2 changed output instructions, not the semantic product policy:

- allowed intent kinds are explicitly limited to `node`, `relation`, and
  `topic_focus`;
- allowed node types and relation types are enumerated;
- all application-owned IDs and Event envelope fields remain prohibited;
- decisions remain candidate-only;
- human commands, automatic confirmation, inferred Owner/Due, and Parking Lot
  node types remain prohibited;
- flat examples were added for Open Item, Decision Candidate, Action, No-op,
  and Existing Topic Return;
- unsupported nested Graph output and prose were explicitly prohibited.

The new v2 schema is provider-facing only. It does not replace or alter the
Canonical Domain/Event Schemas.

## Native Structured Output and Preflight

The first preflight attempt was intentionally stopped before the main run. The
provider rejected `uniqueItems` in the native schema. That unsupported keyword
was removed from the provider-facing v2 schema; no Canonical Schema was
changed. The preflight was then rerun.

| Preflight check | Result |
| --- | ---: |
| Cases | 5 / 5 |
| API success | 5 / 5 |
| JSON parse | 5 / 5 |
| Analyzer Output Schema | 5 / 5 |
| Canonical conversion | 5 / 5 |
| Canonical Event validation | 5 / 5 |

Representative cases covered Topic/Idea, Concern/Option, Action, Architecture
Intent, and Existing Topic Return.

## Structural Metrics

| Metric | Run #1 | Run #2 |
| --- | ---: | ---: |
| API success | 38 / 38 | 38 / 38 |
| JSON parse success | Not usable for 32 | 38 / 38 (100%) |
| Analyzer Output Schema valid | 6 / 38 (15.8%) | 38 / 38 (100%) |
| Canonical conversion without validation error | 6 / 38 | 38 / 38 (100%) |
| Canonical Event Schema valid | 0 accepted | 55 / 55 accepted events (100%) |
| Canonical Candidate Events accepted | 0 | 55 |
| Schema validation failures | 32 | 0 |

Run #2 produced 57 raw intents, of which 55 became Canonical Candidate Events.
Two intents in one utterance were rejected by application safety guards; they
did not enter the Graph. Thus the strict raw-intent acceptance rate was
96.49%, while the utterance-level conversion path returned without a validation
error for 38/38 calls.

## Semantic Metrics

The existing evaluator's aggregate values are shown for Run #1 comparison.
Some values use per-scenario averages and some are undefined when there are no
predicted nodes; they should be read together with the scenario review below.

| Metric | Run #1 | Run #2 |
| --- | ---: | ---: |
| Topic Precision | N/A | 1.0000 |
| Topic Recall | 0.0000 | 0.4000 |
| Important Node Recall | 0.0000 | 0.4333 |
| Candidate Decision Precision | N/A | 0.6000 |
| Action Precision | N/A | 1.0000 |
| Topic Return Accuracy | 0.0000 | 1.0000 |
| No-op Accuracy | 0.7500 validated-only | 0.9000 (7/8 globally: 0.8750) |
| Duplicate Node Rate | N/A | 0.6000 |
| Node Explosion Rate | 0.0000* | 0.0821 |
| Label Quality | N/A | 0.8548 |

`Topic Precision=1.0` means no false Topic label was observed among predicted
Topics; it does not mean that Topic coverage is complete. Topic Recall remains
the largest semantic gap. Scenario E correctly reused the existing MVP Topic
and returned to it without creating a duplicate Topic.

## Critical Errors

### Safety boundary

| Error | Accepted in Graph | Blocked / observed | Severity |
| --- | ---: | ---: | --- |
| Automatic Confirmation | 0 | 0 | Critical |
| Invented Owner | 0 | 0 | Critical |
| Invented Due Date | 0 | 0 | Critical |
| Duplicate Topic | 0 | 0 | Major |
| Unsupported content | 0 | 0 | Major |

### Semantic / guard diagnostics

- False Decision: 1 candidate mismatch against the current Golden Annotation
  (`scenario-b-architecture / real-b-u006`). The wording is arguably a policy
  decision, so this is a semantic review item rather than an automatic
  confirmation violation.
- False Action: 1 raw Action intent was rejected at
  `scenario-e-topic-return / real-e-u006`; no false Action reached the Graph.
- Relation reference unresolved: 1 dependent relation was rejected after the
  Action guard rejected its target. This is a conversion diagnostic, not a
  Graph corruption.

The safety boundary therefore remains intact: no Human Confirmation Event was
generated, and Owner/Due were not invented.

## Scenario Results

| Scenario | Valid | No-op | Candidate Events | Nodes | Edges | Main result |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| A — MVP企画 | 8/8 | 1 | 10 | 9 | 1 | Decision and Action detected; MVP Topic itself was not created |
| B — Architecture | 7/7 | 1 | 8 | 8 | 0 | Important ideas detected; one policy statement became a Candidate Decision |
| C — Brainstorming | 8/8 | 2 | 13 | 7 | 6 | Best structural Map: Topic, Options, Concern, and relations were materialized |
| D — 意見対立 | 8/8 | 2 | 8 | 7 | 1 | Options, Concerns, Open Item, and Candidate Decision detected |
| E — Topic Return | 7/7 | 2 | 16 | 8 | 6 | Existing Topic Return succeeded; one Action boundary was rejected safely |

## Discussion Map Review

The Stable Discussion Map used the same materializer and projection path as the
Fake Analyzer. The Map grew in all five scenarios. Scenario C and Scenario E
were visually useful enough to inspect because they contained a Topic spine
and relations. Scenarios A, B, and D lacked a top-level Topic node, so their
Map would appear as a collection of cards without the intended Topic Lane
anchor.

Positive observations:

- Existing Topic Return in Scenario E used the existing Topic ID and did not
  create a duplicate.
- Candidate Decisions stayed candidate; no automatic confirmation occurred.
- Open Items and Actions were represented as distinct Canonical node types.
- Invalid or unsafe intents did not corrupt the Graph.
- Labels were generally concise and readable; the heuristic label score was
  0.8548.

Remaining Map issues:

- Topic creation/focus is under-detected when the first utterance expresses a
  topic through an idea rather than naming it directly.
- Some scenario graphs therefore have `current_topic.primary_topic_id=null`.
- Scenario E generated a high number of events relative to utterances
  (16/7), which is acceptable for this small scenario but should be monitored
  for Node/Edge explosion in longer sessions.

## Latency, Tokens, and Cost

| Measure | Run #1 | Run #2 |
| --- | ---: | ---: |
| p50 latency | 2.139 sec | 2.149 sec |
| p95 latency | 3.137 sec | 3.994 sec |
| max latency | 3.605 sec | 4.569 sec |
| Input tokens | 20,023 | 74,799 |
| Output tokens | 6,566 | 8,199 |
| Reasoning tokens | 4,487 | 4,618 |
| Total tokens | 26,589 | 82,998 |
| Estimated cost | ~$0.01188 | ~$0.02480 |
| Context characters | 805–931 | 842–3,222 |

The major cost increase is input-side: the strict schema and v2 examples add
prompt/schema overhead. Latency remains within the broad 3–10 second target for
most calls, but the p95/max increase should be measured again after reducing
unnecessary prompt/schema repetition.

## Failure Classification

| Classification | Run #2 finding |
| --- | --- |
| Output Contract Failure | Resolved for this run: 38/38 v2 outputs valid |
| Semantic Classification Failure | Remaining: Topic Recall, one Golden Decision mismatch, one Action boundary mismatch |
| Context Failure | Existing Topic Return passed; initial Topic availability remains weak |
| Canonical Conversion Failure | No schema conversion failure; two guard diagnostics were safely rejected |
| Domain Model Mismatch | None observed |

## Run #1 vs Run #2

Run #2 confirms the Run #1 hypothesis. The Model was able to produce useful
Discussion intents once the output vocabulary, flat shape, examples, and native
JSON Schema constraint were made explicit. Structured validity improved from
15.8% to 100%, and Canonical Candidate Events increased from 0 to 55.

This does not yet establish MVP-level semantic quality: Topic Recall is only
0.4, the Candidate Decision metric is 0.6, and three scenarios lack a Topic
anchor. The improvement is therefore a successful contract-layer iteration,
not a readiness signal for STT.

## Recommended Next Step

**Decision: A — Semantic Prompt Iteration.**

The output contract is now sufficiently stable for semantic iteration. Keep
the v2 schema and Native Structured Output boundary fixed. The next iteration
should target:

1. detecting or reusing a Topic anchor before emitting child Ideas;
2. distinguishing a policy proposal from a Candidate Decision using the Golden
   Annotation and human-confirmation boundary;
3. deciding whether explicit `検証します` is an Action for this dataset, then
   aligning the safety rule and annotation without changing the Domain Schema;
4. reducing schema/prompt input overhead while preserving 100% structural
   validity.

Do not start STT, Live Audio, or other product phases yet.

## Artifacts

Machine-readable artifacts are under:

`evaluation/runs/real-analyzer-run-002-gpt-5.6-luna-analyzer-prompt-v2-20260919/`

They include `preflight.json`, `metadata.json`, `metrics.json`, per-utterance
`raw/` and `parsed/` records, per-scenario results, and final Graph snapshots.
