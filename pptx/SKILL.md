---
name: pptx
description: Create, edit, and analyze PowerPoint decks (.pptx). Build new decks from HTML slides, fill an existing template, duplicate or reorder slides, edit slide XML, and read or write speaker notes. Use when a task produces or modifies a .pptx file, or needs text, layout, or notes read from one.
---

# PowerPoint decks

You already know python-pptx and PptxGenJS. This skill adds a converter that turns HTML slides into native, editable PowerPoint objects, scripts that make template work reliable, and checks that show whether a deck is valid and looks right.

## Running scripts

`<skill>` is the directory containing this file. Run bundled scripts by absolute path from the user's working directory, so relative paths to their files keep working:

```bash
uv run <skill>/scripts/thumbnail.py deck.pptx
```

Run Python you write with its dependencies declared, either `uv run --with python-pptx script.py` or a PEP 723 header. Run Node scripts as `NODE_PATH=<skill>/node_modules node build.js`. If `<skill>/node_modules` is missing, run `npm install` there once. Rendering needs LibreOffice (`soffice`) and poppler (`pdftoppm`).

## Choosing a workflow

| Task | Workflow |
|---|---|
| Read a deck's text | `uv run --with 'markitdown[pptx]' python -m markitdown deck.pptx` |
| New deck, no template | html2pptx, below. Read `html2pptx.md` and `design.md` first. |
| New deck from a template | Template workflow, below |
| Change an existing deck | python-pptx for text and shapes. Slide XML (`ooxml.md`) for what python-pptx can't reach. |
| Speaker notes | `scripts/notes.py` |

markitdown labels slides from 1 (`<!-- Slide number: 1 -->`); every script here counts from 0. To take on an existing deck's look, read `ppt/theme/theme1.xml` from the unpacked file (`<a:clrScheme>`, `<a:fontScheme>`) and look at its thumbnail grid.

## New deck: html2pptx

1. Settle the design system (`design.md`): palette, type scale, grid. State it in two sentences before writing code.
2. Write one HTML file per slide, following the rules in `html2pptx.md`. Mark chart and table areas with `class="placeholder"`.
3. Write a build script that calls `html2pptx()` for each slide, adds charts and tables at the placeholders with PptxGenJS, and calls `pptx.writeFile({ fileName })`. html2pptx throws every problem on a slide at once; fix them all and rerun.
4. Check the deck (below).

## New deck from a template

1. **See the template.** Extract its text with markitdown, and make a thumbnail grid with `uv run <skill>/scripts/thumbnail.py template.pptx grid`. Look at the grid images.
2. **Inventory its layouts.** List every slide by 0-based index with its purpose, e.g. "12: two columns, heading + bullets each".
3. **Map content to layouts.** Count the pieces of content for each slide first, then pick a layout with exactly that many slots:
   - two items to a two-column layout, three to three columns
   - image layouts only when there are images
   - quote layouts only for real quotes with attribution
   - four or more items split across slides or into a list

   Never leave a placeholder empty or invent filler to occupy one.
4. **Assemble the slides.** Duplicates are complete, with charts, embedded workbooks, notes and links:
   ```bash
   uv run <skill>/scripts/rearrange.py template.pptx working.pptx 0,12,12,31,40
   ```
5. **Inventory the text.** Read all of `inventory.json`:
   ```bash
   uv run <skill>/scripts/inventory.py working.pptx inventory.json
   ```
6. **Write the replacements** (format below), then apply them:
   ```bash
   uv run <skill>/scripts/replace.py working.pptx replacements.json output.pptx
   ```
7. Check the deck (below).

### Inventory and replacements

`inventory.json` maps `slide-N` to `shape-N`, both 0-based. Shapes are ordered top to bottom, then left to right, and slide numbers are left out. Each shape has `left`, `top`, `width` and `height` in inches, and `paragraphs`. It also carries:

- `placeholder_type` (`TITLE`, `CENTER_TITLE`, `SUBTITLE`, `BODY`, `OBJECT`, …), only for placeholders
- `default_font_size`, when the layout sets one
- `overflow`, `overlap` and `warnings`, when it detects them

Paragraphs list only the properties that differ from the default.

The replacements file has the same shape, with `paragraphs` for each shape to fill:

```json
{
  "slide-0": {
    "shape-0": {"paragraphs": [{"text": "Revenue grew 18%", "bold": true}]},
    "shape-1": {"paragraphs": [
      {"text": "Renewals drove two thirds of growth"},
      {"text": "Churn fell to 4%", "bullet": true, "level": 0}
    ]}
  }
}
```

- Paragraph fields:
  - `text`, `bold`, `italic`, `underline`
  - `font_size`, `font_name`
  - `color` (`"C0392B"`) or `theme_color` (`"ACCENT_1"`)
  - `alignment` (`LEFT`, `CENTER`, `RIGHT`, `JUSTIFY`)
  - `space_before`, `space_after`, `line_spacing` (in points)
  - `bullet` with `level`
- Carry over the properties the inventory shows for the slot, so the template's styling holds.
- Never type bullet characters. Bulleted paragraphs are left-aligned automatically.
- **On each slide listed, every text shape is cleared and then filled.** A shape left out of the file ends up empty, which removes leftover template text. Slides not listed are untouched.
- replace.py saves nothing if a key doesn't exist ("Shape 'shape-9' not found on 'slide-0'. Available shapes: …") or if new text overflows its box more than the old text did ("Text overflow worsened: slide-0/shape-2: …"). Shorten the text or choose a roomier layout.

## Editing slide XML

Read `ooxml.md` first. Then unpack, edit, validate after each change, and pack:

```bash
uv run <skill>/ooxml/scripts/unpack.py deck.pptx unpacked
uv run <skill>/ooxml/scripts/validate.py unpacked --original deck.pptx
uv run <skill>/ooxml/scripts/pack.py unpacked edited.pptx
```

## Speaker notes

```bash
uv run <skill>/scripts/notes.py deck.pptx                    # print {"slide-0": "…", …}
uv run <skill>/scripts/notes.py deck.pptx notes.json -o out.pptx
```

The JSON maps slide keys to plain text, with one paragraph per line. An empty string clears a slide's notes, and slides not listed keep theirs. In an html2pptx build, use `slide.addNotes('…')` instead.

## Checking the deck

A deck is done when it validates and every slide has been looked at.

1. **Validate.** For a new deck, run `uv run <skill>/ooxml/scripts/validate.py deck.pptx`. For an edited deck or one built from a template, add `--original template.pptx` so only new problems are reported. Fix everything it lists.

   On duplicated slides, validate.py also reports schema errors the template already had. Compare them with the source slide before chasing them.
2. **Look.** Run `uv run <skill>/ooxml/scripts/render.py deck.pptx pages` and read every image. Look for:
   - text cut off, overlapping, or crowding an edge
   - weak contrast
   - leftover template text or empty placeholders
   - anything off the grid

   `thumbnail.py deck.pptx grid --outline-placeholders` gives an overview, with every text box outlined.
3. Fix and repeat until both are clean.

## Pitfalls

- PptxGenJS colours take no `#`. `'#C0392B'` corrupts the file.
- Text that fits in the browser overflows in PowerPoint when a font is substituted. Keep to the font policy in `design.md`.
- Duplicating a slide by copying its XML by hand loses charts and shares notes between slides. Use `rearrange.py`.
- Slide indices are 0-based everywhere except in markitdown's output.
