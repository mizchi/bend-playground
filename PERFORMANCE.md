# Bend / Metal の費用と設計メモ

2026-10-02〜03、Apple M5 / 10 CPU cores / 10 GPU cores / 32 GiB、Bend 2.0.34 の実測から。
以下はこの処理系・マシン・入力で使う目安。普遍的な定数として扱わない。

## 覚えておく数値

| 費用 | 目安 | 何を測った値か |
|---|---:|---|
| 同期 C FFI | **追加 約20 ns / 呼出し** | 小さいスカラー処理の C direct 対照との差。大量反復の傾きから推定 |
| 微小 GPU 呼出し | **約0.28 ms / 同期1往復** | 8 / 32 / 128回の連続呼出し。Bend runtime・Metal submit・queue・完了待ちを含む |
| 微小 GPU の単発呼出し | **0.795 ms median** | 同じ小さい算術。一つだけ実行した場合は揺れが大きい |
| GPU 初回呼出し | **数百 ms を観測** | 最初の raw warmup。遅延初期化等の寄与は未分離。上の warm 値と分ける |
| 共有 buffer の CPU read | **0.53〜1.81 ms** | 4,096 Grid pages、6.19〜21.31 MiB の全有効座標、有限値検査と checksum。固定費ではない |
| CPU 内 memcpy | **0.15〜0.75 ms** | 8〜32 MiB、source は read 済み、destination は first-touch 済み。固定費ではない |

FFI は [計測記録](examples/ffi/README.md)、GPU の往復は [タスク境界の計測](examples/device/README.md)、
read / memcpy は [Grid の連続 buffer 実験](examples/grid/GPU-FLAT.md)を参照。
この Mac の host clock の分解能は1 µs。短い処理の0 nsを無料と解釈しない。

## タスクごとに CPU / GPU を選ぶ

