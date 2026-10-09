# RFC-0009 補助設計: Spot向けRONRO Content契約

| 項目 | 内容 |
| --- | --- |
| Status | Working design / 段階実装の入力。Platform owner確認・実機検証・配備承認ではない |
| Updated | 2026-10-09 |
| Parent | [RFC-0009](../rfc/0009-ronro-as-natadecoco-local-ai-content.md) |
| Implementation | [PR単位の実装計画](../implementation/natadecoco-content-implementation-plan.md) |
| UX / Artwork | [制作・受入れブリーフ](../product/natadecoco-ronro-ux-artwork-brief.md) |

> 契約改訂（2026-10-09）: 以前のHost専用Content操作・Platform終了ガード必須・手動「受取終了/破棄」は採用しない。以下は改訂後の設計であり、既存Content候補コードのHost命名/APIや本番配備が更新済みという意味ではない。[実装計画](../implementation/natadecoco-content-implementation-plan.md)に移行作業を記す。

## 1. 調査で確定した境界

RONROの`prototype/service_final_record.py`には`prepare_final_record`と`render_final_pdf`が既にある。受理済みEventのReplay、Graph/Canvas revision、欠落区間を検査してPDFを作り、Raw Audioや全文TranscriptをPDFへ載せない。再利用候補はこの純粋な生成境界であり、`service_meeting_http.py`のアカウント認証・Postgres保存・7日削除はSpotへ移さない。現行`service_audio_transport.py`は単一owner/単一capture leaseを前提とするため、8台の音声入口をそのまま有効化してはならない。Event/Materializer、Human ConfirmationとSemantic Canvasの契約は維持する。

GDK/Platformの調査対象はGDK `0ba3e224`、Platform作業checkout `44f52ae`。後者は配備Runtimeの証拠ではない。`game.yaml`の`players.max`は8まで指定可能で、`while-playing` Joinと`keep-alive`は対応Runtimeで使用可能。Controller UI moduleにはPlatform credentialやhost lifecycle APIが渡らず、同一originの`requestGameResource`だけがBearer付きContent HTTP requestを行う。WebSocketはこのHTTP bridgeとは別に認可する必要がある。Platformの`/control/end`は即時Terminateし、`finishGame`は1件以上の順位を要求し、result表示時間は最大120秒。**会議用に架空の順位を送らない。**

## 2. 先に固定する設計判断

1. 新repo `natade-coco-ronro`をContentとし、RONRO Coreのversion/hash固定packageを一方向に利用する。Python backendを残し、同一Content Serviceの8080番・同一origin配下でDisplay、Controller module、API、WSSを公開する。GDKのGame互換Manifestを当初使い、`players: {min: 1, max: 8}`、`joinPolicy: while-playing`、`emptySessionPolicy: keep-alive`、対応Runtimeを宣言する。8人は音声処理性能の証明ではない。
2. 初期実行は明示的な`cloud-demo`。機密/Local Secureと表示しない。STTとAnalyzerは別Provider契約で差し替える。Cloud資格情報はContent server側だけに置く。
3. Session Managerは参加・枠・run・host leaseの権威、Contentは会議取込・Drain・PDFの権威。PlatformとContentの状態は混同しない。Platformを`playing`に保ったままContentの会議を終了・PDF受取し、その後PlatformをTerminateする。`finished`/rankingsを流用しない。
4. PlatformのStartと「ゲームを全体終了する」は既存ShellのHost権限に従う。後者はRONROの通常の会議Endではなく強制的なPlatform終了であり、Drain/PDF受取を保証しない。ContentはPlatformの新しい終了ガードを前提にせず、会議EndとPlatform終了を明確に分ける。
5. Content本文は会議中と終了直後の受取窓だけSpot内に置く。PDF readyから30分（暫定上限）で**期限到達時のみ**消去し、どの参加者にも手動削除を許さない。参加者全員がPDFを各自の端末へ持ち出し得ることを事前に示す。一人の取得/保存失敗は他の参加者の受取窓を変えない。

