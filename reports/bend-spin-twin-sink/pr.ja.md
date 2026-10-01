# 自己ジャンプの引数で呼んだ spin は、貸した twin を呼び出しの後で sink する (#<issue>)

<!-- コミット件名も同じ文（upstream の慣例: 新しい振る舞いを 1 文で、末尾に (#issue)） -->

`go(p, Xs.walk(xs, xs, X0{}))` のように、自己ジャンプの引数位置で spin（flat な def）に
同じ値を 2 回渡すと、`go` は `xs` を 1 回 keep して 2 つ目の引数に貸す。
貸した参照はこの呼び出しで死ぬが、`emit_fuse` は tail のときしか `bind_dead` を呼ばず、
自己ジャンプも `bind_dead` を走らせないので、誰も sink しなかった。
結果は正しいが、反復ごとに古いリストのセルが残る（#<issue>）。

変更は `emit_fuse` の 1 行: 非 tail の呼び出しの後も `bind_dead(fl, fl.rest)` で、
残りの項で使われない束縛を sink する。tail のときの動作は従来通り。
生成 C では spin 呼び出しの直後に `term_sink(e, _xs_0);` が 1 行増える。

テスト: `tests/reg/spin_twin_sink.bend`（4 セルのリストで 10^6 反復、答えを固定）。
test.ts は RSS を見ないので、`closure_value_owns.bend` と同じくヘッダに RSS を書いた。
修正前 64 MB → 修正後 10 MB（`--threads 1`、Linux x86_64）。

<details>
<summary>ローカルでの確認</summary>

- gates/repo.ts: PASS 49 / 49
- tests/ の全 .bend を C レーン（`-o t` → `./t --gpu off`）と JS レーン（`-o t.js` → `bun t.js`）で
  修正前後に実行し、`#|` 行との一致を比較: <結果>
- gates/test.ts と gates/perf.ts はクラスタ前提のため未実行
- 環境: Linux x86_64（Intel Xeon、4 スレッド）、Ubuntu clang 18.1.3、bend 2.0.34 (7d24b8d0)。GPU なし

</details>
