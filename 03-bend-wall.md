# Bend の賭け: アフィン性が宇宙階層を置き換える

[01](01-universe-hierarchy.md) と [02](02-affine-types.md) が繋がるところ。Bend の理論的な新規性はここ 1 点に尽きます。

---

## 1. パラドックスは全部「関数を 2 回使う」

[01](01-universe-hierarchy.md) で見た omega を、もう一度よく見る。

```
  omega = λx. (x x)
                ^ ^
                │ └── x を「引数」として使う
                └──── x を「関数」として使う     ← x を 2 回使っている
```

Curry のパラドックス、Hurkens のパラドックス、負の再帰型による Y コンビネータ。**全部これです。** 自己適用には必ず「同じ変数を 2 回使う」瞬間がある。

```
  ┌──────────────────────────────────────────────────────────┐
  │  パラドックスの共通構造                                    │
  │                                                           │
  │    関数値 f  ──┬──> f 自身を呼ぶ                          │
  │                └──> f 自身に渡す      ← ここで 2 回使う   │
  │                                                           │
  │  この「複製」ができなければ、パラドックスは組み立たない     │
  └──────────────────────────────────────────────────────────┘
```

---

## 2. 2 通りの塞ぎ方

```
      ┌─────────────────────────────┐
      │  自己適用を型付けさせない     │
      └──────────────┬──────────────┘
                     │
        ┌────────────┴────────────┐
        │                         │
  【従来のやり方】            【Bend のやり方】
        │                         │
  型に番号を振る              値の使用回数を数える
  (宇宙階層)                  (アフィン型)
        │                         │
  「x : Type n を                「x を 2 回使った」
   Type n 内で使えない」          で落とす
        │                         │
  + 正値性検査で                関数型は Data に
    negative position を禁止      ならないので +x 不可
        │                         │
  Lean / Agda / Rocq          Bend 2
```

Bend 側の主張は「**宇宙階層も正値性検査も要らない。使用回数さえ数えれば同じ穴が塞がる**」。

`bend2/bend.ts:166` の原文がこれを一文で言っている:

> this wall permits `Type : Type`, impredicativity and negative recursive types
> with no universe hierarchy and no positivity check: omega, Curry and Hurkens
> each contract a live function-valued binding, and no function type is Data.
> **the gate is the wall.**

---

## 3. なぜこれで足りるのか

論証は 2 段です。

```
  ステップ 1:  パラドックスは必ず「live な関数値の複製」を要求する
               (omega / Curry / Hurkens を実際に調べた結果)

  ステップ 2:  Bend では live な関数値は複製できない
               ┌ +x: A と書けるのは A : Data のときだけ
               └ 関数型は絶対に Data にならない
                     ↓
               パラドックスは型付かない
```

ループを作る道はもうひとつある（**再帰**）ので、そちらも塞ぐ:

```
  停止性検査 (structural descent, bend.ts:893-931)

    自己呼び出しの引数を、定義自身の case-tree の列と左から比較する
    最初に「真に小さくなった」列が見つかれば合格

        def sum(n: Nat) -> Nat:
          match n:
            case 0n:    0
            case 1n+p:  Nat.add(p, sum(p))
                                   ^^^ p < n  → OK

        def loop(n: Nat) -> Empty:
          loop(n)              ^^^ n = n  → 拒否
```

実測:
```
$ bun bend2/main.ts loop.bend --check-only
Error:
- expected : a decreasing self-call (arguments are read left to right:
             each passed unchanged until one shrinks)
- observed : bad
```

これで「無限ループを証明として使う」道が両方塞がる。

---

## 4. 実測: 本当に落ちるのか

### Hurkens のパラドックス

`tests/check/hurkens_paradox.bend` を実行:

```
$ bun bend2/main.ts tests/check/hurkens_paradox.bend
Error:
- expected : f
- observed : f (consumed more than once)
Context:
- x : Type
Location: tauinner
44>| def tauinner(): x => f => p => w => y => p(f(y(x)(f)))
                                              ~~~~~~~~~~~~
                                              f が 2 回出ている
```

**宇宙のレベル違反ではなく、使用回数違反で落ちている。** 設計通り。

### 負の再帰型

```bend
type Neg is Data:
  Wrap{f: Neg -> Empty}      # 型定義自体は通る (正値性検査がないので)

def app(x: Neg) -> Empty:
  match x:
    case Wrap{f}: f(x)       # ← ここで落ちる
```

型定義は通る。使おうとした瞬間に `f (consumed more than once)` で落ちる。

### 偽の法

```bend
law add_one:
  for x: Nat
  {Nat.add(x, 1n) == x : Nat}    # 偽

def add_one(x):
  match x:
    case 0n:   {==}
    case 1n+xp:
      %add_one(xp) : {1n+Nat.add(xp, 1n) == 1n+_ : Nat}
      {==}
```
```
Error:
- expected : 1n
- observed : 0n
```

---

## 5. Lean 形式化は何を証明しているのか

`bend2/bend.lean` は 20,981 行、`import` 行ゼロ (Mathlib 非依存)、`sorry` 0 件。**実際にコンパイルを通すのを確認しました**:

```
$ lean bend2/bend.lean
'BendCore.church_rosser_holds'    depends on axioms: [propext, Classical.choice, Quot.sound]
'BendCore.subject_reduction_holds' depends on axioms: [propext, Classical.choice, Quot.sound]
'BendCore.progress_holds'         depends on axioms: [propext, Classical.choice, Quot.sound]
'BendCore.normalization_holds'    depends on axioms: [propext, Classical.choice, Quot.sound]
'BendCore.consistency_holds'      depends on axioms: [propext, Classical.choice, Quot.sound]
lean bend2/bend.lean  38.21s user  15.3s total
```

