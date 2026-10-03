# bend-gpui

[English](README.md)

Bendのフレーム関数を、macOSのGPUIウィンドウへ接続するライブラリ。Bend API、C ABI、Rustのsurface view、Metalの描画・NV12変換、ビルド用Pythonをこのディレクトリにまとめた。パッケージだけを別プロジェクトへコピーして使える。

GPUIは0.2.2に固定。macOS 15以降、Metal、Rust/Cargo、Python 3、Bend 2、clangが必要。playgroundでは固定したBend 2.0.34とclang 21で検証する。`BEND_REPO`で別のBend checkoutを選べる。

## playgroundで使う

```sh
just setup
just build-gpui-library
just gpui-build examples/gpui/minimal.bend --output build/gpui/minimal
build/gpui/minimal/BendGPUI.app/Contents/MacOS/bend-gpui --gpu off
# Bendの計算をMetalへ切り替える場合
build/gpui/minimal/BendGPUI.app/Contents/MacOS/bend-gpui --gpu on
just check-gpui
```

`gpui-build`は任意のBend `main`を受け取り、生成C、GPUIのstatic library、Metalをリンクして`.app`を作る。`--name`、`--bundle-id`、`--output`でアプリごとの名前と出力先を指定できる。Rustのreleaseビルドは`--release`、Cは常に`-O3`。RustとCの両方へ`MACOSX_DEPLOYMENT_TARGET`を渡す。

## 別プロジェクトで使う

このディレクトリ全体を`vendor/bend-gpui/`へコピーし、次の`main.bend`を置く。

```python
import Base
import ./vendor/bend-gpui/bend/api.bend as UI

def draw(tick: UI.Tick) -> UI.Frame:
  match tick:
    case UI.Tick{width, height, frame}:
      UI.pixels(width, height, 4281558681)

def main() -> IO(Unit):
  UI.run(640, 360, 0, tick => draw!(tick))
```

```sh
python3 vendor/bend-gpui/build.py main.bend --output build/my-app --name my-app
build/my-app/BendGPUI.app/Contents/MacOS/my-app --gpu off
```

既定ではPATH上の`bend`を使う。checkoutから実行する場合は`--bend-command /path/to/bend-playground/scripts/bend.sh`と`BEND_REPO`を使う。`--target-dir`でCargoのキャッシュを共有できる。ビルダーは呼び出し元のBendファイルと、その相対importをそのままコンパイルする。

ウィンドウを開かず、同じMetal描画経路で3フレームだけ実行する例:

```sh
BEND_GPUI_HEADLESS=1 BEND_GPUI_FRAMES=3 \
  build/my-app/BendGPUI.app/Contents/MacOS/my-app --gpu on
```

## 公開API

| 層 | エントリポイント | 用途 |
| --- | --- | --- |
| Bend | [bend/api.bend](bend/api.bend) | `run`、`Tick`、`Frame`、`pixels`、`capacity` |
| C/C++ | [include/abi.h](include/abi.h) | v1の`BendGpuiConfig`・描画callback・`bend_gpui_run` |
| Rust | [src/lib.rs](src/lib.rs) | 同じC ABIと、既存GPUIアプリへ埋め込む`SurfaceView` |
| ビルド | [build.py](build.py) | `build`、`cargo`、`compile_app`、`.app`とGPUライブラリの生成 |

`Tick{width, height, frame}`を受け取り、次のいずれかを返す。

- `Pixels{width, height, buffer}`: row-majorの`Array<U32>`、色は`0xAABBGGRR`。`pixels(width, height, color)`はサイズに合う配列を確保して単色で埋める。
- `Rects{count, errors, buffer}`: `Array<F32>`の`x/y/width/height`を4セルずつ並べる。先頭は背景rootで、id 1以降を入力順に描く。既定のpaletteと各辺2pxの余白を使う。`errors`は0、`count`は1〜2,048。

配列容量は必要なセル数以上の2の累乗。`capacity(n)`は0〜4,194,304セルに対する深さを返す。`Array.new(T, UI.capacity(n), value)`で確保できる。画面サイズは2〜2,048の偶数で、奇数の環境変数指定は一つ小さい偶数へ丸める。

