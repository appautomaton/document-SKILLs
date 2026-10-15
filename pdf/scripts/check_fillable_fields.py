# /// script
# requires-python = ">=3.12"
# dependencies = ["pypdf>=6"]
# ///
"""Say whether a PDF has fillable form fields, which decides the path to take in forms.md.

Usage:
    uv run check_fillable_fields.py <file.pdf>
"""

import sys

from pypdf import PdfReader

if len(sys.argv) != 2:
    sys.exit("Usage: uv run check_fillable_fields.py <file.pdf>")
fields = PdfReader(sys.argv[1]).get_fields()
if fields:
    print(f"This PDF has {len(fields)} fillable form fields: follow 'Fillable forms' in forms.md")
else:
    print("This PDF has no fillable form fields: follow 'Forms without fields' in forms.md")
