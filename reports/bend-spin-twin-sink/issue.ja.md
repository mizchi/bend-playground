# jump の引数の中で spin に貸した変数が、その呼び出しで死んでも sink されず、ループのたびに RSS が増える

<!-- bug.yml の各欄に対応。テンプレートの見出しは英語のまま -->

### What you did

bend twin.bend -o twin && ./twin --threads 1 --gpu off

### What happened

答えは正しい（`4000010`）が、`go` の 1 回の反復ごとに古いリストのセルが解放されず、
最大 RSS が反復回数に比例して増える。10^6 回・4 セルのリストで 64 MB（Python の `resource.getrusage` で計測）。
2 つ目の引数を `X0{}` にすると 10 MB で一定。

生成 C（`bend twin.bend -o twin.c`）では、`go` が `spin_0(e, _o_0, _xs_0, _xs_0, ...)` を呼ぶ。
`spin_0` は両方の引数を借用として受け取り、1 つ目を `term_peek` で読み、2 つ目は読まずに次の反復へ渡す。`go` は `_xs_0` を `term_sink` しないまま自己ジャンプする。
`let` で結果を一度束縛すると、その後の `bind_dead` が sink して RSS は一定になる。

`emit_fuse`（bend2/comp.ts @ 7d24b8d0）は tail のときだけ `bind_dead` を呼び、jump も `bind_dead` を走らせない。
そのため jump の引数の中で spin を呼ぶと、spin に貸してそこで死ぬ変数を sink する箇所がない。
同じ値を 2 回渡す必要はない: 別の呼び出し元が貸しているせいで借用になった引数に、ここで死ぬ変数を 1 回渡しても起きる
（PR のテストの `go2`）。`go(p, Xs.rev(Xs.walk(xs, xs, X0{}), X0{}))` のように引数の奥にあっても起きる。
確認したのは自己ジャンプだけで、別の def への jump も同じ経路を通るが試していない。

2.0.23（75cb8f3e）でも同じく 64 MB。open な PR の head（#1000 以降）に `emit_fuse` のこの分岐を変えるものは無かった。
修正案と回帰テストは PR #<番号>。再現ファイルと計測手順の gist: <gist URL>

### The file

（twin.bend をそのまま貼る）

### bend --version

bend 2.0.34（`bend version` の出力。main では `bend --version` は未知のオプションになる）

### uname -sm

Linux x86_64

### clang --version (the first line)

Ubuntu clang version 18.1.3 (1ubuntu1)
