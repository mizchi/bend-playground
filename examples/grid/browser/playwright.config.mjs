import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: '.', testMatch: 'grid.spec.mjs', workers: 1, fullyParallel: false,
  reporter: 'line', outputDir: '../../../build/grid/playwright',
  use: { headless: true, viewport: { width: 1600, height: 1200 } },
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
    { name: 'firefox', use: { browserName: 'firefox' } },
  ],
});
