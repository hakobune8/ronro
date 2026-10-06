# Account Service v1 — Identity ADR (P2)

Status: ZITADEL採用をHumanが承認。RONRO専用OIDC Clientの登録・実認証は未実施。

## 決定

既存のZITADELをIdentity Providerとし、RONRO専用のOIDC Clientを登録する。他アプリのClient ID・Secret・redirect URIは流用しない。既存Pilotの`controller_id`も認証主体にはしない。

WebログインはAuthorization Code + PKCEを使う。サーバーは事前に設定した単一issuerのDiscovery/JWKSを参照し、署名、issuer、audience、期限、nonce、stateを検証してから`issuer + subject`を内部userへ写像する。メールアドレスは永続識別子にしない。Callback URIと許可Originは環境ごとに固定し、任意URLへのredirectを許さない。認証コード、PKCE verifier、token、cookie、CSRF値はログ・URL query（OIDC規格上の一時的なCallback queryを除く）・PDFへ残さない。

検証後はサーバー側Web Sessionを発行し、ブラウザには`__Host-` prefixのHost-only、`Secure`、`HttpOnly`、`SameSite=Lax` cookieのみを渡す。状態変更にはSession結合CSRF tokenと厳密なOrigin照合を併用する。WSSもOriginとSession権限を照合し、接続中の失効・Session終了・Capture generation変更を反映する。View-only資格は別のSession限定権限で、ownerのWeb Sessionと混同しない。

ブラウザのログイン期限切れ・再認証は、すでに受理済みの会議Sessionを自動終了させない。操作再開には再認証を要求し、音声取込みの継続/欠落はP3のCapture状態とgapで説明する。期限切れを黙って`ended`と扱わない。会議時間が約2時間を超えても終了を強制しない。

`prototype/service_browser_security.py`はOrigin/CSRF/Cookie形式の独立した検証境界を持つ。`prototype/service_oidc.py`は専用ClientのCode + S256 PKCE認可URL、state/nonce照合、固定HTTPS JWKSからのRS256 ID Token検証を持つ。合成鍵の単体テストは通っているが、認可試行の一回限りの永続化、RONRO専用Client登録、実ZITADELでのToken交換、Web Session、route保護はまだ未実装である。既存Pilot経路・公開サービスには接続しない。

## 実装前に固定・検証する設定

- RONRO専用Clientのissuer、client ID、Client認証方式、固定Callback URI、logout URI、許可Originを環境別に登録する。Secretは配備Secretにのみ置く。
- Discovery/JWKSの取得元をissuerに固定し、署名アルゴリズムを許可リスト化して鍵ローテーションを試験する。失敗時は認証拒否とし、未検証claimsを信用しない。
- Web Sessionの保存・失効・全端末logout・退会、CSRF digestのSession保存、OIDC state/nonce/PKCEの一回使用と期限を実装する。Cookieだけ・CSRFだけでは操作を許可しない。
- 別アカウント/別Session、失効View資格、Cross-Origin、WSS再接続、Callback再送、評価API露出を統合試験する。
- 会議中のWeb Session期限切れ/IdP一時障害で、会議のCanonical Event列が勝手に終了・削除されないことを検証する。

参考: [ZITADEL OAuth/OIDC推奨フロー](https://zitadel.com/docs/guides/integrate/login/oidc/oauth-recommended-flows)、[OWASP CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)。
