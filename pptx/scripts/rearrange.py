# /// script
# requires-python = ">=3.12"
# dependencies = ["python-pptx>=1.0"]
# ///
"""Build a presentation from a template's slides, in any order, with repeats.

Usage:
    uv run rearrange.py template.pptx output.pptx 0,34,34,50,52

Indices are 0-based. A repeated index duplicates that slide. Duplicates are
complete: charts with their embedded workbooks, diagrams, embedded objects,
hyperlinks, backgrounds, transitions and speaker notes all come along. Slides
not listed are deleted.
"""

import argparse
import re
import shutil
import sys
from copy import deepcopy
from pathlib import Path

from pptx import Presentation
from pptx.opc.package import PartFactory
from pptx.opc.packuri import PackURI

R_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
P_NS = "{http://schemas.openxmlformats.org/presentationml/2006/main}"

# Relationship kinds (last segment of the type URI) a duplicate points at
# rather than copies: shared media, other slides, and its layout. Notes and
# comments belong to one slide only; notes text is copied separately.
SHARED = {"image", "media", "video", "audio", "slide", "slideLayout"}
SKIPPED = {"notesSlide", "comments"}


def main():
    parser = argparse.ArgumentParser(
        description="Rearrange PowerPoint slides based on a sequence of indices.",
        epilog="Example: uv run rearrange.py template.pptx output.pptx 0,34,34,50,52",
    )
    parser.add_argument("template", help="Path to template PPTX file")
    parser.add_argument("output", help="Path for output PPTX file")
    parser.add_argument("sequence", help="Comma-separated slide indices (0-based)")
    args = parser.parse_args()

    try:
        sequence = [int(x) for x in args.sequence.split(",")]
    except ValueError:
        sys.exit("Error: the sequence must be comma-separated integers, e.g. 0,34,34,50,52")
    template = Path(args.template)
    if not template.exists():
        sys.exit(f"Error: template not found: {template}")
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        rearrange_presentation(template, output, sequence)
    except ValueError as e:
        sys.exit(f"Error: {e}")


class Cloner:
    """Copies a slide's related parts into new parts of the same package."""

    def __init__(self, package):
        self.package = package
        self.copies = {}
        self.reserved = set()

    def next_partname(self, partname):
        prefix, ext = re.match(r"^(.*?)\d*(\.[^./]+)$", str(partname)).groups()
        used = {str(p.partname) for p in self.package.iter_parts()} | self.reserved
        n = 1
        while f"{prefix}{n}{ext}" in used:
            n += 1
        self.reserved.add(f"{prefix}{n}{ext}")
        return PackURI(f"{prefix}{n}{ext}")

    def clone(self, part):
        if part in self.copies:
            return self.copies[part]
        copy = PartFactory(self.next_partname(part.partname), part.content_type, self.package, part.blob)
        self.copies[part] = copy
        mapping = {rId: self.relate(copy, rel) for rId, rel in part.rels.items()}
        if hasattr(copy, "_element"):
            remap(copy._element, mapping)
        return copy

    def relate(self, source_part, rel):
        """Relate `source_part` to rel's target, copying the target unless it is shared."""
        if rel.is_external:
            return source_part.relate_to(rel.target_ref, rel.reltype, is_external=True)
        kind = rel.reltype.rsplit("/", 1)[-1]
        target = rel.target_part if kind in SHARED else self.clone(rel.target_part)
        return source_part.relate_to(target, rel.reltype)


def remap(element, mapping):
    """Point every r:id-style attribute under `element` at its new relationship."""
    for node in element.iter():
        for attr, value in node.attrib.items():
            if attr.startswith(R_NS) and value in mapping:
                node.set(attr, mapping[value])


