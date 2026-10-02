# CPU / GPU をタスクごとに切り替える費用

Apple M5 / CPU 10 cores / GPU 10 cores、Bend 2.0.34
(`7d24b8d0235cb9781140512c0f163c48ea84a719`) の同期呼び出しを計測した。

```sh
just check-device
just bench-device
just bench-device --depth 7 --batch-depth 0 --rounds 0 \
  --output examples/device/results-macos-m5-scalar.json
just bench-device --depth 3 --batch-depth 0 --rounds 0 \
  --output examples/device/results-macos-m5-scalar-8.json
just bench-device --depth 5 --batch-depth 0 --rounds 0 \
  --output examples/device/results-macos-m5-scalar-32.json
```

## 何を切り替えるか

[`kernel.bend`](kernel.bend) の各 job は `seed + global_index` に同じ回数の xorshift32 を行う。
CPU の IO effect が batch の U32 集計値を受け取り、次の offset を返す。
その後の IO step の root に次の `batch!(...)` を置くため、GPU → CPU → GPU の境界が各回にある。
GPU の各 bang は native runtime の `waitUntilCompleted` を伴う。
大きな結果を CPU に取り出す処理はなく、batch ごとに U32 一つだけ戻す。

固定した総 job 数・反復数で batch のサイズだけを変える。
同じプログラムの `--gpu off` / CPU 1・10 threads を対照にする。
native C の独立した計算で checksum を先に求め、全 sample の一致を要求する。
小さい入力は Python の独立 oracle とも照合する。

2 warmups + 5 samples の中央値。コンパイル・GPU archive 構築・native oracle・標準出力を除外する。
最初の GPU 実行の待ちは raw warmup に含まれる。
driver / pipeline 等の遅延初期化がどれだけ寄与したかは分離していない。
host timer の `CLOCK_MONOTONIC` はこの Mac で 1 µs 分解能。
CPU 側の 0 ns は処理が無料ではなく、時計の分解能以下を意味する。

## 小さい仕事の同期1往復

fork なし、xorshift 0 rounds。各 job の算術は U32 の加算だけ。
各 job ごとに実際の Metal command buffer が一つ実行される。

| 往復回数 | GPU 合計 median | 1往復当たりの平均 |
|---|---:|---:|
| 8 | 2.242 ms | 0.280 ms |
| 32 | 8.753 ms | 0.274 ms |
| 128 | 35.597 ms | 0.278 ms |

連続呼び出し時の目安は **約0.28 ms / 同期1往復**。
128回の CPU 対照は 0.004 ms。Bend GPU runtime、Metal submit・queue・同期をまとめた実測であり、
GPU hardware 自体の kernel launch 費用や片方向の切り替え費用ではない。
この計測だけで、queue の待ちと OS wake-up などの寄与を分離できない。

単発の小さい呼び出しは 0.795 ms の median、計測対象の5 samples は 0.599〜1.591 ms。
最初の raw warmup は 311.192 ms、128往復版の最初の warmup は 383.011 ms。
cold start、単発、連続実行を同じ固定費として扱わない。

128往復の stage median は submit 0.478 ms、GPU execution 11.172 ms、wait 34.916 ms。
per-call に直すとそれぞれ約 3.7 / 87 / 273 µs。
execution と wait は重なり、個別 median の足し算も total median にはならない。

## 同じ総計算量をまとめる

16,384 jobs × 4,096 xorshift rounds。入力と最終 checksum は全条件で一致。
各行の total median、単位 ms。

| jobs / GPU 呼び出し | GPU 呼び出し回数 | Bend CPU 10 | Bend GPU |
|---|---:|---:|---:|
| 128 | 128 | 31.703 | 109.510 |
| 1,024 | 16 | 14.843 | 14.401 |
| 4,096 | 4 | 13.052 | 3.948 |
| 16,384 | 1 | 12.629 | **1.898** |

一つにまとめた GPU はこの CPU 10 対照の約 **6.65倍速い**。
128回に分けると GPU は CPU より遅い。
まとめると同期回数だけでなく、同時に処理できる GPU lane 数、fork / join、CPU pool wake-up も変わる。
109.510 − 1.898 ms をすべて切り替えの固定費に帰属させてはならない。
単一の小さい task の latency と、多数の独立 task の throughput は別の指標である。

xorshift 0 rounds の16,384 jobsでも、128回の GPU 呼び出しで41.703 ms、1回で1.543 ms。
この条件には fork / join 自体の費用が残るので、純粋な空 dispatch とは呼ばない。

## 検証と記録

`just check-device` の3 tests が成功。batch の境界を変えても全 job の集計値が保たれ、
GPU command count / execution time により CPU fallback を拒否する。
本計測と追加の scalar 確認は48条件・336 raw samples。C oracle と CPU/GPU の checksum が全件一致する。
UI アプリが動いている環境で、採用したビルド・テスト・計測は直列に行った。
追加確認を一度同時起動してしまった8 / 32回のデータは破棄し、直列で取り直した。
破棄した結果は ignored `build/device/discarded-concurrent-*.json` に置き、採用結果には混ぜない。
thermal / performance warning は採用計測の前後とも記録されなかった。

- [固定総計算量と単発](results-macos-m5.json)
- [128回の scalar 往復](results-macos-m5-scalar.json)
- [8回の scalar 往復](results-macos-m5-scalar-8.json)
- [32回の scalar 往復](results-macos-m5-scalar-32.json)

使用ソース・生成ソースの SHA-256、実際の Bend commit、環境、全 sample を記録する。
upstream は変更せず、生成 scratch C の Metal dispatch に計測だけを足す。
