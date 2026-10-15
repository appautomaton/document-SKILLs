# /// script
# requires-python = ">=3.12"
# dependencies = ["Pillow>=10"]
# ///
"""Draw the boxes from fields.json onto a page image, to check them by eye.

Usage:
    uv run create_validation_image.py <page_number> <fields.json> <page_image.png> <output.png>

Entry boxes are drawn in red and label boxes in blue.
"""

import json
import sys

from PIL import Image, ImageDraw


def create_validation_image(page_number, fields_json_path, input_path, output_path):
    with open(fields_json_path) as f:
        fields = json.load(f)["form_fields"]
    image = Image.open(input_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    drawn = 0
    for field in fields:
        if field["page_number"] != page_number:
            continue
        draw.rectangle(field["entry_bounding_box"], outline="red", width=2)
        drawn += 1
        if "label_bounding_box" in field:
            draw.rectangle(field["label_bounding_box"], outline="blue", width=2)
            drawn += 1
    image.save(output_path)
    print(f"Created validation image at {output_path} with {drawn} boxes")


if __name__ == "__main__":
    if len(sys.argv) != 5:
        sys.exit("Usage: uv run create_validation_image.py <page_number> <fields.json> "
                 "<page_image.png> <output.png>")
    create_validation_image(int(sys.argv[1]), *sys.argv[2:])
