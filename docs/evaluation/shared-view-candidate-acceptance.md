# Shared View Candidate Acceptance

Status: **Human-approved unnumbered presentation; candidate deployment authorized.**

The approved presentation uses deterministic Stable Recency with at most six
ordinary discussion cards, fixed slots for retained cards, and non-interactive
`ほかN件` overflow. Independent Persistent Rails distinguish 決定候補, 確定事項,
未解決事項 and 次の対応. Each nonempty category shows one item and its overflow.

The latest/current Topic is the leftmost item in the actual Topic-flow history;
older transitions appear to its right with left-pointing arrows. The latest
four entries preserve Topic returns. Single-Topic and generic bucket headings
do not dominate the view. Active-session branding and usage guidance are hidden.

Ordinary text remains 40px, persistent text 30px, and Topic-flow text 32px in
the 1920×1080 view. Rail width and text wrapping were reviewed without changing
canonical labels. A temporary card-number experiment was withdrawn. Fixed item
references and spoken recall remain deferred in [RFC-0006](../rfc/0006-discussion-item-references-and-recall.md).

## Verification

- Saved T1 graph replay (no STT/Analyzer rerun) matches approved card IDs/slots
  at revisions 32/57/72, with overflow 9/23/31.
- Fresh and incremental replay yield identical projection; input is unchanged.
- Actual Chromium screenshots at 1920×1080 cover T1 5/10/15 minutes, persistent
  fixture densities 1/3/9, and a synthetic combined Topic-return/Rail case.
- The reviewed captures show no scrolling, measured overflow or card overlap.
- Related tests cover lifecycle filtering, stable slots, exact overflow,
  deterministic reset/replay, four Rail categories, escaping, current-left
  return highlighting, no reference numbers, Idle entry and retained End state.

Screenshots and transcript-derived artifacts remain private. This public note
contains no source media, full transcript, device identifiers or cluster details.

## Human gate and deployment scope

Human explicitly approved the current unnumbered screen for deployment.
This is **not** a claim that physical 3–5m viewing was measured; that remains
unverified. The longer labels can still require more than a five-second glance.

Deployment is a candidate update through the existing container-publish CI,
with immutable digest pinning and the previous deployed digest retained for
rollback. Existing single-replica Recreate topology, storage, secrets, network
boundary and STT configuration must remain unchanged. Verify no active session
before rollout because runtime state is in memory. No main merge, final release
tag, GitHub Release, Live Pilot or T2/T3 execution is included.
