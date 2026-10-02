//! Narrow, versioned C ABI. macOS surface drawing stays in GPUI.
use core_foundation::base::TCFType;
use core_video::pixel_buffer::{CVPixelBuffer, CVPixelBufferRef};
use gpui::{
    App, Application, Bounds, Context, Render, Window, WindowBounds, WindowOptions, div,
    prelude::*, px, rgb, size, surface,
};
use std::{
    ffi::c_void,
    panic::{AssertUnwindSafe, catch_unwind},
};

#[repr(C)]
#[derive(Clone, Copy)]
pub struct Config {
    pub abi_version: u32,
    pub width: u32,
    pub height: u32,
    pub max_frames: u32,
}

impl Config {
    fn validate(self) -> bool {
        self.abi_version == 1
            && (2..=2048).contains(&self.width)
            && (2..=2048).contains(&self.height)
            && self.width.is_multiple_of(2)
            && self.height.is_multiple_of(2)
    }
}

pub type Draw = unsafe extern "C" fn(*mut c_void, u32, u32, u32, *mut *mut c_void) -> i32;

struct View {
    context: *mut c_void,
    draw: Draw,
    frame: u32,
    max_frames: u32,
    paused: bool,
    image: Option<CVPixelBuffer>,
}

impl Render for View {
    fn render(&mut self, window: &mut Window, cx: &mut Context<Self>) -> impl IntoElement {
        let can_draw = self.max_frames == 0 || self.frame < self.max_frames;
        if can_draw && (!self.paused || self.image.is_none()) {
            let viewport = window.viewport_size();
            let width = (f32::from(viewport.width) as u32).clamp(2, 2048) & !1;
            let height = ((f32::from(viewport.height) - 52.).max(2.) as u32).clamp(2, 2048) & !1;
            let mut raw = std::ptr::null_mut();
            // Callback owns raw until its next invocation; retain immediately.
            let status = unsafe { (self.draw)(self.context, width, height, self.frame, &mut raw) };
            if status != 0 || raw.is_null() {
                eprintln!("Bend/GPUI frame callback failed ({status})");
                cx.quit();
            } else {
                self.image =
                    Some(unsafe { CVPixelBuffer::wrap_under_get_rule(raw as CVPixelBufferRef) });
                self.frame += 1;
            }
        }
        if self.max_frames != 0 && self.frame >= self.max_frames {
            // Give the final scene one display tick before closing.
            window.on_next_frame(|_, cx| cx.quit());
        } else if !self.paused {
            window.request_animation_frame();
        }
        let status = format!("Bend → Metal → GPUI   ·   frame {}", self.frame);
        div()
            .size_full()
            .flex()
            .flex_col()
            .bg(rgb(0x101724))
            .text_color(rgb(0xe1e8f4))
            .child(
                div()
                    .h(px(52.))
                    .px_4()
                    .flex()
                    .items_center()
                    .justify_between()
                    .child(status)
                    .child(
                        div()
                            .id("pause")
                            .px_3()
                            .py_1()
                            .rounded_md()
                            .bg(rgb(0x29384d))
                            .cursor_pointer()
                            .child(if self.paused { "Resume" } else { "Pause" })
                            .on_click(cx.listener(|this, _, window, cx| {
                                this.paused = !this.paused;
                                window.request_animation_frame();
                                cx.notify();
                            })),
                    ),
            )
            .children(
                self.image
                    .clone()
                    .map(|image| surface(image).w_full().flex_1()),
            )
    }
}

/// # Safety
/// config points to a valid Config; context and callback stay valid for this
/// blocking call. Callback returns a live NV12 CVPixelBuffer on the main thread.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn bend_gpui_run(
    config: *const Config,
    context: *mut c_void,
    draw: Option<Draw>,
) -> i32 {
    if config.is_null() || draw.is_none() {
        return 1;
    }
    let config = unsafe { *config };
    if !config.validate() {
        return 1;
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
                    window.set_window_title("Bend / GPUI — shared GPU surface");
                    cx.new(|_| View {
                        context,
                        draw,
                        frame: 0,
                        max_frames: config.max_frames,
                        paused: false,
                        image: None,
                    })
                },
            )
            .expect("open GPUI window");
            cx.activate(true);
        });
    }))
    .map(|_| 0)
    .unwrap_or(2)
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
