# Bend という言語の紹介

Bend という言語を初めて触った日に、ベンチマークを走らせたらマシンが 2 回落ちました。落ちた理由まで含めて面白かったので、初見の感想として、名前も聞いたことがない人向けに書きます。

以下のコードは全部 Bend 2.0.23 (HEAD `75cb8f3e`) で型検査と実行を確認したものです。

## Bend とは

依存型があって、GPU で走る言語です。

依存型の言語は Coq や Agda や Lean があって、GPU で走る言語は CUDA や Metal がありますが、両方を持っている言語というのはあまり聞きません。

Bend はそれを**アフィン型という 1 つの制約**でやろうとしています。

## 動かす

このリポジトリには検証時の Bend を submodule として固定しています。Git、Bun、just を用意して取得します。

```bash
git clone https://github.com/mizchi/bend-playground.git
cd bend-playground
just setup
```

hello world はこれです。

```bend
import Base

def main() -> IO(Unit):
  IO.print("hello")
```

`hello.bend` に置いて叩きます。依存のインストールは要りません。

```bash
just bend hello.bend
```

```
hello
```

`--check-only` を付けると、型検査だけして実行せずに終わります。

## 値は高々 1 回

Bend の型システムは**アフィン**です。値は 1 回までしか使えません。

なので、これは通りません。

```bend
def double(x: U32) -> U32:
  U32.add(x, x)
```

```
Error:
- expected : x
- observed : x (consumed more than once)
```

`x` を 2 回使っているからです。

複製したいときは、仮引数に `+` を付けます。

```bend
def double(+x: U32) -> U32:
  U32.add(x, x)

def main() -> IO(Unit):
  IO.print(U32.show(double(21)))
```

```
42
```

Rust の所有権を知っていれば馴染みのある話で、実際 Rust のムーブとほぼ同じ感覚で書けます。

## `Type : Type`

普通の依存型言語には宇宙階層があります。

```
Nat : Type0 : Type1 : Type2 : ...
```

なぜ階層が要るかというと、`Type : Type` を許すと**任意の偽命題が証明できてしまう**からです。これは Girard のパラドックスとして知られていて、集合論の Russell のパラドックスと同じ形をしています。

階層は安全ですが、高くつきます。同じ定義を宇宙ごとに書き直す羽目になり、universe polymorphism という機能が要り、その制約解決が要ります。

**Bend には階層がありません。** `Type : Type` がそのまま通ります。

それでもパラドックスは通りません。

## パラドックスの正体

パラドックスは必ず「自分を自分に食わせる」形をしています。

```
omega = λx. (x x)
              ^ ^
              │ └── x を「引数」として使う
              └──── x を「関数」として使う
```

`x x` は **x を 2 回使っています**。

嘘つきのパラドックスも、Russell の集合も、Y コンビネータも、Curry のパラドックスも全部ここに帰着します。自己適用には、必ず同じ変数を 2 回使う瞬間があるからです。

アフィン型はその複製を禁じているので、パラドックスがそもそも組み立ちません。

リポジトリには本物の Hurkens のパラドックスが入っていて (`tests/check/hurkens_paradox.bend`)、`def` が 20 個積み上がっています。それが落ちるのは 1 行だけです。

```bend
def tauinner(): x => f => p => w => y => p(f(y(x)(f)))
```

```
Error:
- expected : f
- observed : f (consumed more than once)
```

`f` を関数として呼びながら、同時に引数としても渡しているからです。20 個の定義を積み上げた攻撃が、変数を 2 回使ったという一点だけで崩れます。

自分はここが Bend で一番おもしろいところだと思っています。宇宙階層という重い装置を、メモリの規律 1 個で置き換えているわけです。

## 証明

証明も書けます。等式は `{a == b : T}` で `{==}` が反射律、`law` が定理の文で `def` がその証明です。

```bend
law two:
  {Nat.add(1n, 1n) == 2n : Nat}

def two(): {==}
```

帰納法も書けます。

```bend
type N is Data:
  Z{}
  S{p: N}

law add:
  for a: N
  for b: N
  N

def add(a, b):
  match a:
    case Z{}:
      b
    case S{p}:
      S{add(p, b)}

law add_zero:
  for a: N
  {add(a, Z{}) == a : N}

def add_zero(a):
  match a:
    case Z{}:
      {==}
    case S{p}:
      %add_zero(p) : {S{add(p, Z{})} == S{_} : N}
      {==}
```

