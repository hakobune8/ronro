# Fixture 012: Relation Constraints

## Purpose

Prototype 1で許可する最小Relation Matrixを固定し、ValidなRelationとInvalidなRelationを区別する。

## Valid Matrix

| Relation | Source | Target |
| --- | --- | --- |
| contains | topic | idea、option、concern、open_item、decision、action |
| has_option | topic | option |
| supports | idea、option | idea、option、decision |
| opposes | idea、option、concern | idea、option、decision |
| related_to | 任意の非Archived Node | 任意の非Archived Node |

## Expected Events

events.jsonにはMatrixに適合するcontains、has_option、supports、opposes、related_toを1件ずつ含める。invalid-cases.jsonにはMatrix外の組合せをSuffixとして定義する。

## Expected Graph Behavior

Valid EventはEdgeを追加する。Invalid Relationはunsupported_relationで拒否し、拒否前のGraph Stateを変更しない。

## Requirement / RFC Decision

- RFC-0001: Relation TypeをSchema Enumで制限
- Event Catalog: Relation Matrix外の組合せをMaterializerで拒否

## Assumptions

related_toだけは意味的な用途が広いため、Prototype 1では非Archived Node間に限定する。Self relationは許可しない。

