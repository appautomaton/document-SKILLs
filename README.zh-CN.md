# 文档处理技能集

[English](README.md) | 中文

基于 Anthropic 官方技能改进的一组 SKILLs，用于在 Claude Code 和 Codex 中处理 Word、PDF、PowerPoint 和 Excel。

## 使用方法

### Claude Code：Git Subtree（推荐）

```bash
# 使用默认分支（目前是 master）
git subtree add --prefix=.claude/skills \
  https://github.com/appautomaton/document-SKILLs.git master --squash
```

### Codex / 其他 Agent：克隆并复制

```bash
git clone https://github.com/appautomaton/document-SKILLs.git /tmp/doc-skills
SKILLS_DIR="${CODEX_HOME:-$HOME/.codex}/skills"  # 如需可改为你的 agent skills 目录
mkdir -p "$SKILLS_DIR"
cp -r /tmp/doc-skills/{docx,pdf,pptx,xlsx} "$SKILLS_DIR/"
cp /tmp/doc-skills/requirements.txt "$SKILLS_DIR/requirements.txt"
rm -rf /tmp/doc-skills
```

如果你的 skills 目录里已有 `requirements.txt`，请合并而不是覆盖。
`requirements.txt` 列出了这些技能所需的 Python 依赖。
建议使用 `uv`，并把“使用 uv”的要求写进你自己的 agent rules（按你的环境/安装方式自行决定）。

## 依赖（安装一次）

> [!NOTE]
> 尽量使用隔离环境；推荐用 `uv` 安装。

```bash
# 系统包
sudo apt-get install -y pandoc libreoffice poppler-utils tesseract-ocr

# 可选（PDF CLI 工作流）
sudo apt-get install -y qpdf

# Python 包（Claude Code）
uv pip install -r .claude/skills/requirements.txt
# 或用于 Codex/其他 agents
SKILLS_DIR="${CODEX_HOME:-$HOME/.codex}/skills"
uv pip install -r "$SKILLS_DIR/requirements.txt"

# NPM 包
npm install -g docx pptxgenjs playwright sharp react react-dom react-icons
npx playwright install chromium
```

## Codex MCP（Playwright）

本仓库已配置使用 MCP Playwright 服务进行浏览器渲染。示例 Codex 配置（`$CODEX_HOME/config.toml` 或 `~/.codex/config.toml`）：

```toml
[mcp_servers.playwright]
command = "npx"
args = ["-y", "@playwright/mcp@latest", "--browser", "chromium", "--headless", "--no-sandbox", "--user-data-dir", "/root/.cache/ms-playwright/mcp-chromium-profile"]
startup_timeout_sec = 60
```

> [!IMPORTANT]
> 请将 `--user-data-dir` 调整到你环境中可写的位置。

## 输出组织

> [!TIP]
> 建议把 `outputs/` 加入 `.gitignore`，避免将生成文件纳入版本控制。

将所有生成文件放在专用 `outputs/` 目录中：

```
outputs/
└── <document-name>/           # 每个项目一个文件夹
    ├── final.pptx             # 最终输出文件
    ├── inventory.json         # 中间文件
    ├── replacements.json
    ├── unpacked/              # OOXML 解包目录
    ├── thumbnails/            # 可视化验证图片
    └── images/                # 生成的素材
```

### 命名规范

使用清晰、全小写、短横线分隔的名称：

- `outputs/quarterly-report/`
- `outputs/client-proposal/`
- `outputs/budget-2024/`

### 示例流程

```bash
# 创建输出目录
mkdir -p outputs/sales-deck/

# 生成演示文稿
python pptx/scripts/inventory.py template.pptx outputs/sales-deck/inventory.json
python pptx/scripts/replace.py template.pptx outputs/sales-deck/replacements.json outputs/sales-deck/final.pptx

# 视觉校验
python pptx/scripts/thumbnail.py outputs/sales-deck/final.pptx outputs/sales-deck/thumbnails/
```

## 来源

基于 [Anthropic 官方 skills](https://github.com/anthropics/skills)。
