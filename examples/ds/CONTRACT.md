# Bend 実験の共通コントラクト（第2ラウンド: データ構造と経路探索）

Bend 2.0.23 / Apple M5 (10 core) / Metal / clang 21。
repo: mizchi/bend-playground
Bend: `upstream/bend`（submodule、固定コミット `75cb8f3e`）

**作業はこのディレクトリ以下でやること。** `/tmp` は一度再起動で消えた。

## 走らせ方

`just setup` の後、repo 直下からラッパー経由で動かす。

    just setup
    just bend <file>.bend                 # 型検査して main を走らせる
    just bend <file>.bend --check-only    # 検査だけ
    just bend <file>.bend -o <out>        # ネイティブ (clang -O3 + Metal)

バイナリの実行モード:

    <out>                       # GPU (! があれば使う)
    <out> --gpu off             # CPU 全コア
    <out> --threads 1 --gpu off # CPU 1 コア
    <out> --gpu 8GB             # GPU ヒープを広げる (既定 2GB、起動時固定・伸長不可)

## 言語イディオム（ここで必ず詰まるので先に読む）

### アフィン型: 値は高々 1 回

    U32.add(u, v) と U32.sub(u, v) で u,v を 2 回使う → エラー
    直し方: パターン側で + を付ける。 case L{+u} L{+v}:
            let 側なら +h = ...
    エラー文言: "v (consumed more than once)"

`+x: A` と書けるのは `A : Data` のときだけ。

### Array は複製できない（重要）

    def two(+a: Array<U32>) -> U32: ...
    → Error: expected : Data / observed : Type

    def two(a: Array<U32>) -> U32:
      x y = pick(a[0]) pick(a[1])
    → Error: a (consumed more than once)

**配列を 2 つの fork から読むことは原理的に不可能。**
配列ベースのアルゴリズムは単一インスタンス内では必ず逐次になる。
これは発見であって回避対象ではない。`Array.fork` / `Array.join` は @unsafe なので使わない。

Array を持つ record は `type St is Type:` と宣言する（`is Data` は通らない）。

### Data の木は複製できる（重要）

    def two(+t: T) -> U32:
      x y = sum(t) sum(t)
      U32.add(x, y)
    → 通る

`+` は深いコピーではなく**参照カウントの atomic increment**（`comp.ts:4056` の `term_keep`）。
なので「1 本の木を並列に読む」は可能。粒度を上げたいときはこれを使う。

### 相互再帰は禁止

前方参照は見えない。ヘルパは使用箇所より**前**に定義する。
エラー文言: "expected: a defined name"

### 計算値の match は書けない

    match U32.is_lt(i, s):     → Error: a match cannot scrutinize a computed value
    match x:                   （x が let 束縛でも不可: "cannot scrutinize a local binder"）

回避: 判定結果を **Bool のパラメータとして呼び出し側から渡す**。
ヘルパ def を挟むと相互再帰になるので、多スクルティニ match で 1 つの def に畳む:

    def get(t: T, +i: U32, +s: U32, lt: Bool) -> U32:
      match t lt:
        case L{v} True{}:  v
        case L{v} False{}: v
        case N{a, b} True{}:
          +h = U32.shrn(s, 1n)
          get(a, i, h, U32.is_lt(i, h))
        case N{a, b} False{}:
          +j = U32.sub(i, s)
          +h = U32.shrn(s, 1n)
          get(b, j, h, U32.is_lt(j, h))

### 再帰は構造的に減る必要がある

「条件が成立するまでループ」は書けない。**燃料 (fuel) 付き Nat** を使う:

    def loop(f: Nat, r: St & Bool) -> St:
      match f:
        case 0n:
          (st, more) = r
          st
        case 1n+p:
          (st, more) = r
          match more:
            case False{}: st
            case True{}:  loop(p, step(st))

### 並列 fork の作り方

「2 個以上の束縛が全部 call である let」だけが fork になる:

    a b = f(x) g(y)        # ← これが fork
    U32.add(a, b)

`f!(x)` の `!` で GPU に投げる。main 側の呼び出しに 1 個付ければよい。

### Array API

    Array.new(-T: Data, +d: Nat, +v: T) -> Array<T>   # 2^d 個を v で埋める
    a[i]            # Array.get: (Array<T> & T) が返る。配列ごと返ってくる
    a[i] <- v       # Array.set: Array<T> が返る
    Array.clone     # T: Data なら本物のコピー (O(n))

### その他の落とし穴

- `Nat.pred` は無い。`U32.shrn(U32.shln(1,d), 1n)` のように書く
- match は多スクルティニ可: `match x y:` / `case L{u} L{v}:`。全組み合わせを網羅する必要がある
- **U32 は黙ってオーバーフローする**。`2*K*i` が 2^32 を超えても型検査は通り、結果だけ変わる
- Nat 即値は 2^48 未満
- 数値型は Nat / U32 / F32 のみ。F64 も I64 も無い
- if-then-else は無い。Bool への match を使う

## 計測はしないこと

**このラウンドではタイミングを測らない。** 複数のベンチを同時に走らせると
互いに汚染される（同一バイナリで 6 倍のブレを実測した）。
最終的なタイミングは全員終了後に 1 人が静かなマシンで直列に取る。

## 検証要件（これは必ずやる。競合下でも判定できる）

1. Bend の **SEQ / PAR / GPU の 3 モードが出力ビット一致**すること
2. **C twin と出力が一致**すること
3. 可能ならアルゴリズム非依存の性質でも検証
   （ソートなら「昇順」かつ「入力の多重集合と一致」）
4. C twin は素直な単一スレッド C。わざと遅くしない。`cc -std=c11 -O3`

規模は「C 1 コアでおおよそ 1〜10 秒」に合わせる（正確でなくてよい）。

## チェックサムの作り方

出力は U32 1 個。位置重み付きで畳んで順序の違いが出るようにする:

    acc = U32.add(acc, U32.mul(v, U32.inc(U32.mul(i, 2654435761))))

定数畳み込みで消えないよう、入力は index のハッシュから作る:

    def hash(+i: U32) -> U32:
      U32.xor(U32.mul(U32.inc(i), 2654435761), U32.shrn(i, 3n))

## 参考にすべき既存コード

    upstream/bend/bench/runtime/bfs/main.bend           Array + 燃料ループ + St record の見本
    upstream/bend/bench/runtime/mandelbrot/main.bend    fork 木 + branchless の見本
    upstream/bend/bench/runtime/tree-bitonic/main.bend  バイトニックソートの見本
    examples/                     第1ラウンドの実験（全部動く）
    examples/ds/p3/               共有木への並列ランダムアクセス（動く）
