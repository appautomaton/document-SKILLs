# 文档处理技能集

[English](README.md) | 中文

基于 Anthropic 官方技能改进的一组 Claude Code / Codex 技能，用于处理 Word、PDF、PowerPoint 和 Excel。

## 快速开始

> [!TIP]
> 将本仓库克隆到你管理技能的目录，然后为每个技能创建符号链接。

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

## 技能

| 技能 | 功能 |
|---|---|
| [docx](docx/) | 创建、编辑和分析 Word 文档 — 修订、批注、格式保留 |
| [pdf](pdf/) | 提取文本/表格、填写表单、合并/拆分、OCR 扫描页 |
| [pptx](pptx/) | 编辑现有演示文稿 — 重排幻灯片、替换文本、缩略图 |
| [xlsx](xlsx/) | 创建/编辑电子表格 — 公式、格式、数据分析 |

## 依赖

> [!NOTE]
> Python 脚本使用 [uv](https://docs.astral.sh/uv/) + PEP 723 内联元数据 — 无需虚拟环境或 `pip install`。直接 `uv run` 即可。

系统工具：

```bash
# macOS
brew install pandoc poppler tesseract qpdf
brew install --cask libreoffice

# Linux
sudo apt-get install -y pandoc poppler-utils tesseract-ocr qpdf libreoffice
```

Node.js 包（仅 docx 和 pptx 技能需要）：

```bash
cd docx && npm install
cd ../pptx && npm install
```

## 输出组织

> [!TIP]
> 建议把 `outputs/` 加入 `.gitignore`，避免将生成文件纳入版本控制。

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

## 来源

基于 [Anthropic 官方 skills](https://github.com/anthropics/skills)。

---

🤖 到 [linux.do](https://linux.do) 发现更多 AI 好玩的东西！