## 3. State / Authority / API

| Platform | Content | 可能な操作 | 不変条件 |
| --- | --- | --- | --- |
| waiting/ready | idle | Hostが既存ShellでStart | Contentに音声は入れない |
| playing | active | 認証済み参加者がPause/End/Correction、全員がPTT、途中Join | Source別に取込。Host離脱・無音はEndでない |
| playing | paused | 認証済み参加者がResume/End、途中Join | PTT拒否、Graphと既存run維持 |
| playing | finalizing | 再試行可能なDrain監視 | 新規PTT拒否。既存Sourceの範囲とQueueを確定 |
| playing | handoff（PDF ready、complete/incomplete outcome付き） | 認証済み参加者が各自PDF取得 | 固定Event revisionからPDF。新規PTT拒否。Join QR非表示。一人の取得で窓を閉じない |
| playing | failed（PDF未生成） | 認証済み参加者が原因表示・安全な再試行を要求 | 正常PDFと表示しない。原データが残る間だけ同一runを再試行 |
| playing | purged | Platform Hostが既存Shellの全体終了を選択可能 | 期限到達でContent本文/ticket無効。Platform終了は別の明示操作 |
| terminated/error | incomplete/purged | Operator調査のみ | 強制終了を正常終了と偽らない |

Content Endは`active|paused → finalizing → handoff|failed`の冪等操作。参加者一人のEndは全員の取込を止めるため、操作前に明確な二段階確認を行い、確定したHuman-origin Commandと実行者・run・revisionを監査する。競合するEnd/Resume/Correctionは同じcommand IDとphase/revision検査で決着させる。`ended_incomplete`は**phaseではなく完了結果**であり、既知の欠落範囲/不明範囲をPDFに記して`handoff`へ進める。Drain不能やrevision不一致なら`failed`でPDFを正常成果物と呼ばない。finalizingはEndから最大10分でタイムアウトし、再試行可能なEvent/WALがある場合のみ同一runで再試行、そうでなければ参加者へ失敗/Operator対応を案内する。`handoff`/`failed`はそれぞれ入り時点から最大30分で本文消去・ticket失効・`purged`へ進む。Pauseは音声取込世代を進め、既に受信したPCM/Final/Analyzer仕事をDrainまたは安全な隔離に移す。Resumeは新世代からで、旧Finalを新世代へ帰属させない。Hostや参加者が一時切断してもContent状態は維持する。Platformが異常終了したらPDF取得不能の可能性を非内容ログに残し、Sessionを黙って再作成しない。

### Participant操作の認可境界

Platformの`/control/end`はゲーム全体の強制終了であり、RONRO会議の通常のEndと別操作にする。ContentはPlatformに終了readiness guardを要求しない。Platform Hostが全体終了を選ぶとDrainやPDF受取が中断され得ることをShell/運用に明示する。Contentの成功表示は固定revisionでPDFを生成した場合に限る。Platform Sessionの最終クローズ手順は実機で確認するが、架空のランキングや`finishGame`で迂回しない。

RONRO会議のPause/Resume/End/Correction/会議後PDF・handoff状態取得は、当該Platform session/runの**現在の認証済み参加者**へ許可する。Controller moduleの表示上の`role`、slot、古いBearer、Display credentialだけでは許可しない。各HTTP操作で`requestGameResource`のPlayer BearerをSession Managerのactive-player verifyで検証し、Launcherの現在のplaying RONRO session/runと接続Playerを照合する。認可照会不能・退出/kick・run差替えはfail closedとし、待機中にrunが変わった場合も再確認する。Platform Host leaseはこれらのContent操作の条件ではない。Platform Start/全体終了のHost契約は変えない。

現行Contentの`PlatformPlayerAdmission`/`RunBoundPlayerAdmission`は音声ticket用にこの本人・run照合を持つが、会議Command/Status/PDFへの注入と実機契約検証は未完了。候補の`Host*Authorizer`はParticipant操作へ置換するまでは有効化しない。認可の緩和は本人確認の省略ではない。参加者の操作主体をHuman-origin監査に残し、訂正はEvent経由でGraphへ反映する。

