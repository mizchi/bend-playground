# The C compiler specializes calls with a known callback

main `5a0b523f`（Bend 2.0.35）を基準に、Apple M5/macOSでローカル検証しました。

## What Bend should do

既知のcallbackを渡す呼び出しを特殊化し、通常の関数型を保ったままclosureの確保と動的適用を省きます。

```python
def apply(x: U32, callback: U32 -> U32) -> U32:
  callback(x)

def run(+bias: U32, x: U32) -> U32:
  a = apply(x, y => U32.add(y, bias))
  apply(a, y => U32.add(y, bias))
```

## Why

[GPUI](https://gpui.rs/)のBendバインディングを作り、Bendが計算したパーティクルの状態をCPUに読み戻さず描画へ接続するところから始まりました。線形配列を要素の読み取りへ渡していく小さなcallbackがボトルネックになりました。生成された更新処理には14個のclosure segmentがあり、callbackを明示的な引数に書き換えると大きく速くなりました。

この変更では、対応する呼び出しについてcallbackのAPIを保ったままコンパイラがそのコストを省きます。CPUとGPUは同じC生成処理を使います。同じBendのパーティクルソースで、更新処理のclosure segmentは14個から0個へ減り、UI/IOの2個は残ります。

Apple M5で100万粒子を更新し、main `947db722`とfork `b59588e2`を比較した結果です。追従後の生成Cもbyte一致します。

| 更新 | 基準版 | 最適化版 | 比率 |
| --- | ---: | ---: | ---: |
| CPU・1スレッド | 160.881 ms | 69.830 ms | 2.30× |
| CPU・10スレッド | 24.472 ms | 12.108 ms | 2.02× |
| Metal・完了待ち込み | 8.653 ms | 1.625 ms | 5.32× |

GPUIは利用例です。このPRは一般的なコンパイラを変更します。アプリケーション側は[再利用できるBend/GPUIライブラリ](https://github.com/mizchi/bend-playground/blob/6c21544c51228c88e5ff1559236231a0b88727f7/packages/bend-gpui/README.en.md)、[最小のBendアプリケーション](https://github.com/mizchi/bend-playground/blob/6c21544c51228c88e5ff1559236231a0b88727f7/examples/gpui/minimal.bend)、[粒子の描画例](https://github.com/mizchi/bend-playground/tree/6c21544c51228c88e5ff1559236231a0b88727f7/examples/particles)として公開します。[計測リファレンス実装](https://github.com/mizchi/bend-playground/tree/09fc6e6/compiler-patches/step-02-known-callbacks/refactored)は測定時の版に固定しています。

## Change

2コミットで構成します。先に型・import・コメントの表記を整理して生成結果を保ち、続くコミットで特殊化（compilerは69行追加・15行削除）と回帰例2ファイルを追加します。`comp.ts`は63,956 ttokで、64,000の上限を保ちます。

完全適用された通常の定義に、boxedなcaptureを含まないliteral lambdaが1個渡された場合が対象です。既存のfusionと引数束縛を再利用し、型付きlambdaとconstructor pattern、呼び出し元のcaptureの生存期間を保ちます。ANFによる作り直しや予算切れをまたいで採否をcacheします。

動的callback・boxed capture・複数lambda・foreign/bang呼び出しは従来の処理を使います。calleeに直接の自己参照や並列束縛がある場合は除外します。非tailの展開では、非flatな呼び出しと並列束縛を含むcallbackも除きます。予算切れではclosureへ戻ります。

foreign effectがcallbackを呼ぶときのC生成を修正する#1286とは別の変更です。最初のコミットは、openの#1281とコード量削減という目的を共有しますが、表記とコメントだけの変更です。

## Verification

main `5a0b523f`にこの変更を加えて確認しました。

- `gates/repo.ts`: 49/49。
- callbackの13契約が成功。captureの再使用、線形配列、dependentな型、非flatな呼び出し、fallback、繰り返しコンパイル、予算切れを含みます。
- 新しい回帰例2件とmainで追加されたownership回帰例2件を含む16プログラムで、interpreter・JS・Cの1/4スレッドの結果が一致。計64実行です。
- 表記の整理だけでは、14プログラムの生成C/JSがbyte一致。パーティクルの生成Cも、両flat対照を含む8ファイルが公開した計測対象と一致します。
- TypeScriptは基準版・変更版ともに、既存の`bend.ts`のエラー2件です。クラスタの全test/perf/safeゲートとCUDA実機は未検証です。

`tests/run/known_callback.bend`の出力は`42`です。コマンドは下記に記載します。

<details>
<summary>再現コマンドと計測条件</summary>

小さい回帰例の出力は`42`です。

```sh
bun bend2/main.ts tests/run/known_callback.bend -o /tmp/known_callback.c
clang -O3 -std=c11 -pthread /tmp/known_callback.c -lm -o /tmp/known_callback
/tmp/known_callback --gpu off --threads 1
/tmp/known_callback --gpu off --threads 4
```

表は[main 947db722](https://github.com/bendlang/bend/commit/947db722640c86247849343657bf2f7ef01cb7f1)と[fork b59588e2](https://github.com/mizchi/bend/commit/b59588e2a9c63092b542739bb6908c3329d2e353)を比較した計測です。main 5a0b523fに追従して表記を整理した後も、各laneの生成Cが計8ファイルとも計測した版とbyte一致するため、時間は再計測していません。

Apple M5（CPU/GPU各10core）、macOS 26.6.2、Bun 1.3.5、clang 21.0.0。100万粒子、noise 64回、CPU grain 1,024、GPU grain 16,384、960×540のoffscreen画像を使います。各実行で5フレームをwarmupし、15フレームを計測。3回の実行の中央値の中央値を比較しました。設定の順番をshuffleして直列実行し、ビルド・起動・検証を除外します。計測フレームのCPUへのreadbackは0です。更新時間を測定し、表示完了の遅延は測っていません。

マシンは専有できませんでした。生成Cが同じflat GPU対照はmainで1.543–1.841 ms、forkで1.514–1.725 msと揺れ、小さい差をコンパイラの効果として扱いません。8バイナリをfloat32/画像oracleで検証し、36設定、144フレームが一致しました。

[計測生データ](https://github.com/mizchi/bend-playground/blob/09fc6e6/compiler-patches/step-02-known-callbacks/refactored/results-macos-m5.json)と[アプリケーション検証](https://github.com/mizchi/bend-playground/blob/09fc6e6/compiler-patches/step-02-known-callbacks/refactored/validation-macos-m5.json)。固定したsource/compilerのコミットと再現コマンドはリファレンスREADMEに記載しています。

</details>

OpenAI Codexの支援を使って実装・検証しました。
