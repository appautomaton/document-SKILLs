---
name: docx
description: Create, edit, review, and read Word documents (.docx), including tracked changes (redlines), comments, footnotes, tables, images, headers and page setup. Use when a task produces or modifies a .docx, reviews or redlines one, or needs its text, comments or tracked changes read.
---

# Word documents

You already know Word's features. This skill adds what you can't see from the code: a library that makes tracked changes and comments correctly, validation that catches untracked edits, a way to see pages as a reader will, and the docx-js and OOXML behaviours that silently produce broken files.

## Running scripts

`<skill>` is the directory containing this file. Run bundled scripts by absolute path from the user's working directory, so relative paths to their files keep working:

```bash
uv run <skill>/ooxml/scripts/unpack.py contract.docx unpacked
```

Run Python you write with its dependencies declared, either `uv run --with defusedxml script.py` or a PEP 723 header. Run JavaScript with `NODE_PATH=<skill>/node_modules node build.js`; if `<skill>/node_modules` is missing, run `npm install` in `<skill>` once. Rendering pages needs LibreOffice (`soffice`) and poppler (`pdftoppm`); reading needs pandoc.

## Choosing a workflow

| Task | Use |
|---|---|
| Read the text | `pandoc --track-changes=all file.docx -t markdown`. It also shows tracked changes and comments. Use `accept` or `reject` instead of `all` to see either outcome. |
| Create a document | docx-js: read [docx-js.md](docx-js.md) first. It covers the page size, style and image behaviours that otherwise break the file. |
| Edit someone else's document, or anything legal, academic, business or official | Tracked changes, so every edit is reviewable: the redlining workflow below. |
| Small edits to a document you created in this session | The same library, untracked. Make the edits, then call `doc.save(require_tracking=False)`, which still checks the schema. For larger changes, regenerate the file with docx-js. |
| Comments, metadata, embedded media, raw structure | Unpack and read the XML; [ooxml.md](ooxml.md) has the patterns. |

## Redlining workflow

1. **Read.** Convert the document with pandoc (above) and list every change you will make. Locate each one by its surrounding text, never by markdown line numbers, which have no relation to the XML.
2. **Unpack.** `uv run <skill>/ooxml/scripts/unpack.py contract.docx unpacked` prints a suggested RSID. Pass it as `Document(..., rsid=...)` so the session's edits share one revision ID.
3. **Edit.** Read [ooxml.md](ooxml.md), then write a script that uses the `Document` library. `tracked_replace(old, new)` handles most edits: it finds text across runs and marks only the words that differ. Work in batches of related changes, a few to a dozen per script, so a failure is easy to locate. Grep `unpacked/word/document.xml` again before each batch, because line numbers move after every save.
4. **Save.** `doc.save()` refuses to write a document with untracked edits, or with XML that breaks the schema, and prints what differs. Fix the script rather than skipping validation.
5. **Pack.** `uv run <skill>/ooxml/scripts/pack.py unpacked reviewed.docx` repacks the file and checks that LibreOffice can open it.
6. **Verify.** Run `pandoc --track-changes=all reviewed.docx -t markdown` and confirm every intended change appears and nothing else changed. Then render the pages (below) to check the layout.

To accept or reject existing changes, call `doc.accept_all_changes()` or `doc.reject_all_changes()` before making edits of your own.

## Seeing the result

```bash
uv run <skill>/ooxml/scripts/render.py reviewed.docx pages            # every page
uv run <skill>/ooxml/scripts/render.py reviewed.docx pages --pages 2-4
```

This prints one PNG path per page. Look at them before delivering a document you created or restructured. LibreOffice renders a docx-js table of contents empty; Word fills it in when it opens the file.

## Validation

`uv run <skill>/ooxml/scripts/validate.py reviewed.docx --original contract.docx` checks the schema, and that every change from the original is tracked. Pass `--author NAME` to let that author's earlier insertions be edited directly. Without `--original`, it checks a generated document against the schema alone. `doc.save()` runs the same checks automatically.

## Pitfalls that fail silently

- **Page size.** docx-js defaults to A4. Set Letter explicitly for US documents, and size tables to the page you chose: 9360 DXA of usable width on Letter, 9026 on A4, with 1-inch margins.
- **Bookmarks.** The `bookmark:` option on a docx-js `Paragraph` is ignored, so internal links point nowhere. Use `new Bookmark({ id, children })`.
- **Overriding heading styles.** A `paragraphStyles` entry with id `Heading1` duplicates the built-in style. Restyle headings through `styles.default.heading1`.
- **Partial edits inside other authors' changes.** To remove text inside someone else's insertion, nest your `<w:del>` inside it. Never edit their text directly.
- **pandoc as an editor.** It rewrites the whole document and drops formatting, comments and tracked changes. Use it to read, never to produce the deliverable.
