# GPUの分割方法とruntime段階の診断

CPU対照の次に、flat版Bend GPUと手書きMetalの差を調べる実験を追加した。
固定Bend 2.0.34、コミット`7d24b8d0235cb9781140512c0f163c48ea84a719`を使い、
upstreamは変更していない。結果は[`results-macos-m5-gpu.json`](results-macos-m5-gpu.json)。
旧[A/B](OPTIMIZATION.md)・[C CPU](CPU.md)の結果は保存し、今回との絶対時間の差を改善率に使わない。

**同じBend生成ループを直接kernelから呼ぶと速くなった**。
100万粒子・追加計算64回・16,384 jobsのGPU実行は、汎用Bend 1.291 ms、
直接leaf 0.821 ms、同じ範囲を処理する手書きMetal 0.573 msだった。
独立配列更新の専用loweringは有望だが、leafにもMetalとの差が残る。
この実験だけでは、register・帯域・coherentアクセス・Natループ等の寄与を確定できない。

## 通常測定の結果

2026-10-03、Apple M5 / CPU 10 cores / GPU 10 cores / 32 GiB、macOS 26.6.2。
960×540、半径2 pixels。以下は**カウンター無効時のGPU実行時間**、単位ms。
同じ行では粒子数・演算回数・jobsを合わせている。

| 粒子数 | 追加乱数 | jobs | 汎用Bend | Bend leaf | Metal tiled | Metal strided |
|---:|---:|---:|---:|---:|---:|---:|
| 100,000 | 0 | 1,024 | 0.297 | 0.044 | 0.030 | 0.034 |
| 100,000 | 0 | 16,384 | 0.405 | 0.029 | 0.029 | 0.026 |
| 100,000 | 64 | 1,024 | 1.113 | 0.315 | 0.150 | 0.154 |
| 100,000 | 64 | 16,384 | 0.460 | 0.084 | 0.047 | 0.043 |
| 1,000,000 | 0 | 1,024 | 1.631 | 0.737 | 0.675 | 0.547 |
| 1,000,000 | 0 | 4,096 | 0.989 | 0.584 | 0.551 | 0.474 |
| 1,000,000 | 0 | 16,384 | 0.999 | 0.548 | 0.528 | 0.453 |
| 1,000,000 | 64 | 1,024 | 9.498 | 3.283 | 1.687 | 1.633 |
| 1,000,000 | 64 | 4,096 | 2.819 | 0.936 | 0.608 | 0.542 |
| 1,000,000 | 64 | 16,384 | 1.291 | 0.821 | 0.573 | 0.491 |

100万粒子・追加乱数64回・16,384 jobsの3反復median範囲は、
汎用Bend 1.279〜1.312、leaf 0.819〜0.823、Metal tiled 0.568〜0.596 ms。
汎用Bend → leafは約1.57倍、GPU時間を約36%短縮した。
lightのleaf / tiledは反復範囲が重なる条件もある。小さい差を性能優位と断定しない。

参考として、1粒子1 threadのMetalは100万粒子・追加乱数64回で0.438 ms。
この版はjobsを使わず、1,024 jobsなどの行と同じ仕事粒度ではない。
少ない仕事の長い逐次ループは手書きMetalでも遅い。
一方、jobsを合わせたtiledでもBendとの差があるので、分割数だけで全部は説明できない。

100万粒子・追加乱数64回・16,384 jobsの更新経過時間は、
汎用Bend 1.551 / leaf 1.045 / tiled 0.800 / strided 0.702 ms。
GPU実行より約0.2〜0.3 ms大きいが、これはCPU側準備・queue・待ちの復帰等を含む経過時間差。
純粋なkernel launch固定費やFFI一回の費用ではない。
画像準備までのmedianは8.163 / 7.706 / 7.449 / 7.338 ms。
共通描画が大きいため、更新の改善率を表示FPSの改善率に置き換えない。

Metal tiled → stridedは100万粒子・追加乱数64回・16,384 jobsで0.573 → 0.491 ms。
隣接laneが隣接粒子を読む配置は、今回の大きい配列では改善した。
10万粒子・1,024 jobsではstridedが常に有利ではない。
cache missや実際の帯域を測っていないので、アドレス配置だけでなく反復数と負荷の分布も含む対照として扱う。
今回、Bendソースの分割をstridedへ変更する実装はしていない。

## 段階診断から分かったこと

次の値は**encoderを分けた診断実行**のmedianで、通常測定の内訳ではない。単位ms。
100万粒子・追加乱数64回を示す。

| jobs | grow_single | grow_all | drain | pack |
|---:|---:|---:|---:|---:|
| 1,024 | 0.063 | 9.332 | 0.059 | 0.007 |
| 4,096 | 0.062 | 2.724 | 0.077 | 0.007 |
| 16,384 | 0.064 | 0.199 | 1.016 | 0.008 |

仕事が少ない条件では計算の大部分がgrow_allで実行され、十分に分けるとdrainへ移る。
runtime段階の名前だけでは、算術を実行している場所は決まらない。
今回の診断ではbank整理は小さく、優先して高速化する対象には見えない。
生成ループを直接呼ぶ対照から、汎用kernelの仕事実行経路を外す改善余地を確認できた。
ただし専用kernel化はMetal compilerの最適化やthreadgroup resourceも変えるので、
0.470 msという時間差を特定の仕事管理命令の費用には割り当てない。

