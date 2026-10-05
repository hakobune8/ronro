# RONRO Session Entry / Mobile Control Plan

対象Version候補: `v0.1.1-pilot`
前提: v0.1.0-pilotはimmutable。Live Pilot #1は本PlanのAcceptance完了まで開始しない。

このPlanは、既存の論路・論点図・Audio Pipeline・Session Drainを変更せず、会議の入口とスマートフォンControllerを追加するための実装計画である。

## Scope

### In Scope

- `/`をParticipant Shared Viewとして扱うRoute整理
- `/shared`のCompatibility維持
- `/control`への既存Developer / Facilitator UIの明示配置
- `/session`のスマートフォン向けStart / Microphone / Status / End画面
- 既存`/api/live/start`、`/api/live/stop`、`/live`の再利用
- Shared DisplayのIdle / Active / Finalizing / Ended表示
- iPhone SafariのForeground / no-lock Acceptance
- Kubernetes上の同一Origin HTTPS / WSS確認

### Out of Scope

- Canonical Event Schema変更
- Discussion Graph / Materializer / Projection変更
- Analyzer / Prompt / STT Provider変更
- 分散Session、複数Controller、HA、Redis、外部Queue
- Background AudioやiOS専用Native App
- 大規模Authentication / SSO
- Shared Viewへの操作UI復活
- Live Pilot #1そのものの開始

## S1 — Route Responsibility

### Implementation

- `prototype/server.py`で`/`がShared HTMLを返すようにする。
- `/shared`は同じShared HTMLを返し、既存リンク互換を維持する。
- 現行`index.html`を`/control`で返す。
- `/live` WebSocketと既存HTTP APIのPathは変更しない。
- `/observer`と`/dev`は今回新設しない。Evaluation / Developer UIはまず`/control`に残す。

### Acceptance

- `/`は操作なしで論点図を表示する。
- `/shared`は同一内容を表示する。
- `/control`は現在のReplay / Live / Human Command / Evaluation UIを表示する。
- `/`と`/shared`のHTMLにMutation Command、button、inputがない。
- `/live`のWSS URLとAPI Contractが変わらない。

## S2 — Session Start / End UX

### Shared Display

- Sessionなし: `会議の開始を待っています`
- Active: `聞いています`
- Finalizing: `最後の発話を整理しています…`
- Ended: `会議を終了しました`と最終論点図を保持

### Controller

- Startは明示的なボタン操作からのみ実行する。
- Endは確認ダイアログを挟む。
- End後はDrain完了まで`会議をまとめています…`を表示する。
- Drain完了後、次Sessionを開始できる入口を表示する。

### Acceptance

- Start中に二重Session、二重Microphone、二重Worker、二重STT接続を作らない。
- Permission拒否時にActive表示へ進まない。
- End後にShared DisplayがBlankにならない。
- `pending = 0`、`processing = none`、最終Projectionが表示される。

## S3 — Smartphone Responsive Controller

### Screen

`/session`はスマートフォン幅を優先し、次だけを表示する。

- 論路
- Session状態
- 会議をはじめる
- 聞いています
- 会議を終了
- 会議をまとめています…
- 会議を終了しました
- エラー時の再試行 / Desktop fallback案内

Graph全体、Metrics、Partial Transcript、Queue、Evidence、Human Commandは表示しない。

### State Source

既存`GET /api/live`を1秒程度のPollingで取得する。初期実装では新しいControl WebSocketを作らない。Shared DisplayとControllerが同じRuntime Snapshotを読むため、Manual reloadなしで同期する。

### Acceptance

- iPhone Safariで100%表示、縦向きで主要操作が見える。
- Start / Endのボタンは明示操作なしに実行されない。
- Session状態がIdle → Active → Finalizing → Endedへ追従する。
- ControllerからHuman Command、Evaluation、Replay APIを呼び出さない。

## S4 — Smartphone Microphone

### Reuse

現行`index.html`の以下の処理を共有可能なClient Moduleへ切り出す。

