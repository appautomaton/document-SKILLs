# PDF reference

Recipes for what the obvious API calls get wrong. Run Python with `uv run --with pypdf script.py`, adding packages as needed.

## Coordinates

| Source | Origin | Units |
|---|---|---|
| PDF content, pypdf, reportlab, form-field `/Rect` | bottom-left of the page box | points |
| pdfplumber (`top`, `bottom`), `pdftotext -bbox-layout` | top-left | points |
| Page images | top-left | pixels |

The page box need not start at (0, 0). Read `page.cropbox.left` and `page.cropbox.bottom` rather than assuming it does. `/Rotate` turns the page only for display: content keeps its unrotated coordinates. `scripts/pdf_coords.py` converts boxes between page images and PDF points with both taken into account.

## Text with positions

```python
import pdfplumber

with pdfplumber.open("in.pdf") as pdf:
    for w in pdf.pages[0].extract_words():
        print(w["text"], w["x0"], w["top"], w["x1"], w["bottom"])
```

- **Layout text from the command line:** `pdftotext -layout -f 1 -l 3 in.pdf out.txt` keeps columns side by side. pypdf's `extract_text()` returns text in the order it was drawn, which is not always reading order.
- **Word boxes from the command line:** `pdftotext -bbox-layout in.pdf out.html` writes XHTML with a box for every block, line and word.
- **pypdfium2 5.x**, fast and needing no poppler: `pdfium.PdfDocument("in.pdf")[0].get_textpage().get_text_range()`. For a region in PDF coordinates, use `get_text_bounded(left, bottom, right, top)`. `page.get_text()` no longer exists.

## Merging and splitting

```python
from pypdf import PdfWriter

writer = PdfWriter()
for path in ["a.pdf", "b.pdf"]:
    writer.append(path)               # keeps bookmarks and links; add_page() drops them
writer.write("merged.pdf")
```

- `writer.append(path, pages=(0, 3))` takes a page range.
- From the command line: `pdfunite a.pdf b.pdf merged.pdf` and `pdfseparate -f 2 -l 5 in.pdf page-%d.pdf` (poppler).
- Merging two forms whose fields share names links those fields, so filling one fills both. Flatten each form first with `scripts/flatten_form.py`.

## Stamps, watermarks and page edits

```python
from pypdf import PdfReader, PdfWriter

stamp = PdfReader("stamp.pdf").pages[0]
writer = PdfWriter(clone_from="in.pdf")
for page in writer.pages:
    page.transfer_rotation_to_content()   # make content coordinates match what is displayed
    page.merge_page(stamp, over=False)     # over=False puts the stamp beneath the content
writer.write("stamped.pdf")
```

- **Rotated pages.** Without `transfer_rotation_to_content()`, a stamp lands sideways on them.
- **Cropping.** Set `page.cropbox`, which is what viewers display. Leave `page.mediabox` alone unless you mean to discard the area outside it.
- **Rotating.** `page.rotate(90)` turns the page clockwise for display.

## Fonts for new PDFs

reportlab's built-in fonts (Helvetica, Times, Courier) cover Western European text only. Chinese, Japanese, Korean, Cyrillic and other scripts come out as black boxes. Register and embed a TrueType font that covers the text:

```python
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

pdfmetrics.registerFont(TTFont("Body", "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"))
c = canvas.Canvas("out.pdf")
c.setFont("Body", 14)
c.drawString(72, 720, "合同编号 Contract no. 2026-01")
c.save()
```

- `TTFont` reads `.ttf` and TrueType `.ttc` files, with `subfontIndex=` for collections. It cannot read CFF-based OpenType fonts, which includes most Noto CJK files.
- `UnicodeCIDFont("STSong-Light")` needs no font file, but it is not embedded, so its look depends on the viewer.
- `pdffonts out.pdf` lists each font and whether it is embedded.

## Encryption

- **AES needs an extra package.** Reading or writing AES-encrypted files needs `uv run --with 'pypdf[crypto]'`; without it pypdf raises `DependencyError`.
- **Empty passwords.** Many protected PDFs have an empty user password and open without one. Check `reader.is_encrypted`, then call `reader.decrypt(password)`.
- **Encrypting:** `writer.encrypt(user_password, owner_password, algorithm="AES-256")`. Avoid the RC4 algorithms, which are broken.

## Images and inspection

- **Embedded images:** `pdfimages -list in.pdf` shows each image with its size and resolution, and `pdfimages -all in.pdf out/img` extracts them in their original formats.
- **Document details:** `pdfinfo in.pdf` gives page count, page size, encryption and PDF version.
- **Damaged files:** `PdfWriter(clone_from=PdfReader("broken.pdf")).write("fixed.pdf")` often repairs a broken cross-reference table, since pypdf reads leniently by default.
