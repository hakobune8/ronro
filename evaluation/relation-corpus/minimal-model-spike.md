# Minimal Relation Model Spike — argument + discussion provenance

Status: **offline architecture test, no schema/Analyzer/Materializer/Shared View change**. The 31 pair reclassifications are in [`minimal_model_classification.json`](minimal_model_classification.json); the author's original corpus is unchanged, and the independent review supplied by the user is preserved separately in [`human_review.json`](human_review.json). The [A/B/C Human comprehension artifact](minimal-model-review.html) is diagnostic, not a Product UI. This file makes **no** T1/T2 ground-truth or real-world prevalence claim.

## Working semantics and decision rule

Tested types only: existing directed `supports`, existing directed `opposes`, and one **provisional** directed discussion-provenance relation, meaning **“Node B arose in discussion of Node A.”** A provenance edge is allowed only when accessible speech/command Evidence identifies that conversational origin with sufficiently clear endpoints. It does not assert physical causation, proof, successful resolution, agreement, Decision confirmation, Action creation, or merely that A preceded B. `none` in the reclassification means **no direct edge under this sparse model**; it does not erase a comparison, shared Topic, or a relationship visible through a path. `uncertain` means omit the edge. The same argument and provenance edges are different dimensions and may coexist only if independently justified.

| Classification | Pairs / 31 | Interpretation |
| --- | ---: | --- |
| `supports` | 2 | Explicit reason supporting an Option (R3-p3, R4-p3) |
| `opposes` | 1 | Explicit objection to an Option (R3-p4) |
| provisional provenance | 12 | Direct Evidence-backed **discussion origin**, with Japanese interpretation for every pair |
| no direct semantic edge | 14 | Independent, sequence-only, reverse-direction, or redundant direct shortcut |
| uncertain / insufficient directness | 2 | R1-p6, R5-p5; no edge drawn |

The 31 pairs are hand-selected stress cases, not a random sample. These numbers are **not precision/recall**. All 15 provisionally drawn semantic edges were judged relation-present by the independent Human, but the Human's positive judgment does not by itself select an edge type or prove ecological precision. Among the 12 accepted provenance assignments, **0 were marked semantically strained under the working definition** after rejecting ambiguous/shortcut cases. Two technical assignments (R2-p1/p2) have an important **visual causal-misreading risk**; that is not dismissed by the zero-strain count. An arrow alone may be read as “caused,” so Human comprehension of the diagram remains untested.

## Author vs independent Human Review

Author: 16 present / 9 none / 6 uncertain. Independent Human: 19 present / 10 none / 2 uncertain. Exact three-way outcome agreement: **27/31**. The 25 pairs on which the author made a definite present/none judgment received the same definite Human judgment. Description/type agreement has **not** been numerically scored; both sets retain free-language interpretations rather than a forced enum. The four outcome disagreements are:

| Pair | Author → Human | What the disagreement teaches | Sparse-model treatment |
| --- | --- | --- | --- |
| R1-p2 | uncertain → none | Same broad use context is not a direct Node-to-Node origin. | `none` |
| R3-p7 | uncertain → present | Human recognizes that SMS is an object of the unresolved selection. The scored direction Open Item→earlier SMS cannot mean “SMS arose from the Open Item.” | `none` **in that direction**. A later Option→Open Item link could be separately tested; not added to this 31-pair score. |
| R4-p6 | uncertain → present | Human recognizes that the Decision responds to water shortage, without claiming resolution. But Issue→Option→Decision already carries this route; the utterance selecting the Decision refers most directly to the Option. | `none` as a **redundant direct shortcut**, not denial of the indirect connection. |
| R5-p5 | uncertain → present | The migration context makes a Decision→Open Item reading natural. It remains unclear whether the Decision itself, rather than the broader migration work, is the directly stated origin. | `uncertain`; high-precision abstention pending more explicit Evidence/Human review. |