- `getUserMedia`
- `AudioContext.resume`
- `audioWorklet.addModule('/static/live-audio-worklet.js')`
- `AudioWorkletNode`
- Browser input sample rateから24 kHzへのresampling
- PCM16 little-endian / mono frame生成
- `POST /api/live/start`後の`new WebSocket(started.websocket_url)`
- Binary audio frame送信、`commit` / `stop`処理

別のSTT Adapter、別PCM Format、サーバー側の新しいAudio Pipelineは作らない。

### Start Ordering

初回の実装では、既存のStart API Contractを活かしつつ、次を保証する。

1. User Gestureを受ける。
2. Microphone permissionを要求する。
3. AudioContext / Workletを初期化する。
4. Session StartとWSS接続を確立する。
5. 失敗時はSessionをActiveのまま残さず、Capture / Socket / RuntimeをCleanupする。

実装時に、既存の`/api/live/start`がSessionを先に作ることによるPermission拒否時の残留状態をテストする。

### Acceptance

- iPhone SafariでMic permissionが表示される。
- AudioWorkletが起動する。
- PCM frameが受信される。
- 24 kHz PCMがWSS `/live`へ届く。
- 実STT Final → Analyzer → Graph → Shared View更新が1発話で成立する。
- Evidence loss = 0、Automatic Confirmation = 0、Graph corruption = 0。

## S5 — Shared Display Synchronization

### Implementation

- Shared Viewは現在の1秒Pollingを維持し、Runtime Stateを表示する。
- Controller Start後、次回PollingでShared DisplayがActiveになる。
- Controller End後、FinalizingとEndedを表示する。
- 既存2秒Map render coalescingは変更しない。
- Human Correctionは`/control`で行い、Shared Viewへ既存Snapshot経由で反映する。

### Acceptance

- Shared DisplayのManual reloadなしでIdle / Active / Finalizing / Endedが変わる。
- `rendered_revision == graph_revision`をEndedで確認できる。
- Shared Viewには操作、Debug、Metricsが出ない。

## S6 — Mobile Safari Acceptance

### Test Matrix

1. HTTPS `/session` load
2. 初回Mic permission
3. AudioWorklet load
4. Input sample rate確認と24 kHz resampling
5. WSS `/live`接続
6. Topic発話1件
7. Final STT
8. Shared View更新
9. Candidate Decisionで`candidate`維持
10. ActionでOwner / Dueを推測しない
11. End confirmation
12. Finalizing → Drain → Ended
13. 最終revision一致
14. Foreground / unlocked 10〜15分接続確認
15. Lock / Background時の挙動をWarningとして記録

### Operational Policy

- Controller iPhoneは前面表示し、Lockしない。
- Background Audioはサポート対象外と明記する。
- Wake Lockは補助的に検証するが、失敗しても必須Gateにしない。
- Network / Browser failure時はReconnectで履歴を再構築せず、既存Sessionを保持して安全に終了する。

## S7 — Kubernetes Smoke

### Verification

- `/`、`/shared`、`/control`、`/session`が同一HTTPS Hostで配信される。
- `/live`のWSS UpgradeがIngressを通る。
- SafariのMixed Content / CORSがない。
- Existing `ronro.hakobune8.com` Deployment、replicas=1、PVC、TLSを変更しない。
- v0.1.0-pilot Tagを書き換えず、実装時はv0.1.1-pilot候補として別commit / imageを作る。
- `ronro.hakobune8.com`がNetBird Private Network内からのみ到達可能である。
- QRは`https://ronro.hakobune8.com/session`という通常URLだけを含み、SecretやTokenを含まない。

## Session Ownership and Security

### Pilot Baseline

- 1 room
- 1 Shared Display
- 1 Facilitator smartphone
- 1 active Controller
- 2〜3 participants

Sessionは現行`LiveSessionManager`の単一In-memory Sessionを再利用する。ControllerとShared Displayは`GET /api/live`で同じSession Snapshotを見る。複数ControllerやSession discoveryは作らない。

