# RFC-0010 D7 — 非発話区間のSource/item判定契約（候補）

Status: **設計候補・未承認・未実装**。これはLocal STTの空結果を成功に変える許可ではない。[RFC-0010](../rfc/0010-spot-interaction-and-local-ai-transition.md)と[実装計画](../implementation/rfc0010-spot-delivery-plan.md)のD7を具体化する。Spot上のモデル品質、実機容量、Local Secure、実音声試験はいずれも未受入れ。

## 現行契約と解くべき問題

Core `SourceSTTLedger`はsourceごとの受理済み24 kHz PCM範囲を`STTCommitted`へ結び、非空`STTFinal`だけをTranscript Evidence候補にする。空FinalはEvidenceを作らず、非ゼロ信号の可能性があるitemをDrainで未解決に残す。`STTFailure`も同様に未完了とする。デジタルゼロと小振幅からは「発話なし」を一般化できず、時系列の隣接や他sourceのFinalからも補完しない。この保守的挙動を既定として維持する。

`whisper-server`の`{"text":""}`は、あるitemの全区間に発話が存在しなかったという型付きの証明ではない。BGM、小声、相づち、重なり、モデル失敗のどれでも空になり得る。現行ContentのLocal STT Unix契約はテキストのみを返し、VAD区間・検出器版・判定対象範囲を持たない。したがって現行Bridge、Local STT adapter、Coreに対して、空文字を「非発話で完了」と読み替える変更はしない。

## 最小の将来契約

実装を検討する場合の仮称は`STTNoSpeech`とする。これは**Provider正規化後のSource/item結果**であってCanonical Discussion Event、Transcript Evidence、Graph Nodeではない。意味は「検証済みの判定方針が、この`STTCommitted`の**全PCM範囲**に発話がないと判定した」であり、「音がない」「録音が成功した」「会議で発言がなかった」ではない。

```text
STTCommitted(source, item_id, audio_range)
  → STTFinal(source, item_id, nonempty_text)   # Evidence候補
  | STTNoSpeech(source, item_id, audio_range)   # Evidenceを作らない候補
  | STTFailure(source, item_id, safe_code)      # 未完了
  | empty Final / no result                     # 信号の可能性があれば未完了
```

`STTNoSpeech`の必須値は`source`、`item_id`、`audio_range`のみ。判定器のartifact digestと評価済み方針の識別子は、Contentが実際に検証した**run設定**へ結び、保護されたSource監査記録へ併記する。Peerの自己申告だけで版を確定しない。モデル・判定器がrun中に変わるなら、新しい設定として再検証するまで結果を受理しない。形式の最終決定はCore/Event契約変更PRで行う。

Coreで決定的に検査できるのは、同一source、既知のitem ID、Committedと**完全一致する範囲**、一度だけの結果、Final/Failure/別判定との競合、Provider drain後の到着拒否である。異source、未知・部分・重複範囲、self-reportedな「音声なし」だけの応答は拒否する。**これらの検査は発話なしという意味の正しさを証明しない。** 1 itemに発話と非発話が混在する場合、item全体を非発話にはできない。必要なら先に範囲を切って別itemとし、隙間・重複をCoreで検査する。モデルの空テキストを後から判定イベントへ変換しない。

## 受理・監査・再生の境界

