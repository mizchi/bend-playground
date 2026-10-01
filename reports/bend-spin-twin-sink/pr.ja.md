# jump の引数の中で呼んだ spin は、貸された変数を呼び出しの後で sink する。ループが古いリストのセルを持ち続けなくなる (#<issue>)

`go(p, Xs.walk(xs, xs, X0{}))` のように jump の引数の中で spin を呼び、spin が借用する引数に
そこで死ぬ変数を貸すと、その変数を sink する箇所がなかった。`emit_fuse` は tail のときしか
`bind_dead` を呼ばず、jump も `bind_dead` を走らせないため。結果は正しいが、反復ごとに古いリストのセルが残る（#<issue>）。

変更は `emit_fuse` の 1 行: 非 tail の呼び出しの後も `bind_dead(fl, fl.rest)` で、残りで使われない束縛を sink する。
tail のときは従来通り。jump の引数以外でも、非 tail の spin 呼び出しの後で死ぬ束縛は早めに sink されるので、
継続のフレームが 1 語小さくなる場合がある（bench の hashmap では既存の `term_sink` が spin 呼び出しの直後に移る）。

テスト: `tests/reg/spin_lent_sink.bend`。同じ値を 2 回渡す形（`go`）と、別の呼び出し元のせいで借用になった引数に 1 回渡す形（`go2`）。
test.ts は RSS を見ないので、`closure_value_owns.bend` と同じくヘッダに書いた。
修正前 79 MB → 修正後 10 MB（`--threads 1` と `--threads 4` で同じ）。生成 C の差分は spin 呼び出し 2 か所の後の `term_sink` だけ。

確かめきれていない点: `emit_fork` の逐次側は、引数を `rest: [chain[i]]` で評価する。
ここで fork 呼び出しの引数の中にある spin が、hold だけで生きている束縛を受け取ると、並列側と live が食い違いうる。
そうなる例は作れず、試した fork のプログラムの C は修正前と同一だった。

<details>
<summary>ローカルでの確認</summary>

- gates/repo.ts: PASS 49 / 49
- tests/ の全 .bend を C レーンと JS レーンで修正前後に実行: 結果は同じで、変わったのは新しいテストが通った 1 件だけ
  （C: pass 670 → 671、JS: 692 → 693。残りは型エラー出力を期待値にするテストと、この環境で落ちる io/ のテストで、修正前後で同じ）
- bench/runtime の 16 本: 生成 C は 15 本が同一、hashmap は上記の 1 行の移動
- gates/test.ts と gates/perf.ts はクラスタ前提のため未実行。GPU なし
- Linux x86_64（Intel Xeon、4 スレッド）、Ubuntu clang 18.1.3、bend 2.0.34 (7d24b8d0)

</details>
