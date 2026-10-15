---
name: xlsx
description: Create, edit, analyze, and recalculate Excel workbooks (.xlsx, .xlsm) with live formulas, formatting, and charts. Use when a task produces or modifies a spreadsheet file, turns CSV/TSV data into one, or needs values, formulas, or formatting read from one.
---

# Excel workbooks

You already know openpyxl and pandas. This skill adds what you can't see from the code: a recalculation step that reports what is actually wrong in the workbook, and the behaviours of openpyxl and LibreOffice that silently break files.

## Running scripts

`<skill>` is the directory containing this file. Run bundled scripts by absolute path from the user's working directory, so relative paths to their files keep working:

```bash
uv run <skill>/scripts/recalc.py model.xlsx
```

Run Python you write with its dependencies declared, either `uv run --with openpyxl script.py` or a PEP 723 header. Recalculation needs LibreOffice (`soffice`).

## Choosing a tool

- **openpyxl** for any workbook you deliver: formulas, formatting, charts, validation, comments. It keeps charts, images, comments, data validation and conditional formatting of files it loads. It drops what it does not model, such as shapes, text boxes, slicers and form controls, so check before editing a workbook that has them.
- **pandas** for analysis and bulk reads. Its writer keeps only values, so never use it to edit a workbook someone will keep working in.
- For `.xlsm`, load with `load_workbook(path, keep_vba=True)`, or the macros are lost on save.

## Formulas, not values

Anything derived belongs in the sheet as a formula, so the workbook stays correct when its inputs change. Compute in Python only what has no spreadsheet form, then write it as a labelled input.

```python
ws["B10"] = "=SUM(B2:B9)"          # not ws["B10"] = df["Sales"].sum()
ws["C5"] = "=(C4-C2)/C2"           # growth, from the cells it depends on
ws["D3"] = "=B3*(1+$B$1)"          # assumptions live in their own cells
```

## Checking the output

openpyxl writes formulas without values, so a file is not finished until it has been recalculated. Run this after every save that touched formulas, and fix what it reports before delivering:

```bash
uv run <skill>/scripts/recalc.py model.xlsx
```

It recalculates in LibreOffice, writes the values back into the file, and prints JSON. The exit status is 0 when clean, 1 when there are problems, and 2 when it could not run.

| Field | Meaning and fix |
|---|---|
| `errors` | Error values by type, e.g. `{"#DIV/0!": {"count": 3, "locations": ["Model!C7", …]}}`, with at most 50 locations per type. Fix the formulas at those cells. |
| `missing_prefix` | Newer functions written without the prefix the file format requires (see below). The file is left untouched, and each entry carries the corrected formula in `fix`. |
| `circular_references` | Groups of cells that depend on each other. LibreOffice shows these as `#VALUE!`, so fix the cycle first. |
| `uncalculated` | Formulas LibreOffice left without a value. Usually a function LibreOffice does not implement; the workbook may still work in Excel, but tell the user. |

Links to other workbooks make it stop, because recalculating would overwrite the linked values. Pass `--force` only if the user accepts that.

## Pitfalls that fail silently

- **Function prefixes.** Functions newer than Excel 2007 are stored with a prefix. Write `=_xlfn.XLOOKUP(…)`, `=_xlfn.TEXTJOIN(…)`, `=_xlfn.IFS(…)`, and `=_xlfn._xlws.FILTER(…)` and `=_xlfn._xlws.SORT(…)`. Without it, Excel and LibreOffice both show `#NAME?`. recalc catches these before they do damage.
- **Inserting or deleting rows and columns.** `insert_rows`, `delete_rows`, `insert_cols` and `delete_cols` move cells but do not rewrite any formula that refers to them. `=SUM(B1:B4)` stays `=SUM(B1:B4)` after a row is inserted above it. Rewrite the affected formulas yourself, or lay out the sheet so nothing needs inserting.
- **`data_only=True`** reads cached values. Saving a workbook opened that way replaces every formula with its last value, permanently.
- **Dynamic arrays.** openpyxl cannot write spilling formulas. FILTER, SORT, UNIQUE and SEQUENCE land in one cell, and Excel prefixes them with `@`. Prefer formulas that return one value per cell.
- **Indexing.** Rows and columns are 1-based. Use `get_column_letter` and `column_index_from_string`; never count letters by hand past column Z.

## Charts

Use openpyxl's native charts (`openpyxl.chart`) for charts that belong in the workbook; they stay linked to the cells. Render matplotlib images only when the chart is going somewhere else.

## Existing workbooks and templates

Study the file before changing it, and match its fonts, fills, number formats, column widths and layout exactly. Its conventions override everything below.

## Financial models

Unless the user or the template says otherwise:

- **Font colour by role:** blue `0000FF` for hard-coded inputs, black for formulas, green `008000` for links to other sheets, red `FF0000` for links to other files. A yellow `FFFF00` fill marks key assumptions.
- **Number formats:**
  - Currency: `$#,##0;($#,##0);-`, with units in the header, e.g. "Revenue ($mm)".
  - Percentages: `0.0%`.
  - Multiples: `0.0x`.
  - Negatives: in parentheses.
  - Years: written as text, so "2026" never becomes "2,026".
- **Structure:** every assumption sits in its own labelled cell and is referenced, never typed into a formula. Each projection period uses the same formula as the one before it.
- **Sources:** give every hard-coded number a source in a cell comment or an adjacent cell, e.g. "Source: Company 10-K, FY2025, p. 45".
