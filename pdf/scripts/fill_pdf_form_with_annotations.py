# /// script
# requires-python = ">=3.12"
# dependencies = ["pypdf>=6", "reportlab>=4"]
# ///
"""Fill a form that has no fillable fields by placing text annotations at boxes found on page images.

Usage:
    uv run fill_pdf_form_with_annotations.py <input.pdf> <fields.json> <output.pdf>

fields.json is described in forms.md: entry boxes in pixels of the images made
by convert_pdf_to_images.py, plus each page image's size. Every entry becomes a
FreeText annotation carrying its own appearance, so it renders the same in
every viewer: placed correctly on rotated pages and on pages whose box does not
start at (0, 0), and upright as displayed. Text too wide for its box is shrunk
to fit, down to 6 pt, with a warning.

Text outside Western European characters (Chinese, Cyrillic, ...) needs a
TrueType font that covers it. Set entry_text.font_file; otherwise a few common
system fonts are tried. Exit status 1 when fields.json has errors.
"""

import io
import json
import sys
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    FloatObject,
    NameObject,
    NumberObject,
    TextStringObject,
)
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).parent))
from pdf_coords import displayed_size, image_box_to_pdf  # noqa: E402

DEFAULT_FONT_SIZE = 12
MIN_FONT_SIZE = 6
PADDING = 2
FALLBACK_FONTS = [
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/arialuni.ttf",
]
# Rotates the appearance against the page's /Rotate, so text reads upright as displayed.
COUNTER_ROTATION = {0: [1, 0, 0, 1], 90: [0, 1, -1, 0], 180: [-1, 0, 0, -1], 270: [0, -1, 1, 0]}

_fonts = {}


def needs_unicode_font(text):
    try:
        text.encode("cp1252")
        return False
    except UnicodeEncodeError:
        return True


def font_for(text, font_file=None):
    """Name of a registered font that can draw `text`."""
    if not needs_unicode_font(text) and not font_file:
        return "Helvetica"
    for path in [font_file] if font_file else FALLBACK_FONTS:
        if not path or not Path(path).exists():
            continue
        if path not in _fonts:
            font = TTFont(f"F{len(_fonts)}", path)
            pdfmetrics.registerFont(font)
            _fonts[path] = font
        font = _fonts[path]
        if all(ord(ch) in font.face.charToGlyph for ch in text if not ch.isspace()):
            return font.fontName
    raise ValueError(
        f"no font covers {text!r}; set entry_text.font_file to a TrueType font (.ttf/.ttc) that does"
    )


def draw_appearance(text, width, height, size, color, font):
    """A one-page PDF, width x height points, with `text` laid out in it."""
    lines = text.split("\n")
    widest = max(pdfmetrics.stringWidth(line, font, size) for line in lines)
    room = width - 2 * PADDING
    if widest > room:
        size = max(MIN_FONT_SIZE, size * room / widest)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(width, height))
    c.setFont(font, size)
    c.setFillColor(HexColor(f"#{color}"))
    if len(lines) == 1:
        baseline = (height - 0.7 * size) / 2  # centres the capital height
    else:
        baseline = height - PADDING - 0.8 * size
    for i, line in enumerate(lines):
        c.drawString(PADDING, baseline - i * 1.2 * size, line)
    c.save()
    return PdfReader(buf).pages[0], size


