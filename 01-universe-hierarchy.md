# 宇宙階層 (universe hierarchy) とは何か

型理論を知らない人向け。結論から言うと、**「型にも型がある」ことにした瞬間に無限後退が起きるので、型理論は番号を振って逃げている**。その番号の管理が宇宙階層で、これが証明支援系のチェッカを重くしている原因のひとつ。

---

## 1. 型にも型がある

普通のプログラミング言語では、値には型がある。

```
  42        : Int
  "hello"   : String
  [1,2,3]   : List<Int>
```

依存型の言語では、**型そのものが値として扱える**。関数が型を受け取ったり返したりする。

```python
# Bend
def pick(-A: Type, c: Bool, a: A, b: A) -> A:   # A は「型」という引数
  ...
```

型を引数に取れるということは、型にも型がなければならない。その型が `Type` です。

```
  42 : Int : Type
       ^^^   ^^^^
       値の型  型の型
```

ここで当然の疑問が出る。**`Type` の型は何か？**

---

## 2. 素朴な答え `Type : Type` は壊れる

一番簡単な答えは「`Type` の型は `Type` 自身」。

```
  42 : Int : Type : Type : Type : ...   (ずっと自分自身)
```

これは **Girard のパラドックス**で壊れます。Russell の「自分自身を含まない集合の集合」を型理論に翻訳したもの。

直感的な説明:

```
  Type : Type があると、「すべての型の型」を Type 自身の中で作れる
                    ↓
  「自分自身に適用できる関数」が型付けできるようになる
                    ↓
  omega = λx. (x x)   ← 引数に自分自身を適用する
                    ↓
  omega(omega) が型付く = 無限ループが型付く
                    ↓
  「任意の命題 P の証明」を無限ループとして書ける
                    ↓
  False が証明できる = 論理体系として崩壊
```

証明支援系にとってこれは死です。「証明がある」＝「その型の値が作れる」なので、無限ループが値として通ってしまうと、何でも証明できてしまう。

Hurkens のパラドックスはこれを最小化したもので、Bend のリポジトリに実物があります (`tests/check/hurkens_paradox.bend`)。

---

## 3. 標準的な解決: 番号を振る

Lean / Agda / Rocq / Coq が全部やっているのがこれ。`Type` を 1 個ではなく**無限段の梯子**にする。

```
                                          ┌─────────────┐
                                          │   Type 2    │
                                          └──────┬──────┘
                                                 │ : (「の型は」)
                                 ┌───────────────┴─┐
                                 │     Type 1      │
                                 └────────┬────────┘
                                          │ :
                        ┌─────────────────┴──┐
                        │      Type 0        │
                        └─────────┬──────────┘
                                  │ :
        ┌──────────┬──────────────┼──────────────┬──────────┐
        │          │              │              │          │
      Int       String      List<Int>        Bool      Int -> Int
        │          │              │              │          │
        │ :        │ :            │ :            │ :        │ :
       42      "hello"        [1,2,3]          True     (\x -> x+1)
```

ルール: **`Type n : Type (n+1)`**。自分自身の型にはならないので、輪が閉じない。輪が閉じないから omega が作れない。

```
  ✗ Type : Type        ← 輪になる。壊れる
  ✓ Type0 : Type1      ← 梯子。上に無限に伸びるが、決して戻ってこない
```

### 正値性検査 (positivity check) も同じ目的

もうひとつ、同じ穴を塞ぐための検査があります。次のようなデータ型を禁じるもの。

```
  type Neg:
    Wrap{ f: Neg -> Empty }     ← 自分自身が「関数の引数側」に出ている
          ~~~~~~~~~~~~~~~
```

これを許すと、宇宙階層があっても omega が作れてしまう。

```
  def app(x: Neg) -> Empty:
    match x:
      case Wrap{f}: f(x)        ← x を 2 回使っている (match の対象として + f の引数として)

  app(Wrap{app})  →  app(Wrap{app})  →  ...  無限ループ = Empty の証明
```

だから Lean/Agda/Rocq は「再帰型の自己言及は引数側 (negative position) に出てはいけない」という**正値性検査**を持っています。

---

## 4. 番号を振ることのコスト

ここが Bend の話に繋がるところ。宇宙階層はタダではない。

### (a) レベルを書かされる / 推論させられる

素直にやると全部の定義にレベル番号を書く羽目になる。

```
  def id (A : Type 0) (x : A) : A := x     -- Type 0 でしか使えない
  def id (A : Type 1) (x : A) : A := x     -- Type 1 用にもう一個？
```

これは現実的でないので、**universe polymorphism**（レベルを変数にする）が導入される。

```
  def id.{u} (A : Type u) (x : A) : A := x
```

### (b) レベル制約を解く必要がある

universe polymorphism を入れると、型検査の一部が**制約解決問題**になります。

```
  この定義は  u ≤ v,  max(u,w) < v,  v ≠ 0  を満たす u,v,w があれば通る
                    ↓
  チェッカは毎回この不等式系を解かないといけない
```

Lean の `universe unification`、Agda の `universe level solver` がこれ。ここがエラーになると "universe level mismatch" みたいな、初心者殺しのエラーが出る。

### (c) 正値性検査も全データ型を走査する

再帰型が定義されるたびに、自己言及が negative position に出ていないかを構造全体で調べる。

**まとめると、宇宙階層を持つ言語のチェッカは、型検査に加えて「レベル制約ソルバ」と「正値性チェッカ」を回している。** Bend はこれを両方持っていません。それが「速い」理由の一部であり、同時に「同じ仕事をしていない」という批判の根拠でもあります。

---

## 5. Bend はどうしたか

Bend は `Type : Type` を**許します**。正値性検査も**しません**。負の再帰型も書けます。

```
// bend2/bend.ts:166 のコメント (原文)
// this wall permits Type : Type, impredicativity and negative recursive
// types with no universe hierarchy and no positivity check: omega, Curry
// and Hurkens each contract a live function-valued binding, and no
// function type is Data. the gate is the wall.
```

代わりに置いたのが**アフィン型の壁**。次のドキュメントへ → [02-affine-types.md](02-affine-types.md)

### 実際に確認した挙動

`Type : Type` は成立している (`bend2/bend.ts:3412-3420`)。それでも Hurkens は通らない:

```
$ bun bend2/main.ts tests/check/hurkens_paradox.bend
Error:
- expected : f
- observed : f (consumed more than once)
Location: tauinner
44>| def tauinner(): x => f => p => w => y => p(f(y(x)(f)))
```

「宇宙のレベルが合わない」ではなく「**f を 2 回使った**」で落ちている。ここが Bend の全部です。
