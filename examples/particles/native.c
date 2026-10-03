#include "abi.h"
#include "oracle.h"
#include "cpu.h"
#include "particle-config.h"
#include "particle-source.h"
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#import <CoreVideo/CoreVideo.h>

typedef struct { uint32_t count, rounds, width, height; float radius; uint32_t jobs; } ParticleArgs;
_Static_assert(sizeof(ParticleArgs) == 24, "Metal particle argument layout");
typedef struct { uint32_t width, height, kind, count; } ConvertArgs;
typedef enum { PARTICLE_CPU, PARTICLE_BEND_GPU, PARTICLE_METAL, PARTICLE_C_CPU, PARTICLE_C_DIRECT } ParticleBackend;
typedef struct {
  Env env;
  Term update, buffer;
  uint32_t count, depth;
  uint64_t offset, prepare_ns;
  ParticleBackend backend;
  id<MTLDevice> device;
  id<MTLCommandQueue> queue;
  id<MTLBuffer> input;
  NSUInteger input_offset;
  id<MTLComputePipelineState> compute, convert;
  id<MTLRenderPipelineState> render;
  id<MTLTexture> color;
  CVMetalTextureCacheRef cache;
  CVPixelBufferPoolRef pool;
  CVPixelBufferRef previous;
  Particle *oracle;
  ParticleCPU *cpu;
  const char *mapping;
  bool profile;
  const char *dump;
} ParticleState;

static uint64_t particle_clock(void) {
  struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t);
  return (uint64_t)t.tv_sec * 1000000000ull + t.tv_nsec;
}

static uint64_t particle_gpu_time(id<MTLCommandBuffer> command) {
  return (uint64_t)((command.GPUEndTime - command.GPUStartTime) * 1e9);
}

static uint32_t particle_option(const char *name, uint32_t fallback, uint32_t low, uint32_t high) {
  const char *value = getenv(name); if (!value) return fallback;
  char *end = NULL; unsigned long n = strtoul(value, &end, 10);
  if (!*value || *end || n < low || n > high) err_fail("invalid BEND_PARTICLE option");
  return (uint32_t)n;
}

static void particle_command_ok(id<MTLCommandBuffer> command) {
  if (command.error) {
    fprintf(stderr, "Particle Metal: %s\n", command.error.localizedDescription.UTF8String);
    err_fail("particle command failed");
  }
}

static Term particle_apply(Env e, Term closure, Term argument) {
  // The pinned compiler registers its runtime segments after reading effect
  // sources. FID(Clo~apply) then fails if Bend code makes no dynamic calls.
  // Use the generated runtime macro, which exists in both code variants.
  uint64_t at = task_node(e, FID_CLO_APPLY, TERM_HOLE, 0, 0);
  e.mem[at] = closure; e.mem[at + 1] = argument;
  Term result = corpus_eval(e.mem, term_tsk(FID_CLO_APPLY, at));
  if (err_seen(e.mem)) err_fail("particle Bend evaluation failed");
  return result;
}

