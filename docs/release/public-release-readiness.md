# Public Release Readiness — RONRO / 論路

更新日: 2026-09-21  
対象Repository: `hakobune8/ronro`（予定）  
候補License: Apache License 2.0  
判定対象: GitHub公開前のローカル作業ツリー

## Current Gate

**READY FOR PUBLIC REPOSITORY CREATION — AFTER KEY ROTATION**

公開用のPackage構造、License、README、除外ルール、公開用ドキュメントは整備済みです。機械的に確認できるSecret混入・Docker context混入・公開ガイドの問題は解消しました。

Repository作成前に必要なHuman Actionは、現在の`.env`にある可能性のあるOpenAI API keyの確認と、実キーであればローテーションまたは失効です。Codexはこの操作を行わないため、Key rotation完了後にRepository作成へ進めます。

GitHub Private vulnerability reportingは、Repository作成後に行う **Post-create / Pre-announcement Required Action** とする。

## Previous Findings (pre-resolution)

前回のReadiness Reviewで記録されていたFindingは次のとおり。今回の判定は下記の解消状況を反映している。

- `.env`にSecret設定が存在する可能性。
- Git Commit履歴がなく、History Auditが未実施。
- `evaluation/30min/`の公開可否が未確定。
- `evaluation/real-analyzer/`の公開可否が未確定。
- Pilot Guide PDFとM PLUS 1pの再配布条件が未確認。
- Security vulnerability reporting destinationが未確定。
- Docker buildが未実施。

## Blocker Resolution Summary

| Item | Status | 判定・対応 |
| --- | --- | --- |
| `.env` Secret設定 | **READY AFTER HUMAN KEY ROTATION** | `.env`はGit未追跡、`.gitignore`と`.dockerignore`で除外、Dockerfileからコピーされない。値は表示していない。公開前にHumanがKeyをローテーションする。 |
| Git Commit履歴 | **RESOLVED / NON-BLOCKING VERIFICATION** | Commit数は0。`Historical Secret Audit is not applicable because no Git commit history exists.` と判断する。これはWorking Treeが安全であることを意味しないため、別途Working Tree Auditを実施済み。History Rewriteは不要。 |
| `evaluation/30min/` | **EXCLUDE FROM PUBLIC** | Human Decisionにより初回Public Releaseから除外。元データは削除しない。 |
| `evaluation/real-analyzer/` | **EXCLUDE FROM PUBLIC** | Human Decisionにより初回Public Releaseから除外。元データは削除しない。 |
| `evaluation/golden/v2/` | **EXCLUDE FROM PUBLIC** | Recorded Analyzer datasetの派生Viewであり、Synthetic-only条件を確認できないため除外。 |
| `evaluation/context-spike/` | **EXCLUDE FROM PUBLIC** | Recorded Analyzer dataset / Goldenを参照するSpikeであり、Synthetic-only条件を確認できないため除外。 |
| Pilot Guide Markdown/PDF | **SAFE TO PUBLISH** | 参加者PII、内部Host、API情報、顧客情報、Private Pilot結果を確認できない。MarkdownとPDFは公開候補。 |
| M PLUS 1p / PDF | **SAFE TO PUBLISH**（Font binaryは除外） | RepositoryにFont binaryは含めていない。M PLUS 1P公式RepositoryはSIL Open Font License 1.1を示しており、SIL FAQはOFL Fontの文書へのEmbeddingと文書配布を許容している。根拠は下記。 |
| Security reporting | **POST-CREATE / PRE-ANNOUNCEMENT REQUIRED ACTION** | 公開Issueで脆弱性を受け付けず、GitHub Private vulnerability reportingを第一候補とする方針を`SECURITY.md`へ反映。Repository作成直後、Public announcement前に有効化する。 |
| Docker build | **NON-BLOCKING VERIFICATION** | DockerfileとBuild contextの監査はPASS。Docker daemonが利用できない環境のため実Build/startup/health probeは未実施。Application起因のBuild failureではない。 |

