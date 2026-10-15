# Editing Word documents: the Document library and OOXML

This file covers editing an unpacked `.docx`: the Python `Document` library for tracked changes and comments, and the XML patterns underneath it.

## Running a script with the library

Your script puts the skill directory first on `sys.path`, so the import cannot collide with a `scripts` package in the user's project. It declares its dependencies in a PEP 723 header and runs with `uv run`:

```python
# /// script
# requires-python = ">=3.12"
# dependencies = ["defusedxml>=0.7", "lxml>=5"]
# ///
import sys
sys.path.insert(0, "<skill>")  # absolute path of the docx skill directory
from scripts.document import Document, DocxXMLEditor

doc = Document("unpacked", author="Claude", initials="C")
```

```bash
uv run edit.py
```

`Document` options:

- `author` and `initials`: name the reviewer on every change and comment. They default to "Claude"/"C"; use the name the user wants reviewers to see.
- `rsid`: set it to the value `unpack.py` printed, so all edits in the session share one revision ID. If omitted, one is generated.
- `track_revisions=True`: turns on Track Changes in the file, so the user's own later edits are tracked too.

The library edits a temporary copy of the unpacked directory. `doc.save()` validates the result and copies it back (or to `doc.save("other-dir")`).

## Tracked changes

### Replacing text: `tracked_replace`

Use this for almost every edit. It finds the text in a paragraph even when Word has split it across several runs. Formatting changes, proofing marks, and the script boundaries in Chinese or Japanese text all split runs. It then marks only the words that differ:

```python
body = doc["word/document.xml"]
body.tracked_replace("within 30 days", "within 45 days")      # marks 30 -> 45 only
body.tracked_replace("期限为30天", "期限为45天")                 # CJK is compared per character
body.tracked_replace("Acme Corp", "Acme Inc.", replace_all=True)
body.tracked_replace("the Seller", "the Vendor", scope=body.get_node(tag="w:p", contains="Section 4.2"))
body.tracked_replace(", without limitation,", "")              # deletion
```

- `old` must lie within one paragraph and match its visible text exactly. Deleted text is not searched; tabs match `"\t"` and line breaks `"\n"`.
- If `old` occurs more than once, it raises and shows where. Narrow the search with `scope=` (any element: a paragraph, a table, a cell), or pass `replace_all=True`.
- Unchanged text keeps its original runs, formatting and RSIDs. Inserted text takes the formatting of the text it replaces.
- It returns the new `w:del`/`w:ins` elements, ready for `doc.add_comment(start=..., end=...)`.
- Text inside another author's insertion can be deleted, which nests your deletion inside their insertion. It can be replaced only when the change reaches the start or end of that insertion. For a change in its middle, reject the whole insertion with `revert_insertion()` and insert the corrected text.

### Deleting whole runs or paragraphs

```python
body.suggest_deletion(body.get_node(tag="w:r", contains="text to delete"))
body.suggest_deletion(body.get_node(tag="w:p", contains="paragraph to delete"))
```

Deleting a paragraph also marks its paragraph mark deleted. Accepting the change then removes the paragraph instead of leaving an empty line. The last paragraph of the body, a cell or a text box keeps its mark, as in Word.

### Inserting paragraphs

```python
target = body.get_node(tag="w:p", contains="existing list item")
pPr = tags[0].toxml() if (tags := target.getElementsByTagName("w:pPr")) else ""
body.insert_after(target, DocxXMLEditor.suggest_paragraph(f"<w:p>{pPr}<w:r><w:t>New item</w:t></w:r></w:p>"))
```

`suggest_paragraph` wraps the runs in `<w:ins>` and marks the paragraph mark inserted. Reusing the neighbour's `w:pPr` keeps the list numbering and style.

### Other authors' changes

```python
ins = body.get_node(tag="w:ins", attrs={"w:id": "5"})
body.revert_insertion(ins)        # reject their insertion: nests a <w:del> inside it
dele = body.get_node(tag="w:del", attrs={"w:id": "3"})
body.revert_deletion(dele)        # reject their deletion: re-inserts the text after it
```

Both also accept a paragraph or other container, which handles every insertion or deletion inside it.

### Accepting or rejecting everything

```python
doc.accept_all_changes()   # or doc.reject_all_changes()
```

These cover the body, headers, footers, footnotes, endnotes and comments, like Word's Accept All and Reject All. That includes paragraph marks, moves, table rows and formatting changes. Call them before your own edits. Edits made earlier must already be tracked, and later ones are checked against the resolved document.

### Writing the XML yourself

When no method fits, replace a node with explicit `<w:del>`/`<w:ins>` markup. The library fills in `w:id`, `w:author`, `w:date` and RSIDs on new elements:

```python
node = body.get_node(tag="w:r", contains="The report is monthly")
rpr = tags[0].toxml() if (tags := node.getElementsByTagName("w:rPr")) else ""
body.replace_node(node,
    f'<w:r>{rpr}<w:t xml:space="preserve">The report is </w:t></w:r>'
    f'<w:del><w:r>{rpr}<w:delText>monthly</w:delText></w:r></w:del>'
    f'<w:ins><w:r>{rpr}<w:t>quarterly</w:t></w:r></w:ins>')
```