`%` が書き換えで、再帰呼び出し `add_zero(p)` がそのまま帰納法の仮定になります。

検査は速いです。insertion sort の完全正当性証明 (整列性と置換の両方) が bun の起動込みで 0.058 秒でした。

## 木と配列の非対称

`+` が付けられるのは `Data` 型だけです (`U32` も `Nat` も `Data` なので、さっきの `+x: U32` はこれです)。そして **`Array` は `Data` ではありません** (`base.bend:67` で `type Array<-T: Type> is Type`)。

なので配列は複製できません。

```bend
def twice(+a: Array<U32>) -> U32:
  7
```

```
Error:
- expected : Data
- observed : Type
```

一方、自分で定義した `Data` の木は複製できます。

```bend
type T is Data:
  L{v: U32}
  N{a: T, b: T}

def sum(t: T) -> U32:
  match t:
    case L{v}:
      v
    case N{a, b}:
      x y = sum(a) sum(b)
      U32.add(x, y)

def twice(+t: T) -> U32:
  x y = sum(t) sum(t)
  U32.add(x, y)

def main() -> IO(Unit):
  IO.print(U32.show(twice(N{L{3}, L{4}})))
```

```
14
```

`+` は深いコピーではなく参照カウントの atomic increment なので (`comp.ts:4065`)、これは O(1) です。

つまり、**1 本の木なら多数の並列タスクから同時に読めるのに、1 本の配列ではそれができません。**

これが効くのは、配列に対するアルゴリズムが単一インスタンスの中では必ず逐次になるからです。frontier 並列の BFS も、並列 in-place ソートも、並列 union-find も、この壁の向こう側にあります。

読み取り専用の共有構造が要るなら `Array` ではなく `Data` の木で持つ、というのが、実際に書いてみて一番実用的だった結論です。

## 並列の書き方

並列化の構文は 1 つだけです。「2 個以上の束縛が全部 call である let」が fork になります。

```bend
a b = sum(x) sum(y)
U32.add(a, b)
```

`a b = sum(x) 3` は fork になりません。右側が全部呼び出しである必要があります。

なので分割統治は、この形の自己再帰で書きます。

```bend
def tree(+d: Nat, +i: U32) -> U32:
  match d:
    case 0n:
      i
    case 1n+p:
      a b = tree(p, i) tree(p, U32.add(i, U32.shln(1, p)))
      U32.add(a, b)
```

スレッド数も、分割の粒度も、同期も書きません。書くのは木の形だけです。

## GPU に投げる

`!` を付けます。

```bend
def main() -> IO(Unit):
  IO.print(U32.show(tree!(20n, 0)))
```

これだけです。カーネルも、バッファ確保も、転送も書きません。

`bend main.bend -o main` でネイティブにすると、clang で C を、同じソースから Metal (または CUDA) を吐きます。実行時のモードは引数で選びます。

```bash
./main                        # GPU
./main --gpu off              # CPU 全コア
./main --threads 1 --gpu off  # CPU 1 コア
```

同じバイナリで 3 モードを選べるので対照実験がやりやすく、自分はこの設計がかなり好きです。

## 書けないもの

正直に書くと、ここでだいぶ詰まりました。

**while が書けません。** 自己呼び出しは引数が構造的に減る必要があります。

```bend
def go(+i: U32, +n: U32, more: Bool) -> U32:
  match more:
    case False{}:
      i
    case True{}:
      go(U32.inc(i), n, U32.is_lt(U32.inc(i), n))
```

```
Error:
- expected : a decreasing self-call
- observed : go
```

代わりに燃料付きの `Nat` を渡します。

```bend
def go(f: Nat, +acc: U32) -> U32:
  match f:
    case 0n:
      acc
    case 1n+p:
      go(p, U32.inc(acc))

def main() -> IO(Unit):
  IO.print(U32.show(go(10n, 0)))
```

```
10
```

「絶対に足りる上界」を燃料に取って、本当の終了条件はペアの右側に載せて運ぶ形になります。

**計算した値を `match` できません。** scrutinee になれるのは引数かフィールドだけです。

```bend
def sign(+i: U32, +s: U32) -> U32:
  match U32.is_lt(i, s):
```

```
Error:
- message : a parameter or field scrutinee
            (a match cannot scrutinize a computed value: give it its own def)
```

