# Pilot continuity and discussion-flow candidate

Status: local candidate only. Production has not been updated by this change.

## Why

In a two-person pilot rehearsal, an unexpected audio failure ended the Session,
and a one-Topic conversation appeared to leave both the center and the upper
"話の流れ" unchanged. A meeting must not require participants to stop talking
because the transcription connection needs to recover.

## Capture continuity

- A recoverable Provider, item-timeout, browser WebSocket, or capture-setup
  interruption leaves the continuous Session and existing Graph active.
- The interruption is logged with a code, time, last accepted frame, locally
  pending duration, and uncertainty about possible missed Evidence. No raw
  audio is logged. The separate, consent-gated pilot recording path may retain
  accepted PCM frames for seven days when enabled; this is not Canonical
  Evidence and cannot recover frames never received. The UI shows reconnection instead of claiming
  to be listening. The same controller can reconnect to a fresh Provider
  connection and continue the same Session.
- Browser framing resumes from the last accepted frame sequence and audio end
  time. Provider-local item ranges are translated to Session-relative time.
- Explicit End while disconnected still drains the Analyzer queue. An error
  *during* intentional finalization remains an incomplete-processing failure.
- A possible Evidence gap is never represented as a completed Final and must
  not be reported as Evidence loss = 0. The duration of speech missed while
  disconnected cannot be measured from local PCM.

This is not process-restart recovery: the Live Session and Graph are still
in-memory. A Pod restart during a meeting remains a separate pilot risk.

## Shared View responsiveness

- The upper "大きな話題" line remains the actual Canonical Topic focus history.
  It is not incremented on every utterance.
- The "直前の話" line uses recent within-Topic discussion Nodes in Event order,
  including a newly created Node not yet associated with a Topic. It is
  chronological presentation, not an inferred semantic Relation.
- The current focal Node remains in the center. A label already visible there
  is excluded from the top and from redundant latest detail. A prior label
  shown at the top is excluded from the lower sparse-Graph list. Full
  Canonical detail still appears at the right when it adds information.
- If the Analyzer emits no Node or Topic change, the discussion-flow labels
  cannot assert a semantic update. This remains a validation point for an
  intentional topic shift in a real conversation.

## Local evidence and remaining gate

Unit/DOM regression includes Provider interruption → same-Session reconnect →
next Final, a longer empty VAD item, disconnected explicit End, item-range
offset, within-Topic flow, and duplicate-label suppression. The local 1920×1080
browser rendering has no page scroll or flow-row overflow on the synthetic
basic-discussion fixture. This does not replace a live two-person smoke test.

Before Pilot: deploy only after a candidate review, then verify on the exact
running digest: BGM/quiet intervals; a deliberately interrupted connection;
recovery with preserved Graph and correct frame/time continuity; an intentional
topic change and return; no duplicated prominent labels; and explicit End
draining with possible Evidence gaps clearly reported.
