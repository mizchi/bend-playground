# 自己ジャンプの引数で spin に同じ値を 2 回渡すと、貸した側の参照が sink されずメモリが増え続ける

<!-- bug.yml の各欄に対応。テンプレートの見出しは英語のまま -->

### What you did

bend twin.bend -o twin && ./twin --threads 1 --gpu off

### What happened

答えは正しい（`4000010`）が、`go` の 1 回の反復ごとに古いリストのセルが解放されず、
最大 RSS が反復回数に比例して増える。10^6 回・4 セルのリストで 64 MB。
期待は約 10 MB で一定（2 つ目の引数を `X0{}` にすると 10 MB）。

```text
$ ./twin --threads 1 --gpu off     # 最大 RSS 64 MB（Python の resource.getrusage で計測）
4000010
```

生成 C（`bend twin.bend -o twin.c`）では、`go` が `_xs_0 = term_keep(e, _xs_0, 1)` の後
`spin_0(e, _o_0, _xs_0, _xs_0, ...)` を呼び、`_xs_0` を `term_sink` しないまま自己ジャンプする。
`Xs.walk` が spin にならない形（非末尾の cons）では、呼び出し後の継続が `_xs_0` を sink していて、RSS は一定。

`emit_fuse`（bend2/comp.ts @ 7d24b8d0）は tail のときだけ `bind_dead` を呼ぶ。
自己ジャンプは `bind_dead` を走らせないので、自己ジャンプの引数位置で spin を呼ぶと、
貸した twin の残り 1 参照を落とす箇所がない。修正案と回帰テストを PR #<番号> に出す。

再現ファイルと計測手順の gist: <gist URL>

### The file

（twin.bend をそのまま貼る）

### bend --version

bend 2.0.34

### uname -sm

Linux x86_64

### clang --version (the first line)

Ubuntu clang version 18.1.3 (1ubuntu1)
