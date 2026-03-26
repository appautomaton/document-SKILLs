# Document Processing Skills

English | [中文](README.zh-CN.md)

A collection of Claude Code / Codex skills for document manipulation — PDF extraction/forms, Excel analysis/formulas, Word, and PowerPoint.

## Quick start

> [!TIP]
> Clone this repo anywhere you keep your skills, then symlink each skill into your agent's skills directory.

```bash
git clone https://github.com/appautomaton/document-SKILLs.git ~/skills/documents
cd ~/skills/documents

# Claude Code
for s in docx pdf pptx xlsx; do
  ln -s "$(pwd)/$s" ~/.claude/skills/$s
done

# Codex
for s in docx pdf pptx xlsx; do
  ln -s "$(pwd)/$s" ~/.codex/skills/$s
done
```

## Skills

| Skill | What it does |
|---|---|
| [docx](docx/) | Create, edit, and analyze Word documents — tracked changes, comments, formatting |
| [pdf](pdf/) | Extract text/tables, fill forms, merge/split, OCR scanned pages |
| [pptx](pptx/) | Edit existing presentations — reorder slides, replace text, thumbnails |
| [xlsx](xlsx/) | Create/edit spreadsheets — formulas, formatting, data analysis |

## Dependencies

> [!NOTE]
> Python scripts use [uv](https://docs.astral.sh/uv/) + PEP 723 inline metadata — no virtual environments or `pip install` needed. Just `uv run`.

System tools:

```bash
# macOS
brew install pandoc poppler tesseract qpdf
brew install --cask libreoffice

# Linux
sudo apt-get install -y pandoc poppler-utils tesseract-ocr qpdf libreoffice
```

Node.js packages (docx and pptx skills only):

```bash
cd docx && npm install
cd ../pptx && npm install
```

## Output Organization

> [!TIP]
> Add `outputs/` to your `.gitignore` to keep generated files out of version control.

```
outputs/
└── <document-name>/
    ├── final.pptx
    ├── inventory.json
    ├── replacements.json
    ├── unpacked/
    ├── thumbnails/
    └── images/
```

## Source

Based on [Anthropic's official skills](https://github.com/anthropics/skills).

---

🤖 Checkout [linux.do](https://linux.do) for more fun stuff about AI!
