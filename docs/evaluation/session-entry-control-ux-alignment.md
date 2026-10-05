# RONRO Session Entry / Control UX Alignment

更新日: 2026-09-21
対象: v0.1.0-pilot / Live Pilot #1 前

この文書は、Live Pilot開始前に、会議の開始・音声入力・終了を利用者が迷わず行えるように、既存RouteとDevice責務を整理するためのAlignment Reviewである。今回はProduct Codeを変更せず、実装方針を確定する。

## Current Problems

現在の利用者体験には、次の分かりにくさがある。

- `/` を開くと、再生・Analyzer・Evaluation・Human Commandなどを含むDeveloper / Control画面が表示される。
- `/shared` は参加者向けの読み取り専用論点図だが、開始・終了の入口は表示しない。
- そのため、初めて使う人には「どの画面を開けばよいか」「誰が会議を始めるか」「どこからマイクを入力するか」が明確でない。
- 現在のLive Audio操作はDesktopのDeveloper UIに集約されており、スマートフォンから会議を開始・終了する専用の入口はない。
- `/api/live/start`、`/api/live/stop`、`/live` は既に存在するが、利用者向けの責務分離とアクセス境界はまだ明示されていない。

中心価値である「共有画面で論点図を見る」は成立している。問題は、会議開始前と終了時の入口が、その体験に自然につながっていないことである。

## Current Route Responsibilities

実装を確認した結果、現在の責務は以下のとおりである。

| Route / API | 現在の利用者・用途 | Mutation | 備考 |
|---|---|---:|---|
| `/` | Developer / Facilitator / Evaluation | Yes | `prototype/web/index.html`。Replay、Live Start / Stop、Human Command、Evaluation、Debugを一画面に含む。 |
| `/shared` | 参加者・共有ディスプレイ | No | `prototype/web/shared.html`。`/api/live`を定期取得し、論点図だけを読み取り表示する。 |
| `/live` | BrowserとBackendの音声Transport | Yes相当 | HTTPページではなくWebSocket。Binary PCMと`commit` / `stop`制御を受ける。 |
| `GET /api/live` | Shared View / Control UI | No | 現在のSession、Graph、Projection、Runtime状態を返す。 |
| `POST /api/live/start` | Control UI | Yes | In-memoryの単一Sessionを作成し、WebSocket URLを返す。StartはActive中には冪等である。 |
| `POST /api/live/stop` | Control UI | Yes | Sessionを`finalizing`へ進め、Transport側のSTT commit / Drainを促す。 |
| `POST /api/live/commands` | Facilitator / Developer | Yes | Human Commandを実行する。Shared Viewからは呼ばれない。 |
| `POST /api/live/evaluation/*` | Observer / Evaluation | Yes | Evaluation Artifact、Marker、Feedback等を扱う。 |
| `GET/POST /api/sessions/*` | Replay / Human Command | Yes | Recorded / Fixture向けの既存Control API。 |

現在、`/control`、`/observer`、`/dev`、スマートフォン専用Routeは存在しない。

## Proposed Route Responsibilities

### 推奨するPilot前の最小Route整理

既存のAPIやWebSocket semanticsを大きく変えず、Presentationの入口とRuntime Session Ownershipだけを整理する。Pilot #1のアクセス境界はRONRO独自認証ではなく、NetBird Private Networkとする。

| Route | Audience | Purpose | Mutation |
|---|---|---|---:|
| `/` | 参加者 | 論点図を表示するPrimary Shared View | No |
| `/shared` | 参加者・既存リンク | `/`と同じShared Viewを返すCompatibility入口 | No |
| `/session` | 進行役のスマートフォン | 会議開始、マイク入力、状態確認、会議終了 | Start / Audio / Endのみ |
| `/control` | Facilitator / Developer | 現在の`/`にあるLive Control、Human Command、Replay、Evaluation | Yes |
| `/observer` | Observer | 将来の評価専用View候補 | L6の既存UIを当面`/control`に残す |
| `/dev` | Developer | 将来のDebug / Replay専用View候補 | 今回は新設しない |
| `/live` | Browser Audio Client | 音声WebSocket Transport | Audio / commit / stopのみ |

`/shared`は既存の外部リンクやGuideとの互換性を保つため、PilotではRedirectよりも同一Shared HTMLを返す方式を第一候補とする。Redirectが必要な場合でも、Shared View自体に操作UIを戻さない。

`/session`を採用する理由は、現在の`/control`をDesktop Facilitator用に明確に残し、スマートフォンへDeveloper MetricsやHuman Commandを持ち込まないためである。Route名は将来変更可能だが、責務としては「スマートフォンController」を独立させる。これらのRouteはすべてNetBird Private Network内からのみ到達可能であることをPilotのDeployment前提とする。

## Shared Display UX