`run(width, height, max_frames, draw)`はメインスレッドでイベントループを開始する。`max_frames=0`は連続表示、正の値は指定フレーム数で終了する。描画関数は純粋関数で、`draw!`がBend GPUの実行境界になる。リサイズでTickのサイズが変わり、Pause/Resumeでフレームの更新を止められる。

Rustからは、このパッケージをpath依存にして`SurfaceView::new(context, draw, 0)`を既存のGPUI windowの内容として使える。サイズはウィンドウ全体から52pxのtoolbarを引いて決める。任意の子パネルのサイズに追従する機能は含まない。正の`max_frames`を渡すとアプリ全体を終了する。C/Rust側のcallbackは、完成済みのNV12 full-range `CVPixelBuffer`を返す。Bendの`Frame`に限定せず、粒子など独自のMetal描画にも使える。

## 所有権と実行範囲

Bend配列は、Metalが共有メモリを読み終わるまで保持する。CPUで計算した配列も、ページ境界に合わせた`newBufferWithBytesNoCopy`でMetalに渡す。GPUで計算した場合はBendの`gpu_buf`を使う。通常経路は画像・座標の配列内容をCPUへ読み戻さない。

C/Rust境界ではBendのheap pointerを渡さず、描画callbackが借用した`CVPixelBuffer`を返す。Rustはcallback直後にretainし、次のcallbackが前の画像を解放しても表示中の画像を保持する。`Config`は16 bytes、ABI versionは1。contextとcallbackは、そのviewが破棄されるまで有効に保つ。

Bendの計算、adapterの描画・変換は同期完了を待つ。NV12は不透明な8-bit YUV 4:2:0で、alpha・HDR・Retinaのscale factorへの対応は含まない。GPUI widget全体、マウス・キーイベントのBend APIも未実装。macOSのGPUI `quit`はプロセスを終了し得るため、ウィンドウ終了後にBendのIO継続へ戻ることは契約に含めない。

## 検証と診断

`just check-gpui`はRustのABI検査、Grid・画素デモのCPU/Metal出力検証、パッケージだけを別プロジェクトへコピーしてアプリを構築するテストを実行する。コピー先・出力先に空白を含むパスも検証する。`just check-gpui-window`は実際のウィンドウを開き、3フレームで自動終了する。粒子デモは同じC ABI/static libraryを使い、`just check-particles`で検証する。

パッケージ単体のビルド・CPU/Metal描画・容量計算は、以下のBend commitで確認した。Bendの生成Cにある内部APIを使うため、更新時には同じテストを実行する。

| Bend | 確認したcommit |
| --- | --- |
| playground固定版（2.0.34） | `7d24b8d0235cb9781140512c0f163c48ea84a719` |
| upstream main（2.0.35） | `5a0b523f7759335164f1dead0e0815234a5fd9dc` |
| callback最適化版（2.0.35） | `83d497e52610c42dcc5bddf5ad21fb0285e12e88` |

有限フレーム実行または`BEND_GPUI_PROFILE=1`ではフレームごとのJSONを出す。GPU dispatch数・実行時間は、ビルド時に生成Cへ入れた計測から取得する。対応しないBend runtimeの構造はビルド時に検出する。出力の`cpu_payload_read_bytes=0`はアダプタの契約値で、ハードウェアのメモリ計数ではない。

Gridのpixel oracleは[デモ側のverify.h](../../examples/gpui/verify.h)にある。ライブラリはGrid実装に依存しない。独自の検証を加える場合は`compile_app(..., cflags=['-DBEND_GPUI_VERIFY_HEADER="verify.h"'])`で検証ヘッダーを指定する。検証時だけ変換済み画像をCPUで読む。

既存デモの[計測記録](../../examples/gpui/README.md)と[粒子の比較](../../examples/particles/README.md)は、記録した版の結果として保持する。今回のライブラリ整理による速度差は計測していない。
