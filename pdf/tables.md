# Table Extraction Guide

Advanced table extraction from PDFs using pdfplumber.

## Quick Start

```python
import pdfplumber

with pdfplumber.open("report.pdf") as pdf:
    page = pdf.pages[0]
    tables = page.extract_tables()

    for table in tables:
        for row in table:
            print(row)
```

## Detection Strategies

### Strategy 1: Line-based (tables with visible borders)

```python
table_settings = {
    "vertical_strategy": "lines",
    "horizontal_strategy": "lines"
}

tables = page.extract_tables(table_settings=table_settings)
```

### Strategy 2: Text-based (borderless tables)

```python
table_settings = {
    "vertical_strategy": "text",
    "horizontal_strategy": "text"
}

tables = page.extract_tables(table_settings=table_settings)
```

### Strategy 3: Explicit boundaries

Define table region manually when auto-detection fails:

```python
# Bounding box: (x0, top, x1, bottom)
bbox = (50, 100, 550, 700)

cropped = page.within_bbox(bbox)
tables = cropped.extract_tables()
```

### Strategy 4: Fine-tuned settings

```python
table_settings = {
    "vertical_strategy": "lines",
    "horizontal_strategy": "lines",
    "snap_tolerance": 3,
    "join_tolerance": 3,
    "edge_min_length": 3,
    "min_words_vertical": 3,
    "min_words_horizontal": 1,
    "intersection_tolerance": 3
}

tables = page.extract_tables(table_settings=table_settings)
```

### Strategy 5: Explicit lines

For complex layouts where auto-detection fails, manually define table grid lines:

```python
# Define vertical lines at specific x-coordinates
vertical_lines = [50, 150, 250, 350, 450, 550]

# Define horizontal lines at specific y-coordinates
horizontal_lines = [100, 130, 160, 190, 220, 250]

table_settings = {
    "explicit_vertical_lines": vertical_lines,
    "explicit_horizontal_lines": horizontal_lines
}

tables = page.extract_tables(table_settings=table_settings)
```

Use `debug_tablefinder()` to identify the correct coordinates.

## Multi-page Tables

Extract tables that span multiple pages:

```python
import pdfplumber

def extract_multipage_table(pdf_path, start_page=0, end_page=None):
    """Extract table that spans multiple pages."""
    all_rows = []
    headers = None

    with pdfplumber.open(pdf_path) as pdf:
        pages = pdf.pages[start_page:end_page]

        for page_num, page in enumerate(pages):
            tables = page.extract_tables()
            if not tables:
                continue

            table = tables[0]  # Assume first table on page

            if page_num == 0:
                headers = table[0]
                all_rows.extend(table[1:])
            else:
                # Skip repeated headers on subsequent pages
                if table[0] == headers:
                    all_rows.extend(table[1:])
                else:
                    all_rows.extend(table)

    return [headers] + all_rows if headers else all_rows

# Usage
table = extract_multipage_table("report.pdf", start_page=2, end_page=5)
print(f"Extracted {len(table) - 1} rows")
```

## Handling Merged Cells

Process tables with merged/empty cells:

```python
def handle_merged_cells(table):
    """Fill empty cells with value from left (for horizontal merges)."""
    processed = []

    for row in table:
        new_row = []
        last_value = None

        for cell in row:
            if cell is None or cell == "":
                new_row.append(last_value)
            else:
                new_row.append(cell)
                last_value = cell

        processed.append(new_row)

    return processed

# Usage
with pdfplumber.open("document.pdf") as pdf:
    table = pdf.pages[0].extract_tables()[0]
    clean_table = handle_merged_cells(table)
```

## Normalizing Column Counts

Handle tables with inconsistent column counts (common in poorly-formatted PDFs):

```python
def normalize_table_columns(table):
    """Normalize table with inconsistent column counts by padding short rows."""
    if not table:
        return table

    # Find max column count
    max_cols = max(len(row) for row in table)

    # Pad short rows with empty strings
    normalized = []
    for row in table:
        if len(row) < max_cols:
            row = row + [""] * (max_cols - len(row))
        normalized.append(row)

    return normalized

# Usage
table = page.extract_tables()[0]
normalized = normalize_table_columns(table)
```

## Nested Tables

Extract tables from a specific region (useful when PDFs have tables within tables):

```python
def extract_nested_tables(page, bbox):
    """Extract tables from a specific region of the page."""
    # bbox: (x0, top, x1, bottom)
    cropped = page.within_bbox(bbox)
    tables = cropped.extract_tables()

    return [table for table in tables if table]

# Usage
with pdfplumber.open("document.pdf") as pdf:
    page = pdf.pages[0]

    # Extract tables from a specific region
    inner_tables = extract_nested_tables(page, (100, 200, 500, 400))

    for table in inner_tables:
        print(table)
```

## Visual Debugging

Debug table detection by visualizing what pdfplumber sees:

```python
with pdfplumber.open("document.pdf") as pdf:
    page = pdf.pages[0]

    # Create debug image showing detected table lines
    img = page.to_image(resolution=150)
    img.debug_tablefinder().save("debug_tables.png")
```

Review the debug image to understand why tables aren't detected correctly, then adjust `table_settings`.

## Export Formats

### Export to CSV

```python
import csv

def export_to_csv(table, output_path):
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(table)

export_to_csv(table, "output.csv")
```

### Export to Excel

```python
import pandas as pd

def export_to_excel(tables, output_path):
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for i, table in enumerate(tables):
            if not table:
                continue
            df = pd.DataFrame(table[1:], columns=table[0])
            df.to_excel(writer, sheet_name=f"Table_{i+1}", index=False)

export_to_excel(tables, "output.xlsx")
```

### Export to JSON

```python
import json

def export_to_json(table, output_path):
    if not table:
        return

    headers = table[0]
    records = [
        {headers[i]: row[i] for i in range(len(headers))}
        for row in table[1:]
    ]

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)

export_to_json(table, "output.json")
```

## Troubleshooting

### Tables not detected

1. Use `debug_tablefinder()` to visualize detection
2. Try different strategies: `lines` → `text` → explicit boundaries
3. Check if table is actually an image (use OCR instead)

### Incorrect cell values

1. Adjust `snap_tolerance` and `join_tolerance`
2. Use explicit boundaries to isolate the table region
3. Check text extraction quality with `page.extract_text()`

### Performance with large PDFs

Process pages individually to manage memory:

```python
with pdfplumber.open("large.pdf") as pdf:
    for page in pdf.pages:
        tables = page.extract_tables()
        # Process immediately, don't accumulate
```

## Dependencies

```bash
pip install pdfplumber pandas openpyxl
```
