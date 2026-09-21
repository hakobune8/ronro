# RONRO Public Release Checklist

対象: `hakobune8/ronro`（予定）  
初期候補: `v0.1.0-pilot`  
License: Apache License 2.0

このChecklistは公開作業の手順であり、GitHub Repositoryの作成・Push・Tag作成を自動化しない。

## Current gate

現時点の判定: **READY FOR PUBLIC REPOSITORY CREATION — AFTER KEY ROTATION**

詳細は [`public-release-readiness.md`](public-release-readiness.md) と [`public-evaluation-data-manifest.md`](public-evaluation-data-manifest.md) を参照する。

## Resolved checks

- [x] Root `LICENSE`に標準Apache License 2.0本文がある
- [x] READMEがRONRO / 論路、論点図、Prototype status、Limitationsを説明している
- [x] READMEのRepository-relative linksを検査した
- [x] Participant-facing名称が論路 / 論点図へ揃っている
- [x] Historical docsの旧名称は機械的に変更していない
- [x] `.env`がGit trackedでないことを確認した
- [x] `.gitignore`で`.env`、Runtime artifact、Raw Audioを除外している
- [x] `.dockerignore`で`.env`、Secret variant、Runtime artifact、Raw AudioをBuild contextから除外している
- [x] Dockerfileが`.env`・実評価素材・Raw AudioをImageへ含めないことを確認した
- [x] `.env.example`に実Secretがない
- [x] `secret.example.yaml`に実Secretがない
- [x] KubernetesのHost、Registry、TLS Secret、Cluster情報がTemplate化されている
- [x] Pilot Guide Markdown / PDFを公開安全性の観点で確認した
- [x] M PLUS 1pのFont binaryをRepositoryへ含めていない
- [x] M PLUS 1pのPDF embedding判断と根拠をReadiness Reportへ記録した
- [x] `docs/release/public-evaluation-data-manifest.md`を作成した
- [x] Public packaging dry-runで`evaluation/30min`、`evaluation/real-analyzer`、未確認のGolden/Context Spikeを除外した
- [x] GitHub Repository作成、Remote追加、Push、Tag作成を実施していない
- [x] `python3 -m compileall -q prototype tests`がGreen
- [x] Product testsが145件Green
- [x] `kustomize build deploy/kubernetes/pilot`が成功
- [x] 公開README / Pilot GuideにLocal absolute pathとCodex-specific referenceがないことを確認した

## Human gate — 公開前に必須

- [ ] `.env`の現在のKeyを人間が確認し、実キーならローテーションまたは失効した
- [ ] 初回Commitに含めるファイルを人間がReviewした
- [x] `evaluation/30min/`と`evaluation/real-analyzer/`を初回Public Treeから除外した（元データは削除していない）
- [x] `evaluation/golden/v2/`と`evaluation/context-spike/`をSynthetic-only条件不成立として初回Public Treeから除外した
- [x] 実マイクPre-flight、実Pilot、Raw Audio、参加者Transcript、Feedbackを公開対象から除外した
- [x] Synthetic Fixture / Scenario / Type D / Continuous Simulationの公開範囲を確認し、READMEを追加した
- [ ] 第三者Package / Image / AssetのLicenseを確認した
- [ ] `NOTICE`の要否を確認した
- [x] Security報告方針を`SECURITY.md`へ反映した

## Non-blocking verification

- [ ] Docker daemonが利用可能な環境で`docker build`を実行した
- [ ] BuildしたImageを起動し、`/healthz`と`/readyz`を確認した
- [ ] 必要に応じてKubernetes上でImage pull / startup smokeを確認した

Docker daemon unavailableはApplication起因のBlockerではないが、公開前のVerificationとして残す。

## Post-create / Pre-announcement action

- [ ] Repository作成後、Public announcement前にGitHub Private vulnerability reportingを有効化する

## GitHub Repository creation — 人間が実施

- [ ] Organization `hakobune8`で`ronro`を作成した
- [ ] VisibilityをPublicに設定した
- [ ] Descriptionを設定した
- [ ] Topicsを設定した
- [ ] `main`をDefault Branchに設定した
- [ ] Branch Protection / Required CI / Reviewを設定した
- [ ] Secret Scanning / Push Protectionを有効化した
- [ ] Private vulnerability reportingを有効化した
- [ ] README、License、Security、Contributingの表示を確認した
- [ ] 初回Commitを作成した
- [ ] 初回Pushを行った

## First release

- [ ] `v0.1.0-pilot`をPre-releaseとして作成した
- [ ] Git commit SHA、Image tag、Configuration versionを記録した
- [ ] STT / Analyzer modelとPrompt versionを記録した
- [ ] Live Pilot #1は明示的な開始操作まで実施しない
