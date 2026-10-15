# /// script
# requires-python = ">=3.12"
# dependencies = ["pdf2image>=1.17", "pypdf>=6", "Pillow>=10"]
# ///
"""Render PDF pages to PNG images, one page at a time, as a viewer displays them.

Usage:
    uv run convert_pdf_to_images.py <input.pdf> <output_dir> [--pages 2-5] [--max-dim 1000]
                                    [--fields field_info.json]

Writes page_<n>.png into output_dir (created if missing), scaled so the longer
side is --max-dim pixels, and prints each path with its size. The size is what
fields.json needs as image_width and image_height.

--fields takes the JSON from extract_form_field_info.py and also writes
page_<n>_fields.png with every fillable field outlined and labelled with its
field_id, so fields can be matched to their labels without converting
coordinates by hand.

Requires poppler (pdftoppm).
"""

import argparse
import json
import sys
from pathlib import Path

from pdf2image import convert_from_path
from PIL import ImageDraw
from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).parent))
from pdf_coords import pdf_box_to_image  # noqa: E402


def page_numbers(spec, count):
    if not spec:
        return range(1, count + 1)
    first, _, last = spec.partition("-")
    return range(int(first), min(int(last or first), count) + 1)


def draw_fields(image, page, page_number, fields):
    draw = ImageDraw.Draw(image)
    for field in fields:
        if field.get("page") != page_number:
            continue
        boxes = [(o["rect"], f'{field["field_id"]}={o["value"]}') for o in field.get("radio_options", [])]
        boxes = boxes or [(field["rect"], field["field_id"])]
        for rect, label in boxes:
            box = pdf_box_to_image(page, rect, image.size)
            draw.rectangle(box, outline="red", width=2)
            draw.text((box[0] + 2, box[1] - 11), label, fill="red")
    return image


def convert(pdf_path, output_dir, pages=None, max_dim=1000, fields_path=None):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    reader = PdfReader(pdf_path)
    fields = json.loads(Path(fields_path).read_text()) if fields_path else None
    written = 0
    for n in page_numbers(pages, len(reader.pages)):
        image = convert_from_path(pdf_path, first_page=n, last_page=n, size=max_dim, use_cropbox=True)[0]
        path = output_dir / f"page_{n}.png"
        image.save(path)
        print(f"page {n}: {path} ({image.width}x{image.height})")
        if fields is not None:
            marked = output_dir / f"page_{n}_fields.png"
            draw_fields(image.convert("RGB"), reader.pages[n - 1], n, fields).save(marked)
            print(f"page {n} with fields: {marked}")
        written += 1
    print(f"Rendered {written} page(s)")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("pdf")
    parser.add_argument("output_dir")
    parser.add_argument("--pages", help="page or range, 1-based, e.g. 3 or 2-5")
    parser.add_argument("--max-dim", type=int, default=1000, help="longer side in pixels (default 1000)")
    parser.add_argument("--fields", help="field_info.json from extract_form_field_info.py")
    args = parser.parse_args()
    convert(args.pdf, args.output_dir, args.pages, args.max_dim, args.fields)


if __name__ == "__main__":
    main()
