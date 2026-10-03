# Step 2: 既知 callback の特殊化

固定版 `7d24b8d0235cb9781140512c0f163c48ea84a719`（Bend 2.0.34）の
`comp.ts` に、C/Metal 生成前の特殊化 pass を試作した。
`upstream/bend` と言語実装 `bend.ts` は変更しない。
Step 1 の FFI 修正とは独立したパッチで、上流 PR はまだ作成していない。

## What / Why

元の粒子ソース `simulation.bend` は、配列の所有権を callback で受け渡す。
`read(buffer, base, a => particle => ...)` のように呼び出し先と callback が
ソースから分かる場合も、固定版は callback を実行時の closure にする。
更新処理には14個の closure segment があり、capture の heap 確保と動的適用が発生する。

試作 pass は、既知の lambda を埋め込んだ関数を生成する。
callback の capture は通常の先頭引数に移し、関数引数から callback 自体を取り除く。
たとえば `apply(x, y => U32.add(y, bias))` は、概念的には
`apply_specialized(bias, x)` になる。埋め込んだ lambda の適用も解決する。
値の式を渡す場合は `let` で一度評価してから使い、線形な配列 handle を受け渡す。

コンパイラが読む book のコピーを変換するため、呼び出し元の book、JS 生成、
インタプリタの入力には影響しない。特殊化した定義は既存の emitter と所有権解析に渡す。
粒子の callback/flat 両ソース、物理計算、配列レイアウト、renderer は変更していない。

## 実験の範囲

- fully applied な関数に直接渡した lambda を対象とする。型が閉じており、
  capture の native layout に `box` が含まれない場合だけ特殊化する。
- 動的な関数、関数・配列などを capture する lambda、foreign/bang 呼び出し、
  直接自己再帰する呼び出し先には既存の経路を使う。
- 最大64個の特殊化定義と、元の定義ごとに8,192 node の変換予算を設ける。
  予算を超えた部分は元の経路で実行する。
- callback の形による特殊化の共有、既知の関数参照、相互再帰の自己ループ化、
  JS の特殊化はこのパッチに含めていない。

これは性能を確かめるための試作で、上流へ提出できる状態には達していない。
`gates/repo.ts` は **48/49** で、`comp.ts` の **65,994 ttok > 64,000** が失敗理由。
固定版は63,765 ttok。上限は変更していない。
PR 化するには、既存処理との統合・簡素化でコード量を減らし、特殊化の契約を追加検証する必要がある。

## 再現

```sh
just setup-bend-step02
just check-bend-step02
just check-bend-step02-upstream
BEND_REPO="$PWD/upstream/bend" just check-bend-step02
just check-bend-step02-upstream
BEND_REPO="$PWD/build/bend-steps/step-02/bend" just test

# ビルド・検証を完了してから、直列に計測する。
just bench-bend-step02

# フェーズを分ける場合も、対応する build/verify を先に行う。
just bench-bend-step02 --phase build
just bench-bend-step02 --phase verify
just bench-bend-step02 --phase bench
```

[`compiler.patch`](compiler.patch) を別 checkout に適用する。
準備は繰り返し可能で、既存の競合する編集を reset しない。
ベンチマークはビルド時の compiler hash と生成 C の hash を照合し、
計測する構成の検証記録がなければ停止する。

## 検証

最小例では、固定版でも値は `42` だが5個の closure segment が残るため Red。
修正版では0個になり、C（1/4 workers）、JS、インタプリタの値が一致した。
9テストは、scalar capture、tuple の match、線形配列の受け渡し、動的・boxed・再帰の fallback、
64定義の上限、依存する等式の型の fallback、book の非変更と再コンパイルの再現性、flat 粒子の C が byte 単位で一致することを検証する。
固定版は9件中1件失敗、修正版は9件成功。既存の `just test` 40件も成功した。

上流の12例は interpreter / JS / C（1/4 workers）の48実行で期待出力と一致した。
closure の所有権、closure chain、保存した反復ごとの capture、相互再帰、配列 map・split/join・
boxed element・index wrap などを含む。cluster gate、CUDA、Lean の検証は未実施。
TypeScript の確認では、固定版から存在する `bend.ts` の2エラーが残るが、`comp.ts` の追加エラーはない。