判定を `Bool` の引数として呼び出し側から受け取る形に書き換えます。二分探索も BST の降下もソートの比較も、全部この書き換えに当たります。

**相互再帰と前方参照もありません。** ヘルパは使用箇所より前に定義する必要があるので、コードは常に下から上に読む形になります。

この 3 つは慣れの問題ではなくて、検査が 1 パスで停止性まで見ていることの裏返しです。書きにくさには理由がある、とは思います。

## 速さ

で、実際どれくらい速いのか。

手元 (Apple M5 / 10 core / Metal) での実測です。

1 コア同士だと nbody で C の `-O3` が 4.67 秒、Bend が 5.26 秒でした。**1.13 倍遅いだけ**です。

同じ nbody を GPU に投げると 0.127 秒で、さっきの C 1 コア (4.67 秒) の 36.7 倍です。

ただし全部が速いわけではありません。lexer は GPU で C に負けます (0.96 倍)。起動の固定コストが 90ms ほどあるので、1 コアで 1 秒以上かかる計算でないと元が取れません。

配列を in-place で書ける問題になると C に桁で負けていて、FWHT では 11 倍の差がつきました。

GPU 実行を可能にしているアフィン型が、そのまま最良のアルゴリズムを禁止しているわけで、ここはトレードオフとして受け入れるしかないところだと思っています。

## マシンが 2 回落ちた話

ベンチを走らせていたら macOS ごと落ちました。2 回。

crash ダンプを読んだら、Bend の GPU バイナリが 3 本とも `[MTLCommandBuffer waitUntilCompleted]` の中で止まっていて、WindowServer が 40 秒の watchdog に殺されていました。

原因は**並列性のないプログラムを `!` で GPU に投げたこと**です。16384 × 16384 の迷路 1 枚を逐次 BFS で歩くプログラムだったので、GPU の 1 レーンが 2 億 6800 万歩を 1 つの dispatch の中で歩き続けて、command buffer がいつまでも終わらなくなりました。

そして **`!` は型に現れません。**

`bend.ts` (言語・理論・検査器の本体) が `!` を触るのはパースと印字の 2 箇所だけで、意味は全部コンパイラ側にあります。並列 let も同じで、検査器のソースコメント自身がこう書いています。

```
a parallel let "x y z = a b c" is one Let binding n names to n values,
each checked in the outer scope; the compiler forks its calls.
```

検査器にとって並列 let はただの Let です。

つまり **型検査は「並列になる」とは一言も言っていません**。証明されているのはエイリアスが無いことであって、実行の性質ではありません。

自分の結論としては、型が通ったら「壊れない」は言えますが、「速い」も「並列になる」も一切言えない、というところです。

Issue には出しました ([bendlang/bend#942](https://github.com/bendlang/bend/issues/942))。`waitUntilCompleted` に期限がないので、ディスプレイの繋がった Mac では失敗する代わりにマシンが落ちる、という報告です。

## 見つけた穴

`@unsafe` を使うと 3 行で任意の偽命題が通って、exit code は 0 です。

```bend
@unsafe
def loop(-A: Type) -> A: loop(A)

def anything(x): loop({Nat.add(x, 1n) == x : Nat})
```

救いは汚染が推移的に伝播して `N defs rely on unsafe or foreign code` と一覧されることで、防壁というより汚染追跡です。

`F32` の演算は 33 件が公理なので、浮動小数点については何も証明できません。3D デモの描画も物理も証明の外にあります。

Lean による形式化は 21k 行あって `sorry` が 0 件という立派なものですが、動いているチェッカより**小さい別のモデル**に対する証明で、CI にも入っていません。

## 現在地

ランタイムと型理論は本物だと思っています。1 コアで C と並ぶのも、`Type : Type` が通るのも、実測して確かめました。

一方で証明支援の看板が一番脆い、というのが初見の印象です。README の Limitations 節は異様に正直で、前半と後半で書いている人が違うように読めます。

次は `#942` が片付いてから、ソート・マップ・経路探索の 4 実験のタイミングを静かなマシンで取り直すつもりです。木への並列書き込みが正しくなる問題 (min-plus のような可換冪等な合流) なら配列の壁を回避できるはずなので、そこも確かめたいと思っています。

言語仕様のほうは `bend2/bend.ts` 1 本を読めば全部載っています。人間が手で書いていて、パーサから型検査まで 1 ファイルなので、処理系を読むのが好きな人にはかなり良い教材だと思います。
