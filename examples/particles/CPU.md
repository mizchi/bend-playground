# 最適化後のBend CPUとC CPUを比較する

この測定は[GPU profiling対照](GPU.md)を追加する前の記録。
source SHA256は計測時のソースを表し、後続のMetal helper・native adapter変更で再計測した値ではない。

算術負荷が大きい今回の粒子更新では、**最適化後のBend CPUは通常のC実装に近い時間で動いた**。
100万粒子・追加乱数更新64回・1,024 jobs・10 workersの更新medianは
Bend **12.275 ms**、C **12.159 ms**。差は約1%で、反復の範囲も重なる。
この測定から両者の優劣を確定することはできない。

軽い更新や小さい入力には差が残った。
1万粒子・追加計算なし・64 jobs・1 workerではBend 0.105 ms、C pool 0.015 ms、
呼び出し元のC逐次ループは0.011 msだった。
計算量に加えて、呼び出し・配列handle・fork・同期・ループ内の検査を含む費用が効く条件として評価する。
各要因の寄与はまだ分離していない。

## 対照実装と契約

| backend | 更新の実装 | 実行する場所 |
|---|---|---|
| `bend-cpu --variant flat` | [`simulation-flat.bend`](simulation-flat.bend) | 固定Bendのworker runtime |
| `c-cpu` | [`cpu.c`](cpu.c) | 起動時に作るpthread pool |
| `c-direct` | 同じC kernel | 呼び出し元の1スレッド |

CPUの共有状態と[`cpu.h`](cpu.h)のAPIを分離した。
[`state.h`](state.h)は8個のfloat、32 bytesというCPU/Metal ABIを定義する。
乱数状態は24-bit整数を正確に表すfloatで、更新される状態フィールドは有限値であることを前提とする。
予約2語は変更しない。粒子数・仕事数・乱数回数とpointerの引数はAPIで検査する。
同じpoolへの更新・破棄は所有者が直列に行い、更新が返るまで状態をほかの処理へ渡さない。

Cの物理計算は検証用`oracle.h`を呼ばず、別実装の関数で更新する。
独立Python計算による検証も行う。初期状態は全backendで同じものを使用する。
renderer・画像pool・共有配列・固定dt・seed・float演算の順序も揃える。
通常経路でCPUへ描画用の配列を取り出す処理は行わない。
CPUによるシミュレーションの読み書きは、描画用readbackと区別する。

Cのpoolは次の性質を持つ。

- workerの確保・起動は初期準備に含め、更新時間の外に置く。毎フレームのthread作成はしない。
- atomicな仕事番号を取り、`ceil(count/jobs)`個ずつの連続範囲を更新する。Bendの葉と同じ範囲分割。
- 粒子数より仕事数が多い場合、空の仕事は配列を触らず終了する。
- 更新内にmalloc/freeはない。呼び出し元は全workerの完了を待ってから描画する。
- 最後にstopを通知し、joinしてpoolを解放する。

`c-direct`も同じ範囲を同じC関数で更新し、workerの起床・atomic queue・完了待ちを省く。
**同じ仕事数でもschedulerの実装は異なる**。Bendはforkやhandleの管理を含み、
Cはatomic queueを用いる。両者の時間差を全て算術コードの性能差とは呼ばない。

`threads`は設定したworker数で、呼び出し元は含まない。
Bendは最初の評価を呼び出し元で行う場合もある。C poolの呼び出し元はworkerを待ち、
`c-direct`は呼び出し元だけで実行する。`c-direct --threads`は1だけを受け付ける。
既存のMetal/Bend GPU backendにもスレッド数を記録するが、それはGPU thread数ではない。

## コンパイル条件

Bend 2.0.34 / `7d24b8d0235cb9781140512c0f163c48ea84a719`を固定し、upstreamは変更していない。
CPU側は両方Apple clang 21、`-O3 -ffp-contract=off`。
手動SIMD、SoA、fast-math、CPU affinityは追加していない。Cの通常のcompiler最適化は有効。

