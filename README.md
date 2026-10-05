# RONRO / 論路

**議論の現在地を共有する。**

![現在の論点図：課題から案と決定候補へ展開した画面](docs/pilot/assets/ronro-focused-flow-stage-2.png)

*現行の Focused Flow を制御された合成会議で表示した例です。実会議の記録や、AIによる関係付けの正確さを示すものではありません。*

論路（ろんろ / RONRO）は、会議中の議論を「論点図」として整理し、参加者が「今、何を議論しているか」「何が決まりつつあるか」「何がまだ残っているか」を共有するためのオープンソース・プロトタイプです。

会議後に読むAI議事録ではなく、会議中に見るための共有画面を目指しています。

## 何を作っているか

会議では、複数の論点を行き来したり、以前の論点へ戻ったりします。論路は、上部の「話の流れ」と、今話している論点の近くにあるつながり・状態を同じ共有画面へ整理します。

![話題が移ったときの「話の流れ」と現在の論点](docs/pilot/assets/ronro-focused-flow-topic-change.png)

*こちらも制御された合成会議の画面例です。現在の話題を左端に示し、無関係な論点を無理に結びません。*

- 今話していること
- 出てきた考えや選択肢
- 決定候補（自動確定ではありません）
- 未解決事項
- 次の対応
- これまでの話の流れ

参加者は共有画面を操作せず、必要なときに論点図を見て議論の現在地を確認します。AIの出力が正しいとは限らないため、最終的な判断は人が行います。

## 仕組み

```text
音声
  ↓
Speech-to-Text
  ↓
Discussion Analyzer
  ↓
Candidate Events
  ↓
Event Store / Materializer
  ↓
Discussion Graph
  ↓
論点図（Shared View）
```

音声入力はブラウザのAudioWorkletからバックエンドへ送り、バックエンドがOpenAI Realtime transcriptionとAnalyzerを呼び出します。確定した発話だけが既存のイベント・グラフ処理へ入り、共有画面へ反映されます。

## 現在実装されているもの

- ブラウザのマイク入力とPCM変換
- ローカルWebSocketによる音声転送
- `gpt-transcribe` によるRealtime transcription（用語ヒント対応）
- Final Transcriptの正規化（Normalization v2）
- FIFO Queueと単一Analyzer Worker
- `gpt-5.6-luna` / `analyzer-prompt-v10-action-time-horizon` によるAnalyzer経路（Pilot候補設定）
- Focused Flowによる現在の論点と、上部の「話の流れ」の表示
- 根拠がある場合の論点間のつながり、決定候補、未解決事項、次の対応の表示
- Human Commandによる進行役の修正・確認
- Session DrainとEvaluation Harness
- 1920×1080を対象とした読み取り専用の論点図共有画面

現在は **prototype / live pilot準備段階** です。Production運用、複数ルーム、永続的な業務データ管理を目的としたものではありません。会議後の記録を正式な成果物として提供する機能は、現時点の実装済み機能に含めていません。

## ローカルで試す

### 必要なもの

- Python 3.12程度のPython環境
- マイクを利用できるブラウザ（Realtime Audioを試す場合）
- OpenAI API key

### 起動

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env
# .env の OPENAI_API_KEY に自分のキーを設定する
.venv/bin/python -m prototype.server --host 127.0.0.1 --port 8000 --live-ws-port 8765
```

ブラウザで次を開きます。

- `http://127.0.0.1:8000/` — 参加者向け読み取り専用の論点図
- `http://127.0.0.1:8000/session` — 進行役向けスマートフォンController / Microphone
- `http://127.0.0.1:8000/control` — 開発・進行役向け画面
- `http://127.0.0.1:8000/shared` — `/`の互換入口

マイクは画面上で開始操作をした後にのみ使用されます。公開URLやHTTPS Ingressを使う場合の配備手順は[デプロイ手順](docs/deployment/kubernetes-pilot-deployment.md)を参照してください。

## テスト

```sh
.venv/bin/python -m unittest discover -v
```

テストでは、イベント検証、Materializer、Replay、Analyzer境界、音声・STTアダプター、Queue、Session Drain、Shared View、Evaluationを確認します。通常のテストから外部LLM APIは呼び出しません。

## ドキュメント

- [ドキュメント案内（現行資料と履歴資料）](docs/README.md)
- [MVP要件（改名前の名称を保持）](docs/requirements/discussion-map-ai-facilitator-mvp.md)
- [Architecture Summary](docs/architecture/mvp-architecture-summary.md)
- [論路のNaming Decision](docs/product/ronro-naming.md)
- [ライブパイロットガイド](docs/pilot/ronro-live-pilot-guide.md)
- [Live Pilot Protocol](docs/evaluation/live-pilot-protocol.md)
- [Kubernetes配備手順](docs/deployment/kubernetes-pilot-deployment.md)
- [Public Release Readiness](docs/release/public-release-readiness.md)
- [Security Policy](SECURITY.md)

この公開リポジトリは `hakobune8/ronro` です。改名前のMVP要件、RFC、過去の評価資料には当時の作業名 `Discussion Map AI Facilitator` が残っています。履歴の追跡性を保つため、その記録を一括置換していません。現在の参加者向け名称は論路 / 論点図です。

## 制約とデータの扱い

- AIの整理結果には誤りが含まれる可能性があります。
- 決定候補は自動的に確定されません。最終判断は人が行います。
- マイク音声はSpeech-to-Textと議論整理のため外部APIへ送信されます。
- Raw Audioはデフォルトで永続保存しません。Evaluation Artifactの扱いは実行環境の設定と同意に従います。
- 機密性の高い会議で利用する場合は、データの送信先・保存設定・参加者への説明を事前に確認してください。

## 今後の候補

Pilotで得た知見をもとに、長時間会議での扱い、より堅牢なAnalyzer、配備・認証・永続化の見直しを検討します。これらは現時点でProduction機能として約束するものではありません。

## Contributing

小さな修正や質問はIssue、変更提案はPull Requestで歓迎します。Canonical EventやArchitectureを変更する場合は、先に関連する要件・RFC・回帰テストを確認してください。詳しくは[CONTRIBUTING.md](CONTRIBUTING.md)を参照してください。

## License

このリポジトリのコードと文書は、個別の第三者ライセンス表示があるものを除き、[Apache License 2.0](LICENSE)の下で提供します。第三者依存ライブラリのライセンス条件も各配布物で確認してください。
