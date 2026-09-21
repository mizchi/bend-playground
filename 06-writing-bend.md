# Bend でどういうコードが書けるか（表現力の実測）

[05-gpu-algorithm-fit.md](05-gpu-algorithm-fit.md) は「どんなアルゴリズムが GPU に向くか」。
本稿はその一段手前、**「そのアルゴリズムをそもそも Bend で書けるか」**。

第2ラウンド（データ構造と経路探索）の記録。実験ソースは [examples/ds/](examples/ds/)、
共通コントラクトは [examples/ds/CONTRACT.md](examples/ds/CONTRACT.md)。

- Bend 2.0.23 / HEAD 75cb8f3e / Apple M5 (10 core) / Metal / clang 21
- 下の probe 9 本は全部 `bun bend2/main.ts <file> --check-only` で**再現確認済み**（2026-09-21）。
  エラー文言は実際の出力をそのまま貼っている
- **タイミングは載せない。** 計測前にマシンが 2 回 crash した（[bendlang/bend#942](https://github.com/bendlang/bend/issues/942)）。
  本稿の主張は全部コンパイル時に判定できるものだけに限ってある

---

## 結論を先に

**Bend の並列性はデータ構造では決まらない。問題を独立インスタンスに割れるかで決まる。**

[examples/ds/path/](examples/ds/path/) の p1 / p2 がその証拠になっている。
**同じ def、同じ 2^28 セル、違うのは grain だけ:**

| | 形 | 並列性 |
|---|---|---|
| `p1.bend` | 16384 × 16384 の迷路 **1 枚** | **逐次**。配列 3 本が affine なので pop は同時に 1 つしか飛べない |
| `p2.bend` | 32 × 32 の迷路 **2^18 枚** を fork 木の下に | **完全並列**。葉ごとに独立した迷路 |

同じ grain に揃えると両者は同じ数を出す（[path/check.sh](examples/ds/path/check.sh) の 1 番）。
つまり差はアルゴリズムでも実装でもなく、**問題の割り方だけ**。

p1 を `!` で GPU に投げると、1 レーンが 2^28 歩を 1 つの Metal dispatch の中で歩き、
command buffer が終わらず WindowServer が watchdog で落ちる。
p1 の冒頭コメントは「`!` を付けても何も変わらないことを示すため」と書いてあったが、
実際には**何も変わらないどころかマシンが落ちる**。

---

## 30 秒サマリ: 5 つの壁と 1 つの抜け道

```
  アフィン型 (値は高々 1 回)
        |
        +-- Array は Data ではなく Type       → 壁1  複製できない。fork から共有読みできない
        |        |
        |        +-- Data の木なら + が取れる  → 抜け道  + は refcount bump
        |                 |
        |                 +-- ただし書き込むと木が 2 本に割れる → 抜け道の限界
        |
  検査の一方向性 (linear bidirectional, 1 パス)
        |
        +-- 前方参照が見えない               → 壁2  相互再帰が書けない
        +-- scrutinee は引数かフィールドのみ  → 壁3  計算値を match できない
        +-- 自己呼び出しは構造的に減る必要    → 壁4  while が書けない (燃料を持つ)
        +-- let 束縛は match できない        → 壁5  fork の結果をその場で開けない
```

壁 2〜5 は全部「ヘルパ def を切って引数で渡す」に帰着するが、
壁2 があるのでヘルパは**使用箇所より前**にしか置けない。この 2 つが噛み合うと
コードは常に **bottom-up、かつ判定値は上から降ってくる**形に固定される。

---

## 壁1: Array は複製できない

これが第2ラウンド最大の発見。3 段階で閉じている。

**(1) `+` が付かない** — [probes/b_array_as_data.bend](examples/ds/path/probes/b_array_as_data.bend)

```bend
def probe(+a: Array<U32>) -> U32: ...
```
```
- expected : Data
- observed : Type
```

`+x: A` と書けるのは `A : Data` のときだけ。`base.bend:67` は
`type Array<-T: Type> is Type` なので、Array は永久に条件を満たさない。

**(2) 2 つの fork から読めない** — [probes/a_fork_shared_array.bend](examples/ds/path/probes/a_fork_shared_array.bend)

```bend
def probe(a: Array<U32>) -> U32:
  x y = peek(a, 0) peek(a, 1)
  U32.add(x, y)
```
```
- expected : a
- observed : a (consumed more than once)
```

**(3) record に包んでも逃げられない** — [probes/c_record_is_data.bend](examples/ds/path/probes/c_record_is_data.bend)

```bend
type St is Data:
  St{q: Array<U32>, d: Array<U32>, +head: U32, +tail: U32}
```
```
- expected : Data
- observed : Type
```

だから p1/p2 の状態は `type St is Type` で宣言してある。

> **帰結: 1 つの配列インスタンスに対するアルゴリズムは、Bend では必ず逐次になる。**
> frontier 並列 BFS、並列 in-place ソート、並列 union-find — 全部この壁の向こう側。
> `Array.fork` / `Array.join` は存在するが `@unsafe`（`base.bend:2285,2289`）なので数に入れない。

これは回避対象ではなく**発見**として扱う。配列 in-place が最良アルゴリズムである問題で
Bend が C に桁で負ける（05 の FWHT で 11x）のと、根が同じ。

### 逃げ道になりかけて、ならないもの

[probes/f_clone_fork_merge.bend](examples/ds/path/probes/f_clone_fork_merge.bend) は**通る**。
`Array.clone` (`-T: Data` が要る、O(n)) で 2 本に割ってから fork し、def で merge する。
検査は通るが会計が合わない: fork 前に N のコピー、fork 後に N の merge、計 2N を払って
探索 N/2 を浮かせる。しかも BFS では cell-wise merge が**正しくない**
（真の最短路を持たない側が見つけた距離は誤り）。

---

## 壁2: 前方参照が無い

[probes/d_forward_ref.bend](examples/ds/path/probes/d_forward_ref.bend)

```bend
def probe(x: U32) -> U32:
  later(x)

def later(x: U32) -> U32:
  U32.inc(x)
```
```
- expected : a defined name
- observed : later
```

相互再帰は書けない。ヘルパは使用箇所より前に定義する。
p1.bend の pop 経路が `look.push → look.seen → look.wall → look.open → look → look4
→ pop.done → pop.dist → pop.cell → pop` と**下から上に読む**順で並んでいるのはこのため。

---

## 壁3: 計算値を match できない

[probes/i_match_computed.bend](examples/ds/path/probes/i_match_computed.bend)

```bend
match U32.is_lt(i, s):
```
```
- message : a parameter or field scrutinee
            (a match cannot scrutinize a computed value: give it its own def)
```

let 束縛も同じく不可（"cannot scrutinize a local binder"）。
scrutinee になれるのは**引数かフィールドだけ**。

壁2 があるのでヘルパ def を切ると相互再帰になる。よって正解は
**判定を Bool の引数として呼び出し側から受け取り、多スクルティニ match で 1 つの def に畳む**:

```bend
def get(t: T, +i: U32, +s: U32, lt: Bool) -> U32:
  match t lt:
    case L{v} True{}:  v
    case L{v} False{}: v
    case N{a, b} True{}:
      +h = U32.shrn(s, 1n)
      get(a, i, h, U32.is_lt(i, h))      # 次の判定はここで計算して渡す
    case N{a, b} False{}:
      +j = U32.sub(i, s)
      +h = U32.shrn(s, 1n)
      get(b, j, h, U32.is_lt(j, h))
```

（[p3/gather.bend](examples/ds/p3/gather.bend) の `get`）
二分探索も BST 降下もソートの比較も、全部このイディオムに落ちる。
`if-then-else` は無い。Bool への match を使う。

---

## 壁4: while が書けない

[probes/e_while_loop.bend](examples/ds/path/probes/e_while_loop.bend)

```bend
def drain.go(+head: U32, +tail: U32, more: Bool) -> U32:
  match more:
    case True{}:
      drain.go(U32.inc(head), tail, U32.is_lt(U32.inc(head), tail))
```
```
- expected : a decreasing self-call (arguments are read left to right:
             each passed unchanged until one shrinks)
- observed : drain.go
```

「条件が成立するまでループ」は書けない。**燃料付き Nat** で上から抑える:

```bend
def bfs(f: Nat, r: St & Bool) -> St:
  match f:
    case 0n:
      (st, more) = r
      st
    case 1n+p:
      (st, more) = r
      match more:
        case False{}: st
        case True{}:  bfs(p, pop(st))
```

燃料は「絶対に足りる上界」を取る。p1 はセル数 2^28 を燃料にしている
（1 セルは高々 1 回しか push されないので、キューは燃料内で必ず枯れる）。
**終了条件はペアの右側に載せて運ぶ。**

---

## 壁5: fork の結果をその場で開けない

[probes/g_match_fork_result.bend](examples/ds/path/probes/g_match_fork_result.bend)

```bend
x y = half(St{d1}, 0) half(St{d2}, 1)
St{dx} = x
```
```
- message : a parameter or field scrutinee
            (a match cannot scrutinize a local binder: give it its own def)
```

壁3 の別の顔。fork の 2 つの結果を合流させるには、**両方を def に渡す**しかない。
merge が def になるということは、merge のコストが必ず関数呼び出し 1 回分以上になる。
05 の「combine が O(1) か O(size) か」が効くのはここ。

---

## 抜け道: Data の木は `+` を取れる

ここが第2ラウンドのもう一つの発見。**配列と木は対称ではない。**

[p3/nofork_array.bend](examples/ds/p3/nofork_array.bend) — これは通る:

```bend
def two(+t: T) -> U32:
  x y = sum(t) sum(t)
  U32.add(x, y)
```

`+` は深いコピーではなく**参照カウントの atomic increment**（`comp.ts:4065` の
`term_keep` → `rfc_bump`）。だから「1 本の木を多数の fork から同時に読む」は
**O(1) で**できる。

[p3/gather.bend](examples/ds/p3/gather.bend) はこれを使って、2^22 葉の共有木へ
2^24 回のランダム参照を fork 木から撃つ。対照として同形の C を 2 本（配列 / ポインタ木）置いてある。

> **帰結: read-only の共有構造が要るなら、Array ではなく Data の木で持つ。**
> 逆に言えば、Bend で「共有」と書けるのは木だけ。

### 抜け道の限界: 書くと木が割れる

[probes/h_tree_write_fork.bend](examples/ds/path/probes/h_tree_write_fork.bend) は通る。
1 本の木に 2 つの fork から `set` できる。ただし**それぞれ自分の木を返す**ので、
fork の後には距離マップが 2 本あって共有されたものが無い。
戻すには全走査の merge が要り、BFS では cell-wise の min が**そもそも正しくない**。

```
木は fork を買って sharing を失う。
配列は sharing を持っているが fork を買えない。
両方同時に持てる構造は Bend に無い。
```

これが「1 つのインスタンスに対する探索は逐次」の別表現。

---

## fork の作り方と GPU への投げ方

**fork になる唯一の形** — 「2 個以上の束縛が全部 call である let」:

```bend
a b = f(x) g(y)        # ← これが fork
U32.add(a, b)
```

`a b = f(x) 3` は fork にならない。分割統治は必ずこの形の自己再帰で書く:

```bend
def batch(+k: Nat, +i: U32) -> U32:
  match k:
    case 0n:
      maze(i)                                              # 葉: 独立インスタンス
    case 1n+p:
      a b = batch(p, i) batch(p, U32.add(i, U32.shln(1, p)))
      U32.add(a, b)
```

GPU へは `!` を付けて投げる。**main 側の呼び出しに 1 個付ければよい**:

```bend
def main() -> IO(Unit):
  IO.print(U32.show(batch!(kb(), 0)))
```

**`!` は「並列にしろ」ではなく「GPU に渡せ」。並列性が無い計算に付けると
1 レーンが全部を舐める。** p1 で実際にマシンが落ちた。
並列性が無い計算は `--gpu off` で走らせること。

---

## 数値と型の現実

- 数値型は **Nat / U32 / F32 のみ**。`I64` も `F64` も無い（`base.bend:28,54,57`）
- **U32 は黙ってオーバーフローする**。`2*K*i` が 2^32 を超えても型検査は通り、結果だけ変わる
- Nat 即値は 2^48 未満
- `Nat.pred` は無い。`U32.shrn(U32.shln(1, d), 1n)` のように書く
- `a[i]` は `(Array<T> & T)` を返す。**配列ごと返ってくる**ので、受け側は必ずペアを分解する
- `a[i] <- v` は `Array<T>` を返す
- `Array.new(-T: Data, +d: Nat, +v: T)` は 2^d 個。サイズは 2 冪固定
- match は多スクルティニ可（`match x y:` / `case L{u} L{v}:`）。**全組み合わせの網羅が要る**

---

## 判断表: この問題は Bend で書けるか

| 問題の形 | Bend | 根拠 |
|---|---|---|
| 独立インスタンスが多数（迷路 2^18 枚、Monte Carlo、mandelbrot） | **◎ 素直に並列** | fork 木の葉に 1 インスタンス |
| 分割統治で combine が O(1)（sum, max, checksum） | **◎** | 05 の H2 |
| read-only の共有構造に多数の参照（BST lookup, gather） | **○ Data の木で持つ** | `+` = refcount bump |
| 分割統治で combine が O(size)（merge sort, FWHT） | **△ 書けるが C に負ける** | 05 で FWHT 11x 負け |
| 1 つの配列に対する探索（BFS, union-find, in-place sort） | **× 逐次にしかならない** | 壁1 |
| 共有構造への並列書き込み | **×** | 抜け道の限界 |
| 収束するまでループ（Newton 法、不動点） | **△ 燃料で上界を置けるなら** | 壁4 |
| 相互再帰が本質的な構造（パーサ、相互帰納） | **× 書き換えが要る** | 壁2 |

---

## 書き始めのテンプレ

```bend
import Base
# 1. 型は上から。Array を持つ record は `is Type`
type St is Type:
  St{g: Array<U32>, q: Array<U32>, +head: U32, +tail: U32}

# 2. ヘルパは使用箇所より前。判定は Bool 引数で降ってくる
def step(st: St, +i: U32, lt: Bool) -> St: ...

# 3. ループは燃料付き Nat + ペアの右に終了フラグ
def loop(f: Nat, r: St & Bool) -> St: ...

# 4. 並列は「独立インスタンスの fork 木」。葉で 1 インスタンス
def batch(+k: Nat, +i: U32) -> U32: ...

# 5. GPU は main の呼び出しに ! を 1 個。並列性が無いなら付けない
def main() -> IO(Unit): ...
```

---

## 賭けは半分当たっている

[03-bend-wall.md](03-bend-wall.md) の賭けは「アフィン性が宇宙階層を置き換える」。
ただしこの**1 つの制約は 2 つの配当を同時に狙っています**。03 が採点したのは片方だけなので、
第2ラウンドで分かったもう片方をここに足す。

```
            アフィン性（関数値を複製できない）
                        |
        +---------------+---------------+
        |                               |
   証明側の配当                     実行側の配当
   自己適用が組めない               エイリアスが無い
   → Type:Type が通る              → GC 不要 / 破壊的更新が安全
   → 宇宙階層が要らない             → GPU に載る
```

**どちらも本物で、どちらも半分しか効いていません。**

### 証明側: 壁は立っているが、門が開いている

本物の部分 — Hurkens / Curry / omega が実測で落ちる（[03](03-bend-wall.md) の 4 節）。
`def` が 20 個積み上がった Hurkens が「変数を 2 回使った」の一点で崩れるのは説得力がある。

半分の部分 — `@unsafe` 3 行で任意の偽命題が通り、exit code は 0。`LAWS.bend` はアプリの
ビルド経路から import されない。`bend.lean` はより小さい別モデルに対する形式化で CI にも
入っていない。**防壁ではなく汚染追跡。**

### 実行側: 載る。だが載せる価値があるかは言ってくれない

本物の部分 — 汎用コードが本当に GPU で走る。nbody は C `-O3` の 36.7 倍。
これは型システムが GC を消した直接の結果で、他の依存型言語には無い。

半分の部分 — **型が保証するのは「エイリアスが無い」までで、「並列性がある」ではない。**
3 つ確かめた。

**(1) `!` は型に無い。** `bend2/bend.ts` が `!` を触るのは 2 箇所だけ。`bend.ts:2110` で
パースして呼び出し項の真偽フラグに入れ、`bend.ts:1396` で項を印字するときに戻す。それだけ。
`bangs` という語は `bend.ts` に 1 度も現れず、意味は全部 `comp.ts` 側にある
（`comp.ts:1495` で `fl.bangs` に集め、`comp.ts:3706` の `fid_bangs` という実行時フラグになる）。
**`!` は型付き effect ではなくコンパイラへの注釈。**

**(2) fork も型に無い。** `bend.ts` に `fork` という語が出るのはコメント 2 箇所だけで、
しかもその 1 つ（`bend.ts:127`）がこう書いている:

> a parallel let "x y z = a b c" is one Let binding n names to n values,
> each checked in the outer scope; **the compiler forks its calls.**

検査器にとって並列 let は**ただの Let** です。fork するかどうかはコンパイラの判断。

**(3) p1 と p2 は型で区別がつかない。** 同じ def 群、どちらも `U32` を返す素の関数。
片方は逐次で片方は完全並列なのに、型はまったく同じ。

決定的なのは (3) の帰結です。**p1 は型検査を通り、`!` が付いていて、GPU に投げたら
マシンが落ちた**（[#942](https://github.com/bendlang/bend/issues/942)）。
もし「GPU で動くことの証明」がそこにあるなら、`!` を付けた時点で検査が落ちるべきです。落ちない。

```
型が保証すること     : エイリアスが無い / 各値は高々 1 回 / 再帰は構造的に減る
GPU が必要とすること : それ + 十分な独立並列性
                                ~~~~~~~~~~~~~~ ← 型に現れない
```

その差額が crash です。

### だから

> Bend は「GPU で動くことを証明させる言語」ではない。
> **「エイリアスが無いことを構文で強制したら、副産物として GPU に載った」言語**。
> 証明されているのはメモリの性質であって、実行の性質ではない。

実務的にはこう読むのが安全です。
**型検査が通ったら「壊れない」は言える。「速い」も「並列になる」も一切言えない。**

前節の判断表は、型が教えてくれないその部分を人間が先に判定するための表です。
壁 1〜5 はコンパイラが教えてくれる（落ちるので必ず分かる）。
**並列性があるかどうかだけは、誰も教えてくれない。**

---

## 今回やらなかったこと

- **タイミング未計測。** ds/ 配下の 4 実験（path / sort / map / p3）は正しさの検証
  （SEQ / PAR / GPU の 3 モード一致 + C twin 一致 + アルゴリズム非依存な性質）まで。
  速度は [bendlang/bend#942](https://github.com/bendlang/bend/issues/942) が片付いてから
  静かなマシンで直列に取る
- 木への並列書き込みが「正しい」問題（min-plus のような可換冪等な合流）での評価。
  BFS では正しくないことしか確かめていない
- `@unsafe` な `Array.fork` / `Array.join` を使った場合にどこまで書けるか
