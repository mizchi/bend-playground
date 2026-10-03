#include "abi.h"
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#import <CoreVideo/CoreVideo.h>
#include "convert-source.h"

typedef struct { uint32_t width, height, kind, count; } GpuiArgs;
#ifdef BEND_GPUI_VERIFY_HEADER
#include BEND_GPUI_VERIFY_HEADER
#endif
typedef struct {
  Env env;
  Term draw;
  id<MTLDevice> device;
  id<MTLCommandQueue> queue;
  id<MTLComputePipelineState> pipeline;
  id<MTLRenderPipelineState> rectangles;
  id<MTLTexture> color;
  CVMetalTextureCacheRef cache;
  CVPixelBufferRef previous;
  bool verify, profile;
} GpuiState;

static uint64_t gpui_clock(void) {
  struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t);
  return (uint64_t)t.tv_sec * 1000000000ull + t.tv_nsec;
}

static bool gpui_init(GpuiState *state) {
  state->device = gpu_dev ?: MTLCreateSystemDefaultDevice();
  state->queue = [state->device newCommandQueue];
  NSError *error = nil;
  id<MTLLibrary> library = [state->device newLibraryWithSource:
    [NSString stringWithUTF8String:gpui_shader_source] options:nil error:&error];
  state->pipeline = [state->device newComputePipelineStateWithFunction:
    [library newFunctionWithName:@"convert"] error:&error];
  MTLRenderPipelineDescriptor *render = [MTLRenderPipelineDescriptor new];
  render.vertexFunction = [library newFunctionWithName:@"rectangle_vertex"];
  render.fragmentFunction = [library newFunctionWithName:@"rectangle_fragment"];
  render.colorAttachments[0].pixelFormat = MTLPixelFormatBGRA8Unorm;
  state->rectangles = [state->device newRenderPipelineStateWithDescriptor:render error:&error];
  if (!state->pipeline || !state->rectangles || error || CVMetalTextureCacheCreate(NULL, NULL,
      state->device, NULL, &state->cache)) {
    fprintf(stderr, "GPUI Metal initialization: %s\n", error.localizedDescription.UTF8String);
    return false;
  }
  return true;
}

