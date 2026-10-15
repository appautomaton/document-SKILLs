# Designing a deck

Read this before writing slide HTML. A slide is read in seconds from across a room. Every choice below serves that reader. A choice that doesn't serve them is decoration, so leave it out.

Settle the system first: palette, type scale, grid. State it in two sentences before writing any HTML, then apply it to every slide without exception. Consistency is most of what makes a deck look designed.

## Principles

**One point per slide.** The headline states it as a sentence ("Revenue grew 18%, led by renewals"), not as a topic ("Revenue"). Everything else on the slide supports that sentence. If a slide needs two headlines, make it two slides.

**Hierarchy in three levels.** Use a headline, body, and annotation (sources, footnotes, axis labels). Use size and weight to separate them, never more than three sizes per slide. A step of about 1.5× reads as a clear difference.

| Role | 16:9 (720 × 405pt) |
|---|---|
| Statement / big number | 54–72pt |
| Headline | 28–36pt |
| Body | 16–20pt |
| Annotation | 11–12pt |

Body text never goes below 14pt. If it doesn't fit at 14pt, cut words.

**A grid.** Use outer margins of 36–48pt on every side. Divide the content area into 12 columns, and give every left edge one of the grid lines. The headline sits in the same place on every slide, so slides change and the frame stays still. For a chart or table with text, use two columns at roughly 40/60, with the text beside the chart. Never stack a chart under a paragraph, and never cram a layout to avoid adding a slide.

**Colour: one accent, used sparingly.** Build the palette from a near-white or near-black background, one text colour, a secondary grey for annotations, and a single accent. Use the accent only for what the eye should land on: the key number, the highlighted bar, the active step. When everything is accented, nothing is.

- Prefer off-black text (`1A1A1A`, `222831`) to pure `000000` on light backgrounds. It reads as print rather than screen.
- Text contrast must be at least 4.5:1 against its background. Grey text on a tinted panel is where this usually fails.
- With a brand, take its primary colour as the accent and keep everything else neutral.
- Without a brand, choose an accent that suits the subject without cliché. Finance doesn't have to be navy.

**Restraint.** A shape earns its place by carrying structure: a panel grouping related items, a rule separating sections, a bar marking the active item. Skip drop shadows, gradients, clip-art icons and decorative corner shapes unless the brand calls for them. Whitespace is part of the structure, so don't fill it.

**Charts that make the point.** Each chart answers the headline's claim.

- Grey the series that give context and accent the one that matters.
- Label values or series directly instead of using a legend.
- Start bar charts at zero.
- Delete gridlines, or make them faint.
- Pick the granularity that shows the shape: days under a month, months under two years, years beyond that. A chart with one data point means the aggregation is wrong.

**Repetition.** Recurring elements repeat exactly: the same position, size, colour and spacing. Use a few layouts only (title, section break, statement, text + chart, full-bleed chart or table) and reuse them.

## Fonts

html2pptx measures text in the browser on this machine, and PowerPoint draws it on the audience's machine. If either lacks the font, a substitute with different widths takes its place, and text that fitted overflows. So use only fonts both machines are certain to have:

**Arial, Georgia, Verdana, Trebuchet MS, Times New Roman, Courier New.**

Use one family for everything and get contrast from size and weight, or pair a heading family with a body family. Pairings that work:

- Georgia headlines with Arial body: editorial
- Arial throughout, with bold headlines: neutral, the safest
- Trebuchet MS throughout: friendlier
- Courier New only for code or tabular figures

Avoid single-weight display fonts such as Impact. PowerPoint fakes their bold, which widens the text.

For Chinese, Japanese or Korean text, Latin fonts carry no glyphs, so both sides fall back to their own system fonts. Name a CJK font that the audience's machines have (for example Microsoft YaHei for Windows audiences). Leave a generous margin of slack in every text box, then check the rendered pages closely.

## A starting stylesheet

This puts the system above into CSS custom properties, so each slide only arranges content. It passes html2pptx validation as written.

```html
<style>
:root {
  --bg: #FAFAF7; --text: #1A1A1A; --muted: #6B6B6B; --accent: #C0392B; --panel: #F0EDE6;
  --headline: 32pt; --body: 18pt; --note: 11pt; --margin: 40pt;
}
body {
  width: 720pt; height: 405pt; margin: 0; display: flex; flex-direction: column;
  background: var(--bg); color: var(--text); font-family: Arial, sans-serif;
}
h1 { font-size: var(--headline); margin: var(--margin) var(--margin) 16pt; }
p, ul, ol { font-size: var(--body); margin: 0 var(--margin) 10pt; line-height: 1.3; }
.note { font-size: var(--note); color: var(--muted); }
.accent { color: var(--accent); }
.columns { display: flex; gap: 24pt; margin: 0 var(--margin); }
.columns > .text { width: 40%; } .columns > .figure { width: 60%; }
.columns p, .columns ul { margin-left: 0; margin-right: 0; }
.panel { background: var(--panel); padding: 14pt; }
</style>
```
