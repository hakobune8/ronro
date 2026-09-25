# Semantic Canvas motion review (synthetic)

This review uses synthetic Japanese meeting content and the actual Shared View browser renderer. It tests presentation transitions, not STT or Analyzer quality. No real meeting recording, transcript, or provider output is included.

The 21 scenes cover: empty Canvas; issue and response; supports and opposes; sibling options; Open Item; an independently confirmed discussion entry; branch return; late relation; relation correction without relocation; Candidate Decision and explicit Human confirmation; Action; long Canonical subtitle; 15, 30, 60, and 100 Nodes; and meeting-end zoom-out. Node and subtitle timestamps are synthetic graph-update times, shown in Japan time. The expanded 15–100 Node cases are load/semantic-zoom fixtures, not realistic generated meeting semantics.

Regenerate locally from the repository root:

```sh
PYTHONPATH=. .venv/bin/python tests/canvas_motion_fixture.py > tmp/canvas-motion-scenes.json
.venv/bin/python -m prototype.server --host 127.0.0.1 --port 18080 --live-ws-port 18765
# In another terminal, with Playwright available in NODE_PATH:
node tests/canvas_motion_video.cjs
```

The generated 1920×1080 MP4 is `tmp/ronro-semantic-canvas-motion.mp4`; it is intentionally ignored by Git. The frame images are under `tmp/canvas-motion/`, including a lossless `final-review.png` for inspecting relation captions without JPEG compression. The browser renderer checks focus, the five-Node Live limit, timestamps, scrolling, and Final markers. Unit tests check event progression, stable placement through return/correction, and explicit Candidate-to-Confirmed transition.

The faded peripheral layer sits behind primary Nodes, so it may share screen space without obscuring primary text. The live provenance caption is 「ここから展開」 to describe discussion development without suggesting physical causality. At meeting end, independently confirmed discussion entries receive a short 「別の話題」 hint; nodes whose discussion-origin relation is still unconfirmed have only subdued visual treatment, without a participant-facing 「つながりは未確認」 label. Representative branches and Decision/Open Item/Action callouts remain on the same Canvas. To avoid overlap, callouts may move slightly; final semantic lines connect the displayed callouts directly rather than ending at the invisible original node boxes. Only relations whose two endpoints are shown receive a line. Final lines are continuous; supports/opposes have an opaque, bordered Japanese label over the line as well as distinct colors. The edge label 「案への懸念」 describes opposition to an Option, whereas the Node badge 「懸念」 identifies the Node's type; neither label is inferred from the other's presence. For an opposition target that is not an Option, use the broader 「反対意見」 rather than incorrectly calling it an Option. The previous faint dot-to-callout leaders and detached zoomed-out world edges are removed. The video contains no test-only text overlay. The local browser QA also checks fixed Node width/type size during focus changes and counts for currently active Nodes by participant-facing category. The video does not establish physical 3–5 m readability or real Analyzer behavior.
