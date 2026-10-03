# The C compiler specializes calls with a known callback

現状は提出前の試作です。main `947db722` に対してローカルで再現し、機能検証は通っています。`comp.ts` は64,777 ttokで、64,000のコード量ゲートを満たすための整理が残っています。

## What Bend should do

静的に分かるcallbackを渡した呼び出しで、closureの確保と動的適用を省けるようにします。通常の関数定義と型を保ったまま、コンパイラが対応する呼び出しを特殊化します。

```python
def apply(x: U32, callback: U32 -> U32) -> U32:
  callback(x)

def run(+bias: U32, x: U32) -> U32:
  a = apply(x, y => U32.add(y, bias))
  apply(a, y => U32.add(y, bias))
```

## Why

配列要素の処理や継続の連結をcallbackで記述した場合、closureの確保と動的適用が小さな計算を繰り返すコストに加わります。実装を引数展開した別の関数へ書き換えずに、このコストを減らすのが目的です。C生成のCPU/GPU共通処理を改善します。

## Change

完全適用された通常の定義にliteral lambdaが1個渡され、captureにboxedな値を含まない場合を対象にします。既存の関数展開と引数束縛を再利用し、型付きlambdaとconstructorのパターン束縛を保ちます。呼び出し元のcaptureの生存期間を保持し、ANFが呼び出しを作り直しても最適化予算に関する採否を維持します。

動的な関数、複数のlambda引数、foreign/bang呼び出し、直接の自己参照や並列束縛を持つcalleeは従来の処理を使います。途中の呼び出しの展開では非flatな呼び出しも除外し、予算切れではclosureによる処理へ戻します。生成JSとinterpreterは比較対象の結果を確認するために実行します。

## Verification

`tests/run/known_callback.bend` を次のコマンドで確認できます。期待する出力は`42`です。

```sh
bun bend2/main.ts tests/run/known_callback.bend -o /tmp/known_callback.c
clang -O3 -std=c11 -pthread /tmp/known_callback.c -lm -o /tmp/known_callback
/tmp/known_callback --gpu off --threads 1
/tmp/known_callback --gpu off --threads 4
```

- scalar captureの再使用、tupleのmatch、線形配列、予算切れ、非flatな呼び出し、genericな処理への復帰をCの1/4スレッドとJS/interpreterで検証。
- 既存のclosure・配列・相互再帰など12例を4実行方式で確認。上流クラスタの全test/perf/safeゲートは未実行。
- GPUIのパーティクル更新を利用例として検証。Bendソースを保ったまま、更新処理のclosure segmentが14個から0個へ減少。callbackを使わないflat版の生成Cは基準版と一致。

GPUIのバインディング、描画コード、手書きMetal kernelはこのPRの変更範囲に含めません。GPUIは一般的なコンパイラ最適化の効果を測る利用例です。Apple M5/macOSでのCPU/Metalの実行を確認し、CUDAの実機検証は未実行です。

リファレンス実装とCPU/Metalの比較: [bend-playground](https://github.com/mizchi/bend-playground/tree/main/compiler-patches/step-02-known-callbacks/refactored)。比較したコンパイラ: [上流main](https://github.com/bendlang/bend/commit/947db722640c86247849343657bf2f7ef01cb7f1)、[mizchi fork](https://github.com/mizchi/bend/commit/b59588e2a9c63092b542739bb6908c3329d2e353)。
