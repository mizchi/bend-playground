# Bend CSS Grid layout engine

CSS Grid の配置とトラックサイズ計算を Bend 内で実行する実用サブセット。
固定サイズのダッシュボード、span を使うカード一覧、入れ子のウィジェットを対象にする。
JSON を正規化する Python フロントエンド、Bend エンジン、同じ計算を行う C 比較実装、
Playwright による実ブラウザとの照合、CPU ベンチマークを含む。

## 実行

リポジトリ直下から実行する。Bend は `just setup` で取得した固定コミットを使う。

```sh
just grid examples/grid/fixtures/dashboard.json --output build/grid/dashboard.json
just grid examples/grid/fixtures/catalog.json --backend c
just grid-demo
# build/grid/demo.html をブラウザで開く。外部サーバーは不要。

just test
just setup-grid-browser
just check-grid
just bench-grid
just check-grid-gpu
just bench-grid-gpu
just check-grid-gpu-flat
just bench-grid-gpu-flat
```

ブラウザ検証には Node.js 24+ と pnpm が必要。
依存関係は `browser/package.json` と lockfile に固定し、既存のルート package.json に依存させない。
`build/` に生成するソース、バイナリ、ビューアーはコミットしない。

独立ページの Metal バッチと、全矩形の CPU 側での取り出し時間は [GPU.md](GPU.md) に記録する。
GPU が共有連続バッファへ直接出力し、CPU が読む版は [GPU-FLAT.md](GPU-FLAT.md) に記録する。
GPU 実測には Metal と clang 19+ が必要。CPU / browser の検証は GPU を要求しない。

## 入出力と対応範囲

```json
{
  "id": "page",
  "width": 800,
  "height": 600,
  "grid": {
    "columns": "160px repeat(2, minmax(80px, 1fr))",
    "rows": "64px 1fr",
    "auto_rows": "90px",
    "gap": 12,
    "dense": true
  },
  "children": [
    { "id": "sidebar", "column": 1, "row": 1, "span_row": 2 },
    { "id": "header", "column": 2, "row": 1, "span_column": 2 },
    { "id": "card" }
  ]
}
```

出力は `{ "boxes": { "id": [x, y, width, height] }, "errors": 0 }`。
座標はルートの content box 左上からの絶対 CSS px。root 自身の矩形も含む。
子の `grid` と `children` で入れ子を指定でき、サイズは親の grid area から受け取る。

| 項目 | 対応 |
|---|---|
| トラック | 非負の `px` / `fr`、`minmax(px, px)` / `minmax(px, fr)`、整数回の `repeat()` |
| 配置 | 正の開始 line と span、両軸の明示配置、行のみ・列のみの固定、自動配置 |
| 自動配置 | row / row dense、末尾の implicit rows / columns |
| implicit サイズ | `auto_rows` / `auto_columns` に上と同じ単一トラック指定 |
| gap | `gap` / `column_gap` / `row_gap`、数値は CSS px |
| 方向・整列 | horizontal LTR、content は start、grid items は stretch |
| 数値 | F32、有限の非負値、入力 dimension は最大 1,000,000 |
| 容量 | 32 列、128 行、256 直接子、木全体 2,048 nodes、深さ 8 |

root の幅・高さは必須。`column` / `row` は 1 始まりで、0 / 省略は auto。
span の既定値は 1。columns の既定値は `1fr`、rows は空、implicit row は `64px`、
implicit column は `0px`。id は木全体で一意にする。

この API の item は `min-width: 0; min-height: 0`、margin / border / padding なし。
文字・画像を測らず、裸の `fr` の content-based minimum は 0 として扱う。
そのため、ブラウザ側でも同じ minimum を明示して比較する。
内容の intrinsic sizing、`auto` / `min-content` / `max-content`、auto-fit / auto-fill、
percentage、名前付き line / area、負の line、RTL、subgrid、baseline、任意の item alignment は未対応。
未知のプロパティや未対応構文はフロントエンドでエラーにする。
容量不足は `errors > 0` として返し、CLI は有効なレイアウトとして出力しない。

