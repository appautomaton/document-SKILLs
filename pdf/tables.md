# Table extraction with pdfplumber

Run scripts with `uv run --with pdfplumber script.py`. pdfplumber measures from the **top-left** of the page (`top` grows downward), unlike pypdf and reportlab, whose origin is the bottom-left.

## Choosing a strategy

`page.extract_tables(table_settings)` finds cell edges one of three ways, set separately for each axis:

| Table looks like | Settings |
|---|---|
| Ruled grid, every cell bordered | the default, `"lines"` on both axes |
| No rules, columns aligned by whitespace | `{"vertical_strategy": "text", "horizontal_strategy": "text"}` |
| Rules between rows only | `{"vertical_strategy": "text", "horizontal_strategy": "lines"}` |
| Detection keeps failing | explicit lines, below |

Explicit lines need `"explicit"` as the strategy too. Otherwise pdfplumber adds them to the lines it detects, and any stray rule on the page becomes an extra column:

```python
import pdfplumber

with pdfplumber.open("report.pdf") as pdf:
    page = pdf.pages[0]
    rows = page.extract_table({
        "vertical_strategy": "explicit",
        "horizontal_strategy": "explicit",
        "explicit_vertical_lines": [72, 172, 272, 372],         # x positions
        "explicit_horizontal_lines": [100, 125, 150, 175, 200],  # distances from the top
    })
```

Read the positions off `page.chars` or `page.extract_words()`, whose `x0` and `top` share the same coordinates. To restrict detection to one region, crop first with `page.crop((x0, top, x1, bottom))`.

## Seeing what pdfplumber sees

When a table comes out wrong, draw the detected edges and look at the image before tuning numbers:

```python
import pdfplumber

with pdfplumber.open("report.pdf") as pdf:
    page = pdf.pages[0]
    page.to_image(resolution=150).debug_tablefinder({"vertical_strategy": "text"}).save("debug.png")
```

Red lines are the detected edges, circles their intersections, and shaded areas the cells found. The usual adjustments are `snap_tolerance` and `join_tolerance` (merge nearly-aligned edges), `intersection_tolerance`, and, for the text strategy, `min_words_vertical` and `min_words_horizontal`.

## Tables across pages

pdfplumber works page by page. Concatenate rows, and drop a header that repeats at the top of later pages:

```python
import pdfplumber

with pdfplumber.open("report.pdf") as pdf:
    header, rows = None, []
    for page in pdf.pages:
        for table in page.extract_tables():
            if header is None:
                header, table = table[0], table[1:]
            elif table and table[0] == header:
                table = table[1:]
            rows.extend(table)
```

## When nothing works

- `page.extract_text()` returns nothing: the table is an image. Use [ocr.md](ocr.md).
- Merged cells come back as `None` in every cell except the first. Fill them from the left or above, depending on the layout.
- Very large documents: handle each page inside the loop rather than collecting everything first. pdfplumber caches parsed pages, so call `page.close()` when done with one.