static void particle_init(ParticleState *s) {
  s->device = gpu_dev ?: MTLCreateSystemDefaultDevice();
  s->queue = [s->device newCommandQueue];
  NSError *error = nil;
  MTLCompileOptions *options = [MTLCompileOptions new];
  options.mathMode = MTLMathModeSafe;
  options.mathFloatingPointFunctions = MTLMathFloatingPointFunctionsPrecise;
  id<MTLLibrary> library = [s->device newLibraryWithSource:
    [NSString stringWithUTF8String:particle_shader_source] options:options error:&error];
  s->mapping = getenv("BEND_PARTICLE_METAL_MAPPING") ?: "particle";
  NSString *kernel;
  if (!strcmp(s->mapping, "particle")) kernel = @"particle_update";
  else if (!strcmp(s->mapping, "tiled")) kernel = @"particle_update_tiled";
  else if (!strcmp(s->mapping, "strided")) kernel = @"particle_update_strided";
#ifdef PARTICLE_GPU_PROBE
  else if (!strcmp(s->mapping, "leaf")) kernel = @"particle_bend_leaf";
#endif
  else err_fail("invalid particle Metal mapping");
  if (s->backend != PARTICLE_METAL && strcmp(s->mapping, "particle"))
    err_fail("particle Metal mapping requires Metal backend");
  id<MTLLibrary> update_library = library;
#ifdef PARTICLE_GPU_PROBE
  if (!strcmp(s->mapping, "leaf")) {
    MTLCompileOptions *leaf_options = [MTLCompileOptions new];
    leaf_options.mathMode = MTLMathModeSafe;
    leaf_options.preprocessorMacros = @{@"CUBE_LOG":@(CUBE_LOG)};
    update_library = [s->device newLibraryWithSource:@(BEND_SRC) options:leaf_options error:&error];
  }
#endif
  s->compute = [s->device newComputePipelineStateWithFunction:
    [update_library newFunctionWithName:kernel] error:&error];
  s->convert = [s->device newComputePipelineStateWithFunction:
    [library newFunctionWithName:@"convert"] error:&error];
  MTLRenderPipelineDescriptor *render = [MTLRenderPipelineDescriptor new];
  render.vertexFunction = [library newFunctionWithName:@"particle_vertex"];
  render.fragmentFunction = [library newFunctionWithName:@"particle_fragment"];
  render.colorAttachments[0].pixelFormat = MTLPixelFormatBGRA8Unorm;
  render.colorAttachments[0].blendingEnabled = YES;
  render.colorAttachments[0].sourceRGBBlendFactor = MTLBlendFactorSourceAlpha;
  render.colorAttachments[0].destinationRGBBlendFactor = MTLBlendFactorOne;
  render.colorAttachments[0].sourceAlphaBlendFactor = MTLBlendFactorZero;
  render.colorAttachments[0].destinationAlphaBlendFactor = MTLBlendFactorOne;
  s->render = [s->device newRenderPipelineStateWithDescriptor:render error:&error];
  if (!s->device || !s->queue || !s->compute || !s->convert || !s->render || error ||
      CVMetalTextureCacheCreate(NULL, NULL, s->device, NULL, &s->cache)) {
    fprintf(stderr, "Particle initialization: %s\n", error.localizedDescription.UTF8String);
    err_fail("particle Metal initialization failed");
  }
#ifdef PARTICLE_GPU_PROBE
  particle_probe_setup(s->device, s->compute);
#endif
  uint64_t begin = particle_clock();
  while ((1ull << s->depth) < (uint64_t)s->count * 8) ++s->depth;
  Term zero = f32_rewrap(0);
  s->buffer = blk_new(s->env, false, s->depth, 0, 1, &zero);
  if (err_seen(s->env.mem)) err_fail("particle state allocation failed");
  s->offset = blk_loc(s->env.mem, s->buffer) * sizeof(uint64_t);
  unsigned char *bytes = (unsigned char *)s->env.mem + s->offset;
  for (uint32_t i = 0; i < s->count; ++i) {
    Particle p = particle_initial(i); memcpy(bytes + (size_t)i * sizeof p, &p, sizeof p);
  }
  // Unused capacity is a canary; all update paths must respect count.
  uint32_t canary = 0x7fc12345;
  for (uint64_t i = (uint64_t)s->count * 8; i < (1ull << s->depth); ++i)
    memcpy(bytes + i * 4, &canary, 4);
  s->input = gpu_buf;
  s->input_offset = s->offset;
  if (!s->input) {
    uintptr_t ptr = (uintptr_t)bytes, base = ptr & ~(uintptr_t)16383;
    size_t length = (ptr - base + (4ull << s->depth) + 16383) & ~(size_t)16383;
    s->input = [s->device newBufferWithBytesNoCopy:(void *)base length:length
      options:MTLResourceStorageModeShared deallocator:nil];
    s->input_offset = ptr - base;
  }
  if (!s->input) err_fail("particle shared buffer import failed");
  if (s->backend == PARTICLE_C_CPU) {
    s->cpu = particle_cpu_create(pool_size);
    if (!s->cpu) err_fail("particle C worker pool failed");
  }
  s->prepare_ns = particle_clock() - begin;
  if (getenv("BEND_PARTICLE_VERIFY")) {
    s->oracle = malloc((size_t)s->count * sizeof(Particle));
    if (!s->oracle) err_fail("particle oracle allocation failed");
    for (uint32_t i = 0; i < s->count; ++i) s->oracle[i] = particle_initial(i);
  }
}