These are real pair-level disagreements; neither reviewer is treated as absolute truth. Human-positive R3-p5 (SMS/App comparison) is also deliberately **not** drawn as a direct minimal-model edge: the common Issue→SMS and Issue→App parents communicate the comparison without falsely making one option derive from the other. R2-p6 is another conservative distinction: possible physical relation between leaves and leakage does not make later-observed leaves the discussion origin of an earlier leakage report. Topic return in R1/R2 likewise remains Event history/navigation, not a provenance cycle.

## Provenance subpatterns — diagnostic readings, not new types

| Natural-language reading | Pair examples | Count accepted as provenance |
| --- | --- | ---: |
| Issue discussed → response Option | R3-p1/p2, R4-p1/p2 | 4 |
| Specific discussion → unresolved question | R1-p3 | 1 |
| Option discussed → Decision candidate | R4-p4 | 1 |
| Confirmed Decision discussed → Action | R5-p1 | 1 |
| Open Item discussed → Action | R5-p2 | 1 |
| Issue discussed → more specific observation | R1-p1, R2-p1 | 2 |
| Technical condition discussed → another hypothesis | R2-p2 | 1 |
| Technical issue discussed → investigation approach | R2-p3 | 1 |

The shared meaning is **how the next contribution entered the meeting**, not the logical status of the source and target. This is broad but remains testable with linking Evidence and directness checks. The technical hypothesis case is the hardest: R2-p2 is supported by “排水口だけを原因と決めず” and adds a competing possibility; it does **not** mean the observed blockage physically produced seal deterioration. If ordinary participants repeatedly read that arrow causally, the semantic model or its presentation fails despite the annotation. We have not added `elaborates`, `causes`, `answers`, `alternative_to`, `results_in`, `related_to`, or `implements` to rescue individual cases.

## Minimality, roots, multiple parents, and cycles

- R3-p1/p2 forms Issue→two sibling Options. R3-p5's meaningful comparison needs no Option↔Option edge in the initial map. `supports` and `opposes` still show the distinct argumentative reasons for each Option.
- R4 keeps Issue→Option→Decision, plus Idea→Option `supports`. R4-p6 is omitted because it would duplicate the path without separate direct linking Evidence. **Decision status stays `candidate` until the existing Human confirmation command**; no edge changes it or marks water shortage resolved.
- R5 keeps Decision→Action and Open Item→different Action. Action owner and due come from explicit utterances, not from an edge. The Open Item remains active until its own lifecycle Event. R5-p5 is omitted pending clearer directness. R3-p7 illustrates that an *opposite-direction* Option→Open Item might be meaningful; the scored Open Item→Option is not automatically flipped or counted.
- R1's event-publicity discussion, R2's separate bridge, and R5's meeting-room issue are independently introduced; **multiple presentation roots are valid**. A future Action could have both Decision and Open Item as provenance parents if the linking Evidence states both; the corpus does not fabricate such a case.
- Provenance should be DAG-like: cycles would say each Node arose from discussion of the other. Revisiting an earlier Node updates Event/focus history instead. A later utterance may establish a missing edge between already-existing Nodes, provided it supplies new linking Evidence; event creation time and Node creation time are different. Do not infer origin from chronology alone.
- The graph is intentionally sparse. `none`/`uncertain` Nodes remain fully available in Graph and final detail. No transitive closure is materialized; no edge is added to improve layout symmetry.

## A/B/C diagnostic value for Live and Final

The generated [comparison artifact](minimal-model-review.html) shows all five archetypes in three views: A temporal Node order only; B only the two existing argument types; C argument plus the 12 accepted provenance pairs. For each archetype it also shows a **3–5 Node Live neighborhood**, a separately labeled latest full evaluation-Node text, and a **Final multi-entry overview** using the same accepted semantic edges. These are offline **conceptual** views; no ordinary participant has scored them yet.

