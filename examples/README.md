# 実験ソース

[../05-gpu-algorithm-fit.md](../05-gpu-algorithm-fit.md) の対照実験一式。計測環境は Apple M5 / 10 core / Metal / clang 21 / Bend 2.0.23。生の計測値は [results.txt](results.txt)。

## ファイル

| ファイル | 役割 |
|---|---|
| `fwht_check.bend` | **正しさの検証。** FWHT の involution 則 `FWHT(FWHT(x)) == 2^d · x` を d=1,2,5,10 で確認する。まずこれを走らせる |
| `mc.bend` | **実験1の本体。** Monte Carlo π 推定。reduce-heavy / 均等 / 分岐なし＝Bend の GPU にとって理想形 |
| `mc.c` | `mc.bend` の C twin（単一スレッド、同一 LCG・同一分岐なし判定） |
| `fw.bend` | **実験2の本体。** FWHT。merge-heavy（combine が O(subtree)） |
| `fw_arr.c` | C twin #1: 配列 in-place FWHT。C 屋が実際に書くもの |
| `fw_tree.c` | C twin #2: Bend と同形の木 + malloc/free。データ構造の差と実行系の差を分離するため |
| `hot.bend` | 実験3: 仕事が index の**剰余**に偏る（`i % 64 == 0`）。総仕事量は `mc.bend` と同一 |
| `skew.bend` | 実験3: 仕事が index の**範囲**に偏る（線形ランプ）。総仕事量は同一 |
| `block.bend` | 実験3: 仕事が index の**範囲**に偏る（先頭 1/64 に集中）。総仕事量は同一 |
| `uni.bend` | 実験4の対照: 常に 32 ラウンド、分岐なし |
| `div.bend` | 実験4: 乱数ビットで 64 ラウンド / 0 ラウンドに分岐。平均仕事量は `uni.bend` と同一 |
| `bench.sh` | best-of-3 の壁時計を測る `best` 関数 |

`hot` / `skew` / `block` は `mc.bend` の `leaf` だけを差し替えたもの。`div` / `uni` も互いに `pick` だけが違う。**差分以外は同一**にしてある。

## 走らせ方

リポジトリ直下で `just setup` を済ませてから実行する。Bend の起動には固定コミットを使うラッパーを通す。

```sh
just setup
mkdir -p build

# まず正しさ
just bend examples/fwht_check.bend
#=> d=1 .. d=10 すべて involution: True

# ネイティブバイナリを作る（clang + Metal）
just bend examples/mc.bend -o build/mc
```

生成されたバイナリの実行モード:

```sh
build/mc                          # GPU (! があれば自動で使う)
build/mc --gpu off                # CPU 全コア
build/mc --threads 1 --gpu off    # CPU 1 コア
```

C twin:

```sh
cc -std=c11 -O3 examples/mc.c -o build/mc_c && build/mc_c
cc -std=c11 -O3 -DDEP=24 examples/fw_arr.c  -o build/fw_arr  && build/fw_arr
cc -std=c11 -O3 -DDEP=24 examples/fw_tree.c -o build/fw_tree && build/fw_tree
```

## 規模の変え方

Bend 側は末尾の定数を書き換える。C 側は `-DDEP=` / `-DPER=` で渡す。

| | Bend | C |
|---|---|---|
| `mc.bend` 系 | `def dep()` = 木の深さ、`def per()` = 葉あたりサンプル数 | `-DDEP` / `-DPER` |
| `fw.bend` | `def dep()` = 木の深さ | `-DDEP` |
| `div` / `uni` | `main` の `tree!(20n, 0, 256n)` の第3引数 | — |

Bend と C の定数を合わせれば出力は**ビット一致する**。一致しなければどこかが壊れている。

## 期待値

| 条件 | 出力 |
|---|---|
| `mc.bend` d=20 K=4096（`mc.c` の既定と同じ） | `3373374630`（π = 3.141700） |
| `fw.bend` d=20 | `950534144` |
| `fw.bend` d=22 | `3802136576` |
| `fw.bend` d=24 | `2323644416` |

## 注意

- **d を上げるとメモリを食う。** `fw.bend` は d=24 で数百 MB。GPU ヒープは起動時固定なので、足りなければ `--gpu 8GB` を渡す
- **`fw_tree.c` は d=24 で 10 秒近くかかる。** malloc/free が律速なので、これは想定どおり
- **U32 はオーバーフローする。** 規模を変えるとき `2*K*i` のような式が 2^32 を超えると、エラーにならず静かに総仕事量が変わる（実験中に一度これで偽の結果が出た）