static void particle_output(ParticleState *s, uint32_t width, uint32_t height) {
  if (s->color && s->color.width == width && s->color.height == height) return;
  if (s->pool) { CVPixelBufferPoolRelease(s->pool); s->pool = NULL; }
  MTLTextureDescriptor *desc = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:
    MTLPixelFormatBGRA8Unorm width:width height:height mipmapped:NO];
  desc.storageMode = MTLStorageModePrivate;
  desc.usage = MTLTextureUsageRenderTarget | MTLTextureUsageShaderRead;
  s->color = [s->device newTextureWithDescriptor:desc];
  NSDictionary *attributes = @{
    (__bridge NSString *)kCVPixelBufferPixelFormatTypeKey: @(kCVPixelFormatType_420YpCbCr8BiPlanarFullRange),
    (__bridge NSString *)kCVPixelBufferWidthKey: @(width),
    (__bridge NSString *)kCVPixelBufferHeightKey: @(height),
    (__bridge NSString *)kCVPixelBufferMetalCompatibilityKey: @YES,
    (__bridge NSString *)kCVPixelBufferIOSurfacePropertiesKey: @{}
  };
  NSDictionary *pool_attributes = @{(__bridge NSString *)kCVPixelBufferPoolMinimumBufferCountKey: @3};
  if (!s->color || CVPixelBufferPoolCreate(NULL, (__bridge CFDictionaryRef)pool_attributes,
      (__bridge CFDictionaryRef)attributes, &s->pool)) err_fail("particle surface pool failed");
  CVPixelBufferRef warm[3] = {NULL, NULL, NULL};
  for (int i = 0; i < 3; ++i)
    if (CVPixelBufferPoolCreatePixelBuffer(NULL, s->pool, &warm[i])) err_fail("particle pool warmup failed");
  for (int i = 0; i < 3; ++i) CVPixelBufferRelease(warm[i]);
}

