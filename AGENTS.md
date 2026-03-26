# Document Skills

Skills for creating, reading, and manipulating PDF, PPTX, XLSX, and DOCX files.

> `CLAUDE.md` in this directory is a symlink to this file (`AGENTS.md`).

## Python

- Always use `uv run` to execute Python scripts in these skills.
- All scripts declare their dependencies via PEP 723 inline metadata — `uv run` resolves them automatically. No manual `pip install` needed.
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
| openpyxl | `openpyxl` | xlsx | Excel file manipulation |
| pandas | `pandas` | xlsx | Data analysis, table operations |
| matplotlib | `matplotlib` | xlsx | Chart and visualization creation |
| lxml | `lxml` | pptx, docx | XML processing and XSD schema validation |
| defusedxml | `defusedxml` | pptx, docx | Secure XML parsing (XXE protection) |
| six | `six` | pptx | Python 2/3 compatibility |

## Node.js

Each skill that needs Node packages has its own `package.json` and `node_modules/`. Run `npm install` in the skill directory once to set up.

| Skill | Packages |
|-------|----------|
| pptx | `pptxgenjs`, `playwright` (launches Chromium for HTML→image rendering), `sharp`, `react`, `react-dom`, `react-icons` |
| docx | `docx` |

pdf and xlsx do not use Node packages.

## System Tools (`brew` or `apt-get`)

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
| qpdf | `brew install qpdf` | `qpdf` | pdf |
| coreutils | `brew install coreutils` | `gtimeout` | xlsx |

## Skill Structure

Each skill has:
- `SKILL.md` — the prompt/instructions for the skill
- `scripts/` — Python scripts the agent calls via `uv run`
- `package.json` — Node.js dependencies (docx, pptx only)
- `ooxml/` — XML pack/unpack/validate tooling (docx, pptx only)

All output files go to the user's working directory. Never write artifacts inside the skill folder.
