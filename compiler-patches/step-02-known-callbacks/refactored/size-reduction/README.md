# 64,000トークン以内に収める整理の試作

公開したcallback版 `b59588e2` を別checkoutで整理し、**64,777 → 63,909 ttok**に削減した。合計868トークンで、上限に対する余裕は91トークン。型・import・コメントの表記を整理し、コンパイラの実行処理を保つ。

## 削減箇所

同じ順番で変更を加え、ファイル全体を`ttok`の標準設定で計測した差分。

| 箇所 | 内容 | 削減 |
| --- | --- | ---: |
| 型表記 | `Book`等をtype importし、`Of<"Var">`を`Variable`に集約。`HTerm`は`import type { HTerm as Term }`として由来を示す | 239 |
| ASTコンストラクタ | `Ann`・`App`・`Ctr`等をnamed importし、繰り返す`Bend.`修飾を整理 | 38 |
| コンパイラの説明 | 21箇所のコメントを、制約・理由・数値を保ちながら簡潔に書く | 591 |
| 合計 | 64,777 → 63,909 | **868** |

コメントでは、Constantsの上限説明、Layの再帰・配列制約、Fileのownership解析、Emitの評価順序、C/JSの到達可能性・継続の説明などを整理した。captureの生存期間とANFの予算切れを説明する追加コメントも保持する。

例えば型の関係は、`import type { Book, HTerm as Term, Name } from "./bend.ts"`と`type Variable = Of<"Var">`で定義する。`Term`の実体は従来と同じhigher-order termであり、公開する型や言語の構文は変わらない。

## パッチの分け方

型名の変更は多くの行に及ぶため、callback最適化のレビューから分ける。

1. [compiler-compaction.patch](compiler-compaction.patch): 上流main `947db722`を63,933 → **63,082**へ整理する。コンパイラのdiffは238行追加・261行削除。
2. [callback-after-compaction.patch](callback-after-compaction.patch): 整理したmainへcallback最適化を適用する。コンパイラのdiffは従来と同じ**69行追加・15行削除**で、回帰例2ファイルを含む。最終的に63,909となる。

二段階のパッチを順に適用できることと、最終ソースのhashが検証した試作と一致することを確認した。

## 検証

- 整理のみ・callback込みの両版で、repo gate **49/49**。
- callbackの回帰テスト13件が成功。
- 両版で既存の上流12プログラムをinterpreter、JS、Cの1/4スレッドで実行し、各48件が成功。
- 公開callback版と試作で、上流14例の生成C/JS、計28ファイルがbyte一致。
- パーティクルのcallback/flat各版をCPU/GPUの両grainで生成し、同じ計測用instrumentationを施したCが公開版の4ファイルとbyte一致。
- TypeScriptのエラーは既存の`bend.ts`の2件で、新規エラーはない。

計測対象の生成Cが一致したため、速度の再計測は行っていない。上流クラスタの全ゲートとCUDA実機は未検証。実行ログ・hash・一致確認は[validation.json](validation.json)に記録した。

## ローカルで確認する

playgroundのルートで実行する。最初のコマンドは公開済みの固定コミットを準備する。

```sh
python3 scripts/bend_step02_refactor.py setup
git clone --no-hardlinks build/bend-steps/step-02-refactored/base build/bend-prs/callback-size-trial
git -C build/bend-prs/callback-size-trial apply "$PWD/compiler-patches/step-02-known-callbacks/refactored/size-reduction/compiler-compaction.patch"
git -C build/bend-prs/callback-size-trial apply "$PWD/compiler-patches/step-02-known-callbacks/refactored/size-reduction/callback-after-compaction.patch"
BEND_REPO="$PWD/build/bend-prs/callback-size-trial" BEND_BASE_REPO="$PWD/build/bend-steps/step-02-refactored/base" BEND_PARTICLE_CID=Tick python3 tests/bend_step02_refactor.py
ttok -i build/bend-prs/callback-size-trial/bend2/comp.ts
```

公開済みの性能比較は`b59588e2`を対象にした記録で、この試作はそれとは別のレビュー用パッチである。
