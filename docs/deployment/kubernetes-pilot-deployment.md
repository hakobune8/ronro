# Kubernetes Pilot Deployment

Status: **Pilot candidate deployed; this page describes the repository templates and repeatable checks, not approval to start a Pilot.** The deployment and acceptance history is recorded in [Minimal Semantic Graph Hypothesis](../evaluation/minimal-semantic-graph-hypothesis.md).

This deployment packages the already-green Limited Live Prototype for Pilot #1. It does not start Pilot #1 and it does not change Analyzer, STT, Event Store, Materializer, Projection, or Session Drain behavior.

## Architecture

```text
Safari
  │ HTTPS / WSS
  ▼
Edge Ingress (SSLHQ/staips-infra)
  ├─ /      → application NodePort 30100 → Service:http:8000
  └─ /live  → application NodePort 30101 → Service:websocket:8765
                    │
                    ▼
              RONRO Pod (existing Kubernetes resource names retained)
              ├─ HTTP API / static UI
              ├─ Audio WebSocket
              ├─ gpt-transcribe Realtime client
              ├─ in-memory FIFO + one Analyzer worker
              ├─ Event Store / Materializer / Projection
              └─ Evaluation Harness → PVC
```

The Pod is intentionally single-replica. Event Store, Live Session state, FIFO state, and Analyzer Worker state are in memory.

## Repository layout

```text
Dockerfile
.dockerignore
deploy/kubernetes/
  base/
    configmap.yaml
    deployment.yaml
    ingress.yaml
    kustomization.yaml
    namespace.yaml
    pvc.yaml
    secret.example.yaml
    service.yaml
  pilot/
    kustomization.yaml
docs/deployment/
  kubernetes-pilot-deployment.md
  kubernetes-pilot-checklist.md
```

## Prerequisites

- Kubernetes access with permission to create the `ronro-pilot` namespace, Deployment, Service, ConfigMap, and PVC. The edge-cluster Ingress is managed by `SSLHQ/staips-infra`.
- A reachable container registry and a cluster pull path for the image.
- For the deployed edge topology, access to the separately managed Traefik Ingress in `SSLHQ/staips-infra`. The standalone template uses `ingress-nginx` annotations and `ingressClassName: nginx` instead.
- A valid DNS name and TLS configuration in the edge cluster. Self-signed TLS is not the Safari Pilot default.
- A Kubernetes Secret containing `OPENAI_API_KEY`, created out-of-band.
- StorageClass support for a 1Gi `ReadWriteOnce` PVC.

The `ghcr-edge` overlay pins the current candidate image by digest. Verify the
running digest and the Pilot-specific Human gates anew before use; an earlier
smoke test alone is not Pilot approval. The application-cluster resources now use
`ronro-pilot`; the former `discussion-map-pilot` resources were migration sources.

## Pilot candidate configuration

The current candidate ConfigMap identifies `semantic-graph-rc4` and supplies:

- STT: `gpt-transcribe`, Japanese, terminology hints enabled
- Analyzer: `gpt-5.6-luna`, reasoning `medium`
- Prompt: `analyzer-prompt-v10-action-time-horizon`, output schema `v3`
- Context: `v1`
- Normalization: `v2`
- Type D: `OFF`
- Presentation Compaction: `ON`
- Open Item Lifecycle: `ON`
- Render coalescing: 2 seconds
- Drain timeout: 30 seconds

`EVALUATION_ROOT` and `EVALUATION_REPORT_ROOT` point to the mounted PVC. The application copies this runtime configuration into derived Evaluation metadata; it never stores the API key there.

## Build and push

The image contains the Python runtime, runtime dependencies, `prototype/`, schemas, static UI / AudioWorklet, and the Evaluation fixture resources needed by the application. `.env`, tests, docs, raw audio, and historical STT chunks are excluded.

Set the registry outside the repository. Do not put credentials in a manifest or Dockerfile.

```sh
export REGISTRY_HOST=registry.example.com
export IMAGE_NAME="$REGISTRY_HOST/ronro"
export IMAGE_TAG=pilot-001
export VCS_REF=unknown
export BUILD_DATE="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

docker build \
  --build-arg APP_VERSION="$IMAGE_TAG" \
  --build-arg VCS_REF="$VCS_REF" \
  --build-arg BUILD_DATE="$BUILD_DATE" \
  -t "$IMAGE_NAME:$IMAGE_TAG" .
docker push "$IMAGE_NAME:$IMAGE_TAG"
```

If the target environment uses `nerdctl` or another approved builder, use the equivalent commands. The pilot overlay image name must be changed from `registry.example.invalid/...` before apply.

The image carries OCI labels for application version, git revision, and build timestamp.

## Secret handling

`deploy/kubernetes/base/secret.example.yaml` is a template only and is intentionally not included in Kustomize resources. Create the Secret out-of-band:

```sh
kubectl -n ronro-pilot create secret generic ronro-openai \
  --from-literal=OPENAI_API_KEY="$OPENAI_API_KEY"
```

