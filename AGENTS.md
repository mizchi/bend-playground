# Bend Playground

ユーザーには日本語で答える。

Bend 2 の理解ノート、実験ソース、C の比較実装、計測結果を管理する独立リポジトリ。

- タスクは `justfile` を使う。`just setup` で固定した Bend を取得し、`just test` で検証する。
- 開発は探索 → Red → Green → Refactoring の順に進める。
- Bend の実行は `./scripts/bend.sh` または `just bend` を使う。元の checkout や個人の絶対パスに依存させない。
- `upstream/bend` は実験時のコミットに固定した submodule。内部を編集しない。特に `bend2/bend.ts` は人間が書く言語実装なので変更しない。
- `BEND_REPO` を指定すると別の Bend checkout を使える。実験結果には使用コミットと環境を記録する。
- `examples/intro/` と `examples/ds/path/probes/` は意図的に型検査に失敗する例を含む。成功するよう書き換えない。
- ソースと計測結果は追跡する。生成バイナリ・GPU ライブラリ・作業ファイルはコミットしない。
- ベンチマークの時間計測は静かなマシンで直列に行う。
- 関心の分離、状態とロジックの分離、厳密な API・型、可読性と保守性を重視する。
