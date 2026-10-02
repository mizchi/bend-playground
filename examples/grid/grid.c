#include "grid.h"
#include <errno.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdlib.h>
#include <string.h>

typedef struct { uint32_t c, r, cs, rs; } Place;
typedef struct { float base, maximum, flex, active; } Cell;
static uint32_t umax(uint32_t a, uint32_t b) { return a > b ? a : b; }
static float fmax2(float a, float b) { return a > b ? a : b; }
static float fmin2(float a, float b) { return a < b ? a : b; }
static uint32_t mask(uint32_t c, uint32_t cs) { return (UINT32_MAX >> (32 - cs)) << c; }

static int clear(const uint32_t *occupied, uint32_t c, uint32_t r, uint32_t cs, uint32_t rs) {
  const uint32_t bits = mask(c, cs);
  for (uint32_t row = r; row < r + rs; ++row) if (occupied[row] & bits) return 0;
  return 1;
}

static int placement(const Node *node, Place *places, uint32_t *columns, uint32_t *rows) {
  uint32_t occupied[GRID_ROWS] = {0}, locked[GRID_ROWS] = {0}, cc = 0, cr = 0;
  *columns = node->style->nc; *rows = node->style->nr;
  for (uint32_t i = 0; i < node->count; ++i) {
    Item s = node->children[i]->item;
    *columns = umax(*columns, s.column ? s.column - 1 + s.cs : s.cs);
  }
  for (unsigned phase = 0; phase < 3; ++phase) {
    for (uint32_t i = 0; i < node->count; ++i) {
      const Item s = node->children[i]->item;
      int selected = phase == 0 ? s.column && s.row : phase == 1 ? !s.column && s.row : !s.row;
      if (!selected) continue;
      uint32_t c = s.column ? s.column - 1 : node->style->dense ? 0 : cc;
      uint32_t r = s.row ? s.row - 1 : node->style->dense ? 0 : cr;
      if (phase == 1) {
        c = 0;
        if (!node->style->dense) c = locked[r];
      }
      if (phase == 2 && !node->style->dense && s.column && c < cc) ++r;
      const unsigned mode = phase == 1 ? 1 : s.column ? 2 : 3;
      int found = phase == 0;
      for (unsigned step = 0; !found && step < 4256; ++step) {
        if (r + s.rs > GRID_ROWS) return 0;
        if (mode == 3 && c + s.cs > *columns) { c = 0; ++r; continue; }
        if (c + s.cs > GRID_COLUMNS) return 0;
        if (clear(occupied, c, r, s.cs, s.rs)) { found = 1; break; }
        if (mode == 2) ++r; else ++c;
      }
      if (!found || c + s.cs > GRID_COLUMNS || r + s.rs > GRID_ROWS) return 0;
      const uint32_t bits = mask(c, s.cs);
      for (uint32_t row = r; row < r + s.rs; ++row) {
        occupied[row] |= bits;

      }
      if (phase == 1) locked[r] = c + s.cs;
      places[i] = (Place){c, r, s.cs, s.rs};
      *columns = umax(*columns, c + s.cs); *rows = umax(*rows, r + s.rs);
      if (phase == 2) { cc = c; cr = r; }
    }
  }
  return 1;
}

static void tracks(const Track *explicit, uint32_t n_explicit, Track implicit,
                   uint32_t count, float available, float gap, float *prefix) {
  Cell cells[GRID_ROWS];
  const float space = fmax2(0, available - gap * (float)(umax(count, 1) - 1));
  for (uint32_t i = 0; i < count; ++i) {
    const Track t = i < n_explicit ? explicit[i] : implicit;
    cells[i] = (Cell){t.minimum, t.maximum, t.flex, t.flex};
  }
  for (unsigned pass = 0; pass < 129; ++pass) {
    float base = 0; uint32_t growing = 0;
    /* Match the Bend right fold, including its floating-point addition order. */
    for (uint32_t i = count; i-- > 0;) { base += cells[i].base; growing += cells[i].maximum > cells[i].base; }
    if (space - base <= .00001f || !growing) break;
    const float amount = (space - base) / (float)growing;
    for (uint32_t i = 0; i < count; ++i) cells[i].base = fmin2(cells[i].maximum, cells[i].base + amount);
  }
  float unit = 0;
  for (unsigned pass = 0; pass < 129; ++pass) {
    float fixed = 0, flex = 0;
    for (uint32_t i = count; i-- > 0;) {
      if (cells[i].active <= 0) fixed += cells[i].base;
      flex += cells[i].active;
    }
    unit = fmax2(0, space - fixed) / fmax2(1, flex);
    int frozen = 0;
    for (uint32_t i = 0; i < count; ++i) {
      if (cells[i].active > 0 && cells[i].active * unit < cells[i].base) {
        cells[i].active = 0; frozen = 1;
      }
    }
    if (!frozen) break;
  }
  float offset = 0;
  for (uint32_t i = 0; i < count; ++i) {
    prefix[i] = offset;
    offset = (offset + fmax2(cells[i].base, cells[i].flex * unit)) + gap;
  }
  prefix[count] = offset;
}