## エンジン

[`contract.bend`](contract.bend) は正規化済み入力と矩形・出力木の契約。
[`placement.bend`](placement.bend) は明示配置 → 行固定 → 残りの自動配置を行う。
各 Grid が occupancy の row bitmask、行固定 cursor、配置結果の `Array` を所有する。
行固定の sparse cursor は開始 row ごとに持つ。span で覆う他の row の cursor は更新しない。

[`tracks.bend`](tracks.bend) は最小サイズを初期化し、有限の上限まで余白を均等分配し、
`fr` を解決する。最小値を下回る flexible track は固定して配分を再計算する。
flex factor 合計が 1 未満なら分母を 1 にし、要求されなかった余白を残す。
gap を除いた空間を使い、overflow しても最小値を縮めない。
これらは CSS Grid 1 の[配置アルゴリズム](https://www.w3.org/TR/css-grid-1/#auto-placement-algo)と
[トラック最大化・fr 解決](https://www.w3.org/TR/css-grid-1/#algo-maximize)の対応部分に沿う。

[`layout.bend`](layout.bend) は親の配置とサイズを確定して子の job を作る。
子部分木と後続の兄弟は独立なので `a b = ... ...` で fork する。
mutable workspace を共有せず、正規化済み入力は reusable Data、作業配列は affine Type とする。
再帰の fuel は入力ノード数の上限より大きくし、配置探索の fuel は capacity 内の全候補を覆う。
配置・トラック計算で foreign code や `@unsafe` は使わない。
共有連続バッファの GPU 実験では、ページごとに範囲を分けた出力配列の共有に `@unsafe` を使う。

## 正しさ

手計算の `fr` 配分、有限上限、gap / span / dense、行固定 cursor の退行例、
配列容量超過、benchmark の全ノード数・checksum を native tests で検証する。
TDD の最初は parser / native geometry tests が失敗することを確認し、その後両実装を通した。

実アプリ例を 480 / 1024 / 1440 px で比較し、ゼロ幅・overflow・明示的 overlap・implicit track・
乱数 seed `20261002` の 80 ケースも加える。C と Bend 1 / 10 threads は 103 ケースで一致。
Playwright は各 DOM の `getBoundingClientRect()` を独立オラクルとして使う。
ブラウザのトラック丸めが累積するため許容差は 0.25 CSS px。
F32 同士の C / Bend 比較は 0.002 px 以下とする。

Firefox 155.0 は 103 ケースで一致。Chromium 153.0.8010.12 は 102 ケースで一致。
通常ケースの最大差は Firefox 0.142457 px、Chromium 0.015625 px。
合計 2,064 矩形を各ブラウザで照合した。記録は [`results/browser-verification.json`](results/browser-verification.json)。

Chromium の `random-29` は dense の row-span 配置が Firefox / Bend / C と異なる。
同じ入力で Chromium は 10 行、Firefox / Bend / C は 9 行になる。
ブラウザ間のこの差は expected failure として明示しており、ブラウザ完全互換を主張しない。
[`fixtures/chromium-dense-variance.json`](fixtures/chromium-dense-variance.json) に、子を削って差が残る再現入力を保存した。
セルを順に探索する CSS Grid 1 §8.5 と Firefox の結果を現在の契約とする。
Playwright がこの差を検出しなくなった場合は expected failure のテストが失敗し、再調査が必要になる。

## CPU 性能

Apple M5（4P + 6E、32 GiB）/ Bend 2.0.34 / clang 21、CPU only。2026-10-02 の実測。

逐次 relayout の回帰から推定した 1 ページ当たりの時間。起動時間の切片と傾きは別に推定する。

| ページ | nodes | C 1 thread | Bend 1 thread | Bend 10 threads |
|---|---:|---:|---:|---:|
| dashboard | 99 | 1.12 µs | 28.43 µs | 139.60 µs |
| catalog | 121 | 8.97 µs | 325.36 µs | 706.13 µs |
| nested | 341 | 4.08 µs | 111.11 µs | 209.31 µs |

独立した 65,536 ページの batch。時間は 3 回の median、プロセス起動を含む。

| ページ | C 1 | C 10 | Bend 1 | Bend 10 | Bend の並列倍率 |
|---|---:|---:|---:|---:|---:|
| dashboard | 0.073s | 0.015s | 1.803s | 0.398s | 4.53x |
| catalog | 0.592s | 0.103s | 21.586s | 4.529s | 4.77x |
| nested | 0.284s | 0.055s | 7.516s | 1.700s | 4.42x |

**この実装では、小さい Grid の低レイテンシ計算に Bend の並列化は効いていない。**
Bend 1 thread は C 1 thread の約 25〜36 倍の時間がかかり、ページ内だけを 10 threads にするとさらに遅くなる。
独立ページをまとめると Bend は 4.42〜4.77 倍に伸びるが、C の同じ 10 threads より 27〜44 倍遅い。
配置のカーソル更新と占有判定は逐次で、各 Grid のサイズ確定を子が待つ。小さな仕事では fork の費用を回収しにくい。
immutable list、job、出力 tree の確保と操作も C の連続配列より多い。この違いが負担になっている可能性はあるが、
割り当ての寄与を分離した測定はしていない。今回の結果だけで言語一般の性能差にはできない。
Bend 1 thread の単一ページは約 0.028〜0.325 ms で、指定サイズのレイアウト単体は 16.7 ms のフレーム予算内に収まる。
DOM / 内容計測 / paint を含む UI 全体や、任意サイズのページが同じ予算に収まることは未検証。

回帰の R² は全条件 0.99991 以上。切片は OS scheduling / clock noise のため負になる場合があり、
実際の起動コストとして解釈しない。CPU の thermal / performance warning は前後とも記録されなかった。

入力 JSON の解析・正規化とコンパイルは測定外。正規化した tree は一度作って共有し、
各レイアウトで幅を `base + index % 97` に変えて再計算する。
配置探索、両軸のサイズ計算、入れ子、矩形の作成、メモリ確保と回収、全矩形の checksum が測定に入る。
checksum は座標を 1/16 px に量子化した U32 の加算。正しさ検証は checksum だけに依存せず、全矩形を比較する。

latency は 1 / 2,048 / 16,384 回の逐次 relayout を各 3 回実行し、median に対して
`T(N) = startup + N * cost` を回帰する。ページ間の並列化をせず、ページ内の fork の効果を測る。
batch は 8,192 / 65,536 個の独立ページを C 1 / 10 threads、Bend 1 / 10 threads で測る。
C は pthread のページ queue を使い、1 ページ内は逐次。Bend はページと兄弟部分木の両方を fork する。
したがって latency の C と Bend 10 threads はスケジューラ構成まで同一ではない。

C は入力を const の木、作業領域と出力を連続配列で表現する。
Bend は線形配列と immutable list / output tree を使う。
計算する Grid アルゴリズムと矩形は同じだが、割り当て回数・データ表現は同一ではない。
比率はこの実装の比較であり、言語一般の下限性能やブラウザ全体の描画性能ではない。
CSS parse、DOM、フォント、paint、GPU、FFI の性能はこの結果に含めない。

計測は Apple M5 / macOS、CPU only、直列。起動済み UI アプリはそのまま。
同時に他のビルド・テスト・ベンチマークを起動していない。
ソース SHA-256、実際の Bend コミット、環境、各 3 サンプル、RSS、回帰係数と R² を
[`results/macos-m5-grid.json`](results/macos-m5-grid.json) に記録する。