C kernelは別translation unitの`cpu.o`としてコンパイルし、LTOを使わない。
count / jobs / roundsはruntime引数なので、Cだけ0回・64回の専用関数に展開しない。
実際に8種類のBend buildの`cpu.o`が同じSHA256だったことも確認した。
これらの条件はCやBendの性能上限を示すものではなく、今回の対照実験の条件である。

## 同じ分割数・worker数での結果

2026-10-03、M5 / CPU 10 cores / GPU 10 cores / 32 GiB、macOS 26.6.2。
960×540、半径2 pixels、固定dt=1/60。以下は更新のCPU経過時間、単位ms。
表のBend/Cは経過時間の比で、1に近いほど同じ時間になる。

| 粒子数 | 追加乱数更新 | jobs | workers | Bend flat | C pool | Bend/C |
|---:|---:|---:|---:|---:|---:|---:|
| 10,000 | 0 | 64 | 1 | 0.105 | 0.015 | 7.00 |
| 10,000 | 0 | 64 | 10 | 0.124 | 0.052 | 2.38 |
| 1,000,000 | 0 | 1,024 | 1 | 2.160 | 1.587 | 1.36 |
| 1,000,000 | 0 | 1,024 | 10 | 0.947 | 0.753 | 1.26 |
| 1,000,000 | 64 | 1,024 | 1 | 70.002 | 68.691 | 1.02 |
| 1,000,000 | 64 | 1,024 | 10 | 12.275 | 12.159 | 1.01 |

100万粒子・追加計算64回の3反復の更新median範囲は、
1 workerでBend 69.585〜70.048 / C 66.968〜73.740 ms、
10 workersでBend 11.448〜12.632 / C 12.133〜12.425 ms。
100万粒子の軽い更新・10 workersはBend 0.582〜0.990 / C 0.695〜0.938 msだった。
medianだけで小さい差を性能優位と判断しない。

1,024 jobsの1 worker→10 workersの更新改善は、
軽い100万粒子でBend約2.28倍 / C約2.11倍、追加計算64回で約5.70倍 / 約5.65倍。
workerを増やした効果も、計算量によって違う。
CPUの種類・memory traffic・schedulerを個別に計測した結果ではない。

## C逐次ループと仕事管理の費用

次は64 jobsの軽い更新。

| 粒子数 | C direct / 1 thread | C pool / 1 worker | C pool / 10 workers | Bend / 1 worker | Bend / 10 workers |
|---:|---:|---:|---:|---:|---:|
| 10,000 | 0.011 | 0.015 | 0.052 | 0.105 | 0.124 |
| 100,000 | 0.104 | 0.111 | 0.076 | 0.252 | 0.212 |
| 1,000,000 | 1.203 | 1.542 | 0.631 | 2.161 | 0.848 |

小さい軽い更新ではCもworkerを使うと遅くなった。
10 workersを設定した軽い1万粒子のCでは、非空の仕事を処理したworker数が1〜8だった。
仕事が短いと、全workerが処理を始める前に終わる場合がある。
設定数と実際に仕事を処理した数は別に記録する。

追加計算64回の100万粒子・1,024 jobsでは、
C direct 68.827 ms、C pool / 1 worker 68.691 ms、Bend / 1 worker 70.002 ms。
10 workersのCは全測定フレームで10 workerが非空の範囲を処理していた。
この大きい計算では起床・完了待ちの費用が相対的に小さくなり、並列化が効く。
これは今回のpool実装での観測で、汎用のworker起床時間の定数ではない。

## 分割しすぎる費用はCにもある

100万粒子・10 workersの更新時間。

| jobs | 軽い更新 Bend | 軽い更新 C | 追加計算64 Bend | 追加計算64 C |
|---:|---:|---:|---:|---:|
| 64 | 0.848 | 0.631 | 13.183 | 12.688 |
| 1,024 | 0.947 | 0.753 | 12.275 | 12.159 |
| 4,096 | 0.963 | 0.926 | 12.907 | 12.315 |
| 16,384 | 1.751 | 1.740 | 14.094 | 12.446 |

細かい分割はBendだけでなくCのatomic queueでも費用が増える。
今回の軽い条件では64 jobsが速く、計算が多い場合は1,024 jobsが有利だった。
反復の変動を含む値なので、任意の入力に対する最適なscheduler規則にはしていない。

