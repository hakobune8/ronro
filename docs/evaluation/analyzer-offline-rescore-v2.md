# Analyzer Offline Re-score v2

Status: Completed

Evaluation Version: `analyzer-eval-v2`

Golden Version: `golden-v2`

Date: 2026-09-19

## Scope

Runs #2, #3, and #4 were re-scored from their stored scenario results and
final Graphs. No LLM API was called. Prompt versions, Models, Raw outputs,
Parsed outputs, Final Graphs, historical `metrics.json`, and historical review
documents were not changed.

Derived files are under:

`evaluation/rescored/golden-v2/`

The current baseline is now represented by three independent versions:

| Dimension | Value |
| --- | --- |
| Prompt | Run-specific `analyzer-prompt-v2` / `v3` / `v4` |
| Golden | `golden-v2` |
| Evaluation | `analyzer-eval-v2` |

## Golden v2 policy applied

The primary Decision policy evaluates only Strong Candidate Decisions:

- explicit commitment;
- explicit scope choice;
- explicit adoption; or
- explicit rejection.

The four Strong annotations are `real-a-u005`, `real-b-u006`, `real-d-u006`,
and `real-e-u001`. `real-e-u005` is a Weak Scope Signal and is not a missed
Strong Decision when the Analyzer represents it as an Option.

Weak Signal Recall is reported separately and is not a primary Map gate.

## Run comparison

| Metric | Run #2 | Run #3 | Run #4 |
| --- | ---: | ---: | ---: |
| Topic Precision | 1.0000 | 0.8000 | 0.8000 |
| Topic Recall | 0.4000 | 0.7000 | 0.7000 |
| Strong Decision Precision | 0.7500 | 1.0000 | 1.0000 |
| Strong Decision Recall | 0.7500 | 1.0000 | 0.5000 |
| Weak Signal Recall | 0.8571 | 1.0000 | 1.0000 |
| Action Precision | 1.0000 | 1.0000 | 1.0000 |
| Action Recall | 1.0000 | 1.0000 | 1.0000 |
| No-op Accuracy | 0.9000 | 0.9000 | 0.9000 |
| Topic Return Accuracy | 1.0000 | 1.0000 | 1.0000 |
| Proposed Duplicate Rate | 0.0000 | 0.0000 | 0.0000 |
| Accepted Duplicate Rate | 0.0000 | 0.0000 | 0.0000 |
| Accepted New Nodes / Utterance | 1.0263 | 1.1053 | 0.9474 |
| Max Nodes / Utterance | 3 | 3 | 2 |
| 3+ Node Utterance Rate | 0.0526 | 0.0789 | 0.0000 |
| Final Map Node Count | 39 | 42 | 36 |
| Topic Count | 3 | 6 | 6 |
| Child Nodes | 12 | 36 | 30 |
| Nodes / Topic | 4.0000 | 6.0000 | 5.0000 |
| Relation Count | 14 | 39 | 30 |
| Relations / Node | 0.3590 | 0.9286 | 0.8333 |
| Legacy Event Burst Rate | 0.0821 | 0.1893 | 0.1643 |

### Interpretation

Run #2 has a low Node count per Topic partly because three Scenarios have no
Topic Node in the final Graph. That is not a Map-quality advantage. Topic
Count, Topic Coherence, and the Human Map Quality score must be read together
with Node Economy.

Run #3 has the strongest Strong Decision coverage under the v2 Golden, but it
also has the largest Map and the highest Relation density. Run #4 has the best
Node Economy and no False Strong Decision, while missing two Strong Candidates.

## Critical safety results

| Error | Run #2 | Run #3 | Run #4 |
| --- | ---: | ---: | ---: |
| False Strong Decision | 1 | 0 | 0 |
| Missed Strong Decision | 1 | 0 | 2 |
| False Action accepted | 0 | 0 | 0 |
| Invented Owner | 0 | 0 | 0 |
| Invented Due Date | 0 | 0 | 0 |
| Automatic Confirmation | 0 | 0 | 0 |
| Unsupported Content accepted | 0 | 0 | 0 |
| Duplicate Topic accepted | 0 | 0 | 0 |

Run #2's False Strong Decision is E-u005. Run #4's omission of E-u005 is not
an error under Golden v2. The two Run #4 misses are B-u006 and E-u001, which
are explicit policy/scope choices under the v2 rule and should remain visible
as a future semantic improvement target.

## Node Economy and Map Density

The new Primary Node Economy metrics show a consistent Run #4 improvement:

- accepted new Nodes per Utterance fell from `1.1053` in Run #3 to `0.9474`;
- maximum Nodes from one Utterance fell from `3` to `2`;
- 3+ Node Utterance Rate fell from `0.0789` to `0.0000`;
- final active Nodes fell from `42` to `36`;
- Relations fell from `39` to `30`.

Run #2 has `39` final Nodes, but its Topic Count is only `3 / 6` because the
Analyzer often produced flat Nodes. A smaller flat Graph is not preferable to
a slightly larger coherent Graph.

The legacy Event Burst Rate remains historical only. In particular, Run #4's
`0.1643` does not contradict its `0.0000` 3+ Node Utterance Rate because the
legacy numerator includes Relations and Topic Focus Events.

## Human Map Quality comparison

Scores are provisional reviewer scores from the stored final Graphs using the
six-dimension 1–5 rubric: Clarity, Density, Stability, Decision Safety, Topic
Coherence, and Usefulness. They are not participant-study measurements.

Decision Safety receives weight 2 in the weighted score; the other dimensions
receive weight 1. This is intentionally simple and reflects the asymmetric
cost of showing a non-decision as a Decision.

### Scenario means

| Scenario | Run #2 | Run #3 | Run #4 |
| --- | ---: | ---: | ---: |
| A — MVP企画 | 2.50 | 4.00 | 4.00 |
| B — Architecture | 2.50 | 3.33 | 4.17 |
| C — Brainstorming | 4.17 | 4.33 | 4.33 |
| D — 意見対立 | 3.00 | 4.33 | 4.83 |
| E — Topic Return | 3.00 | 3.17 | 4.67 |
| **Unweighted mean** | **3.03** | **3.83** | **4.40** |
| **Decision-Safety-weighted mean** | **3.23** | **3.91** | **4.49** |

### Product reading

- Run #2 has useful content in Brainstorming and Topic Return, but A, B, and
  D are mostly flat because their Topic structure is missing.
- Run #3 establishes a much better Topic spine and has excellent Strong
  Decision coverage, but Architecture is crowded and Topic Return contains a
  False Strong Decision under v2.
- Run #4 is the best shared-display Map baseline. Architecture is materially
  easier to scan, Disagreement retains its useful structure with fewer
  Relations, and Topic Return is stable without a duplicate.

For an actual meeting-room display, choose Run #4 among these three. This is a
product choice, not a claim that Run #4 has completed Analyzer quality: its
Strong Decision Recall is only `0.5000` under the newly explicit v2 Golden.

## Label evaluation

The old `label_quality` remains in the historical metrics, but it is only a
length proxy. Golden v2 treats labels semantically and requires preservation
of Node type, polarity, scope, and commitment strength.

The v2 reviewer rubric is:

| Dimension | Requirement |
| --- | --- |
| Faithful | Meaning and commitment strength are preserved |
| Concise | A short Map label rather than a transcript sentence |
| Understandable | Readable without reopening the transcript |
| Non-redundant | Adds a distinct contribution |

No new automatic label score was invented from the existing artifacts. The
stored Map Quality scores include this rubric qualitatively; a future offline
annotation pass can produce per-Node 1–5 label scores without calling the LLM.

## Baseline and next decision

### Current Evaluation Baseline

Freeze the following combination for comparison:

```text
Prompt:     analyzer-prompt-v4
Golden:     golden-v2
Evaluation: analyzer-eval-v2
```

This is a baseline freeze, not permission to modify v4 or to declare the
Recorded Analyzer ready for STT.

### Prompt v5

Prompt v5 is not created or run in this task. Golden v2 exposes two genuine
Strong Decision misses in Run #4, so a future semantic iteration is justified
after the baseline has been frozen. The current task does not optimize for
that gap.

### Next Decision

**A + B**

- **A — Freeze Prompt v4 / Golden v2:** use this pair as the stable Recorded
  Analyzer evaluation baseline.
- **B — Prompt v5 later:** after baseline publication, address Strong Decision
  Recall for B-u006 and E-u001 without weakening Decision Safety or Node
  Economy.

Do not select C or D yet. Model comparison and STT require the evaluation
baseline to be stable first; Run #4's `0.5000` Strong Decision Recall is not
enough to claim Recorded Analyzer readiness for STT.

## Artifacts

- Golden v2 definition: `docs/evaluation/golden-annotation-v2.md`
- Golden v2 JSON: `evaluation/golden/v2/`
- Derived Run #2: `evaluation/rescored/golden-v2/run-002.json`
- Derived Run #3: `evaluation/rescored/golden-v2/run-003.json`
- Derived Run #4: `evaluation/rescored/golden-v2/run-004.json`