def annotation(writer, page, rect, text, size, color, font):
    rotation = page.rotation % 360
    width, height = rect[2] - rect[0], rect[3] - rect[1]
    if rotation in (90, 270):
        width, height = height, width  # the box as the reader sees it
    drawn, used_size = draw_appearance(text, width, height, size, color, font)

    stream = DecodedStreamObject()
    stream.set_data(drawn.get_contents().get_data())
    stream.update({
        NameObject("/Type"): NameObject("/XObject"),
        NameObject("/Subtype"): NameObject("/Form"),
        NameObject("/BBox"): ArrayObject([FloatObject(v) for v in (0, 0, width, height)]),
        NameObject("/Matrix"): ArrayObject([FloatObject(v) for v in COUNTER_ROTATION[rotation] + [0, 0]]),
        NameObject("/Resources"): drawn["/Resources"].clone(writer),
    })
    r, g, b = (int(color[i:i + 2], 16) / 255 for i in (0, 2, 4))
    annot = DictionaryObject({
        NameObject("/Type"): NameObject("/Annot"),
        NameObject("/Subtype"): NameObject("/FreeText"),
        NameObject("/Rect"): ArrayObject([FloatObject(v) for v in rect]),
        NameObject("/Contents"): TextStringObject(text),
        NameObject("/DA"): TextStringObject(f"/Helv {used_size:.1f} Tf {r:.3f} {g:.3f} {b:.3f} rg"),
        NameObject("/F"): NumberObject(4),  # print
        NameObject("/BS"): DictionaryObject({NameObject("/W"): NumberObject(0)}),
        NameObject("/AP"): DictionaryObject({NameObject("/N"): writer._add_object(stream)}),
    })
    return annot, used_size


def check(fields, reader):
    errors = []
    pages = {p["page_number"]: p for p in fields.get("pages", [])}
    for n, info in pages.items():
        if not 1 <= n <= len(reader.pages):
            errors.append(f"pages: page {n} does not exist (the PDF has {len(reader.pages)})")
            continue
        width, height = displayed_size(reader.pages[n - 1])
        image_ratio, page_ratio = info["image_width"] / info["image_height"], width / height
        if abs(image_ratio / page_ratio - 1) > 0.03:
            errors.append(
                f"pages: page {n} image is {info['image_width']}x{info['image_height']} but the page "
                f"is {width:.0f}x{height:.0f} pt as displayed; use the size convert_pdf_to_images.py printed"
            )
    for field in fields["form_fields"]:
        n, box = field["page_number"], field["entry_bounding_box"]
        if n not in pages:
            errors.append(f"`{field.get('description', box)}`: no entry for page {n} in pages")
        elif not (0 <= box[0] < box[2] <= pages[n]["image_width"]
                  and 0 <= box[1] < box[3] <= pages[n]["image_height"]):
            errors.append(f"`{field.get('description', box)}`: entry box {box} is not inside the page image")
    return errors


def fill_pdf_form(input_pdf, fields_json, output_pdf):
    fields = json.loads(Path(fields_json).read_text())
    reader = PdfReader(input_pdf)
    if errors := check(fields, reader):
        print("ERROR: fix fields.json and run again:\n  " + "\n  ".join(errors))
        sys.exit(1)

    writer = PdfWriter(clone_from=reader)
    pages = {p["page_number"]: p for p in fields["pages"]}
    added = 0
    for field in fields["form_fields"]:
        entry = field.get("entry_text") or {}
        text = entry.get("text")
        if not text:
            continue
        n = field["page_number"]
        page = writer.pages[n - 1]
        image_size = (pages[n]["image_width"], pages[n]["image_height"])
        rect = image_box_to_pdf(page, field["entry_bounding_box"], image_size)
        size = float(entry.get("font_size", DEFAULT_FONT_SIZE))
        try:
            font = font_for(text, entry.get("font_file"))
        except ValueError as e:
            print(f"ERROR: `{field.get('description', text)}`: {e}")
            sys.exit(1)
        annot, used = annotation(writer, page, rect, text, size, entry.get("font_color", "000000"), font)
        if used < size:
            print(f"Warning: `{field.get('description', text)}` shrunk from {size:g} to {used:.1f} pt to fit its box")
        writer.add_annotation(page_number=n - 1, annotation=annot)
        added += 1

    with open(output_pdf, "wb") as f:
        writer.write(f)
    print(f"Added {added} text annotations; saved {output_pdf}")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit("Usage: uv run fill_pdf_form_with_annotations.py <input.pdf> <fields.json> <output.pdf>")
    fill_pdf_form(*sys.argv[1:])
