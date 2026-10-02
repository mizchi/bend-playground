# Bendコードの改善とコンパイラ本体の改善を分ける

今回の粒子更新は、**コンパイラを変えずに大幅に改善できた**。
100万粒子・追加乱数更新64回・16,384 jobsのBend GPU更新は、
同じ計測内で6.762 msから1.481 msへ改善した。約4.57倍速い。
旧実装の測定を、そのままBendコンパイラの性能上限と見ることはできない。

ただし、新版にも手書きMetalとの差は残る。GPU更新の経過時間は
Bend 1.481 msに対してMetal 0.653 ms、GPU実行時間だけでも1.281 / 0.440 msだった。
この差のすべてをコンパイラに帰属させるだけのprofilingは、まだ行っていない。

## 比較条件と変えたもの

| 条件 | A: callback | B: flat |
|---|---|---|
| 粒子更新 | [`simulation.bend`](simulation.bend) | [`simulation-flat.bend`](simulation-flat.bend) |
| コンパイラ | 固定Bend 2.0.34 | 同じ固定版 |
| 物理計算 | 元の関数 | Aのrespawn / integrate / writeを直接利用 |
| 読み出し | 6個のArray.getをcallbackでつなぐ | 静的に決まる関数呼び出しでつなぐ |
| 仕事内の反復 | tile → callback → tileの再帰 | 正確な範囲長による自己末尾再帰 |
| 並列分割・状態・描画 | fork、共有配列、共通Metal renderer | 同じ方式 |

コンパイラは`7d24b8d0235cb9781140512c0f163c48ea84a719`。upstreamは編集していない。
Aのソースは前回の測定時と同じSHA256で、Bはその物理計算をimportする。
乱数更新の回数や浮動小数点演算を減らす変更はしていない。
両方のforkで、粒子配列のhandleは非重複の範囲だけに共有する。

Bでは各仕事の開始位置と終了位置をcount以下に収め、その差を反復回数にする。
粒子数より仕事の数が多い場合は、空の仕事が0回で終わる。
この形にすると、既存コンパイラが粒子更新をネイティブループへまとめられる。

新しいC接続コードはA/Bで共通。`FID(Clo~apply)`の解決失敗を避けるため、
生成される`FID_CLO_APPLY`マクロを直接使う。後述のFFIの問題の回避であり、
粒子更新を手書きC/Metalに差し替える処理ではない。

## 生成コードで確認できたこと

Aでは粒子を読み出すためのクロージャ処理が14種類生成される。
読み出し途中でcapture用のヒープを確保し、動的なClo.applyへ渡す。
respawnの戻り値をParticleとして一度ヒープに置き、次のcallbackで展開する経路もある。

Bではtileが`spin_16`という自己末尾再帰のネイティブループになった。
そのループと、そこから呼ぶ14個の補助spin関数をたどると、
`heap_alloc`、`term_clo`、`FID_CLO_APPLY`の出現はそれぞれ**0**だった。
Particleも6個のスカラーとして受け渡され、粒子ごとのヒープへの格納を省けている。

これは生成Cの静的な検査結果。実行時のallocation数やMetal機械語の測定ではない。
forkの仕事管理、配列handleの参照管理、フレーム単位のcallbackには、引き続きruntimeの処理がある。
`state_allocations=1`も、粒子配列本体についての契約値である。

検査は[`particles.py`](../../scripts/particles.py)の`codegen_report`で行い、
ループと呼出し先を含む結果を各測定ケースの`codegen`に保存する。
`just check-particles`でも、Bの粒子ループに上記の処理が戻っていないことを確認する。
`spin_16`などの名前は固定版の出力に固有で、公開APIではない。

## 同じ分割数でのA/B結果

2026-10-03、M5 / CPU 10 cores / GPU 10 cores / 32 GiB、macOS 26.6.2。
960×540、100万粒子、半径2 pixels。値はms。
CPUは1,024 jobs、GPUは16,384 jobsで、各行のA/Bは同じ分割数。

