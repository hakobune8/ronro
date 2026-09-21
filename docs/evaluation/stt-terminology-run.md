# STT Terminology Run

## Purpose

This run isolates the effect of STT lexical/context hints. Analyzer Noise Guard, Prompt v5, Type D, Normalization v2, the Canonical Schema, Materializer, and Presentation Compaction were unchanged.

The comparison is:

* Run A: saved `gpt-4o-transcribe-diarize` result, reused without another STT call.
* Run B: recorded audio → `gpt-transcribe` with meeting context and keyword hints → Normalization v2 → the same `gpt-5.6-luna` Analyzer v4 pipeline.

The model choice follows the current OpenAI transcription API: `gpt-transcribe` supports unstructured context and keyword hints, while `gpt-4o-transcribe-diarize` does not support `prompt`. See the [Create transcription API reference](https://developers.openai.com/api/reference/cli/resources/audio/subresources/transcriptions/methods/create) and [GPT-Transcribe model documentation](https://developers.openai.com/api/docs/models/gpt-transcribe).

## Frozen Configuration

| Layer | Configuration |
|---|---|
| STT A | `gpt-4o-transcribe-diarize` |
| STT B | `gpt-transcribe` |
| STT B context | Short Japanese meeting description; no reference transcript |
| STT B hints | Dataset terms only: Discussion Map, MVP, Visual Artifact, Current Topic, STT, Open Item, Action, Decision, Privacy, Transcript, Provider, Human Correction, Event Catalog, Parking, Recent Flow, Compact Overview, Static Mock, Discussion Analysis, Recorded Transcript, Partial Transcript, Visual, Analyzer, Topic |
| Analyzer | `gpt-5.6-luna`, reasoning `medium`, `analyzer-prompt-v4`, Context v1 |
| Normalization | v2 |
| Golden / Evaluation | `golden-v2` / `analyzer-eval-v2` |
| Type D / Noise Guard | OFF / OFF |

The runtime API surface returned JSON text for `gpt-transcribe`, without segment timestamps. To preserve deterministic audio traceability, Run B used fixed 15-second transport chunks and attached absolute chunk offsets to Raw STT Evidence. This is an adapter transport detail; no semantic merge or Analyzer rule was added.

## Preflight

The existing 4-minute audio preflight completed before the 30-minute run:

| Metric | A: diarized baseline | B: terminology-aware |
|---|---:|---:|
| CER | 0.3589 | 0.0705 |
| Raw segments | 17 | 16 |
| Normalized v2 utterances | 16 | 16 |
| Proper-term accuracy on observed terms | 1.0000 | 1.0000 |
| Critical STT errors | 0 | 0 |

The preflight gate passed, so B was continued to the full audio. The preflight artifacts are in `evaluation/stt/terminology-run/preflight/`.

## 30-minute STT Results

| Metric | A | B |
|---|---:|---:|
| Audio | 1800 s | 1800 s |
| Raw segments | 129 | 120 |
| Normalized v2 utterances | 119 | 120 |
| CER | 0.2834 | 0.2527 |
| Proper-term accuracy (strict term set) | 0.4130 | 0.6522 |
| Critical STT errors | 0 | 0 |

The improvement is real but smaller than the preflight improvement. B removed many baseline phonetic substitutions for the short English technical terms, but it still missed or split longer phrases such as `Current Topic`, `Compact Overview`, and `Recorded Transcript`.

### Technical term accuracy

Accuracy uses occurrence counts from the clean transcript. Japanese renderings such as `ディスカッションマップ` and `オープンアイテム` are accepted as correct; partial or phonetic substitutions are recorded separately.

| Term | Occurrences | A | B |
|---|---:|---:|---:|
| Discussion Map | 3 | 2/3 (0.6667) | 3/3 (1.0000) |
| MVP | 5 | 3/5 (0.6000) | 5/5 (1.0000) |
| Visual Artifact | 2 | 1/2 (0.5000) | 1/2 (0.5000) |
| Current Topic | 3 | 0/3 (0.0000) | 0/3 (0.0000; 2 partial substitutions) |
| STT | 2 | 1/2 (0.5000) | 2/2 (1.0000) |
| Open Item | 5 | 3/5 (0.6000) | 5/5 (1.0000) |
| Privacy | 5 | 3/5 (0.6000) | 4/5 (0.8000) |
| Transcript | 5 | 1/5 (0.2000) | 3/5 (0.6000) |
| Provider | 2 | 1/2 (0.5000) | 2/2 (1.0000) |
| Parking | 2 | 1/2 (0.5000) | 1/2 (0.5000) |

The complete per-occurrence trace is in `evaluation/stt/terminology-run/full/technical-term-accuracy.json`.

## Analyzer and Graph Comparison

Both branches used the same Analyzer and Materializer. No Noise Guard or Prompt change was applied.

| Metric | Clean | A | B |
|---|---:|---:|---:|
| Topic count | 6 | 6 | 6 |
| Topic precision | 1.0000 | 1.0000 | 1.0000 |
| Topic recall | 1.0000 | 1.0000 | 1.0000 |
| Final nodes | 90 | 94 | 95 |
| Relations | 85 | 90 | 89 |
| Nodes / topic | 15.0000 | 15.6667 | 15.8333 |
| Candidate decisions | 6 | 5 | 8 |
| Strong decision precision* | — | 0.4000 | 0.1250 strict / 0.2500 semantic review |
| Strong decision recall* | — | 1.0000 | 0.5000 strict / 1.0000 semantic review |
| Actions | 5 | 7 | 7 |
| Action precision | — | 1.0000 | 1.0000 |
| Action recall | — | 0.8750 | 0.6250 |
| Open items | 13 | 16 | 12 |
| Non-strong decisions | — | 3 | 6 semantic / 7 strict |
| Strict no-op accuracy | — | 0.5000 | 0.6500 |
| Max nodes / utterance | — | 2 | 2 |
| 3+ node utterance rate | — | 0.0000 | 0.0000 |

\* The existing workload metric recognizes two strong decision axes. B's `ERとASCRIT全文は外部PROVIDERへ送信しない方針` is semantically the expected external-provider decision despite lexical corruption, so semantic review counts it; the strict label matcher does not. This distinction is why both values are reported.

The detailed machine-readable comparison is `evaluation/stt/terminology-run/full/comparison.json`.

### Graph differences

Compared with Clean:

* A retained all six Topic axes, had three extra non-strong decisions, three extra Open Items, and two extra action concepts (`comparison-table`, `event-catalog`) under the existing workload diagnostic.
* B retained all six Topic axes and the semantic Current Topic, but produced six semantic non-strong decisions, one missing strict strong decision label, one extra event-catalog action, and one missing strict static-mock action label. The underlying utterance still contains the static mock execution intent, but the STT label `スタキック目標` is not accepted by the strict action matcher.
* No wrong Current Topic or automatic confirmation was observed.

## Map Quality

| Map | Clarity | Density | Decision Safety | Topic Coherence | Stability | Usefulness |
|---|---:|---:|---:|---:|---:|---:|
| Clean | 5 | 5 | 5 | 5 | 5 | 4.8 |
| A | 3 | 4 | 4 | 3 | 5 | 3.8 |
| B | 4 | 3 | 4 | 4 | 5 | 4.0 |

`B` is visibly better than A on terminology and Topic labels, but it does not reach the 4.3 target. The remaining degradation comes from Analyzer-visible consequences: eight Candidate Decisions, residual phonetic labels, and seven Actions rather than only the five Clean action concepts. Presentation Projection still preserved all generated critical state; both A and B report projection Critical Information Recall 1.0. That projection metric does not mean the labels are equally understandable.

## Critical STT Safety

| Error class | A | B |
|---|---:|---:|
| Negation inversion | 0 | 0 |
| Decision meaning reversal | 0 | 0 |
| Action meaning reversal | 0 | 0 |
| Invented Owner / Due | 0 / 0 | 0 / 0 |
| Automatic confirmation | 0 | 0 |

B has nine diagnostic Topic-keyword misses, but none reversed a negation, Decision, or Action. The Analyzer also recorded three diagnostics in B (`relation_reference_unresolved` twice and `inferred_action_metadata_rejected` once); no invalid data was applied to the graph.

## Speaker Attribution

A retained diarized speaker labels. B's `gpt-transcribe` JSON response did not include speaker attribution, so every B normalized utterance has `speaker=null`. In this dataset no Owner-bearing Action depended on speaker identity, so no observed Map or Action Safety regression resulted. The loss is still material for future Owner attribution, minutes, and human auditability, so B is not a drop-in replacement where speaker-aware downstream features are required.

## Latency and Cost

| Metric | A | B |
|---|---:|---:|
| STT processing time | 390.471 s | 102.598 s |
| STT RTF | 0.2169 | 0.0570 |
| B STT API calls | saved result | 120 transport chunks |
| B estimated STT cost | — | ~$0.135 for 30 minutes |
| B Analyzer p50 / p95 / max | — | 2.805 / 4.230 / 5.187 s |
| B Analyzer estimated cost | — | ~$0.15125 |

The B STT estimate uses the official `gpt-transcribe` list price of $0.0045/min. The transcription response did not expose billable audio units through this adapter, so this is an estimate rather than an invoice value. The Analyzer cost is the existing adapter estimate.

## Artifacts and Reproducibility

Run artifacts are under `evaluation/stt/terminology-run/`:

* `preflight/` — actual STT preflight, normalization, and lexical trace.
* `full/` — Raw STT, Normalization v2, canonical input, Analyzer run, final Graph, final Projection, term trace, and comparison.
* `full/raw/stt-result.json` contains provider output only; no API key or Authorization header is stored.

The added offline runners are `prototype/stt_terminology_run.py` and `prototype/stt_terminology_compare.py`. Existing tests plus terminology adapter tests pass.

## Decision

**B — STT improvementあり + Noise Guard必要**.

Terminology hints materially improved lexical accuracy and improved Map Quality from 3.8 to 4.0, but did not reach 4.3. The remaining Map degradation is now a mixed issue: residual long-term lexical errors plus Analyzer acceptance of additional non-strong Decision / Action state. Noise Guard remains OFF in this run and should be evaluated separately; no Noise Guard or Live Audio work was started here.

Recorded STT terminology improvement is promising, but the pipeline is not yet ready to declare the full Map-quality target met.
