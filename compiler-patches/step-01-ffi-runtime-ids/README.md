# Step 1: FFI から runtime segment を参照する

C の effect source が `FID(Clo~apply)` または `FID(IO~emit)` を使うと、
Bend 側にその segment を参照する式がない場合、コンパイルが失敗する。
`c_ids` は book の名前と登録済み ID を照合するが、runtime 専用 segment の生成は
`compile_reqs` が effect source を読むより後だった。

`compile_book` の `file_book` 直後に両者の `seg_fid` を呼び、名前を先に予約する。
変更はコメントを含む **3 行**。segment 自体と数値 ID のテーブルは従来の場所で生成する。
`file_book` が ID の global map を消すため、予約はその後に行う。

[`compiler.patch`](compiler.patch)には compiler 修正と、upstream の `tests/io/` に追加する
2 組の Bend/C/JS 回帰テストを含めた。同じ fixture をこのディレクトリにも保存し、
準備スクリプトがパッチ内の fixture と一致することを確認する。

```sh
# 別 checkout を作成し、固定コミットへパッチを適用する。
just setup-bend-step01

# 自動で準備して回帰テストを実行する。
just check-bend-step01

# 固定版では runtime ID の再現テストが失敗する。
BEND_REPO="$PWD/upstream/bend" just check-bend-step01

# 修正版で既存の全テストを実行する。
BEND_REPO="$PWD/build/bend-steps/step-01/bend" just test
```

準備は繰り返し実行できる。既存 checkout のコミットが異なる、または競合する編集がある場合は
停止して保存する。reset や上書きは行わない。環境変数で指定した checkout は検証だけを行う。

検証項目は次の通り。

- Bend 内に動的呼び出しがなくても、C から closure を適用して `42` を出力する。
- C から `IO~emit` を実行し、返された `Emit` の payload `42` を取り出す。
- 名前空間付き import と、runtime と同じ C macro 名になるユーザー定義を扱う。
- 未知の `FID`/`CID` と、runtime segment を `CID` で指定した場合を拒否する。
- comment/string 内の ID 表記を置換しない。
- 同一プロセスで同じ book を再コンパイルし、JS コンパイルを挟んでも C が一致する。
- JS twin と interpreter の出力も C の `42` と一致する。
- 既存の pure/IO-pure/FFI と flat 粒子の C 生成結果が固定版と byte 単位で一致する。

固定版では 9 テスト中 6 テストが失敗した（名前空間の 2 subtest を含む 7 failures）。
修正版では **9 テストすべてが成功**し、既存の `just test` **40 テストも成功**した。
新しい checkout にパッチを適用・逆適用でき、準備タスクを繰り返し実行できることも確認した。
Apple M5 / macOS の結果と環境・ソース hash は
[`results-macos-m5.json`](results-macos-m5.json)に記録した。
CPU の 1/4 workers で effect の実行を検証した。GPU 上の新しい effect 実行は追加していない。
CUDA の実行と upstream の cluster gate は未実施。

このパッチは FFI の正当な参照をコンパイルできるようにする修正で、
FFI 呼び出しの固定費や GPU の更新時間を減らす変更ではない。性能計測は行っていない。
既存の粒子 adapter の `FID_CLO_APPLY` workaround は、固定版で動かすため残している。

## 上流 PR

[bendlang/bend#1286](https://github.com/bendlang/bend/pull/1286)を作成した。
提出コミットは `f5fadf405df89f339d33582e4f4b937acb603d10`、
比較元の上流 main は `947db722640c86247849343657bf2f7ef01cb7f1`。
[`pr.patch`](pr.patch)には上流 main に載せ直した差分、
[`draft.en.md`](draft.en.md)には送信した本文を保存した。

上流 main でも修正前の ID 解決失敗を再現し、修正後は9テストが通った。
新規2件と既存6件の上流テストは interpreter / JS / C（1/4 threads）で出力が一致し、
`gates/repo.ts` は49/49。`comp.ts` は63,933 → 63,961 ttok（上限64,000）。
結果は [`results-upstream-main-macos-m5.json`](results-upstream-main-macos-m5.json)に保存した。

PR 本文はその後、Bug issue template の6項目に `Why`、`Change`、`Verification` を加えた形式に更新した。
本文の2ファイルだけで、上流 main でのエラーと修正版での出力 `42` を再確認した。
更新時にも上流 HEAD は `947db722` だった。
更新前後の本文、HEAD の照合、再現結果は
[`pr-description-update-2026-10-03.json`](pr-description-update-2026-10-03.json)に記録した。

元の `results-macos-m5.json` は固定版で検証した時点のソース hash と結果を保持している。
検証コードにはその後、`BEND_BASE_REPO` で比較元を選ぶ処理を追加した。
粒子の C 生成対照ではコピーした effect source 内の `CID(api.Tick)` を `CID(Tick)` にして、
比較元・修正版とも effect 自身の名前空間で解決する。アプリのソースは変更していない。

```sh
BEND_REPO="$PWD/build/bend-prs/ffi-runtime-ids" \
BEND_BASE_REPO="$PWD/build/bend-prs/ffi-runtime-ids-base" \
just check-bend-step01
```
