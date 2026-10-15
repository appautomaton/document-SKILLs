# /// script
# requires-python = ">=3.12"
# dependencies = ["pypdf>=6"]
# ///
"""Check the boxes in fields.json before filling a form with annotations.

Usage:
    uv run check_bounding_boxes.py <fields.json> [form.pdf]

Reports label and entry boxes that overlap, and entry boxes too short for their
font size. Boxes are in image pixels and font sizes in points; pass the PDF so
the two can be compared at the page's real scale, otherwise one pixel is taken
as one point. Prints SUCCESS or the failures; exit status 1 on failure.
"""

import json
import sys
from dataclasses import dataclass
from pathlib import Path

DEFAULT_FONT_SIZE = 12
MAX_MESSAGES = 20


@dataclass
class Box:
    rect: list[float]
    kind: str
    field: dict


def overlaps(a, b):
    return not (a[0] >= b[2] or a[2] <= b[0] or a[1] >= b[3] or a[3] <= b[1])


def get_bounding_box_messages(fields_json_stream, px_per_pt=None):
    """Messages describing problems in fields.json; `px_per_pt` maps page number to scale."""
    fields = json.load(fields_json_stream)
    messages = [f"Read {len(fields['form_fields'])} fields"]
    boxes = []
    for f in fields["form_fields"]:
        if "label_bounding_box" in f:
            boxes.append(Box(f["label_bounding_box"], "label", f))
        boxes.append(Box(f["entry_bounding_box"], "entry", f))

    failed = False

    def fail(message):
        nonlocal failed
        failed = True
        messages.append(f"FAILURE: {message}")
        if len(messages) >= MAX_MESSAGES:
            messages.append("Aborting further checks; fix bounding boxes and try again")
            return True
        return False

    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            if a.field["page_number"] == b.field["page_number"] and overlaps(a.rect, b.rect):
                if a.field is b.field:
                    message = (f"intersection between label and entry bounding boxes for "
                               f"`{a.field['description']}` ({a.rect}, {b.rect})")
                else:
                    message = (f"intersection between {a.kind} bounding box for `{a.field['description']}` "
                               f"({a.rect}) and {b.kind} bounding box for `{b.field['description']}` ({b.rect})")
                if fail(message):
                    return messages
        if a.kind == "entry" and "entry_text" in a.field:
            font_size = a.field["entry_text"].get("font_size", DEFAULT_FONT_SIZE)
            scale = (px_per_pt or {}).get(a.field["page_number"], 1)
            height = a.rect[3] - a.rect[1]
            if height < font_size * scale:
                if fail(f"entry bounding box height ({height}px) for `{a.field['description']}` is too "
                        f"short for {font_size}pt text ({font_size * scale:.0f}px on this page image). "
                        "Increase the box height or decrease the font size."):
                    return messages

    if not failed:
        messages.append("SUCCESS: All bounding boxes are valid")
    return messages


def page_scales(fields_path, pdf_path):
    """Pixels per point for each page listed in fields.json."""
    from pypdf import PdfReader

    sys.path.insert(0, str(Path(__file__).parent))
    from pdf_coords import displayed_size

    reader = PdfReader(pdf_path)
    scales = {}
    for info in json.loads(Path(fields_path).read_text()).get("pages", []):
        n = info["page_number"]
        if 1 <= n <= len(reader.pages):
            width, _ = displayed_size(reader.pages[n - 1])
            scales[n] = info["image_width"] / width
    return scales


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        sys.exit("Usage: uv run check_bounding_boxes.py <fields.json> [form.pdf]")
    scales = page_scales(sys.argv[1], sys.argv[2]) if len(sys.argv) == 3 else None
    with open(sys.argv[1]) as f:
        messages = get_bounding_box_messages(f, scales)
    print("\n".join(messages))
    sys.exit(0 if messages[-1].startswith("SUCCESS") else 1)
