# Public Evaluation Data Manifest — RONRO / 論路

更新日: 2026-09-21  
目的: 公開Repositoryへ含める評価データの範囲と判断を明示する

このManifestは、評価データを一括公開しないための台帳です。実参加者の音声、文字起こし、Feedback、Observer note、個人情報、顧客・内部情報は公開対象から除外します。Secretや個人情報の本文は記載しません。

## 判定ルール

- **A. Synthetic / Generated**: 決定的なFixture・生成データ。内容と再配布条件を確認できれば公開候補。
- **B. Public Source Derived**: 公開資料から作成したデータ。元資料と再配布条件の確認が必要。
- **C. Real Human / Meeting Derived**: 実参加者・実会議由来。原則として公開しない。
- **D. Customer / Internal Derived**: 顧客・内部情報由来。公開しない。
- **E. Unknown Provenance**: 生成元や再配布条件を確認できない。人間の承認まで公開しない。

## Path別判断

| Path | Provenance | Public Decision | Reason |
| --- | --- | --- | --- |
| `evaluation/fixtures/` | A. Synthetic / Generated | 公開候補 | Repository-authoredの決定的なテスト用Fixture。`evaluation/README.md`で実参加者データではないことを明記する。 |
| `evaluation/scenarios/` | A. Synthetic / Generated | 公開候補 | Fixed TranscriptとFake Analyzerによる再現可能なシナリオ。実参加者データではないことを明記する。 |
| `evaluation/type-d-spike/` | A. Synthetic / Generated | 公開候補 | APIを呼ばないofflineの決定的な検証データ。現在のPrototype設定とは別の検証資料であることを明記する。 |
| `evaluation/live/l4-l5-continuous-simulation.json` | A. Synthetic / Generated | 公開候補 | Repository-authored Continuous Simulatorの生成Artifact。実会議の記録ではないことを`evaluation/live/README.md`で明記する。 |
| `evaluation/30min/` | E. Unknown Provenance | **EXCLUDE FROM PUBLIC** | Recorded benchmarkですが、Provenanceと再配布条件が未確定。元データは削除せず、初回Public Treeから除外する。 |
| `evaluation/real-analyzer/` | E. Unknown Provenance | **EXCLUDE FROM PUBLIC** | Recorded analyzer benchmarkですが、実参加者非該当性と再配布条件が未確定。元データは削除せず、初回Public Treeから除外する。 |
| `evaluation/golden/v2/` | E. Unknown Provenance | **EXCLUDE FROM PUBLIC** | README上でRecorded Analyzer datasetの派生Viewと説明されており、初回Public ReleaseのSynthetic-only条件を満たすと確認できない。 |
| `evaluation/context-spike/` | E. Unknown Provenance | **EXCLUDE FROM PUBLIC** | README上でRecorded Analyzer datasetおよびGoldenを参照するSpikeと説明されており、初回Public ReleaseのSynthetic-only条件を満たすと確認できない。 |
| `evaluation/live/preflight/` | C. Real Human / Meeting Derived の可能性 | 公開対象外 | 実マイクPre-flight由来のRuntime artifact。参加者・環境情報を含み得るため公開しない。 |
| `evaluation/live/sessions/` | C. Real Human / Meeting Derived の可能性 | 公開対象外 | Live Evaluation Session artifact。参加者Feedback・Observer情報等を含み得るため公開しない。 |
| `evaluation/stt/` | C. Real Human / Meeting Derived の可能性 | 公開対象外 | 録音素材・Raw Chunk・STT出力を含み得るため公開しない。 |
| `evaluation/runs/` | E. Unknown Provenance / Generated Output | 公開対象外 | 実Provider実行結果を含み得る生成物。公開Packageへ含めない。 |
| `evaluation/rescored/` | E. Unknown Provenance / Generated Output | 公開対象外 | 再評価結果のRuntime artifact。公開Packageへ含めない。 |

## 初回Public Treeの確認

初回Public Treeへ含める評価データは、`evaluation/README.md`に列挙した4つのSynthetic候補だけとする。各候補には、Repository-authoredの決定的データであり、実Pilot参加者のTranscriptを含まないことを説明するREADMEを用意した。

`evaluation/30min/`、`evaluation/real-analyzer/`、`evaluation/golden/v2/`、`evaluation/context-spike/` は、テスト依存を壊さないよう元データを削除せず、`.gitignore`とPublic Packaging方針で初回Public Treeから除外する。

Synthetic候補に実会議由来の情報が後から混入していると判明した場合は、公開前にそのPathを除外する。