static void layout(const Node *node, Box box, Output *out, unsigned depth) {
  if (out->count >= GRID_NODES || depth > 8) { ++out->errors; return; }
  out->boxes[out->count++] = box;
  if (!node->style) return;
  Place places[GRID_CHILDREN];
  uint32_t nc, nr;
  if (!placement(node, places, &nc, &nr)) { ++out->errors; return; }
  float x[GRID_COLUMNS + 1], y[GRID_ROWS + 1];
  const Style *s = node->style;
  tracks(s->columns, s->nc, s->auto_column, nc, box.width, s->cg, x);
  tracks(s->rows, s->nr, s->auto_row, nr, box.height, s->rg, y);
  for (uint32_t i = 0; i < node->count; ++i) {
    Place p = places[i];
    const Node *child = node->children[i];
    Box b = {child->item.id, box.x + x[p.c], box.y + y[p.r],
             fmax2(0, (x[p.c + p.cs] - x[p.c]) - s->cg),
             fmax2(0, (y[p.r + p.rs] - y[p.r]) - s->rg)};
    layout(child, b, out, depth + 1);
  }
}

void grid_run(const Node *node, float width, float height, Output *out) {
  out->count = 0; out->errors = 0;
  layout(node, (Box){node->item.id, 0, 0, width, height}, out, 0);
}

void grid_show(const Output *out) {
  for (uint32_t i = 0; i < out->count; ++i) {
    const Box b = out->boxes[i];
    printf("box=%u,%.9g,%.9g,%.9g,%.9g\n", b.id, (double)b.x, (double)b.y, (double)b.width, (double)b.height);
  }
  printf("errors=%u\n", out->errors);
}

static uint32_t quantize(float x) {
  return (uint32_t)fmin2(4294967040.0f, fmax2(0, x * 16));
}

Stats grid_inspect(const Output *out) {
  Stats stats = {0, out->count, out->errors};
  for (uint32_t i = 0; i < out->count; ++i) {
    const Box b = out->boxes[i];
    stats.checksum += (b.id + 1) * (quantize(b.x) + 3 * quantize(b.y)
      + 5 * quantize(b.width) + 7 * quantize(b.height));
  }
  return stats;
}

typedef struct {
  const Node *page; float width, height;
  uint32_t jobs, repetitions; atomic_uint next;
} Queue;
typedef struct { Queue *queue; Stats stats; } Worker;
static void *worker(void *opaque) {
  Worker *w = opaque; Queue *q = w->queue; Output out;
  for (;;) {
    const uint32_t first = atomic_fetch_add_explicit(&q->next, 16, memory_order_relaxed);
    if (first >= q->jobs) break;
    const uint32_t end = first + 16 < q->jobs ? first + 16 : q->jobs;
    for (uint32_t i = first; i < end; ++i) for (uint32_t r = 0; r < q->repetitions; ++r) {
      grid_run(q->page, q->width + (float)((i + r) % 97), q->height, &out);
      Stats s = grid_inspect(&out);
      w->stats.checksum += s.checksum; w->stats.nodes += s.nodes; w->stats.errors += s.errors;
    }
  }
  return NULL;
}

int grid_bench(int argc, char **argv, const Node *page, float width, float height,
               uint32_t jobs, uint32_t repetitions) {
  unsigned threads = 1;
  if (argc != 1) {
    if (argc != 3 || strcmp(argv[1], "--threads")) return 2;
    char *end; errno = 0;
    long value = strtol(argv[2], &end, 10);
    if (errno || end == argv[2] || *end || value < 1 || value > 128) return 2;
    threads = (unsigned)value;
  }
  Queue q = {page, width, height, jobs, repetitions, ATOMIC_VAR_INIT(0)};
  Worker workers[128] = {{0}}; pthread_t ids[128];
  for (unsigned i = 0; i < threads; ++i) {
    workers[i].queue = &q;
    if (threads > 1 && pthread_create(&ids[i], NULL, worker, &workers[i])) return 1;
  }
  if (threads == 1) worker(&workers[0]);
  else for (unsigned i = 0; i < threads; ++i) if (pthread_join(ids[i], NULL)) return 1;
  Stats total = {0};
  for (unsigned i = 0; i < threads; ++i) {
    total.checksum += workers[i].stats.checksum;
    total.nodes += workers[i].stats.nodes; total.errors += workers[i].stats.errors;
  }
  printf("checksum=%u nodes=%u errors=%u\n", total.checksum, total.nodes, total.errors);
  return total.errors ? 1 : 0;
}