描画は共通だが、既存UIアプリの動作などによる変動がある。
例えば追加計算64回・100万粒子・10 workers / 1,024 jobsの画像準備medianは
Bend 24.174 / C 23.396 msだった。共通の描画GPU時間もBend 10.073 / C 8.668 msと変動する。
更新言語の評価には分離した`update_ns`を使い、画像準備だけの小さい差を言語の優劣にしない。
GPUIのscene / present / input latencyは引き続き計測外で、表示FPSではない。

## 検証と再現

```sh
just check-particles
just check-gpui
just test

# pthread poolの競合検査。C kernel単体なのでMetal/GPUIを起動しない。
BEND_PARTICLE_C_SANITIZER=thread python3 tests/particles.py ParticleTest.test_c_workers_reuse_pool_across_counts_grains_and_rounds

# 120条件、順序を変えた3反復。過去のA/B測定を上書きしない。
just bench-particles-cpu

# 比較を絞る例。
just bench-particles-cpu --count 1000000 --noise-rounds 64 --jobs 1024 --output build/particles/cpu-small.json

# Cから同じ共有配列を更新し、GPUIで描画する。
just particles --backend c-cpu --count 1000000 --noise-rounds 64 --jobs 1024 --threads 10
just particles --backend c-direct --count 10000 --jobs 64
```

独立Python oracleによるC単体テストは、同じpoolでcount / jobs / roundsを12回変更する。
未更新の範囲と非ゼロの予約語が残ること、全状態、APIの無効引数、shutdownを確認する。
1 / 4 workersとC directで検証し、ThreadSanitizerでもデータ競合は検出されなかった。

`just check-particles`は5テスト。state・画像照合は追加したCの2経路も含めて168フレーム。
浮動小数点の状態は絶対誤差2e-6以内、seed・予約語は完全一致、NV12の画素差は最大2/255。
全容量のcanary、固定したbufferアドレス、実際のCPU/GPU経路を検査する。
GPUIのRust/Python 4テスト、既存の`just test` 40テストも通過した。
C poolは実GPUIウィンドウでも100万粒子・追加計算64回を3フレーム照合して自動終了を確認した。
見た目やクリック操作の検証は含めていない。

本計測は3粒子数 × 2追加負荷 × 4分割数 ×
（BendとC poolの1 / 10 workers、C directの1 thread）、計120条件。
各条件を先に別processで4フレーム検証し、その後ビルドやほかのbenchmarkを同時に実行せず直列に測る。
最初5フレームを除いた11フレームのmedianを取り、順序をshuffleした3反復のmedianを採用する。
360計測process / 5,760 raw frames / 3,960 measured frames。

source / generated / C object SHA256、commit・環境・schedulerの違い、全sampleと反復範囲は
[`results-macos-m5-cpu.json`](results-macos-m5-cpu.json)に保存する。
`c_completed_jobs`は実際に処理した仕事数、`c_workers_used`は非空の範囲を処理したworker数。
更新の検証と状態読み取りは別processで行い、計測フレームには含めない。
`state_prepare_ns`にはC poolの準備も含むが、`frame_ready_ns`の外に置いている。
既存UIアプリは起動したままで、計測前後にthermal/performance warningは記録されていない。

## この結果から次に調べるもの

今回の算術負荷が大きい条件では、CPU全般の計算性能が大幅に遅いという根拠は得られなかった。
軽い更新のBend側の費用は、host callback・fork・handle管理・配列アクセスを個別に測る候補になる。
今回の差だけで「FFI一回が90µs」「fork一回が何ns」とは決めない。

GPU側の差は別に調べる。[前回のA/B比較](OPTIMIZATION.md)では、
確保を除いた後もBendのGPU実行1.281 msに対して手書きMetalは0.440 msだった。
CPUの算術性能が今回Cに近かったことは、GPU側のworker処理やメモリアクセスを調べる優先度を上げる材料になる。
GPUの原因を確定する証拠ではなく、次のprofiling対象を選ぶ判断である。
