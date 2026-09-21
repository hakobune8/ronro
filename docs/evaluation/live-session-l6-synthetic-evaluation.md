# Live Evaluation Session l6-synthetic-evaluation

## Session

- Started: 2026-09-20T11:18:02.983Z
- Ended: 2026-09-20T11:18:03.016Z
- Duration (s): 0.033
- Participants: 2
- Theme: Discussion Map AI Facilitatorを社内会議で使う場合、必要な機能
- STT: OpenAI / gpt-transcribe
- Analyzer: gpt-5.6-luna / medium
- Prompt: analyzer-prompt-v4
- Configuration: live-eval-v1
- Raw audio: not_persisted

## System Metrics

- Final utterances: 10
- Partial transcripts: 0
- STT failures: 0
- Analyzer calls / failures: 10 / 0
- Queue max depth: 4
- Queue wait p50 / p95 / max: 0.002384 / 0.009366 / 0.009366 sec
- Analyzer p50 / p95 / max: 3.1e-05 / 5.3e-05 / 5.3e-05 sec
- E2E p50 / p95 / max: 0.007305 / 0.01701 / 0.01701 sec
- Graph updates / Map renders: 10 / 6
- Final graph / rendered revision: 12 / 12

## Discussion Metrics

- topic_count: 1
- topic_transitions: 0
- candidate_decisions: 1
- confirmed_decisions: 0
- revoked_decisions: 0
- open_items: 2
- resolved_open_items: 0
- actions: 1
- parking_items: 0

## Human Corrections

- Counts: {"confirm_decision": 0, "merge": 0, "parking": 0, "rename": 0, "reopen_open_item": 0, "resolve_open_item": 0, "restore": 0, "revoke_decision": 0, "set_current_topic": 0, "update_action": 0}
- Correction rate: 0.0
- Candidate confirmation rate: 0.0

## Observer Markers

- Marker count: 3

## Map Quality

- clarity: 4
- decision_safety: 5
- density: 4
- stability: 4
- topic_coherence: 4
- usefulness: 4

## Participant Feedback

- current_topic: 4
- decision_open_item_usefulness: 4
- distraction: 2
- free_comment: Synthetic Evaluation artifact generation succeeded.
- usefulness: 4
- would_use_again: 4

## Post-session Golden Comparison

- Critical information recall: 1.0
- main_topics recall: 1.0
- strong_decisions recall: 1.0
- important_open_items recall: 1.0
- actions recall: 1.0

## Success Criteria

- pipeline_crash: 0
- graph_corruption: 0
- automatic_confirmation: 0
- evidence_loss: 0
- critical_information_recall: 1.0
- map_quality: 4.1667
- median_e2e_seconds: 0.007305
- p95_e2e_seconds: 0.01701
- queue_runaway: 0

## Failure / Issues

- Observer wrong item: 
- Observer missing item: 

## Recommended Changes

Use observer markers, post-session golden, and latency artifacts to decide the next scoped change. This harness does not change Analyzer behavior.
