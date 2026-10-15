# Document Processing Skills

English | [中文](README.zh-CN.md)

A collection of Claude Code / Codex skills for document manipulation — PDF extraction/forms, Excel analysis/formulas, Word, and PowerPoint.

## Quick start

### Claude Code, as a plugin

Two commands inside Claude Code, no cloning:

```
/plugin marketplace add appautomaton/document-SKILLs
/plugin install document-skills@appautomaton-skills
```

Skills are then invoked as `document-skills:pdf`, `document-skills:docx`, and so on. The system tools under [Dependencies](#dependencies) are still required; the docx and pptx skills install their Node packages the first time they need them.

### Any agent, via symlinks

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
| [docx](docx/) | Create, redline, comment on, and read Word documents — real tracked changes, checked so no edit goes untracked |
| [pdf](pdf/) | Extract text/tables, fill fillable and flat forms, merge/split/stamp, OCR scanned pages |
| [pptx](pptx/) | Build decks from HTML as native slides, fill templates, duplicate and reorder slides, edit speaker notes |
| [xlsx](xlsx/) | Create/edit workbooks with live formulas, then recalculate and get every error, circular reference, and broken function by cell |

Every workflow checks its own output before handing it back: workbooks are recalculated and scanned for errors, Word and PowerPoint files are validated against the OOXML schemas, and documents, PDFs and decks are rendered so the agent can look at them.

## Dependencies

> [!NOTE]
> Python scripts use [uv](https://docs.astral.sh/uv/) + PEP 723 inline metadata — no virtual environments or `pip install` needed. Just `uv run`.

System tools:

```bash
# macOS: one command via the repo Brewfile.
# Installs uv and node only if missing, optional tools are commented in the file.
brew bundle

# Linux
sudo apt-get install -y pandoc poppler-utils libreoffice
sudo apt-get install -y tesseract-ocr   # optional, OCR of scanned PDFs
```

Node.js packages (docx and pptx skills only):

```bash
cd docx && npm install
cd ../pptx && npm install
```

## Development

`tests/` runs every script through `uv run`, the way an agent does. See [AGENTS.md](AGENTS.md#tests).

## License

MIT — see [LICENSE](LICENSE).

---

🤖 Checkout [linux.do](https://linux.do) for more fun stuff about AI!
