// Demo-only independent pixel oracle; included when the builder enables it.
#define Style GpuiOracleStyle
#include "grid.c"
#include "oracle-input.h"
#undef Style

// CPU oracle uses independent C Grid output or the arithmetic pixel formula.
// It reads only the converted NV12 planes, never the Bend output payload.
static void gpui_oracle_rgb(uint32_t kind, uint32_t x, uint32_t y, uint32_t frame,
                            const Output *layout, float rgb[3]) {
  if (kind == 0) {
    rgb[0] = (float)((x + frame * 3) % 256) / 255;
    rgb[1] = (float)((y * 2 + frame) % 256) / 255;
    rgb[2] = (float)((((x / 16) ^ (y / 16)) * 37) % 256) / 255;
  } else {
    uint32_t selected = 0;
    for (uint32_t i = 1; i < layout->count; ++i) {
      Box r = layout->boxes[i];
      if (x + .5f >= r.x + 2 && y + .5f >= r.y + 2 &&
          x + .5f < r.x + r.width - 2 && y + .5f < r.y + r.height - 2) selected = r.id;
    }
    rgb[0] = (float)(selected ? 55 + (selected * 53) % 160 : 16) / 255;
    rgb[1] = (float)(selected ? 65 + (selected * 97) % 150 : 23) / 255;
    rgb[2] = (float)(selected ? 95 + (selected * 31) % 140 : 36) / 255;
  }
}

static int gpui_byte_matches(unsigned char actual, float expected) {
  int wanted = (int)lrintf(fminf(1, fmaxf(0, expected)) * 255);
  return abs((int)actual - wanted) <= 1;
}

static bool gpui_verify(CVPixelBufferRef pixel, GpuiArgs a, uint32_t frame) {
  Output layout;
  if (a.kind) {
    grid_run(pages[0], a.width, a.height, &layout);
    if (layout.errors || layout.count != a.count) return false;
  }
  if (CVPixelBufferLockBaseAddress(pixel, kCVPixelBufferLock_ReadOnly)) return false;
  const unsigned char *y_plane = CVPixelBufferGetBaseAddressOfPlane(pixel, 0);
  const unsigned char *uv_plane = CVPixelBufferGetBaseAddressOfPlane(pixel, 1);
  size_t ys = CVPixelBufferGetBytesPerRowOfPlane(pixel, 0), uvs = CVPixelBufferGetBytesPerRowOfPlane(pixel, 1);
  bool okay = true;
  for (uint32_t y = 0; y < a.height; y += 2) for (uint32_t x = 0; x < a.width; x += 2) {
    float u = 0, v = 0;
    for (uint32_t dy = 0; dy < 2; ++dy) for (uint32_t dx = 0; dx < 2; ++dx) {
      float rgb[3]; gpui_oracle_rgb(a.kind, x + dx, y + dy, frame, &layout, rgb);
      float yy = .299f*rgb[0] + .587f*rgb[1] + .114f*rgb[2];
      u += -.168736f*rgb[0] - .331264f*rgb[1] + .5f*rgb[2] + .5f;
      v += .5f*rgb[0] - .418688f*rgb[1] - .081312f*rgb[2] + .5f;
      okay &= gpui_byte_matches(y_plane[(y+dy)*ys+x+dx], yy);
    }
    okay &= gpui_byte_matches(uv_plane[(y/2)*uvs+x], u/4);
    okay &= gpui_byte_matches(uv_plane[(y/2)*uvs+x+1], v/4);
  }
  CVPixelBufferUnlockBaseAddress(pixel, kCVPixelBufferLock_ReadOnly);
  return okay;
}
