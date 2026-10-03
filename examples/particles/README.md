# 永続バッファのパーティクル実験

Bend CPU、Bend GPU、手書きMetal computeで同じ粒子状態を更新し、同じMetal rendererで描画する。
更新後の粒子をCPUの描画用配列へ取り出さず、GPUIのNV12 surfaceまでGPU上で接続した。
macOS / Metal / Rustが必要。GPUIは既存バインディングの固定版0.2.2を使用する。

コンパイラを固定したコード改善の比較は[`OPTIMIZATION.md`](OPTIMIZATION.md)を参照。
`--variant flat`では粒子ごとのcallbackを省き、100万粒子＋追加計算64回のGPU更新が
同じ分割数で6.762→1.481 msに改善した。アプリ側で改善できた部分と、本体側に残る候補を分けて記録している。

さらに[`CPU.md`](CPU.md)でCのCPU対照実装と比較した。
100万粒子＋追加計算64回・1,024 jobs・10 workersではBend 12.275 / C 12.159 msと近い値になった。
軽い更新には差が残るため、Cの逐次ループ・worker poolと分けて計測している。

[`GPU.md`](GPU.md)では分割方法・runtime段階・生成ループの直接kernel化を比較した。
100万粒子＋追加計算64回・16,384 jobsのGPU実行は汎用Bend 1.291 / 直接leaf 0.821 / Metal tiled 0.573 ms。
直接leafはコンパイラlowering案を調べる実験用対照で、通常のbackendには含めていない。

```sh
# ネイティブGPUIウィンドウ。Pause/Resumeとリサイズに対応。
just particles --backend bend-cpu --count 100000
just particles --backend bend-gpu --count 1000000 --noise-rounds 64
just particles --backend metal --count 1000000 --noise-rounds 64

# コンパイラを変えずにcallbackを省いた版。比較元は--variant callback（デフォルト）。
just particles --variant flat --backend bend-gpu --count 1000000 --noise-rounds 64 --jobs 16384
just bench-particles-code

# C CPU対照との比較。--threadsはCPU worker数。
just particles --backend c-cpu --count 1000000 --noise-rounds 64 --threads 10
just particles --backend c-direct --count 10000 --jobs 64
just bench-particles-cpu

# GPU分割方法と生成ループの直接kernel化を比較。段階診断は通常測定と分離する。
just check-particles-gpu
just bench-particles-gpu

# 状態・描画・実ウィンドウの検証。
just check-particles
just check-particles-window

# 42条件 × 順序を変えた3反復。ビルド・検証・計測は直列。
just bench-particles

# 小さい比較、分割数の指定、タイミングと検証データの保存。
just bench-particles --count 100000 --jobs 16384 --samples 7 --repeats 3 --output build/particles/small.json
just particles --backend bend-gpu --count 10003 --jobs 4096 --frames 4 --headless --verify --dump build/particles/dump --output build/particles/check.json
```

## 状態と契約

[`api.bend`](api.bend) のcallbackは `Tick -> Array<F32> -> Array<F32>`。
前フレームの配列を消費して更新し、同じ確保領域を返す。native側は配列の型・容量・アドレスを確認する。
更新後のGPU描画が完了してから、次のcallbackへ所有権を渡す。
GPUIへ渡す画像は別のCVPixelBufferで、Rust側がretainする。

| 項目 | 契約 |
|---|---|
| 粒子数 | 1〜1,000,000。端数の粒子数も扱う |
| 配列 | 1粒子8個のF32、32 bytes。全体容量を2の冪に切り上げる |
| 内容 | x、y、vx、vy、寿命、24-bit整数を正確に表す乱数状態、予約2語 |
| 座標 | 正規化した2D座標。描画では画面外をclipする |
| 時間 | 固定dt=1/60秒。表示の経過時間から独立、Pause中は更新しない |
| 更新 | 中心への弱い引力、重力、速度への抵抗、寿命減少、寿命切れによる再生成 |
| 追加負荷 | `--noise-rounds 64`で乱数を64回更新し、乱数由来の加速度を加える |
| 分割 | `--jobs`は64〜16,384の2の冪。各仕事が連続した範囲を更新 |
| 描画 | 半径2 pixelsの円形sprite、6 vertices/instance、加算合成、BGRA8 |
| 出力 | GPUでBGRA→NV12変換。偶数の幅・高さ、2〜2048。奇数指定は切り下げ |

追加負荷は算術量を増やす対照条件で、Perlin/curl noiseの実装ではない。
粒子間の衝突・近傍探索・透明度ソート・HDRは含まない。
フレーム間で粒子の状態は残るが、CPU/GPUの複数フレームを同時には処理しない。
ウィンドウは既存の[GPUI ABI](../gpui/README.md)を共有し、終了時の制御もその制約に従う。

