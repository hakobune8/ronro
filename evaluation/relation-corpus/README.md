# RONRO Relation Evaluation Corpus — offline Spike

**Status: provisional, authored evaluation material; not a Golden taxonomy and not a Product change.** All controlled Japanese utterances here were written for this Spike. T1/T2 are registered as real-world probes but have **no semantic pair labels** because accessible retained files do not expose the necessary utterance text. No source audio, transcript, Provider call, Analyzer rerun, or Product change is involved.

## Files and review order

1. Give an independent Human reviewer [`review-blind.html`](review-blind.html) **only**. It shows authored utterances, proposed Node units, and candidate pairs, but no author's outcome or type mapping. The reviewer records `present`, `none`, or `uncertain`, a free Japanese explanation, and supporting Evidence IDs. “No relation” and independent roots are valid answers. A reviewer may flag a missing candidate pair.
2. Then compare with [`comparison.html`](comparison.html), which displays A: sequence only; B: current `supports`/`opposes` only; C: author-intended natural-language semantics. C is not a Canonical Graph or accepted model output. The [structured corpus](corpus.json) carries the same provisional author intent, Evidence references, Node units, and existing-type mapping.
3. Run `python3 evaluation/relation-corpus/build_review.py` from the repository root to validate references and regenerate both HTML files. It uses only the Python standard library. The blind reviewer should not open `corpus.json`, this README's results section, or `comparison.html` before making their pass.

The visual pages are **diagnostic**, not a UI or 3–5 m readability proposal. A chronological arrow only means “later,” never “caused/supports.” B does not hide other Nodes: it shows which Node-to-Node semantic links existing types can express. `contains`/`has_option` remain Topic structure and are not counted as semantic pair coverage. C leaves uncertain pairs unconnected.

## Corpus composition and Evidence coverage

| Source | Role | Evidence and limits |
| --- | --- | --- |
| T1 completed panel | Ecological exploratory-discovery probe | 53 Finals, 38 Nodes, 31 `contains` edges, 0 semantic edges. Saved Node labels/Evidence IDs but no accessible Final utterance text here: **UNVERIFIABLE for pair annotation**. Its 16 prior screening pairs are not imported as Goldens. |
| T2 technical panel | Ecological technical-workload probe | Retained failed-run Graph has 12 Nodes and 11 `contains` edges. Accessible Evidence/Utterance records do not contain speech text. Later run's four empty Provider items total ~5.248 s: **UNVERIFIABLE**, with no inferred missing content. |
| R1–R5 controlled | Known-intent boundary cases | 29 authored spoken utterances plus two explicit Human-command records; all 27 proposed Nodes and all 31 candidate pairs cite accessible authored Evidence IDs. Author intent is provisional, not independent Human agreement. |

| Controlled case | Discussion structure | Evidence records | Nodes | Pairs | Author `present` / `none` / `uncertain` |
| --- | --- | ---: | ---: | ---: | ---: |
| R1 | Exploratory: concrete examples, open question, separate issue, Topic return | 6 | 5 | 6 | 2 / 2 / 2 |
| R2 | Technical: observation vs unproven cause, alternative hypotheses, separate bridge, return | 6 | 6 | 6 | 3 / 2 / 1 |
| R3 | Option comparison: two routes, support, explicit opposition, deferred choice | 6 | 6 | 7 | 5 / 1 / 1 |
| R4 | Decision-making: two options, Candidate Decision, explicit Human confirmation | 7 incl. 1 command | 5 | 6 | 4 / 1 / 1 |
| R5 | Execution: Confirmed Decision, Open Item, two Actions, explicit owner/due, separate root | 6 incl. 1 command | 5 | 6 | 2 / 3 / 1 |
| **Total** | Five archetypes | **31** | **27** | **31** | **16 / 9 / 6** |

R1 and R2 are *controlled* examples that exercise structures observed in real discussions; they are not reconstructed T1/T2 speech. R3/R4/R5 make positive and negative cases explicit. In R5 the due date and owners appear directly in authored utterances. R4's Decision remains `candidate` until a separate Human confirmation record; conversational “異論ありません” alone does not confirm it. An Action origin link would not create an Action or infer owner/due. R3 intentionally ends without choosing between options.

## Emergent natural-language semantics, before taxonomy

The author descriptions recurring across cases include: an issue explored through a more specific observation or example; a problem followed by an approach or option; competing possibilities compared without logical opposition; explicit support or opposition; an option becoming the content of a Decision candidate; and a Decision/Open Item motivating a concrete next action. These descriptions are retained as Japanese free text in the corpus; they are **not adopted Relation names**. A technical observation next to a fault is **not** labeled “causes,” and a decided response does **not** mean the issue is resolved. Broad same-Topic similarity, conversational return, and adjacent independent items remain unconnected or uncertain.

Three of 16 author-`present` pairs match a currently allowed, reasonably precise Node-to-Node semantic type: two `supports` and one `opposes`. Thirteen author-`present` pairs are not truthfully expressible by those two types. That is **not measured recall** or evidence that thirteen new edges should be Canonical: pair candidates were deliberately selected to probe model boundaries, and only one author has annotated them. `related_to` could connect nearly anything but would erase the distinction among example, comparison, origin, and outcome; it is not counted as meaningful coverage. `has_option` is currently Topic→Option and cannot directly express Concern→Option without changing its endpoint semantics.