static int32_t gpui_draw(void *context, uint32_t width, uint32_t height,
                         uint32_t frame, void **pixel_buffer) {
  GpuiState *s = context;
  if (width < 2 || height < 2 || width > 2048 || height > 2048 || ((width | height) & 1)) return 1;
  @autoreleasepool {
    Env e = s->env;
    // Reusable language closures are constructor values; retain before applying.
    s->draw = term_keep(e, s->draw, 1);
    u64 tick_at = heap_alloc(e, cls_fit(3));
    e.mem[tick_at] = width; e.mem[tick_at+1] = height; e.mem[tick_at+2] = frame;
    Term tick = term_ctr(CID(Tick), tick_at);
    u64 apply_at = task_node(e, FID_CLO_APPLY, TERM_HOLE, 0, 0);
    e.mem[apply_at] = s->draw; e.mem[apply_at+1] = tick;
    bend_gpui_probe_commands = 0; bend_gpui_probe_execution = bend_gpui_probe_wait = bend_gpui_probe_submit = 0;
    uint64_t begin = gpui_clock();
    Term result = corpus_eval(e.mem, term_tsk(FID_CLO_APPLY, apply_at));
    uint64_t ready = gpui_clock();
    if (err_seen(e.mem) || term_tag(result) != TAG_CTR) return 2;
    const Term *fields = e.mem + term_peek(e.mem, result);
    GpuiArgs a = {width, height, 0, 0}; Term data;
    if (term_aux(result) == CID(Pixels)) {
      if (fields[0] != width || fields[1] != height) return 3;
      data = fields[2];
    } else if (term_aux(result) == CID(Rects)) {
      a.kind = 1; a.count = (uint32_t)fields[0]; data = fields[2];
      if (fields[1] || !a.count || a.count > 2048) return 3;
    } else return 3;
    if (term_tag(data) != TAG_BUF || blk_cls(data) > 22) return 4;
    uint64_t active = a.kind ? (uint64_t)a.count * 4 : (uint64_t)width * height;
    if ((1ull << blk_cls(data)) < active) return 4;
    uint64_t offset = blk_loc(e.mem, data) * sizeof(u64);
    id<MTLBuffer> input = gpu_buf;
    if (!input) {
      // CPU heap: borrow only the pages covering this Array, without copying.
      uintptr_t ptr = (uintptr_t)e.mem + offset, base = ptr & ~(uintptr_t)16383;
      size_t bytes = ((ptr - base + active * 4 + 16383) & ~(size_t)16383);
      input = [s->device newBufferWithBytesNoCopy:(void *)base length:bytes
        options:MTLResourceStorageModeShared deallocator:nil];
      offset = ptr - base;
    }
    if (!input || offset + active * 4 > input.length) return 5;
    CVPixelBufferRef pixel = NULL;
    NSDictionary *attributes = @{
      (__bridge NSString *)kCVPixelBufferMetalCompatibilityKey: @YES,
      (__bridge NSString *)kCVPixelBufferIOSurfacePropertiesKey: @{}
    };
    if (CVPixelBufferCreate(NULL, width, height, kCVPixelFormatType_420YpCbCr8BiPlanarFullRange,
          (__bridge CFDictionaryRef)attributes, &pixel)) return 6;
    CVMetalTextureRef yt = NULL, uvt = NULL;
    CVReturn yrc = CVMetalTextureCacheCreateTextureFromImage(NULL, s->cache, pixel, NULL,
      MTLPixelFormatR8Unorm, width, height, 0, &yt);
    CVReturn uvrc = CVMetalTextureCacheCreateTextureFromImage(NULL, s->cache, pixel, NULL,
      MTLPixelFormatRG8Unorm, width/2, height/2, 1, &uvt);
    if (yrc || uvrc) {
      if (yt) CFRelease(yt); if (uvt) CFRelease(uvt); CVPixelBufferRelease(pixel); return 7;
    }
    id<MTLCommandBuffer> command = [s->queue commandBuffer];
    if (!s->color || s->color.width != width || s->color.height != height) {
      MTLTextureDescriptor *descriptor = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:
        MTLPixelFormatBGRA8Unorm width:width height:height mipmapped:NO];
      descriptor.storageMode = MTLStorageModePrivate;
      descriptor.usage = MTLTextureUsageRenderTarget | MTLTextureUsageShaderRead;
      s->color = [s->device newTextureWithDescriptor:descriptor];
      if (!s->color) { CFRelease(yt); CFRelease(uvt); CVPixelBufferRelease(pixel); return 7; }
    }
    if (a.kind) {
      MTLRenderPassDescriptor *pass = [MTLRenderPassDescriptor renderPassDescriptor];
      pass.colorAttachments[0].texture = s->color;
      pass.colorAttachments[0].loadAction = MTLLoadActionClear;
      pass.colorAttachments[0].storeAction = MTLStoreActionStore;
      pass.colorAttachments[0].clearColor = MTLClearColorMake(16.0/255, 23.0/255, 36.0/255, 1);
      id<MTLRenderCommandEncoder> draw = [command renderCommandEncoderWithDescriptor:pass];
      [draw setRenderPipelineState:s->rectangles];
      [draw setVertexBuffer:input offset:offset atIndex:0];
      [draw setVertexBytes:&a length:sizeof a atIndex:1];
      // Six generated vertices per instance; x/y/w/h stay in the Bend heap.
      [draw drawPrimitives:MTLPrimitiveTypeTriangle vertexStart:0 vertexCount:6 instanceCount:a.count-1];
      [draw endEncoding];
    }
    id<MTLComputeCommandEncoder> encoder = [command computeCommandEncoder];
    [encoder setComputePipelineState:s->pipeline];
    [encoder setBuffer:input offset:offset atIndex:0];
    [encoder setBytes:&a length:sizeof a atIndex:1];
    [encoder setTexture:CVMetalTextureGetTexture(yt) atIndex:0];
    [encoder setTexture:CVMetalTextureGetTexture(uvt) atIndex:1];
    [encoder setTexture:s->color atIndex:2];
    [encoder dispatchThreads:MTLSizeMake(width/2, height/2, 1)
      threadsPerThreadgroup:MTLSizeMake(8, 8, 1)];
    [encoder endEncoding]; [command commit];
    uint64_t wait = gpui_clock(); [command waitUntilCompleted]; uint64_t done = gpui_clock();
    if (command.error) {
      fprintf(stderr, "GPUI converter: %s\n", command.error.localizedDescription.UTF8String);
      CFRelease(yt); CFRelease(uvt); CVPixelBufferRelease(pixel); return 8;
    }
    CFRelease(yt); CFRelease(uvt);
    CVMetalTextureCacheFlush(s->cache, 0);
    // Bend allocation remains alive until conversion has finished reading it.
    term_drop(e, result);
    uint64_t dropped = gpui_clock();
    uint32_t verified = 0;
#ifdef BEND_GPUI_VERIFY_HEADER
    if (s->verify) {
      if (!gpui_verify(pixel, a, frame)) {
        fprintf(stderr, "GPUI NV12 pixel oracle mismatch at frame %u\n", frame);
        CVPixelBufferRelease(pixel); return 9;
      }
      verified = width * height;
    }
#endif
    if (s->previous) CVPixelBufferRelease(s->previous);
    s->previous = pixel; *pixel_buffer = pixel;
    if (s->profile) printf("{\"frame\":%u,\"width\":%u,\"height\":%u,\"kind\":\"%s\","
      "\"bend_ns\":%llu,\"bend_gpu_commands\":%u,\"bend_gpu_ns\":%llu,"
      "\"convert_gpu_ns\":%llu,\"convert_wait_ns\":%llu,"
      "\"handoff_ns\":%llu,\"drop_ns\":%llu,\"frame_ready_ns\":%llu,"
      "\"cpu_payload_read_bytes\":0,\"verified_pixels\":%u}\n",
      frame, width, height, a.kind ? "rects" : "pixels", (unsigned long long)(ready-begin),
      bend_gpui_probe_commands, (unsigned long long)bend_gpui_probe_execution,
      (unsigned long long)((command.GPUEndTime-command.GPUStartTime)*1e9),
      (unsigned long long)(done-wait), (unsigned long long)(done-ready),
      (unsigned long long)(dropped-done), (unsigned long long)(dropped-begin), verified);
    fflush(stdout);
    return 0;
  }
}

