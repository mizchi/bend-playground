#ifndef BEND_GRID_H
#define BEND_GRID_H
#include <stdint.h>
#include <stdio.h>

enum { GRID_COLUMNS = 32, GRID_ROWS = 128, GRID_CHILDREN = 256, GRID_NODES = 2048 };
typedef struct { float minimum, maximum, flex; } Track;
typedef struct { uint32_t id, column, row, cs, rs; } Item;
typedef struct {
  const Track *columns, *rows;
  uint32_t nc, nr;
  Track auto_column, auto_row;
  float cg, rg;
  int dense;
} Style;
typedef struct Node Node;
struct Node { Item item; const Style *style; const Node *const *children; uint32_t count; };
typedef struct { uint32_t id; float x, y, width, height; } Box;
typedef struct { Box boxes[GRID_NODES]; uint32_t count, errors; } Output;
typedef struct { uint32_t checksum, nodes, errors; } Stats;

void grid_run(const Node *, float width, float height, Output *);
void grid_show(const Output *);
Stats grid_inspect(const Output *);
int grid_bench(int argc, char **argv, const Node *, float width, float height,
               uint32_t jobs, uint32_t repetitions);
#endif
