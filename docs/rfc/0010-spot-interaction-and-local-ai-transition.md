# RFC-0010: Spotでの会議操作・共有表示とLocal AIへの段階移行

| 項目 | 内容 |
| --- | --- |
| Status | **Proposed / 実装候補の開発中**。RFC-0009の残る実機受入れを引き継ぐ。候補コードの統合は、配備・実機受入れ・機密会議利用の承認ではない |
| Date | 2026-10-16 |
| Scope | Spot Display、スマホController、artwork、STT/AnalyzerのProvider移行、実機受入れ |
| Supersedes | [RFC-0009](0009-ronro-as-natadecoco-local-ai-content.md)の「押して話す」第一候補と、当時の画面文言・Cloud移行順。Event/Graph、データ境界、Platform責務は継承 |
| Tracking | 未完了の実機受入れは[Content #104](https://github.com/hakobune8/natade-coco-ronro/issues/104)へ移管。[旧#82](https://github.com/hakobune8/natade-coco-ronro/issues/82)の過去の実機証跡は変更しない |

## 1. 背景と現在地

RONROは`ronro`をCore/Research、`natade-coco-ronro`をSpot Contentとする。[現状整理](../architecture/spot-content-current-status.md)に従い、TranscriptはEvidence、Event StreamはHistory、Discussion GraphはCurrent State、Human CorrectionはEventとする。LiveとFinalは同じSemantic Canvasの異なるCameraである。スマホの識別子はマイクsourceの識別であり、人・発言者の本人確認ではない。Spot Controllerの参加資格とRONRO内の会議操作を、PlatformのGame全体終了やHost権限と混同しない。

2026-10-16時点でSpotへ配布されたContentは`v0.10.0-rc.6`（source `06b8d6c`）。DisplayはQRへ「途中参加」、Controllerは長押し「押して話す」とテキスト訂正欄を表示する。発話からの関係訂正はサーバー保持の提案をControllerで確認・反映する経路もある。Runtimeは`OpenAIRealtimeSTTProvider`と`OpenAIAnalyzerProvider`を組み立て、後者を含め外部APIへ直接送るCloud-demoである。Contentの`develop`にはその後Toggle・表示・Local Providerの**候補コード**が入っているが、Spotの稼働版や実機受入れとは区別する。**NetBird上のLiteLLM経由もSpot上のLocal LLMも、稼働中のProviderとしてはまだ確認されていない。**

RC6は`tamarind-22`に限定配布済みだが、配布と受入れは別である。Content `develop`には`0.10.0-rc.7`の**ソース候補**（[PR #158](https://github.com/hakobune8/natade-coco-ronro/pull/158)、[合成UI確認 #159](https://github.com/hakobune8/natade-coco-ronro/pull/159)）が入った。ローカル回帰はGreenだが、GitHub Actionsの課金／支出制限で当該候補のhosted jobは開始できておらず、RC7タグ・公開Image・Fleet配布・実機受入れはまだない。RC6の稼働DigestをRC7と読み替えない。[実機受入れ #104](https://github.com/hakobune8/natade-coco-ronro/issues/104)の19項目は未完了で、Controllerの同期中／操作可能の往復は[Platform #939](https://github.com/SSLHQ/natade-coco-edge/issues/939)とowner review待ちの[修正候補 #943](https://github.com/SSLHQ/natade-coco-edge/pull/943)、単発音声がFinalへ届かない問題は[Content #98](https://github.com/hakobune8/natade-coco-ronro/issues/98)に残る。RC4の1回の音声試験は失敗、RC6の追加試験は未実施・保留であり、このRFCは再試験やProvider通信の承認を与えない。旧#82を閉じたことは19項目の受入れ・#98・#939が完了した意味ではない。

### RFC-0009から維持する境界

- スマホController最大8台、途中参加、同じCanvasのLive/Final、会議終了時のDrainと固定revisionのPDFは維持する。会議後のWeb記録庫や7日／20件保存を再導入しない。
- 参加を認められたControllerによるRONRO内の中断・再開・訂正・二段階確認付き終了・受取窓内のPDF取得という**現行候補契約**を維持する。早期削除UIは追加せず期限で消去する。PlatformのGame全体終了は別操作であり、Drain/PDFを妨げうる。
- Raw AudioをCanonical Eventにしない。Decision確定、Action/Owner/Due、論点の関係をProviderや表示効果から捏造しない。Cloud-demoは外部送信を伴い、Local Secureや機密会議対応と表示しない。
- Launcher/Session Manager/Gateway/Fleet/NetworkPolicyはPlatform責務。Contentで独自の認証・隔離を名乗らず、未保証の箇所を受入れゲートに残す。

## 2. 目的と非目的

目的は、会議を止めずに「何台のマイクが参加し、RONROが音声を処理しているか」を共有画面で誠実に示し、スマホ操作を会話に馴染ませること、訂正を扱いやすくすること、開かれた議論に合う視覚表現へ寄せること、そしてCloud依存から段階的にLocal AIへ移ることである。

このRFCでは本体コード・artwork・Fleet/Platformを変更しない。LiteLLMや特定Localモデルの採用、8台同時・2時間超・機密会議の保証、未解決の実機試験をPASSとすること、関係訂正の新しいCanonical意味や会議後保存機能の追加は目的としない。

## 3. Display — 状態を増やすが画面操作は増やさない

| 要素 | 提案する表示・データ源 | 誤認させない条件 |
| --- | --- | --- |
| 接続台数 | 上部の小さな`マイク n台`。`n`は**現runで`audio_ready`まで進み、まだ`capture_stop`も接続喪失も起きていない収音中source数**。STT Final待ちや中断cleanup中のWebSocketは数えない。参加枠数や話者数ではない | 初期段階では「参加中のスマホ台数」は表示しない。Controllerだけ参加してマイクOFFなら数えない。集計不明時は前回値を固定せず`確認中`。8を超えず、IDや個人名は出さない |
| 処理中 | 取込中／STT Final待ち／Analyzer・Queue処理中を既存のrun内状態から集約し、控えめな1箇所の緩い明滅またはフェードと短い`処理中`表示にする | BGMの音量・波形だけを「意味のある発話を理解中」と見なさない。`idle`、`paused`、`finalizing`、音声欠落／失敗は区別し、永続Spinnerにしない。Reduced Motionでは静止表示。数値・状態は内容や端末IDを公開しない |
| 参加QR | 上部を`参加はコチラ`に変更。QRの参加先・期限・run切替、Final時の非表示は従来通り | QRへ認証token・音声ticketを埋めない。画面表示だけで参加権限を推定しない |

既存のCanvas、現在地、下部Canonical本文、種別件数の視認性を損なわない。3–5m・1920×1080の実機と、0/1/4/8台・切断・再接続・中断・Finalの状態遷移で検査する。投影用Displayに操作ボタン、参加者名、音声レベルの監視UIを増やさない。Read-only projectionはrun ID/時刻が一致する値だけ採用し、古い状態を「接続中」「処理中」と表示し続けない。

### 3.1 Content内のread-only runtime状態契約（実装候補）

CanvasのCanonical projectionには混ぜず、既存`/games/ronro/api/state`のrun-bound Display応答へ`audio_activity_v1`を追加する。Contentの`AudioIngress`が、現runの`audio_ready`送信後から`capture_stop`受理または接続喪失までの収音source数、受理PCMの単調時刻、停止後のFinal待ち数と中断cleanup中の数を持つ。`AnalysisPump.snapshot()`がpending/processing/failed、`RunDrainTracker.snapshot()`がSourceの不完全/failed-open/unresolvedを供給する。これらは**揮発的な観測値**であり、Evidence・Event・Graph revisionへ書き込まない。`DisplayStateReader`は認証・現run検証後にのみこれらを読み取る。Paused/Finalはphaseを優先し、end後に過去の接続数を見せない。収音が終わってもFinal待ちの間はSource予約とDrain判定を保持する。

```text
audio_activity_v1:
  connected_sources: 0..8  # 互換フィールド名。収音中source数であり、物理端末や生存WebSocketの総数ではない
  stage: idle | receiving | audio_processing | queued | analyzing | uncertain
```

`receiving`は収音中かつ**最近4秒以内にPCM frameをサーバーが受理した**ことだけを意味する。発話認識や理解成功を意味しない。`audio_processing`は受理PCMの収音が終わりSource Final/Drainが未完了、`analyzing`はAnalyzerが実行中、`queued`は未処理Finalがあるが実行中ではない、`uncertain`は中断cleanup中・既知のAnalyzer失敗・Source不完全/failed-open/unresolved・状態取得失敗を示す。優先度は`uncertain > analyzing > receiving > audio_processing > queued > idle`とし、`receiving`/`audio_processing`/`analyzing`のみ穏やかに点滅する。これらは正確な内容理解を意味せず、Source不完全を`idle`へ戻さない。Displayは現行2秒pollを維持し、responseが取れないときは**Canvasを保持したまま活動表示だけ`確認中`へ失効**させる。run切替ではCanvasも含め旧状態を破棄する。表示状態をGraph revisionだけでキャッシュしない。

## 4. Controller — Toggle Captureと訂正

### 4.1 押下保持から明示的なON/OFFへ

大きなマイクボタンを**1回タップで開始、再タップで停止**にする。ON要求後、権限・source admission・音声WebSocket・実際の送信可能性が確定するまでは`準備中`であり、緑色のON表示やDisplayの`音声ON`には数えない。録音・送信中はON状態を色と文言の両方で明示する。会議の`paused/finalizing/ended`は全sourceを停止するが、会議自体を音声sourceの停止で終了させない。

画面ロック、ページ非表示、ブラウザ移動、権限失効、ネットワーク断、lease失効、run切替ではそのsourceを**確実にOFF**とし、自動でONへ戻さない。復帰後は明示的な再タップを要する。ブラウザのvisibilityイベントだけに依存せず、Spot側のsource lease/heartbeatで停止を確定する。無音・BGMそのものは会議Endにも他sourceの停止にもならない。OFF時の未確定音声はsource/item単位でbounded finalizeし、空commit、重複Final、古いFinalによる新音声消去、欠落の隠蔽を防ぐ。

同じrunの状態取得を始めた際にGDKの同期状態が一時的に`syncing`へ戻っても、そのrunで準備中・受理済みのマイクを過渡状態だけで止めない。新規ONの入場判定とは分け、捕捉開始時のrun ID・現run・接続を照合する。実際の`failed`同期、休憩/終了、run変更、端末非表示、音声ソケット喪失は引き続き停止する。状態取得自体の失敗や実Safari継続は実機ゲートに残し、ローカル回帰のみで#98の原因解消やRFC全体の受入れとは判定しない。

最大8台が同時ONになれる設計は維持するが、1台のスマホを複数人が使うことも許す。8台が同じ室内音を拾う重複問題や長時間ONのProvider負荷・バッテリー・データ送信量は実測し、話者同定や根拠のない自動重複破棄を行わない。会議中の注意は短くし、初回だけ「使うときにON、画面を離れるとOFF」と伝える。外部Cloud-demoである間は、音声が外部Providerへ送られることの事前説明・同意を省かない。

### 4.2 「論点のつながりを訂正」の入口

長文テキスト欄を主導線にしない。第一候補は、会話で表明された訂正を既存の**サーバー保持提案→Controllerで確認→Human-origin Event**へ通す方法である。これに加えControllerに少数の現在地周辺の関係を人間向け短縮タイトルで示し、`このつながりを外す`、`元の話を変える`、`別の話題として扱う`等の意図を選択・確認できる候補を比較する。Node ID・Relation enumを見せず、Shared View上のタップは要求しない。対象が複数ある、聞き取りが曖昧、revisionが変わった場合は**推測で反映せず**確認・再選択を促す。フリーテキストは代替／アクセシビリティ手段として残すかHuman Reviewで判断する。

既存の`remove/add/change endpoint/type`の範囲と検証を再利用し、追加のCanonical Relation型は設けない。Correction Eventで以前の関係を監査可能に残し、旧EvidenceだけからAnalyzerが直後に同じ誤結線を再作成しない。新Evidenceによる再提案は区別する。Decision/Open Item/Actionの状態を関係訂正だけで変更しない。

### 4.3 案内文の整理

通常画面は**短い状態1行＋必要時だけ詳細**にする。`音声入力は現在利用できません〜`の繰り返しは、例えば`マイクを使えません`と具体的な回復操作へ集約する。`操作結果を確認できません〜`は成功と推定せず、`結果を確認中`→状態再取得→未確定なら短い再試行案内にする。End・訂正の再試行は既存command ID/idempotencyを保持し、重複操作や二重Endを誘発しない。権限拒否、送信断、欠落、PDF期限切れ等の重要な失敗・不確実性は短縮しても隠さない。VoiceOver、色覚差、狭幅320/390/430pxを検査する。

## 5. Artworkと視覚トーン

現行[Launcher artwork](https://github.com/hakobune8/natade-coco-ronro/blob/v0.10.0-rc.6/docs/launcher-artwork.md)の「話に花が咲く」は、勝敗・単一結論を押しつけない比喩として維持できる。一方、現行水彩／紙の質感が強いというフィードバックを受け、次候補は**形を明瞭にした線・面、抑制した色数、軽い質感**へ寄せる。Catalog/LobbyのPlatform文字・QR・ボタンの余白とコントラストを優先し、発話やNodeの実データを装飾に流用しない。花の比喩を残す案と、枝分かれ／対話の抽象形へ寄せる案をHuman Reviewで比較する。画像権利・生成過程・Source/配信用資産・失敗時fallbackを記録し、実際のLauncher cropとDisplayの読みやすさを検査する。ArtworkはLive Canvas背景に置かない。

## 6. Provider移行 — 転送境界を段階ごとに正確に名付ける

`AnalyzerProvider`と`STTProvider`は別境界のままにし、Core Event/GraphへProvider固有のendpoint、model、credentialを入れない。**NetBirdは私設の通信経路であってLocal処理やデータ不外送の証明ではない。LiteLLMの配置場所・保持・ログ・上流Providerは別途確認する。** 現在のOpenAI Realtime STTをLiteLLM経由にできるとは仮定しない。Realtime WSSのprotocol、VAD/item correlation、Final/bounded fallbackを個別に適合試験する。

| 段階 | STT | Analyzer | 機密境界と昇格条件 |
| --- | --- | --- | --- |
| 0 現行Cloud-demo | OpenAI Realtimeへ外部送信 | OpenAIへ外部送信 | 音声・Transcript外送を明示。#98、#939と実機受入れは未完了 |
| 1 私設経路候補 | まず現行STTを維持。変更するなら別Provider適合試験 | NetBird到達のLiteLLM adapterを**候補**として接続。上流先、ログ、Secret、失敗時のfallbackを検査 | Analyzer入力にはTranscript/Graph等の会議内容が含まれる。LiteLLM経由をLocal Secureと呼ばない。単なるbase URL差替えで品質・安全・再現性を合格にしない |
| 2 Local STT | Spot実機のLocal STT adapter。端末→Spot以外へRaw Audioを送らない | 段階1のAnalyzerを継続可能 | Raw Audio外送の否定を通信観測と政策で実証。Transcriptは依然Spot外へ出うるため機密会議向け完全Localと呼ばない |
| 3 Local Analyzer | 合格済みLocal STT | Spot上のLocal LLM adapter | 日本語会議、訂正、Decision/Owner/Due安全性、2時間・1/4/8 source負荷、遅延、障害復帰を実測。会議内容を出すNetwork egressを実効拒否し、Offline起動/継続/終了を検証して初めてLocal Secure候補 |

Stage 1と2の順番は、安全条件を満たすなら個別PRで調整可能。ただし各段階の外送先・データ種・Consent表示を構成と実測に一致させ、失敗時に別Providerへ黙ってfallbackしない。Local STTの有力候補は`whisper.cpp`の多言語smallとmediumを**同一の日本語Evidence・実機負荷条件で比較**することとし、まだモデルを選定しない。SpotのCPU/GPU/メモリ予算、modelの配置・更新、LiteLLMへのNetBird到達性、上流への再転送、Platform NetworkPolicy/Fleet権限は未決。Platform変更が要る場合はPlatform ownerの別審査とし、Contentの設定だけで隔離を保証したとは言わない。

## 7. 実装順とPR単位の受入れ

具体的な変更ファイル、契約テスト、PR間の依存とロールバック単位は[実装計画](../implementation/rfc0010-spot-delivery-plan.md)に記す。このRFCと計画を先に`develop`へ統合し、各PRを**1つの責務**に限定する。`develop`統合は配布・実機受入れを意味しない。

| 順 | Repository / 対象 | 作業 | 依存・検証・完了条件 |
| --- | --- | --- | --- |
| 0 | `natade-coco-ronro`＋必要なPlatform issue / RC6基線 | #82の実機受入れを後続issueへ移し、#98・#939と未実施項目を維持。Controller同期不安定を原因別に切り分け、最新Digestとrun保護を読み取る | 修正PRは別途。Controllerが安定参加・再読み込みでき、未承認の音声/Provider再試験をしない |
| 1 | Content / Display projection | `マイク接続 n台`と処理状態の**実データ**をrun-scoped read-only payloadへ追加し、QR文言を変更。接続数から発話者数や音声内容を推定しない | 0/1/4/8、切断・古いheartbeat・pause/end・reduced motion、1920×1080の合成/実機検査。端末ID・音声内容の漏出なし |
| 2 | Content / audio Controller・backend | PTTをToggleへ変更。source lease、foreground/lock/断線での停止、再タップ復帰、bounded finalizeを維持 | #98の音声経路原因把握。短発話/長発話/無音+BGM/重複/古いFinal、1/4/8台と2時間負荷。いずれも一sourceの故障で会議を終わらせない |
| 3 | Content / Correction・文言 | 音声提案の見せ方と少数の関係選択UIを比較・実装。短文+詳細の状態表示へ整理 | Human-origin Event/replay、曖昧時no-op、stale Evidence抑制、End/訂正idempotency、狭幅/VoiceOverを検証。Participant Human Reviewを通す |
| 4 | Content / artwork | Catalog/Lobbyの2方向を試作し、権利・出典・最適化を記録 | Platform crop、QR/文字コントラスト、offline/asset failure fallback、Human Review。Live Canvasへ干渉なし |
| 5 | Content＋必要なPlatform / Provider | AnalyzerのLiteLLM候補を別adapterとして接続し、診断/秘密/外送政策を確認 | SyntheticのEvent/Graph replay、関係訂正・安全regression、NetBird/上流とaudit、制限付き同意済み実機試験。STTを勝手にLiteLLMへ流さない |
| 6 | Content＋Platform / Local AI | Local STT→Local Analyzerを独立候補として実装・比較 | 正確なRaw Audio/Transcript外送否定、NetworkPolicy実効、Japanese品質/遅延/8台・2時間/Offline、機密向け表示の審査までLocal Secureを名乗らない |

全PRでCore回帰、Content UI/Backendテスト、同じaccepted Event→同じGraph/Canvas、PDFの固定revision、Cloud-demo既存経路の回帰を確認する。Release/実機試験はCI発行DigestとFleetの実際の稼働Digestを照合する。実音声・外部Provider呼出しは試験ごとに範囲、同意、費用上限、停止条件を別途承認する。PR単位のGreenは#82引継ぎ全体のPASSではない。

## 8. Open Questions / Risk

1. `audio_ready`後の収音中判定には既存heartbeat／membership checkと`capture_stop`境界を使う。WebSocketがFinal待ちで開いていてもマイク台数へ残さない。画面からの状態取得が一時失敗した際、何秒で`確認中`へ切り替えるかは2秒pollと実機遅延を踏まえて計測する（暫定上限4秒）。Platformの参加枠数とは別値であることをHuman Reviewで確認する。
2. Toggleの長時間ON、ロック、iOS Safariの復帰時に、端末表示・Spot lease・実際のPCM送信をどう一致させるか。ロック中の収音を約束しない。
3. 訂正の音声提案が無音/BGM/複数の同時発話時に曖昧なら、どの少数選択肢が会議を中断しないか。テキストの代替導線をどこまで残すか。
4. LiteLLMの実配置、上流Provider、Data Controls、ログ、証明書/Secret、NetBird/NetworkPolicy境界。Stage 1でSTTを接続できるかはRealtime protocol適合後に別決定。
5. Local STT/LLMの端末実機性能と資源競合、モデル更新/署名・オフライン配布。名前やモデルを先に固定しない。
6. Artwork候補の比較は実機Catalog/Lobbyで行う。装飾が開放感より可読性を損ねれば見送る。

## 9. 決定ゲート

RFC承認後も、(a) Controller安定参加、(b) Source別の実音声→Final→Event→Canvas、(c) 1/4/8台・途中参加・中断/End/Drain/PDF、(d) 訂正のHuman Event/Replay、(e) 3–5m表示/短い案内/Artwork、(f) 安全違反ゼロ、(g) 移行段階ごとの外送事実の説明、を**実機で**確認するまではSpot版の総合受入れ・機密用途を宣言しない。結果はPASS/FAIL/NOT RUNと具体的な版・時刻を残す。#98/#939が未解決の間はUIの見栄えだけで音声受入れへ進まない。

### Recommended next implementation step（RFC承認後）

候補コードが`develop`へ入った後も、次の実機受入れ前の優先作業は**RC6で報告されたController同期問題（#939）の修正候補 #943 のowner reviewと、RC7の正確なソースでのhosted security／供給網検査**である。前者のCI Greenは実Safariでの安定参加を証明せず、後者の課金起因のjob未開始は合格ではない。どちらも整い、別途リリース判断された後にのみ候補Digestを固定し、接続・表示・音声・終了を実機で検証する。ToggleやProvider候補のローカルGreenを旧実機失敗の解決と見なさない。
