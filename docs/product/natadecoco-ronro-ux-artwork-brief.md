# natadeCOCO版 論路 — UI / Artwork 制作・受入れブリーフ

| 項目 | 内容 |
| --- | --- |
| Status | RFC-0009に基づく制作仕様。画像・UI本体は未制作、実機Human Review前 |
| Updated | 2026-10-07 |
| Related | [RFC-0009](../rfc/0009-ronro-as-natadecoco-local-ai-content.md)、[実装計画](../implementation/natadecoco-content-implementation-plan.md)、[名称判断](ronro-naming.md) |

## 目的と画面ごとの役割

論路が提供するのは、会議中に「今何を議論しているか、何が決まりつつあるか、何がまだ残っているか」を共有する**論点図**である。Spot版はその価値をLauncherで誤解なく伝え、会議中は議論を妨げず、終了時はPDF受取まで案内する。現行[Semantic Canvasの合成例](../pilot/ronro-live-pilot-guide.md)を出発点とし、旧6カード画面へ戻さない。Launcherの販促画像とLive Graphは別物であり、artworkに架空の「実際の会議結果」を描かない。

ここでの「オープンでクリーンなディスカッション」は**会議内容の一般公開**ではない。参加者が自由に発言・保留・異議・訂正でき、AIの判断や誰かの発言量を競わせず、どの音声が取り込まれているかとAIの暫定解釈が分かる体験を指す。[Naming Decision](ronro-naming.md)の「会議の主役は参加者」と[RFC-0003の人物評価をしない原則](../rfc/0003-discussion-map-ux-and-layout.md)を継承する。

### 非誘導・非監視の表現原則

- 論点図は**議論の現時点の仮説**。提案／懸念／未解決は失敗や勝敗ではない。確定Decisionだけを人間の確認後に明示し、候補を「決まったこと」に見せない。provenanceの線は議論上の由来であり、因果・正しさ・多数派の証明に見せない。
- 参加者の名前・端末・発言回数・押下時間・発言順位・感情・賛否集計を大画面に出さない。共有画面の収音表示は集約状態のみ。自分の端末の入力可否は本人に明瞭に示すが、押し忘れを公開画面で責めない。内部分類の件数表示は「会議の得点」や進捗ゲージにしない。
- 余白と落ち着いた動きで議論へ視線を戻せるようにする。Focusの強調と種類別色は見分けられるが、懸念を「危険な人の発言」の赤、確定を「優勝」の金など道徳・ゲーム的評価として扱わない。線種・文字も併用し、色だけで意味を決めない。
- AIの訂正は特別な失敗演出にしない。関係の削除・つなぎ替えや別Rootへの移動を静かに反映し、参加者が普通の言葉で修正できる状態を維持する。曖昧な訂正は勝手に反映しない。Hostだけが修正可能な操作と、参加者の会話での指摘を混同しない。
- 空のCanvas、沈黙、Pause、話題の脱線を「悪い状態」として演出しない。「話してください」等の圧力、沈黙タイマー、未来の論点予告、発言を促すランキングを置かない。
- 収音中/停止中/取りこぼし可能性、Cloud-demoでの外部AI送信、PDFの端末保存とSpotからの消去は短い事実表現で説明する。Artworkや小文字の脚注に重要な情報を隠さない。機密モード未対応の段階で鍵・盾・Local Secureを連想させる表示をしない。

