# CSS Grid の Metal バッチと結果取り出し

Apple M5 / 10 CPU cores / 10 GPU cores / 32 GiB / macOS 26.6.2、Bend 2.0.34
(`7d24b8d0235cb9781140512c0f163c48ea84a719`) で計測した。
独立ページをまとめて一度の `!` に渡しても、この実装では GPU が CPU 10 threads より速くならなかった。
Metal の共有メモリは明示的な D2H コピーを省くが、全矩形の CPU 側での取り出しは有料だった。

GPU が共有連続バッファへ直接出力する[追加実験](GPU-FLAT.md)では、
4,096 ページの全座標の直接 read・検査・checksum は **0.53〜1.81 ms** に収まった。
このページの取り出し時間は出力木を走査・変換する費用を含み、Metal の転送帯域を示すものではない。

```sh
just check-grid-gpu
just bench-grid-gpu
just bench-grid-gpu --page-parallel --depth 0 --depth 12 \
  --output examples/grid/results/macos-m5-grid-gpu-forked.json
# 一つの規模を試す:
just bench-grid-gpu --workload dashboard --depth 12 --samples 5 --warmups 2
```

GPU 実測には Metal と clang 19+ が必要。`just test` は従来どおり GPU を要求しない。
生成 C、ネイティブ実行ファイル、`.gpu`、矩形のバイナリ dump は `build/` に置く。
GPU フォールバックは許可せず、`--gpu on` と実際の command buffer 実行回数・GPU 時刻で確認する。
GPU が実行できなかった条件は `status: failed` として記録し、成功した測定に混ぜない。

## 実装

[`gpu.bend`](gpu.bend) の balanced binary fork が `2^depth` ページを生成する。
各ページの幅は `base + (round * pages + page_index) % 97` に変え、毎回再計算する。
正規化済み入力 Data は一度作って共有する。ページ間の依存はない。

既定では [`serial-layout.bend`](serial-layout.bend) が一つのページを一つの lane で処理する。
明示的な DFS 作業リストで出力 Tree を構築し、配置・トラックサイズは元の `layout.prepare` を再利用する。
`--page-parallel` は元の `layout.bend` の兄弟・子部分木の fork も残す。
どちらも全矩形の出力木を返し、GPU 上で checksum に縮約しない。

[`gpu-probe.bend`](gpu-probe.bend) の二つの IO ステップが計測の境界になる。
`start` の後に `batch!(...)`、その結果を `consume` に渡すため、GPU 呼び出しが IO ステップの root に達する。
FFI は計測と出力形式の変換に使い、レイアウト計算は Bend で行う。
`consume` は共有ヒープの Tree を読み、`page:u32, node:u32, x/y/width/height:f32` の
24 bytes / rectangle の連続バッファを作る。id の範囲、重複、全ノード数、有限座標を検査する。
その後に checksum を計算し、最後に元の Tree を回収する。各段階を別々に測る。

C 比較版は同じ配置・トラック計算を行い、常駐 pthread workers が独立ページを chunk 16 で取る。
各ページの出力は連続した Box 配列に保存し、その後、同じ 24-byte 矩形形式に変換する。
C と Bend は出力の木・配列やメモリ管理が異なる。比率はこの二つの実装の比較である。
全ページが共有する入力 Data の参照カウント競合の寄与は分離していない。

## 時間の意味

初期入力の構築、JSON 解析、コンパイル、GPU 初期化・pipeline 構築、標準出力、dump の保存を除外する。
各 backend を直列に動かし、同じプロセスで 2 warmups + 5 samples を実行する。
stage ごとの median と、同一 sample の stage 合計の median を保存する。

| フィールド | 測定範囲 |
|---|---|
| `layout_ns` | CPU/GPU に計算を渡してから、全矩形の Tree/Box 配列を CPU が扱える状態になるまで |
| `gpu_execution_ns` | `MTLCommandBuffer.GPUEndTime - GPUStartTime`。device の実行時間 |
| `gpu_submit_ns` | command buffer の作成・encode・commit にかかった CPU 時間 |
| `gpu_wait_ns` | commit 後の `waitUntilCompleted` の CPU 経過時間。GPU 実行と重なる |
| `materialize_ns` | CPU が全矩形を走査・検査し、24-byte 連続バッファに書く時間 |
| `checksum_ns` | 取り出した連続バッファの checksum 計算 |
| `drop_ns` | Bend の元の出力木の回収。C は output storage をプロセス終了まで再利用するので 0 |

