# GPU 実行: 制約とメリット、表現力、readback

計測はすべて **Apple M5 / 10 core / Metal / clang 21** の実機。

---

## 1. なぜ汎用言語が GPU に載るのか

GPU に普通のプログラミング言語が載らない最大の理由は **GC** です。

```
  【普通の言語】                          【Bend】

  値にエイリアスがある                    アフィン型 = エイリアスがない
        ↓                                       ↓
  いつ free していいか実行時まで不明        最後の使用地点が静的に確定
        ↓                                       ↓
  トレーシング GC / 参照カウントが必要      コンパイラが free を置ける
        ↓                                       ↓
  ・全スレッド停止が要る                  ・GC が存在しない
  ・ポインタ追跡が分岐だらけ              ・回収は term_drop 1 個
  ・GPU の実行モデルと相性最悪              (アロケーションゼロの反復ループ)
        ↓                                       ↓
     GPU に載らない                          GPU に載る
```

[02-affine-types.md](02-affine-types.md) の「GC が要らない」が、そのまま GPU 実行の許可証になっている。**これが Bend の設計の核心です。**

### interaction net ではない

著者の前作 HVM は interaction combinator でしたが、**Bend 2 は違います**。論文 BendRT §1 が明言 (「Readers of the author's earlier runtimes may expect interaction nets; there are none」)。実体は:

```
  1 ノード = 64 bit ワード      (comp.ts:3998)
  ┌──────┬──────────┬────────────────────────────────┐
  │ tag  │   aux    │            loc                 │
  │ 7bit │  16bit   │           40bit                │
  └──────┴──────────┴────────────────────────────────┘
   種類    ctr id     ヒープ上の位置 (2^40 ワード上限)

  U32 / F32 / 2^48 未満の Nat / 1 ワードの ctr は
  ワードに packed されてヒープに触らない
```

C のコールスタックを使わず、**フラットな worklist ステートマシン**で回す。各関数は `work_loop` 内の 1 セグメントで、ホストでは `musttail`、デバイスでは 1 個の `switch` のケース。

### 1 ソースからホストとデバイス

`bend file.bend -o out.c` で出る C を実際に見ると:

```c
#ifdef __METAL_VERSION__
#include <metal_stdlib>
using namespace metal;
...
#include <Metal/Metal.h>
```

**1 ファイルの中に Metal シェーダとホストコードが両方入っている。** `#embed __FILE__` で自分のソースを自分に埋め込み、実行時に GPU 用に再コンパイルする (`comp.ts:3666`)。

---

## 2. メリット: 実測

### nbody ベンチ (bench/runtime/nbody)

| | 時間 | 対 C |
|---|---|---|
| C `-O3 -ffp-contract=off` 1 コア | 4.67s | 1.00x |
| Bend `--threads 1 --gpu off` | 5.26s | 1.13x **遅い** |
| Bend 10 コア CPU | 0.893s | 5.2x 速い |
| Bend GPU (Metal) | **0.127s** | **36.7x 速い** |

出力チェックサムは 4 つとも一致 (`3516450380`)。C twin は `musttail` まで付けた誠実な実装で、手加減はない。

**コードは 1 行も変えていません。** `!` を付けるだけ:

```python
def main() -> IO(Unit):
  result = pow2!(20n)      #  ! = この呼び出しを GPU で
```

### ピン全体 (M4 Max、16 本)

| | 対 C |
|---|---|
| SEQ (1 コア) | 中央値 1.21x 遅い / 幾何平均 1.30x 遅い。16 本中 15 本が C 以下、勝ちは tree-matmul のみ |
| PAR (16 コア) | 2.6x 〜 13.1x 速い |
| GPU | **0.96x (負け) 〜 107.6x** |

GPU の幅が異常に広い。これが次の「制約」の話に直結します。

---

## 3. 制約 (1): 負荷分散はプログラマの責任

**work-stealing が存在しません** (`grep steal` = 0 件)。

```
  構造: 128 x 128 = 16384 個の固定リング (各 1024 スロットの SPSC FIFO)
        1 threadgroup = 128 スレッド = 1 行
        1 lane = 1 リング = 1 タスク列

  分割点は構文だけ (comp.ts:1429):
        「2 個以上の束縛が全部 call である let」だけが fork になる

        a b = pow2(p) pow2(p)      ← これが fork
        ~~~~~~~~~~~~~~~~~~~~

  スケジューリング: bulk-synchronous の 2 相
        grow 相 → 行方向に fork を展開
        work 相 → 各 lane が自分のリングを逐次ドレイン
```

lane 間で仕事を移す経路が**存在しない**。偏ったら末尾で lane が遊ぶだけ。論文自身が認めている:

> the runtime declines to correct that: **balance is the program's job**

### 実測: 逐次チェーンを GPU に投げるとどうなるか

fork が 1 個も出ない、純粋に逐次な計算 (8M 回の加算):

```python
def sum(+n: Nat, acc: U32) -> U32:
  match n:
    case 0n: acc
    case 1n+p: sum(p, (acc + 1 : U32))
```

| | 時間 |
|---|---|
| GPU | 0.336s |
| CPU 1 スレッド | 0.003s |

**GPU が 100 倍遅い。** 1 lane だけが動いて、残り 16383 個が完全に遊んでいる。

ピンの `lexer` が GPU で 1.075s、16 コア CPU で 0.198s (GPU が **5.4 倍遅い**) なのも同じ理由。字句解析は本質的に逐次だから。

```
  ┌─────────────────────────────────────────────────────────┐
  │  Bend の GPU は「分割統治が書ける問題」専用と考えるべき   │
  │                                                          │
  │    木・再帰・divide and conquer  →  40〜100x            │
  │    逐次 fold / 状態機械           →  CPU より遅い        │
  └─────────────────────────────────────────────────────────┘
```

---

## 4. 制約 (2): 表現力は制約されるか

**言語機能としては、ほぼ制約されません。** ただし 4 つ現実的な壁がある。

### (a) IO は 100% ホスト専用

`comp.ts:4823-6226` が丸ごと `#if !DEVICE`。デバイスからのコールバックは**ない**。

```
        ホスト                          デバイス
  ┌──────────────────┐            ┌──────────────────┐
  │ イベントループ    │            │                  │
  │  io_step         │            │  純粋計算のみ     │
  │   ├ 評価          │  ← ! →     │                  │
  │   ├ C handler 実行│            │  print も        │
  │   ├ 継続に適用    │            │  file も         │
  │   └ 再評価        │            │  socket も なし   │
  └──────────────────┘            └──────────────────┘
        effs/*.c
```

Bend 側は `IO.OP` の ctr を作って返すだけ。実際の副作用はホストの handler が実行する。

**つまり GPU には「純粋な計算カーネル」を投げる形になる。** これは Bend 固有ではなく GPU 一般の制約で、むしろ CUDA より綺麗に分離されている。

### (b) `!` から到達可能な部分だけがデバイスに載る

```
  dev = reach([...bangs])              (comp.ts:3048)
  それ以外は #if !DEVICE で落ちる
```

到達解析を外すと実行時に `ERR_FIDS` (「a function the device does not hold」)。`!` の引数に closure が来うる場合は保守的に**全 closure を載せる** (`wide`) という粗い近似が入っていて、ここは脆い。

### (c) CPU と GPU は同時に計算しない

`!` は「GPU カーネル化」ではなく**逐次点でのシーム**。`corpus_eval` (`comp.ts:5402`) が継続を root に差し替えてリング 0 に積み、`cube_run(H, true)` を呼ぶ。その間ホストは待つだけ。

```
  ホスト ────┐                    ┌──── ホスト
             │   [cb commit]      │
             └─── GPU 全開 ───────┘
                   ↑
            この間ホストは waitUntilCompleted で寝ている
```

デバイスが無ければ `!` は**完全に無視される** (CPU で走る)。移植性としては良い設計。

### (d) 固定上限

| 項目 | 上限 | エラー |
|---|---|---|
| lane あたり再帰深度 | 2048 ワード (`STAK_LEN = 1<<11`) | `ERR_DEEP` |
| リング | 1024 タスク | `ERR_RING` |
| GPU ヒープ | **起動時固定。伸長不可** (`corpus_grow` が `io_gpu` なら即失敗) | `ERR_HEAP` |
| Metal のデフォルト span | `min(recommendedMaxWorkingSetSize, maxBufferLength, 2GB)` | — |
| Nat 即値 | 2^48 | — |
| refcount | 2^24 | — |
| arity / cid / fid | 255 / 65535 / 65535 | — |

CPU 側は 8GiB から in-place で倍々に伸びるのに対し、**GPU はヒープを伸ばせない**。`--gpu 8GB` で明示指定する必要がある。ホストは 1 worker あたり 2GiB の mmap + ガードページ + SIGSEGV ハンドラなので、再帰深度は事実上無制限。

また `F64` が存在しないのは **Metal に f64 がないから** (README の Limitations に明記)。言語の数値型が GPU に引っ張られている唯一の箇所。

---

## 5. readback は低速化しないか → **実測でゼロ**

質問の核心。結論から言うと **Metal では readback が存在しません。**

### 仕組み

```c
// comp.ts:5078
gpu_buf = [gpu_dev newBufferWithBytesNoCopy:CORPUS length:bytes
  options:MTLResourceStorageModeShared
    | MTLResourceHazardTrackingModeUntracked deallocator:nil];
```

`newBufferWithBytesNoCopy` + `StorageModeShared` = **ホストの mmap したページをそのまま GPU バッファとして包む**。

```
  【従来の GPU プログラミング】          【Bend on Metal】

   ホストメモリ                           ┌─────────────────┐
   ┌──────────┐                           │                 │
   │  入力     │                          │   Corpus        │
   └────┬─────┘                           │   (1 本の配列)  │
        │ cudaMemcpy H2D                  │                 │
        ▼                                 │  ヘッダ         │
   デバイスメモリ                         │  ALC            │
   ┌──────────┐                           │  ring           │
   │  計算     │                          │  lane stack     │
   └────┬─────┘                           │  static         │
        │ cudaMemcpy D2H   ← ここが遅い   │  heap           │
        ▼                                 │                 │
   ホストメモリ                           └─────────────────┘
   ┌──────────┐                            ↑            ↑
   │  結果     │                        ホストが     GPU が
   └──────────┘                        同じアドレスで参照

                                        コピーは 0 回
```

Apple Silicon は UMA (Unified Memory Architecture) なので、**物理的に同じ DRAM**。「readback」という概念自体がない。

### 実測 1: 返す構造の大きさを 16 倍にしても時間が変わらない

GPU で二分木を構築して返し、CPU 側で畳む:

```python
def build(+d: Nat) -> T:              # GPU で構築
  match d:
    case 0n: L{1}
    case 1n+p:
      a b = build(p) build(p)
      N{a, b}

def main() -> IO(Unit):
  t = build!(20n)                     # GPU から木がそのまま返る
  r = total(t)                        # CPU で畳む
  IO.print(U32.show(r))
```

| 木のサイズ | 葉の数 | wall | user | sys |
|---|---|---|---|---|
| d=18 | 262,144 | 0.09s | 0.01s | 0.07s |
| d=20 | 1,048,576 | 0.09s | 0.02s | 0.07s |
| d=22 | 4,194,304 | **0.10s** | 0.08s | 0.11s |

**返すデータ量を 16 倍にしても wall time はほぼ不変。** `user` が増えているのは CPU 側の畳み込みそのもの。転送コストは観測できない。

### 実測 2: スカラを返す場合と構造を返す場合が同じ

| | wall |
|---|---|
| 100 万ノードの木を GPU から返す | 0.090s |
| U32 を 1 個だけ返す (畳み込みも GPU) | 0.090s |

**完全に同じ。** readback は文字通りタダです。

### ただし本当のコストは別にある

readback ではなく、こちらが効く:

**(a) GPU 起動の固定コスト ~90ms**

```
$ ./tiny            # ! の中身は pow2(1) = ほぼ何もしない
real 0.09 〜 0.10s

$ ./tiny --gpu off
real 0.00s
```

デバイス初期化 + バッファマップ + パイプライン読み込みで **約 90ms の床**がある。短い計算に `!` を付けると純損。

**(b) Metal シェーダのコンパイル (初回)**

`gpu_desc()` が `newLibraryWithSource` でソースから Metal ライブラリを作る。バイナリアーカイブにキャッシュされる (`<binary>.gpu`) が、初回は必ず払う。

```
cold: 0.218s / warm: 0.096s     (この小さいプログラムの場合)
```

大きいプログラムでは深刻で、`comp.ts:154` のコメントが実測値を書いている:

> hvm5 under a bang: **32 s of Metal compile**, 2.6 s so

**(c) `cube_run` 1 周ごとのホスト同期**

```c
static void gpu_run(u32 f) {
  if (f < CUBE_T) gpu_kernel(0, 1);
  if (f < LANES)  gpu_kernel(0, CUBE_G);
  gpu_kernel(1, CUBE_G);
  gpu_kernel(2, 1);
}
// gpu_pass: [cb commit]; [cb waitUntilCompleted];
```

最大 4 個のカーネルを 1 個のコマンドバッファにまとめて、**1 回だけ同期**する。この `cube_run` ループがフロンティアが尽きるまで回る。フロンティアが太い（＝分割統治）なら周回数が少なく、細い（＝逐次）なら周回数が多くなって同期が効いてくる。

```
  ┌────────────────────────────────────────────────────────┐
  │  GPU 性能の実際の支配要因 (readback ではない)            │
  │                                                         │
  │   1. 起動固定コスト        ~90ms                        │
  │   2. Metal シェーダ compile 初回のみ、プログラム規模次第 │
  │   3. cube_run の周回数     計算の「形」で決まる          │
  │   4. lane の遊び           work-stealing がないので      │
  └────────────────────────────────────────────────────────┘
```

---

## 6. Metal ならその問題は解消できるか → **すでに解消されている**

正確には「Metal だから解消されている」。逆に **CUDA 側にはコストが残っている**。

| | Metal (Apple Silicon) | CUDA (discrete NVIDIA) |
|---|---|---|
| 確保 | `newBufferWithBytesNoCopy` + `StorageModeShared` | `cuMemAllocManaged(CU_MEM_ATTACH_GLOBAL)` |
| 物理メモリ | **ホストと同じ DRAM (UMA)** | **別の VRAM** |
| 配置ヒント | — | `SET_PREFERRED_LOCATION = DEVICE` |
| readback | **ゼロ。概念として存在しない** | ホストが触るとページフォルト → **PCIe 越しにページ移送** |
| 前提条件 | Metal が使えること | `CONCURRENT_MANAGED_ACCESS` 必須 (無ければ GPU を使わない) |

CUDA 側は corpus 全体を `SET_PREFERRED_LOCATION = DEVICE` にしているので、**GPU の計算結果をホストが読むと managed memory のページ移送が走ります**。discrete GPU では PCIe 帯域がそのままコストになる。上で測った「16 倍のデータを返しても同じ時間」は **Metal 固有の結果**で、NVIDIA では成立しません。

さらに、論文 §12 が CUDA レーンについて「in the source and **not measured here**」と自認しています。**CUDA パスは実測されていない。**

```
  ┌──────────────────────────────────────────────────────────────┐
  │  結論                                                         │
  │                                                               │
  │  Metal / Apple Silicon:                                       │
  │    readback は存在しない。UMA で物理的に同じメモリ。           │
  │    実測でデータ量に対して完全にフラット。                      │
  │    Bend の設計が一番綺麗にハマるのがこの組み合わせ。            │
  │                                                               │
  │  CUDA / discrete GPU:                                         │
  │    managed memory のページ移送が readback 相当のコストになる。 │
  │    しかも著者が「未計測」と認めている。                        │
  └──────────────────────────────────────────────────────────────┘
```

Bend が M4 / M4 Max でピンを取り、`CUBE_LOG = 7` / `CUBE_T = 128` / `TG_HOLD = 2304` といった定数を Apple の実測で焼き込んでいる (`comp.ts:3604-3620`) のも同じ話。**現状 Bend は事実上 Apple Silicon 向けにチューニングされた処理系**と見るのが正確です。

---

## 7. まとめ: いつ `!` を付けるべきか

```
  付けるべき                              付けてはいけない
  ──────────                              ────────────────
  ✓ 分割統治が書ける                      ✗ 逐次 fold / 状態機械
    (a b = f(x) g(y) の形)                  (CPU より 100 倍遅くなる)
  ✓ 木構造の構築・走査                    ✗ 総計算量が小さい
  ✓ 各枝の仕事量が揃っている                (90ms の起動コストで負ける)
  ✓ 数百 ms 以上かかる計算                ✗ 文字列処理
                                            (連結リストなので元から遅い)
  ✓ 結果が大きくても構わない              ✗ 深い再帰
    (Metal なら readback タダ)              (lane あたり 2048 ワード)
```

### 評価

**「汎用言語が GPU で動く」は本物。** 配列コンビネータを flatten する Futhark / Accelerate 方式ではなく、再帰・ヒープ確保・代数的データ型込みの**スケジューラそのものがデバイス上で走り**、ホストと 1 本の unified heap を共有している。これは既存のどの処理系とも違う。

**ただし限定付き:**

1. IO は 100% ホスト側。`!` は逐次点での同期シームで、CPU と GPU は同時に走らない
2. デバイスに載るのは `!` から到達可能な部分プログラムだけ
3. GPU ヒープは起動時固定・伸長不可。再帰深度は lane あたり 2048 ワード
4. work-stealing がないので、負荷分散義務が**言語契約としてプログラマに転嫁されている**

**「no threads, no locks, no kernels」は文字通りには正しい**（ユーザは書かない）が、内部にはホスト pthread プール・`bank_lock`・3 パスのカーネルディスパッチが実在する。**「full memory unification」は誇張ではなく、Metal のゼロコピー共有バッファという実装で裏付けられている。**
