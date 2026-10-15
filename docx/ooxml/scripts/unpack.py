# /// script
# requires-python = ">=3.12"
# dependencies = ["defusedxml>=0.7"]
# ///
"""Unpack an Office file (.docx, .pptx, .xlsx) and pretty-print its XML for editing.

Usage:
    uv run unpack.py <office_file> <output_dir>

XML is written as UTF-8, so text in any script can be edited literally.
For .docx, also prints a fresh RSID to mark this editing session.
"""

import random
import sys
import zipfile
from pathlib import Path

import defusedxml.minidom

if len(sys.argv) != 3:
    sys.exit("Usage: uv run unpack.py <office_file> <output_dir>")
input_file, output_path = Path(sys.argv[1]), Path(sys.argv[2])

output_path.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(input_file) as zf:
    zf.extractall(output_path)

for xml_file in [*output_path.rglob("*.xml"), *output_path.rglob("*.rels")]:
    dom = defusedxml.minidom.parseString(xml_file.read_bytes())
    xml_file.write_bytes(dom.toprettyxml(indent="  ", encoding="UTF-8"))

if input_file.suffix.lower() == ".docx":
    rsid = "".join(random.choices("0123456789ABCDEF", k=8))
    print(f"Suggested RSID for edit session: {rsid}")