依存公理は Lean 標準の 3 つだけ。追加公理も抜け穴もない。5 つの定理は本物です。

### ただし、何に対する証明かが重要

```
  ┌──────────────────────────────────────────────────────────────┐
  │                                                               │
  │   bend.lean の BendCore     ←─ ここが証明されている           │
  │   (宣言的な inductive Prop のモデル)                          │
  │                                                               │
  │              ↕  この対応が 未 証 明                            │
  │                                                               │
  │   bend.ts の実際のチェッカ  ←─ ここが実際に走っている         │
  │                                                               │
  └──────────────────────────────────────────────────────────────┘
```

具体的なギャップ:

| 項目 | 状態 |
|---|---|
| `Check` の形 | `inductive ... Prop` の**宣言的関係**。実行可能なチェッカではない。決定可能性の証明も抽出もない |
| モデルの範囲 | Lean の `Term` に `Lit` / `Ann` / `Hol` / `Sub` が**ない**。`Lit` は `term_wnf` / `term_compare` / `term_descend` 全部に特殊ケースを持つ信頼カーネルの一部で、そこが完全に未モデル |
| template (`~`) | 未モデル。実装では呼び出しごとに本体を再検査する単相化 (64 段のハードリミット付き) |
| `@unsafe` | `Book.Ok` が**拒否**する。つまりモデルの外 |
| 出荷される `base.bend` | 本体なし law が 52 件あるので `Book.Ok` を満たさない |
| CI | `.github/workflows/` が存在しない。`gates/` の 4 ゲートにも Lean は入っていない。**この 21k 行はリポジトリのどの自動検査でもコンパイルされていない** |

`bend.lean` の冒頭が自分でこう書いている:

> Even though we've reviewed the spec carefully, it doesn't fully match the
> implementation (bend.ts) yet. Bugs in the implementation COULD result in
> inconsistencies.

---

## 6. 実際に見つかった穴

### (a) `@unsafe` で任意の偽命題が通る

```bend
@unsafe
def loop(-A: Type) -> A:
  loop(A)                          # 停止性検査をスキップ

law anything:
  for x: Nat
  {Nat.add(x, 1n) == x : Nat}      # 偽

def anything(x):
  loop({Nat.add(x, 1n) == x : Nat})
```
```
$ bun bend2/main.ts absurd.bend --check-only
All terms check, but 2 defs rely on unsafe or foreign code:
- loop
- anything
$ echo $?
0                                   ← exit code 0
```

`@unsafe` は「停止性検査をスキップ」するだけに見えて、**ex falso quodlibet の穴**そのもの。しかも exit code が 0 なので、CI を exit code で組んでも捕まらない。

**擁護:** 汚染は推移的に伝播する。安全な def が unsafe な def を呼べば、それも一覧に載る（上の例で `anything` も出ているのがそれ）。設計としては「防壁」ではなく「**汚染追跡**」で、これ自体は筋が通っている。足りないのは exit code と `--deny-unsafe` フラグだけ。

### (b) 変換検査が発散する (`@unsafe` なし)

```bend
def T(n: Nat) -> Type:
  {T(n) == T(n) : Type}        # 3 つの端点すべて dead 位置

def p(n: Nat) -> {T(n) == T(n) : Type}:
  {==}
```
```
Error: the machine stack overflowed (a deep recursion, or a literal too large to expand)
```

停止性検査は live な自己呼び出しにしか掛からない (`bend.ts:3394`)。dead 位置には降下義務がないので、型レベルの計算が無限に展開されうる。番人は JS のスタックオーバーフロー捕捉 (`main.ts:636`) だけ。

これは**クラッシュであって不健全性ではない**（偽を通すわけではない）ので、`@unsafe` の穴より軽い。ただし「one pass で必ず止まる」という主張への反例ではあります。

### (c) base.bend の公理 52 件

本体のない `law` は公理として扱われます。

| 種類 | 件数 | 例 |
|---|---|---|
| F32 演算 | 33 | `F32.add`, `F32.mul`, ... (`base.bend:1541-1698`) |
| Array atomics | 9 | `Array.atomic.add`, ... (`base.bend:2293-2350`) |
| 抽象型 | 10 | `File`, `Socket`, `Window`, `Audio`, `Chan`, `IO`, `Word` |

**F32 が公理 = 浮動小数点について何も証明できない。** 3D デモの描画も物理も全部証明の外。デモ自身が `app_ray_tracer_3d/LAWS.bend:2` で「The F32 scene is not claimed」と自白しています。

救いは、これらの戻り値が `F32` / `U32` / `Bool` / `Array` であって、等式や `Empty` を産まないこと。つまり公理から直接 False は出ない。

---

## 7. 評価

**理論として:** 本物で、しかも新しい。「宇宙階層をアフィン性で置き換える」は僕の知る限り前例がない。Hurkens が実測で落ちるのは説得力がある。

**形式化として:** Lean 21k 行 / `sorry` ゼロ / 標準公理のみは立派。ただし**より小さい別モデル**に対する証明で、動いているチェッカとの対応は未証明。CI にも入っていない。README の「the Lean formalization and bend.ts mismatch」は**控えめすぎる**表現。

**運用として:** `@unsafe` 1 行で全部崩れて exit 0 を返す。「mathematically impossible to break laws」はこの穴が閉じるまで成立しない。しかも `LAWS.bend` は `main.bend` から import されないので、アプリのビルド経路は法を一度も見ない（ゲームデモの壁を壊して確認済み: アプリは普通に動き、`bend PROOF.bend` だけが落ちる）。
