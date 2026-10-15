# Editing slide XML

Edit the XML only for what python-pptx cannot reach: theme colours and fonts, layouts and masters, transitions and animations, bullet and numbering details, chart internals, hidden slides. Use python-pptx for text and shapes, `scripts/rearrange.py` to add, duplicate, reorder or delete slides, and `scripts/notes.py` for speaker notes. Those keep the package consistent for you.

Work in a loop: unpack, change one thing, run `<skill>/ooxml/scripts/validate.py unpacked --original deck.pptx`, fix what it reports, then pack.

## Where things live

| Part | Holds |
|---|---|
| `ppt/presentation.xml` | Slide order (`<p:sldIdLst>`) and slide size |
| `ppt/slides/slideN.xml` | One slide's shapes and text |
| `ppt/slides/_rels/slideN.xml.rels` | What that slide uses: its layout, images, charts, links, notes |
| `ppt/slideLayouts/`, `ppt/slideMasters/` | Placeholders and positions that slides inherit. A change here changes every slide built on it. |
| `ppt/theme/theme1.xml` | Colour scheme (`<a:clrScheme>`) and fonts (`<a:fontScheme>`) |
| `ppt/media/` | Images |
| `[Content_Types].xml` | The type of every part |

## Keeping the package whole

Every part is reached through a relationship and declared in `[Content_Types].xml`. Adding a part means three changes: the file, a relationship from the part that uses it (referenced by its `r:id`), and a content type, either a `<Default>` for the file extension or an `<Override>` for the part's path. Removing a part means undoing all three. validate.py reports broken references and parts nothing points to.

## Rules the schema enforces

- **Child order is fixed.** A `<p:txBody>` holds `<a:bodyPr>`, `<a:lstStyle>`, then the `<a:p>` paragraphs. A paragraph holds `<a:pPr>`, then its runs, then `<a:endParaRPr>`.
- **Paragraph properties** (`<a:pPr>`) take their children in this order: spacing (`lnSpc`, `spcBef`, `spcAft`), then bullet colour, size and font, then the bullet itself (`buNone`, `buAutoNum` or `buChar`), then `tabLst` and `defRPr`.
- **Run properties** (`<a:rPr>`) carry size and style as attributes: `sz` is in hundredths of a point (`2400` is 24pt), with `b="1"`, `i="1"` and `u="sng"`. The fill comes first among its children, and the font follows as `<a:latin typeface="…"/>`, never as an attribute.
- **Units.** Positions and sizes are in EMU: 914400 per inch, 12700 per point.
- **Shape ids** (`<p:cNvPr id>`) are unique within a slide.
- **Text** is UTF-8, so type any character literally. Escape only `&`, `<` and `>`.

## A text shape

```xml
<p:sp>
  <p:nvSpPr>
    <p:cNvPr id="10" name="Callout"/>
    <p:cNvSpPr txBox="1"/>
    <p:nvPr/>
  </p:nvSpPr>
  <p:spPr>
    <a:xfrm><a:off x="914400" y="1371600"/><a:ext cx="4572000" cy="914400"/></a:xfrm>
    <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
  </p:spPr>
  <p:txBody>
    <a:bodyPr wrap="square"/>
    <a:lstStyle/>
    <a:p>
      <a:pPr marL="285750" indent="-285750">
        <a:spcBef><a:spcPts val="600"/></a:spcBef>
        <a:buFont typeface="Arial"/>
        <a:buChar char="•"/>
      </a:pPr>
      <a:r>
        <a:rPr lang="en-US" sz="1800" b="1">
          <a:solidFill><a:srgbClr val="C0392B"/></a:solidFill>
          <a:latin typeface="Georgia"/>
        </a:rPr>
        <a:t>Churn fell to 4%</a:t>
      </a:r>
    </a:p>
  </p:txBody>
</p:sp>
```

## Pitfalls

- **Hidden slides** carry `show="0"` on `<p:sld>`. They still count in the slide order.
- **Notes belong to one slide.** Two slides pointing at the same notes slide corrupt the file.
- **Theme colours** (`<a:schemeClr val="accent1"/>`) follow the theme, while `<a:srgbClr>` is fixed. Keep a template's scheme colours when editing it, so the deck still restyles with its theme.