def duplicate_slide(pres, index):
    source = pres.slides[index]
    new_slide = pres.slides.add_slide(source.slide_layout)
    cloner = Cloner(pres.part.package)
    mapping = {}

    def rel_ids(element):
        for node in element.iter():
            for attr, value in node.attrib.items():
                if attr.startswith(R_NS) and value in source.part.rels and value not in mapping:
                    rel = source.part.rels[value]
                    if rel.reltype.rsplit("/", 1)[-1] not in SKIPPED:
                        mapping[value] = cloner.relate(new_slide.part, rel)

    # Replace the layout's empty placeholders with copies of the source's shapes.
    tree = new_slide.shapes._spTree
    for shape in list(new_slide.shapes):
        tree.remove(shape.element)
    framing = {f"{P_NS}nvGrpSpPr", f"{P_NS}grpSpPr", f"{P_NS}extLst"}
    for child in source.shapes._spTree:
        if child.tag in framing:
            continue
        copy = deepcopy(child)
        rel_ids(copy)
        remap(copy, mapping)
        tree.insert_element_before(copy, "p:extLst")

    # Background, transition and animation timing live outside the shape tree.
    src, dst = source.element, new_slide.element
    background = src.find(f"{P_NS}cSld/{P_NS}bg")
    if background is not None:
        copy = deepcopy(background)
        rel_ids(copy)
        remap(copy, mapping)
        dst.find(f"{P_NS}cSld").insert(0, copy)
    anchor = dst.find(f"{P_NS}clrMapOvr")
    for tag in ("transition", "timing"):
        node = src.find(f"{P_NS}{tag}")
        if node is not None and anchor is not None:
            copy = deepcopy(node)
            remap(copy, mapping)
            anchor.addnext(copy)
            anchor = copy

    if source.has_notes_slide and source.notes_slide.notes_text_frame is not None:
        text = source.notes_slide.notes_text_frame.text
        if text:
            new_slide.notes_slide.notes_text_frame.text = text
    return new_slide


def delete_slide(pres, index):
    rId = pres.slides._sldIdLst[index].rId
    pres.part.drop_rel(rId)
    del pres.slides._sldIdLst[index]


def reorder_slides(pres, slide_index, target_index):
    slides = pres.slides._sldIdLst
    slide_element = slides[slide_index]
    slides.remove(slide_element)
    slides.insert(target_index, slide_element)


def rearrange_presentation(template_path, output_path, slide_sequence):
    if template_path != output_path:
        shutil.copy2(template_path, output_path)
    prs = Presentation(output_path)

    total = len(prs.slides)
    for idx in slide_sequence:
        if idx < 0 or idx >= total:
            raise ValueError(f"Slide index {idx} out of range (0-{total - 1})")

    # Step 1: duplicate repeated slides. slide_map holds the current position
    # of the slide for each place in the final sequence.
    slide_map = []
    duplicated = {}
    print(f"Processing {len(slide_sequence)} slides from template...")
    for i, idx in enumerate(slide_sequence):
        if duplicated.get(idx):
            slide_map.append(duplicated[idx].pop(0))
            print(f"  [{i}] Using duplicate of slide {idx}")
        elif slide_sequence.count(idx) > 1 and idx not in duplicated:
            slide_map.append(idx)
            count = slide_sequence.count(idx) - 1
            print(f"  [{i}] Using original slide {idx}, creating {count} duplicate(s)")
            duplicated[idx] = []
            for _ in range(count):
                duplicate_slide(prs, idx)
                duplicated[idx].append(len(prs.slides) - 1)
        else:
            slide_map.append(idx)
            print(f"  [{i}] Using original slide {idx}")

    # Step 2: delete unused slides, last first.
    keep = set(slide_map)
    print(f"\nDeleting {len(prs.slides) - len(keep)} unused slides...")
    for i in range(len(prs.slides) - 1, -1, -1):
        if i not in keep:
            delete_slide(prs, i)
            slide_map = [idx - 1 if idx > i else idx for idx in slide_map]

    # Step 3: move each slide into its final position.
    print(f"Reordering {len(slide_map)} slides to final sequence...")
    for target in range(len(slide_map)):
        current = slide_map[target]
        if current != target:
            reorder_slides(prs, current, target)
            for i in range(len(slide_map)):
                if current < slide_map[i] <= target:
                    slide_map[i] -= 1
                elif target <= slide_map[i] < current:
                    slide_map[i] += 1
            slide_map[target] = target

    prs.save(output_path)
    print(f"\nSaved rearranged presentation to: {output_path}")
    print(f"Final presentation has {len(prs.slides)} slides")


if __name__ == "__main__":
    main()