1. 既定は無効。Contentは、固定された判定器・モデルのdigest、判定方針版、対象run、実際のlocal peerを照合した構成でのみ候補結果をCoreへ渡す。未承認のProvider、実行時の不明な版、区間を返さないupstream、検査失敗では空Finalの既存未完了処理に戻す。Cloudへfallbackしない。
2. `STTNoSpeech`をDrain完了の根拠にする**前**に、Contentは保護されたrun内Source監査へ、source/item、受理PCMの相対sample範囲、判定結果、検証済み方針・artifact識別子を耐久記録する。Raw Audio、全文Transcript、参加者本人、モデルの自由文をこの記録や通常ログへ混ぜない。監査書込み失敗は未完了であり、Graphに補完イベントを作らない。
3. 同一結果の再送は冪等、異なる結果・範囲への書き換えはIntegrity Errorとする。Coreのitem完了状態は監査受理後に進める。Sourceのcapture closeとProvider drainは別に必要であり、非発話判定だけで会議Endや他sourceを進めない。既存の不完全区間を後から一括で完了へ昇格させない。
4. Source監査はCanonical Event/Graphの正本ではなく、同じrunの終了判定を説明する保護記録である。Graph replayは従来どおり受理済みEventだけから決まる。Contentの現行runはPod消滅後の復旧を保証しないため、この設計だけで再起動復旧を約束しない。監査とSource状態を再生できると主張する場合は、別途クラッシュ境界の試験を要する。runの受取期限でほかの一時記録とともに消去する。
5. Controller/Displayのマイク・処理中表示はこの判定から「聞き取れた」を推定しない。非発話itemからNode、Decision、Action、Owner、Dueを作らない。未解決区間が残れば`ended_incomplete`とPDFの欠落可能性表示を維持する。

## 判定器を有効にする前の評価

多言語whisper.cpp **smallとmediumのそれぞれ**で、同一の人手確認済み・Evidence完全な日本語区間を使う。通常／小声／短い相づち／技術語／否定／BGM下の発話／複数人の重なり／環境音のみ／音楽のみ／デジタルゼロ／発話と非発話の混在を含める。完全非発話と判定してよいitem、発話を含むitem、不確実itemを人が独立に区別する。モデルにHumanラベルを渡さず、モデル間でfixture、順序、分割、負荷条件を揃える。私有音声・書き起こし・case別結果はGit/PR/通常ログへ載せない。

主指標は**発話を含むitemを誤って非発話完了にした件数**とその内容の重要度である。完全非発話itemの回収率、空Final未解決数、STTのCER、1/4/8 sourceの待ち時間・CPU/RAMは別指標とする。ゼロ誤判定の小標本を一般的な無欠落保証と呼ばない。小声・BGM等の難条件で一つでも欠落疑いがあれば、その条件を自動完了させない方針をHuman Reviewで決める。現行upstreamが区間と判定理由を出せないなら、Bridgeに空文字からの推測を足さず、明示的なローカル検出器または別プロトコルを評価する。

## 実装PRの依存順（承認後）

| 順 | Repository / 責務 | 変更とテスト | 完了条件 |
| --- | --- | --- | --- |
| 1 | `ronro` Core | 仮称`STTNoSpeech`とLedgerの全範囲・同一source・競合・重複・late/drain検査。既定は不受理。空Finalの現行挙動を回帰 | Core単体/ReplayがGreen。新結果がCanonical EventやEvidenceを作らない |
| 2 | `natade-coco-ronro` Content | 明示opt-inのrun方針、検証済みartifact identity、Source監査の先行書込み・失敗時incomplete、再試行冪等、PDF/Endの未完了表示。Core wheelを固定更新 | 合成正常/混在/衝突/監査失敗/再起動境界で欠落を隠さず、Cloud-demo不変 |
| 3 | Spot-local AI Runtime候補（Content側） | 全区間の型付き判定を出せる実装と区間対応。whisper.cpp空文字を判定へ転用しない。公開前にsource・モデル・ライセンスとログを審査 | 同一private fixtureでsmall/mediumの誤非発話・遅延・資源結果をHuman Review。モデル未選定なら無効のまま |
| 4 | Platform/Fleet・実機 | 限定Digest、実効通信境界、1/4/8台と2時間、音声→Final/Evidence→Graph、End/Drain/PDFを実測 | #104の対象版で個別PASS。未確認をPASSにしない |

この候補はD7の欠落隠蔽を避けるための設計であり、PR 1–2を先行してもPR 3–4の品質・実機結果がなければ自動非発話完了を**有効化しない**。