Contentの外部HTTP契約は`/games/ronro/`配下に置く（ここで`ronro`はManifestの実IDで置換）。Player BearerをURL/Local Storage/JS moduleへ露出させず、Controller moduleは`requestGameResource`からだけ呼ぶ。既存Player JWTにはrun IDがないため、署名検証だけでは足りない。Command bodyは`command_id`（retry時に同一値）、`expected_content_revision`、必要な訂正対象だけとし、session/run/playerは認可済みPlatform contextと照合する。重複Commandは同じ結果、revision競合は409、参加資格なしは403、認可照会不能は503で**状態変更しない**。Endは確認UIを経た一回のCommandとし、二重押下や別端末との競合で二重Drainしない。訂正Commandは既存Human-origin Event境界を通し、Graphを直接書き換えない。

| Endpoint（概念path） | Caller / response | 権限・条件 |
| --- | --- | --- |
| `GET /api/state` | Display: Canvas snapshot/revision、Controller:自分に必要な会議/取込/PDF状態だけ | Displayはrun-bound Display credential、Controllerはactive player。全文Transcriptを一般Controllerへ返さない |
| `POST /api/audio-ticket` | Controller:一回限りの短命ticket | active player、Content `active`、run一致、1 playerにつき1 capture generation |
| `WSS /audio` | Controller:最初のframeでticket、以後source別PCMとACK | ticket/Origin/lease、`paused|finalizing`ではPCM拒否 |
| `POST /api/commands/{pause,resume,end,correct}` | 現在の参加者:冪等な結果＋新revision | 操作ごとにPlayer Bearer＋現在のsession/run/接続照合。`purge`は公開しない |
| `GET /api/handoff-state`・`GET /api/final.pdf` | 現在の参加者:状態／固定revisionの添付PDF | `handoff`かつPDF ready、受取期限内。HTTP成功は端末保存成功としない |

Displayへのsnapshot配信とController状態更新はreconnect時に**revision付きfull snapshot**を先に返し、差分はその後に適用する。古いrunの音声ticket/差分は無効。既存Display SDKのSession snapshotはPlatform状態であってRONRO Graph正本ではない。Shared ViewのJoin QRは既存Launcherの`/launcher-api/v1/session`応答に含まれる`joinUrl`をDisplay権限で取得し、現在のsession/runおよびSpot local originを照合して表示する。room/sessionの参加情報以外のCredentialを含めず、Contentが独自の参加認証を作らない。ローカルURLと端末Wi-Fiの関係は実機試験する。

`POST /api/audio-ticket`は上記active-player権限から、session/run/player/connection generation限定の一度きり・15秒有効ticketを発行する。Browser WSSはURLやログにticketを載せず、接続後3秒以内の最初のcontrol frameで渡す。検証前のPCMを受けない。Origin、TLS、Session/run、replay、個別rate/capacityを検査する。接続は短い入力leaseを更新するが、**押下が継続しPCMを実際に送れるときだけ**収音状態とする。参加資格/leaseの失効は遅くとも次の更新周期でそのSourceを止める。秒数は初期値であり、実機遅延とネットワーク試験で安全側に調整する。

## 4. 最大8台のPTT音声契約

各Controllerは`idle → preparing → transmitting → closing → idle`を持つ。押下というUser Gestureで`getUserMedia`、AudioWorklet、WSS/ticketを準備し、最初のPCMをserverが受理した時点でのみ「収音中」。指を離す、`pointercancel`、blur、`visibilitychange:hidden`、pagehide、権限失効、disconnect、会議Pause/EndではMediaStream trackを停止し、送信可能leaseを解除する。再接続後に押しっぱなしと推測して自動再開しない。準備中の発話は拾われない可能性を表示し、非押下状態を「聞いている」と誤表示しない。現行GDK controller moduleのbrowser permission/CSP/AudioWorklet動作は実機契約試験が必要。

