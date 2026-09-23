# Shared View display_label (local implementation; quality gate NOT passed)

`display_label` is an optional, replaceable **non-Canonical** representation.
Canonical Node `label`, Evidence and Events remain authoritative. It never
participates in identity, deduplication, relations, Topic association or state
lifecycles. Stable Recency, slots, overflow and Rail selection are unchanged.

## Contract and ownership

Analyzer output **v3** extends v2 node intents with `display_label: string|null`.
The strict provider schema requires the nullable key; local intake tolerates
missing/malformed presentation values without rejecting otherwise valid semantic
intents. v1/v2 schemas remain unchanged. The semantic v4/v5 prompt builder is
unchanged; v3 adds the versioned `display-label-v1` presentation instruction to
the **same** inference. No summarization pass or render-time model call exists.
Strict nullable-key treatment follows the
[official Structured Outputs contract](https://developers.openai.com/api/docs/guides/structured-outputs).

Choose persistence option **B: associated non-canonical projection metadata**.
`CandidateEvent.presentation` is excluded from `to_event()`. Only after the
corresponding Canonical node event is accepted is its validated hint written to
`ReplayResult.presentation`, keyed by Node ID. Each record binds event ID,
accepted sequence, Node content hash and policy version. First accepted write
wins. Queue transaction rejection cannot install its staged hints.

`map.presentation` carries this sidecar and `map.display_labels` carries derived
text/fallback diagnostics. Existing evaluation snapshot/projection-final JSON
persistence therefore retains the accepted hints. Rebuild with
`ReplayRunner.replay_events(..., presentation=saved_projection['presentation'])`
then `map_projection(state, events, layout, result.presentation)`; there is no
new inference. Old artifacts without sidecars fall back to Canonical text.
The runtime's existing in-memory session durability is unchanged: this does not
add a database or promise session recovery after process loss without an export.

Changed Node text/Action attributes invalidate the content hash. Human rename
therefore cannot leave stale machine text displayed. Confirming an unchanged
Decision preserves its short label; the Canonical status determines the Rail.
The sidecar is not fed back into Analyzer context or Graph materialization.

## Validation and fallback

Trim; reject empty, non-string, control characters, markup, ellipsis, generic
headings and values longer than 72 characters. This is a safety ceiling, not
a line-count guarantee. The prompt targets about 1–3 lines using the approved
typography and may use null if safe shortening is impossible.

Conservative guards reject new numerical tokens and recognizable unsupported
owner/deadline expressions. Action owner/due are rendered structurally from
Canonical attributes, never inferred from label prose. Dates/names in generated
text are not a source of execution metadata.

Selected certainty/negation/necessity markers and selected temporal-state forms
are retained lexically or the hint is rejected. In particular, already proposed,
will propose, checked, unchecked, planned and in-progress are not interchangeable.
The prompt also requests preservation of subject, core proposition, essential
technical terms and material numbers/comparisons.

**These rules are not an entailment or Japanese temporal-logic validator.**
Equivalent safe rephrasing can be rejected; unrecognized semantic mistakes can
still pass. Important-number omission and subject loss require semantic review.
Do not equate a valid schema/length with meaning preservation. Missing, invalid,
stale or unknown-version metadata always shows full Canonical text, never hides
a Node. Extremely long safe fallbacks can still exceed the display budget;
they are never truncated. See the bounded fit policy below.

Control's existing Developer details show Canonical label, accepted hint,
effective text and fallback reason. No extra content logging is added. Shared
View shows only participant content and explicit Action owner/due.

## Rollout gate

`REAL_ANALYZER_OUTPUT_SCHEMA_VERSION=v3` explicitly enables the candidate in the
Live Analyzer factory. **Default remains v2**, because initial real-generation
evaluation failed its meaning/readability acceptance gate. The STT item-scoped
candidate is independent and unchanged; only its completed snapshot's map call
receives presentation metadata.

No deployment/packaging/push occurred in this task. Prepared order after label
quality approval: full suite and public audit → unique candidate CI publish →
digest-pinned deploy (retain rollback digest) → independent short natural/long/
near-boundary STT smoke → Shared View hint/fallback/owner-due smoke → T2 retry
readiness review. Keep `server_vad_bounded`/30 seconds and generic STT context
unchanged. A short smoke must check item correlation, no duplicate Evidence,
clean Drain and no lost newer audio independently of display-label quality.
T2 retry, RFC-0006 completion, T3, Pilot and final release remain unauthorized.

## Five-line fit and presentation policy v2 follow-up

Current-discussion cards measure actual rendered text, not character count.
They try 40, 38, then 36px, retaining the largest size that fits at most five
lines and the available card height/width. Only at 36px, vertical padding may
reduce to 12px. Resize and font loading trigger remeasurement. No ellipsis,
clipping or sub-36px text is introduced. Extreme content remains visible and
is marked `data-text-fit=unresolved` for diagnostics; this is not a universal
five-line guarantee for arbitrary Canonical text. Rail typography is unchanged.

`display-label-policy-v2` strengthens same-inference instructions for subject,
tense/aspect, negation, comparison direction and scope. Conservative lexical
guards reject selected state changes, missing scope and comparators. Safe
paraphrases can also fall back; these checks do not prove semantic equivalence.
Newline whitespace is normalized. Persisted hints carry their validation policy;
legacy hints retain their previous validator to avoid changing historical replay.
The sidecar storage version and Canonical schema remain unchanged.

Generation remains opt-in v3, with v2 the default. Controlled fixed-Canonical
generation isolates display quality but does not certify normal Analyzer
extraction. No extra inference is added to the production path.