The rules every tracked change must follow:

- `<w:ins>` and `<w:del>` wrap whole `<w:r>` elements at paragraph level, never the inside of a run.
- Deleted text goes in `<w:delText>`, not `<w:t>`.
- Mark only what changes. Keep unchanged text in its original run, with its attributes.
- Never edit inside another author's `<w:ins>` or `<w:del>` directly. To remove part of their insertion, nest your `<w:del>` inside it. To restore their deletion, add your `<w:ins>` after it.

```xml
<!-- Rejecting part of Jane's insertion, then adding a replacement after it -->
<w:ins w:id="16" w:author="Jane Smith" w:date="2026-01-15T10:00:00Z">
  <w:r><w:t xml:space="preserve">in silence, </w:t></w:r>
  <w:del w:author="Claude"><w:r><w:delText>safe and sound</w:delText></w:r></w:del>
</w:ins>
<w:ins w:author="Claude"><w:r><w:t>soft and unbound</w:t></w:r></w:ins>

<!-- Restoring Jane's deletion -->
<w:del w:id="50" w:author="Jane Smith" w:date="2026-01-15T10:00:00Z">
  <w:r><w:delText>within 30 days</w:delText></w:r>
</w:del>
<w:ins w:author="Claude"><w:r><w:t>within 30 days</w:t></w:r></w:ins>
```

### What `save()` checks

`doc.save()` raises if the result is invalid. It checks two things:

- **Schema:** the XML must match the OOXML schema, ignoring problems the original file already had.
- **Tracking:** rejecting every tracked change must give back the original text, so an edit made without tracking shows up as a difference, whoever the author. Other authors' insertions must also keep their text.

The error prints the differing text. The usual causes are editing text directly instead of through `<w:ins>`/`<w:del>`, and editing inside someone else's change. For a document of your own that needs no review, `save(require_tracking=False)` keeps the schema check and drops the tracking one. `save(validate=False)` skips both; use it only to inspect a broken state, never for a deliverable.

## Comments

```python
para = body.get_node(tag="w:p", contains="paragraph text")
cid = doc.add_comment(start=para, end=para, text="Please confirm this date.")
doc.reply_to_comment(parent_comment_id=cid, text="Confirmed with finance.")

changes = body.tracked_replace("30 days", "45 days")
doc.add_comment(start=changes[0], end=changes[-1], text="Extended per the March amendment.")
```

`start` and `end` can be paragraphs, runs or tracked-change elements. The library creates or updates `comments.xml` and its companion parts, and their relationships and content types. That works on documents from Word, LibreOffice, docx-js and pandoc alike.

## Finding nodes

```python
body.get_node(tag="w:p", contains="specific text")             # text within the element
body.get_node(tag="w:del", attrs={"w:id": "1"})                 # attribute values
body.get_node(tag="w:p", line_number=42)                        # line where the tag opens
body.get_node(tag="w:r", contains="Section", line_number=range(2400, 2500))
```

`get_node` must match exactly one element. `contains` sees the text of a single element, so text split across runs is found with `tag="w:p"`, or replaced directly with `tracked_replace`. Line numbers refer to the file as it was unpacked, so grep `word/document.xml` again after every saved edit.

`doc["word/comments.xml"]`, `doc["word/header1.xml"]` and so on give editors for other parts. Each editor's `.dom` is a minidom document for anything the methods don't cover.

## Inserting an image

```python
# /// script
# requires-python = ">=3.12"
# dependencies = ["defusedxml>=0.7", "lxml>=5", "Pillow>=10"]
# ///
import shutil, sys
sys.path.insert(0, "<skill>")
from PIL import Image
from scripts.document import Document, DocxXMLEditor

doc = Document("unpacked")
body = doc["word/document.xml"]

# Copy the image into the working copy the library edits, under an unused name
media = doc.unpacked_path / "word" / "media"
media.mkdir(exist_ok=True)
n = 1
while (media / f"image{n}.png").exists():
    n += 1
shutil.copy("chart.png", media / f"image{n}.png")

# Full usable width (6.5 in on Letter with 1 in margins), keeping the aspect ratio
w, h = Image.open("chart.png").size
cx = int(6.5 * 914400)
cy = cx * h // w

rels = doc["word/_rels/document.xml.rels"]
rid = rels.get_next_rid()
rels.append_to(rels.dom.documentElement,
    f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image{n}.png"/>')
types = doc["[Content_Types].xml"]
if not any(d.getAttribute("Extension").lower() == "png" for d in types.dom.getElementsByTagName("Default")):
    types.append_to(types.dom.documentElement, '<Default Extension="png" ContentType="image/png"/>')

# Drawing ids must be unique across the document
pic_id = 1 + max((int(e.getAttribute("id")) for e in body.dom.getElementsByTagName("wp:docPr")), default=0)

anchor = body.get_node(tag="w:p", contains="Second paragraph")
body.insert_after(anchor, DocxXMLEditor.suggest_paragraph(f'''<w:p><w:r><w:drawing>
  <wp:inline distT="0" distB="0" distL="0" distR="0">
    <wp:extent cx="{cx}" cy="{cy}"/>
    <wp:docPr id="{pic_id}" name="Picture {pic_id}"/>
    <a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">
      <pic:pic>
        <pic:nvPicPr><pic:cNvPr id="{pic_id}" name="image{n}.png"/><pic:cNvPicPr/></pic:nvPicPr>
        <pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>
        <pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>
      </pic:pic>
    </a:graphicData></a:graphic>
  </wp:inline>
</w:drawing></w:r></w:p>'''))
doc.save()
```

