# /// script
# requires-python = ">=3.12"
# dependencies = ["pypdf>=6"]
# ///
"""Convert boxes between page-image pixels and PDF points, accounting for rotation and page origin.

Usage:
    uv run pdf_coords.py <file.pdf> <page> <image_width>x<image_height> --to-pdf L,T,R,B
    uv run pdf_coords.py <file.pdf> <page> <image_width>x<image_height> --to-image L,B,R,T

Image boxes are [left, top, right, bottom] in pixels, origin at the top-left of
an image made by convert_pdf_to_images.py. PDF boxes are [left, bottom, right,
top] in points in the page's own coordinate space, the one its content, form
fields and annotations use. Pages are 1-based. Prints the converted box as JSON.

Page images show the crop box as a viewer displays it, rotated by /Rotate. PDF
coordinates ignore /Rotate and need not start at (0, 0), so a plain scale and
y-flip is wrong for rotated pages and for pages whose box is offset.
"""

import argparse
import json
import sys

from pypdf import PdfReader


def geometry(page):
    """(left, bottom, right, top, rotation) of the visible area in PDF points."""
    box = page.cropbox
    return float(box.left), float(box.bottom), float(box.right), float(box.top), page.rotation % 360


def displayed_size(page):
    """Width and height in points of the page as a viewer shows it."""
    x0, y0, x1, y1, rotation = geometry(page)
    return (y1 - y0, x1 - x0) if rotation in (90, 270) else (x1 - x0, y1 - y0)


def _to_pdf_point(page, u, v, image_size):
    x0, y0, x1, y1, rotation = geometry(page)
    width, height = displayed_size(page)
    dx, dy = u * width / image_size[0], v * height / image_size[1]  # points from top-left as displayed
    match rotation:
        case 0:
            return x0 + dx, y1 - dy
        case 90:
            return x0 + dy, y0 + dx
        case 180:
            return x1 - dx, y0 + dy
        case 270:
            return x1 - dy, y1 - dx
    raise ValueError(f"unsupported page rotation {rotation}")


def _to_image_point(page, x, y, image_size):
    x0, y0, x1, y1, rotation = geometry(page)
    width, height = displayed_size(page)
    match rotation:
        case 0:
            dx, dy = x - x0, y1 - y
        case 90:
            dx, dy = y - y0, x - x0
        case 180:
            dx, dy = x1 - x, y - y0
        case 270:
            dx, dy = y1 - y, x1 - x
        case _:
            raise ValueError(f"unsupported page rotation {rotation}")
    return dx * image_size[0] / width, dy * image_size[1] / height


def image_box_to_pdf(page, box, image_size):
    """[left, top, right, bottom] in image pixels -> [left, bottom, right, top] in PDF points."""
    (ax, ay), (bx, by) = (_to_pdf_point(page, box[0], box[1], image_size),
                          _to_pdf_point(page, box[2], box[3], image_size))
    return [min(ax, bx), min(ay, by), max(ax, bx), max(ay, by)]


def pdf_box_to_image(page, rect, image_size):
    """[left, bottom, right, top] in PDF points -> [left, top, right, bottom] in image pixels."""
    (ax, ay), (bx, by) = (_to_image_point(page, rect[0], rect[1], image_size),
                          _to_image_point(page, rect[2], rect[3], image_size))
    return [min(ax, bx), min(ay, by), max(ax, bx), max(ay, by)]


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("pdf")
    parser.add_argument("page", type=int, help="1-based page number")
    parser.add_argument("image_size", help="WIDTHxHEIGHT of the page image in pixels")
    direction = parser.add_mutually_exclusive_group(required=True)
    direction.add_argument("--to-pdf", metavar="L,T,R,B", help="image box to convert")
    direction.add_argument("--to-image", metavar="L,B,R,T", help="PDF box to convert")
    # Join a box to its flag, so one starting with a minus sign is not read as an option.
    argv = sys.argv[1:]
    for i, arg in enumerate(argv[:-1]):
        if arg in ("--to-pdf", "--to-image"):
            argv[i:i + 2] = [f"{arg}={argv[i + 1]}"]
            break
    args = parser.parse_args(argv)

    page = PdfReader(args.pdf).pages[args.page - 1]
    size = tuple(int(n) for n in args.image_size.lower().split("x"))
    if args.to_pdf:
        box = image_box_to_pdf(page, [float(n) for n in args.to_pdf.split(",")], size)
    else:
        box = pdf_box_to_image(page, [float(n) for n in args.to_image.split(",")], size)
    print(json.dumps([round(n, 2) for n in box]))


if __name__ == "__main__":
    main()
