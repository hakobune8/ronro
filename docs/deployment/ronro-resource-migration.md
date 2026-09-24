# RONRO Pilot リソース名の移行（2026-09-24）

この記録は、作業名 `discussion-map-ai-facilitator` から論路 / RONRO へ移った後の**現行リソース**を示す。過去の配備・評価記録に残る旧名は当時の事実として書き換えない。

| 用途 | 現行名 |
| --- | --- |
| Application Namespace / Deployment / Service | `ronro-pilot` |
| ConfigMap | `ronro-pilot-config` |
| OpenAI API Secret | `ronro-openai` |
| Evaluation PVC | `ronro-pilot-evaluation` |
| GHCR pull Secret | `ronro-ghcr-pull` |
| 公開Ingress / TLS | 別クラスターの `SSLHQ/staips-infra` が管理する `staips-edge/ronro` / `ronro-tls` |

アプリケーションの `ghcr-edge` overlay は公開Ingressを作らず、Serviceを固定NodePort **30100（HTTP）/30101（WebSocket）** で公開する。別クラスターの既存RONRO Ingress / EndpointSliceはすでにこの2ポートを参照していたため、infra Repositoryの差分・PRは不要だった。新Serviceの最初の生成時にはKustomizeのstrategic mergeでNodePort指定が落ち、一時的に502になった。JSON6902 patchで生成結果にNodePortを固定し、同じoverlayの再適用後も30100/30101が維持されることを確認した。

旧PVCから新PVCへ、298ファイルを同一digestのアプリケーションイメージを使って移した。ファイル数と全ファイルの内容チェックサムが、旧PVC・一時退避・新PVCで一致した。Raw Audioや評価本文、Secret値はPublic Gitへ入れていない。新DeploymentはReady 1/1、同一イメージdigest、restart 0、内部 `/healthz`・`/readyz` は200。公開 `/`、`/shared`、`/control`、`/session`、`/healthz`、`/readyz` は200、`/live` はWebSocket upgrade 101、`/api/live` は待機状態だった。

旧 `discussion-map-pilot` Deploymentは0 replicaにし、旧PVC・Secret・Namespaceを一時的なロールバック元として保持している。旧ServiceはNodePort切り替え時に削除した。旧アプリケーションクラスターIngressは公開Ingressの管理元ではない。旧Namespaceの最終削除は、移行後の稼働確認とバックアップ保持方針を確認してから別途行う。**本移行はLive Pilot開始の承認ではない。**
