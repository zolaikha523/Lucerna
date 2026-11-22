// Render assets/brand/*.svg to PNG with the pre-installed Chromium:  node tools/rasterize_brand.js
const { chromium } = require('playwright');
const fs = require('fs'); const path = require('path');
const dir = path.join(__dirname, '..', 'assets', 'brand');
const jobs = [
  ['lucerna-symbol.svg', 'lucerna-symbol.png', 256], ['favicon.svg', 'favicon.png', 64], ['favicon.svg', 'favicon-32.png', 32],
  ['favicon.svg', 'apple-touch-icon.png', 180], ['lucerna-logo-horizontal-light.svg', 'lucerna-logo-horizontal-light.png', 900],
  ['lucerna-logo-horizontal-dark.svg', 'lucerna-logo-horizontal-dark.png', 900], ['lucerna-logo-stacked-light.svg', 'lucerna-logo-stacked-light.png', 600],
  ['lucerna-logo-stacked-dark.svg', 'lucerna-logo-stacked-dark.png', 600], ['lucerna-logo-monochrome.svg', 'lucerna-logo-monochrome.png', 900],
  ['lucerna-logo-monochrome-white.svg', 'lucerna-logo-monochrome-white.png', 900],
];
(async () => {
  const b = await chromium.launch(); const p = await b.newPage();
  for (const [src, dst, width] of jobs) {
    const svg = fs.readFileSync(path.join(dir, src), 'utf8');
    const m = svg.match(/viewBox="0 0 ([\d.]+) ([\d.]+)"/); const w = +m[1], h = +m[2]; const H = Math.round(width * h / w);
    await p.setViewportSize({ width, height: H });
    await p.setContent(`<html><body style="margin:0;background:transparent">${svg.replace(/width="[\d.]+" height="[\d.]+"/, `width="${width}" height="${H}"`)}</body></html>`);
    await p.screenshot({ path: path.join(dir, dst), omitBackground: true, clip: { x: 0, y: 0, width, height: H } });
    console.log(dst, width + 'x' + H);
  }
  await b.close();
})();
