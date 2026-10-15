# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Render a document's pages to PNG images, to look at the output as a reader will.

Usage:
    uv run render.py <file.docx|.pptx|.xlsx|.pdf> <out_dir> [--pages 2-5] [--dpi 110]

Office files go through LibreOffice to PDF, then poppler's pdftoppm to PNG.
Prints one image path per line, in page order.
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import soffice  # noqa: E402


def render(src, out_dir, pages=None, dpi=110):
    src, out_dir = Path(src).resolve(), Path(out_dir)
    if shutil.which("pdftoppm") is None:
        raise SystemExit("pdftoppm not found. Install poppler: `brew install poppler` "
                         "or `apt-get install poppler-utils`.")
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        pdf = src
        if src.suffix.lower() != ".pdf":
            try:
                pdf = soffice.convert(src, tmp, "pdf", timeout=180)
            except soffice.SofficeError as e:
                raise SystemExit(str(e)) from None
        for old in out_dir.glob(f"{src.stem}-*.png"):
            old.unlink()
        cmd = ["pdftoppm", "-png", "-r", str(dpi)]
        if pages:
            first, _, last = pages.partition("-")
            cmd += ["-f", first, "-l", last or first]
        result = subprocess.run([*cmd, str(pdf), str(out_dir / src.stem)],
                                capture_output=True, text=True)
        if result.returncode != 0:
            raise SystemExit(f"pdftoppm failed: {result.stderr.strip()}")
    return sorted(out_dir.glob(f"{src.stem}-*.png"), key=lambda p: int(p.stem.rsplit("-", 1)[1]))


def main():
    parser = argparse.ArgumentParser(description="Render document pages to PNG")
    parser.add_argument("file")
    parser.add_argument("out_dir")
    parser.add_argument("--pages", help="page or range, 1-based, e.g. 3 or 2-5")
    parser.add_argument("--dpi", type=int, default=110)
    args = parser.parse_args()
    for image in render(args.file, args.out_dir, args.pages, args.dpi):
        print(image)


if __name__ == "__main__":
    main()
