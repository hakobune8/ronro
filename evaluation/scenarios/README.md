# M6 Analyzer Scenarios

ここにあるScenarioはGolden Event Fixtureとは分離した、Transcript起点のEnd-to-End検証入力である。

`m6-e2e.json` は、Fixed Transcript → Fake Analyzer → Candidate Events →
Human Commands → Graph Materialization → Stable Mapの一連の体験を検証する。
AnalyzerはDecisionをCandidateまでしか生成せず、ConfirmとParkingはScenarioのHuman
Commandとして明示している。

Scenarioの期待値を実装結果に合わせて変更してはならない。挙動を変更する場合は、先に
Canonical ContractまたはFake Analyzerのルール変更として理由を記録し、その後に期待値を更新する。
