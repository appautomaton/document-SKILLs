# /// script
# requires-python = ">=3.12"
# dependencies = ["pypdf>=6"]
# ///
"""List a PDF's fillable form fields as JSON, with the values each one accepts.

Usage:
    uv run extract_form_field_info.py <input.pdf> <field_info.json>

Each entry has field_id, type (text, checkbox, radio_group, choice), page
(1-based) and rect ([left, bottom, right, top] in PDF points, origin at the
bottom-left of the page). Checkboxes add checked_value and unchecked_value,
radio groups add radio_options, and choice fields add choice_options. See
forms.md for the full format.
"""

import json
import sys

from pypdf import PdfReader


def full_field_id(annotation):
    """The dotted field name pypdf's get_fields and update_page_form_field_values use."""
    parts = []
    while annotation:
        if name := annotation.get("/T"):
            parts.append(name)
        annotation = annotation.get("/Parent")
    return ".".join(reversed(parts)) if parts else None


def choice_options(field):
    """Options of a choice field as [{value, text}].

    Each /Opt entry is either a plain string, used as both export value and
    display text, or an [export value, display text] pair.
    """
    options = []
    for opt in field.get("/Opt") or field.get("/_States_") or []:
        if isinstance(opt, str):
            options.append({"value": str(opt), "text": str(opt)})
        elif len(opt) == 2:
            options.append({"value": str(opt[0]), "text": str(opt[1])})
    return options


def field_entry(field, field_id):
    entry = {"field_id": field_id}
    kind = field.get("/FT")
    if kind == "/Tx":
        entry["type"] = "text"
    elif kind == "/Btn":
        entry["type"] = "checkbox"  # radio groups are collected separately
        states = list(field.get("/_States_", []))
        if len(states) == 2:
            on = [s for s in states if s != "/Off"]
            if "/Off" in states and on:
                entry["checked_value"], entry["unchecked_value"] = on[0], "/Off"
            else:
                print(f"Checkbox `{field_id}` has unusual states {states}; check the result visually.")
                entry["checked_value"], entry["unchecked_value"] = states
    elif kind == "/Ch":
        entry["type"] = "choice"
        entry["choice_options"] = choice_options(field)
    else:
        entry["type"] = f"unknown ({kind})"
    return entry


def get_field_info(reader: PdfReader):
    fields = reader.get_fields() or {}
    entries, radio_parents = {}, set()
    for field_id, field in fields.items():
        if field.get("/Kids"):
            # A parent node; only button parents matter, as radio groups.
            if field.get("/FT") == "/Btn":
                radio_parents.add(field_id)
            continue
        entries[field_id] = field_entry(field, field_id)

    # Locations live on the widget annotations of each page. Every option of a
    # radio group is its own widget under the group's name.
    radios = {}
    for page_number, page in enumerate(reader.pages, 1):
        for annotation in page.get("/Annots", []):
            annotation = annotation.get_object()
            field_id = full_field_id(annotation)
            rect = [float(v) for v in annotation.get("/Rect", [0, 0, 0, 0])]
            if field_id in entries:
                entries[field_id].update(page=page_number, rect=rect)
            elif field_id in radio_parents:
                try:
                    on = [v for v in annotation["/AP"]["/N"] if v != "/Off"]
                except KeyError:
                    continue
                if len(on) == 1:
                    group = radios.setdefault(field_id, {
                        "field_id": field_id, "type": "radio_group",
                        "page": page_number, "radio_options": [],
                    })
                    group["radio_options"].append({"value": on[0], "rect": rect})

    located = []
    for entry in entries.values():
        if "page" in entry:
            located.append(entry)
        else:
            print(f"No widget found for field `{entry['field_id']}`; it cannot be filled visibly, skipping.")

    def reading_order(entry):
        rect = entry["radio_options"][0]["rect"] if "radio_options" in entry else entry["rect"]
        return entry["page"], -rect[3], rect[0]

    return sorted(located + list(radios.values()), key=reading_order)


def main():
    if len(sys.argv) != 3:
        sys.exit("Usage: uv run extract_form_field_info.py <input.pdf> <field_info.json>")
    info = get_field_info(PdfReader(sys.argv[1]))
    with open(sys.argv[2], "w") as f:
        json.dump(info, f, indent=2, ensure_ascii=False)
    print(f"Wrote {len(info)} fields to {sys.argv[2]}")


if __name__ == "__main__":
    main()