| 面 | 主役 | 必要な改善 | 禁止・注意 |
| --- | --- | --- | --- |
| Launcher Catalog | 論路の識別・用途・参加人数 | 日本語名「論路」、短い説明「議論の現在地を共有する」、16:9で読める専用Catalog artwork。Gameの対戦・順位を示唆しない | Raw Transcript/実会議のScreenshot、遠隔Cloud使用を秘匿する機密訴求 |
| Launcher Lobby / Join | 会議に入ることと音声の扱い | 専用Lobby artwork、最大8台、途中参加、Hostと参加者の役割、Cloud-demoなら外部AI送信の説明へ自然に進める | Artwork上の疑似QR・押すべきボタン。PlatformのJoin/認証を複製しない |
| 大画面Display（Live） | 同一Semantic Canvasの現在地 | 1920×1080と実投影で3–5m可読。Focus、周辺、provenance/支持/懸念、決定候補/確定、未解決/Action、最新Canonical本文、種類別件数、右上の真正Join QR。0 source時は「発話待ち」、収音中だけ「聞いています」。QRと字幕が重ならない | マウス操作、過度なchrome/背景装飾、無音時の偽「聞いています」、線を因果や確定と誤読させる表現 |
| 大画面Display（Pause/Final/障害） | 状態と同じCanvas | Pauseは図を保持し明確に「中断中」。Finalは同Canvasのzoom-out。欠落可能性/更新停止は見落とさないが、会議を不必要に止めない。Join QRはEnd後に消す | 空画面化、Errorを正常終了と見せる、別Graphへの切替、細字だけの全体図 |
| 参加者Controller | 大きな「押して話す」 | 未押下/準備中/送信中/取込不能/中断中/終了処理中を区別。押下で最初のPCMが受理されるまでは収音中と表示しない。指を離す・画面ロック・切断で停止。8台のうち自分の状態を明確化 | ボタンを押さずに収音、ロックからの自動再開、内部Graph用語、押下成功とSTT成功の混同 |
| Host Controller | 会議の開始/中断/再開/終了・訂正・PDF受取 | 主要操作と危険操作を分け、PauseとEndを取り違えにくくする。End後はDrain→PDF準備→取得→端末保存確認→Spot内容消去→Platformを閉じる順を案内。訂正とHost移譲は役割再認可に従う | PDF HTTP 200を端末保存成功と断定、消去前の早期Terminate、参加者へのHost操作露出 |

スマホは縦持ち片手操作を基本とする。Platform Controller Shellが所有するナビゲーションや認証状態は壊さず、RONRO moduleが占有できる範囲で大きなPTTを配置する。小画面・Safe Area・片手押下・VoiceOver/TalkBack・色覚差・高コントラスト・Reduced Motion・ブラウザ背景化を実機で検査する。**PTTによって自然な発話、相槌、言い直し、割り込み、複数人の会話が継続しにくいなら、見た目だけ直して実装完了にしない。** 共有室内マイク等の別Capture profileを比較する設計判断へ戻る。本人がスマホを操作できない場合の代替参加方法も同じ判断に含む。

## 実装前・実機で確かめる設計判断

1. **自然な収音と参加の公平性（PR5、PR10a）**: PTTを初期案として試し、手を離すまでの負担・押し忘れ・相槌や割り込みの欠落・操作できない人の参加を観察する。単に8台接続できるだけでは合格にしない。会話を繰り返し止めるなら、会議室マイク等の代替Capture profileの同意・重複収音・停止方法を設計し直す。初期仕様にない代替方式を黙って自動起動しない。
2. **自然な訂正と権限（PR8、PR9a）**: 参加者の「それは別の論点です」等は議論上の指摘として拾えるべきだが、[Host専用Command契約](../architecture/natadecoco-content-contract.md)を迂回して誰の声でも確定的にGraphを書き換えない。訂正提案の認識、曖昧な対象の確認、Hostの確定操作、反映結果の控えめな表示を一続きの体験として設計・評価する。認識できない／反映されない場合も黙って成功表示しない。
3. **取り込み状態と誤解防止（PR9a）**: 個人端末では「押した」「PCMが受理された」「文字起こし／論点図に反映された」を混同しない。共有画面は個人別監視にせず、集約した入力状態と更新停止・欠落可能性だけを必要時に示す。Cloud-demoの外部送信とPDF受取後の消去を、開始前・終了時の適切な場面で事実として説明する。
4. **議論の多様性と見え方（PR9a、PR10a）**: 少数意見・反対・保留・独立論点・AIの誤接続が、中央Focusや色使いによって「会議の正解」から外れたように見えないか検証する。訂正後に誤った線が残らず、候補と人間が確定した事項の区別がPDFにも保たれることを確認する。読みやすさと、発言や訂正をためらわせないことを別々に質問する。

この4点は画像だけでは合否を決められない。合成状態の画面比較に加え、検証用Spotでの模擬会議と参加者本人への非誘導的なHuman Reviewを必要とする。未解決なら[実装計画のGate](../implementation/natadecoco-content-implementation-plan.md)へ戻し、Artwork完成だけでProduct受入れとしない。

## Artworkの成果物と既存GDK契約

