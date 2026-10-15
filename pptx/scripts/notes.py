# /// script
# requires-python = ">=3.12"
# dependencies = ["python-pptx>=1.0"]
# ///
"""Read or write speaker notes.

Usage:
    uv run notes.py deck.pptx                          # print notes as JSON
    uv run notes.py deck.pptx notes.json [-o out.pptx] # write notes from JSON

The JSON maps 0-based slide keys, as in inventory.py, to plain text:
{"slide-0": "Open with the headline number.\\nPause for questions."}
Each line becomes a paragraph; an empty string clears a slide's notes.
Slides not listed keep theirs. Writes in place unless -o is given.
"""

import argparse
import json
import sys
from pathlib import Path

from pptx import Presentation


def read_notes(prs):
    return {
        f"slide-{i}": slide.notes_slide.notes_text_frame.text
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame is not None
        else ""
        for i, slide in enumerate(prs.slides)
    }


def write_notes(prs, notes):
    slides = {f"slide-{i}": slide for i, slide in enumerate(prs.slides)}
    unknown = [key for key in notes if key not in slides]
    if unknown:
        sys.exit(f"Error: no such slide: {', '.join(unknown)}. "
                 f"The deck has slide-0 to slide-{len(slides) - 1}.")
    for key, text in notes.items():
        slide = slides[key]
        if not text and not slide.has_notes_slide:
            continue
        frame = slide.notes_slide.notes_text_frame
        if frame is None:
            sys.exit(f"Error: {key}'s notes page has no body placeholder to write into.")
        frame.text = text


def main():
    parser = argparse.ArgumentParser(description="Read or write speaker notes")
    parser.add_argument("deck", type=Path)
    parser.add_argument("notes", type=Path, nargs="?", help="JSON of notes to write")
    parser.add_argument("-o", "--output", type=Path, help="write to this file instead")
    args = parser.parse_args()

    prs = Presentation(args.deck)
    if args.notes is None:
        print(json.dumps(read_notes(prs), indent=2, ensure_ascii=False))
        return
    write_notes(prs, json.loads(args.notes.read_text(encoding="utf-8")))
    prs.save(args.output or args.deck)
    print(f"Saved notes to {args.output or args.deck}")


if __name__ == "__main__":
    main()
