// C twin of sat-core.bend: immutable clauses, same scan and branch order.
#ifndef SAT_CORE_H
#define SAT_CORE_H
#include <pthread.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

typedef struct { uint32_t pos, neg; } Clause;
typedef struct { uint32_t sat, model, nodes, errors; } Answer;
typedef struct { unsigned kind; uint32_t bit, yes, no; } Check;

static Check sat_scan(const Clause *clauses, size_t count, uint32_t yes, uint32_t no) {
  uint32_t choice = 0;
  for (size_t i = 0; i < count; ++i) {
    uint32_t pos = clauses[i].pos, neg = clauses[i].neg;
    if ((pos & yes) | (neg & no) | (pos & neg)) continue;
    uint32_t remaining = (pos | neg) & ~(yes | no);
    if (!remaining) return (Check){1, 0, 0, 0};
    if (!(remaining & (remaining - 1u))) return (Check){2, 0, remaining & pos, remaining & ~pos};
    if (!choice) choice = remaining & (0u - remaining);
  }
  return (Check){choice ? 3u : 0u, choice, 0, 0};
}

static Answer sat_search(const Clause *clauses, size_t count, uint32_t yes, uint32_t no, unsigned fuel) {
  if (!fuel) return (Answer){0, 0, 1, 1};
  Check state = {0};
  unsigned propagation;
  for (propagation = 0; propagation < 33; ++propagation) {
    state = sat_scan(clauses, count, yes, no);
    if (state.kind != 2) break;
    yes |= state.yes; no |= state.no;
  }
  if (propagation == 33) return (Answer){0, 0, 1, 1};
  if (state.kind == 1) return (Answer){0, 0, 1, 0};
  if (state.kind == 0) return (Answer){1, yes, 1, 0};
  Answer first = sat_search(clauses, count, yes | state.bit, no, fuel - 1);
  if (first.sat || first.errors) { ++first.nodes; return first; }
  Answer second = sat_search(clauses, count, yes, no | state.bit, fuel - 1);
  second.nodes += first.nodes + 1u;
  return second;
}

static Answer sat_solve(const Clause *clauses, size_t count, uint32_t yes, uint32_t no) {
  return sat_search(clauses, count, yes, no, 33);
}

static int sat_holds(const Clause *clauses, size_t count, uint32_t model) {
  for (size_t i = 0; i < count; ++i)
    if (!((clauses[i].pos & model) | (clauses[i].neg & ~model))) return 0;
  return 1;
}

static Answer sat_merge(Answer a, Answer b) {
  uint32_t nodes = a.nodes + b.nodes;
  if (a.errors || b.errors) return (Answer){0, 0, nodes, 1};
  if (b.sat && (!a.sat || b.model < a.model)) a = b;
  a.nodes = nodes;
  return a;
}

typedef struct {
  const Clause *clauses;
  size_t count;
  uint32_t jobs, mask;
  unsigned repetitions, threads, arrived, generation;
  pthread_mutex_t mutex;
  pthread_cond_t condition;
  atomic_uint next;
} SatQueue;
typedef struct { SatQueue *queue; Answer result; } SatWorker;

// macOS has no pthread_barrier_t. The last arrival resets the prefix queue;
// every worker finishes the current solve before starting its next repetition.
static void sat_barrier(SatQueue *queue) {
  if (queue->threads == 1) {
    atomic_store_explicit(&queue->next, 0, memory_order_relaxed);
    return;
  }
  pthread_mutex_lock(&queue->mutex);
  unsigned generation = queue->generation;
  if (++queue->arrived == queue->threads) {
    queue->arrived = 0;
    ++queue->generation;
    atomic_store_explicit(&queue->next, 0, memory_order_relaxed);
    pthread_cond_broadcast(&queue->condition);
  } else {
    while (generation == queue->generation) pthread_cond_wait(&queue->condition, &queue->mutex);
  }
  pthread_mutex_unlock(&queue->mutex);
}

static void *sat_worker(void *arg) {
  SatWorker *worker = arg;
  SatQueue *queue = worker->queue;
  Answer result = {0};
  for (unsigned r = 0; r < queue->repetitions; ++r) {
    for (;;) {
      uint32_t i = atomic_fetch_add_explicit(&queue->next, 1, memory_order_relaxed);
      if (i >= queue->jobs) break;
      result = sat_merge(result, sat_solve(queue->clauses, queue->count, i, queue->mask ^ i));
    }
    if (r + 1 < queue->repetitions) sat_barrier(queue);
  }
  worker->result = result;
  return NULL;
}

static Answer sat_repeat_partition(const Clause *clauses, size_t count, unsigned depth, unsigned threads,
                                   unsigned repetitions) {
  uint32_t jobs = 1u << depth;
  if (threads > jobs) threads = jobs;
  SatQueue queue = {.clauses = clauses, .count = count, .jobs = jobs, .mask = jobs - 1u,
                   .repetitions = repetitions, .threads = threads};
  atomic_init(&queue.next, 0);
  if (pthread_mutex_init(&queue.mutex, NULL) || pthread_cond_init(&queue.condition, NULL)) {
    fprintf(stderr, "SAT barrier initialization failed\n"); exit(1);
  }
  SatWorker workers[128] = {0};
  pthread_t handles[127];
  for (unsigned i = 0; i < threads; ++i) workers[i].queue = &queue;
  for (unsigned i = 0; i + 1 < threads; ++i) {
    int error = pthread_create(&handles[i], NULL, sat_worker, &workers[i]);
    if (error) { fprintf(stderr, "pthread_create failed: %d\n", error); exit(1); }
  }
  sat_worker(&workers[threads - 1]);
  Answer total = {0};
  for (unsigned i = 0; i < threads; ++i) {
    if (i + 1 < threads) {
      int error = pthread_join(handles[i], NULL);
      if (error) { fprintf(stderr, "pthread_join failed: %d\n", error); exit(1); }
    }
    total = sat_merge(total, workers[i].result);
  }
  pthread_cond_destroy(&queue.condition);
  pthread_mutex_destroy(&queue.mutex);
  return total;
}

static Answer sat_partition(const Clause *clauses, size_t count, unsigned depth, unsigned threads) {
  return sat_repeat_partition(clauses, count, depth, threads, 1);
}

static void sat_show(Answer answer) {
  printf("status=%s model=%u nodes=%u errors=%u\n", answer.errors ? "UNKNOWN" : answer.sat ? "SAT" : "UNSAT",
         answer.model, answer.nodes, answer.errors);
}
#endif
