# Fixture 003: Candidate Decision to Confirmed

## Purpose

AnalyzerがDecision Candidateまでを生成し、Confirmedへの遷移はHuman Commandだけが行うことを確認する。

## Input Discussion

- A: 「スマホUIはMVPから外しましょう」
- B: 「それでいきましょう」
- Human: UI上でConfirm操作を実行

## Expected Events

Analyzerはdecision Nodeをcandidateで作る。自然言語の「それでいきましょう」はEvidenceとして残るが、Analyzerはconfirm_decisionを生成しない。Humanのconfirm_decision Eventで同じNodeをconfirmedへ遷移させる。

## Expected Graph Behavior

- Revision 3ではDecision statusがcandidate
- Revision 4では同一Node IDのstatusがconfirmed
- 新しいConfirmed Decision Nodeは作らない

## Requirement / RFC Decision

- RFC-0001: Candidate / Confirmedを同一Decision Nodeの状態として扱う
- RFC-0002: DecisionはCandidateまでをAnalysis Pipelineが生成
- RFC-0003: CandidateとConfirmedをUI上で混同しない
- RFC-0005: Confirmed Decisionのみ正式Decisionへ出力

## Assumptions

Confirm操作はHuman UI Commandとして扱い、source_evidence_idsは空配列とする。