static uint32_t gpui_option(const char *name, uint32_t fallback, uint32_t low, uint32_t high) {
  const char *value = getenv(name); if (!value) return fallback;
  char *end = NULL; unsigned long n = strtoul(value, &end, 10);
  if (!*value || *end || n < low || n > high) err_fail("invalid BEND_GPUI option");
  return (uint32_t)n;
}

static Term gpui_run_effect(Env e, Term *f, IoWork *w) {
  (void)w;
  if (![NSThread isMainThread]) err_fail("GPUI must run on the main thread");
  BendGpuiConfig config = {BEND_GPUI_ABI_VERSION, gpui_option("BEND_GPUI_WIDTH", (u32)f[0], 2, 2048) & ~1u,
    gpui_option("BEND_GPUI_HEIGHT", (u32)f[1], 2, 2048) & ~1u,
    gpui_option("BEND_GPUI_FRAMES", (u32)f[2], 0, 10000)};
  GpuiState state = {.env = e, .draw = f[3], .verify = getenv("BEND_GPUI_VERIFY") != NULL,
    .profile = config.max_frames != 0 || getenv("BEND_GPUI_PROFILE") != NULL};
#ifndef BEND_GPUI_VERIFY_HEADER
  if (state.verify) err_fail("this application has no frame verifier");
#endif
  if (!gpui_init(&state)) err_fail("GPUI adapter initialization failed");
  if (getenv("BEND_GPUI_HEADLESS")) {
    if (!config.max_frames) err_fail("headless GPUI requires a finite frame count");
    for (uint32_t frame = 0; frame < config.max_frames; ++frame) {
      void *pixel;
      if (gpui_draw(&state, config.width, config.height, frame, &pixel)) err_fail("GPUI frame failed");
    }
  } else if (bend_gpui_run(&config, &state, gpui_draw)) err_fail("GPUI application failed");
  if (state.previous) CVPixelBufferRelease(state.previous);
  if (state.cache) CFRelease(state.cache);
  term_drop(e, state.draw);
  return term_pak(CID(Unit), 0);
}

static void __attribute__((constructor)) gpui_register(void) {
  _Static_assert(sizeof(BendGpuiConfig) == 16, "GPUI ABI layout");
  if (cid_arity(CID(Tick)) != 3 || cid_arity(CID(Pixels)) != 3 ||
      cid_arity(CID(Rects)) != 3) abort();
  io_eff(CID(run), gpui_run_effect, 0);
}
