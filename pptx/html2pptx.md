# html2pptx

`scripts/html2pptx.js` renders an HTML slide in Chromium, reads where everything landed, and rebuilds it as native PowerPoint objects with PptxGenJS. Text stays editable and positions match the browser. Read `design.md` before writing slides.

## Setup

- If `<skill>/node_modules` is missing, run `npm install` in `<skill>` once.
- Slides render in the Google Chrome already installed on the machine; nothing to download. Only on a machine without Chrome (CI, containers) run `npx playwright-core install chromium` in `<skill>` once. It downloads a Chromium of about 250 MB into Playwright's shared cache, so never run it where Chrome exists.
- Run build scripts from the user's working directory with `NODE_PATH=<skill>/node_modules node build.js`, so `require('pptxgenjs')` resolves.

## Slide HTML

Each slide is a complete HTML file starting with `<!DOCTYPE html>`; without it the browser lays the page out in quirks mode and html2pptx refuses it. The body is the slide. Its size must match the presentation layout:

| Layout | Body |
|---|---|
| `LAYOUT_16x9` | `width: 720pt; height: 405pt` |
| `LAYOUT_4x3` | `width: 720pt; height: 540pt` |
| `LAYOUT_16x10` | `width: 720pt; height: 450pt` |

Give the body `margin: 0`. `display: flex` on it stops margin collapse from hiding overflow.

| HTML | Becomes |
|---|---|
| `<p>`, `<h1>`–`<h6>` | A text box. Inside it, `<b>`/`<strong>`, `<i>`/`<em>`, `<u>`, `<s>`, `<sup>`, `<sub>` and `<span>` keep their weight, style, colour, size, font and letter-spacing, and `<br>` breaks the line within the paragraph. |
| `<ul>`, `<ol>`, nested to any depth | One text box of bulleted or numbered paragraphs. `<ol>` honours `start` and `list-style-type` (decimal, lower/upper-alpha, lower/upper-roman). |
| `<div>` with a background or border | A shape. `border-radius` gives rounded corners, `box-shadow` an outer shadow, and a one-sided border becomes a line. |
| `<img>` | A picture. Paths are relative to the HTML file, and `data:` URLs work. |
| `class="placeholder"` | Nothing is drawn. Its position is returned for a chart or table. Give it an `id`. |

Text outside `<p>`, `<h1>`–`<h6>`, `<ul>` and `<ol>` does not reach PowerPoint. CSS gradients and SVG don't convert either: rasterize them to PNG first (see below). Fonts follow the policy in `design.md`.

### What html2pptx rejects

It collects every problem on a slide and throws them together, prefixed with the file name. Fix them all and run again.

- Content overflowing the body, or a body size that doesn't match the layout.
- Text over 12pt ending within 0.5" of the bottom edge.
- A `<div>` containing bare text: wrap it in `<p>`.
- A background, border or shadow on a text element: put it on a wrapping `<div>`.
- `background-image` on a `<div>`: use an `<img>`.
- CSS gradients.
- Margins on inline elements (`<span>`, `<b>`, …), which PowerPoint runs can't hold.
- A paragraph starting with a typed bullet character: use `<ul>`/`<ol>`.
- A placeholder with zero width or height.

## Building the deck

A CommonJS script with an async `main`:

```javascript
const pptxgen = require('pptxgenjs');
const html2pptx = require('<skill>/scripts/html2pptx.js');

async function main() {
  const pptx = new pptxgen();
  pptx.layout = 'LAYOUT_16x9';
  pptx.title = 'Quarterly review';

  await html2pptx('slides/01-title.html', pptx);

  const { slide, placeholders } = await html2pptx('slides/02-growth.html', pptx);
  const area = placeholders.find((p) => p.id === 'chart');
  slide.addChart(pptx.charts.BAR, [
    { name: 'Revenue', labels: ['Q1', 'Q2', 'Q3', 'Q4'], values: [4.5, 5.5, 6.2, 7.1] }
  ], { ...area, chartColors: ['C0392B'], showLegend: false, showValue: true });
  slide.addNotes('Growth came from renewals; new logos were flat.');

  await pptx.writeFile({ fileName: 'deck.pptx' });
}

main().catch((e) => { console.error(e.message); process.exit(1); });
```

`html2pptx(htmlFile, pptx, options)` returns `{ slide, placeholders }`, with each placeholder as `{ id, x, y, w, h }` in inches. The options are:

- `slide`: draw onto an existing slide.
- `screenshotPlaceholders: true`: also returns each placeholder as a PNG in `placeholder.image`.
- `renderDelay: ms`: waits before reading the page.

