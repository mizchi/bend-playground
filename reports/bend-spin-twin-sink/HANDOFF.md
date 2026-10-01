# ハンドオフ: bendlang/bend への spin の参照リーク報告

2026-10-01 時点。このセッションには gh 認証と bendlang/bend への書き込み権限がなく、
gist・issue・upstream PR は未送信。以下を、gh が使える環境で上から順に実行する。

## 状態

| 項目 | 状態 |
|---|---|
| 原因の特定・修正・回帰テスト | 済み。`bend2/comp.ts` の `emit_fuse` 1 行と `tests/reg/spin_lent_sink.bend` |
| ローカル検証 | 済み（下の「検証済みのこと」） |
| 日本語下書きの承認 | 済み（mizchi が 2 回承認。英訳は承認済みの日本語版から作成） |
| 読み手役サブエージェントによる確認 | 4 回（issue・PR を各 2 回）。指摘は反映済み |
| fork 上の PR | [mizchi/bend#2](https://github.com/mizchi/bend/pull/2)（head `fix/spin-lent-sink` @ `c6e7958`、base `upstream-main` = upstream `7d24b8d0`） |
| gist | **未作成** |
| bendlang/bend の issue | **未作成**。重複検索も未実施（issue 側は API が無く見られなかった） |
| bendlang/bend への PR | **未作成** |

## ファイル（このディレクトリ）

| ファイル | 用途 |
|---|---|
| `twin.bend` | 最小再現。gist に入れる |
| `README.md` | gist の説明（再現手順、RSS の測り方、修正案）。gist に入れる |
| `issue.en.md` | 送る issue。1 行目がタイトル。`#<PR>` と `<gist URL>` が未記入 |
| `pr.en.md` | 送る PR。1 行目がタイトル。`#<issue>` が未記入 |
| `issue.ja.md` / `pr.ja.md` | 承認済みの日本語版（内容の正本） |
| `0001-*.patch` | fork のブランチと同じコミット |
| `../../personas/bendlang/bend.md` | 対象リポジトリのペルソナ（git 履歴から手で計測） |

## 手順

作業ディレクトリは bend-playground のルート。`D=reports/bend-spin-twin-sink`。

### 0. 前提の確認

```sh
D=reports/bend-spin-twin-sink
gh auth status
gh repo view bendlang/bend --json visibility,defaultBranchRef   # PUBLIC / main
git -C upstream/bend fetch origin main && git -C upstream/bend log --oneline -1 origin/main
```

origin/main が `7d24b8d0` から進んでいたら、`emit_fuse` が変わっていないか確認する:
`git -C upstream/bend diff 7d24b8d0 origin/main -- bend2/comp.ts | grep -n -A3 'function emit_fuse'`。
変わっていれば修正の当て直しと再検証が必要（下の「再検証」）。

### 1. 重複の検索（このセッションでは未実施）

```sh
gh search issues --repo bendlang/bend --include-prs "leak spin"
gh search issues --repo bendlang/bend --include-prs "emit_fuse"
gh search issues --repo bendlang/bend --include-prs "bind_dead"
gh search issues --repo bendlang/bend --include-prs "RSS grows"
```

state は指定しない（open も closed も見る）。同じ現象の issue があれば新規に出さず、そこに PR を紐付ける。
open な PR の head（#1000 以降）は git で確認済みで、`emit_fuse` のこの分岐を変えるものは無かった。

### 2. gist を作る

```sh
gh gist create --public -d "Bend: a variable lent to a spin inside a jump argument is never sunk" \
  $D/twin.bend $D/README.md
```

出力された URL を `GIST=` に入れる。

### 3. issue を出す

bendlang/bend は空の issue を禁止しているので、本来はバグ報告フォーム `bug.yml` を使う。
`issue.en.md` はそのフォームの欄見出し（`### What you did` など）で書いてあり、gh で本文として送れば同じ形になる。

```sh
GIST=<2 の URL>
sed "s|<gist URL>|$GIST|; s| A fix with a regression test is in #<PR>\.||" $D/issue.en.md > /tmp/issue.md
grep -n '<' /tmp/issue.md | grep -v '<details>\|</details>\|<summary>\|</summary>'   # 残ったプレースホルダが無いこと
```

PR 番号は issue の後でしか決まらないので、issue の本文からは PR への言及を外して送り、PR 側から `(#issue)` で紐付ける。
送信前チェック（スキルの `check-draft.ts`。gh があれば本物が動く）:

```sh
S=<maintainer-persona skill>/scripts
node $S/check-draft.ts --persona personas/bendlang/bend.md --kind issue /tmp/issue.md
```

ペルソナにはまだ計測スクリプトのデータが無く（このセッションでは gh が無かった）、
このままだと `no measured block` で止まる。先に一度
`node $S/measure.ts bendlang/bend --corpus personas/bendlang/bend.corpus` を実行する。
空のマーカーを入れてあるので計測ブロックだけが入り、手で測った「0. Hand measurement」と §1-7 は残る。
計測結果の「First-time authors」の行（初回 PR の通過率、自動クローズの割合）は必ず読む。

```sh
gh issue create --repo bendlang/bend --label bug \
  --title "$(head -1 /tmp/issue.md | sed 's/^# //')" --body-file <(tail -n +3 /tmp/issue.md)
```

出力された issue 番号を `N=` に入れる。

### 4. コミット件名に issue 番号を入れて push

upstream の慣例はコミット件名の末尾に `(#N)`。

```sh
N=<3 の番号>
git -C /path/to/mizchi-bend fetch origin fix/spin-lent-sink
git -C /path/to/mizchi-bend checkout fix/spin-lent-sink
git -C /path/to/mizchi-bend commit --amend -m "A spin called in a jump's argument sinks the variable it was lent, so a loop no longer keeps the old list's cells (#$N)

Co-authored-by: Claude Opus 5.5 <noreply@anthropic.com>"
git -C /path/to/mizchi-bend push --force-with-lease origin fix/spin-lent-sink
```

### 5. bendlang/bend に PR を出す

```sh
sed "s/(#<issue>)/(#$N)/g" $D/pr.en.md > /tmp/pr.md
grep -n '#<' /tmp/pr.md            # 何も出ないこと
node $S/check-draft.ts --persona personas/bendlang/bend.md --kind pr /tmp/pr.md \
  && gh pr create --repo bendlang/bend --base main --head mizchi:fix/spin-lent-sink \
       --title "$(head -1 /tmp/pr.md | sed 's/^# //')" --body-file <(tail -n +3 /tmp/pr.md)
```

PR 本文の末尾には、mizchi/bend#2 と同じ Claude Code の署名を付けるかを決めてから送る（upstream のコミットには
`Co-authored-by: Claude` が多く、AI 利用は普通に受け入れられている）。

### 6. 後片付け

- mizchi/bend#2 を閉じる（upstream の PR に置き換わったため）。`upstream-main` ブランチも削除してよい。
- `personas/bendlang/bend.md` の §7 に送信した issue / PR の番号を書く。

## 検証済みのこと

環境: Linux x86_64（Intel Xeon、4 スレッド）、Ubuntu clang 18.1.3、bend 2.0.34 (`7d24b8d0`)。GPU なし。

- 再現: `twin.bend` は最大 RSS 64 MB（修正後 10 MB）。2.0.23（`75cb8f3e`）でも 64 MB
- 回帰テスト: 79 MB → 10 MB（`--threads 1` / `4`）。答え `4000010 2000000 4` は C と JS で一致
- upstream の tests/ 全件を C レーン・JS レーンで修正前後に実行: 新しいテスト以外は結果が同一（C pass 670 → 671、JS 692 → 693）
- bench/runtime 16 本の生成 C: 15 本は同一、hashmap は既存の `term_sink` 1 行が前に移るだけ
- `gates/repo.ts`: PASS 49 / 49

使ったスクリプトはこのセッションの一時領域にあり、残らない。必要なら作り直す:
テストランナーは「各 `tests/**/*.bend`（`import Base` と `#|` 行があるもの）を `bun bend2/main.ts f -o t` でビルドし、
`./t --gpu off` と `bun t.js` の標準出力を `#|` 行と比べる」だけのもの。

## 未確認のこと（PR 本文の「Not settled」と同じ）

- `gates/test.ts` と `gates/perf.ts` は upstream のクラスタ前提で未実行。perf に影響する可能性がある
  （漏れていたセルを解放する分、時間がかかるケースがある）
- `emit_fork` の並列側・逐次側で、`hold` だけが生かしている束縛を spin が借りると、両側の live が食い違う可能性。実例は作れていない
- 別の def への jump（`WL_JMP`）でも同じ経路を通るはずだが未検証

## 再検証（upstream が進んでいた場合）

1. 新しい main に `0001-*.patch` を当てる（`git am`）。当たらなければ `emit_fuse` の
   `if (tail) { bind_dead(fl, []); }` を `bind_dead(fl, tail ? [] : fl.rest);` に置き換える
2. `twin.bend` と `tests/reg/spin_lent_sink.bend` を修正前後でビルドし、RSS と答えを比べる
3. tests/ 全件を C・JS レーンで修正前後に比較、`bun gates/repo.ts`（`ttok` が必要: `pip install ttok`）
4. 数値が変わったら `pr.en.md` / `issue.en.md` を直し、日本語版にも反映する