static void particle_verify(ParticleState *s, CVPixelBufferRef pixel, uint32_t frame) {
  // Verification is explicitly outside frame timing. The production path does
  // not load particle payload on the CPU (apart from its CPU simulation mode).
  unsigned char *bytes = (unsigned char *)s->env.mem + s->offset;
  for (uint32_t i = 0; i < s->count; ++i) {
    s->oracle[i] = particle_reference(s->oracle[i], PARTICLE_NOISE_ROUNDS);
    Particle actual; memcpy(&actual, bytes + (size_t)i * sizeof actual, sizeof actual);
    float a[8], b[8]; memcpy(a, &actual, sizeof a); memcpy(b, &s->oracle[i], sizeof b);
    for (uint32_t j = 0; j < 8; ++j) if (!isfinite(a[j]) ||
        (j >= 5 ? a[j] != b[j] : fabsf(a[j] - b[j]) > 0.000002f)) {
      fprintf(stderr, "Particle oracle mismatch frame=%u particle=%u field=%u: %.9g != %.9g\n",
        frame, i, j, a[j], b[j]); err_fail("particle verification failed");
    }
  }
  for (uint64_t i = (uint64_t)s->count * 8; i < (1ull << s->depth); ++i) {
    uint32_t word; memcpy(&word, bytes + i * 4, 4);
    if (word != 0x7fc12345) err_fail("particle capacity canary overwritten");
  }
  if (!s->dump) return;
  char path[4096];
  if (snprintf(path, sizeof path, "%s/%u.particles", s->dump, frame) >= sizeof path)
    err_fail("particle dump path too long");
  FILE *file = fopen(path, "wb");
  size_t n = (size_t)s->count * sizeof(Particle);
  if (!file || fwrite(bytes, 1, n, file) != n || fclose(file)) err_fail("particle dump failed");
  if (CVPixelBufferLockBaseAddress(pixel, kCVPixelBufferLock_ReadOnly)) err_fail("particle image lock failed");
  if (snprintf(path, sizeof path, "%s/%u.nv12", s->dump, frame) >= sizeof path)
    err_fail("particle dump path too long");
  file = fopen(path, "wb");
  if (!file) err_fail("particle image dump failed");
  for (uint32_t plane = 0; plane < 2; ++plane) {
    unsigned char *base = CVPixelBufferGetBaseAddressOfPlane(pixel, plane);
    size_t stride = CVPixelBufferGetBytesPerRowOfPlane(pixel, plane);
    size_t width = CVPixelBufferGetWidth(pixel), height = CVPixelBufferGetHeightOfPlane(pixel, plane);
    for (size_t y = 0; y < height; ++y)
      if (fwrite(base + y * stride, 1, width, file) != width) err_fail("particle image write failed");
  }
  if (fclose(file)) err_fail("particle image close failed");
  CVPixelBufferUnlockBaseAddress(pixel, kCVPixelBufferLock_ReadOnly);
}

