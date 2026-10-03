# C の effect から Bend の callback を呼ぶプログラムの C 生成を修正する

C の effect は Bend から受け取った callback を呼び出せるはずだが、runtime helper の ID を登録する前に解決しようとして、コンパイル時に失敗する場合がある。

### What you did

以下の2ファイルを保存し、上流 `main` @ `947db722` でコンパイルした。2026-10-03 の再確認でも最新 HEAD はこのコミットだった。

```sh
bend main.bend -o main.c
```

C の effect が callback に `40` を渡し、callback が `2` を足す。

### What happened

clang が実行される前に C 生成が失敗する。

```text
Error: FID(Clo~apply) names no constructor or def
```

期待する動作はコンパイル成功と、native program の出力 `42`。

### The file

`main.bend`:

```python
import Base

def native.apply(step: U32 -> U32, value: U32) -> IO(Unit):
  import "./native.c"

def main() -> IO(Unit):
  native.apply(x => (x + 2 : U32), 40)
```

`native.c`:

```c
static Term native_apply_run(Env e, Term* f, IoWork* w) {
  (void)w;
  u64 at = task_node(e, FID(Clo~apply), TERM_HOLE, 0, 0);
  e.mem[at] = f[0];
  e.mem[at + 1] = f[1];
  Term result = corpus_eval(e.mem, term_tsk(FID(Clo~apply), at));
  if (err_seen(e.mem)) err_fail("foreign closure application failed");
  printf("%u\n", (u32)result);
  return term_pak(CID(Unit), 0);
}

static void __attribute__((constructor)) native_apply_use(void) {
  io_eff(CID(native.apply), native_apply_run, 0);
}
```

### Why

`Clo~apply` は closure を適用する runtime のコード、`IO~emit` は IO の結果を包むコード。生成される runtime 内に実装されており、Bend book の宣言ではない。

`compile_book` はこの2つの runtime segment を生成する前に、`effect_srcs` で foreign C source を読む。`c_ids` が受理するのは book または ID テーブルにある名前だけ。生成済みの Bend の呼び出しがまだ helper を登録していない場合、有効な runtime の名前を拒否する。

### Change

`file_book` が ID テーブルを初期化した直後に、`seg_fid` で `IO_EMIT` と `CLO_APPLY` を登録する。これにより foreign source を読む時点で名前を解決できる。runtime entry と数値 ID の生成位置は同じ。

C から Bend callback を呼ぶ場合と、`IO~emit` の payload を取り出す場合の C/JS 回帰テストを追加する。どちらも `42` を出力する。

### Verification

- 上記の2ファイルによる再現は上流 main で失敗し、修正版では `42` を出力する（C、1/4 threads、GPU off）。
- 新規2件と既存6件が interpreter、JS、C で期待出力と一致する。
- ローカルの9テストが通り、4つの C 生成対照は修正前後で byte 単位で一致する。
- `gates/repo.ts`: PASS 49/49。`comp.ts`: 63,933 → 63,961 ttok（上限64,000）。

クラスタ全体の test/perf gate と CUDA はローカルでは実行していない。

### bend --version

`bend version` の出力:

```text
bend 2.0.34
```

比較元: `947db722640c86247849343657bf2f7ef01cb7f1`、PR head: `f5fadf405df89f339d33582e4f4b937acb603d10`。

### uname -sm

```text
Darwin arm64
```

Apple M5、macOS 26.6.2。

### clang --version (the first line)

```text
Apple clang version 21.0.0 (clang-2100.0.123.102)
```

AI（Codex）の支援で作成した。
