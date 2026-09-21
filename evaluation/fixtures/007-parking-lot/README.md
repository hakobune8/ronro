# Fixture 007: Parking Lot and Restore

## Purpose

Parking LotをNode TypeではなくNode statusとして扱い、Node IDとEvidenceを保ったままRestoreできることを確認する。

## Input Discussion

- A: 「Teams連携も将来検討したい」
- Human: 「これは今回は後回し」
- A: 「Teams連携の話に戻ろう」

## Expected Events

Topicを作成し、Humanのmove_to_parking_lotでparkedにする。その後restore_from_parking_lotでactiveへ戻し、明示的なtopic_focus_changedでCurrent Topicへ復帰する。

## Expected Graph Behavior

- Parking Lot専用Node Typeを作らない
- Node IDは全期間で同一
- Revision 5ではstatus parked
- Restore後はstatus active
- Restoreは自動Focusではない。明示Focus EventでCurrent Topicに戻す
- Fixtureでは、Current TopicだったNodeをParking Lotへ移動した時点でcurrent_topicをnullにする

## Requirement / RFC Decision

- RD 8.9: Parking Lot
- RFC-0001: Parking Lotはstatus parked
- RFC-0003: Parking Lot移動とCurrent Topic表示

## Assumptions

ParkingされたCurrent Topicは通常表示対象から外すため、Materializerはcurrent_topicをnullにする。RestoreだけではFocusを戻さず、戻りは別のAnalyzer Eventで明示する。

