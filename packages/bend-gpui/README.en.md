# bend-gpui

Connect a Bend frame function to a GPUI window on macOS. The package contains the Bend API, a versioned C ABI, a Rust surface view, Metal rendering and NV12 conversion, and a standalone Python builder. It can be copied into another project without the playground demos.

Requires macOS 15 or newer, Metal, Rust/Cargo, Python 3, Bend 2 and clang. GPUI is pinned to 0.2.2. The playground wrapper also requires Bun; `just setup` obtains its pinned Bend checkout.

## Run the application example

From the playground root:

```sh
just setup
just gpui-build examples/gpui/minimal.bend --output build/gpui/minimal
build/gpui/minimal/BendGPUI.app/Contents/MacOS/bend-gpui --gpu off
build/gpui/minimal/BendGPUI.app/Contents/MacOS/bend-gpui --gpu on
```

Close the first window before running the second command. Both paths use Metal for rendering and conversion; `--gpu` selects the backend for Bend computation.

To compile with another Bend checkout, set `BEND_REPO` when building:

```sh
BEND_REPO=/path/to/bend just gpui-build examples/gpui/minimal.bend --output build/gpui/minimal
```

## Use in another project

Copy this directory to `vendor/bend-gpui/`. A minimal `main.bend` is:

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

The builder defaults to `bend` on PATH. `--bend-command` accepts an executable or wrapper path; `--target-dir` shares the Cargo cache. `--release` selects the Rust release profile; C always uses `-O3`. Relative imports in the caller's source tree are preserved.

## API and ownership

The [Bend API](bend/api.bend) passes `Tick{width, height, frame}` to a pure `Tick -> Frame` callback. Return either:

- `Pixels{width, height, buffer}`: row-major `Array<U32>` with `0xAABBGGRR` colors. `pixels(width, height, color)` allocates a solid frame at the current size.
- `Rects{count, errors, buffer}`: four `F32` cells per rectangle, `x/y/width/height`. Entry zero is the background root; subsequent entries use the built-in palette and a 2px inset. `errors` must be zero, and `count` must be 1–2,048.

`capacity(n)` returns the array depth for up to 4,194,304 cells. Frame dimensions are even numbers between 2 and 2,048. `max_frames=0` keeps the event loop running; a positive limit quits the application. `draw!` is the Bend GPU execution boundary.

Bend arrays stay alive until Metal completes reading them. The normal rendering path does not read their image or coordinate payload on the CPU. The [C ABI](include/abi.h) uses a 16-byte config with version 1 and a callback returning a borrowed NV12 full-range `CVPixelBuffer`. Rust retains that buffer immediately. Keep the callback and context valid until the view is dropped.

Rust applications can use this crate as a path dependency and place `SurfaceView::new(context, draw, 0)` in a window. Its dimensions follow the window viewport minus a 52px toolbar. Computation and conversion wait for GPU completion. The binding covers opaque 8-bit NV12 surfaces; alpha, HDR, Retina scaling and Bend input-event APIs are not implemented. GPUI quit may exit the process, so the blocking C call does not promise to resume the caller's event loop.

## Checks and performance records

`just check-gpui` checks the ABI, Grid/pixel output against independent oracles, and an application built from a copy of this package outside the playground. `just check-gpui-window` opens actual windows. `just check-particles` checks the particle application sharing this ABI.

The standalone package's build, CPU/Metal rendering and capacity helpers passed with pinned Bend `7d24b8d0` (2.0.34), upstream main `5a0b523f` (2.0.35), and the callback-specialization branch `83d497e5` (2.0.35). The adapter uses generated C runtime internals; repeat the checks when updating Bend.

For three offscreen frames through the same rendering path:

```sh
BEND_GPUI_HEADLESS=1 BEND_GPUI_FRAMES=3 \
  build/my-app/BendGPUI.app/Contents/MacOS/my-app --gpu on
```

Finite runs print frame JSON. `cpu_payload_read_bytes=0` describes the adapter's normal path, not a hardware memory counter. Pixel verification explicitly reads the converted image.

The [particle experiment](../../examples/particles/) contains the simulation and handwritten Metal kernels. [Published compiler comparisons](../../compiler-patches/step-02-known-callbacks/refactored/README.en.md) retain their original source/compiler revisions. Timings were not rerun for this package extraction.