Unmapped patterns that recur across archetypes are candidate *questions* for later evaluation, especially issue→approach and outcome→Action. There is no support here for adding a type that appears once. If independent reviewers disagree frequently about a distinction, that is evidence against making it Canonical. Present vs no-relation precision takes priority over edge density.

## A/B/C conceptual maps by archetype

The companion HTML gives each case's utterances, Nodes, and three representations. In condensed form:

| Case | A. Sequence only | B. Existing semantic types only | C. Author-intended semantics — provisional |
| --- | --- | --- | --- |
| R1 | Evening-use discussion → separate event-publicity issue → return; clear “when,” weak “why.” | No `supports`/`opposes` edges. | Issue-specific example and resulting unresolved question may explain the local 3–5-Node neighborhood. Publicity remains an independent presentation entry, not forced under evening use. |
| R2 | Leak observations → second bridge → leak return; chronology cannot certify cause. | No precise semantic edge; especially no invented cause. | Observation, alternative hypothesis, and investigation approach can be distinguished; separate bridge stays unlinked. |
| R3 | Options arrive in order; chronology alone obscures that both address the same notification problem. | SMS support and explicit app-only opposition are expressible. | Common issue, compared options, and deferred choice clarify the Final multi-root/branch view without calling the options opponents. |
| R4 | Discussion → proposal → Human confirmation is visible as history, but why this option was selected is weak. | Supporting reason → option is expressible. | Option selected into Decision candidate is a distinct outcome claim; Human confirmation changes the same Decision Node's state, not the edge. |
| R5 | Confirmed plan → actions → separate meeting-room issue is chronological only. | Neither Decision→Action nor Open Item→Action fits `supports`/`opposes`. | Origin of each Action matters in the Final record. The unrelated meeting-room issue remains a separate root. |

For **Live**, a 3–5-Node local view gains potential value from knowing whether an adjacent Node is an example, counterargument, response, or merely next in time. For **Final**, supported option/outcome/action origins could make a multi-root record more intelligible than chronological cards. These are *design hypotheses from authored cases*. No Human comprehension score or real-world relation precision was measured, and an unlinked Node is not automatically a verified independent semantic root. A/B/C should be judged by whether the meaning becomes clearer **without false lines**, not by visual attractiveness.

## Annotation agreement and safety

There is currently **one author-intended pass and zero independent completed passes**. Relation-present agreement, description/type agreement, no-relation agreement, and reviewer uncertain rate are therefore **not measurable**; do not report 100% or use the author's own re-reading as an independent annotator. The blind sheet enables a Human pass. Adjudication should compare each pair's `present`/`none`/`uncertain`, supporting Evidence IDs, and freely written Japanese relationship, with a separate tally for false causal, false Decision, and false Action-origin claims. The candidate-pair list should not constrain reviewers from identifying missing pairs, and its sampled proportions are not population prevalence.

Existing fixtures establish syntactic safety (endpoint matrix, self-edge rejection, Decision confirmation, Action owner/due guards, Topic return). They do **not** validate relation truth. Neither a deterministic endpoint check nor agreement between model outputs would replace Human Evidence review.

## Decision and exactly one next Spike

**E. MORE DIVERSE EVIDENCE REQUIRED.** Controlled archetypes expose plausible gaps, but real-world pair Evidence is inaccessible and no independent Human pass is complete. Do not adopt a taxonomy, add schema types, tune Analyzer, or change Shared View from this corpus alone. Sequence plus existing precise Relations remains the safe interim representation; it is not yet declared the final sufficient model.

**One next Spike: blinded cross-archetype validation.** Have an independent Human annotate the controlled blind sheet, then add a *small* consented, Evidence-complete real-world sample spanning exploratory and technical/decision/execution discussion (or recover authorized Evidence only where genuinely available). Adjudicate natural-language descriptions and none/uncertain outcomes, measure agreement and high-precision mapping to current types, and compare A/B/C comprehension. Only after that decide whether any recurring semantic distinction deserves a Canonical type. T1/T2 audio is not rerun; T3, RFC-0006, Pilot, and Release remain out of scope.

## Follow-up: minimal one-relation stress test

The independent Human's **pair-level** review is now preserved in
[`human_review.json`](human_review.json); it is not replaced by the author's
earlier annotation. The separate [Minimal Relation Model Spike](minimal-model-spike.md)
reclassifies all 31 pairs using only existing `supports`/`opposes`, one
provisional discussion-provenance meaning, no direct edge, or uncertain. Its
[offline A/B/C artifact](minimal-model-review.html) compares sequence-only,
existing argument edges, and the minimal model for every archetype, including
Live local and Final multi-entry conceptual views. This follow-up supersedes
the earlier “one next Spike” paragraph above; the original Corpus construction
and annotations remain intact as diagnostic history. No Canonical type was
added and no Product behavior was changed.