## 実装の分離

- [`simulation.bend`](simulation.bend): 粒子更新とforkによる範囲分割。CPU/GPUで同じソース。
- [`simulation-flat.bend`](simulation-flat.bend): 上記の物理計算を共有し、静的な読み出しと自己末尾再帰で更新する比較版。
- [`state.h`](state.h) / [`cpu.h`](cpu.h) / [`cpu.c`](cpu.c): CPU/Metalの共有状態契約と、独立したC逐次更新・永続worker pool。
- [`particles.metal`](particles.metal): 手書き更新kernelと、3経路共通の円形sprite描画。
- [`native.c`](native.c): 永続配列の所有権、Metal command、画像pool、計測、GPUI接続。
- [`oracle.h`](oracle.h): 初期状態と検証専用の独立C計算。計測中の更新には使用しない。
- [`../../tests/particles.py`](../../tests/particles.py): 独立Python float32計算、円形spriteとNV12の画像oracle。
- [`../../scripts/particles_bench.py`](../../scripts/particles_bench.py): ビルド後に検証し、順序を変えて直列計測。
- [`gpu-profile.h`](gpu-profile.h) / [`gpu-leaf.metal`](gpu-leaf.metal) / [`../../scripts/particles_gpu.py`](../../scripts/particles_gpu.py): opt-inのGPU段階診断と生成ループの専用kernel対照。

配列は初期化時に一度確保する。通常のArray.splitは配列をコピーするため使わず、
`@unsafe`を限定してdisjointな範囲の共有handleを渡し、Array.joinで余分な参照を解放する。
この範囲の非重複性は型検査だけでは証明していない。全状態の照合と、未使用容量のcanaryで検証する。
`state_allocations=1`は粒子データ本体についての値で、Bend runtimeの全allocationを数えるものではない。

画像はCVPixelBufferPoolから取得する。粒子配列と中間のBGRA textureは再利用し、
以前の画像をGPUIが保持していても上書きしない。プールの最小個数は3で、サイズ変更時に作り直す。
更新は完了を待つ。描画commandとNV12変換commandは同じqueueに続けて投入し、変換完了時だけCPUで待つ。
手書きMetal更新もこの同期境界に合わせる。これは同期版の比較で、非同期化したMetal rendererの性能上限ではない。

## 検証と計測範囲

`just check-particles`は1・17・10,003粒子、追加負荷0・64、callback版の3 backendとflat版のCPU/GPU・Cの2経路、連続4フレームを検証する。
位置・速度・寿命は絶対誤差2e-6以内、乱数状態と予約語は完全一致。
1粒子の全NV12画素は独立した円形sprite計算と照合し、複数粒子の全画素もbackend間で照合する
（8-bit変換・rasterizationの差として最大2/255を許容）。
さらにbenchmark前に42条件の全粒子を、別の検証用processで連続4フレーム照合する。

本計測は1万・10万・100万粒子、追加負荷0・64、Bendのjobs=1,024・4,096・16,384。
手書きMetalはjobsに依存しないので各粒子数・負荷で一度だけ測る。
各条件は3回の別processで実行順をshuffleし、各processの最初3フレームを除いた7フレームを保存する。
表の値は各processのmedianを取り、その3個のmedianをさらにmedianにしたもの。
全raw samples、反復medianの範囲、順序、実際のBend commit・環境・source SHA256を
[`results-macos-m5.json`](results-macos-m5.json)に保存する。

| フィールド | 測定範囲 |
|---|---|
| `state_prepare_ns` | 最初の粒子配列の確保・初期化・Metal bufferへの共有mapping。フレーム時間の外 |
| `surface_prepare_ns` | 出力画像の取得とMetal plane textureの準備。初回はpool作成も含む |
| `update_ns` | 更新のCPU経過時間。Bend callback評価／Metal submit／GPU完了待ちを含む |
| `update_gpu_ns` | 更新commandのGPU開始〜終了。CPU版は0 |
| `update_wait_ns` | 更新中のCPU完了待ち。`update_ns`の内数 |
| `draw_gpu_ns` | 共通の粒子描画commandのGPU時間 |
| `convert_gpu_ns` | 共通のNV12変換commandのGPU時間 |
| `render_wait_ns` | 描画・変換の最後に行うCPU完了待ち。`render_ns`の内数 |
| `render_ns` | 共通の描画・変換のCPU経過時間。encode・submit・waitを含む |
| `frame_ready_ns` | 出力準備＋更新＋描画・変換＋古い画像の解放。GPUIへ渡す画像が完成するまで |
| `cpu_readback_bytes` | 描画adapterで粒子配列をCPUへ取り出す量。通常経路は0 |
| `verify_ns` | 任意のC oracle照合とdump。フレーム時間の外 |

