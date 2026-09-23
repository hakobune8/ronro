# Kubernetes Pilot Day Checklist

This checklist is for the deployment smoke test and Pilot preparation. Checking it does not start Pilot #1.

## Cluster and image

- [ ] Correct Kubernetes context selected and `kubectl auth can-i` succeeds.
- [ ] Registry host and image tag recorded.
- [ ] Image digest recorded.
- [ ] Previous Green image tag recorded for rollback.
- [ ] Private registry pull Secret attached if required.
- [ ] IngressClass confirmed.
- [ ] StorageClass confirmed.
- [ ] Network egress to OpenAI HTTPS/WSS confirmed.

## Resources

- [ ] Namespace `discussion-map-pilot` exists.
- [ ] API Secret `discussion-map-openai` created out-of-band.
- [ ] TLS Secret provisioned for the exact Pilot hostname.
- [ ] ConfigMap shows candidate configuration `semantic-graph-rc1` and Analyzer output schema `v3`.
- [ ] PVC `discussion-map-pilot-evaluation` is Bound.
- [ ] Deployment has `replicas=1` and `strategy=Recreate`.
- [ ] Pod is Ready.
- [ ] Liveness `/healthz` is 200.
- [ ] Readiness `/readyz` is 200.
- [ ] Service has HTTP and WebSocket endpoints.
- [ ] Ingress exposes the intended host.

## HTTPS / Safari

- [ ] Shared Display and Controller devices are connected to the NetBird Private Network.
- [ ] A device outside NetBird cannot reach `ronro.hakobune8.com`.
- [ ] Pilot QR, if shown, contains only `https://ronro.hakobune8.com/session` and no secret or credential.
- [ ] One active Controller is assigned for the Session; a second Controller cannot take Start / End / Audio control.
- [ ] UI loads over valid HTTPS.
- [ ] Certificate hostname matches.
- [ ] Smartphone Controller remains in the foreground and unlocked during the Pilot.
- [ ] Safari microphone permission is granted only after Start.
- [ ] Microphone active indicator is visible.
- [ ] AudioWorklet loads.
- [ ] WSS URL is same-origin `/live`.
- [ ] Ingress WebSocket timeout is at least the 10–15 minute Pilot window.
- [ ] Shared display is ready.
- [ ] Room and external microphone are ready.
- [ ] Consent text is shown.
- [ ] Raw Audio default is not persisted.

## Kubernetes three-case smoke

- [ ] Topic utterance finalizes and updates the 論点図.
- [ ] Candidate Decision is visible as `candidate` / pending, never confirmed.
- [ ] Action is visible.
- [ ] Owner and due date are not invented.
- [ ] Evidence trace exists for all three cases.
- [ ] Evidence loss is 0.
- [ ] Graph corruption is 0.
- [ ] Automatic Confirmation is 0.
- [ ] E2E values are recorded and within the Prototype budget.
- [ ] Continuous smoke session reaches `finalizing` then `ended`.
- [ ] Queue is drained and rendered revision equals graph revision.

## Artifact persistence

- [ ] One non-Pilot Evaluation artifact is written.
- [ ] Artifact path and checksum are recorded.
- [ ] Pod restart test completed between sessions.
- [ ] Artifact remains on the PVC after restart.
- [ ] Evaluation reports are under the PVC-backed report path.

## Pilot readiness

- [ ] `git commit` SHA recorded.
- [ ] Image tag/digest recorded.
- [ ] Configuration version `semantic-graph-rc1` recorded.
- [ ] Prompt `analyzer-prompt-v9-semantic-edge-balance` recorded.
- [ ] STT `gpt-transcribe` recorded.
- [ ] Analyzer `gpt-5.6-luna` / reasoning `medium` recorded.
- [ ] No Pilot has started during smoke testing.
- [ ] Facilitator, observer, 2–3 participants, and 10–15 minute scope confirmed separately.
- [ ] Abort conditions reviewed: Graph corruption, false confirmed state, evidence loss, queue runaway, persistent >20s latency, privacy issue.
