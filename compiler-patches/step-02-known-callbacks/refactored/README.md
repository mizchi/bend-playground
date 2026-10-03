# 既知callbackのコンパイラ最適化: リファレンス実装

[上流PR #1288](https://github.com/bendlang/bend/pull/1288)を作成した。最新main `5a0b523f`を基準に、GPUIバインディングで見つかったcallbackのコストを一般的なコンパイラ最適化として改善する。

Bendの一般的なCコンパイラ最適化を、GPUIのパーティクル更新で検証する。通常の関数に既知のlambdaを渡す場合に、closureの確保と動的適用を省く。CPUとGPUは同じC生成処理を使う。[仕様](SPEC.md)、[English instructions](README.en.md)、[日本語のPR下書き](draft.ja.md)、[英語のPR下書き](draft.en.md)を用意した。

## 公開した比較対象

| 対象 | 固定コミット |
| --- | --- |
| 計測対象の上流main（2026-10-03確認） | [`947db722`](https://github.com/bendlang/bend/commit/947db722640c86247849343657bf2f7ef01cb7f1) |
| mizchi/bend `perf/known-callback-fusion` | [`b59588e2`](https://github.com/mizchi/bend/commit/b59588e2a9c63092b542739bb6908c3329d2e353) |
| playgroundの計測ソース | [`0d2b737a`](https://github.com/mizchi/bend-playground/commit/0d2b737a2b0e020428e223e572d85e6d2c4d748e) |

コミットとcompiler hashは[reference.json](reference.json)に記録した。両コンパイラの未変更のcheckoutを使い、HEAD・hash・未コミット変更を検査する。異なる版やローカルの変更があれば上書きせず停止する。両者を公開URLから新規取得できることも確認済み。

## 変更とコード量

独立したbook変換passを、既存の関数展開・引数束縛・lambda適用へ統合した。旧試作の166行追加から、**69行追加・15行削除（純増54行）**に削減した。検査済みbookへ新しい定義を追加する処理を省き、単一callbackのcapture計数を再利用する。captureの生存期間と予算切れの説明はコードに残した。

[compiler.patch](compiler.patch)はコンパイラだけ、[pr.patch](pr.patch)は`comp.ts`とBendの回帰例2ファイルの差分。基準コミットへの`git apply --check`を確認した。GPUIのバインディング、描画方式、手書きMetal kernelはコンパイラの変更に含まれない。

計測対象の`b59588e2`は`comp.ts`が**64,777 ttok**で、コード量ゲートは48/49だった。[提出用の版](submission/README.md)は最新main `5a0b523f`（Bend 2.0.35）を基準に、表記の整理と最適化を2コミットに分けて**63,956 ttok、repo gate 49/49**を確認した。恒久上限は変更せず、別ファイルへの移動も行っていない。

[追加の整理の試作](size-reduction/README.md)では、型・import・説明を整理して**63,909 ttok、repo gate 49/49**を確認した。基礎の整理とcallbackの変更を別パッチに分け、検証した生成C/JSが公開版とbyte一致することも確認している。

## 再現

計測環境はApple M5、macOS 26.6.2、Bun 1.3.5、clang 21.0.0、Rust 1.98.0。Git・just・Python 3・Bunを使い、描画の検証・計測にはRust/CargoとMetal SDKを含むXcodeが必要。

```sh
git clone https://github.com/mizchi/bend-playground.git
cd bend-playground
git checkout 0d2b737a2b0e020428e223e572d85e6d2c4d748e
just setup
just check-bend-step02-refactored
just bench-bend-step02-refactored --phase build
just bench-bend-step02-refactored --phase verify
just bench-bend-step02-refactored --phase bench
```

固定コミットを`build/bend-steps/step-02-refactored/`へ取得する。固定submoduleと`bend.ts`は変更しない。上流のC名解決に合わせ、作業コピーの`native.c`だけで`CID(api.Tick)`を`CID(Tick)`へ置換する。両コンパイラで同じBend/C入力を使う。

## 正しさ

- compilerの13テスト: scalar captureの再使用、tupleのmatch、線形配列、動的・boxed・再帰・関数capture、再コンパイル、dependentな型、予算切れ、複数lambda、非flatな呼び出し。元のStep 2の9契約を再利用する。
- 固定コミットの取得・変更の検出に関する4テストと、playgroundの既存40テストが成功。
- 上流のclosure・配列・相互再帰など12例をinterpreter／JS／Cの1・4スレッドで実行し、48件一致。
- CPU/Metal向けの8バイナリを検証。1・17・10,003粒子で独立したfloat32／画像oracleを使い、100万粒子でも全状態を確認。計36設定、144フレーム。
- callback版のclosure segmentは合計16 → 2、更新処理では14 → 0。残る2個はUI/IOのcallback。flat版の生成CはCPU/GPUの両grainでbyte一致。
- TypeScriptは基準・変更版とも`bend.ts`の既存エラー2件があり、新規の型エラーは増えていない。

calleeのbindingを呼び出し元から分離し、captureの早い解放を防ぐ。ANFが呼び出しを作り直しても採否が変わらないよう、callee・lambdaの同一性で判定をcacheする。600回の呼び出しでも予算切れからgenericなclosureへ戻って`601`を返す。

全クラスタのtest/perf/safeゲートとCUDA実機は未検証。実行ログとhashは[validation-macos-m5.json](validation-macos-m5.json)。

## 性能

100万粒子、noise 64回、CPU grain 1,024／GPU grain 16,384。960×540のoffscreen画像を準備する。5フレームをwarmup、15フレームを計測し、3回の中央値を比較した。順番をshuffleして直列に実行し、ビルド・検証を時間計測から分けた。

| callback版の区間 | 上流main | mizchi fork | 比率 |
| --- | ---: | ---: | ---: |
| CPU更新・1スレッド | 160.881 ms | 69.830 ms | 2.30× |
| CPU更新・10スレッド | 24.472 ms | 12.108 ms | 2.02× |
| Metal更新・完了待ち込み | 8.653 ms | 1.625 ms | 5.32× |
| Metal更新・GPU timestamp | 7.550 ms | 1.372 ms | 5.50× |

更新・描画・NV12変換を含むGPUのframe preparationは、16.227 → 9.849 ms。表示完了までの遅延は計測しない。GPU timestampとCPUの待ち時間は重なるため、足し合わせない。

読み戻しは全720フレームで0 bytes、状態バッファの確保は1回、実際のGPU dispatchも確認した。検証時の読み戻しは性能測定から除外する。3回すべての中央値・範囲・フレーム記録は[results-macos-m5.json](results-macos-m5.json)。

flat版は生成Cが同一でも、GPU完了待ちの中央値が1.572 → 1.524 ms、反復の範囲が1.543–1.841／1.514–1.725 msと揺れた。マシンは専有できず、計測前のCPU idleは2回の観測で74.60%／60.51%。callback版の大きな差は確認できるが、小さい割合の差をコンパイラの効果として扱わない。

提出用の版はcallbackの13契約と、上流の16プログラム×4実行方式（64実行）が成功。最新mainのownership回帰2件も含めた。表記の整理のみでは14プログラムの生成C/JSが一致し、計測対象のパーティクルCも両lane計8ファイルが一致したため、時間は再計測していない。[検証記録](submission/validation-macos-m5.json)に最新のコミット・hash・結果を記録した。