Shared Displayは「見る画面」であり、「会議を操作する画面」ではない。現在の`shared.html`の読み取り専用方針を維持し、以下のRuntime状態を受動的に表示する。

### 会議前: Idle

論点図の中央領域に大きな操作ボタンを置かず、次のようなPassive Stateを表示する。

> 論路
> 会議の開始を待っています

必要な場合だけ、画面の端にController URLまたはQRを控えめに表示する。QRにAPI Keyや長期Secretを埋め込まない。

### 会議中: Active

既存のShared Viewを中心に、次を表示する。

- 今話していること
- 主要な論点
- 決定候補
- 未解決事項
- 次の対応
- 話の流れ

Start / End / Confirm / Rename等の操作は表示しない。`/api/live`の定期取得で、Controller側の開始・終了を自動反映する。

### 終了中: Finalizing

論点図を消さず、Statusだけを控えめに更新する。

> 最後の発話を整理しています…

既存のAudio flush、STT Finalization、Queue / Analyzer Drain、Graph更新、最終Renderをそのまま利用する。

### 終了後: Ended

Shared DisplayはBlankに戻さず、最終論点図を残す。

> 会議を終了しました

進行役が次のSessionを開始するまで、最後の論点図を確認できる状態を保つ。

## Smartphone UX

スマートフォンは、論点図を読むための縮小画面ではなく、以下に限定したController / Microphoneとする。

### 開始前

```text
論路
会議の開始を待っています

[ 会議をはじめる ]
```

ボタン押下後の明示的なUser Gestureから、`getUserMedia`、AudioContext、AudioWorkletを開始する。マイク権限はページロード時に要求しない。

### 会議中

```text
論路
● 聞いています

必要なら: 今話していること

[ 会議を終了 ]
```

スマートフォン側へ論点図全体、Queue、Latency、Evidence、Human Command、Evaluation Markerを移植しない。

### 終了時

誤操作を避けるため、次の確認を挟む。

> 会議を終了しますか？

`キャンセル` / `終了する`

終了後は、以下を表示する。

> 会議をまとめています…

Drain完了後は、

> 会議を終了しました

とする。ControllerはShared Displayと同じRuntime Snapshotを参照するため、Manual reloadなしで状態が追従する。

## Start Flow

推奨する最小フローは次のとおりである。

1. 共有ディスプレイで`/`を開く。
2. Shared Viewに「会議の開始を待っています」と表示する。
3. 進行役がスマートフォンで`/session`を開く。PilotではQRまたは配布URLを使用できる。
4. 進行役が「会議をはじめる」を押す。
5. その明示操作を起点に、マイク権限を確認する。
6. 既存の`POST /api/live/start`、`/live` WebSocket、AudioWorklet、PCM変換を開始する。
7. Shared Displayとスマートフォンの両方がActive状態になる。
8. 参加者は普段どおり話し、必要なときだけ論点図を見る。

Audio開始に失敗した場合は、SessionをActiveとして残さず、原因をControllerに表示し、再試行可能な状態へ戻す。既存のGraphやCanonical Eventを変更しない。

## Active Flow

既存のBrowser Audio Pipelineを再利用する。

```text
iPhone Safari
  → getUserMedia
  → AudioWorklet
  → Browser側の明示的なresampling
  → PCM16 little-endian / mono / 24 kHz
  → WSS /live
  → Realtime STT
  → Normalization v2
  → FIFO Queue / Single Analyzer Worker
  → Graph / 論点図
```

既存のDesktop Safari経路と、スマートフォン専用の別STT Pipelineを作らない。違いはControllerの画面と、iPhone SafariのLifecycle制約への対応だけに限定する。

## End / Drain Flow

スマートフォンの終了操作は、既存のSession Drainを利用する。

```text
会議を終了
  → 新しいAudio Captureを停止
  → 残Audio Bufferをflush
  → STTへcommit / finalization
  → Final Transcriptを待つ
  → Queue / AnalyzerをDrain
  → Event / Graph / Projectionを確定
  → Shared Displayへ最終Render
  → ended
```

既知の周辺音がDrain中に追加Finalになる可能性は、VADを新設せず、まずControllerとTransportの停止順序で観察・改善する。成功条件は、`pending = 0`、`processing = none`、`graph_revision == rendered_revision`、Evidence loss = 0である。

## Fallback Desktop Flow

スマートフォンを必須依存にしない。Pilotでは、スマートフォンが使用できない場合に、Desktopの`/control`から既存のLive Start / Stopを実行できるようにする。

- Desktop `/control`はFacilitator / Developer向けの既存画面を維持する。
- Shared Display `/`は引き続きRead-onlyである。
- DesktopがSessionを開始しても、Shared Displayは`/api/live`の更新でActiveへ追従する。
- Sessionが終了した場合も、同じDrainと最終Renderを使用する。

