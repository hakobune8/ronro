# Contributing to RONRO

小さな修正、ドキュメント改善、再現可能な不具合報告を歓迎します。

## Issue

再現手順、期待した結果、実際の結果、実行環境を簡潔に記載してください。秘密情報、実参加者の発話、Raw Audio、個人情報は添付しないでください。

## Pull Request

- 変更の目的と影響範囲を説明する
- 関連するテストとドキュメントを更新する
- Product / Architectureの変更では、関連する要件またはRFCを確認する
- Analyzer、STT、Canonical Event、Materializerを変更する場合は、回帰リスクを明記する

## テスト

```sh
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -v
```

通常のテストから外部LLM APIや外部STT APIを呼び出さないでください。実Providerを使う確認は、秘密情報と費用を管理できるローカル環境で個別に行います。

## ライセンス

Pull Requestを送ることで、変更内容をこのリポジトリの[Apache License 2.0](LICENSE)に従って提供できることを確認してください。第三者素材を追加する場合は、再配布条件と必要なNOTICEを明記してください。