## アプリとコンパイラの次の対象

| 対象 | 今回の証拠 | 次の実験 |
|---|---|---|
| アプリの分割数 | 同じ算術でもjobsで大きく変わる。手書きMetalでも同様 | 入力規模と負荷別に粒度を選ぶ |
| アプリのアドレス配置 | 大きい配列ではMetal stridedがtiledより速かった | Bendにもstrided版を作り、同じjobsで比較する |
| コンパイラの独立配列更新lowering | 生成したleafを直接kernelへ落とすとGPU時間が短縮した | 非重複範囲と所有権を契約化し、別checkoutで汎用runtimeを経由しない経路を作る |
| 生成ループとGPU用型表現 | 重い更新はleafにもtiledとの1.43〜1.95倍の差が残った | shader profilerで命令・register・メモリを見てから、Nat / U32反復、scalar化、coherentアクセスの対象を絞る |
| bank整理 | この条件の診断では約7〜8 µs | ここを主要因として先に書き換える根拠はない |

全52条件 × 3反復、156 process / 2,496 raw frames / 1,716 measured frames。
別途、208フレームの全規模検証と832フレームの段階診断を保存した。
既存UIアプリは起動したまま、ほかのbench/buildを同時に開始せず測定。
前後のthermal/performance warningは記録されていない。

## 比較する実装

物理計算・初期状態・配列レイアウト・描画・同期境界は共通。
Metalの3版は同じ`particle_advance`を呼び、追加乱数更新はruntime引数0 / 64。
安全な浮動小数点設定を使い、式の順序や演算回数を減らしていない。

| mapping | 仕事の割り当て | group内のthreads | 更新kernel |
|---|---|---:|---|
| bend | forkでjobs個に分け、各仕事が連続した粒子範囲を反復 | 128 | 汎用Bend runtime |
| leaf | Bendが生成した`spin_16`を直接呼び、同じ連続範囲を反復 | 128 | 追加した実験用kernel |
| particle | 粒子ごとに1 thread | 64 | 手書きMetal |
| tiled | jobs個のthread、各threadがBendと同じ連続範囲を反復 | 128 | 手書きMetal |
| strided | jobs個のthread、`job, job+jobs, …`を反復 | 128 | 手書きMetal |

tiledの範囲は`chunk=ceil(count/jobs)`、`[min(job*chunk,count), min(start+chunk,count))`。
stridedはすべての粒子をちょうど1回更新し、隣接threadは各反復で隣接粒子を読む。
countがjobsより小さい場合も未使用容量を書かない。予約2語は保持する。

これは粒子ごとに1 threadのMetalと、粗い連続仕事のBendという違いを調べる対照。
tiledとBendの仕事範囲は同じだが、schedulerや総dispatch数は同じではない。
Bendは128 groups × 128 lanesのbagを使い、native tiledはjobs / 128 groupsを直接dispatchする。
共有配列は同じpayload形式でも、Bendの参照管理・runtime heap・`coherent(device)`アクセスは
nativeの`device Particle*`と異なる。tiledとBendの時間差を、純粋なscheduler費用と断定しない。

leafは[`gpu-leaf.metal`](gpu-leaf.metal)から**Bendの生成関数をそのまま呼ぶ**対照。
手書きの物理計算に置き換えず、算術・配列アクセス・`coherent(device)`を維持し、
`fork / work_loop / ring / Array.join / bank_pack`を通さない。
共有Bend heapの同じ配列handleを引数に渡し、未使用のallocation欄は参照しない。
生成コードの粒子ループが固定版の`spin_16`で、推移的な呼出し先を含めて
ヒープ確保・クロージャ生成・動的applyが0であることをビルド時に確認する。
この性質が崩れたら実験を停止する。

これは独立配列更新を直接kernelへ落とす案の対照実装で、Bend本体の改善版ではない。
メモリ範囲の非重複性とhandleの所有権をアプリが保証している。
`spin_16`は固定版固有の内部関数なので、一般用途の公開APIや通常のbackendとして提供しない。
結果JSONの`mapping=leaf`がこの対照を識別する。生フレームの`backend=metal`は
nativeの直接Metal dispatch経路を示し、物理計算を手書きMetalに置き換えた意味ではない。
汎用kernelと専用kernelでは、Metal compilerのinliningやregister割当も変わりうる。
leafとの差も、仕事管理命令だけを除いた正確な費用とは解釈しない。

## 通常の速度測定と段階診断を分ける

**通常測定**ではカウンターをサンプリングしない。Bendのdispatch構成とbarrierを維持し、
command bufferの`GPUStartTime` / `GPUEndTime`でGPU実行時間を記録する。
CPUの更新経過時間・完了待ち・描画・NV12変換も、従来と同じ契約で記録する。
GPU時間とCPU待ちは重なるため加算しない。GPUIのpresentや表示FPSは含まない。