## Mobile Safari Constraints

既存コードから、スマートフォンで再利用できる要素は確認できている。

- `navigator.mediaDevices.getUserMedia`を明示操作後に呼び出せる。
- `AudioContext`を`resume()`し、既存の`AudioWorklet`をロードできる。
- Browser側で入力サンプルレートからTarget 24 kHzへresampleする処理がある。
- `/api/live/start`が返す同一OriginのWebSocket URLを使い、HTTPS環境ではWSSになる。
- `/live`は既存のBinary PCM Transportを受ける。

iPhone Safariでは、次をPilot Acceptance Riskとして扱う。

- 画面Lock、別Appへの切替、BrowserのBackground化でAudioContext、AudioWorklet、WSSが停止または中断する可能性がある。
- Microphone権限はHTTPSと明示操作が必要である。
- SafariのページLifecycleや省電力挙動により、長時間の連続入力が不安定になる可能性がある。
- Browserが入力サンプルレートを固定値にする前提は置かず、既存resamplingを維持する。

初回Pilotでは、次の運用条件を採用する。

> Controllerとして使うiPhone Safariは前面表示し、画面をLockしない。

Web Wake Lock APIは利用可能性を検証するが、必須条件やBackground Audioの代替にはしない。

## Security

### Pilot #1のAccess Boundary

`ronro.hakobune8.com`はPublic Internetへ公開せず、NetBird Private Network内からのみ到達可能とする。Pilot #1では、NetBirdがNetwork Access Boundaryであり、RONRO独自のAuthentication / Authorization Layerではない。

NetBirdに接続していないSmartphoneから、`ronro.hakobune8.com`へアクセスできないことをPre-flightで確認する。`/`、`/shared`、`/session`、`/control`、`/live`および対応するHTTP APIは、このNetwork boundary内でのみ使用する。

Shared DisplayにQRを表示する場合は、通常のNavigation URLである`https://ronro.hakobune8.com/session`だけを埋め込む。API Key、Secret、Credential、Controller tokenはQRやURLに含めない。

### 実装しない認証

今回、以下は実装しない。

- short-lived controller authentication token
- login / user-password
- OAuth / OIDC / JWT
- User Authentication Platform
- Temporary Authenticationを兼ねるSession token

将来は、NetBirdのNetwork Accessの後段にZITADELを接続し、Identity、Role、Capabilityを段階的に追加する。ZITADEL連携は今回のScope外である。

```text
Network Access (NetBird)
        ↓
Identity (future: ZITADEL)
        ↓
Role / Authorization (future)
        ↓
RONRO Route / Capability
```

### Runtime Session Ownership

Network boundaryとは別に、Pilot Runtimeでは`1 active session / 1 active controller`を採用する。これはUser Authenticationではなく、同一Session内の操作競合を防ぐためのRuntime Ruleである。

- 最初にSession StartしたControllerがActive Controllerになる。
- Active Session中に別Smartphoneが接続した場合は、「別の端末で会議を操作中です」と表示し、Start / End / Audio controlを奪えない。
- Active Controllerのreload、短時間のWi-Fi interruption、NetBird interruption、Safari lifecycle interruptionでSessionを即終了しない。
- ControllerはBrowser内に生成した非機密のRuntime instance identifierで短時間のReconnectを識別する。これはCredential、認証Token、権限証明ではない。
- PilotではActive Controllerの所有権をSession終了まで保持し、別端末への自動handoverは行わない。所有端末を失った場合は、Facilitatorの`/control`から安全にSessionを終了する。
- Session終了後、次のSessionではOwnershipを初期化する。

### Controllerの権限境界

スマートフォンControllerからは次を許可しない。

- 任意のSession IDに対する操作
- Human Command
- Evaluation Marker / Feedback
- Replay / Debug API
- Graphの直接Mutation

Controllerは、現在の単一Live Sessionに対するStart / Audio / Endのみを扱う。Pilotでは同時Controller数を1台に固定する。

## Architecture Impact

今回の方針は、Domain Architectureの変更ではない。

### Reuseするもの

- Browser AudioWorklet
- Browser側のPCM変換、mono化、24 kHz resampling
- Local / IngressのWSS `/live`
- `POST /api/live/start`、`POST /api/live/stop`
- Realtime STT Adapter
- Normalization v2
- FIFO Queue / Single Analyzer Worker
- Event Store、Materializer、Projection、Shared View
- Session DrainとRuntime Snapshot

### 必要になるSmall Extension

- Shared Viewを`/`で提供するRoute alias / Static asset選択
- 現在のDeveloper / Control UIを`/control`で提供するRoute alias
- スマートフォン向けの小さな`/session` Controller HTML / JavaScript
- ControllerからSession状態を取得するPollingまたは既存Snapshot購読
- NetBird Network boundaryを前提にしたControllerアクセス
- Active Controllerを保持するRuntime Session Ownershipと短時間Reconnect
- Idle / Active / Finalizing / Endedの参加者向け表示文言

