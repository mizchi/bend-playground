#ifndef BEND_GPUI_ABI_H
#define BEND_GPUI_ABI_H
#include <stdint.h>

// v1: callback runs serially on the macOS main thread. Output is a borrowed
// CVPixelBufferRef in NV12 full-range format; Rust retains it before returning.
// No Bend heap pointer or buffer payload crosses this C/Rust boundary.
typedef struct {
  uint32_t abi_version, width, height, max_frames;
} BendGpuiConfig;
typedef int32_t (*BendGpuiDraw)(void *context, uint32_t width, uint32_t height,
                              uint32_t frame, void **pixel_buffer);
int32_t bend_gpui_run(const BendGpuiConfig *config, void *context, BendGpuiDraw draw);
#endif