The API key is injected only into the backend container through `envFrom`. It is not in ConfigMap, image, browser JavaScript, repository, or application logs. For a private registry, create a separate `docker-registry` Secret and attach it with an environment-specific Kustomize patch; do not place registry credentials in this repository.

## ConfigMap

`deploy/kubernetes/base/configmap.yaml` contains non-secret runtime configuration. Model, prompt, terminology, language, timeout, configuration version, PVC paths, and presentation settings are visible by design.

The Realtime STT prompt is a short generic Japanese meeting context. It is an
audio-recognition hint only: it must not contain a demo scenario, expected
transcript, analyzer semantics, or evaluation answers. `OPENAI_REALTIME_KEYWORDS`
is reserved for a small terminology hint list; the Pilot candidate uses `論路`
as the only product terminology hint.

The generic code default remains `OPENAI_REALTIME_FINALIZATION_MODE=none` for
compatibility. The validated Pilot candidate explicitly selects
`OPENAI_REALTIME_FINALIZATION_MODE=server_vad_bounded` and
`OPENAI_REALTIME_PERIODIC_COMMIT_SECONDS=30`. Provider `server_vad` handles
normal turns; the bound is only a safety fallback for a long unfinalized turn.
The current candidate measures the bound from the first meaningful frame
in the uncommitted range, excluding leading silence but including subsequent
pauses. Raw pending PCM duration can therefore exceed 30 seconds during silent
preparation without requiring a commit. This accounting is part of the candidate
image; it is not an environment override.
Keep the `none` mode available for non-Pilot usage and experiments.

`LIVE_STT_EMPTY_VAD_POLICY` defaults to `warn_short_no_delta`. The `strict`
setting remains available. A known
automatic Server VAD item of at most 3 seconds with no transcription deltas
and no explicit commit can be reported as `possible_untranscribed_audio`
without ending capture. This is **not** proof of silence. The facilitator's
session view shows the accumulated warning; the runtime counts possible
Evidence gaps and cannot assert Evidence loss zero when that count is nonzero. Longer,
unknown-range, partially recognized, and explicit-commit empty completions
remain fatal. Pilot readiness still requires a separate safety review of
the possible gaps and the facilitator's response.

## Storage

The PVC `ronro-pilot-evaluation` requests 1Gi with `ReadWriteOnce`. It is used for:

```text
/data/evaluation/live/sessions/
/data/evaluation/live/reports/
```

Raw audio is not persisted by default. If an Evaluation session has explicit consent for raw audio, it may be stored as an Evaluation artifact under the existing application policy; consent is not granted by the manifest.

## Deployment strategy and resources

- `replicas: 1`
- `strategy.type: Recreate` to avoid a temporary second in-memory session
- CPU request/limit: `250m` / `1`
- Memory request/limit: `512Mi` / `1Gi`
- `terminationGracePeriodSeconds: 60`
- non-root UID/GID `10001`
- read-only root filesystem, writable `/tmp` and Evaluation PVC only

No autoscaling, Redis, external Event Store, production database, service mesh, or distributed worker is included.

## HTTPS / WSS / Ingress

The Service exposes two named ports. In the deployed `ghcr-edge` topology,
`SSLHQ/staips-infra` owns the edge-cluster Ingress and its TLS Secret; it sends
`/` and HTTP/API paths to NodePort 30100 and `/live` to NodePort 30101. The
application-cluster `ghcr-edge` overlay does **not** create another Ingress.
The browser receives a same-origin WebSocket URL. Behind an Ingress, the
application uses `X-Forwarded-Proto` and `X-Forwarded-Host` to return
`wss://<pilot-host>/live`; local direct HTTP development keeps its two-port
`ws://` behavior.

The standalone pilot template includes ingress-nginx timeouts of 1200 seconds.
For `ghcr-edge`, confirm the separate Traefik edge-cluster configuration before
use. HTTPS is required for Safari microphone access.

Before apply, replace these placeholders in the pilot overlay or environment-specific patch:

- `registry.example.invalid/ronro` (base-manifest image placeholder; the `ghcr-edge` overlay maps it to `ghcr.io/hakobune8/ronro`)
- `ronro-pilot.example.invalid` and `ronro-pilot-tls` (standalone pilot overlay only)
- `nginx` if the cluster uses another IngressClass

The `ghcr-edge` overlay deliberately omits the application-cluster Ingress. The
public `ronro.hakobune8.com` Ingress and its TLS Secret are owned in the edge
cluster by `SSLHQ/staips-infra`; its EndpointSlice forwards to application
NodePorts **30100/30101**. Preserve those ports during future rollouts. Do not
make the Ingress anonymous on the public Internet; retain the NetBird boundary.

## Build manifest and deploy

Render first:

```sh
kubectl kustomize deploy/kubernetes/pilot/ghcr-edge
```

Create the API Secret in `ronro-pilot`; ensure the edge-cluster Ingress and TLS
are ready separately before applying the workload. Then apply:

```sh
kubectl apply -k deploy/kubernetes/pilot/ghcr-edge
kubectl -n ronro-pilot rollout status deployment/ronro-pilot --timeout=120s
```

