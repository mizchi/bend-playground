# Grid の共有連続バッファ出力

GPU が全矩形を連続領域に書き、CPU が同じ領域を直接読む実験。
[出力木を返す版](GPU.md) と同じ配置・トラック計算を使い、出力表現を変えて取り出し費用を分離する。

```sh
just check-grid-gpu-flat
just bench-grid-gpu-flat
# 4,096 ページだけ再計測する場合
just bench-grid-gpu-flat --depth 12 --output build/grid/gpu-flat-repeat.json
```

## 出力契約と実装

[`gpu-flat.bend`](gpu-flat.bend) は `FlatOutput{buffer: Array<F32>, errors: U32}` を返す。
一つの `Array<F32>` に全ページの x / y / width / height を保存する。
page と node id は配列位置から決まり、座標だけなら **16 bytes / rectangle**。
各ページの stride は `4 * nodes` 以上の最小の 2 の累乗で、残りは padding。
dashboard / catalog は 512 floats、nested は 2,048 floats / page を確保する。

出力 Tree を作らず、明示的な pending-list stack を使って入力を歩く。
レイアウトは元の `layout.prepare` を呼び、各ノードの矩形を確定した時点で四つの値を書き込む。
ページ間を binary fork し、ページ内の出力走査は逐次とする。

出力配列の共有と `Array.join` に `@unsafe` を使う。
ページ p は `[p*stride, (p+1)*stride)` だけを書き、正規化済み node id はページ内で一意。
並列書き込みの範囲は交差しない。fork が完了してから handle を join し、CPU に一つの所有権を渡す。
通常の配置・トラック計算は変更せず、upstream の compiler / runtime も編集しない。

[`gpu-flat-probe.bend`](gpu-flat-probe.bend) の `start` が CPU 上で runtime の packed buffer を確保し、
NaN で初期化する。これは計算開始前に行い、`prepare_ns` に別記する。
その直後の IO step の root に `batch!(...)` を置き、Metal dispatch を確実に起こす。
GPU が全有効セルを上書きするので、書き忘れは CPU の有限値検査で失敗する。
FFI はバッファ準備、計測、結果検査を担当し、矩形計算は Bend が行う。

## 測定範囲

Apple M5 の同じ環境で C、出力木の Bend CPU / Metal、連続バッファの Bend CPU / Metal を直列に動かす。
入力は一度だけ作り、各回の width を `base + (round*pages + index) % 97` に変える。
コンパイル、GPU 初期化、JSON 解析、ログ、dump 保存は時間に含めない。
同じプロセスで 2 warmups + 5 samples。生の全 sample と median を保存する。

| フィールド | 測定範囲 |
|---|---|
| `prepare_ns` | 共有配列の確保・NaN 初期化、host 検査用 storage の確保、memcpy destination の first-touch |
| `layout_ns` | GPU/CPU 呼び出しから、全矩形入りの FlatOutput が CPU に戻るまで |
| `view_ns` | ABI・buffer class・error の検査と、共有配列の pointer 取得。全座標を読まない |
| `read_ns` | pointer から全有効座標を直接読み、有限値を検査し、同じ整数 checksum を計算する最初の pass |
| `read_again_ns` | 同じ領域を同じ処理で再度読む pass |
| `copy_ns` | 全 buffer を CPU の別領域へ memcpy。padding も含む。destination は準備時に first-touch 済み |
| `copy_read_ns` | memcpy 先を同じ検査・checksum 処理で読む pass |
| `materialize_ns` | 共有配列から従来の 24-byte 矩形形式を作り、件数・id・有限値を検査する pass |
| `checksum_ns` | 24-byte 形式を同じ checksum で読む pass |
| `drop_ns` | FlatOutput と配列 handle の回収 |

順序は **view → 最初の read → 再 read → memcpy → コピー先 read → 24-byte 変換 → checksum → drop**。
再 read、memcpy、変換は最初の read によって source が読まれた後なので、cold-cache のコピー帯域とは呼ばない。
hash 関数の compiler barrier と noinline 指定で各 read pass の省略を防ぐ。
checksum は座標の読み込みだけでなく、有限値検査・量子化・整数演算を含む。
`read_ns` は純粋なメモリ帯域を測る指標ではない。

`direct_end_to_end_ns` は同一 sample の `layout + view + read + drop` の median。
再 read・memcpy・変換は比較用の追加 pass なので、この合計には含めない。
`direct_with_prepare_ns` は buffer 準備も足した合計。
この prepare には optional memcpy の検査用 allocation も入るため、直接利用だけの最小実装費用ではない。
drop 自体は追加 pass 後に測るので、この合計も追加 pass を外して実行した wall-clock 測定ではない。