GPU時間とCPU待機は重なるので足し算しない。
`cpu_readback_bytes=0`は実装経路の契約値で、hardware byte counterではない。
Bend CPU版がシミュレーションのために状態を読むこと、最初の初期化、明示的な検証の読み取りは別の処理。
検証なしの計測ではCPUで粒子の描画用データや全画素を取り出さない。
GPUIのscene構築・present・display/input latencyは計測外で、この時間の逆数を表示FPSとは呼ばない。
MacのCPU clockの分解能は1µs。0 nsは無料を意味しない。

## M5での結果

以下は最初のcallback版の結果。コード改善後のA/B再計測は[`OPTIMIZATION.md`](OPTIMIZATION.md)に分けている。

2026-10-03、Apple M5 / CPU 10 cores / GPU 10 cores / 32 GiB、Bend 2.0.34。
960×540、半径2 pixels。以下はms。
Bendは測った3種類の分割数のうち、更新時間が最短だったものを掲載する。
CPUは全条件で1,024 jobs、GPUは1万粒子で4,096 jobs、10万・100万粒子で16,384 jobs。
CLIの省略時もこの測定に基づく分割数を使う。任意の入力で最適な分割数を保証するものではない。
表の太字はBendのCPU/GPU間で速い方。

| 粒子数 | 追加乱数更新 | Bend CPU 更新 | Bend GPU 更新 | 手書きMetal 更新 |
|---:|---:|---:|---:|---:|
| 10,000 | 0 | **0.384** | 0.668 | 0.195 |
| 100,000 | 0 | 1.471 | **1.268** | 0.216 |
| 1,000,000 | 0 | 11.789 | **6.998** | 1.027 |
| 10,000 | 64 | **0.516** | 0.678 | 0.202 |
| 100,000 | 64 | 3.059 | **1.339** | 0.274 |
| 1,000,000 | 64 | 28.923 | **8.985** | 0.885 |

計測した条件では、10万・100万粒子の更新でBend GPUがBend CPUより速かった。
100万粒子＋追加計算ではBend GPUがBend CPUの約**3.22倍**速い。
一方、同条件の手書きMetal更新に対しては約**10.15倍の時間**がかかる。
CPU対GPUの改善と、他のGPU実装に対する優位性は別に判断する。

追加計算64回のとき、画像をGPUIへ渡せるまでの時間は次の通り。

| 粒子数 | Bend CPU 画像準備 | Bend GPU 画像準備 | 手書きMetal 画像準備 |
|---:|---:|---:|---:|
| 10,000 | 0.793 | 0.947 | 0.466 |
| 100,000 | 5.083 | 2.166 | 1.182 |
| 1,000,000 | 39.661 | 18.958 | 10.450 |

100万粒子では、Bend GPUの更新GPU時間8.688 msに加え、共通の描画GPU時間も8.420 msある。
更新時間の改善は3.22倍でも、画像準備までの改善は約**2.09倍**となる。
NV12変換GPU時間は同条件で0.032 ms程度。CPUへのreadbackは省けているが、
大量のspriteを描く費用は残る。半径・重なり・解像度を変える追加実験では、この描画負荷も別に評価する。

反復ごとのmedianの範囲にも差がある。100万粒子＋追加計算の更新は
CPU 27.654〜32.873 ms、Bend GPU 8.460〜9.015 ms、手書きMetal 0.734〜1.904 ms。
画像準備はそれぞれ38.337〜41.882 / 17.528〜19.696 / 9.640〜12.312 ms。
既存のUIアプリを動かしたまま、他のbenchmark/buildを同時に開始せず測った。
計測前後にthermal/performance warningは記録されていない。

## この実験から得た設計上の目安

- **大きい配列を保持する。** 初期化後は同じ粒子データ本体を使い、毎フレームの再生成・copy・回収を避ける。
- **forkの粒度を測る。** 100万粒子＋追加計算のBend GPU更新は、1,024 jobsで42.238 ms、
  4,096 jobsで20.504 ms、16,384 jobsで8.985 ms。入力の粒子数だけではGPU性能を説明できない。
- **小さい更新はCPUも候補にする。** 1万粒子は軽い条件・追加計算ありともCPUが速かった。
  GPUへの呼出しを粒子ごとに行わず、更新全体で一度だけ行う。
- **描画を共通にして比較する。** 更新言語による差、GPU利用による差、共通rendererの費用を混ぜない。
- **読み出しと同期を区別する。** 読み出し0でも、Bend runtimeとadapterの完了待ちは残る。
  複数フレームの同時処理へ進むには、共有ヒープと画像resourceの所有権を別途設計する。

ここで示したのはこの同期版のMac実装。Rust/C CPU、WebGPU、他のGPU/OSとの同条件比較は未実施。
