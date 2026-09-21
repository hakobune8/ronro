# Fixture 006: Human Correction

## Purpose

Rename、Archive、MergeをすべてEventとして記録し、AIの誤整理を人間が会議を止めずに修正できることを確認する。

## Input Discussion

- AI: 「価格モデル」
- AI: 「Visual生成」
- AI: 「イメージ生成」
- AI: 「一時的なメモ」
- Human: 「価格モデル」を「料金体系」にRename
- Human: 「Visual生成」と「イメージ生成」をMerge
- Human: 「一時的なメモ」をArchive

## Expected Events

Rename、Merge、ArchiveはいずれもHuman EventとしてAppendする。Mergeのsource Nodeは物理削除せずarchivedとして残す。

## Expected Graph Behavior

- 価格モデルのNode IDを保ったままLabelだけ変更
- Visual生成をCanonical Nodeとして残す
- イメージ生成のNodeとEvidence / Event履歴を残す
- 一時的なメモをarchivedにする

## Requirement / RFC Decision

- RD 16: Human Correction
- RFC-0001: 自動Mergeを行わずHuman Correctionで確定
- Architecture Summary: DeleteはArchive / Tombstone

## Assumptions

MergeのCanonical Targetは先に作られたVisual生成Nodeとする。Mergeに伴うEdge再接続は、このFixtureではEdgeがないため発生しない。