新Content repoの`/games/<game-id>/assets/`配下に、少なくとも`catalog.webp`と`lobby.webp`を**bundle**する。GDKの[`presentation`契約](https://github.com/hakobune8/natade-coco-gdk/blob/0ba3e224d503b131ab0d7969cc9e7dd82026a364/docs/game-development.md)は`catalogArtworkPath`、`lobbyArtworkPath`、6桁Hexの`accentColor`を揃えて指定する。許可される画像はAVIF/JPEG/PNG/WebPで、SVG・外部URL・HTMLをManifest artworkへ使わない。Catalogは16:9-safe、Lobbyは左・下のPlatform status overlay越しにも読める構図。画像がない場合はLauncher fallbackがあるが、Spotコンテンツ完成判定では専用artworkを必須とする。Core repoへ製品用ラスターファイルを依存させず、Content repoで原画・出力物・ライセンス/制作元・生成/編集履歴・最適化手順を管理する。

制作方向: 「話が整理され、道筋が見える」静かな抽象表現。明るい余白、論点図のBlue/Green/Amber/Purple系と整合する色、会議室らしい落ち着き。**一本の正解ルートや先が決まっている矢印ではなく、複数の入口と開いた余白を感じられる構図**を候補にする。ただしArtworkの線を実際のSemantic Relationと誤認させない。実会議で生成されたNode/Relation、Transcript、実在人物/組織、重要そうな架空の決定は描かない。監視カメラ・波形監視・採点表・トロフィー・議論を戦わせる対戦表現・未実装の鍵/盾の安全訴求を避ける。Live Display背景にはCatalog artworkを敷かず、Canvasのコントラストと文字を優先する。Wordmarkを入れる場合は製品名「論路」を使い、旧名称・`Discussion Map`・内部enumを見せない。文字やボタンを画像へ焼き込まず、必要な説明はPlatform/ContentのHTMLテキストで示す。

受入れ時に、両画像の元解像度・圧縮サイズ・寸法・色域・透過可否、Catalog/Lobbyへのcrop位置、実Launcherの左/下overlayとの重なり、暗い/明るいDisplayでの視認性、読み込み失敗時fallback、オフライン配信、ライセンス記録を確認する。サイズ上限はGDK validator/実配備の上限を確認して固定し、根拠なく推測しない。専用アートの美観評価と、議論中UIの可読性評価は別に行う。

## UIレビュー用シナリオと証跡

合成会議のみで、少なくとも次の状態を再現する: Launcher Catalog→Lobby/QR→1台開始→2台途中参加→8台参加→0/1/複数台PTT→Pause/Resume→論点追加/更新/訂正→Decision候補/確定・未解決・Action→切断/ロック/取込不能→End/Drain→Final Canvas→PDF受取/消去。加えて、**沈黙、相槌、重なった発話、意見の対立、仮提案と正式決定の差、訂正後に誤った線が消える様子**を評価する。Displayは1920×1080の静止画と短い遷移動画、Controllerは320/390/430px級の縦画面の状態別スクリーンショット、LauncherはCatalog/Lobbyの実UI画面を残す。これらは**合成データ**と明記してPrivate Reviewへ渡し、機密会議の内容を公開Repoへ入れない。実機では16:9大画面を3m/5mからHuman確認する。もし画面から論点・状態・押下成否が分からないならUI GateはFAIL。

実機の模擬会議では、参加者が普段どおり話せたか、PTTのために会話を止めたり順番待ちしたりしなかったか、スマホを見続けず論点図へ視線を戻せたかを本人への短いHuman Reviewで確認する。技術的に8台が繋がっても、**オープンな議論を妨げたならUX GateはFAIL**。その場合はPTTの小改修か、会議室マイク等の別Capture profileを比較し、同じ候補をPASSにしない。

## Completionと後続改善の切り分け

初期Spot Contentの実装完了には、専用ArtworkをManifestへ組み込み、Launcher/Lobby・Live/Final Display・参加者/Host Controller・PDF導線が**検証用Spot実機**で一連に動くことを含める。改善候補を「既知の問題」として隠さず、影響/再現条件/優先度/Owner/次の検証を[実装計画](../implementation/natadecoco-content-implementation-plan.md)の台帳に整理する。P0安全・データ損失・誤操作による中断、主要操作不能、見えない音声欠落、**PTTが自然な議論を止める問題**は「後続改善」へ先送りせず実装完了を止める。一方、Local STT/Analyzerと強制ネットワーク隔離は初期Cloud-demo完了とは別の後続Phaseとして扱い、機密モードを名乗らない。
