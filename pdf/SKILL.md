---
name: pdf
description: Read, create, fill, and transform PDF files. Covers extracting text and tables, OCR of scanned pages, filling fillable and flat forms, and flattening, merging, splitting, rotating, stamping and encrypting. Use when a task takes a .pdf as input or must produce one.
---

# PDF files

You already know pypdf, pdfplumber and reportlab. This skill adds what they don't give you: form-filling scripts that check their own input, a way to see pages as a reader will, and the PDF behaviours that silently put content in the wrong place.

## Running scripts

`<skill>` is the directory containing this file. Run bundled scripts by absolute path from the user's working directory, so relative paths to their files keep working:

```bash
uv run <skill>/scripts/convert_pdf_to_images.py report.pdf pages
```

Run Python you write with its dependencies declared, either `uv run --with pypdf script.py` or a PEP 723 header. Rendering pages needs poppler (`pdftoppm`); OCR also needs Tesseract.

## Choosing a tool

| Task | Use |
|---|---|
| Fill a form, fillable or flat | [forms.md](forms.md), always. It has scripts for every step. |
| Text | pdfplumber, or `pdftotext -layout` from the command line. Text missing from pages that visibly have it means a scan: see [ocr.md](ocr.md). |
| Tables | pdfplumber: see [tables.md](tables.md) |
| New PDFs | reportlab: Platypus for flowing documents, canvas for exact placement |
| Merge, split, rotate, crop, stamp, encrypt | pypdf: see [reference.md](reference.md) for the calls that keep bookmarks, links and orientation intact |
| See what a page looks like | `scripts/convert_pdf_to_images.py` |

## Checking the output

Whenever you create or change a PDF, render the pages you touched and look at them before delivering. Check that the text is present and readable, nothing is clipped or overlapping, and every stamp or value is where it belongs:

```bash
uv run <skill>/scripts/convert_pdf_to_images.py out.pdf check --pages 1-3
```

## Pitfalls that fail silently

- **Two coordinate systems.** PDF coordinates start at the bottom-left of the page box, in points. pdfplumber and page images start at the top-left. The page box need not start at (0, 0), so read `page.cropbox.left` and `.bottom`.
- **Rotated pages.** `/Rotate` turns a page only for display; content and form fields keep unrotated coordinates. Anything placed with a plain scale and y-flip lands in the wrong spot. Convert boxes with `scripts/pdf_coords.py`, and call `page.transfer_rotation_to_content()` before stamping.
- **Non-Latin text in new PDFs.** reportlab's built-in fonts draw Chinese, Cyrillic and similar scripts as black boxes. Register and embed a TrueType font; see [reference.md](reference.md#fonts-for-new-pdfs).
- **Merging.** `PdfWriter.append()` keeps bookmarks and links, while copying pages with `add_page()` drops them. Merged forms with matching field names become one field, so filling one fills both.
- **AES encryption** needs `uv run --with 'pypdf[crypto]'`. Without it, pypdf raises `DependencyError` on open or on encrypt.

## Scripts

| Script | Does |
|---|---|
| `check_fillable_fields.py <pdf>` | Says which form path in forms.md applies |
| `extract_form_field_info.py <pdf> <out.json>` | Lists fillable fields, their pages, boxes and accepted values |
| `fill_fillable_fields.py <pdf> <values.json> <out.pdf>` | Fills fields after checking every id, page and value |
| `convert_pdf_to_images.py <pdf> <dir> [--pages] [--fields]` | Renders pages one at a time to PNG, optionally outlining each fillable field |
| `check_bounding_boxes.py <fields.json> [pdf]` | Finds overlapping or too-short boxes before a flat form is filled |
| `create_validation_image.py <page> <fields.json> <png> <out.png>` | Draws those boxes on a page image for checking by eye |
| `fill_pdf_form_with_annotations.py <pdf> <fields.json> <out.pdf>` | Fills a flat form with text that renders identically everywhere |
| `flatten_form.py <pdf> <out.pdf>` | Draws filled values into the page so they can't be edited |
| `pdf_coords.py <pdf> <page> <WxH> --to-pdf/--to-image <box>` | Converts boxes between page-image pixels and PDF points |
