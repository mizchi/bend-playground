//! Surface rendering and per-view state.
use crate::Draw;
use core_foundation::base::TCFType;
use core_video::pixel_buffer::{CVPixelBuffer, CVPixelBufferRef};
use gpui::{Context, Render, Window, div, prelude::*, px, rgb, surface};
use std::ffi::c_void;

pub struct SurfaceView {
    context: *mut c_void,
    draw: Draw,
    frame: u32,
    max_frames: u32,
    paused: bool,
    image: Option<CVPixelBuffer>,
}

impl SurfaceView {
    /// Use a callback-driven surface as the contents of a GPUI window.
    /// Dimensions follow the window viewport, minus a 52px toolbar. Use
    /// max_frames=0 in an existing application; a frame limit quits the app.
    ///
    /// # Safety
    /// Call on the main thread. context and draw must remain valid until this
    /// view is dropped. draw returns a borrowed live NV12 CVPixelBuffer; it may
    /// release its previous buffer on the next invocation. Calls are serial.
    pub unsafe fn new(context: *mut c_void, draw: Draw, max_frames: u32) -> Self {
        Self {
            context,
            draw,
            max_frames,
            frame: 0,
            paused: false,
            image: None,
        }
    }
}

impl Render for SurfaceView {
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
        let status = format!("Frame {}", self.frame);
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