`suggest_paragraph` makes the insertion a tracked change. Drop it to insert the image silently, if the user doesn't want it reviewed. On A4 with 1-inch margins, the usable width is 6.27 inches.

## XML reference

### Schema rules that bite

- **`<w:pPr>`:** children follow a fixed order, starting `pStyle`, `keepNext`, `keepLines`, `pageBreakBefore`, `numPr`, … `spacing`, `ind`, … `jc`, … and ending `rPr`, `sectPr`, `pPrChange`.
- **Whitespace:** a `<w:t>` whose text starts or ends with a space needs `xml:space="preserve"`, or the space is dropped.
- **Text encoding:** `unpack.py` writes UTF-8, so curly quotes, dashes and CJK text can be typed literally. Entities such as `&#8220;` (“) also work. In `contains=` searches, both forms find the same text.
- **Settings:** turn on Track Changes with `Document(..., track_revisions=True)`, which puts `<w:trackRevisions/>` at its schema position in `settings.xml`: after `w:proofState`, `w:attachedTemplate`, `w:documentType`, `w:mailMerge` and `w:revisionView`, whichever are present.
- **IDs and RSIDs:** RSIDs are 8 hex digits. Tracked-change `w:id` values must be unique; the library assigns them.

### Paragraphs and runs

```xml
<w:p>
  <w:pPr><w:pStyle w:val="Heading2"/><w:jc w:val="center"/></w:pPr>
  <w:r><w:rPr><w:b/><w:bCs/></w:rPr><w:t>Bold heading text</w:t></w:r>
</w:p>
<!-- run formatting: <w:i/> italic, <w:u w:val="single"/> underline,
     <w:highlight w:val="yellow"/>, <w:rFonts w:ascii="Courier New" w:hAnsi="Courier New"/> -->
<w:p><w:r><w:br w:type="page"/></w:r></w:p>   <!-- page break -->
```

### Lists

```xml
<w:p>
  <w:pPr>
    <w:pStyle w:val="ListParagraph"/>
    <w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>
  </w:pPr>
  <w:r><w:t>First item</w:t></w:r>
</w:p>
```

`w:ilvl` sets the nesting level. A different `w:numId`, defined in `numbering.xml`, starts a separate list. Copy the `w:pPr` of an existing item to continue its list.

### Tables

```xml
<w:tbl>
  <w:tblPr><w:tblStyle w:val="TableGrid"/><w:tblW w:w="0" w:type="auto"/></w:tblPr>
  <w:tblGrid><w:gridCol w:w="4680"/><w:gridCol w:w="4680"/></w:tblGrid>
  <w:tr>
    <w:tc><w:tcPr><w:tcW w:w="4680" w:type="dxa"/></w:tcPr><w:p><w:r><w:t>Cell 1</w:t></w:r></w:p></w:tc>
    <w:tc><w:tcPr><w:tcW w:w="4680" w:type="dxa"/></w:tcPr><w:p><w:r><w:t>Cell 2</w:t></w:r></w:p></w:tc>
  </w:tr>
</w:tbl>
```

### Hyperlinks and bookmarks

```xml
<w:hyperlink r:id="rId5"><w:r><w:rPr><w:rStyle w:val="Hyperlink"/></w:rPr><w:t>External link</w:t></w:r></w:hyperlink>
<w:hyperlink w:anchor="myBookmark"><w:r><w:rPr><w:rStyle w:val="Hyperlink"/></w:rPr><w:t>Internal link</w:t></w:r></w:hyperlink>
<w:bookmarkStart w:id="0" w:name="myBookmark"/><w:r><w:t>Target</w:t></w:r><w:bookmarkEnd w:id="0"/>
```

- **External links:** these need a relationship in `word/_rels/document.xml.rels`: `<Relationship Id="rId5" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="https://example.com/" TargetMode="External"/>`.
- **The Hyperlink style:** links look like plain text unless `styles.xml` defines it:

```xml
<w:style w:type="character" w:styleId="Hyperlink">
  <w:name w:val="Hyperlink"/><w:basedOn w:val="DefaultParagraphFont"/><w:uiPriority w:val="99"/><w:unhideWhenUsed/>
  <w:rPr><w:color w:val="467886" w:themeColor="hyperlink"/><w:u w:val="single"/></w:rPr>
</w:style>
```

### Parts to update when adding content

- `word/_rels/document.xml.rels`: a `Relationship` for each new part, image or external link.
- `[Content_Types].xml`: a `Default` per file extension (`png`, `jpeg`), and an `Override` per new XML part. Check before adding, since a duplicate entry corrupts the package.