| 追加乱数更新 | backend | jobs | A 更新 | B 更新 | A/B |
|---:|---|---:|---:|---:|---:|
| 0 | Bend CPU | 1,024 | 10.819 | 0.596 | 18.15倍 |
| 0 | Bend GPU | 16,384 | 6.039 | 1.183 | 5.10倍 |
| 64 | Bend CPU | 1,024 | 23.885 | 11.962 | 2.00倍 |
| 64 | Bend GPU | 16,384 | 6.762 | 1.481 | 4.57倍 |

CPU/GPUの有利不利も変わった。軽い更新では、旧版はGPUの方が速かったが、
新版はCPU 0.596 ms、GPU 1.183 msでCPUが速い。
追加計算64回では、新版のGPUがCPUに対して約8.08倍速い。
「このアルゴリズムならGPU」と決める前に、実行時の表現と制御の費用を減らして比較する必要がある。

追加計算64回のフレームについて、画像準備までの時間は次の通り。

| backend | A 画像準備 | B 画像準備 |
|---|---:|---:|
| Bend CPU / 1,024 jobs | 30.483 | 18.849 |
| Bend GPU / 16,384 jobs | 13.554 | 7.930 |
| 手書きMetal | 7.108 | 共通の対照実装 |

手書きMetalの更新は0.653 ms。同じ対照実装を一度だけ測っている。
Bend GPUの更新が4.57倍改善しても、画像準備まででは約1.71倍になる。
新版の描画GPU時間が6.222 ms程度あるため、以降はspriteの重なり・粒子サイズ・描画方法も改善対象になる。
描画の改善はこのBendコンパイラのA/B実験と分ける。
画像準備にはGPUIのscene / presentを含まないので、表示FPSではない。

3反復の更新medianの範囲は、追加計算64回のCPUで
A 23.790〜24.832 / B 10.749〜16.766 ms、GPUで
A 6.725〜6.766 / B 1.454〜1.486 msだった。特にCPU版には変動がある。
前回の結果と今回の結果は別の測定なので、改善率には今回同時に測ったA/Bだけを使う。

## 分割数は最適化後に測り直す

新版のBend GPU更新時間は次の通り。

| 粒子数 | 追加乱数更新 | 1,024 jobs | 4,096 jobs | 16,384 jobs |
|---:|---:|---:|---:|---:|
| 100,000 | 0 | 0.456 | 0.509 | 0.656 |
| 100,000 | 64 | 1.343 | 0.715 | 0.698 |
| 1,000,000 | 0 | 1.794 | 1.177 | 1.183 |
| 1,000,000 | 64 | 9.636 | 3.061 | 1.481 |

元のGPU実装では大きい粒子数に16,384 jobsが有利だった。
新版の軽い10万粒子では、1,024 jobsの方が速い。
また、100万粒子・追加計算64回の新版CPUは4,096 jobsで11.161 msとなり、
1,024 jobsの11.962 msを少し下回った。ただしこの差の確実性は反復の変動も考慮する。
同じ分割数でのコード改善と、分割数の選択による改善を合算して説明しない。

CLIのデフォルトは比較元のcallback版と従来の分割数を維持している。
新版は`--variant flat`で選び、分割数は`--jobs`で明示できる。
この実験から任意の入力に対する自動schedulerを導いたわけではない。

## 本体側の改善対象をどう判断するか

| 対象 | 今回わかったこと | 次に調べる場所・方針 |
|---|---|---|
| ローカルcallbackの特殊化 | アプリ側で静的な呼び出しに変えると費用が消えた | `comp.ts`の`flat_of`、`emit_unfold`、`emit_body`。既知のcalleeとcaptureを持つ呼び出しを特殊化し、Aの書き方でもB相当へ落とせるか |
| レコードのスカラー化 | BのParticleは既存コンパイラで展開される | 「Recordが常に遅い」とは言えない。動的callbackをまたぐ場合に、同じ展開を維持できるかを先に調べる |
| 独立配列更新のGPU lowering | 粒子ループの確保を消しても、GPU実行はMetalの約2.91倍 | 汎用のfork / worker処理を調べる。非重複範囲を表すAPI・型と、直接GPU kernelへ落とす経路は候補。occupancyや参照管理の寄与は未測定 |
| GPU完了待ち | Bでもruntimeの`gpu_pass`が毎回待つ | completionとbuffer所有権を表すAPI、描画queueとの依存、複数フレームのresource lifetime。adapter側も合わせて設計する |
| FFIのruntime関数ID | Bend側から動的呼び出しが消えると、effect Cの`FID(Clo~apply)`が解決に失敗した | runtime用IDをeffect読込みより前に登録する、または専用host callback APIを用意する。本体の正しさの問題で、速度改善とは別 |