## Secret / Credential Audit

秘密値は出力・コピー・このReportへの記録をしていない。

- `.env`は存在するがGit trackedではない。
- `.gitignore`で`.env`および`.env.*`を除外している。ただし`.env.example`は公開可能な例外とする。
- `.dockerignore`で`.env`および`.env.*`をBuild contextから除外している。
- `Dockerfile`は`.env`、Runtime artifact、Raw Audio、Real Analyzer素材を`COPY`しない。
- `deploy/kubernetes/base/secret.example.yaml`は空のPlaceholderのみで、実Secretを含まない。
- README、公開Docs、ConfigMapに実Secretを参照する記述はない。

現在のキーが実運用キーか、過去に外部へ露出したかは、秘密値を表示せずにRepositoryだけからは判定できない。したがって、人間が公開前に現在のKeyを確認し、実キーならローテーションまたは失効することを必須とする。CodexはKeyを変更・削除・失効していない。

## Git History Audit

- Commit数: `0`
- Remote: 未設定
- History Rewrite: 実施していない
- GitHub Repository作成: 実施していない
- Push / Tag: 実施していない

**Historical Secret Audit is not applicable because no Git commit history exists.**

これはWorking Treeが自動的に安全であることを意味しない。Working Treeについては、`.env`、Runtime artifact、Raw Audio、Secret Manifest、local path、Codex-specific referenceを別途確認した。初回Commitは人間の公開対象Review後に作成する。

## Evaluation Data Decision

個別のProvenance、公開判断、理由は [`public-evaluation-data-manifest.md`](public-evaluation-data-manifest.md) に記録した。

- 公開候補: `evaluation/fixtures/`, `evaluation/scenarios/`, `evaluation/type-d-spike/`、`evaluation/live/l4-l5-continuous-simulation.json`。
- 公開対象外: `evaluation/30min/`, `evaluation/real-analyzer/`, `evaluation/golden/v2/`, `evaluation/context-spike/`。
- 公開対象外: `evaluation/live/preflight/`, `evaluation/live/sessions/`, `evaluation/stt/`, `evaluation/runs/`, `evaluation/rescored/`。
- Real microphone、Raw Audio、participant feedback、observer notes、private session artifactはPublic Packageへ含めない。

除外対象は既存テストのためにローカルへ保持している。`.gitignore`とPublic Packaging方針で初回Public Treeから外しており、元データは削除していない。

## Pilot Guide / Public Documentation

対象:

- `docs/pilot/ronro-live-pilot-guide.md`
- `docs/pilot/ronro-live-pilot-guide.pdf`

両方を確認し、Participant PII、Internal Hostname、API情報、Customer Information、Private Pilot Result、Local Absolute Path、Codex-specific referenceは確認されなかった。内容はPrototype / Pilot向けの公開説明として扱えるため、**SAFE TO PUBLISH候補**とする。

## Font and Third-party Asset Decision

Repository内にM PLUS 1pのFont binaryは含めていない。PDF生成時に使用したFontは、公開PackageへBinaryとして再配布する対象ではない。

M PLUS 1P公式RepositoryはSIL Open Font License v1.1での提供を示している。SIL OFL FAQは、OFL Fontを文書へEmbeddingでき、Embeddingされた文書のLicenseは変更されないと説明している。

- Font binaryのRepository再配布: **実施しない**。
- M PLUS 1pを埋め込んだPilot Guide PDFの配布: **SAFE TO PUBLISH**。
- RONROのApache-2.0とM PLUS 1pのOFLは別Licenseとして扱う。
- Font binaryを将来配布する場合は、OFL本文と必要なAttributionを同梱する別判断が必要。
- 現時点では、PDF配布のための追加License本文は不要と判断する。

根拠:

