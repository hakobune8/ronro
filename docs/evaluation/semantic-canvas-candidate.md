# Semantic Canvas / Auto Camera candidate (Issue #21)

Status: **development hypothesis, not deployed or Human-accepted**.

## Implemented slice

- `semantic_canvas` is a Presentation projection of the accepted Canonical Graph and Event History. Node coordinates do not enter the Canonical contract. Live and ended Shared View use this same coordinate system; only the camera and semantic detail level change.
- Creation-Evidence-linked provenance places a new point below its discussion source; `supports` and `opposes` place argument points to either side. An unlinked point receives a separate world region, without claiming it is a verified independent Root. A Human-declared independent point is distinguished in projection metadata.
- During an active meeting, the deterministic latest meaningful Node is focal. A Topic Return may move focus back to an existing Node without creating a semantic edge or a copy. At most five local points receive non-Canonical short display labels where valid, with distant context shown quietly. The **focal Node's** Canonical text appears as a passive, centered subtitle at the bottom of the same Canvas, visually distinct from graph cards; missing/unsafe display labels fall back to Canonical text. The subtitle shows up to five lines and explicitly says 「続きあり」 when longer. This display limit never changes the stored Canonical text.
- At session end, the camera widens over the same coordinates. Far points become topology marks; selected branch/outcome labels remain readable where space permits. The generic 「この周辺N件」 marker is omitted because the number does not explain the discussion. Semantic lines remain distinct from chronological movement. The Shared View has no pan, zoom, pagination, or click controls.
- Session-local placement state prevents a late Relation or Human correction from moving a point already displayed. Connectors and Root classification can change without relocation.
- The Live camera centers the focal Node horizontally. Its vertical target keeps the focal Node in the central viewing region while preserving room for provenance parents above and the five-line subtitle below; exact geometric centering would clip the parent in the R4 chain at readable scale.
- Live and ended states keep the same 16:9 Canvas extent. Wider spatial placement reserves a readable gap for relation labels; the generic lower-left Final note was removed. The only remaining Final note is a processing-incomplete warning.

## Verification

- Unit tests include R4 Decision structure, late Relation and removal, Topic Return, deterministic reprojection, and 5/15/30/60/100/300-point placement.
- `tests/canvas_browser_qa.cjs` renders 1920×1080 via the local prototype server. It checks Live/Final scroll, primary-card clipping and capacity at 5/15/30/60/100/300 disconnected points, plus 300 points across ten branching regions. The R4 controlled case checks identical Live/Final Canvas width, readable relation labels, short focal title, and Canonical focal overlay. Screenshots are private `/tmp` QA outputs, not repository artifacts.
- The disconnected-point stress case intentionally tests a worst-case sparse Graph; it is not a forecast of a 60-minute meeting. A 100-Node ceiling is **not** assumed.

## Open acceptance gaps

1. At 300 points, Final semantic zoom is an overview of topology and a few named regions, not a readable map of every point. The first version must be judged against real meeting structure, not only synthetic count. Do not call 60-minute capacity accepted yet.
2. Placement state currently lives in the in-process Projection object. Replay from accepted Events is deterministic when the same Projection state is retained; restoring a long session from the final Graph alone can choose a different placement after a late same-Evidence Relation. Persist or reconstruct placement state before a production rollout.
3. The passive subtitle deliberately indicates when Canonical text exceeds five readable lines. A post-meeting Web detail surface that exposes the complete text has not yet been connected to this candidate.
4. The existing Pilot Guide still describes the deployed Focused Flow and state rail. Do not replace its screenshots or instructions until Human Review approves this candidate and deployment is planned.
5. Physical 3–5m viewing, correction-in-place, and Live→Final visual transition need Human review. Synthetic QA establishes no-scroll/clipping only.

No production deployment, Analyzer change, Canonical schema change, audio rerun, or Pilot Guide update is part of this development slice.