One browser serves every call and closes after a second idle. `html2pptx.close()` closes it at once.

PptxGenJS on its own writes some XML that PowerPoint tolerates but the schema rejects: repeated paragraph properties, a misordered presentation part, and chart XML for line, area, scatter and radar charts. Once html2pptx has seen a presentation, it repairs all of that as the file is written, including anything you added directly with PptxGenJS.

## PptxGenJS: the parts you'll use

**Colours** are hex without `#`: `'C0392B'`. A `#` corrupts the file.

**Charts.** `BAR` (with `barDir: 'bar'` for horizontal and `barGrouping: 'stacked'`), `BAR3D`, `LINE`, `AREA`, `PIE`, `DOUGHNUT`, `SCATTER` and `RADAR` all produce valid files. Useful options:

- `chartColors: ['C0392B', 'B0B0B0']`
- `showValue`, `dataLabelPosition: 'outEnd'`
- `showLegend`, `legendPos: 'r'`
- `showTitle`, `title`
- `showCatAxisTitle`, `catAxisTitle`, `showValAxisTitle`, `valAxisTitle`
- `valAxisMinVal`, `valAxisMaxVal`, `valAxisMajorUnit`
- `catAxisLabelRotate`
- `lineSize`, `lineDataSymbol`
- `showPercent` (pie)

Data comes as series: `[{ name, labels, values }]`. Pie and doughnut take one series. Scatter is the odd one out: the first series holds the X values, and each later series holds Y values only.

```javascript
slide.addChart(pptx.charts.SCATTER, [
  { name: 'X', values: [1, 2, 3, 4] },
  { name: 'Conversion', values: [2.1, 2.9, 3.2, 4.0] }
], { ...area, lineSize: 0, lineDataSymbol: 'circle', chartColors: ['C0392B'] });
```

**Tables.** Rows of strings or `{ text, options }` cells:

```javascript
slide.addTable([
  [{ text: 'Product', options: { bold: true, color: 'FFFFFF', fill: { color: '1F3A5F' } } },
   { text: 'Revenue', options: { bold: true, color: 'FFFFFF', fill: { color: '1F3A5F' } } }],
  ['Core', '$50M'],
  ['Add-ons', '$35M']
], { ...area, colW: [3, 2], fontSize: 14, border: { pt: 1, color: 'DDDDDD' } });
```

`colspan` and `rowspan` go in a cell's options; `autoPage: true` continues a long table onto new slides.

**Images** added directly need their aspect ratio kept by hand. Read the pixel size with `await sharp('photo.jpg').metadata()` and derive `h` from `w`.

**Speaker notes:** `slide.addNotes('text')`.

## Icons and gradients as PNG

Rasterize with Sharp, then reference the PNG from the HTML: `<img src="icon.png" style="width: 36pt; height: 36pt">`, or `background-image: url('bg.png')` on `<body>`.

An icon is any SVG: one the user supplies, or a simple one you draw. Use `currentColor` in it and set the colour when rasterizing.

```javascript
const sharp = require('sharp');

const chartLine = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
  stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M3 3v18h18"/><path d="M7 15l4-4 3 3 5-6"/></svg>`;

async function iconPng(svg, color, file, size = 256) {
  const colored = svg.replaceAll('currentColor', `#${color}`);
  await sharp(Buffer.from(colored), { density: 300 }).resize(size, size).png().toFile(file);
}

async function gradientPng(from, to, file, width = 1920, height = 1080) {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}">
    <defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#${from}"/><stop offset="1" stop-color="#${to}"/>
    </linearGradient></defs>
    <rect width="100%" height="100%" fill="url(#g)"/></svg>`;
  await sharp(Buffer.from(svg)).png().toFile(file);
}

async function main() {
  await iconPng(chartLine, '1F3A5F', 'icon.png');
  await gradientPng('1F3A5F', '0B1A2B', 'bg.png');
}

main().catch((e) => { console.error(e); process.exit(1); });
```

## Browser-drawn content

For a chart drawn by Chart.js, D3 or inline SVG inside a placeholder, let html2pptx capture it as it renders the slide:

```javascript
const { slide, placeholders } = await html2pptx('slide.html', pptx, {
  screenshotPlaceholders: true,
  renderDelay: 500  // let the script finish drawing; or turn its animation off
});
for (const p of placeholders) slide.addImage({ data: p.image, x: p.x, y: p.y, w: p.w, h: p.h });
```

Prefer native PptxGenJS charts when the type exists. A native chart stays editable, and its data stays in the file.
