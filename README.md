# RONRO / 論路

**議論の現在地を共有する。**

![論路の共有画面](docs/pilot/assets/ronro-shared-view-stage-3.png)

論路（ろんろ / RONRO）は、会議中の議論を「論点図」として整理し、参加者が「今、何を議論しているか」「何が決まりつつあるか」「何がまだ残っているか」を共有するためのオープンソース・プロトタイプです。

会議後に読むAI議事録ではなく、会議中に見るための共有画面を目指しています。

## 何を作っているか

会議では、複数の論点を行き来したり、以前の論点へ戻ったりします。論路は、議論の流れと現在の状態を同じ共有画面へ整理します。

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
- `gpt-5.6-luna` / `analyzer-prompt-v4` によるAnalyzer経路
- Current Topic、決定候補、未解決事項、次の対応、話の流れの表示
- Human Commandによる進行役の修正・確認
- Session DrainとEvaluation Harness
- 1920×1080を対象とした読み取り専用の論点図共有画面

現在は **prototype / live pilot stage** です。Production運用、複数ルーム、永続的な業務データ管理を目的としたものではありません。Visual Artifact生成と会議議事録生成は、現時点の実装済み機能には含めていません。

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

- `http://127.0.0.1:8000/` — 開発・進行役向け画面
- `http://127.0.0.1:8000/shared` — 参加者向け読み取り専用画面

マイクは画面上で開始操作をした後にのみ使用されます。公開URLやHTTPS Ingressを使う場合の配備手順は[デプロイ手順](docs/deployment/kubernetes-pilot-deployment.md)を参照してください。

## テスト

```sh
.venv/bin/python -m unittest discover -v
```

テストでは、イベント検証、Materializer、Replay、Analyzer境界、音声・STTアダプター、Queue、Session Drain、Shared View、Evaluationを確認します。通常のテストから外部LLM APIは呼び出しません。

## ドキュメント

- [MVP要件](docs/requirements/discussion-map-ai-facilitator-mvp.md)
- [Architecture Summary](docs/architecture/mvp-architecture-summary.md)
- [論路のNaming Decision](docs/product/ronro-naming.md)
- [ライブパイロットガイド](docs/pilot/ronro-live-pilot-guide.md)
- [Live Pilot Protocol](docs/evaluation/live-pilot-protocol.md)
- [Kubernetes配備手順](docs/deployment/kubernetes-pilot-deployment.md)
- [Public Release Readiness](docs/release/public-release-readiness.md)
- [Security Policy](SECURITY.md)

RFCや過去の評価資料には、当時の作業名 `Discussion Map` が残っています。これは履歴の追跡性を保つためであり、現在の参加者向け名称は論路 / 論点図です。

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
