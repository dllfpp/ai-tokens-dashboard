// Renders the PNG brand assets with Chromium (playwright). Run in brand/ inside the
// mcr.microsoft.com/playwright image:  node render.js out/
//   og.png 1200x630, favicon-16/32/48.png and icon-192/512.png (transparent, rounded tile),
//   apple-touch-icon.png 180 and icon-maskable-512.png (full-bleed tile, the OS rounds it).
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

(async () => {
  const out = path.resolve(process.argv[2] || 'out');
  fs.mkdirSync(out, { recursive: true });
  const here = __dirname;
  const mark = fs.readFileSync(path.join(here, 'mark.svg'), 'utf8');
  // full-bleed variant: square tile, no corner highlight (iOS/Android apply their own mask)
  const full = mark
    .replace(/<rect x="2" y="2" width="60" height="60" rx="16"/, '<rect x="0" y="0" width="64" height="64"')
    .replace(/<path d="M6 18[^>]*\/>/, '');
  fs.writeFileSync(path.join(out, 'mark-full.svg'), full);

  const b = await chromium.launch();
  const shot = async (svg, size, file, transparent) => {
    const p = await b.newPage({ viewport: { width: size, height: size } });
    const uri = 'data:image/svg+xml;base64,' + Buffer.from(svg).toString('base64');
    await p.setContent(`<html><body style="margin:0;background:transparent">
      <img src="${uri}" width="${size}" height="${size}" style="display:block"></body></html>`);
    await p.waitForTimeout(100);
    await p.screenshot({ path: path.join(out, file), omitBackground: transparent });
    await p.close();
  };
  for (const s of [16, 32, 48, 192, 512]) await shot(mark, s, s <= 48 ? `favicon-${s}.png` : `icon-${s}.png`, true);
  await shot(full, 180, 'apple-touch-icon.png', false);
  await shot(full, 512, 'icon-maskable-512.png', false);

  const og = await b.newPage({ viewport: { width: 1200, height: 630 } });
  await og.goto('file://' + path.join(here, 'og.html'), { waitUntil: 'networkidle' });
  await og.evaluate(() => document.fonts.ready);
  await og.screenshot({ path: path.join(out, 'og.png') });
  await b.close();
  console.log('rendered into', out);
})();
