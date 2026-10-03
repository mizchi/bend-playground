//! GPUI surface binding for Bend and other native producers (macOS).
//! See the package README for the blocking event-loop and buffer ownership contract.
mod abi;
mod view;

pub use abi::{ABI_VERSION, Config, Draw, INVALID_CONFIG, PANIC};
use gpui::{App, AppContext, Application, Bounds, WindowBounds, WindowOptions, px, size};
use std::{
    ffi::c_void,
    panic::{AssertUnwindSafe, catch_unwind},
};
pub use view::SurfaceView;

/// # Safety
/// Call on the macOS main thread. config points to a valid Config; context and
/// callback stay valid for this blocking call. Callback returns a borrowed live
/// NV12 CVPixelBuffer. GPUI quit may exit the process rather than return here.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn bend_gpui_run(
    config: *const Config,
    context: *mut c_void,
    draw: Option<Draw>,
) -> i32 {
    if config.is_null() || draw.is_none() {
        return INVALID_CONFIG;
    }
    let config = unsafe { *config };
    if !config.validate() {
        return INVALID_CONFIG;
    }
    let draw = draw.unwrap();
    catch_unwind(AssertUnwindSafe(|| {
        Application::new().run(move |cx: &mut App| {
            cx.on_window_closed(|cx| {
                if cx.windows().is_empty() {
                    cx.quit();
                }
            })
            .detach();
            let bounds = Bounds::centered(
                None,
                size(px(config.width as f32), px(config.height as f32 + 52.)),
                cx,
            );
            cx.open_window(
                WindowOptions {
                    window_bounds: Some(WindowBounds::Windowed(bounds)),
                    ..Default::default()
                },
                |window, cx| {
                    window.set_window_title("Bend GPUI");
                    cx.new(|_| unsafe { SurfaceView::new(context, draw, config.max_frames) })
                },
            )
            .expect("open GPUI window");
            cx.activate(true);
        });
    }))
    .map(|_| 0)
    .unwrap_or(PANIC)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn abi_layout_and_size_contract() {
        assert_eq!(std::mem::size_of::<Config>(), 16);
        let config = Config {
            abi_version: 1,
            width: 512,
            height: 256,
            max_frames: 0,
        };
        assert!(config.validate());
        assert!(
            !Config {
                abi_version: 2,
                ..config
            }
            .validate()
        );
        assert!(
            !Config {
                width: 513,
                ..config
            }
            .validate()
        );
        assert!(
            !Config {
                height: 0,
                ..config
            }
            .validate()
        );
        assert!(
            !Config {
                width: 2050,
                ..config
            }
            .validate()
        );
        assert_eq!(
            unsafe { bend_gpui_run(std::ptr::null(), std::ptr::null_mut(), None) },
            1
        );
    }
}
