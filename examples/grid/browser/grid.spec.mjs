import { test, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const checks = JSON.parse(fs.readFileSync(path.join(root, 'build/grid/checks.json'), 'utf8'));

for (const [index, check] of checks.entries()) {
  test(`Grid ${index}: ${check.input.id} at ${check.input.width}px`, async ({ page, browser, browserName }) => {
    const knownVariance = browserName === 'chromium' && check.input.id === 'random-29';
    test.fail(knownVariance, 'Dense placement differs between Chromium and Firefox; Bend/C follow Firefox and the cell search in CSS Grid 1 §8.5.');
    await page.setContent('<style>*{box-sizing:content-box}body{margin:0}</style><main></main>');
    const boxes = await page.evaluate(input => {
      const elements = [];
      function mount(node, parent, isRoot = false) {
        const el = document.createElement('div');
        el.dataset.id = node.id;
        Object.assign(el.style, { minWidth: '0px', minHeight: '0px', margin: '0px', padding: '0px', border: '0px' });
        if (isRoot) Object.assign(el.style, { width: `${input.width}px`, height: `${input.height}px` });
        el.style.gridColumn = node.column ? `${node.column} / span ${node.span_column ?? 1}` : `span ${node.span_column ?? 1}`;
        el.style.gridRow = node.row ? `${node.row} / span ${node.span_row ?? 1}` : `span ${node.span_row ?? 1}`;
        if (node.grid) {
          const g = node.grid;
          Object.assign(el.style, { display: 'grid', gridTemplateColumns: g.columns ?? '1fr', gridTemplateRows: g.rows ?? '',
            gridAutoColumns: g.auto_columns ?? '0px', gridAutoRows: g.auto_rows ?? '64px',
            columnGap: `${g.column_gap ?? g.gap ?? 0}px`, rowGap: `${g.row_gap ?? g.gap ?? 0}px`,
            gridAutoFlow: g.dense ? 'row dense' : 'row' });
        }
        parent.append(el); elements.push(el);
        for (const child of node.children ?? []) mount(child, el);
      }
      mount(input, document.querySelector('main'), true);
      return Object.fromEntries(elements.map(el => {
        const r = el.getBoundingClientRect();
        return [el.dataset.id, [r.x, r.y, r.width, r.height]];
      }));
    }, check.input);
    expect(Object.keys(boxes).sort()).toEqual(Object.keys(check.bend.boxes).sort());
    let error = 0;
    const differences = [];
    for (const [id, actual] of Object.entries(check.bend.boxes)) {
      for (const [axis, value] of actual.entries()) {
        const delta = Math.abs(value - boxes[id][axis]);
        error = Math.max(error, delta);
        // Accumulated track rounding differs between browser layout units and F32.
        if (delta > .25) differences.push({ id, axis, bend: value, browser: boxes[id][axis], delta });
      }
    }
    const resultPath = path.join(root, `build/grid/${browserName}-results.json`);
    const previous = fs.existsSync(resultPath) ? JSON.parse(fs.readFileSync(resultPath, 'utf8')).cases : [];
    const results = previous.filter(row => row.index !== index);
    results.push({ index, id: check.input.id, width: check.input.width, rectangles: Object.keys(boxes).length,
      max_error_px: error, status: knownVariance ? 'known_browser_difference' : 'verified', differences });
    fs.writeFileSync(resultPath, JSON.stringify({
      browser: browserName, version: browser.version(), tolerance_px: .25,
      max_verified_error_px: Math.max(...results.filter(row => row.status === 'verified').map(row => row.max_error_px), 0),
      rectangles: results.reduce((sum, row) => sum + row.rectangles, 0), cases: results.sort((a, b) => a.index - b.index),
    }, null, 2) + '\n');
    expect(differences, JSON.stringify(differences.slice(0, 4))).toEqual([]);
  });
}
