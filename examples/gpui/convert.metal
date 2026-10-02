#include <metal_stdlib>
using namespace metal;
struct Args { uint width, height, kind, count; };

float3 palette(uint index) {
  if (index == 0) return float3(16, 23, 36) / 255.0;
  return float3(55 + (index * 53) % 160, 65 + (index * 97) % 150,
                95 + (index * 31) % 140) / 255.0;
}

struct RectVertex { float4 position [[position]]; float3 color; };

vertex RectVertex rectangle_vertex(uint vertex_id [[vertex_id]], uint instance_id [[instance_id]],
                                   device const float *rects [[buffer(0)]],
                                   constant Args &a [[buffer(1)]]) {
  const float2 corners[6] = {float2(0,0), float2(1,0), float2(0,1),
                             float2(0,1), float2(1,0), float2(1,1)};
  uint i = instance_id + 1;
  float2 origin = float2(rects[4*i], rects[4*i+1]) + 2.0;
  float2 extent = max(float2(rects[4*i+2], rects[4*i+3]) - 4.0, 0.0);
  float2 p = origin + corners[vertex_id] * extent;
  return RectVertex{float4(p.x * 2.0 / a.width - 1.0, 1.0 - p.y * 2.0 / a.height, 0, 1), palette(i)};
}

fragment float4 rectangle_fragment(RectVertex input [[stage_in]]) {
  return float4(input.color, 1);
}

float3 rgb_at(device const uint *data, constant Args &a, uint2 p,
              texture2d<float, access::read> rectangles) {
  if (a.kind == 0) {
    uint rgba = data[p.y * a.width + p.x];
    return float3(rgba & 255, (rgba >> 8) & 255, (rgba >> 16) & 255) / 255.0;
  }
  return rectangles.read(p).rgb;
}

kernel void convert(device const uint *data [[buffer(0)]],
                    constant Args &a [[buffer(1)]],
                    texture2d<float, access::write> y_plane [[texture(0)]],
                    texture2d<float, access::write> uv_plane [[texture(1)]],
                    texture2d<float, access::read> rectangles [[texture(2)]],
                    uint2 cell [[thread_position_in_grid]]) {
  if (cell.x >= a.width / 2 || cell.y >= a.height / 2) return;
  float2 uv = 0;
  for (uint dy = 0; dy < 2; dy++) for (uint dx = 0; dx < 2; dx++) {
    uint2 p = cell * 2 + uint2(dx, dy);
    float3 rgb = rgb_at(data, a, p, rectangles);
    float y = dot(rgb, float3(0.299, 0.587, 0.114));
    uv += float2(dot(rgb, float3(-0.168736, -0.331264, 0.5)),
                 dot(rgb, float3(0.5, -0.418688, -0.081312))) + 0.5;
    y_plane.write(float4(y, 0, 0, 1), p);
  }
  uv_plane.write(float4(uv / 4.0, 0, 1), cell);
}