`gpu_execution_ns` と `gpu_wait_ns` は重なるため、足してはならない。
`layout_ns` は submit・wait とランタイムの前後処理を含む。
readback 相当の利用コストとして `materialize_ns` を報告するが、これは純粋な転送帯域の測定ではない。
Tree のポインタ・参照カウントを読み、id の検査と F32 の取り出し、出力メモリへの書き込みを含む。
host buffer の malloc/calloc 呼び出しは layout の前に行うが、遅延割り当ての first-touch は取り出しに含まれる。

Metal は upstream の `newBufferWithBytesNoCopy` / `MTLResourceStorageModeShared` をそのまま使う。
明示的な device-to-host コピー API の呼び出しは **0 回**。
そのことから、CPU 側の結果処理まで 0 ms とは言えない。
CUDA のページ移送、WebGPU の staging buffer / mapAsync は今回測っていない。

## 結果

4,096 ページ、ページ間だけを並列化した版。各 stage の median、単位 ms。

| ページ | 矩形 payload | C 10 layout | Bend 10 layout | GPU layout | GPU 実行 | GPU 完了待ち | GPU 結果取り出し |
|---|---:|---:|---:|---:|---:|---:|---:|
| dashboard / 99 nodes | 9.28 MiB | 0.977 | 25.613 | 53.024 | 52.599 | 52.973 | 18.790 |
| catalog / 121 nodes | 11.34 MiB | 5.832 | 247.071 | 653.321 | 653.038 | 653.275 | 32.922 |
| nested / 341 nodes | 31.97 MiB | 2.959 | 71.308 | 215.591 | 215.197 | 215.553 | 86.166 |

同一 sample の layout + 取り出しの median は GPU で **71.814 / 684.563 / 301.442 ms**、
Bend 10 で **35.212 / 261.363 / 100.215 ms**。GPU は約 **2.0 / 2.6 / 3.0 倍遅い**。
checksum と出力木の回収まで含めると、GPU は **98.867 / 729.356 / 421.445 ms**。

1 ページの GPU layout は dashboard 12.865、catalog 186.239、nested 47.247 ms。
16,384 ページでは dashboard 143.445 + 取り出し 81.202 ms、nested 715.377 + 342.146 ms。
規模を増やすと GPU のページ当たり時間は減るが、CPU 10 を上回らなかった。

ページ内 fork を残した 4,096 ページでは GPU layout が **39.948 / 826.313 / 242.199 ms**、
取り出しが **24.975 / 43.065 / 89.274 ms**。
dashboard の計算は改善し、catalog と nested は悪化した。
小さい nested 1 ページは 8.944 ms に改善したが、Bend CPU 10 の 0.224 ms より遅い。
fork の切り方は効くが、この Grid 実装の GPU 適性を裏付ける結果にはならなかった。

## 正しさと制約

`just check-grid-gpu` の 6 tests が成功。dashboard、span/dense を含む catalog、nested、
flex minimum / fractional flex / gap のケースで、C 1 / 4、Bend CPU 1 / 4、Metal の全矩形を比較し、
既存の独立した C engine の出力とも 0.002 px 以下で一致する。
元のページ内 fork 版も全矩形を比較する。計測では全成功 sample の checksum、ノード数、ページ数が一致する。
GPU geometry 検証はここに挙げたケースに限る。既存の 103 browser cases の Metal 全件照合はしていない。

catalog の 16,384 ページは `memory fault (machine stack overflow?)` で失敗する。
generated scratch C の error boundary に診断を足すと `gpu=1, error_code=7`。
これは device の `WL_ROOM` guard による `ERR_DEEP` で、upstream の per-lane stack は 2,048 words。
GPU span を既定から 4 GiB に増やしても同じエラーになる。
明示的な DFS 作業リストに置き換えても、配置・矩形 job の生成には元の再帰処理が残り、
このケースは実行できなかった。スタック容量や本家ランタイムは変更していない。

計測コードは生成した scratch C の `gpu_pass` に時刻と回数の収集を足す。
kernel の計算、scheduler、共有メモリ、stack size は変えず、`upstream/bend` は編集しない。
borrowed Tree の読み取りは固定 compiler の constructor ABI を前提とし、arity が異なる場合は失敗する。
OS の thermal / performance warning は計測前後とも記録されなかった。

生データ:

- [ページ間だけの並列化と 1〜16,384 ページ](results/macos-m5-grid-gpu.json)
- [元のページ内 fork を残した比較](results/macos-m5-grid-gpu-forked.json)
- [catalog の device stack エラー診断](results/macos-m5-grid-gpu-stack-probe.json)

使用ソース、生成ソースの SHA-256、環境、各 sample の stage 時刻、失敗した条件を記録している。
