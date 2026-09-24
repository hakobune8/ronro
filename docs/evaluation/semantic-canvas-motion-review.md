# Semantic Canvas motion review (synthetic)

This review uses synthetic Japanese meeting content and the actual Shared View browser renderer. It tests presentation transitions, not STT or Analyzer quality. No real meeting recording, transcript, or provider output is included.

The 21 scenes cover: empty Canvas; issue and response; supports and opposes; sibling options; Open Item; independent discussion branch; branch return; late relation; relation correction without relocation; Candidate Decision and explicit Human confirmation; Action; long Canonical subtitle; 15, 30, 60, and 100 Nodes; and meeting-end zoom-out. Node and subtitle timestamps are synthetic graph-update times, shown in Japan time. The expanded 15–100 Node cases are load/semantic-zoom fixtures, not realistic generated meeting semantics.

Regenerate locally from the repository root:

```sh
PYTHONPATH=. .venv/bin/python tests/canvas_motion_fixture.py > tmp/canvas-motion-scenes.json
.venv/bin/python -m prototype.server --host 127.0.0.1 --port 18080 --live-ws-port 18765
# In another terminal, with Playwright available in NODE_PATH:
node tests/canvas_motion_video.cjs
```

The generated 1920×1080 MP4 is `tmp/ronro-semantic-canvas-motion.mp4`; it is intentionally ignored by Git. The frame images are under `tmp/canvas-motion/`. The browser renderer checks focus, the five-Node Live limit, timestamps, scrolling, and Final markers. Unit tests check event progression, stable placement through return/correction, and explicit Candidate-to-Confirmed transition.

Observed limitation: in the long-Canonical scene, a faded peripheral label overlaps an active Canvas Node near the top. This is a Presentation collision, not a Canonical-data issue. The video retains it for honest review; peripheral placement should be adjusted before adopting this UI. The video does not establish physical 3–5 m readability or real Analyzer behavior.