## 物理とモンテカルロの実験

[../08-physics-and-monte-carlo.md](../08-physics-and-monte-carlo.md) の実験ソースは `sim/` にある。

| ファイル | 役割 |
|---|---|
| `sim/galton.bend` / `galton.c` | 物理: Galton board。重力 + ピンとの円衝突 + 壁。2^16 個の独立なボール |
| `sim/anneal.bend` / `anneal.c` | モンテカルロ探索: 32 品目ナップサックの焼きなまし。2^14 本の独立チェーン。C は厳密解（DP）も出す |
| `sim/balls.bend` / `balls.c` | 物理: 1 箱 8 球の衝突（O(N²) の弾性衝突）。2^12 個の独立な箱 |
| `sim/balls_flat.bend` / `gen_balls_flat.py` | balls.bend の箱の状態を f32 引数 32 個に展開した生成コード（C twin は `balls.c`）。生成し直すときは `python3 examples/sim/gen_balls_flat.py > examples/sim/balls_flat.bend` |
| `sim/fmc.bend` / `fmc.c` | モンテカルロ探索: 三目並べの flat Monte Carlo。初手の評価と、対ランダム 2^8 局。`fmc.c --audit` は完全読みとの照合（C のみ） |
| `sim/mcts.bend` / `mcts.c` | モンテカルロ探索: 三目並べの MCTS（UCT）を root parallelization で。1 手 16 本 × 576 反復。`mcts.c --audit` は完全読みとの照合（C のみ） |
| `sim/c4.bend` / `c4.c` | Connect Four の MCTS。同じ予算で「木 2^w 本 × 予算/2^w」と「木 1 本 × 予算」を対戦させ、root parallelization の質の落ち方を測る |
| `sim/ttt.bend` | fmc と mcts が共有する三目並べ（盤面、プレイアウト、集計、対局の記録） |
| `sim/probes/twin_leak.bend` | 共有リストを 2 つの引数に渡すとメモリが解放されない最小再現 |
| `sim/check.sh` | 小さい規模で Bend と C の出力がビット一致するか（`just check-sim`） |
| `sim/bench.sh` | C / Bend 1 core / Bend 全コアの best-of-3 と max RSS（`just bench-sim`） |
| `sim/results.txt` | 生の計測値 |

規模は各 `.bend` の `def dep()` / `def steps()`（fmc・mcts・c4 は `def games()`、mcts・c4 はさらに `def iters()`、c4 は `def budget()`）、C 側は `-DDEP=` / `-DSTEPS=` / `-DGAMES=` / `-DITERS=` / `-DBUDGET=`。
C twin は `-ffp-contract=off` でビルドする（`check.sh` / `bench.sh` が付ける）。

| 条件 | 出力 |
|---|---|
| `galton` dep=16 steps=2048 | `0 75 331 867 2204 4610 7760 10693 12118 11002 7804 4719 2126 876 301 50` |
| `anneal` dep=14 steps=4096 | `best=976 chains=1 mask=882706334`（DP の厳密解も 976） |
| `balls` / `balls_flat` dep=12 steps=4096 | `contacts=231820 checksum=4256907475` |
| `fmc` dep=10 games=8 | `1382 1252 1418 1211 1569 1222 1376 1240 1400` と `as X: 128 won 0 drawn 0 lost; as O: 121 won 3 drawn 4 lost` |
| `mcts` dep=4 iters=576 games=8 | `1099 764 1042 813 1700 843 1095 776 1084` と `as X: 127 won 1 drawn 0 lost; as O: 120 won 8 drawn 0 lost` |
| `c4` dep=4 iters=256 budget=1024 games=6 | `480 503 609 891 562 572 479`、続いて `1 trees x 1024 vs 1 x 1024: 31 won 0 drawn 33 lost` など 4 行 |

## データ構造の実験

`ds/` の前提は [ds/CONTRACT.md](ds/CONTRACT.md) を参照。

```sh
just build-path       # ソースに記録された規模でビルド
just check-path       # SEQ / PAR / GPU / C の出力を表示
just build-sort 12    # 小さい規模でソートをビルド（既定は25）
just check-sort       # 正例・負例の出力を表示
```

`check-path` / `check-sort` は既存の実験スクリプトで、GPU を使う。
`just test` は GPU を必要としない軽い検証。時間計測は同時実行せず、静かなマシンで行う。
