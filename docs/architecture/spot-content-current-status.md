# RONRO Core と natadeCOCO Content — 現在の境界

最終確認: 2026-10-09。これは [RFC-0009](../rfc/0009-ronro-as-natadecoco-local-ai-content.md) の実装状況を読むための案内であり、RFC本文の過去の提案を遡って書き換えるものではありません。

| 領域 | 現在の役割 |
| --- | --- |
| [`hakobune8/ronro`](https://github.com/hakobune8/ronro) | Canonical Event、Evidence、Materializer、Replay、Graph、Semantic Canvas、PDF生成、評価の正本。旧単独Web Pilotも研究・回帰用として残す。 |
| [`hakobune8/natade-coco-ronro`](https://github.com/hakobune8/natade-coco-ronro) | GDKに載るSpot向けContent。固定したRONRO Core wheelを取り込み、Display、スマホController、音声入口、Provider接続、会議中の一時状態を組み立てる。 |
| natadeCOCO Platform | Launcher、参加・接続、Platform Session、Catalog、Fleet配布、実効ネットワーク境界。RONROの会議状態やGraphの意味は決めない。 |

## 実装と検証の到達点

[Content PR #81](https://github.com/hakobune8/natade-coco-ronro/pull/81) は、通常は静的表示のままにし、明示的な `cloud-demo` 設定のときだけ音声→STT→Analyzer→Event→Canvas→PDFの候補経路を組み立てる。Controller操作と同一runの認可、合成データによる統合テストも含む。`v0.10.0-rc.1` のイメージは[CIで発行済み](https://github.com/hakobune8/natade-coco-ronro/actions/runs/37926759548)だが、発行とSpot実機受入れは別である。実音声のProvider適合、最大8台、長時間会議、画面の実距離可読性、End/Drain/PDFは実機未確認。**機密会議向けのLocal Secure版ではない。** Cloud-demoでは音声・発話内容が外部Providerへ送られる。

[Platform配布PR #859](https://github.com/SSLHQ/natade-coco-edge/pull/859) は検証用SpotへのFleet候補で、**Draft・未マージ・未配布**。2026-10-09時点では、Cloud-demoが必要とする外向き通信許可を既存の「ゲームPodにegress allowを追加しない」セキュリティゲートが拒否している。これはゲートを外して済ませる問題ではなく、Platform側の承認済み通信境界が必要である。Secretの移行はPlatform側がマージ前に実施する予定であり、このリポジトリにもPRにも値を置かない。対象実機の接続・イメージ取得権限・実Providerの短い検査も未了。PRをマージするとFleetが配布するため、これらのゲートが揃う前にマージしない。

## 現在の操作・データ契約

- スマホControllerは最大8台を目標とする押して話すマイクであり、端末IDは話者や個人を証明しない。途中参加はPlatformのJoinを使う。8台の宣言は8本の音声を実機で処理できた証拠ではない。
- PlatformのHostはSpot全体のSession開始・Game終了を扱う。RONRO内の中断・再開・会議終了・関係訂正・PDF取得は、**現在のrunへ参加を認められたController** が行える候補契約になった。Host専用という[RFC-0009の初期案](../rfc/0009-ronro-as-natadecoco-local-ai-content.md)はこの点で置き換えられた。会議終了は全マイクに影響するため二段階確認を要する。PlatformのGame終了は別操作で、RONROのDrainやPDF受取を妨げ得る。
- 会議後の成果物は同一Canvasの固定revisionから作るPDF。会議後Web閲覧やアカウント別の記録庫をSpot版の初期機能としない。現在の候補はEndから最大30分の受取窓を持ち、参加資格のあるControllerがその間にPDFを保存できる。利用者による早期削除ボタンはなく、期限到達でContent内の記録を消す。HTTP成功は端末への保存成功の証明ではない。
- Raw AudioはCanonical Eventに入れない。TranscriptはEvidence、Event StreamはHistory、Graphは受理済みEventから導くCurrent State、Human CorrectionはEvent。Cloud-demoの外部送信と、旧Web Pilotの同意付き評価録音（7日削除）を混同しない。

操作の一次資料はContent側の[参加Controller契約](https://github.com/hakobune8/natade-coco-ronro/blob/v0.10.0-rc.1/docs/participant-operations-contract.md)と[実機検証チェックリスト](https://github.com/hakobune8/natade-coco-ronro/blob/v0.10.0-rc.1/docs/spot-device-rc1-checklist.md)。後者には発行前の時点で書かれた手順も残るため、公開・配布の最新事実はCIとPlatform PRで照合する。

## 残る受入れゲート

1. PlatformがCloud-demoの外向き通信を安全審査し、CIの隔離契約に整合する形を決める。Secret移行・GHCR private image pull・対象実機の接続を別々に検証する。
2. 公開安全な短い実Provider検査の後、検証用Spotで1/4/8台、途中参加、ロック・切断、訂正、中断・再開、全source Drain、固定Canvas/PDF、期限削除を確認する。実音声を入れる前に外部送信と同意を説明する。
3. 実機での表示・操作と安全性が通るまで、Cloud-demo候補を「実会議で利用可能」「Local Secure」「機密会議対応」と案内しない。Local STT/Analyzer、ネットワーク遮断、Offlineは後続の別ゲートである。
