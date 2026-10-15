# Creating Word documents with docx-js

docx-js (the `docx` npm package, v9) builds a `.docx` from JavaScript objects. This file covers the parts of its API that produce broken or surprising output when guessed at.

## Running a script

Write CommonJS (`require`), and put `await` inside an async function, since a `.js` file run by Node is not a module and rejects top-level `await`. Point Node at the skill's packages, and run from the user's working directory so output lands there:

```bash
NODE_PATH=<skill>/node_modules node build.js
```

If `<skill>/node_modules` is missing, run `npm install` in `<skill>` once.

## A complete document

Every pattern below appears in this example, which validates cleanly and renders as intended. Start from it and remove what you don't need.

```javascript
const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType, LevelFormat,
  Table, TableRow, TableCell, WidthType, BorderStyle, ShadingType, VerticalAlign,
  ImageRun, ExternalHyperlink, InternalHyperlink, Bookmark, TableOfContents,
  Header, Footer, PageNumber, PageBreak, FootnoteReferenceRun,
} = require("docx");

const LETTER = { width: 12240, height: 15840 };     // 8.5 x 11 in, in DXA
const MARGIN = 1440;                                 // 1 in
const CONTENT = LETTER.width - 2 * MARGIN;           // 9360 DXA of usable width

const border = { style: BorderStyle.SINGLE, size: 4, color: "BFBFBF" };
const cell = (text, width, opts = {}) => new TableCell({
  width: { size: width, type: WidthType.DXA },
  borders: { top: border, bottom: border, left: border, right: border },
  shading: opts.fill ? { fill: opts.fill, type: ShadingType.CLEAR, color: "auto" } : undefined,
  verticalAlign: VerticalAlign.CENTER,
  children: [new Paragraph({ children: [new TextRun({ text, bold: opts.bold })] })],
});

async function main() {
  const doc = new Document({
    features: { updateFields: true },  // Word refreshes the TOC and page fields on open
    styles: {
      default: {
        document: { run: { font: "Arial", size: 22 } },  // 11 pt body
        title: { run: { font: "Arial", size: 48, bold: true } },
        heading1: { run: { font: "Arial", size: 32, bold: true }, paragraph: { spacing: { before: 360, after: 120 } } },
        heading2: { run: { font: "Arial", size: 26, bold: true }, paragraph: { spacing: { before: 240, after: 80 } } },
      },
      paragraphStyles: [
        { id: "Note", name: "Note", basedOn: "Normal", run: { italics: true, color: "595959" } },
      ],
    },
    numbering: {
      config: [
        { reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
        { reference: "steps", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
      ],
    },
    footnotes: {
      1: { children: [new Paragraph("Source: internal finance report, Q3 2026.")] },
    },
    sections: [{
      properties: { page: { size: LETTER, margin: { top: MARGIN, right: MARGIN, bottom: MARGIN, left: MARGIN } } },
      headers: { default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, children: [new TextRun("Quarterly review")] })] }) },
      footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
        children: [new TextRun({ children: ["Page ", PageNumber.CURRENT, " of ", PageNumber.TOTAL_PAGES] })] })] }) },
      children: [
        new Paragraph({ heading: HeadingLevel.TITLE, children: [new TextRun("Quarterly Review")] }),
        new TableOfContents("Contents", { hyperlink: true, headingStyleRange: "1-2" }),
        new Paragraph({ children: [new PageBreak()] }),
        new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new Bookmark({ id: "results", children: [new TextRun("Results")] })] }),
        new Paragraph({ children: [
          new TextRun("Revenue grew 18%"), new FootnoteReferenceRun(1), new TextRun(". See "),
          new ExternalHyperlink({ link: "https://example.com", children: [new TextRun({ text: "the dashboard", style: "Hyperlink" })] }),
          new TextRun("."),
        ] }),
        new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("Enterprise up 24%")] }),
        new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun("Consumer flat")] }),
        new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("By region")] }),
        new Table({
          width: { size: CONTENT, type: WidthType.DXA },
          columnWidths: [CONTENT / 2, CONTENT / 2],
          rows: [
            new TableRow({ tableHeader: true, children: [cell("Region", CONTENT / 2, { bold: true, fill: "D9E2F3" }), cell("Growth", CONTENT / 2, { bold: true, fill: "D9E2F3" })] }),
            new TableRow({ children: [cell("EMEA", CONTENT / 2), cell("12%", CONTENT / 2)] }),
          ],
        }),
        new Paragraph({ alignment: AlignmentType.CENTER, children: [
          new ImageRun({ type: "png", data: fs.readFileSync("chart.png"), transformation: { width: 400, height: 200 },
            altText: { name: "chart", description: "Revenue by quarter" } }),
        ] }),
        new Paragraph({ children: [
          new ImageRun({ type: "svg", data: fs.readFileSync("logo.svg"), transformation: { width: 100, height: 50 },
            fallback: { type: "png", data: fs.readFileSync("chart.png") } }),
        ] }),
        new Paragraph({ numbering: { reference: "steps", level: 0 }, children: [new TextRun("Review the figures")] }),
        new Paragraph({ numbering: { reference: "steps", level: 0 }, children: [new TextRun("Approve the budget")] }),
        new Paragraph({ style: "Note", children: [
          new TextRun("Back to "), new InternalHyperlink({ anchor: "results", children: [new TextRun({ text: "Results", style: "Hyperlink" })] }),
        ] }),
      ],
    }],
  });
  fs.writeFileSync("report.docx", await Packer.toBuffer(doc));
}

main();
```

