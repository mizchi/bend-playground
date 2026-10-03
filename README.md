# bend-playground

Bend 2 の理解ノートと実験コード。Bend 本体の checkout に置いていた `.mizchi` を独立させたリポジトリです。

上流へのリファレンス実装: [既知callbackのコンパイラ最適化とmain／forkの比較](compiler-patches/step-02-known-callbacks/refactored/README.md)。固定コミットからCPU/Metalの検証・計測を再現できます。[English instructions](compiler-patches/step-02-known-callbacks/refactored/README.en.md)も用意しています。

## セットアップ

必要なもの: Git、Bun、just、Python 3。ネイティブ実験には C コンパイラも必要です。
GPU の実測環境は Apple M5 / Metal です。

```sh
git clone https://github.com/mizchi/bend-playground.git
cd bend-playground
just setup
just test
```

Bend 本体は `upstream/bend` の Git submodule で管理し、
Bend 2.0.34 のコミット `7d24b8d0235cb9781140512c0f163c48ea84a719` に固定しています
（01〜07 の計測は 2.0.23 / `75cb8f3e041aeaad2b37e726c0a33ba19dc49df8` で行ったもの）。
元の Bend checkout は不要です。`just setup` は記録されたコミットを取得します。

```sh
just bend examples/intro/s01_hello.bend
just bend examples/intro/s01_hello.bend --check-only
just check-intro

# ネイティブバイナリを生成する
mkdir -p build
just bend examples/mc.bend -o build/mc
./build/mc --threads 1 --gpu off
```

`./scripts/bend.sh` は作業ディレクトリを変えずに Bend を起動します。
別バージョンとの比較時は `BEND_REPO=/path/to/bend ./scripts/bend.sh ...` で上書きできます。
利用できるタスクは `just`、実験ごとの説明は [examples/README.md](examples/README.md) を参照してください。

`just test` は別ディレクトリ・空白を含むパスからの実行、引数の受け渡し、紹介記事の13サンプル
（意図した型エラー4本を含む）、FWHT の involution、`@unsafe` な偽の証明が検査に落ちること、
物理・モンテカルロの7本が C twin とビット一致すること、
N-Queens・素因数分解・AST 変換・DPLL SAT が C の逐次・並列版と独立オラクルに一致すること、
C FFI とその比較用ループが同じ結果になること、CSS Grid サブセットの配置・サイズ・容量エラーを検証します
（C コンパイラが必要、GPU は不要）。
生成バイナリや作業ファイルは Git 管理から除外しています。

01〜07 のノート・計測値は 2.0.23 を対象にした当時の記録です。08 は 2.0.34 で計測しています。
01〜06 に現れる `bend2/`、`bench/`、`tests/` などの upstream のパスやコマンドは、
`upstream/bend/` を基準に読んでください。

## 目次

| ファイル | 内容 |
|---|---|
| [01-universe-hierarchy.md](01-universe-hierarchy.md) | 宇宙階層とは何か。なぜ必要で、なぜ高くつくか |
| [02-affine-types.md](02-affine-types.md) | アフィン型とは何か。線形型・Rust との関係 |
| [03-bend-wall.md](03-bend-wall.md) | Bend の賭け: アフィン性が宇宙階層を置き換える |
| [04-gpu-execution.md](04-gpu-execution.md) | GPU 実行の制約とメリット、表現力、readback 実測 |
| [PERFORMANCE.md](PERFORMANCE.md) | FFI・CPU/GPU 往復の費用、タスク分割、readback を省く描画経路の設計メモ |
| [05-gpu-algorithm-fit.md](05-gpu-algorithm-fit.md) | どんなアルゴリズムが GPU に向くか、対照実験4本 |
| [06-writing-bend.md](06-writing-bend.md) | Bend で何が書けて何が書けないか。壁5つと抜け道1つ、probe 9 本。03 の賭けの実行側の採点 |
| [07-bend-intro.md](07-bend-intro.md) | Bend を知らない人向けの紹介記事。サンプル 13 本は型検査と実行を確認済み |
| [08-physics-and-monte-carlo.md](08-physics-and-monte-carlo.md) | Bend 2.0.34 に更新して、物理シミュレーション 2 本とモンテカルロ探索 1 本を C twin と比較。2.0.23 からの変化も記録 |
| [examples/](examples/) | 05 の実験ソース（Bend 8 本 + C twin 3 本）と生の計測値 |
| [examples/ds/](examples/ds/) | 06 の実験ソース（経路探索 / ソート / マップ / 共有木）。タイミングは未計測 |
| [examples/sim/](examples/sim/) | 08 の実験ソース（Galton board / 焼きなまし / 衝突する球）と C twin、生の計測値 |
| [examples/algorithms/](examples/algorithms/README.md) | 適性の候補16項目と、N-Queens / Pollard ρ / AST 変換 / DPLL SAT の Mac CPU 実測。C の逐次・並列版とも比較 |
| [examples/ffi/](examples/ffi/README.md) | C FFI の1呼出し当たりの追加時間と、処理をまとめた場合の比較 |
| [examples/device/](examples/device/README.md) | CPU/GPU の同期往復と、同じ総計算量をまとめた場合の比較 |
| [examples/gpui/](examples/gpui/README.md) | Bend → GPUI のmacOS描画バインディング。共有配列からMetal描画・NV12 surfaceへ接続し、CPUで画像・座標を読み出さない |
| [examples/particles/](examples/particles/README.md) | 永続バッファの粒子シミュレーションとGPUI描画。Bend CPU / Bend GPU / 手書きMetalを比較し、[コード改善と本体の改善候補](examples/particles/OPTIMIZATION.md)を分けて記録 |
| [examples/grid/](examples/grid/README.md) | CSS Grid の実用サブセット。Bend / C 実装、ブラウザ照合、CPU / Metal バッチ比較、出力木と共有連続バッファの読み取り時間 |