static int32_t particle_draw(void *context, uint32_t width, uint32_t height,
    uint32_t frame, void **pixel_buffer) {
  ParticleState *s = context;
  if (width < 2 || height < 2 || width > 2048 || height > 2048 || ((width | height) & 1)) return 1;
  @autoreleasepool {
    uint64_t begin = particle_clock();
    particle_output(s, width, height);
    CVPixelBufferRef pixel = NULL;
    CVMetalTextureRef yt = NULL, uvt = NULL;
    if (CVPixelBufferPoolCreatePixelBuffer(NULL, s->pool, &pixel) ||
        CVMetalTextureCacheCreateTextureFromImage(NULL, s->cache, pixel, NULL,
          MTLPixelFormatR8Unorm, width, height, 0, &yt) ||
        CVMetalTextureCacheCreateTextureFromImage(NULL, s->cache, pixel, NULL,
          MTLPixelFormatRG8Unorm, width/2, height/2, 1, &uvt)) err_fail("particle surface allocation failed");
    uint64_t prepared = particle_clock();
    ParticleArgs args = {s->count, PARTICLE_NOISE_ROUNDS, width, height, 2, PARTICLE_JOBS};
    grid_probe_commands = 0; grid_probe_execution = grid_probe_wait = grid_probe_submit = 0;
    uint64_t update_gpu = 0, update_wait = 0;
    ParticleCPUStats cpu_stats = {0};
#ifdef PARTICLE_GPU_PROBE
    particle_probe_begin(s->device, frame, s->count, PARTICLE_JOBS, PARTICLE_NOISE_ROUNDS,
      s->backend == PARTICLE_BEND_GPU ? "bend-gpu" : "metal");
#endif
    if (s->backend == PARTICLE_C_CPU || s->backend == PARTICLE_C_DIRECT) {
      Particle *state = (Particle *)((unsigned char *)s->env.mem + s->offset);
      int result = s->cpu ? particle_cpu_run(s->cpu, state, s->count, PARTICLE_JOBS, PARTICLE_NOISE_ROUNDS, &cpu_stats)
        : particle_cpu_direct(state, s->count, PARTICLE_JOBS, PARTICLE_NOISE_ROUNDS, &cpu_stats);
      if (result || cpu_stats.completed_jobs != PARTICLE_JOBS || !cpu_stats.workers_used)
        err_fail("particle C update failed");
    } else if (s->backend == PARTICLE_METAL) {
      id<MTLCommandBuffer> command = [s->queue commandBuffer];
      uint32_t lanes = !strcmp(s->mapping, "particle") ? s->count : PARTICLE_JOBS;
      uint32_t group_threads = !strcmp(s->mapping, "particle") ? 64 : 128;
#ifdef PARTICLE_GPU_PROBE
      id<MTLComputeCommandEncoder> encoder = particle_probe_active
        ? particle_probe_encoder(command, s->mapping, 0, (lanes + group_threads - 1) / group_threads, group_threads)
        : [command computeCommandEncoder];
#else
      id<MTLComputeCommandEncoder> encoder = [command computeCommandEncoder];
#endif
      [encoder setComputePipelineState:s->compute];
#ifdef PARTICLE_GPU_PROBE
      if (!strcmp(s->mapping, "leaf")) {
        struct { uint64_t buffer; uint32_t count, jobs, rounds, reserved; } leaf_args =
          {s->buffer, s->count, PARTICLE_JOBS, PARTICLE_NOISE_ROUNDS, 0};
        _Static_assert(sizeof(leaf_args) == 24, "Bend leaf argument layout");
        [encoder setBuffer:gpu_buf offset:0 atIndex:0];
        [encoder setBytes:&leaf_args length:sizeof leaf_args atIndex:1];
      } else
#endif
      {
        [encoder setBuffer:s->input offset:s->input_offset atIndex:0];
        [encoder setBytes:&args length:sizeof args atIndex:1];
      }
      [encoder dispatchThreads:MTLSizeMake(lanes, 1, 1) threadsPerThreadgroup:MTLSizeMake(group_threads, 1, 1)];
      [encoder endEncoding]; [command commit];
      uint64_t waiting = particle_clock(); [command waitUntilCompleted];
      update_wait = particle_clock() - waiting;
      particle_command_ok(command); update_gpu = particle_gpu_time(command);
#ifdef PARTICLE_GPU_PROBE
      if (!strcmp(s->mapping, "leaf") && a32_load(a32_at(s->env.mem, H_ERROR_CODE)))
        err_fail("direct Bend GPU leaf failed");
#endif
    } else {
      Env e = s->env;
      s->update = term_keep(e, s->update, 1);
      uint64_t at = heap_alloc(e, cls_fit(2)); e.mem[at] = s->count; e.mem[at + 1] = frame;
      Term closure = particle_apply(e, s->update, term_ctr(CID(api.Tick), at));
      s->buffer = particle_apply(e, closure, s->buffer);
      if (term_tag(s->buffer) != TAG_BUF || blk_cls(s->buffer) != s->depth ||
          blk_loc(e.mem, s->buffer) * sizeof(uint64_t) != s->offset)
        err_fail("particle callback must preserve its state allocation");
      update_gpu = grid_probe_execution; update_wait = grid_probe_wait;
      if ((s->backend == PARTICLE_BEND_GPU) != (grid_probe_commands != 0))
        err_fail("particle backend fallback");
    }
#ifdef PARTICLE_GPU_PROBE
    particle_probe_finish(s->device);
#endif
    uint64_t updated = particle_clock();
    // Same rendering path for all backends. Render and conversion use one queue;
    // conversion depends on the completed render command, without a CPU wait
    // between them. Waiting only for conversion also covers the render command.
    id<MTLCommandBuffer> draw_command = [s->queue commandBuffer];
    MTLRenderPassDescriptor *pass = [MTLRenderPassDescriptor renderPassDescriptor];
    pass.colorAttachments[0].texture = s->color;
    pass.colorAttachments[0].loadAction = MTLLoadActionClear;
    pass.colorAttachments[0].storeAction = MTLStoreActionStore;
    pass.colorAttachments[0].clearColor = MTLClearColorMake(16.0/255, 23.0/255, 36.0/255, 1);
    id<MTLRenderCommandEncoder> draw = [draw_command renderCommandEncoderWithDescriptor:pass];
    [draw setRenderPipelineState:s->render];
    [draw setVertexBuffer:s->input offset:s->input_offset atIndex:0];
    [draw setVertexBytes:&args length:sizeof args atIndex:1];
    [draw drawPrimitives:MTLPrimitiveTypeTriangle vertexStart:0 vertexCount:6 instanceCount:s->count];
    [draw endEncoding]; [draw_command commit];
    id<MTLCommandBuffer> command = [s->queue commandBuffer];
    id<MTLComputeCommandEncoder> convert = [command computeCommandEncoder];
    ConvertArgs ca = {width, height, 1, s->count};
    [convert setComputePipelineState:s->convert];
    [convert setBuffer:s->input offset:s->input_offset atIndex:0];
    [convert setBytes:&ca length:sizeof ca atIndex:1];
    [convert setTexture:CVMetalTextureGetTexture(yt) atIndex:0];
    [convert setTexture:CVMetalTextureGetTexture(uvt) atIndex:1];
    [convert setTexture:s->color atIndex:2];
    [convert dispatchThreads:MTLSizeMake(width/2, height/2, 1) threadsPerThreadgroup:MTLSizeMake(8, 8, 1)];
    [convert endEncoding]; [command commit];
    uint64_t waiting = particle_clock(); [command waitUntilCompleted];
    uint64_t done = particle_clock();
    particle_command_ok(draw_command); particle_command_ok(command);
    CFRelease(yt); CFRelease(uvt);
    CVMetalTextureCacheFlush(s->cache, 0);
    if (s->previous) CVPixelBufferRelease(s->previous);
    s->previous = pixel; *pixel_buffer = pixel;
    uint64_t ready = particle_clock();
    uint64_t verify_begin = ready;
    if (s->oracle) particle_verify(s, pixel, frame);
    uint64_t verified = particle_clock();
    const char *backend = s->backend == PARTICLE_CPU ? "bend-cpu" :
      s->backend == PARTICLE_BEND_GPU ? "bend-gpu" : s->backend == PARTICLE_METAL ? "metal" :
      s->backend == PARTICLE_C_CPU ? "c-cpu" : "c-direct";
    if (s->profile) printf("{\"frame\":%u,\"width\":%u,\"height\":%u,\"count\":%u,"
      "\"backend\":\"%s\",\"noise_rounds\":%u,\"jobs\":%u,\"threads\":%u,\"radius_px\":2,"
      "\"c_completed_jobs\":%u,\"c_workers_used\":%u,"
      "\"buffer_offset\":%llu,\"buffer_bytes\":%llu,\"state_allocations\":1,\"state_prepare_ns\":%llu,"
      "\"surface_prepare_ns\":%llu,\"update_ns\":%llu,\"update_gpu_ns\":%llu,\"update_wait_ns\":%llu,"
      "\"bend_gpu_commands\":%u,\"bend_gpu_submit_ns\":%llu,"
      "\"draw_gpu_ns\":%llu,\"convert_gpu_ns\":%llu,\"render_wait_ns\":%llu,"
      "\"render_ns\":%llu,\"release_ns\":%llu,\"frame_ready_ns\":%llu,"
      "\"cpu_readback_bytes\":0,\"verified_particles\":%u,\"verify_ns\":%llu}\n",
      frame, width, height, s->count, backend, PARTICLE_NOISE_ROUNDS, PARTICLE_JOBS,
      s->backend == PARTICLE_C_DIRECT ? 1 : pool_size, cpu_stats.completed_jobs, cpu_stats.workers_used,
      (unsigned long long)s->offset, (unsigned long long)(4ull << s->depth),
      (unsigned long long)s->prepare_ns, (unsigned long long)(prepared-begin),
      (unsigned long long)(updated-prepared), (unsigned long long)update_gpu, (unsigned long long)update_wait,
      grid_probe_commands, (unsigned long long)grid_probe_submit, (unsigned long long)particle_gpu_time(draw_command),
      (unsigned long long)particle_gpu_time(command), (unsigned long long)(done-waiting),
      (unsigned long long)(done-updated), (unsigned long long)(ready-done), (unsigned long long)(ready-begin),
      s->oracle ? s->count : 0, (unsigned long long)(verified-verify_begin));
    fflush(stdout);
    return 0;
  }
}

