# RFC-0009 実装計画 — RONROをSpot Contentへ移す

| 項目 | 内容 |
| --- | --- |
| Status | In progress — Core baseline/package PRと独立Content scaffold PRを作成。Platform変更は保留。配備・実音声は未着手 |
| Updated | 2026-10-07 |
| Source | [RFC-0009](../rfc/0009-ronro-as-natadecoco-local-ai-content.md)、[接続・状態・音声・PDFの詳細契約](../architecture/natadecoco-content-contract.md)、[UI / Artworkブリーフ](../product/natadecoco-ronro-ux-artwork-brief.md) |

## 実装順序とブランチ境界

各行は原則1 PR。新Content repo名の第一候補は`hakobune8/natade-coco-ronro`。GDK/Platformへの変更は既存Gameの後方互換テストを通してからContentへ取り込む。PlatformとContentを未検証のまま同時配備しない。Coreの正本は`ronro`だけで、依存はContent→versioned Core/GDKの一方向。現行Pilot/Account Serviceや既存評価Artifactを暗黙に移行・削除しない。

### 2026-10-07 実装順の変更: Contentを先行

利用者の判断により、`natade-coco-edge`の変更を進めず、独立Content repositoryを先に立ち上げる。Platform認可案の[PR #828](https://github.com/SSLHQ/natade-coco-edge/pull/828)は未マージのまま閉じ、終了ガード案も公開しない。新しい[Content draft PR #10](https://github.com/hakobune8/natade-coco-ronro/pull/10)はGDKテンプレートの独立初期化のみで、現時点のゲーム画面はRONROの機能ではない。

次の順序は (1) Core wheelの検証、(2) Contentで合成データ専用Canvas/Controllerのローカルプレビュー、(3) 現行GDK/Platformだけで可能なphone PTT・Session動作の契約試験、(4) 実音声・Host操作・PDF受取に必要な権限/終了保護の不足を再評価、である。**Platform変更なしに実現できない保証をContent内の見かけのrole判定で代替しない。** 不足が残れば実音声を伴うSpot配備は停止し、最小のPlatform変更またはUX/受取手順の改訂を別途判断する。したがって、下表のPR3/4は現在の着手順から外した保留案であり、PR7の合成データ骨組みはPR3/4を前提としない。PR8以降の実音声受入れには依然として認可/終了の実効保証が必要である。

**今回の初期実装完了**は、Cloud STT/Analyzerを明示したSpot Content（PR1–10とUI/Artwork PR、PR10a）が検証用Spot実機でE2E動作し、重大欠陥がなく、後続改善を台帳に整理した時点。PR11–13のLocal STT/Analyzer/secure enforcementは別Phaseであり、初期実装完了や機密会議利用許可と混同しない。

| PR | Repository / Component | 変更内容・依存 | Test | 完了条件 |
| --- | --- | --- | --- | --- |
| 1: Core baseline | `ronro` / Event, Evidence, Replay, Canvas, PDF | 最初に着手。既存テストの固定・公開安全な合成Fixtureを追加し、Event/Materializer/Canvas、Human訂正、Final PDFの回帰を可視化。依存なし。 | 全既存suite、同一Event列のReplay同値、長文/日本語PDF、欠落警告。 | **挙動変更なし**で既存契約がテスト可能。秘密・実会議音声/全文をFixtureへ含めない。 |
| 2: Core package | `ronro` / import・distribution | PR1後。Provider非依存のEvent/Schema/Store/Materializer/Projection/PDF rendererをversioned Python packageへ抽出。`prototype/server`、Pilot録音、Account/Postgres、OpenAI秘密設定を配布境界から外す。 | wheel install in clean env、package public API/replay、既存Pilot suite。 | Source SHA/hash付きwheelで同一Graph/PDF。RONRO→GDK/Content依存なし。 |
| 3: Platform auth contract | `natade-coco-edge`（Platform）、必要なGDK文書 | PR1後に並行可。現行Player Bearerを内部で検証し、session/run/player active membershipとHost leaseをoperation別に返すservice-to-service endpointを追加。Controller moduleにはtoken/host cookieを渡さない。 | 不正run、離脱/蹴り出し、host移譲、role偽装、token期限、非Host PDF/Command拒否、既存Game回帰。 | Contentが毎回Host権限を確かめられ、既存Shell経路を壊さない。Platform ownerレビュー済み。 |
| 4: Platform termination guard | `natade-coco-edge` / Launcher, Session, manifest/schema、GDK validator/docs | PR3後。Content opt-inだけに終了readiness guardと期限後のorphan終了を追加。`playing`中のContent End/Drain/PDF受取を許し、purgedで初めて通常`/control/end`を通す。管理者強制終了は監査。Gameの`finishGame`/rankingsは無変更。 | 途中End拒否、PDF準備後も未受取End拒否、受取終了/TTLで許可、backend timeout fail-closed、forced termination監査、旧Game終了回帰。 | PDF受取前の誤Endで記録を失わず、期限後にContent/Platform双方が閉じる。 |
| 5: Phone/browser contract | `natade-coco-gdk`＋Platform test harness / Controller module | PR3と並行。8枠、途中Join、同一origin `requestGameResource`→audio-ticket→WSS、iOS/AndroidのPTT user gesture/mic/AudioWorklet/visibility/lockを契約テストと実機Spikeで検証。拡張が必要なら後方互換で最小化。 | 1/4/8参加、9台目拒否、開始遅延、release/cancel/lock/background/disconnect停止、Join QR→local Wi-Fi→Join、120分超。自然な相槌・言い直し・同時発話を含む模擬会議で操作負担を観察。 | 技術上の実効値と失敗時UI契約が確定。接続枠試験を8音声処理の証明にしない。PTTが会話を止める兆候があればCapture方式の設計判断へ戻る。 |
| 6: Provider boundary | `ronro` / Live STT, Analyzer | PR1/2後。source別stream/turn/item/range/Drain contractと`AnalyzerProvider`のSchema版境界を抽出し、現行Remote Adapterを移す。Canonical Eventを不要に変えない。 | 空/極短押下、duplicate/out-of-order、古いFinalと新音声、gap、pause/resume、遅延Analyzer、訂正優先、同一Event Replay、現行Pilot回帰。 | STT/Analyzerの交換点が明確で、source取り違え・空commit起因のSession Endなし。 |
| 7: Content skeleton | `natade-coco-ronro` / GDK manifest, Container, Python runtime | PR2後の合成データ経路を先行。独立repoをGDKで初期化し、Core packageとplatform setをpin。最大8枠や`while-playing`/`keep-alive`は実動作検証後に宣言。未採用のopt-in guardは宣言しない。Pythonと静的Display/Controllerの同一8080 Serviceを検証する。 | `make validate/test/lint/build`相当、旧Game非影響、route/health、local synthetic smoke。 | 合成データでCanvas/Controllerの境界が動く。実録音、Host権限、PDF受取、Cloud/Local安全性は主張しない。 |
| 7a: Product artwork | `natade-coco-ronro` / Launcher presentation assets | PR7後。専用`catalog.webp`/`lobby.webp`と6桁`accentColor`を制作・bundleし、`game.yaml`の`presentation`へ登録。元データ、権利、最適化条件、代替fallbackを記録。Live Canvasの背景へは流用しない。[非誘導・非監視の表現原則](../product/natadecoco-ronro-ux-artwork-brief.md)を制作レビューに含める。 | GDK schema/asset route検証、16:9 Catalog crop、Lobby左/下overlay、実Launcher表示、offline配信、画像失敗fallback、会議結果や機密性を誇張しないHuman Review。 | 既定fallbackに頼らず、論路を「採点・監視するゲーム」と誤認させない専用ArtworkがCatalog/Lobbyに表示される。 |
| 8: Audio and lifecycle | `natade-coco-ronro` / Controller PTT, WSS, Session Adapter | PR5/6/7後。押下中だけのMic、source別一回ticket/lease/seq、Host Pause/Resume/Endと進行中Join、Host訂正、8 source公平Queue、gapを実装。Content EndはPlatform Endと別。 | 1/4/8 source同時押下、近接重複/同時発話、空/長押下、切断/ロック、Host移譲、中断中Join、古いFinal、Queue満杯、2時間超、全source Drain。 | 未押下/lock時にtrack送信0。1台の障害・無音/BGMで会議終了なし。欠落を隠さず、Event/Graphと訂正が再現可能。 |
| 9: Canvas and PDF handoff | `natade-coco-ronro` / Display, Controller, ephemeral Store | PR8後。既存Semantic CanvasをLive/Final共通で表示し、右上Join QR、実入力状態を反映。固定revisionの既存PDF rendererをHost Controllerへ配信、30分以内の再試行/受取終了/期限切れ・消去を実装。会議内容はtmpfs WALでSession中のみ維持。 | 1920×1080、3–5m Human Review、PDF日本語/大Graph/警告/State、非Host拒否、期限・別run拒否、tmpfs/backup/log非残存、process再起動Replay、Pod消滅の明示失敗。 | 固定CanvasとPDFが整合し、Host受取後に通常Platform End可能。会議後Web閲覧/再ダウンロードなし。 |
| 9a: UI finish | `natade-coco-ronro` / Display, Host・参加者Controller | PR5/7a/8/9後。[UIブリーフ](../product/natadecoco-ronro-ux-artwork-brief.md)の状態・余白・文字・色・Host/PDF導線を仕上げる。Platform Shellの認証/ナビを複製しない。発言者別の量/順位を出さず、AI候補と人間の確定を明確に分ける。 | 合成状態全景の1920×1080画像/短い動画、320/390/430px Controller、沈黙/相槌/対立/訂正、Pause/lock/disconnect/Host transfer/欠落、色覚/Reduced Motion、3–5m Human Review。 | 論点・現在の取込状態・押下成功/失敗・Host End/PDFが誤解なく分かり、ArtworkとCanvasの役割が混ざらない。参加者に評価/監視の印象を与えない。 |
| 10: Cloud-demo integration | `natade-coco-ronro`＋Platform Fleet | PR7–9a後。Remote STT/Analyzerのみ明示有効、限定Egress/資格情報注入、2時間超・8台負荷、同意済み合成/試験音声、rollbackを実施。 | 端末→Spot→Remote送信先、同意/モード表示、漏えいのない診断、操作/音声/PDF E2E、旧Game/Pilot回帰。 | **Cloud-demo候補としてのみ**受入れ。Local Secureや機密会議対応と表示しない。Provider障害で自動的に別Modeへ落ちない。 |
| 10a: 検証用Spot実機受入れ | `natade-coco-ronro`＋Platform/Fleet / Release evidence | PR10後。固定image digestを検証用実機へ配備。実Launcher→Join QR→最大8台PTT→中断/再開/途中参加→論点/訂正→End/Drain→同Canvas Final→Host PDF→消去/Platform終了を一連で確認。機密会議は使わない。 | 実機構成・Runtime/GDK版・image digest・日時・UI/artwork screenshot・Private E2Eログ・Queue/Evidence/権限・2時間超・ロック/切断・9台目拒否・失敗/rollbackを記録。模擬会議の自然さ/視線/押下負担/非誘導性を参加者に確認。8台は8実端末で確認し、機材不足なら容量項目未達と明記。 | P0/P1なし。Launcher artwork、Display、両Controller、PDF、消去、**会話を止めないUX**が実機でPASS。後続改善台帳がトリアージ済み。この時点で**初期実装完了**、Local Secureは未完了。 |
| 11: Local STT | `natade-coco-ronro`/AI Runtime候補 | PR6/10後。Local STT Adapter、モデル配布/資源/healthとsource別Finalを追加。 | 1/4/8 source、BGM/無音/長発話/重なり、端末/AP/Spot packet capture、no raw-audio remote path。 | Raw AudioのSpot外Provider送信0を観測。Analyzer remoteの場合はTranscript外送を明示し、`local-stt`と呼ぶ。 |
| 12: Local Analyzer | `natade-coco-ronro`/AI Runtime候補 | PR11後。Local Providerを既存Analyzer Schemaへ接続し、モデルを固定しすぎず資源上限と失敗分類を実装。 | R1–R5、Human訂正、Decision/Owner/Due安全、長時間Queue、Provider切替/Replay。 | Cloudなしでも会議中核機能が成立し、安全ゲートとHuman Reviewを通る。 |
| 13: Secure enforcement | `natade-coco-edge` Fleet/Network と Content | PR11/12後。Content Pod/Local AIのdeny-by-default、限定Spot内通信、DNS/IPv6/hostNetwork/Sidecar/端末経路、監査とfail-closed mode claimを実装。 | CNI実測の拒否試験、policy drift、model pre-load、Offline再起動、端末経路、raw audio/log/cache非保存、旧Game回帰。 | 実効分離の証拠が揃った場合のみ`local-secure`/`offline`表示。端末OS全体の無通信を保証しない。 |

## Gateと運用上の失敗定義

PR2の配布境界は`pyproject.toml`の明示allowlistで`prototype`中の純粋な実装15モジュールとCanonical Schema 5件だけを`ronro_core` wheelへ写す。`prototype`ファイルが実装の正本であり、配布物は`ronro_core`の公開APIから使う。`prototype/server`、Pilot録音、Account/Postgres、OpenAI秘密設定はwheel/sdistに含めない。`scripts/verify_core_wheel.py`はwheelの全ファイルを検査し、クリーンなPython 3.12環境で同じ合成Event列からGraph/Canvas/PDFが一致することを確認する。`scripts/build_core_wheel.py`は**クリーンなコミット**からだけビルドし、Git SHAとwheel SHA-256をsidecarへ記録する。Source checkoutの`ronro_core`は配布時に選択モジュールを組み込むため、Contentからはeditable/source importではなく検証済みwheelをpinする。CIの`.github/workflows/core-wheel.yml`はPRで配布境界を再検査する。

- **G0 / Architecture**: 本RFC・補助設計・Platform ownerによる認可/終了ガード承認。`getUserMedia`/AudioWorklet/同一origin WSS、Runtime 1.1+を実機確認。失敗ならPR7以降を止める。
- **G1 / Cloud-demo candidate**: PR1–10（7a/9a含む）。8台接続だけでなく8 source音声、2時間超、Host中断/再開/終了、PDF受取/削除、Replay、誤Host操作拒否、Launcher ArtworkとUIの合成データQAを確認。予期しないTerminate・黙ったEvidence loss・不正確認・Owner/Due捏造・訂正無視はFAIL。Cloud Providerへの送信を参加者に明示。
- **G1a / Initial implementation complete**: PR10a。検証用Spot実機でEnd-to-End PASS、3–5mの共有画面とスマホControllerのHuman Review PASS、**自然な会話・相槌・訂正を妨げないこと**を模擬会議で確認し、後続改善台帳を公開安全な形で整理。Simulator/CIだけでは完了にしない。端末型番/OS/Browser、Spot/Runtime、image digest、実行時刻と結果を残す。PTTのために会議を繰り返し止めるならFAILとし、別Capture profileを設計し直す。
- **G2 / Raw-audio-local**: PR11。端末/AP/Spotで送信先を実測。Spot内STTであることだけを検証し、Analyzer remoteなら機密モードではない。
- **G3 / Local secure**: PR12–13。端末からSpotまでのローカル経路、Pod/Host Network deny、Local Model品質、削除/障害・Human Reviewを通す。未達ならCloud-demoまたは停止とし、自動fallbackしない。

全Gateで`Transcript = Evidence`、`Event Stream = History`、`Discussion Graph = Current State`、`Human Correction = Event`を守る。Raw AudioはCanonical Eventに入れない。Public Gitには実会議音声・全文Transcript・Private Evaluation artifactを含めない。製品指標（STT開始遅延、8台の重複収音、会議中の長押し負担、PDFの閲覧性）は合成と実機の計測値を提示し、数値保証は受入れ前に捏造しない。

## 後続改善台帳と完了判定

PR10aの証跡とともに、未解決項目を少なくとも「問題/発生状態/利用者影響/再現手順・証拠/優先度/Owner/次の実験またはPR」に分けて登録する。**P0/P1**（会議中断、音声入力不能を隠す、Graph/Evidence破損、Host権限逸脱、PDF喪失を正常完了と表示、3–5mで現在地が読めない、**PTT操作のために自然な議論が成立しない**等）は初期実装完了をブロック。**P2以降**（受入れを妨げない見た目や押下負担の微調整、Local STT/Analyzer、機密モードの隔離検証など）は受入れ済みCloud-demoの制限を明記したうえで後続改善にできる。P2であっても利用者に安全性を誤認させる表示はブロックする。台帳の項目を「将来対応」だけで閉じず、判断責任者と次の検証を明記する。実機で通った範囲以上の性能・機密性を宣言しない。

## 最初のPR

着手順の先頭は**PR1: `ronro`の公開安全なEvent/Replay/Canvas/PDF契約テスト固定**。外部Platformや機密音声を変えずに移行前後の意味差分を検知でき、Core package抽出・Platform接続の双方へ安全な基準を与える。PR1のmergeは後続PRや配備の自動承認ではない。