**段階診断**は別processで実行する。M5の`MTLDevice.counterSets`は
`timestamp / GPUTimestamp`のみで、stage boundaryは対応、dispatch boundaryは未対応だった。
そのためBendの4 dispatchをそれぞれ別compute encoderにし、encoderの前後にtimestampを取る。

| 段階 | pass | groups | 役割 |
|---|---:|---:|---|
| grow_single | 0 | 1 | frontierを最初のgroupで展開 |
| grow_all | 0 | 128 | 全groupsへ仕事を広げる |
| drain | 1 | 128 | 各laneのringにある仕事を実行 |
| pack | 2 | 1 | allocatorのbankを整理 |

この粒子callbackはfrontierが1から始まり、固定runtimeで4段階を通る。
growも汎用`work_loop`を呼ぶので、展開だけでなくアプリの計算を含みうる。
「growの時間＝純粋なfork費用」「drainの時間＝純粋な算術」とは扱わない。

Bendのheapは`MTLResourceHazardTrackingModeUntracked`。
encoderを分けただけでは既存のencoder内barrierの依存を維持できず、
最初の検証で`frontier drained without a result`になった。
診断版は各encoder末尾で`updateFence`、次の先頭で`waitForFence`を使い、
CPUでの中間待ちは追加していない。すべての段階は同じcommand buffer内で実行する。
通常版の同期を変更したわけではなく、encoder分割による依存を補う処理である。

stage timestampは`sampleTimestamps`をGPU処理の前後で採取し、
`(cpu_after-cpu_before)/(gpu_after-gpu_before)`でCPU nanosecondsへ換算する。
生timestampと校正値も保存する。resolveとJSON出力は診断版だけで行う。
**encoder分割・fence・カウンターは計測対象を変える**ため、
診断の段階時間を通常測定から引いて、改善可能な費用と解釈しない。

実装は[`gpu-profile.h`](gpu-profile.h)と[`particles_gpu.py`](../../scripts/particles_gpu.py)。
generated scratch Cのhost側に診断処理を追加し、device側にはleaf kernelだけを追加する。
既存のBend device関数・汎用kernelとupstreamは維持する。
固定版は`#embed __FILE__`で生成ファイル全体を`BEND_SRC`に含めるため、
埋め込む文字列のバイト列は変わる。host側の診断branchはMetalの条件コンパイルで除外される。
固定版の置換anchorが一致しなければビルドを止める。
通常ビルドにはこの診断コードを組み込まない。

## 測定の再現

```sh
just check-particles-gpu
just bench-particles-gpu

# 条件を絞った再測定。保存済みの全結果を上書きしない。
just bench-particles-gpu --count 1000000 --noise-rounds 64 --jobs 16384 --output build/particles/gpu-small.json
```

10万 / 100万粒子、追加乱数0 / 64、1,024 / 4,096 / 16,384 jobs。
particleの仕事数は粒子数なので、各count / noiseで一度だけ測る。計52条件。
全ビルド後、52条件の全粒子をそれぞれ4フレーム検証し、段階診断も済ませてから、
通常測定を直列で行う。最初5フレームを除き、次の11フレームのmedianを採用。
順序をshuffleした3反復のmedianと反復の範囲、生フレーム、環境とsource/generated SHA256を保存する。
独立Python/C oracleによる検証読み取りは測定用processでは行わない。
カウンターの読み取りは粒子のreadbackとは別で、通常測定では両方とも行わない。

`just check-particles-gpu`は1 / 17 / 10,003粒子、追加乱数0 / 64、5 mappingsについて、
診断あり・なしの4連続フレーム、計240フレームを検証する。
粒子状態は独立Python float32 oracleと照合し、診断の有無ではバイト単位で一致する。
全NV12画素は最大2/255の差を許容。予約語・capacity canary・同一buffer・GPU dispatchも検証する。

GPU検証4テスト、既存粒子5テスト、GPUIのRust ABI 1＋Python 3テスト、
`just test`の既存40テストは通過した。ウィンドウの目視・クリック操作は今回の対象に含めていない。

## 取得していない情報

pipeline metadataでは、M5のSIMD幅は32、Bendの動的threadgroup memoryは18,432 bytesだった。
両pipelineの`maxTotalThreadsPerThreadgroup`は1,024、静的threadgroup memoryは0。
これらは実際の占有率・register数・帯域・cache missを測るカウンターではない。
現時点では、低occupancyや帯域不足を原因として確定しない。

Appleの説明では占有率や帯域の診断にはInstruments / Metal debuggerのshader profilingを使う。
今回の公開timestamp APIでの診断とは別の測定になる。
[GPU occupancy](https://developer.apple.com/documentation/xcode/finding-your-metal-apps-gpu-occupancy)、
[GPU performance](https://developer.apple.com/documentation/xcode/optimizing-gpu-performance)。
timestampの校正とencoder boundaryの扱いは、
[clock conversion](https://developer.apple.com/documentation/metal/converting-gpu-timestamps-into-cpu-time)、
[counter sampling](https://developer.apple.com/documentation/metal/sampling-gpu-data-into-counter-sample-buffers)に従う。