音声frameは`source_id=(session,run,player,connection_generation)`、単調`frame_seq`、PCMサンプル範囲、受信時刻を持つ。初期Remote STT adapterには既存`prototype/live_audio.py`のmono PCM16LE/24 kHz正規化を使い、Browser実際のsample rateからの変換をFrame境界で検証する。Local Providerには同じTransport契約から別のrateへ変換でき、Canonへsample rateを混ぜない。source IDは話者本人/Ownerの証明ではない。サーバーはsourceごとに順序/重複/gap/backpressureを検出し、Sourceをまたいでitemを完了扱いにしない。重なった発話は複数Evidenceとなり得る。近接端末で同じ発話を二重収音しても、検証できない類似度だけでEvidenceを消さない。複数sourceのFinalは「発話の正確な全順序」を捏造せず、受信時刻・source・turn IDを持つ決定的なmerge順にEventへ受け渡し、同時発話は重なりとして診断する。意図的Pauseの無音はEvidence欠落としない。意図しない切断でPCM欠落/未確定音声があればsource別のgap intervalを記録する。Queueが溢れた場合は明示拒否・gap記録し、黙ってdropしない。

PTTを8台運用する場合でも、全員の常時収音はしない。ボタン操作の負担、押下開始遅延、端末ロック、同室マイク重複、同時発話は1/4/8台・2時間超の実機/合成試験で評価する。8台接続だけを性能PASSにしない。端末がWi-Fiから携帯回線へ移ったとき、Controller単独でローカル経路を証明できなければそのsourceをfail-closedで停止する。Pod NetworkPolicyだけでスマホ端末全体を保護できるとは言わない。

## 5. Provider、Store、Canvas、PDF

`ronro` CoreはSession IDを含む`source`を渡す`LiveSTTProvider.open(source,config)`から`Partial/Boundary/Committed/Final/Failure`を正規化し、source台帳の`Drain`で未解決を検査する。`AnalyzerProvider.complete_json`相当をOutput Schema版つきで呼ぶ。Cloud/Local AdapterはContent側に置く。Provider固有item IDとsource PCM rangeを保持し、FinalはEvidence候補、Partialは揮発。Analyzerの候補Eventは既存Validator/受理境界を通し、Decision確定・Owner/Due・Human訂正優先を変えない。受理済みEvent列だけでReplayでき、Replay時にProviderを呼ばない。新しい音声由来のHuman Commandと手動訂正はHuman-origin Eventとして監査可能にする。

Core wheel `0.1.0.dev4`候補では、この境界のAnalyzer側を`AnalyzerProvider`、`RealAnalyzer`、`CandidateEvent`として配布する。Prompt/文脈構築/Output Schema検証/候補Event変換はProvider非依存の`analysis_engine`が正本である。従来の`OpenAICompatibleProvider`はPrototype専用の互換層に分離し、Core wheelには含めない。Spot Contentは独自の明示的なCloud/Local Provider実装を注入する。現時点でContentの実Analyzer QueueやProvider実接続が完成したことを意味しない。

Provider非依存の初期契約は`prototype/source_stt.py`（配布時は`ronro_core.SourceSTTLedger`等）に置く。1つの`STTSource(session, run, player, connection_generation)`ごとに単調frame sequenceと24 kHz sample範囲を照合し、Provider Adapterが報告する既知範囲のCommitted itemだけをFinalと結びつける。同じProvider item IDが別sourceに存在しても混ぜない。source内の順序逆転FinalはCommitted順にEvidence受理待ちとし、受理後にだけacknowledgeする。空Final・明示的Provider failureは会議を終了せず、後続itemを進めながら未解決をDrainに残す。Drainのcompleteには収音区間のcloseとProviderのfinish/イベント排出完了の**両方**を要する。PCMの非ゼロ振幅は発話の証明ではなく、欠落**可能性**の保守的な診断に限る。未知範囲、重複衝突、容量超過は推測補完せず失敗とする。CoreはRaw AudioもProvider認証情報も保存せず、複数sourceのEvidence採番・耐久化・実Provider接続はContent側の後続実装とする。この契約だけで実音声の受入れを許可したことにはならない。