| Case | What C adds over sequence/argument only | Residual caution |
| --- | --- | --- |
| R1 | Evening-use issue→specific parking point→Open Item; separate publicity entry stays independent. | After a Topic return, “latest added Node” and current focus may differ; label the detail area honestly. |
| R2 | Leak observation→context/hypothesis/investigation; separate bridge remains unlinked. | Plain arrows may be mistaken for physical causes. No cause has been confirmed. |
| R3 | Both Options visibly emerge under the same notification Issue; B already contributes support/opposition. | The deferred Open Item's target may need reverse/multiple-parent provenance, but scored direction is invalid. |
| R4 | Issue→Options→Decision explains the selection path without an Issue→Decision shortcut. | Confirmation and actual problem resolution are separate states/events. |
| R5 | Distinct Decision and Open Item origins explain why two different Actions exist; separate issue stays a second entry. | Direct Decision→Open Item remains disputed; no owner/due is inferred. |

This suggests a useful common **Graph + Event history** basis for Live (“where are we?”) and Final (“how did we get here and what remains?”). It does **not** prove distance readability, participant comprehension, or real-world relation precision. Sequence overlays can show returns and shifts where no semantic edge exists, but must not be styled as provenance arrows. Latest Detail uses full Canonical content and must be visually separate from the focused overview; the corpus examples use authored evaluation Node labels as stand-ins, not deployed Canonical Nodes.

## Existing contract and smallest *eventual* impact — design only

Current `related_to` accepts almost any non-archived endpoint but lacks the **directional, Evidence-testable “B arose from discussing A” assertion**; using it would collapse meaningful and merely topical relationships. `has_option` remains structural **Topic→Option**. Widening it to Concern→Option would silently change existing semantics and would still not cover Option→Decision or Decision/Open Item→Action.

If a real-world probe validates the minimal model, the smallest future product proposal would add one distinct directed enum value to Analyzer Output, Event, and Graph schemas and one endpoint rule for non-Topic Nodes, leaving old Graphs with no such edges valid. Materializer would enforce distinct endpoints, valid existing Nodes, duplicate/idempotency checks, and **no provenance cycle**; evidence would be in the `relation_detected` Event's `source_evidence_ids`, traceable through Graph Edge `source_event_ids`. The evidence must include the utterance/command that **establishes the link**, not merely the utterances that separately created each endpoint. Source and target Node IDs and their existing Evidence lineage remain available. Where the existing Analyzer adapter only permits current-utterance Evidence, a late relation must be justified by a later linking utterance or Human command; merely reinterpreting old separate labels is insufficient. Human add/remove relation commands would eventually need auditable Events rather than direct Graph mutation. No confidence score or broad new taxonomy is proposed. None of this was implemented in this Spike.

Developer-name candidates **only because the offline model provisionally holds**: `arose_from_discussion_of`, `discussion_provenance`, or `emerged_from_discussion_of`. The first most clearly limits the claim to discussion; none is selected as an enum or participant-facing Japanese label. A simple unlabeled directional connection may be possible in UI, but causal misreading must be tested before adoption.

## Decision and exactly one next step

**A. MINIMAL MODEL HOLDS — provisionally on the controlled corpus.** `supports`/`opposes` plus one conservatively defined provenance edge explains the most useful direct paths across R1–R5 without adding a taxonomy or forcing connectedness. This is **not** a schema-adoption or Pilot-readiness decision. Abstaining on two uncertain pairs and omitting three Human-recognized but redundant/reverse/comparison pairs is intentional precision-first behavior. The absence of an evidence-complete real-world pair set and a Human comprehension review of the *new* maps remains the chief validation gap.

**Exactly one next Spike: a 5–10-minute Evidence-complete real-world Relation Probe.** Obtain consent and preserve Final transcript Evidence→Node→proposed Relation, sample a discussion with at least a problem/approach and an actual comparison or execution transition, have Human reviewers audit **every** proposed edge and an explicit no-edge/uncertain sample, check causal/resolution/confirmation misreadings in both Live and Final conceptual views, and compare against sequence-only. Do not replay T1/T2 audio or change Product for this probe. T3, RFC-0006, Pilot, and Release remain pending.