非同期化しても、今回のGPU実行1.281 msをそのまま消せるわけではない。
完了待ちを減らす目的はCPUの次の準備とGPU処理を重ねること。
共有配列を更新し直す時点、描画が読む時点、GPUIが画像を保持する期間を揃える必要がある。
本体の待ちだけを削除する変更ではこの契約を満たせない。

FFIの失敗は、固定版`comp.ts`の`compile_book`が`compile_reqs`でeffect Cを読む時点より後に、
`Clo~apply`のsegmentを登録するため起きる。
Aでは粒子のcallback生成でIDが先に登録されていたが、Bではその副作用に依存できなくなった。
今回のadapterはマクロを直接参照して回避した。本体修正は行っていない。

## 次の比較で守ること

| 比較 | アプリのコード | コンパイラ | 状態 |
|---|---|---|---|
| A | 元のcallback版 | 固定版 | 今回再計測 |
| B | flat版 | 固定版 | 今回実装・計測 |
| C | 元のcallback版 | 改善版 | 未実施 |
| D | flat版 | 改善版 | 未実施 |

本体の変更は別checkoutを`BEND_REPO`で指定して実験する。固定submoduleは変更しない。
まず既知のcallbackの特殊化でAをどこまでBに近づけられるかを測る。
その後、Bにも残るGPU実行の差を、専用loweringやruntimeの変更で測る。
アプリの改善と本体の改善が同じ費用を消す場合、A→BとA→Cの改善率は足さない。
Dを測って、組み合わせたときの効果を確認する。

## 検証と再現

```sh
# 新旧の状態・全NV12画素・生成コードを検証する。
just check-particles

# A/B × CPU/GPU × 3粒子数 × 2追加負荷 × 3分割数、Metal対照6条件。
# 78条件を3反復。元のresults-macos-m5.jsonは上書きしない。
just bench-particles-code

# 範囲を絞った比較。
just bench-particles-code --count 1000000 --noise-rounds 64 --output build/particles/compare.json

# 新版を実際のGPUIウィンドウで動かす。
just particles --variant flat --backend bend-gpu --count 1000000 --noise-rounds 64 --jobs 16384
```

`just check-particles`では1 / 17 / 10,003粒子、追加負荷0 / 64、
Aの3 backendとBのCPU/GPU、連続4フレーム、計120フレームを照合する。
位置・速度・寿命の絶対誤差は2e-6以内、乱数状態と予約語は完全一致。
独立Python計算と画像oracle、A/B間の全NV12画素の比較を行う（8-bit画素は最大2/255を許容）。
未使用容量のcanary、同じ配列アドレス、readback 0、実際のGPU commandも確認する。

benchmark前には78条件の全粒子を別processで4フレーム検証する。
計測はビルド・検証後に直列で実施し、各processの最初3フレームを除く7フレームを採用する。
実行順をshuffleした3反復のmedianを保存する。
234 process / 2,340 raw frames / 1,638 measured frames、反復範囲、
環境・commit・source/generated SHA256・生成コード検査は
[`results-macos-m5-code.json`](results-macos-m5-code.json)に記録した。
通常の計測フレームでは検証による読み取りを行わない。

`just test`の既存40テストも通過した。
新版のGPU版は100万粒子・追加負荷64・実ウィンドウでも3フレームを照合し、自動終了を確認した。
ウィンドウの見た目やPause/Resumeのクリック操作は、今回の検証には含めていない。

既存UIアプリは起動したまま、ほかのbenchmark/buildを同時に開始せず測定した。
計測前後にthermal/performance warningは記録されていない。