16個の粒子バイナリをビルドし、72構成・288フレームを検証した。
`count=1/17/10003` は独立した Python float32 oracle と粒子全フィールドを比較し、
seed/padding は完全一致、浮動小数点は2e-6以内。NV12 画像も旧版と2/255以内で一致した。
計測する100万粒子は、計測とは別のプロセスで全粒子を native oracle と比較した。
実際の Metal dispatch、永続 buffer、state allocation 1回、計測フレームの readback 0 bytes を確認している。

## 生成コード

| ソース | 固定版 | 修正版 |
| --- | ---: | ---: |
| callback 版の更新に属する closure segment | 14 | 0 |
| callback 版の live closure segment 全体 | 16 | 2 |
| flat 版の live closure segment 全体 | 2 | 2 |

残る2個は UI/IO の callback。flat 版の C は旧版と byte 単位で一致する。
callback 版の `tile → tile_step → ... → tile` という再帰構造は残り、
flat 版と同じ `spin` の自己ループにはなっていない。

計測結果は [`results-macos-m5.json`](results-macos-m5.json) に、
検証・環境・ソース hash は [`validation-macos-m5.json`](validation-macos-m5.json) に保存する。

## M5 の計測結果

100万粒子、CPU は1,024 jobs、Metal は16,384 jobs。旧版・修正版で jobs を揃えた。
各構成は5 warmup＋25 measured frames、独立プロセスで3回反復し、run の中央値の中央値を採用した。
全24構成を固定 seed で並べ替え、72回を直列に実行した。GPU の更新時間は完了待ちを含む。

| 追加乱数回数 | 更新先 | 固定版 ms | 修正版 ms | 倍率 | 固定版の run 中央値範囲 | 修正版の範囲 |
| --- | --- | ---: | ---: | ---: | --- | --- |
| 0 | CPU / 1 worker | 63.269 | 2.687 | 23.54× | 62.825–63.390 | 2.685–2.689 |
| 0 | CPU / 10 workers | 11.025 | 0.824 | 13.38× | 10.781–11.375 | 0.771–0.942 |
| 0 | Metal / wait 込み | 6.213 | 1.224 | 5.08× | 6.172–6.271 | 1.211–1.470 |
| 64 | CPU / 1 worker | 161.520 | 70.253 | 2.30× | 160.746–161.846 | 70.055–70.297 |
| 64 | CPU / 10 workers | 25.768 | 11.866 | 2.17× | 24.757–26.684 | 11.752–12.289 |
| 64 | Metal / wait 込み | 6.845 | 1.739 | 3.94× | 6.834–7.170 | 1.734–1.761 |

乱数64回の Metal GPU 本体は **6.5278 → 1.3744 ms**。
同じ構成の画像準備全体は **14.144 → 8.615 ms**。
GPU duration と CPU の wait は重なるため足し合わせない。GPUI の present・表示 FPS は測定していない。

対照の flat 版は生成 C が同じなのに、CPU/10 workers の軽い更新は0.736 → 0.655 ms、
乱数64回の Metal の wait 込み更新は1.732 → 1.576 ms と揺れた。
一方、後者の GPU 本体は1.3082 → 1.3202 msでほぼ同じ。
flat 版の小さい差をコンパイラの改善として扱わない。通常の UI アプリが動く共有 Mac で、
計測前後の CPU idle は約71%/77%。CPU/Metal の細かい差や他機種の倍率は追加測定が必要。

callback 版の大きな改善は3回すべてで再現した。重い更新は、ソース側で callback を手で除いた
flat 版に近づく。軽い CPU 更新では、修正版 callback の1 workerが2.687 ms、flat が1.832 ms、
10 workersが0.824 ms、flat が0.655 msで、再帰構造などの違いがまだ残る。

既知 lambda の特殊化を compiler に入れる効果は確認できた。次は既存の展開処理との統合で
コード量と重複を減らし、最新上流 main に移植する。その後に Step 3 の型付き helper 戻り値を比較する。
粒子ソースの改善と compiler の改善は同じコストを削るため、両者の倍率を掛け合わせない。
