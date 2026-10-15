# /// script
# requires-python = ">=3.12"
# dependencies = ["defusedxml>=0.7"]
# ///
"""Pack an unpacked directory back into a .docx, .pptx, or .xlsx file.

Usage:
    uv run pack.py <input_directory> <office_file> [--force]

Undoes the pretty-printing added by unpack.py, then checks that LibreOffice
can open the result; a file it cannot open is deleted and the exit status is 1.
--force skips that check.
"""

import argparse
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

import defusedxml.minidom

sys.path.insert(0, str(Path(__file__).parent))
import soffice  # noqa: E402

OPEN_CHECK_TARGETS = {
    ".docx": "html:HTML",
    ".pptx": "html:impress_html_Export",
    ".xlsx": "html:HTML (StarCalc)",
}


def main():
    parser = argparse.ArgumentParser(description="Pack a directory into an Office file")
    parser.add_argument("input_directory", help="Unpacked Office document directory")
    parser.add_argument("output_file", help="Output Office file (.docx/.pptx/.xlsx)")
    parser.add_argument("--force", action="store_true", help="Skip the LibreOffice open check")
    args = parser.parse_args()

    try:
        ok = pack_document(args.input_directory, args.output_file, validate=not args.force)
    except ValueError as e:
        sys.exit(f"Error: {e}")
    if args.force:
        print("Warning: skipped the open check; the file may be corrupt", file=sys.stderr)
    elif not ok:
        sys.exit("LibreOffice could not open the packed file, so it was deleted. "
                 "Run validate.py on the directory to find the problem.")


def pack_document(input_dir, output_file, validate=False):
    """Pack `input_dir` into `output_file`; return False if the open check fails."""
    input_dir, output_file = Path(input_dir), Path(output_file)
    if not input_dir.is_dir():
        raise ValueError(f"{input_dir} is not a directory")
    if output_file.suffix.lower() not in OPEN_CHECK_TARGETS:
        raise ValueError(f"{output_file} must be a .docx, .pptx, or .xlsx file")

    with tempfile.TemporaryDirectory() as temp_dir:
        content = Path(temp_dir) / "content"
        shutil.copytree(input_dir, content)
        for xml_file in [*content.rglob("*.xml"), *content.rglob("*.rels")]:
            condense_xml(xml_file)

        # [Content_Types].xml goes first; some consumers expect it there.
        files = sorted(
            (f for f in content.rglob("*") if f.is_file()),
            key=lambda f: (f.name != "[Content_Types].xml", str(f.relative_to(content))),
        )
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output_file, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in files:
                zf.write(f, f.relative_to(content))

    if validate and not opens_in_libreoffice(output_file):
        output_file.unlink()
        return False
    return True


def opens_in_libreoffice(path):
    with tempfile.TemporaryDirectory() as out:
        try:
            soffice.convert(path, out, OPEN_CHECK_TARGETS[path.suffix.lower()], timeout=120)
            return True
        except soffice.SofficeError as e:
            if "not found" in str(e) or "timed out" in str(e):
                print(f"Warning: open check skipped: {e}", file=sys.stderr)
                return True
            print(f"Open check failed: {e}", file=sys.stderr)
            return False


def condense_xml(xml_file):
    """Remove pretty-printing whitespace and comments.

    Indentation only ever sits between child elements, so whitespace-only text
    is dropped from elements that have element children and kept everywhere
    else. That preserves meaningful spaces such as <w:delText> </w:delText>.
    """
    dom = defusedxml.minidom.parse(str(xml_file))
    for element in dom.getElementsByTagName("*"):
        has_element_child = any(c.nodeType == c.ELEMENT_NODE for c in element.childNodes)
        for child in list(element.childNodes):
            if child.nodeType == child.COMMENT_NODE or (
                has_element_child
                and child.nodeType == child.TEXT_NODE
                and not child.nodeValue.strip()
            ):
                element.removeChild(child)
    xml_file.write_bytes(dom.toxml(encoding="UTF-8"))


if __name__ == "__main__":
    main()