static Term particle_run_effect(Env e, Term *f, IoWork *w) {
  (void)w;
  if (![NSThread isMainThread]) err_fail("particles require the main thread");
  BendGpuiConfig config = {1,
    particle_option("BEND_PARTICLE_WIDTH", (uint32_t)f[0], 2, 2048) & ~1u,
    particle_option("BEND_PARTICLE_HEIGHT", (uint32_t)f[1], 2, 2048) & ~1u,
    particle_option("BEND_PARTICLE_FRAMES", (uint32_t)f[3], 0, 10000)};
  const char *backend = getenv("BEND_PARTICLE_BACKEND") ?: "bend-cpu";
  ParticleBackend mode;
  if (!strcmp(backend, "bend-cpu")) mode = PARTICLE_CPU;
  else if (!strcmp(backend, "bend-gpu")) mode = PARTICLE_BEND_GPU;
  else if (!strcmp(backend, "metal")) mode = PARTICLE_METAL;
  else if (!strcmp(backend, "c-cpu")) mode = PARTICLE_C_CPU;
  else if (!strcmp(backend, "c-direct")) mode = PARTICLE_C_DIRECT;
  else err_fail("invalid particle backend");
  bool direct_leaf = false;
#ifdef PARTICLE_GPU_PROBE
  direct_leaf = mode == PARTICLE_METAL && getenv("BEND_PARTICLE_METAL_MAPPING") &&
    !strcmp(getenv("BEND_PARTICLE_METAL_MAPPING"), "leaf");
#endif
  if ((mode == PARTICLE_BEND_GPU || direct_leaf) != io_gpu) err_fail("particle GPU option mismatch");
  ParticleState state = {.env = e, .update = f[4], .backend = mode,
    .count = particle_option("BEND_PARTICLE_COUNT", (uint32_t)f[2], 1, 1000000),
    .profile = config.max_frames != 0 || getenv("BEND_PARTICLE_PROFILE") != NULL,
    .dump = getenv("BEND_PARTICLE_DUMP")};
  if (state.dump && !getenv("BEND_PARTICLE_VERIFY")) err_fail("particle dump requires verification");
  particle_init(&state);
  if (getenv("BEND_PARTICLE_HEADLESS")) {
    if (!config.max_frames) err_fail("headless particles require finite frames");
    for (uint32_t frame = 0; frame < config.max_frames; ++frame) {
      void *pixel;
      if (particle_draw(&state, config.width, config.height, frame, &pixel)) err_fail("particle frame failed");
    }
  } else if (bend_gpui_run(&config, &state, particle_draw)) err_fail("particle window failed");
  if (state.previous) CVPixelBufferRelease(state.previous);
  if (state.pool) CVPixelBufferPoolRelease(state.pool);
  if (state.cache) CFRelease(state.cache);
  free(state.oracle);
  particle_cpu_destroy(state.cpu);
  term_drop(e, state.buffer); term_drop(e, state.update);
  return term_pak(CID(Unit), 0);
}

static void __attribute__((constructor)) particle_register(void) {
  // Effect constructors include the runtime continuation after the five args.
  if (cid_arity(CID(api.Tick)) != 2 || cid_arity(CID(run)) != 6) abort();
  io_eff(CID(run), particle_run_effect, 0);
}