Contentはrun単位のEvent Store/WALをバックアップ対象外のSpot tmpfs上に置き、Raw Audioは揮発ring bufferのみ。Graph/CanvasはEventから再生成し、配置metadataは非Canonical。process再起動時はWALからReplayし、未確定PCM/sourceのgapを付ける。Pod消滅でtmpfsが失われた場合は復元保証せず、Content失敗として見せる。Meeting Recordの`prepare_final_record`/`render_final_pdf`をCore package側の純粋関数として抽出するが、Spot側の認証/PDF受渡し/TTLは新Contentで実装する。PDFには固定revision・Candidate/Confirmed・Open/Action・分かる範囲の欠落時刻を含める。会議中CanvasとFinal Canvasは同じProjection/座標を使う。Cloud-demoではSpot→外部STT/Analyzerへ会議内容が送信されることを明示し、端末・Content・ProviderのログへRaw Audioや全文を記録しない。

参加者ControllerのPDF応答は`Cache-Control: no-store`、添付filename、Content-Type、Content-Security-Policy、`X-Content-Type-Options`を定め、URLにBearerを置かない。各自が端末内保存を確認できるようにし、HTTP 200だけで保存成功とはしない。期限後・別run・参加資格喪失後の取得は拒否。**取得回数や一人の保存完了に関係なく**PDF readyから30分（暫定）の期限到達時にのみ、tmpfsのrunディレクトリ、in-memory cache、ticket、WAL、生成PDFを削除する。失敗は本文なしの診断値を残し、次のSession起動時にも旧runの残存を検査する。これは端末側PDF回収やProvider側の削除保証ではない。

Controller moduleでは`requestGameResource`のPDF `Response`をBlobとして端末へ渡す。Blob URLの生成/クリック/破棄、iOS Safariの保存導線、CSPと大きなPDFによるメモリ上限を実機試験する。Blob URLを長期保持しない。保存の最終確認はOS側で利用者が行う。全員の画面に受取期限を示し、期限後は再ダウンロード不能と明示する。「受取終了」「記録を削除する」ボタンは設けない。

## 6. 実装前に証明する契約ゲート

以下は設計上の未決事項ではなく、**実環境で真偽を確認するゲート**である。FAILなら依存PR/配備を止め、代替方式をレビューする。

1. Controller moduleのiOS Safari/Android Chromeでuser gesture→microphone/AudioWorklet、release/lock/background時のtrack停止、同一origin WSS、最初のPCMまでの遅延を実測する。長押し負担はHuman Reviewを別に要する。
2. 配備PlatformでRuntime 1.1以上の`while-playing`/`keep-alive`、8枠、2時間超、Host transfer、Content HTTP/WSS routingを確認する。作業checkoutを配備済み契約とみなさない。
3. Content側でPlayer Bearer・同一session/run・現時点の接続を各Command/Status/PDFに対して照合し、kick/期限切れ/別run/照会不能ではfail closedになることを実機で確認する。参加者Endの二段階確認、競合の冪等性、Human-origin監査、全員のPDF受取窓、期限以外で削除不可も試験する。Platform全体終了は別の強制操作として失敗表示を確認する。
4. PDF生成器が大きなGraph・日本語・長文・欠落警告を収め、PDFが受取端末へ届くことを確認する。既存rendererは再利用候補であり、大規模会議の表示品質保証ではない。
5. Cloud-demoの限定Egressと、将来のlocal-secureに必要なDNS/IPv6/hostNetwork/Sidecar/端末経路の拒否試験を別々に通す。Cloud-demoの成功から機密性を推論しない。

本書はRFC-0009の決定補助であり、未検証のPlatform拡張を「実装済み」と記すものではない。
