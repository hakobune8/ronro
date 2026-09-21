# Fixture 011: Replay Determinism

## Purpose

同一Initial Stateと同一Ordered Event Streamを2回Replayしたとき、Materializerの結果が一致することを確認する。

## Input Discussion

- A: 「MVPはDiscussion Mapを中心にしたい」
- B: 「Mapを見ながら話せるようにする」

## Replay Procedure

replay-manifest.jsonの同一events.jsonをrun-aとrun-bでそれぞれReplayする。両方の結果をexpected-final-graph.jsonのgraphと比較する。

## Expected Graph Behavior

次のすべてが一致すること。

- Final Graphの意味
- Node ID
- Edge ID
- Node / EdgeのStatus
- Graph Revision
- Current Topic

## Requirement / RFC Decision

- RFC-0001: Event StreamからGraphをMaterialize
- Event Catalog: MaterializerはLLM、Clock、Randomnessに依存しない

## Assumptions

同じEvent Streamを参照するため、Event Producer側のAnalyzer非決定性はこのFixtureの対象外である。Analyzer評価とMaterializer評価を分離する。

