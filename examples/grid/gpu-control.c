#include "grid.h"
#include "gpu-profile.h"
#include <pthread.h>
#include <stdatomic.h>

typedef struct {
  const Node *node;
  float width, height;
  uint32_t pages, nodes, offset, threads, tick, finished;
  int stop;
  Box *boxes;
  atomic_uint next, errors;
  pthread_mutex_t lock;
  pthread_cond_t start, done;
} GridPool;

static void grid_control_work(GridPool *q) {
  Output out;
  for (;;) {
    uint32_t first = atomic_fetch_add_explicit(&q->next, 16, memory_order_relaxed);
    if (first >= q->pages) break;
    uint32_t end = first + 16 < q->pages ? first + 16 : q->pages;
    for (uint32_t i = first; i < end; ++i) {
      grid_run(q->node, q->width + (float)((q->offset + i) % 97), q->height, &out);
      if (out.count != q->nodes || out.errors) atomic_fetch_add(&q->errors, 1);
      else memcpy(q->boxes + (size_t)i * q->nodes, out.boxes, q->nodes * sizeof(Box));
    }
  }
}

static void *grid_control_worker(void *arg) {
  GridPool *q = arg;
  uint32_t tick = 0;
  pthread_mutex_lock(&q->lock);
  for (;;) {
    while (!q->stop && tick == q->tick) pthread_cond_wait(&q->start, &q->lock);
    if (q->stop) break;
    tick = q->tick;
    pthread_mutex_unlock(&q->lock);
    grid_control_work(q);
    pthread_mutex_lock(&q->lock);
    if (++q->finished == q->threads) pthread_cond_signal(&q->done);
  }
  pthread_mutex_unlock(&q->lock);
  return NULL;
}

static int grid_control(int argc, char **argv, const Node *node, float width, float height,
    uint32_t pages, uint32_t nodes, uint32_t rounds) {
  unsigned threads = 1;
  if (argc != 1) {
    if (argc != 3 || strcmp(argv[1], "--threads")) return 2;
    char *end;
    long value = strtol(argv[2], &end, 10);
    if (end == argv[2] || *end || value < 1 || value > 128) return 2;
    threads = (unsigned)value;
  }
  GridPool q = {.node=node, .width=width, .height=height, .pages=pages, .nodes=nodes,
    .threads=threads, .lock=PTHREAD_MUTEX_INITIALIZER,
    .start=PTHREAD_COND_INITIALIZER, .done=PTHREAD_COND_INITIALIZER};
  q.boxes = malloc((size_t)pages * nodes * sizeof(Box));
  if (!q.boxes) abort();
  pthread_t workers[128];
  if (threads > 1) for (unsigned i = 0; i < threads; ++i)
    if (pthread_create(&workers[i], NULL, grid_control_worker, &q)) abort();
  for (uint32_t round = 0; round < rounds; ++round) {
    GridProfile p;
    grid_profile_start(&p, pages, nodes, round);
    q.offset = round * pages;
    atomic_store(&q.next, 0); atomic_store(&q.errors, 0);
    uint64_t begin = grid_clock();
    if (threads == 1) grid_control_work(&q);
    else {
      pthread_mutex_lock(&q.lock);
      q.finished = 0; q.tick++;
      pthread_cond_broadcast(&q.start);
      while (q.finished != threads) pthread_cond_wait(&q.done, &q.lock);
      pthread_mutex_unlock(&q.lock);
    }
    uint64_t ready = grid_clock();
    p.errors = atomic_load(&q.errors);
    for (uint32_t i = 0; i < pages; ++i) for (uint32_t j = 0; j < nodes; ++j) {
      const Box *b = &q.boxes[(size_t)i * nodes + j];
      grid_profile_put(&p, i, b->id, b->x, b->y, b->width, b->height);
    }
    uint64_t copied = grid_clock();
    uint32_t hash = grid_profile_hash(&p);
    uint64_t hashed = grid_clock();
    grid_profile_report(&p, ready-begin, copied-ready, hashed-copied, 0, hash, 0, 0, 0, 0);
  }
  if (threads > 1) {
    pthread_mutex_lock(&q.lock); q.stop = 1;
    pthread_cond_broadcast(&q.start); pthread_mutex_unlock(&q.lock);
    for (unsigned i = 0; i < threads; ++i) pthread_join(workers[i], NULL);
  }
  free(q.boxes);
  return 0;
}
