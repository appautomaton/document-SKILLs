# /// script
# requires-python = ">=3.12"
# dependencies = ["pypdf>=6"]
# ///
"""Flatten a filled form: draw every form field and annotation into the page content.

Usage:
    uv run flatten_form.py <filled.pdf> <output.pdf>

Each field and annotation is painted from its own appearance, the same picture
viewers show, then removed, so the values can no longer be edited and look
identical everywhere. Covers fields filled by fill_fillable_fields.py and text
added by fill_pdf_form_with_annotations.py. Hidden annotations, and ones with
no appearance, are dropped without being drawn.
"""

import sys

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, ContentStream, DictionaryObject, NameObject

HIDDEN, NO_VIEW = 2, 32


def appearance(annotation):
    """The appearance stream a viewer would paint for `annotation`, or None."""
    if int(annotation.get("/F", 0)) & (HIDDEN | NO_VIEW):
        return None
    normal = annotation.get("/AP", {}).get("/N")
    if normal is None:
        return None
    normal = normal.get_object()
    if "/BBox" not in normal:  # a dictionary of states, as on checkboxes and radio buttons
        normal = normal.get(annotation.get("/AS", "/Off"))
        normal = normal.get_object() if normal is not None else None
    return normal


def placement(stream, rect):
    """Matrix that maps the appearance's transformed bounding box onto the annotation's rect."""
    a, b, c, d, e, f = [float(v) for v in stream.get("/Matrix", [1, 0, 0, 1, 0, 0])]
    x0, y0, x1, y1 = [float(v) for v in stream["/BBox"]]
    corners = [(x * a + y * c + e, x * b + y * d + f) for x in (x0, x1) for y in (y0, y1)]
    bx0, by0 = min(p[0] for p in corners), min(p[1] for p in corners)
    bx1, by1 = max(p[0] for p in corners), max(p[1] for p in corners)
    rx0, ry0, rx1, ry1 = [float(v) for v in rect]
    sx = (rx1 - rx0) / (bx1 - bx0) if bx1 > bx0 else 1
    sy = (ry1 - ry0) / (by1 - by0) if by1 > by0 else 1
    return sx, 0, 0, sy, rx0 - bx0 * sx, ry0 - by0 * sy


def flatten_page(writer, page, page_index):
    annotations = page.get("/Annots")
    if not annotations:
        return 0
    resources = page.setdefault(NameObject("/Resources"), DictionaryObject())
    xobjects = resources.setdefault(NameObject("/XObject"), DictionaryObject())
    ops, kept, drawn = [], ArrayObject(), 0
    for ref in annotations:
        annotation = ref.get_object()
        if annotation.get("/Subtype") in ("/Link", "/Popup"):
            kept.append(ref)
            continue
        stream = appearance(annotation)
        if stream is not None and "/BBox" in stream:
            name = f"/Flat{page_index}_{drawn}"
            xobjects[NameObject(name)] = writer._add_object(stream) if stream.indirect_reference is None \
                else stream.indirect_reference
            matrix = " ".join(f"{v:.4f}" for v in placement(stream, annotation["/Rect"]))
            ops.append(f"q {matrix} cm {name} Do Q")
            drawn += 1
    original = page.get_contents()
    data = original.get_data() if original is not None else b""
    content = ContentStream(None, writer)
    content.set_data(b"q\n" + data + b"\nQ\n" + "\n".join(ops).encode() + b"\n")
    page.replace_contents(content)
    if kept:
        page[NameObject("/Annots")] = kept
    else:
        del page["/Annots"]
    return drawn


def flatten(input_pdf, output_pdf):
    writer = PdfWriter(clone_from=PdfReader(input_pdf))
    drawn = sum(flatten_page(writer, page, i) for i, page in enumerate(writer.pages))
    if "/AcroForm" in writer.root_object:
        del writer.root_object["/AcroForm"]
    with open(output_pdf, "wb") as f:
        writer.write(f)
    print(f"Flattened {drawn} fields and annotations; saved {output_pdf}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Usage: uv run flatten_form.py <filled.pdf> <output.pdf>")
    flatten(*sys.argv[1:])
