# Analyzer Noise Guard Spike

## Scope and Freeze

This spike uses the saved 120 Normalized Utterances v2 from Terminology Run B. No STT API or Analyzer API was called.

Frozen configuration:

* STT: `gpt-transcribe` + terminology hints
* Analyzer: `gpt-5.6-luna`, reasoning `medium`
* Prompt: `analyzer-prompt-v4`
* Context: v1
* Normalization: v2
* Golden / Evaluation: `golden-v2` / `analyzer-eval-v2`
* Type D: OFF

## Deterministic Guard Policy

The Guard is a narrow input filter, not a semantic Analyzer replacement. It skips only exact normalized matches for:

* Filler-only: `えー`, `えっと`, `あの`, `まあ`
* Backchannel-only: `はい`, `うん`, `なるほど`, `そうですね`, `賛成です`, `了解です`, `わかりました`, `そうしましょう`, `それでいきましょう`, `それもそうですね`
* Very low content: closing acknowledgement such as `お疲れさまでした`

Short semantic utterances are passed. In particular, `やります`, `外します`, `それで進めます`, `今回はなしで`, `金曜までです`, `山田さんで`, `戻りましょう`, and `保留で` are never skipped by length alone. `はい、それで進めましょう` also passes because it contains semantic content.

Skipped input remains in Raw STT, Transcript Evidence, and timestamp trace. Only Analyzer eligibility is changed.

## Guard Audit

| Metric | Result |
|---|---:|
| Total utterances | 120 |
| Passed | 109 |
| Skipped | 11 |
| Skip rate | 9.17% |
| Filler-only | 0 |
| Backchannel-only | 10 |
| Very low content | 1 |
| False skip | 0 |

The 11 skipped sequences are `12, 20, 40, 47, 51, 60, 88, 97, 99, 110, 120`. Sequences 12, 51, and 110 are Proposal + Agreement candidates, but Type D is intentionally deferred; they are recorded as deferred Type D agreements rather than false skips.

The complete per-utterance decision log is in `evaluation/stt/noise-guard/guard-decisions.json`.

## B-Guard-Sim

The first pass was offline event filtering. Events whose source evidence belonged to a skipped utterance were removed from the saved B Event Stream and replayed from the same initial state.

| Metric | B | B-Guard-Sim |
|---|---:|---:|
| Topics | 6 | 6 |
| Final nodes | 95 | 95 |
| Relations | 89 | 89 |
| Open Items | 12 | 12 |
| Candidate Decisions | 8 | 8 |
| Non-Strong Decisions | 6 | 6 |
| Visible cards | 19 | 19 |
| Map Quality | 4.0 | 4.0 |
| Critical Information Recall | 1.0 | 1.0 |
| Events avoided | — | 0 |
| Nodes avoided | — | 0 |
| Relations avoided | — | 0 |

All skipped utterances had no accepted Analyzer events in the saved B run. Therefore the simulation did not change the Graph or Projection. Replay remained deterministic. This is an approximation: a real rerun would also change the Analyzer's Recent Events context after a skip. Since the simulation did not improve any target metric, the requested Simulation Gate stopped the experiment before any real Guard Analyzer run.

## Decision Audit

B's six semantic Non-Strong Decisions were all passed by the Guard:

| Source sequence | Utterance / label | Guard |
|---:|---|---|
| 17 | スマホVを一旦MVP対象外とし… | pass |
| 34 | 名前とDECISION・オープンアイテム… | pass |
| 63 | アナライザーはイベントを返すだけ… | pass |
| 80 | MVPをMATの表示とHuman… | pass |
| 113 | 料金モデルの比較は急がず… | pass |
| 115 | スマホコントローラーは今回は… | pass |

This is expected: these are semantic contributions, not filler or backchannel-only input. The Guard cannot solve the Strong Decision Precision problem without becoming a semantic classifier.

## Action Audit

B detected Actions at sequences `19, 39, 59, 77, 87, 100, 112`; the Golden also expects sequence `119`, which remained a missed Action because its STT text contains the lexical error `アバルーション`. Every Action-bearing utterance passed the Guard. The Guard did not worsen Action Recall.

## Open Item Audit

The 12 B Open Items were classified as useful discussion questions or unresolved work. The offline audit found:

* Useful: 12
* Noise-derived: 0
* Duplicate: 0
* Resolved: 0

Consequently, Open Item reduction cannot be attributed to this Guard. The B count of 12 already exists before filtering.

## Safety and Cost

| Metric | Result |
|---|---:|
| Automatic Confirmation | 0 |
| Invented Owner | 0 |
| Invented Due | 0 |
| Critical Decision Reversal | 0 |
| Analyzer calls, theoretical | 120 → 109 |
| Calls avoided | 11 (9.17%) |
| Estimated Analyzer cost | $0.15125 → $0.13738 |
| Estimated saving | ~$0.01386 |
| Guard p50 latency | 0.00475 ms / utterance |
| Guard max latency | 0.01000 ms / utterance |

Cost is a linear estimate from the saved B run; no Analyzer API call was made for C. Raw Evidence is preserved.

## Clean / A / B / C Comparison

| Branch | Map Quality | Nodes | Relations | Open Items | Non-Strong Decisions |
|---|---:|---:|---:|---:|---:|
| Clean | 4.8 | 90 | 85 | 13 | — |
| A: diarize | 3.8 | 94 | 90 | 16 | 3 |
| B: terminology | 4.0 | 95 | 89 | 12 | 6 |
| C: B + Guard | not run; simulation 4.0 | 95 | 89 | 12 | 6 |

Topic Precision / Recall remains `1.0 / 1.0` for B and the simulation. Projection Critical Information Recall remains `1.0`, but Decision Precision, Action Recall, and label quality remain below the desired product threshold.

## Conclusion

**C — Guard Not Useful** for the current blocker.

The deterministic Guard is safe and inexpensive, but it removes only utterances that already produced no Events. It reduces theoretical calls by 9.17% without improving Map Quality, Non-Strong Decisions, Open Items, Nodes, or Relations. The remaining problem is Analyzer semantic classification and residual STT lexical errors, not filler/backchannel noise.

Prompt v5 or STT-aware Analyzer context remains a future candidate, but Prompt v5 was not created in this spike. Live Audio is **not ready** because Map Quality remains 4.0 and the Guard did not reach the required recovery target.