- [M PLUS 1P official repository](https://github.com/googlefonts/MPLUS_1P)
- [SIL Open Font License official text](https://openfontlicense.org/open-font-license-official-text/)
- [SIL OFL FAQ](https://openfontlicense.org/ofl-faq/)

## Security Reporting Decision

`SECURITY.md`を更新し、次の方針を明記した。

- 公開Issueへ脆弱性の詳細を投稿しない。
- Repository作成後はGitHub Private vulnerability reportingを第一候補として有効化する。
- Private routeが有効になるまで、公開Issueへ詳細を書かず、管理者へ非公開経路を確認する。

Private vulnerability reportingはRepository作成後、Public announcement前に有効化する。これは **POST-CREATE / PRE-ANNOUNCEMENT REQUIRED ACTION** である。既存の公開Security ContactはRepositoryから確認できないため、メールアドレスは追加していない。

## Docker Verification

実行済み:

- Dockerfileの静的監査: PASS
- `.dockerignore`のSecret / Runtime / Raw Audio除外確認: PASS
- `docker build --check .`: Docker daemon unavailable

Docker daemonが利用できないため、Image Build、Container起動、`/healthz`、`/readyz`は未実施である。これは環境制約による **NON-BLOCKING VERIFICATION** とし、Release Checklistへ残す。daemonが利用可能になった時点で公開前に実行する。

## Public Tree Proposal

初回Public Repositoryへ含める予定のTop-level構成:

```text
README.md
LICENSE
SECURITY.md
CONTRIBUTING.md
.env.example
.gitignore
.dockerignore
Dockerfile
.github/dependabot.yml
prototype/
schemas/
tests/
docs/
evaluation/        # README/manifestに列挙したSynthetic候補のみ
deploy/
requirements-dev.txt
```

`evaluation/30min/`、`evaluation/real-analyzer/`、`evaluation/golden/v2/`、`evaluation/context-spike/`は初回Public Treeから除外する。

## Exclusion Manifest

初回Public Repositoryへ含めないPath / Category:

- `.env`、Secret、Token、Private Key、Kubeconfig、実Secret Manifest
- `.venv/`、Cache、`tmp/`、Runtime Log、Temporary File
- `evaluation/live/preflight/`
- `evaluation/live/sessions/`
- `evaluation/30min/`
- `evaluation/real-analyzer/`
- `evaluation/golden/v2/`
- `evaluation/context-spike/`
- `evaluation/stt/` とRaw Audio / Media
- `evaluation/runs/`
- `evaluation/rescored/`
- Real participant / Real meeting / Customer / Internal derived data
- 実Registry、Internal Hostname、TLS Secret、Cluster Credential、VPN情報
- Repositoryへ同梱していないFont binary

## Repository Metadata Proposal

- Repository: `hakobune8/ronro`
- Visibility: `public`
- License: `Apache-2.0`
- Description: `議論の現在地を「論点図」として共有するリアルタイムAIファシリテーション・プロトタイプ`
- Topics: `ai`, `meeting`, `facilitation`, `realtime`, `visualization`, `speech-to-text`, `llm`, `discussion`, `collaboration`
- Initial version candidate: `v0.1.0-pilot`（Pre-release）

Repository作成、Remote追加、Push、Tag作成はまだ行っていない。

## Validation Results

- Product tests: **145 tests, all Green**
- `python3 -m compileall -q prototype tests`: PASS
- `kustomize build deploy/kubernetes/pilot`: PASS
- README relative links: PASS
- `.env` tracked check: PASS（untracked）
- `.env` ignore check: PASS
- Docker context exclusion check: PASS
- Local absolute path / Codex-specific reference audit: PASS for public README and Pilot Guide
- Docker build/startup/health probes: **NON-BLOCKING VERIFICATION**（daemon unavailable）

## Final Gate

**READY FOR PUBLIC REPOSITORY CREATION — AFTER KEY ROTATION**

Repository作成前のHuman Action:

1. `.env`の現在のKeyを確認し、実キーならローテーションまたは失効する。

Post-create / Pre-announcement Required Action:

1. GitHub Private vulnerability reportingを有効化する。

Docker daemon unavailableによるImage smoke check未実施は、引き続き **NON-BLOCKING VERIFICATION** とする。