通常の `f(...)` と `f!(...)` は同じ native binary に存在できる。
ただし GPU 呼出しが IO step の root に達するように段階を分ける。
CPU の parallel evaluation の中で bang を書くだけでは、そこを GPU に切り替えない場合がある。
固定版の [runtime](https://github.com/bendlang/bend/blob/7d24b8d0235cb9781140512c0f163c48ea84a719/bend2/comp.ts)
と [shader guide](https://github.com/bendlang/bend/blob/7d24b8d0235cb9781140512c0f163c48ea84a719/guide/SHADERS.md)で確認できる。

小さい task ごとに CPU → GPU → CPU と往復すると、計算より境界が高くなりやすい。
連続微小呼出しの目安では、100回の同期往復だけで **約28 ms**。これは測定値からの概算。
実用上は CPU の準備・制御を一つの段階にまとめ、独立した仕事の束を一度 GPU に渡す。
CPU 側で直後に結果が必要な小さい処理は、CPU で実行する方が有利になり得る。

同じ16,384 jobs × 4,096 rounds は、GPU を128回呼ぶと109.510 ms、1回なら1.898 ms。
後者は Bend CPU 10 の12.629 msより約6.65倍速い。
この差には GPU の稼働 lane 数と fork / join の変化も含み、すべてを切り替え固定費には帰属させない。

GPU submit、GPU execution、CPU wait、結果利用、回収を分けて測る。
CPU wait は GPU execution と重なるので足し算しない。
冷えた初回、連続実行、単発の値を混ぜない。実行順を変えた反復や sample の揺れも確認する。

## ゲームのように CPU へ結果を取り出さない経路

Metal では GPU が生成した buffer / texture を、次の GPU 処理に渡す経路を設計できる。
CPU が必要としない座標・粒子・画像を CPU の配列へ変換する費用を省ける。
描画まで GPU の resource のまま使い、CPU は scene、camera、入力などの小さい情報を渡す。

固定版の Mac `Window.frame` は、すでにこの方向の実装になっている。
[`window.c`](https://github.com/bendlang/bend/blob/7d24b8d0235cb9781140512c0f163c48ea84a719/bend2/effs/window.c#L359) の
`window_corpus` は Bend の `gpu_buf` を再利用し、`window_dev` の Metal kernel が Image を GPU 上で読み、
drawable の texture に書く。CPU が画像全体を取り出す処理はない。
ただし Image の木を読む処理は GPU 側に残る。raw buffer をそのまま fragment shader に渡す API と同じではない。

**readback を省いても同期は残る。**
`gpu_pass` は毎回 `waitUntilCompleted` を行い、`window_show` も表示用 command buffer の完了を待つ。
この呼出し経路では、CPU が次フレームを準備する前に GPU の完了を待つ。
表示用 texture へ直接書くことと、複数フレームを同時に処理できることは別の条件。

一般の Metal renderer で CPU/GPU を重ねるには、複数 buffer を使い、GPU 内の依存を queue / barrier で順序づけ、
CPU の待ちを buffer の再利用時などにまとめる。
Apple の [Triple Buffering](https://developer.apple.com/library/archive/documentation/3DDrawing/Conceptual/MTLBestPracticesGuide/TripleBuffering.html)
と [Command Buffers](https://developer.apple.com/library/archive/documentation/3DDrawing/Conceptual/MTLBestPracticesGuide/CommandBuffers.html)がこの設計を説明する。
これを Bend の共有ヒープと所有権に適用するには、非同期処理中の resource lifetime まで含む runtime / API の設計が必要。
今回、その変更や表示性能の再計測はしていない。

## 今回の Grid への当てはめ

出力木を返すと、取り出し27〜120 ms、回収36〜158 msという費用があった。
連続 buffer への直接出力では、全座標の read が0.53〜1.81 ms、回収は時計の分解能程度まで減った。
入力の意味を表す木と、実行・出力用の連続配列を分けることが効いた。

それでも、準備を除いた連続 buffer 版の計測区間は約99%以上が layout。
CPU read を省くだけでは、現在の Grid の GPU 計算が CPU を上回る根拠にならない。
ゲームでも分岐の多い配置・探索・scene準備と、大量の均一な pixel / tile 処理を分けて考える。
今回の xorshift は均一な独立計算では GPU が速くなる例で、ゲーム全体や手書き MSL shader と同等の性能を示すものではない。

## GPUIへの接続実験

[`examples/gpui/`](examples/gpui/README.md) にBendの共有配列をGPUIの画像surfaceへ接続するバインディングを実装した。
矩形は共有座標をMetalのvertex shaderが直接読み、画素はcompute shaderが直接読む。
NV12のIOSurfaceへGPU上で描画・変換し、CPUで出力配列を読み出す処理を省く。
出力配列はadapterのGPU完了後に回収し、GPUIは別の画像resourceを保持する。

M5 / 960×540では、CPUで一ページのGridを計算して画像を用意するまでのmedianが0.647 ms、
同じGridをBend Metalで計算すると12.815 msだった。
単純な画素生成もCPU 1.139 ms、Bend Metal 12.409 msで、この条件ではCPU計算とGPU描画の組合せが有利。
これらはGPUIへの画像準備時間で、GPUIの描画・presentや表示FPSの測定ではない。

この版でもBend GPUとadapter描画には同期完了待ちが残る。
readbackを省くことは実装できたが、計算のGPU適性やフレーム間の非同期化は引き続き別に評価する。

## 永続パーティクルでの比較

[`examples/particles/`](examples/particles/README.md)では、粒子の位置・速度・寿命・乱数状態を
同じ共有配列に保持してフレームごとに更新し、Metalのvertex shaderで直接描画する。
画像poolと中間textureも再利用する。Bend CPU、Bend GPU、手書きMetal computeを同じrendererへ接続した。

960×540、100万粒子、追加乱数計算64回の更新medianは
CPU **28.923 ms**、Bend GPU **8.985 ms**、手書きMetal **0.885 ms**。
画像準備までではそれぞれ**39.661 / 18.958 / 10.450 ms**だった。
各条件は順序を変えた3反復で、初回3フレームを除く7フレームのmedianを使った。
GPUはCPUに対し更新で約3.22倍、画像準備までで約2.09倍の改善を得たが、手書きMetalにはまだ差がある。

分割数による差も大きい。同じ100万粒子＋追加計算のBend GPU更新は、
1,024 jobsで42.238 ms、4,096 jobsで20.504 ms、16,384 jobsで8.985 ms。
CPUの最短は1,024 jobsだった。forkで分ければ速いというだけでなく、分割数を入力とbackendに合わせて測る必要がある。
1万粒子では追加計算ありでもCPU 0.516 ms、GPU 0.678 msでCPUが有利だった。

100万粒子のBend GPUでは、描画GPU時間も8.420 msを占める。
更新を速くしても、粒子の数・大きさ・重なりによる描画負荷は残る。
readbackを省くこと、永続配列にすること、十分な独立仕事を用意すること、描画負荷を抑えることを別々に評価する。
ここでもGPU完了待ちは残り、GPUIのpresentや表示FPSは測っていない。

## コンパイラを固定した粒子コードの改善

[`particles/OPTIMIZATION.md`](examples/particles/OPTIMIZATION.md)では、
粒子ごとのcallbackを静的な関数呼び出しにし、仕事内の反復を自己末尾再帰にした。
元の物理計算をimportするので、算法と計算量は同じ。Bend本体は変更していない。
生成コードの粒子ループと呼出し先から、ヒープ確保・クロージャ生成・動的callback呼び出しが消えた。

同じ計測内で、100万粒子＋追加乱数計算64回の更新は
CPU / 1,024 jobsが**23.885→11.962 ms**、GPU / 16,384 jobsが**6.762→1.481 ms**。
改善率はそれぞれ約2.00倍、4.57倍。画像準備までのGPU時間は13.554→7.930 msとなった。
前回と今回の絶対時間には変動があるため、改善率には今回同時に測ったA/Bを使う。

軽い100万粒子のCPU更新は10.819→0.596 msに改善し、GPU 1.183 msより速くなった。
CPU/GPUの選択やforkの粒度は、ソースの最適化後に測り直す必要がある。
旧版のコストをそのまま言語の性能上限とは考えない。

一方、新版GPUの更新は手書きMetalの0.653 msに対して約2.27倍、
GPU実行だけでも1.281 / 0.440 msで約2.91倍の時間がかかる。
汎用fork/workerの費用、直接kernelへ落とす経路、非同期resourceの所有権が次の候補。
原因別の寄与は未測定で、本体改善の効果は別checkoutでA/B/C/Dを比較して確認する。
また、新版の描画GPU時間は約6.22 msあり、以後は共通renderer側の改善も効く。

## C CPU対照から見た言語の費用

[`particles/CPU.md`](examples/particles/CPU.md)に、同じ共有状態・物理計算・分割数で
最適化後のBendとCを比較する実装と測定を追加した。
Cは初期準備でpthread poolを作って再利用し、worker起床・queue・完了待ちを含めて測る。
呼び出し元で同じC kernelを実行する逐次経路も用意した。Bend/Cでschedulerの実装は異なる。

100万粒子・追加計算64回・1,024 jobs・10 workersの更新medianは
Bend **12.275 ms**、C **12.159 ms**。1 workerでは**70.002 / 68.691 ms**だった。
反復の範囲は重なり、この差を性能優位とは断定しない。
今回の算術負荷が大きいCPU処理では、通常のCに近い実行時間まで改善できたと評価できる。

小さい軽い更新では差が残る。1万粒子・64 jobs・1 workerの更新は
Bend **0.105 ms**、C pool **0.015 ms**、C direct **0.011 ms**。
呼び出し・fork・handle・同期・配列アクセスを含む費用で、要因ごとの寄与はまだ分離していない。
この差をFFI一回やGPU起動の固定費に置き換えない。

また、分割を細かくしすぎるとCにも費用がある。
100万粒子の軽い更新・10 workersは、64 jobsでBend **0.848 / C 0.631 ms**、
16,384 jobsで**1.751 / 1.740 ms**だった。
言語だけでなく、計算量と仕事の粒度に合わせて並列化を選ぶ。
GPU側の残る差は、CPUの算術速度とは別にworker runtimeやメモリアクセスをprofilingして判断する。

## GPU runtimeと生成ループの対照

[`particles/GPU.md`](examples/particles/GPU.md)では、手書きMetalにも同じ連続仕事を与え、
Bendの生成ループをそのまま直接kernelから呼ぶ対照を作った。固定コンパイラは変更していない。
100万粒子・追加乱数64回・16,384 jobsのGPU実行medianは、
汎用Bend **1.291 ms**、直接leaf **0.821 ms**、Metal tiled **0.573 ms**。
52条件を3反復し、速度比較とencoder-boundaryカウンター診断は別processで実施した。

生成ループの直接kernel化は約1.57倍の改善で、独立配列更新の専用loweringが候補になる。
ただし生成ループ自体にもMetalとの差が残る。汎用kernelと専用kernelでは
仕事管理に加え、Metal compilerの最適化やthreadgroup resourceも変わるため、純粋なscheduler費用とは断定しない。
アプリ側では分割数とアドレス配置、本体側では非重複範囲を直接kernelへ落とす契約、
生成ループのGPU用型表現を分けて調べる。占有率・帯域・registerの寄与は未測定。

同条件の画像準備まででは8.163 → 7.706 ms。描画の費用が大きく、表示FPSは測っていない。

## Bend 本体のパッチ実験

[段階別の実験計画](compiler-patches/README.md)を追加した。
Step 1 は FFI が runtime segment の ID を参照できない問題を、別 checkout の compiler で修正した。
回帰テスト9件と既存40件が通り、FFIとflat粒子を含む4プログラムのC生成結果は固定版と一致した。
動作の修正であり速度改善は測っていない。

[Step 2](compiler-patches/step-02-known-callbacks/README.md)では、固定版の別 checkout に
既知 lambda の特殊化 pass を追加した。同じ `simulation.bend` から更新の closure segment が14→0になった。
M5・100万粒子・乱数64回・同じ jobs で、CPU/10 workers は **25.768→11.866 ms**、
Metal の完了待ち込み更新は **6.845→1.739 ms**、GPU 本体は **6.5278→1.3744 ms**。
画像準備全体は **14.144→8.615 ms**で、表示FPSは測っていない。

9回帰テスト、既存40テスト、上流12例の48実行、粒子288フレームを検証した。
flat 版の生成 C は旧版と byte 単位で一致し、その計測の揺れを対照にした。
共有MacのCPU負荷は残るため小さい差は性能改善としない。
試作の `comp.ts` は65,994 ttokで上流の64,000上限を超える。提出には簡素化と最新mainへの移植が必要。
ソース側とcompiler側は同じcallbackのコストを削るので、それぞれの改善倍率を掛け合わせない。
