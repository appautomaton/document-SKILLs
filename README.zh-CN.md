# 文档处理技能集

[English](README.md) | 中文

一组用于处理 Word、PDF、PowerPoint 和 Excel 的 Claude Code / Codex 技能。

## 快速开始

### Claude Code 插件

在 Claude Code 中执行两条命令，无需克隆：

```
/plugin marketplace add appautomaton/document-SKILLs
/plugin install document-skills@appautomaton-skills
```

之后以 `document-skills:pdf`、`document-skills:docx` 等名称调用技能。仍需安装[依赖](#依赖)中的系统工具；docx 和 pptx 技能会在首次需要时自行安装 Node 包。

### 任意智能体，通过符号链接

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
| [docx](docx/) | 创建、修订、批注和读取 Word 文档 — 真正的修订记录，并校验没有未记录的改动 |
| [pdf](pdf/) | 提取文本/表格、填写可填写与不可填写表单、合并/拆分/加盖、OCR 扫描页 |
| [pptx](pptx/) | 从 HTML 生成原生幻灯片、套用模板、复制和重排幻灯片、编辑演讲者备注 |
| [xlsx](xlsx/) | 创建/编辑带实时公式的工作簿，重新计算并按单元格报告每个错误、循环引用和失效函数 |

每个工作流在交付前都会检查自己的产出：工作簿会重新计算并扫描错误，Word 和 PowerPoint 文件会按 OOXML 架构校验，文档、PDF 和演示文稿会渲染成图片供智能体查看。

## 依赖

> [!NOTE]
> Python 脚本使用 [uv](https://docs.astral.sh/uv/) + PEP 723 内联元数据 — 无需虚拟环境或 `pip install`。直接 `uv run` 即可。

系统工具：

```bash
# macOS：使用仓库中的 Brewfile 一条命令完成。
# 仅在缺失时安装 uv 和 node，可选工具在文件中以注释列出。
brew bundle

# Linux
sudo apt-get install -y pandoc poppler-utils libreoffice
sudo apt-get install -y tesseract-ocr   # 可选，用于扫描版 PDF 的 OCR
```

Node.js 包（仅 docx 和 pptx 技能需要）：

```bash
cd docx && npm install
cd ../pptx && npm install
```

## 开发

`tests/` 通过 `uv run` 运行每个脚本，与智能体的调用方式一致。详见 [AGENTS.md](AGENTS.md#tests)。

## 许可证

MIT 许可证 — 详见 [LICENSE](LICENSE)。

---

🤖 到 [linux.do](https://linux.do) 发现更多 AI 好玩的东西！