### 変更しないもの

- Canonical Event Schema
- Discussion Graph
- Materializer
- Analyzer / Prompt
- STT Provider
- Queue / Worker semantics
- Evaluation Schema
- Kubernetes topology

## Risks

| Risk | 影響 | 初回Pilotでの扱い |
|---|---|---|
| iPhoneがLock / Backgroundになる | Audio停止、WSS切断、Evidence欠落の可能性 | 前面表示・非Lockを運用条件にする。失敗時はSessionを終了し再開する。 |
| NetBird外からの到達 | Pilot外の端末がSession APIへ到達する | 非NetBird端末からの到達不可をPre-flightで確認する。 |
| Controllerの競合 | 別端末がSession Start / Endを奪う | 最初のControllerをSession終了まで保持し、別端末は操作不可とする。 |
| Controllerの一時切断 | 操作端末が一時的にreload / offlineになる | Sessionを即終了せず、Runtime instance identifierで短時間Reconnectする。 |
| Mic permission拒否 | Session開始不能 | 明示Start後に権限要求し、失敗時はSessionをActiveにしない。 |
| Browser終了 / Network切断 | Transport失敗、Incomplete drain | GraphとEvidenceを保持し、Runtimeをdegraded / incompleteとして表示する。 |
| Drain中の周辺音 | 余分なFinal Utterance | VADは追加せず、停止順序と観測で扱う。 |
| 複数Controller | 競合・意図しない二重Start / End | Pilotはone active controllerに固定する。 |
| In-memory Session | Pod restartでActive Sessionを失う | 既存Known Limitationを維持し、Pilot中のRestartを避ける。 |

## Pilot Recommendation

### Decision: B — Small Architecture Extension

理由は、既存Audio / STT / Graph / Session Drainを再利用でき、必要なのはRouteとPresentation、Controller用Client、Runtime Session Ownershipの小さな拡張だからである。PilotのNetwork Accessは既存のNetBird Private Networkを利用し、暫定Authenticationは追加しない。

- A（Existing Architecture / Minimal UX Change）だけでは、スマートフォンにDeveloper UIを見せずにStart / End / Microphoneだけを提供できない。
- Bなら、既存Backend Contractを保ったまま、`/`・`/shared`・`/control`・`/session`の責務を明確にできる。
- C（Significant Architecture Change）は不要である。Session共有のための分散Sessionや新STT Pipelineは必要ない。
- D（Defer Smartphone Until After Pilot）は安全側の選択肢だが、今回のUX課題を残す。NetBird境界を確認できない場合のみ、PilotではDesktop fallbackに戻す。

### v0.1.1-pilotで推奨する最小範囲

1. `/`をPrimary Shared Viewにする。
2. `/shared`は同じShared Viewを返すCompatibility入口として残す。
3. `/control`に現行Developer / Facilitator UIを移す。
4. `/session`にStart / Microphone / Listening / EndだけのControllerを追加する。
5. Shared ViewへIdle / Active / Finalizing / EndedのPassive Stateを追加する。
6. Controllerは既存APIとWSSを再利用し、スマートフォン側へGraph全体を表示しない。
7. iPhone SafariでForeground / no-lockの1発話Vertical Sliceを実施する。
8. NetBird外からの到達不可を確認し、`/session`のQRは通常Navigation URLだけにする。
9. 最初のControllerをSession終了まで保持し、別ControllerをRead-only / 操作不可にする。
10. 同一Controller Browserの短時間Reconnectを確認する。

## Pilot Gate

このAlignmentだけではLive Pilot #1を開始しない。実装後、次を別途確認する。

- `/`が論点図のIdle / Active / Finalizing / Endedを受動表示する。
- `/shared`の互換リンクが壊れていない。
- `/control`からMac Safari単体の既存Live Audioが動く。
- iPhone Safariの明示Start、Mic permission、AudioWorklet、WSSが成立する。
- Smartphone StartでShared DisplayがActiveへ追従する。
- Smartphone EndでFinalizing → Ended、最終Renderまで追従する。
- Evidence loss = 0、Automatic Confirmation = 0、Graph corruption = 0、Owner / Due invention = 0。
- `pending = 0`、`processing = none`、`graph_revision == rendered_revision`。
- ControllerへのアクセスがPilotのNetwork境界で制限されている。
- NetBird未接続SmartphoneからHostへ到達できない。
- 別ControllerがStart / End / Audio controlを奪えない。
- Active Controllerの短時間ReconnectでSessionが維持される。
- `v0.1.0-pilot`のArchitectureと既存APIを破壊していない。

ここを満たすまで、Live Pilot #1は開始しない。
