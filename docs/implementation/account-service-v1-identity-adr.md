# Account Service v1 — Identity ADR (P2)

Status: ZITADEL採用をHumanが承認。RONRO専用OIDC Clientは登録済み。実認証・Service配備は未実施。

## 決定

既存のZITADELをIdentity Providerとし、RONRO専用のOIDC Clientを登録する。他アプリのClient ID・Secret・redirect URIは流用しない。既存Pilotの`controller_id`も認証主体にはしない。

WebログインはAuthorization Code + S256 PKCEを使う。ZITADELの作成ウィザードではPKCE/`none`とCode/`client_secret_basic`が別の選択肢だったため、Human確認後にRONRO専用WebクライアントをPKCE/`none`で登録した。`client_secret_basic`との併用を検証済みと扱わず、本ClientにSecretを発行・設定しない。サーバーは一回限りの認可試行、state/nonce、サーバー側PKCE verifierを保持し、事前に設定した単一issuerのDiscovery/JWKSを参照して署名、issuer、audience、期限を検証してから`issuer + subject`を内部userへ写像する。メールアドレスは永続識別子にしない。Callback URIと許可Originは環境ごとに固定し、任意URLへのredirectを許さない。認証コード、PKCE verifier、token、cookie、CSRF値はログ・URL query（OIDC規格上の一時的なCallback queryを除く）・PDFへ残さない。

登録記録（識別子はSecretではない）: ZITADEL Project `RONRO` / `393875059124469810`、Web application `RONRO Web` / `393875378680102962`、Client ID `393875378680168498`。Auth method `None`、response `Code`、grant `Authorization Code`、refresh token無効、開発モード無効。Callback `https://ronro.hakobune8.com/api/service/auth/callback`、logout redirect `https://ronro.hakobune8.com/`。この登録は本番RONROの認証開始や既存Pilotの切替を意味しない。実Token交換、IdPの許可条件、Callbackの到達性、複数端末と失効を別途試験する。

検証後はサーバー側Web Sessionを発行し、ブラウザには`__Host-` prefixのHost-only、`Secure`、`HttpOnly`、`SameSite=Lax` cookieのみを渡す。状態変更にはSession結合CSRF tokenと厳密なOrigin照合を併用する。WSSもOriginとSession権限を照合し、接続中の失効・Session終了・Capture generation変更を反映する。View-only資格は別のSession限定権限で、ownerのWeb Sessionと混同しない。

ブラウザのログイン期限切れ・再認証は、すでに受理済みの会議Sessionを自動終了させない。操作再開には再認証を要求し、音声取込みの継続/欠落はP3のCapture状態とgapで説明する。期限切れを黙って`ended`と扱わない。会議時間が約2時間を超えても終了を強制しない。

`prototype/service_browser_security.py`はOrigin/CSRF/Cookie形式の検証境界を持つ。`prototype/service_oidc.py`は専用ClientのCode + S256 PKCE認可URL、`none`または`client_secret_basic`の明示的なクライアント認証方式、state/nonce照合、固定HTTPS JWKSからのRS256 ID Token検証を持つ。実登録は`none`である。`0009_service_identity.sql`と`0010_oidc_browser_binding.sql`、`prototype/service_identity_store.py`は、同一ブラウザに結合した一回限りの認可試行、暗号化nonce/PKCE、`issuer + subject`の鍵付きダイジェストによる内部user対応、ハッシュ化Cookie/CSRFと失効可能なWeb SessionをPostgreSQLに保持する。CSRF tokenは同一Sessionの別Tabでも取得できるよう、秘密鍵とCookie tokenから導出し、DBにはそのdigestだけを残す。`prototype/service_owner_access.py`は、これを会議owner照合に接続する内部境界である。`prototype/service_auth_http.py`はログイン開始→Callback→Session確認→Logoutのローカル専用HTTP候補である。`prototype/service_meeting_http.py`はこれと同じloopback専用サーバーでownerのSession状態とCanvas、短命表示資格のCanvasだけを読み出す。owner照合・表示資格の有効性確認とEvent replayを同一DB transactionに置き、表示資格ではEvidence/Transcript・Session状態を返さない。ownerのOrigin/CSRF確認後だけ5分の表示資格を発行・取消でき、資格はAuthorization headerでCanvas読出しにのみ使用する。URL queryには資格を受け入れない。実ZITADELでのToken交換、永続identity keyの運用、会議の作成/変更/音声WSS経路、別ディスプレイへの安全なpairing/更新、退会はまだ未実装である。既存Pilot経路・公開サービスには接続しない。

## 実装前に固定・検証する設定

- 登録済みRONRO専用Web ClientのCode + S256 PKCE / `none`、固定Callback URI、logout URI、IdPの許可条件を実接続で照合する。他アプリのClient ID/Secretは再利用しない。実認証試験は未実施であり、Client登録だけで認証完了とみなさない。
- Discovery/JWKSの取得元をissuerに固定し、署名アルゴリズムを許可リスト化して鍵ローテーションを試験する。失敗時は認証拒否とし、未検証claimsを信用しない。
- Web Sessionの発行・失効とCSRF digest、OIDC state/nonce/PKCEの一回使用と期限の保存境界は実装済み。実routeからの呼び出し、全端末logout・退会時の安全な停止/削除、期限切れレコード清掃の運用スケジュールを実装・試験する。Cookieだけ・CSRFだけでは操作を許可しない。
- identity keyの永続保管・復旧・ローテーションを実証する。この鍵を失うと主体対応と既存Web Sessionが使えず、会議のDEKとは別の障害となる。DBバックアップへ鍵を含めない。
- 別アカウント/別Session、失効View資格、Cross-Origin、WSS再接続、Callback再送、評価API露出を統合試験する。
- 会議中のWeb Session期限切れ/IdP一時障害で、会議のCanonical Event列が勝手に終了・削除されないことを検証する。

参考: [ZITADEL OAuth/OIDC推奨フロー](https://zitadel.com/docs/guides/integrate/login/oidc/oauth-recommended-flows)、[OWASP CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)。
