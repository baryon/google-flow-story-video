#!/usr/bin/env node
/**
 * Render crisp official vector brand end slates using headless Chrome/Chromium (zero npm dependencies).
 * Usage:
 *   node render_endslates.mjs --logo ./logo.svg --series "THE BOOK OF LIFE" \
 *     --volume "VOLUME I" --domain "example.com" --count 10 --out-dir ./endslates
 */
import { existsSync, mkdirSync, readFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { extname, join } from 'node:path';

function arg(name, fallback = '') {
  const idx = process.argv.indexOf(name);
  return idx >= 0 && process.argv[idx + 1] && !process.argv[idx + 1].startsWith('--')
    ? process.argv[idx + 1]
    : fallback;
}

if (process.argv.includes('-h') || process.argv.includes('--help')) {
  console.log(`Usage: node render_endslates.mjs --logo <svg-or-png> [options]

Options:
  --logo <path>        Path to official brand SVG or PNG (required)
  --series <text>      Series title (default: "THE BOOK OF LIFE")
  --volume <text>      Volume/season label (default: "VOLUME I")
  --domain <text>      Website domain shown on end slate (default: "")
  --count <n>          Number of episodes to render (default: 10)
  --size <WxH>         Output resolution (default: 1080x1920)
  --accent <hex>       Episode subtitle & glow accent color (default: #7ee3bd)
  --bg-center <hex>    Radial gradient center color (default: #0e323d)
  --bg-edge <hex>      Radial gradient outer color (default: #02090e)
  --chrome <path>      Custom Chrome/Chromium executable path
  --out-dir <dir>      Output directory (default: ./endslates)`);
  process.exit(0);
}

function escapeHtml(str) {
  return String(str)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

function detectChrome(explicit) {
  if (explicit) return explicit;
  const candidates = [
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
    '/usr/bin/google-chrome',
    '/usr/bin/google-chrome-stable',
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
  ];
  for (const c of candidates) {
    if (existsSync(c)) return c;
  }
  throw new Error('Chrome/Chromium binary not found. Pass --chrome /path/to/chrome.');
}

const logoPath = arg('--logo');
if (!logoPath) {
  console.error('Error: missing required --logo <path-to-svg-or-png>. Run with --help for usage.');
  process.exit(1);
}

const series = arg('--series', 'THE BOOK OF LIFE');
const volume = arg('--volume', 'VOLUME I');
const domain = arg('--domain', '');
const count = Number(arg('--count', '10'));
const [width, height] = arg('--size', '1080x1920').split('x').map(Number);
const accent = arg('--accent', '#7ee3bd');
const bgCenter = arg('--bg-center', '#0e323d');
const bgEdge = arg('--bg-edge', '#02090e');
const outDir = arg('--out-dir', './endslates');
const chromeBin = detectChrome(arg('--chrome'));

mkdirSync(outDir, { recursive: true });

const ext = extname(logoPath).toLowerCase();
const mime = ext === '.svg' ? 'image/svg+xml' : ext === '.webp' ? 'image/webp' : 'image/png';
const logoUri = `data:${mime};base64,` + readFileSync(logoPath).toString('base64');
const ROMAN = [
  'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X',
  'XI', 'XII', 'XIII', 'XIV', 'XV', 'XVI', 'XVII', 'XVIII', 'XIX', 'XX',
];
const logoWidthPx = Math.round(width * 0.62);

for (let i = 0; i < count; i++) {
  const num = String(i + 1).padStart(2, '0');
  const epLabel = ROMAN[i] ?? String(i + 1);
  const domainHtml = domain ? `<div class="url">${escapeHtml(domain)}</div>` : '';
  const html = `<!doctype html><html><head><meta charset="utf-8"><style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    html, body {
      width: 100vw; height: 100vh; overflow: hidden;
      background-color: ${bgEdge};
      background-image: radial-gradient(ellipse at 50% 38%, ${bgCenter} 0%, ${bgEdge} 78%);
      display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 34px;
      padding-bottom: ${height > width ? '140px' : '40px'};
    }
    .logo { width: ${logoWidthPx}px; filter: drop-shadow(0 0 36px ${accent}55); }
    .logo img { width: 100%; height: auto; display: block; }
    .series {
      font-family: "Iowan Old Style", "Palatino Linotype", Georgia, serif;
      font-size: 36px; letter-spacing: 0.24em; text-transform: uppercase; color: #f3e8c9;
    }
    .ep {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-size: 26px; letter-spacing: 0.28em; text-transform: uppercase; color: ${accent};
    }
    .url {
      margin-top: 28px;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-size: 28px; letter-spacing: 0.16em; color: rgba(243, 232, 201, 0.74);
    }
  </style></head><body>
    <div class="logo"><img src="${logoUri}" /></div>
    <div class="series">${escapeHtml(series)}</div>
    <div class="ep">${escapeHtml(volume)} · EPISODE ${epLabel}</div>
    ${domainHtml}
  </body></html>`;

  const dataUrl = 'data:text/html;charset=utf-8,' + encodeURIComponent(html);
  const pngOut = join(outDir, `ep${num}-endslate.png`);
  execFileSync(
    chromeBin,
    [
      '--headless=new',
      '--disable-gpu',
      '--hide-scrollbars',
      '--force-device-scale-factor=1',
      `--window-size=${width},${height}`,
      `--screenshot=${pngOut}`,
      dataUrl,
    ],
    { stdio: 'ignore' },
  );
}

console.log(`ENDSLATES_OK count=${count} size=${width}x${height} dir=${outDir}`);