The apply must be performed only after the image, edge host/TLS, StorageClass,
and any private-registry pull Secret are set for the target cluster.

## Verify

```sh
kubectl -n ronro-pilot get pods,svc,pvc
kubectl -n ronro-pilot get endpoints ronro-pilot
kubectl -n ronro-pilot describe pod -l app.kubernetes.io/name=ronro
kubectl -n ronro-pilot logs deployment/ronro-pilot --tail=100
```

Verify all of the following before Safari:

- Pod is Ready.
- PVC is Bound.
- Service has endpoints for both ports.
- The edge-cluster Ingress has the expected host and address.
- The edge TLS certificate is valid for the host.
- `GET /healthz` is 200.
- `GET /readyz` is 200 without making an OpenAI request.
- Backend egress to OpenAI HTTPS/WSS is permitted.

## Kubernetes smoke test

This is a deployment smoke test, not Live Pilot #1. Run the Safari three-case pre-flight through the HTTPS host after rollout:

1. Load the UI over HTTPS.
2. Confirm AudioWorklet loads.
3. Grant microphone permission explicitly.
4. Start one-utterance mode and confirm WSS `/live`.
5. Run the Topic utterance.
6. Run the Candidate Decision utterance and verify `status=candidate`, never confirmed.
7. Run the Action utterance and verify no invented owner/due.
8. Run continuous mode once, End Session, and verify complete drain.
9. Verify the same Evaluation artifact fields and PVC persistence.

Compare the three E2E values with the local pre-flight reference:

| Case | Local E2E reference |
|---|---:|
| Topic | 4.561 sec |
| Candidate Decision | 5.792 sec |
| Action | 3.602 sec |

Deployment Gate PASS requires evidence loss 0, graph corruption 0, automatic confirmation 0, complete drain, and E2E within the prototype budget (median ≤5 sec, p95 ≤10 sec). This test does not start the human Pilot.

## Evaluation artifact persistence test

After a non-Pilot smoke evaluation creates one artifact, record its PVC path and checksum, then restart the Pod once and verify the same artifact is still present:

```sh
kubectl -n ronro-pilot get pod -l app.kubernetes.io/name=ronro
kubectl -n ronro-pilot delete pod -l app.kubernetes.io/name=ronro
kubectl -n ronro-pilot rollout status deployment/ronro-pilot --timeout=120s
kubectl -n ronro-pilot exec deploy/ronro-pilot -- \
  find /data/evaluation/live/sessions -maxdepth 2 -type f -print
```

This restart check is not a Pilot session. A restart during an active session loses in-memory session state; PVC artifacts already written remain.

## Graceful shutdown

On `SIGTERM`, the application rejects new Live sessions, requests the current session to stop, allows the Realtime transport to commit final audio when connected, waits for queue/Analyzer/Graph drain, and exits within a bounded 45-second application window. Kubernetes allows 60 seconds. New Human mutations are already disabled once a session is finalizing.

If the provider or browser connection is already gone, the existing runtime marks the session incomplete/degraded and preserves received Evidence rather than mutating the Graph. A timeout is reported in the runtime snapshot and Evaluation artifact.

## Rollback

Record the previous image tag before rollout:

```sh
kubectl -n ronro-pilot get deployment ronro-pilot \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
```

Rollback the Deployment revision:

```sh
kubectl -n ronro-pilot rollout undo deployment/ronro-pilot
kubectl -n ronro-pilot rollout status deployment/ronro-pilot --timeout=120s
```

Because the runtime is in-memory, rollback/restart is not a continuation mechanism for an active session. Use it only between sessions or after the session is safely finalized.

## Pilot version record

Record these values in the Pilot artifact and release note before Pilot #1:

- git commit SHA
- image tag and image digest
- `LIVE_CONFIGURATION_VERSION=semantic-graph-rc4`
- prompt `analyzer-prompt-v10-action-time-horizon`, output schema `v3`
- STT `gpt-transcribe`
- Analyzer `gpt-5.6-luna`
- reasoning `medium`

## Known limitations

Long continuous turns can make the bounded fallback exceed the normal live
latency target. The validation reference was p50 9.063 seconds and p95
13.838 seconds. Record VAD, bounded-fallback, and session-end boundary counts
and maximum unfinalized duration during a Pilot; do not retune thresholds
automatically during the session.

- Use the live cluster and image digest for a fresh environment check; the template alone cannot establish the current Ingress/TLS/StorageClass/registry state.
- `replicas > 1` is unsafe because state is in memory; sticky sessions are not used.
- A Pod restart loses active Session/Queue/Worker state; only persisted Evaluation artifacts survive.
- No production authentication, persistence, HA, autoscaling, distributed queue, or observability stack is included.
- The L1/L2 real-microphone acceptance history remains part of the pre-flight record; this deployment still requires the Kubernetes-path three-case smoke test before Pilot #1.

## Stop point

Deployment packaging ends after manifest/image validation and, once cluster access is restored, the deployment smoke test. Do not begin Live Pilot #1 automatically.
