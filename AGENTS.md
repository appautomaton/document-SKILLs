# Document Skills

Skills for creating, reading, and manipulating PDF, PPTX, XLSX, and DOCX files.

> `CLAUDE.md` in this directory is a symlink to this file (`AGENTS.md`).

## Python

- Always use `uv run` to execute Python scripts in these skills.
- All directly-run scripts declare their dependencies via PEP 723 inline metadata — `uv run` resolves them automatically. (Library modules imported by those scripts inherit the runner's environment and need no header of their own.) No manual `pip install` needed.
- When writing a new script, add a PEP 723 header:
  ```python
  # /// script
  # requires-python = ">=3.12"
  # dependencies = ["pypdf", "Pillow"]
  # ///
  ```
- Never run bare `pip install`. Never use the system Python (`/usr/bin/python3`).

### Python Packages

| Package | PyPI name | Used by | Purpose |
|---------|-----------|---------|---------|
| pypdf | `pypdf` | pdf | PDF reading/writing, form fields, annotations |
| pdf2image | `pdf2image` | pdf | PDF page to image conversion (requires poppler) |
| Pillow | `Pillow` | pdf, pptx | Image processing, drawing, fonts |
| pdfplumber | `pdfplumber` | pdf | Text and table extraction |
| reportlab | `reportlab` | pdf | PDF creation from scratch |
| pytesseract | `pytesseract` | pdf | OCR wrapper for Tesseract |
| pypdfium2 | `pypdfium2` | pdf | PDF rendering using PDFium engine |
| python-pptx | `python-pptx` | pptx | PowerPoint file manipulation |
| markitdown | `markitdown[pptx]` | pptx | Extract PPTX text as Markdown |
| openpyxl | `openpyxl` | xlsx | Excel file manipulation |
| pandas | `pandas` | xlsx | Data analysis, table operations |
| matplotlib | `matplotlib` | xlsx | Chart and visualization creation |
| lxml | `lxml` | pptx, docx | XML processing and XSD schema validation |
| defusedxml | `defusedxml` | pptx, docx | Secure XML parsing (XXE protection) |

## Node.js

Each skill that needs Node packages has its own `package.json` and `node_modules/`. Run `npm install` in the skill directory once to set up.

| Skill | Packages |
|-------|----------|
| pptx | `pptxgenjs` (pinned exactly: html2pptx repairs its XML output), `jszip`, `playwright-core` (drives the installed Google Chrome; it never downloads a browser), `sharp` (rasterizes SVG icons and gradients in agent-written scripts) |
| docx | `docx` |

pdf and xlsx do not use Node packages.

## System Tools (`brew` or `apt-get`)

On macOS, `brew bundle` at the repo root installs everything below. The Brewfile keeps optional tools commented out and skips uv and node when they are already on the PATH.

### Required

| Package | Install | Provides | Used by |
|---------|---------|----------|---------|
| poppler | `brew install poppler` | `pdftoppm`, `pdftotext`, `pdfimages` | pdf, pptx, docx |
| LibreOffice | `brew install --cask libreoffice` | `soffice` | pptx, xlsx, docx |
| pandoc | `brew install pandoc` | `pandoc` | docx |

### Optional

| Package | Install | Provides | Used by |
|---------|---------|----------|---------|
| tesseract | `brew install tesseract` | `tesseract` | pdf |
| tesseract-lang | `brew install tesseract-lang` | language packs | pdf |

## Skill Structure

Each skill has:
- `SKILL.md` — the prompt/instructions for the skill
- `scripts/` — scripts the agent runs by absolute path (`uv run <skill>/scripts/...`) from the user's working directory
- `package.json` — Node.js dependencies (docx, pptx only)
- `ooxml/` — unpack, pack, validate and render tooling for Office XML (docx, pptx only)

Each skill folder is the unit of distribution, so shared code is copied rather than linked. `docx/ooxml/` and `pptx/ooxml/` must stay identical, as must the three copies of `soffice.py` (in both `ooxml/scripts/` and `xlsx/scripts/`). Edit the docx copy, then sync: `rsync -a --delete --exclude __pycache__ docx/ooxml/ pptx/ooxml/ && cp docx/ooxml/scripts/soffice.py xlsx/scripts/`. A test enforces this.

LibreOffice always runs through `soffice.py`, which gives every run a private, throwaway profile and a timeout. Never call `soffice` directly from a script: a shared profile collides with any LibreOffice window the user has open.

## Tests

`tests/` runs every skill script through `uv run`, the way an agent does, against generated documents:

```bash
uv run --with pytest --with openpyxl --with python-docx --with python-pptx --with Pillow --with pypdf --with reportlab pytest tests -q
```

Every bug fix comes with a test that fails on the old code. python-docx is used only to build test fixtures. GitHub runs the same suite on Ubuntu for every pull request and every push to master (`.github/workflows/tests.yml`).