Metal は元の `MTLResourceStorageModeShared` / `newBufferWithBytesNoCopy` を使う。
GPU → CPU の明示的な転送 API は呼ばない。view の後はコピーせずに同じ pointer を読める。
任意の `copy_ns` は CPU 内で独立バッファが必要な場合の memcpy であり、Metal の転送ではない。
GPU 実行時間と完了待ちは重なるため、足さない。

この Mac の `clock_getres(CLOCK_MONOTONIC)` は **1,000 ns**。
view / drop の median に記録された 0 ns は時計の分解能以下を意味し、処理が無料だと示さない。

## 結果

2026-10-02、Apple M5 / CPU 10 cores / GPU 10 cores、Bend 2.0.34。
同じ run で両出力表現を再計測した。4,096 ページ、各 stage の median、単位 ms。

| ページ | 有効座標 / 確保 buffer | 出力木 → 24-byte 矩形 | 共有 buffer の最初の read | CPU memcpy | 共有 buffer → 24-byte 矩形 |
|---|---:|---:|---:|---:|---:|
| dashboard / 99 nodes | 6.19 / 8 MiB | 27.458 | **0.525** | 0.152 | 0.809 |
| catalog / 121 nodes | 7.56 / 8 MiB | 30.192 | **0.576** | 0.159 | 0.757 |
| nested / 341 nodes | 21.31 / 32 MiB | 119.803 | **1.814** | 0.746 | 2.349 |

共有 buffer の直接 read は 0.53〜1.81 ms。出力木の取り出しは 27〜120 ms。
これは結果表現と処理内容を変えた比較であり、Metal 自体の転送速度が 50 倍になったという意味ではない。
前者は 16-byte 座標をその場で検査・checksum 計算し、後者は木を歩いて 24-byte 矩形を作る。
従来と同じ矩形形式が必要な場合でも、連続配列からの変換は 0.76〜2.35 ms だった。
この変換は追加の read / memcpy pass 後の測定である。

同じ buffer を Bend CPU 10 が生成した時の最初の read は **0.560 / 0.684 / 2.686 ms**。
GPU が書いた buffer の CPU read と同じ桁に収まる。
Metal shared storage の読み取りに、従来の木構造の取り出しに相当する大きな費用は観測しなかった。
連続 buffer の drop は今回の時計の分解能程度で、出力木の drop は **36.450 / 41.950 / 158.161 ms**。
配置計算以外にも、出力木の走査と回収がかなりの費用を占めていた。

計算時間と、全座標を直接利用する経路の合計も比較する。単位 ms。

| ページ | 出力木 GPU layout | 連続 buffer GPU layout | 連続 buffer CPU 10 layout | 出力木 GPU 全段階 | 連続 buffer GPU 直接利用 | 準備込み GPU 直接利用 |
|---|---:|---:|---:|---:|---:|---:|
| dashboard | 61.399 | 54.741 | 24.574 | 125.651 | 55.249 | 55.845 |
| catalog | 649.546 | 602.227 | 257.442 | 728.914 | 602.803 | 603.356 |
| nested | 221.882 | 185.566 | 133.622 | 503.411 | 187.268 | 189.958 |

直接利用と準備込みは上記 stage 合計の median。個別 median を足した値ではない。
出力木の構築・取り出し・回収を省くと合計は改善するが、**レイアウト計算自体は CPU 10 の方が速い**。
GPU の方が Grid に適するという結論にはならなかった。
この改善は元の Grid 実装の出力表現・共有配列の書き方の変更によるもので、言語全体の一般的な性能比ではない。

1 / 512 / 4,096 ページ × 三つの workload × 六つの mode、**54 条件・378 raw samples** が成功。
両出力表現、C、CPU、GPU の全 sample の件数・checksum が一致する。
既存の UI アプリが起動した状態で直列に測定した。CPU scheduling や cache による sample 差は生データに残す。
OS の thermal / performance warning は計測前後とも記録されなかった。
catalog 16,384 ページを含む、それより大きな batch は今回の連続 buffer 実験では測っていない。

## 検証

`just check-grid-gpu-flat` は shape / 不正 profile の契約と、全矩形の比較を行う。
dashboard、span / dense の catalog、nested、空 Grid、flex minimum / fractional flex / gap の五つの入力で、
4 ページ × 3 rounds の checksum が C と一致する。
最後の round の全座標を C と Bend CPU 1 / 4、Metal で 0.002 px 以下まで照合する。
GPU fallback は command count / device execution time が 0 なら失敗する。
共有・再 read・memcpy 先・24-byte 出力の checksum はすべて一致を要求する。

生データは [results/macos-m5-grid-gpu-flat.json](results/macos-m5-grid-gpu-flat.json)。
使用した Bend commit、実行環境、使用ソースと生成ソースの SHA-256、失敗条件を記録する。
