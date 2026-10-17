# RFC-0010 実装・検証計画（Spot Content）

Status: **proposed / 候補コードの開発中**。設計正本は[RFC-0010](../rfc/0010-spot-interaction-and-local-ai-transition.md)、未完了の実機ゲートは[Content #104](https://github.com/hakobune8/natade-coco-ronro/issues/104)。Content `develop`にD2–D8の一部候補コードが統合されても、実機・Provider・隔離の受入れは別である。この文書は実音声試験、外部Provider呼出し、Fleet配布の承認ではない。

## ベースラインと分岐

- `ronro`はCore/Event/Graphの契約とRFCを保持し、`natade-coco-ronro`はSpot向け実行・UI・Provider adapterを保持する。後者から前者へだけ依存する。
- 実装は`natade-coco-ronro`の`develop`から短命ブランチを切り、**PR単位で`develop`に統合**する。RFC文書PRも`ronro/develop`へ統合する。現在の`main`やFleet稼働Digestは、検証なしに進めない。
- PRごとに`git diff --check`、Contentの`make validate test lint build`（必要なlocked setup後）、変更対象の回帰とローカルの合成runを確認する。CIでしか実行できない供給網・CodeQL・Container smokeはPR上の結果も確認する。ローカルCI相当がGreenなら統合可能だが、実機受入れ・Provider費用/同意・配備のゲートは別に残す。
- `#98`の音声反映失敗とPlatform `#939`のController同期切替は未解決。これらをToggleや見た目の変更で解決済みと推定しない。原因・修正・実機再確認を明示するまで、#104の音声/総合受入れはNOT PASS。
- 2026-10-17時点の配布版はRC6のまま。Content `develop`にはRC7ソース候補と後続のD7診断修正（[#161](https://github.com/hakobune8/natade-coco-ronro/pull/161)）が統合されたが、RC7のhosted CIは課金／支出制限でjob未開始、タグ・公開Image・Fleet変更なし。Platform [#943](https://github.com/SSLHQ/natade-coco-edge/pull/943)はowner reviewとhosted CIを通って`main`（`003baa781ffbe04cd543297825b8e4b7dd6e2ede`）へ統合済み。修正を含む隔離Launcher画像は[既存CI run 38978432317](https://github.com/SSLHQ/natade-coco-edge/actions/runs/38978432317)で署名・SBOM・scanを通して公開済み（`sha256:dcf419153946520f669efa43af5929d474c4f704b4c93162bf858dbd6894dad5`）。[Draft #950](https://github.com/SSLHQ/natade-coco-edge/pull/950)はTamarind限定の通常Fleet走査対象外optionと差分検査を提示しており、**Fleet選択・実機適用はまだない**。ローカルCI相当での`develop`統合例外を、Image公開・実機受入れの合格条件へ拡張しない。
- **配布基準の訂正**: 古いローカルPlatform checkoutの`fleet.yaml`からLauncher 0.3.47を誤って採用した。tamarind-22の実配布と現行Platform `main`のFleet定義は、共通Runtime／Launcher **0.3.63**。source `5bc25e10618482cb9dc939d140047a6fb7a2cbaa`、Launcher digest `sha256:f8e33aec6d63020bcbc1c55e862b54759d3f2e8a0188b1becc88b4d33bd179dd`（[RC6実配布のreadback](https://github.com/hakobune8/natade-coco-ronro/issues/82#issuecomment-6210354443)）。RC6のController契約2は0.3.47のController実装とは互換にならない。0.3.63 sourceから#943統合sourceまでのLauncherビルド入力差分は#943の修正・テスト6ファイルのみであり、「大規模Platform更新が必要」という前版の結論を撤回する。それでも正確なImage Digest、供給網検査、Fleet差分、実機同期確認を経るまでD1をPASSにしない。誤った基準で中断した候補公開run `38977034356`が途中pushした未スキャン・未署名のprivate candidate tagは使用禁止（[Platform #939の訂正記録](https://github.com/SSLHQ/natade-coco-edge/issues/939#issuecomment-6226180041)）。
- Local STTの多言語whisper.cpp small／mediumは未選定。モデル画像のタグ起点公開手順を加えた[Content #137](https://github.com/hakobune8/natade-coco-ronro/pull/137)は`develop`へ統合済みだが、公開tag・候補image・Fleet切替はない。`packages: write`は公開jobだけ、`security-events: write`はgate jobだけの契約とした。2026-10-17時点でContentの登録済みGitHub Actions 3本は利用者依頼で一時停止されており、再開判断なく候補公開を実行しない。build-only jobやローカル試験を画像公開・8台／2時間性能の証拠にしない。

## PRの依存順

| PR | Repo / 最小変更 | 依存 | ローカル試験・完了条件 |
| --- | --- | --- | --- |
| D0 設計 | `ronro`: RFC-0010と本計画。`natade-coco-ronro`: `docs/`に現行コードとの対応表とPublic-safeテスト手順 | なし | リンク・矛盾確認、変更が文書のみであること。Core/Event意味を変更しない |
| D1 基線 | Content: RC6のController同期失敗をContentから再現/観測し、Platform #939との境界を切り分ける。#943のsource修正は統合済み。実配布Launcher 0.3.63との6ファイル差分を基準に、完全な公開ゲートを通した一意な候補を限定配布する | D0、未検証tagの不使用、Platform配布候補のsource差分審査 | 5秒ごとの正常refetchで操作欄が消えず、実際の断線/旧runは閉じること。正確な稼働DigestとiPhone/Safari実機再確認までPASSにしない。音声試験なし |
| D2 Display状態 | Content `backend/audio_ingress.py`, `run_assembly.py`, `display_read.py`, `src/display-state.ts`, `display.ts`, `canvas.ts`とCSS: `audio_activity_v1`、QR文言、控えめな状態表示 | D0、D1の状態を記録 | 0/1/4/8、停止/切断/古いsnapshot、分析queue、reduced motion、1920×1080。現runのDisplay ticket以外は不可、Canvas/Evidenceへ混入なし |
| D3 Toggle capture | Content `src/controller-audio-ui.ts`, `ptt-capture.ts`等: タップでON/OFF、緊急停止、短文状態。`backend`のsource lease/停止境界を確認・必要箇所だけ補強 | D1、D2の状態契約。#98の失敗段階を把握 | 同一gestureのmic開始、連打/準備中OFF、visibility/lock/pagehide/断線、source間独立、bounded finalizeと未完了警告、WSS認可/重複/容量。#98が残れば実音声受入れ不可 |
| D4 Correction UX | Content Controller: server-held音声訂正提案の要約と確認を主導線にし、焦点近傍の既存関係を短い文言で選べる候補を試す。自然文textは代替とする | D1、D3とGraph read契約 | Human-origin Event、曖昧時no-op、revision race、remove/add/change endpoint、再提案抑止、Decision/Action不変、320/390/430pxとVoiceOver |
| D5 Copy/artwork | Content `docs/launcher-artwork.md`, `artwork/source`, `public/assets`, CSS: 現行水彩から洗練した2方向をレビューし1方向を候補化 | D0。D2-D4と並行可 | 権利/制作履歴、画像サイズと最適化、Catalog/Lobby crop、文字・QR余白、offlineとasset失敗、開かれた議論のHuman Review |
| D6 LiteLLM候補 | ContentのAnalyzer adapter/factoryだけを候補分岐化。Secretをコード/ログへ置かず、上流・保持・NetBird reachabilityとEgress方針を確認 | D1、Cloud-demo回帰。STTは独立 | 合成Final→同じCore検証/Replay、安全禁止事項、timeout/retry/failed-no-fallback。限定実Provider検査は別承認。LiteLLM経由をLocal Secureと表示しない |
| D7 Local STT | Content/AI RuntimeのSTT adapter。多言語`whisper.cpp` small/mediumを同じ条件で比較し、必要なPlatform政策は別PR | D3、Provider-neutral STT contract、実機資源確認 | PCM/Final/item correlation、両モデルの日本語品質・1/4/8台と2時間・CPU/RAM、gap/Drain/End、Raw Audio外送否定。ただしAnalyzerが遠隔ならTranscript外送を明示 |
| D8 Local Analyzer | Content/AI RuntimeのAnalyzer adapter。Spot上でmodel・resources・healthを管理し、必要なPlatform egress政策は別PR | D6/D7、モデル評価・政策 | 日本語Node/Relation/訂正、安全、latency/負荷、Offline起動/継続/End、実効Egress拒否。初めてLocal Secure候補を審査できる |

D1がPlatform原因で保留の場合、D2の**純粋なContentローカル実装**は進められる。ただしController/Displayを使った実機合格や#104総合判定に昇格させない。D6のNetBird/LiteLLM候補も配置・上流・保持の審査までCloud-demoと同等の外送前提で扱う。

## D2 詳細契約：活動状態

`AudioIngress`の`_active`は予約済みで、`audio_ready`前を含む。表示へは直接出さず、`audio_ready`を送った後のrun内接続集合を別途追跡し、`finally`で必ず消す。受理したframeの単調時刻だけを保持し、音声サンプル/レベル/端末IDをDisplayへ渡さない。Paused/Endの権限境界を越えて状態を保持しない。

`DisplayStateReader`に読み取り専用のProvider-neutralなsnapshot callbackを渡し、既存のDisplay JWT、session/run照合、`no-store`を再利用する。応答は既存`canvas`と並列の`audio_activity_v1`で、`connected_sources`は0–8（収音中で`capture_stop`未受理のsource数）、`stage`は`idle/receiving/audio_processing/queued/analyzing/uncertain`。収音終了後のSource Final待ちは件数から外すが`audio_processing`で表し、Source不完全/failed-open/unresolvedは`uncertain`へ残す。Cue優先順位・4秒frame窓はRFCに従う。`DisplayState` parserは型/範囲/現runを検証する。2秒pollの同じGraph revisionでも活動状態が変化したら表示を更新し、状態取得失敗時は古い「マイク接続」を表示し続けない。`prefers-reduced-motion`では明滅しない。Canvasと下部Canonical本文の読みやすさを変えない。

## D3 詳細契約：Toggle

`PressToTalkCapture`のmic起動・generation fence・late permission response cleanup・WSS停止処理を再利用し、UIイベントを「押下保持」から`click`/keyboard activationのON/OFFへ替える。最初のclickの同じgesture内で`getUserMedia`を呼び、準備中の2回目clickはgenerationを進めて安全に解放する。Pointer/keyboardの重複発火で二重接続を作らない。可視性喪失、Platform断線、Hostの休憩/終了、run切替、WebSocket失敗はsourceをOFFにする。新規ON前のreadiness失効は開始を拒否する。一方、受理済みの現run音声ソケットは、並走するreadiness照会の一時失敗や、同一runの定期Host取得に伴う過渡的なGDK `syncing`だけでは停止しない。捕捉開始時と現在のrun IDが一致することを要し、実際の同期`failed`、権限/接続喪失、Host phase変化では停止する。復帰時はreadinessを再取得するが**自動でmicをONにしない**。`aria-pressed`と本文は「準備中」と「音声が受理済み」を区別する。

Content側の既存`membership check`/WebSocket heartbeat、one-use ticket、最大8source、sourceごとのstop/abort/Drainを維持する。無音・BGMは会議Endではない。OFF後の未確定音声は完了またはincompleteとして追跡し、空commitを成功扱いしない。8台同時ONの重複収音は、根拠なしに同一発話へ統合しない。

## D4 詳細契約：訂正

まず既存`/api/relation-proposal`の読み取り、proposal ID＋expected revisionでの反映、`/api/relation-correction`自然文経路を活用する。画面にはCanonical Node ID/enumを見せない。新しい選択UIに既存Canvasの関係を使う場合は**Controller認可済み・現run限定の読み取り応答**を設計/検証してから使い、Display ticketをControllerへ流用しない。曖昧なNode候補や複数関係は確認待ちとし、推測でEventを追加しない。変更はHuman Eventを通し、取り消した旧Evidenceによる即時再結線を禁止する。失敗/結果不明のcommand ID再利用を維持する。

## D6–D8 詳細契約：Provider

Stage 1でLiteLLMを導入する場合も、現行`OpenAIRealtimeSTTProvider`は直接経路のままなら**Raw Audioが外部へ出る**。Analyzerの`OpenAIAnalyzerProvider`をbase URLだけ変更して互換とみなさず、adapterに明示的なendpoint・TLS・schema・timeout・error分類・logging禁止を持たせる。NetBirdと上流の配置、秘密/ログ/保持、Platform egress allowの承認を明示する。Core `RealAnalyzer`はCandidate Eventsを検証し、失敗時はfailed jobとして残す。勝手な別Provider fallbackをしない。

Local STTはProvider-neutralなsource/item/Final/Drain契約、Local Analyzerは同じCandidate Event検証を維持する。Raw Audio/Transcriptの外送境界を各Stageで個別に証明する。`whisper.cpp`のsmall/medium候補については、CIのビルド・スキャン成功を実機性能やEvidence完全性の合格と取り違えず、同じ日本語音声集合と同じSpot負荷・計測条件で比較する。Local Secureの表示/配布は、実機性能だけでなくPlatformの実効ネットワーク隔離、model更新経路と監査を含む別審査後に限定する。

空の認識結果から発話なしを推論しない。D7で必要な非発話判定のSource/item範囲、Content監査の先行書込み、Coreの競合検査、small/medium共通評価、実機ゲートは[非発話区間の判定契約候補](../architecture/stt-no-speech-disposition-candidate.md)に具体化する。現行upstreamは型付き判定を出さず、この文書だけでは非発話の自動完了を実装・有効化しない。まずCore契約PR、その後Content監査/adapter、Runtimeの判定品質、実機の順に分ける。

## 完了判定と残課題

D2–D6がローカルCI相当でGreen、合成runのCanvas/訂正/PDF replayが一致し、変更PRが`develop`へ統合された状態は**RFC-0010のUI/私設経路候補の開発到達点**であり、RFC全体の完了ではない。**RFC-0010実装完了**にはD7/D8も検証を伴って統合し、#98/#939に起因する未解決の経路を残さず、#104の実機19条件を対象版で判定する必要がある。未実施はPASSに変えない。**Local Secure提供**はさらにPlatform egress・保持審査の別判定である。どの段階も本番Fleetの更新、同意済み実音声、外部Provider通信を自動承認しない。