## Page size

docx-js defaults to **A4** (11906 × 16838 DXA). For US documents, set Letter explicitly as above. Every width depends on this choice, with 1440 DXA = 1 inch:

| Page, 1" margins | `size` | Usable width | Two columns | Three columns |
|---|---|---|---|---|
| Letter | `{ width: 12240, height: 15840 }` | 9360 | `[4680, 4680]` | `[3120, 3120, 3120]` |
| A4 | `{ width: 11906, height: 16838 }` | 9026 | `[4513, 4513]` | `[3009, 3009, 3008]` |

For landscape, add `orientation: PageOrientation.LANDSCAPE` to `size` and keep the portrait numbers; docx-js swaps them. `TabStopPosition.MAX` is 9026, the A4 right margin, so on Letter use 9360 for a right-aligned tab.

## Styles

- Restyle built-in styles through `styles.default`: `document`, `title`, `heading1` … `heading6`, `listParagraph`, `hyperlink`. Defining a `paragraphStyles` entry with id `Heading1` writes a second Heading1 style next to the built-in one, and which one Word applies is undefined.
- Use `paragraphStyles` and `characterStyles` for your own styles, with your own ids, and apply them with `style: "Note"`.
- Headings must use `heading: HeadingLevel.HEADING_n` with no custom `style`, or the table of contents will not find them.
- Sizes are in half-points: `size: 22` is 11 pt.

## Text

- One `Paragraph` per line. `\n` inside a `TextRun` does not make a line break.
- Run options: `bold`, `italics`, `underline: { type: UnderlineType.SINGLE }`, `strike`, `superScript`, `subScript`, `smallCaps`, `color: "C00000"`, `font`, `size`.
- `highlight: "yellow"` also writes a `w:highlightCs` element that fails schema validation. Pass `highlightComplexScript: false` alongside it.
- Type symbols as plain characters in a `TextRun` ("✓ ✗ © ™"). `SymbolRun` codes such as `F0FC` only mean a check mark in the Wingdings font.

## Lists

Use a numbering config with `LevelFormat.BULLET` or `LevelFormat.DECIMAL`, never a typed "•", which looks like a list but does not behave like one. Paragraphs sharing a `reference` continue one sequence, and a different reference restarts at 1. So give each separately numbered list its own reference.

## Tables

- Set `columnWidths` on the table and the same `width` (type `WidthType.DXA`) on every cell. Make the widths add up to the usable width of the page size you chose.
- Shade cells with `type: ShadingType.CLEAR`. `ShadingType.SOLID` paints the cell black in Word.
- Put borders on cells, not on the table. Every cell needs at least one `Paragraph`.

## Links, bookmarks, table of contents

- **Bookmarks:** create the target with `new Bookmark({ id, children })` inside a paragraph, and point at it with `new InternalHyperlink({ anchor: id, … })`. A `bookmark:` option on `Paragraph` is silently ignored.
- **Table of contents:** `TableOfContents` inserts a field that Word fills in when it updates fields. `features: { updateFields: true }` makes Word offer to do that on open. LibreOffice and `render.py` show the table empty, which is expected.

## Images

- `type` is required (`png`, `jpg`, `gif`, `bmp`, `svg`).
- `transformation` is in pixels. Keep the aspect ratio of the source, and keep the width within the page.
- An `svg` image also needs a raster `fallback: { type: "png", data }`, or docx-js throws "Cannot read properties of undefined (reading 'type')".
- `altText` is optional. When you give it, include `name`, or the drawing fails schema validation.

## Footnotes

Define the notes in `footnotes` on the `Document`, keyed by number, and reference them with `new FootnoteReferenceRun(n)`. There is no `Footnote` class to import.

## Page breaks and sections

- **Page breaks:** `new PageBreak()` only works inside a paragraph's children. For a heading that should start a new page, use `pageBreakBefore: true` on the paragraph.
- **Sections:** each entry in `sections` starts a new page, with its own size, orientation, margins, headers and footers.
- **Headers and footers:** they take paragraphs. Page numbers go in a run's children, `PageNumber.CURRENT` and `PageNumber.TOTAL_PAGES`, mixed with plain strings as in the example.
