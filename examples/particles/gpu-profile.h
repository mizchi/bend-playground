// Opt-in host diagnostics, included only in scratch generated C. The pinned
// runtime and embedded Metal program stay unchanged. M5 supports encoder-boundary
// timestamp sampling; splitting Bend's encoder is a profiling perturbation.
static bool particle_probe_active, particle_probe_requested;
static id<MTLCounterSampleBuffer> particle_probe_buffer;
static id<MTLFence> particle_probe_fence;
static id<MTLCommandBuffer> particle_probe_command;
static uint64_t particle_probe_cpu_before, particle_probe_gpu_before;
static uint32_t particle_probe_frame, particle_probe_count, particle_probe_jobs, particle_probe_rounds;
static const char *particle_probe_backend;
static NSMutableArray *particle_probe_dispatches;

static void particle_probe_json(NSDictionary *record) {
  NSError *error = nil;
  NSData *data = [NSJSONSerialization dataWithJSONObject:record options:0 error:&error];
  if (!data || error) err_fail("particle GPU profile serialization failed");
  printf("GPU_PROFILE %s\n", [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding].UTF8String);
}

static NSDictionary *particle_probe_pipeline(id<MTLComputePipelineState> pso, uint32_t dynamic) {
  return @{@"execution_width":@(pso.threadExecutionWidth),
    @"max_threads":@(pso.maxTotalThreadsPerThreadgroup),
    @"static_threadgroup_bytes":@(pso.staticThreadgroupMemoryLength),
    @"dynamic_threadgroup_bytes":@(dynamic)};
}

static void particle_probe_setup(id<MTLDevice> device, id<MTLComputePipelineState> compute) {
  particle_probe_requested = getenv("BEND_PARTICLE_GPU_PROFILE") != NULL;
  if (!particle_probe_requested && !getenv("BEND_PARTICLE_GPU_INFO")) return;
  NSMutableArray *sets = [NSMutableArray new];
  id<MTLCounterSet> timestamps = nil;
  for (id<MTLCounterSet> set in device.counterSets) {
    NSMutableArray *names = [NSMutableArray new];
    for (id<MTLCounter> counter in set.counters) [names addObject:counter.name];
    [sets addObject:@{@"name":set.name, @"counters":names}];
    if ([set.name isEqualToString:MTLCommonCounterSetTimestamp]) timestamps = set;
  }
  bool stage = [device supportsCounterSampling:MTLCounterSamplingPointAtStageBoundary];
  NSMutableDictionary *pipelines = [NSMutableDictionary dictionaryWithObject:
    particle_probe_pipeline(compute, 0) forKey:@"metal"];
  if (gpu_pso) pipelines[@"bend"] = particle_probe_pipeline(gpu_pso, TG_HOLD * 8);
  particle_probe_json(@{@"kind":@"gpu_metadata", @"device":device.name,
    @"counter_sets":sets, @"stage_boundary":@(stage),
    @"dispatch_boundary":@([device supportsCounterSampling:MTLCounterSamplingPointAtDispatchBoundary]),
    @"pipelines":pipelines, @"bend_threads_per_group":@(CUBE_T),
    @"bend_groups":@(CUBE_G), @"bend_lanes":@(LANES)});
  if (!particle_probe_requested) return;
  if (!stage || !timestamps) err_fail("GPU encoder timestamps unsupported");
  MTLCounterSampleBufferDescriptor *desc = [MTLCounterSampleBufferDescriptor new];
  desc.counterSet = timestamps; desc.storageMode = MTLStorageModeShared; desc.sampleCount = 8;
  NSError *error = nil;
  particle_probe_buffer = [device newCounterSampleBufferWithDescriptor:desc error:&error];
  if (!particle_probe_buffer || error) err_fail("GPU counter buffer failed");
  // Bend's heap is hazard-untracked. Encoder boundaries need an explicit GPU
  // fence; command-buffer order alone does not replace its original barrier.
  particle_probe_fence = [device newFence];
  if (!particle_probe_fence) err_fail("GPU probe fence failed");
}

static void particle_probe_begin(id<MTLDevice> device, uint32_t frame, uint32_t count,
    uint32_t jobs, uint32_t rounds, const char *backend) {
  particle_probe_active = particle_probe_requested;
  if (!particle_probe_active) return;
  particle_probe_frame = frame; particle_probe_count = count;
  particle_probe_jobs = jobs; particle_probe_rounds = rounds; particle_probe_backend = backend;
  particle_probe_dispatches = [NSMutableArray new];
  [device sampleTimestamps:&particle_probe_cpu_before gpuTimestamp:&particle_probe_gpu_before];
}

static id<MTLComputeCommandEncoder> particle_probe_encoder(id<MTLCommandBuffer> cb,
    const char *name, uint32_t pass, uint32_t groups, uint32_t threads) {
  NSUInteger index = particle_probe_dispatches.count;
  if (index >= 4) err_fail("too many GPU probe dispatches");
  MTLComputePassDescriptor *desc = [MTLComputePassDescriptor computePassDescriptor];
  desc.sampleBufferAttachments[0].sampleBuffer = particle_probe_buffer;
  desc.sampleBufferAttachments[0].startOfEncoderSampleIndex = index * 2;
  desc.sampleBufferAttachments[0].endOfEncoderSampleIndex = index * 2 + 1;
  [particle_probe_dispatches addObject:[@{@"name":@(name), @"pass_index":@(pass),
    @"groups":@(groups), @"threads":@(threads)} mutableCopy]];
  id<MTLComputeCommandEncoder> encoder = [cb computeCommandEncoderWithDescriptor:desc];
  if (index) [encoder waitForFence:particle_probe_fence];
  encoder.label = @(name);
  return encoder;
}

static void particle_probe_finish(id<MTLDevice> device) {
  if (!particle_probe_active) return;
  uint64_t cpu_after, gpu_after;
  [device sampleTimestamps:&cpu_after gpuTimestamp:&gpu_after];
  NSUInteger count = particle_probe_dispatches.count;
  NSData *data = [particle_probe_buffer resolveCounterRange:NSMakeRange(0, count * 2)];
  if (!count || data.length != count * 2 * sizeof(MTLCounterResultTimestamp))
    err_fail("incomplete GPU counter samples");
  const MTLCounterResultTimestamp *samples = data.bytes;
  for (NSUInteger i = 0; i < count; ++i) {
    particle_probe_dispatches[i][@"begin"] = @(samples[i * 2].timestamp);
    particle_probe_dispatches[i][@"end"] = @(samples[i * 2 + 1].timestamp);
  }
  particle_probe_json(@{@"kind":@"gpu_dispatch_profile", @"frame":@(particle_probe_frame),
    @"backend":@(particle_probe_backend), @"count":@(particle_probe_count),
    @"jobs":@(particle_probe_jobs), @"noise_rounds":@(particle_probe_rounds),
    @"cpu_before":@(particle_probe_cpu_before), @"gpu_before":@(particle_probe_gpu_before),
    @"cpu_after":@(cpu_after), @"gpu_after":@(gpu_after), @"dispatches":particle_probe_dispatches});
  particle_probe_active = false;
  particle_probe_command = nil;
  particle_probe_dispatches = nil;
}
