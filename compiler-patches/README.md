# Bend 本体の実験パッチ

固定版 `7d24b8d0235cb9781140512c0f163c48ea84a719` を基準に、次の順に試す。
`upstream/bend` と `bend2/bend.ts` は変更せず、各実験のパッチと検証結果をここに保存する。
別 checkout は無視対象の `build/bend-steps/` に置き、`BEND_REPO` で選ぶ。

| Step | 実験 | 確認すること | 状態 |
| --- | --- | --- | --- |
| 1 | [FFI の runtime ID 登録](step-01-ffi-runtime-ids/README.md) | 通常の `FID(...)` で closure/emit を呼べる。既存 C 生成結果が変わらない | 実装・検証済み |
| 2 | [既知 callback の特殊化](step-02-known-callbacks/README.md) | 同じ Bend ソースから closure と動的呼び出しを減らせる。CPU/Metal の結果と時間を旧版と比較 | 試作・計測済み（コード量 gate は未達） |
| 3 | 内部 flat helper の型付き戻り値 | `Term*` の出力を型付き構造体に置き換え、C/Metal の最適化に効果があるか測る | 未着手 |
| 4 | 独立配列更新の専用 GPU kernel | scalar capture、固定幅要素、非重複書き込みの契約を検査して直接 dispatch する | 未着手 |

Step 2 以降は、まず小さい再現例で探索 → Red → Green → Refactoring を行う。
粒子の callback/flat 両ソースを旧版・修正版でコンパイルし、同じ count、jobs、noise、
worker 数で比較する。検証・ビルドを先に終え、時間計測は静かなマシンで直列に行う。
CPU 更新、GPU 実行、待機を含む更新、画像準備までの時間を分けて記録する。

専用 kernel は [既存の直接 leaf 実験](../examples/particles/GPU.md)を出発点にするが、
実験の kernel 名や `spin_16` に依存する挿入を compiler の一般的な契約に置き換える。
`Array.map` の新規配列生成や配列の共有・所有権の意味を保つ。

範囲が証明できる loop の特殊化と async submit/await は、その後の候補とする。
一般の配列 index mask や Metal の `coherent` は一括で削除しない。