## 30 秒サマリ

Bend は**アフィン型という単一の制約**で、普通は両立しない3つを同時に取ろうとしている。

```
                  アフィン型 (値は高々1回しか使えない)
                            |
        +-------------------+-------------------+
        |                   |                   |
   関数を複製できない    エイリアスがない    エイリアスがない
        |                   |                   |
   パラドックスが       GC が要らない      破壊的更新が安全
   型付かない                |
        |                   |
   Type : Type で OK    GPU に載る
   (宇宙階層が不要)
```

左の枝が [01](01-universe-hierarchy.md)+[03](03-bend-wall.md)、右の枝が [04](04-gpu-execution.md)。

## 評価の結論（2026-09-21 時点、HEAD 75cb8f3e）

実機 (Apple M5 / 10 core / Metal) で検証した結果。

**本物:**

- 1 コアで C 並み。nbody で C `-O3` 4.67s に対し Bend seq 5.26s = **1.13x 遅い**だけ。16 本のピン全体で中央値 1.21x
- GPU で汎用コードが走る。同じ nbody が GPU で **0.127s = C の 36.7 倍速**
- チェッカが速い。insertion sort の完全正当性証明（整列性 + 置換）が bun 起動込み **0.058s**
- `bend2/bend.lean` 20,981 行が**実際にコンパイルを通る**。15.3 秒、`sorry` 0 件、依存公理は `propext / Classical.choice / Quot.sound` の 3 つだけ
- Hurkens のパラドックスが実測で落ちる（`f (consumed more than once)`）

**誇張:**

- チェッカが「several OOMs 速い」→ 比較対象が機械生成の反復ファイル。4 言語全部が完走する `trees_400` では対 Rocq **2.2x** でしかない。しかも Bend は型推論も宇宙制約解決も正値性検査も**やっていない**
- 「10000s のコア」→ 対抗馬は 1 コアの C だけ。`lexer` は GPU で C に**負ける** (0.96x)
- 「one *linear* pass」→ linear は時間計算量ではなく使用量の話。変換検査は実際に発散する（`@unsafe` なしでスタックオーバーフローを再現済み）
- Lean 形式化は**より小さい別モデル**に対するもの。`Lit` / template / `@unsafe` / base の law が入っておらず、`bend.ts` がそれを実装している証明は無い。CI にも入っていない

**成立していない:**

- 「the compiler *enforces* it」→ `LAWS.bend` は `main.bend` から import されない。アプリのビルド経路は法を一度も見ない。`.github/workflows/` は空、git hook も無い
- 「mathematically impossible to break laws」→ 次の 3 行で任意の偽命題が通り、**exit code は 0**:

  ```bend
  @unsafe
  def loop(-A: Type) -> A: loop(A)
  def anything(x): loop({Nat.add(x, 1n) == x : Nat})
  ```

  救いは汚染が推移的に伝播して `N defs rely on unsafe or foreign code` と一覧されること。防壁ではなく**汚染追跡**。足りないのは exit code と `--deny-unsafe` だけ

  **2.0.34 追記:** 同じファイルは `SOME PROOFS FAIL` を出して **exit 1** になった。exit code の穴は埋まっている（[08](08-physics-and-monte-carlo.md)）

## 実測の要点（[05](05-gpu-algorithm-fit.md) より）

同一の総仕事量・同一の出力で、条件だけを変えた対照実験の結果:

- **Bend の単一コア = C -O3 の単一コア**（Monte Carlo で誤差 1%、3 サイズとも）
- **GPU は 1 コア C の 55 倍**。ただし単一コアで 1 秒以上かかる計算でないと起動コスト (~90ms) 負けする
- **負荷の偏りは「index の範囲」に相関したときだけ致命的**（12.4x 悪化）。「剰余」への偏りは無料。lane に連続した部分木が割り当たるため
- **divergence のコストはゼロ**。CPU は分岐予測ミスで 36% 悪化するのに GPU は悪化しない。Bend は GPU スレッドをベクトルレーンではなく独立スレッドとして使っているため
- **配列 in-place で書ける問題は C に桁で負ける**（FWHT で 11x）。アフィン型が GPU 実行を可能にしている当のものが、最良アルゴリズムを禁止している
- 同じデータ構造なら Bend のアロケータは C の malloc/free の **11 倍速い**

**総評:** ランタイムと型理論が本物で、証明支援の看板が一番脆い。README の Limitations 節は異様に正直で、前半と後半で書いている人格が違う。