### Access Model

Pilot #1では、`ronro.hakobune8.com`をNetBird Private Networkからのみ到達可能にする。NetBirdがNetwork Access Boundaryであり、RONRO独自のAuthentication Systemは追加しない。

QRを使う場合は、`https://ronro.hakobune8.com/session`という通常Navigation URLだけを使用する。API Key、Secret、Credential、short-lived tokenはQRへ埋め込まない。NetBird未接続端末からHostへ到達できないことをPre-flight条件にする。

将来は、Network Accessの後段にZITADELを接続してUser Authentication / Authorizationを追加する。OAuth、OIDC、JWT、Login、Temporary Authenticationは今回作らない。

```text
Network Access (NetBird)
        ↓
Identity (future: ZITADEL)
        ↓
Role / Authorization (future)
        ↓
RONRO Route / Capability
```

### Runtime Ownership Rule

これは認証ではなく、同時操作の競合を防ぐRuntime Ruleである。

- 最初にStartしたControllerをActive Controllerとして保持する。
- Active Session中の別Controllerは、状態を見られてもStart / End / Audioを操作できない。
- 別Controllerには「別の端末で会議を操作中です」と表示する。
- Active Controllerのreload、短時間のWi-Fi / NetBird interruption、Safari lifecycle interruptionではSessionを即終了しない。
- Browserが生成した非機密Runtime instance identifierを保持し、同一Controller Browserの短時間Reconnectだけを許可する。これはCredentialではない。
- Pilotでは自動handoverを行わず、所有権はSession終了まで保持する。所有端末を失った場合は`/control`のFacilitatorがSessionを終了する。
- Session終了時にOwnershipを破棄し、次Sessionで初期化する。

## First Vertical Slice

```text
iPhone Safari /session
  → User Gesture
  → Microphone permission
  → AudioWorklet / PCM
  → Start + WSS /live
  → 1 Final STT
  → Existing Analyzer / Graph
  → Shared Display update
  → End
  → Drain
  → Ended + final projection
```

### Required Assertions

- Smartphone StartでShared DisplayがActiveになる。
- 1 Final Utteranceが論点図へ反映される。
- Candidate Decisionが自動確定されない。
- ActionのOwner / Dueを推測しない。
- Evidence loss = 0。
- Graph corruption = 0。
- `pending = 0`。
- `processing = none`。
- `graph_revision == rendered_revision`。
- Smartphone End後にDrain完了する。
- Mac Safariの既存Desktop Live Audio PathがGreenのまま。
- NetBird外の端末からHostへ到達できない。
- 別ControllerがSession controlを奪えない。
- Active Controllerの短時間ReconnectでSessionが維持される。

## Rollout / Stop Conditions

### Rollout順

1. Local desktop `/control` regression
2. Local iPhone Safari HTTPS / WSS test
3. Kubernetes staging / pilot host smoke
4. 1発話 vertical slice
5. 3-case mobile smoke
6. Pilot gate review

### Stop Conditions

- Microphone permission / AudioWorklet failure
- WSS failure
- Evidence loss
- Graph corruption
- Automatic Confirmation
- Drain incomplete
- Unauthorized Controller access
- iPhone lock / backgroundでの安定性不足

## Definition of Ready for v0.1.1-pilot

- `/` Shared、`/shared` compatibility、`/control` Desktop control、`/session` Mobile controllerが明確に分離されている。
- Existing APIs / WSS semanticsを維持している。
- Mac Safariの既存Live AudioがGreen。
- iPhone Safariの1発話Vertical SliceがGreen。
- Session Start / EndのShared Display同期がGreen。
- Finalizing / Drain / EndedがGreen。
- NetBird Network boundaryが確認済み。
- Runtime Session Ownershipと短時間Reconnectが確認済み。
- Kubernetes HTTPS / WSS smokeがGreen。
- v0.1.0-pilot immutable baselineを変更していない。

このDefinitionを満たすまで、Live Pilot #1は開始しない。
