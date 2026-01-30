# Document Processing Skills

English | [中文](README.zh-CN.md)

A set of improved SKILLs from the Official Anthropic skills for Word, PDF, PowerPoint, and Excel manipulation in Claude Code and Codex.

## How to Use

### Option 1: Git Subtree

```bash
# Replace <skills_dir> with your agent's skills path
git subtree add --prefix=<skills_dir> \
  https://github.com/appautomaton/document-SKILLs.git master --squash
```

### Option 2: Clone and Copy

```bash
git clone https://github.com/appautomaton/document-SKILLs.git /tmp/doc-skills
mkdir -p <skills_dir>
cp -r /tmp/doc-skills/{docx,pdf,pptx,xlsx} <skills_dir>/
cp /tmp/doc-skills/requirements.txt <skills_dir>/requirements.txt
rm -rf /tmp/doc-skills
```

If you already have a `requirements.txt` in your skills directory, merge instead of overwriting.
`requirements.txt` lists the Python dependencies used by these skills.
Recommended: use `uv` and add a “use uv” requirement to your own agent rules (adapt to your environment/install method).

## Dependencies (Install Once)

> [!NOTE]
> Use an isolated environment where possible; `uv` is the recommended installer.

```bash
# System packages
sudo apt-get install -y pandoc libreoffice poppler-utils tesseract-ocr

# Optional (PDF CLI workflows)
sudo apt-get install -y qpdf

# Python packages (recommended)
uv venv
source .venv/bin/activate
uv pip install -r <skills_dir>/requirements.txt

# NPM packages
npm install -g docx pptxgenjs playwright sharp react react-dom react-icons
npx playwright install chromium
```

## Codex MCP (Playwright)

This repo is set up to use an MCP Playwright server for browser-backed rendering. Example Codex config (`$CODEX_HOME/config.toml` or `~/.codex/config.toml`):

```toml
[mcp_servers.playwright]
command = "npx"
args = ["-y", "@playwright/mcp@latest", "--browser", "chromium", "--headless", "--no-sandbox", "--user-data-dir", "/root/.cache/ms-playwright/mcp-chromium-profile"]
startup_timeout_sec = 60
```

> [!IMPORTANT]
> Adjust `--user-data-dir` to a writable location for your environment.

## Output Organization

> [!TIP]
> Add `outputs/` to your `.gitignore` to keep generated files out of version control.

Organize all generated files in a dedicated `outputs/` directory:

```
outputs/
└── <document-name>/           # One folder per document project
    ├── final.pptx             # Final output file
    ├── inventory.json         # Intermediate files
    ├── replacements.json
    ├── unpacked/              # OOXML extraction directory
    ├── thumbnails/            # Visual validation images
    └── images/                # Generated assets
```

### Naming Convention

Use descriptive, lowercase, hyphenated names:

- `outputs/quarterly-report/`
- `outputs/client-proposal/`
- `outputs/budget-2024/`

### Example Workflow

```bash
# Create output directory
mkdir -p outputs/sales-deck/

# Generate presentation
python pptx/scripts/inventory.py template.pptx outputs/sales-deck/inventory.json
python pptx/scripts/replace.py template.pptx outputs/sales-deck/replacements.json outputs/sales-deck/final.pptx

# Validate visually
python pptx/scripts/thumbnail.py outputs/sales-deck/final.pptx outputs/sales-deck/thumbnails/
```

## Source

Based on [Anthropic's official skills](https://github.com/anthropics/skills).
