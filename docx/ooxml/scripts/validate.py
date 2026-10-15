# /// script
# requires-python = ">=3.12"
# dependencies = ["lxml>=5"]
# ///
"""Validate an Office document's XML against the OOXML schemas.

Usage:
    uv run validate.py <unpacked_dir | file.docx | file.pptx> [--original FILE] [--author NAME]

With --original, only errors the edit introduced are reported, and for .docx
every change must be a tracked change (see validation/redlining.py). Without
it, every schema error counts, which suits documents generated from scratch.
--author names whose earlier tracked insertions may be edited directly.
Exit status 0 when valid, 1 otherwise.
"""

import argparse
import sys
import tempfile
import zipfile
from pathlib import Path

from validation import DOCXSchemaValidator, PPTXSchemaValidator, RedliningValidator


def main():
    parser = argparse.ArgumentParser(description="Validate Office document XML files")
    parser.add_argument("target", type=Path, help="Unpacked directory, or a .docx/.pptx file")
    parser.add_argument("--original", type=Path, help="The file before editing")
    parser.add_argument("--author", help="Author of this session's tracked changes (.docx)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    reference = args.original or args.target
    kind = reference.suffix.lower()
    if kind not in (".docx", ".pptx"):
        sys.exit(f"Error: validation supports .docx and .pptx, not {kind or args.target}")
    if args.original and not args.original.is_file():
        sys.exit(f"Error: {args.original} is not a file")

    with tempfile.TemporaryDirectory() as temp_dir:
        unpacked = args.target
        if args.target.is_file():
            unpacked = Path(temp_dir)
            with zipfile.ZipFile(args.target) as zf:
                zf.extractall(unpacked)
        elif not args.target.is_dir():
            sys.exit(f"Error: {args.target} does not exist")

        schema = DOCXSchemaValidator if kind == ".docx" else PPTXSchemaValidator
        validators = [schema(unpacked, args.original, verbose=args.verbose)]
        if kind == ".docx" and args.original:
            validators.append(
                RedliningValidator(unpacked, args.original, args.verbose, author=args.author)
            )
        success = all([v.validate() for v in validators])

    print("All validations PASSED!" if success else "Validation FAILED")
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
