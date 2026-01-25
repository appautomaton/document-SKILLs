# Document Processing Skills

Official Anthropic skills for Word, PDF, PowerPoint, and Excel manipulation in Claude Code.

## How to Use

### Option 1: Git Subtree (Recommended)

```bash
git subtree add --prefix=.claude/skills \
  git@github.com:anthropics/document-SKILLs.git main --squash
```

### Option 2: Clone and Copy

```bash
git clone git@github.com:anthropics/document-SKILLs.git /tmp/doc-skills
cp -r /tmp/doc-skills/{docx,pdf,pptx,xlsx} .claude/skills/
rm -rf /tmp/doc-skills
```

## Installation

```bash
# System packages
sudo apt-get install -y pandoc libreoffice poppler-utils tesseract-ocr

# Python packages (run from your project root, not .claude/skills/)
uv pip install -r .claude/skills/requirements.txt

# NPM packages
npm install -g docx pptxgenjs playwright sharp react react-dom react-icons
npx playwright install chromium
```

## Codex MCP (Playwright)

This repo is set up to use an MCP Playwright server for browser-backed rendering. Current Codex config (`/root/.codex/config.toml`):

```toml
[mcp_servers.playwright]
command = "npx"
args = ["-y", "@playwright/mcp@latest", "--browser", "chromium", "--headless", "--no-sandbox", "--user-data-dir", "/root/.cache/ms-playwright/mcp-chromium-profile"]
startup_timeout_sec = 60
```

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
