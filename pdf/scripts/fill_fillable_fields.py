# /// script
# requires-python = ">=3.12"
# dependencies = ["pypdf>=6"]
# ///
"""Fill a PDF's fillable form fields from a JSON list of values.

Usage:
    uv run fill_fillable_fields.py <input.pdf> <field_values.json> <output.pdf>

field_values.json is a list of {"field_id", "page", "value"} objects using the
ids, pages and accepted values from extract_form_field_info.py. Everything is
checked before anything is written; on errors they are all printed and the
exit status is 1. A choice field accepts either an option's value or its
display text.

Fields get appearance streams written into the file, so every viewer shows the
same result. The one exception is text in characters the form's font cannot
encode (Chinese, Cyrillic, ...): then viewers are asked to redraw fields with
their own fonts, which poppler-based viewers do poorly for radio buttons.
"""

import json
import sys
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, TextStringObject

sys.path.insert(0, str(Path(__file__).parent))
from extract_form_field_info import full_field_id, get_field_info  # noqa: E402


def check(values, info):
    """Return (errors, values normalised to what the PDF stores)."""
    by_id = {f["field_id"]: f for f in info}
    errors, normalised = [], []
    for item in values:
        field_id, value = item.get("field_id"), item.get("value")
        field = by_id.get(field_id)
        if field is None:
            errors.append(f"`{field_id}` is not a field id; see field_info.json")
            continue
        if item.get("page") != field["page"]:
            errors.append(f"`{field_id}` is on page {field['page']}, not {item.get('page')}")
            continue
        if value is None:
            continue
        match field["type"]:
            case "checkbox":
                allowed = [field["checked_value"], field["unchecked_value"]]
                if value not in allowed:
                    errors.append(f"`{field_id}` is a checkbox: use {allowed[0]!r} to check it "
                                  f"or {allowed[1]!r} to clear it, not {value!r}")
            case "radio_group":
                allowed = [o["value"] for o in field["radio_options"]]
                if value not in allowed:
                    errors.append(f"`{field_id}` accepts {allowed}, not {value!r}")
            case "choice":
                options = field["choice_options"]
                match = next((o for o in options if value in (o["value"], o["text"])), None)
                if match is None:
                    errors.append(f"`{field_id}` accepts {[o['value'] for o in options]}, not {value!r}")
                    continue
                value = match
        normalised.append((field, value))
    return errors, normalised


def needs_viewer_fonts(normalised):
    for field, value in normalised:
        if field["type"] == "text":
            try:
                str(value).encode("cp1252")
            except UnicodeEncodeError:
                return True
    return False


def set_stored_value(writer, page_number, field_id, value):
    """Store `value` as the field's /V without touching its appearance."""
    for annotation in writer.pages[page_number - 1].get("/Annots", []):
        annotation = annotation.get_object()
        if full_field_id(annotation) == field_id:
            target = annotation if "/T" in annotation else annotation["/Parent"].get_object()
            target[NameObject("/V")] = TextStringObject(value)


def patch_pypdf_list_box_options():
    """Work around pypdf (verified up to 6.20) failing on list boxes whose options are pairs.

    When drawing a list box, pypdf joins its /Opt entries as strings, which
    raises TypeError when the entries are [export value, display text] pairs.
    Hand it the export values instead.
    """
    from pypdf.constants import FieldDictionaryAttributes
    from pypdf.generic import DictionaryObject

    original = DictionaryObject.get_inherited

    def get_inherited(self, key, default=None):
        result = original(self, key, default)
        if key == FieldDictionaryAttributes.Opt and isinstance(result, list) and all(
            isinstance(v, list) and len(v) == 2 for v in result
        ):
            result = [v[0] for v in result]
        return result

    DictionaryObject.get_inherited = get_inherited


def fill_pdf_fields(input_pdf, values_json, output_pdf):
    values = json.loads(Path(values_json).read_text())
    reader = PdfReader(input_pdf)
    errors, normalised = check(values, get_field_info(reader))
    if errors:
        print("ERROR: fix field_values.json and run again:\n  " + "\n  ".join(errors))
        sys.exit(1)

    patch_pypdf_list_box_options()
    writer = PdfWriter(clone_from=reader)
    by_page = {}
    for field, value in normalised:
        # A choice is drawn with its display text and stored as its export value.
        shown = value["text"] if isinstance(value, dict) else value
        by_page.setdefault(field["page"], {})[field["field_id"]] = shown
    for page_number, page_values in by_page.items():
        writer.update_page_form_field_values(
            writer.pages[page_number - 1], page_values, auto_regenerate=False
        )
    for field, value in normalised:
        if isinstance(value, dict) and value["text"] != value["value"]:
            set_stored_value(writer, field["page"], field["field_id"], value["value"])

    viewer_fonts = needs_viewer_fonts(normalised)
    writer.set_need_appearances_writer(viewer_fonts)
    with open(output_pdf, "wb") as f:
        writer.write(f)
    print(f"Filled {len(normalised)} fields; saved {output_pdf}")
    if viewer_fonts:
        print("Note: some text needs fonts the form does not embed, so viewers will draw it "
              "themselves. Rendered previews may not show those characters; check the "
              "result in the user's PDF viewer.")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit("Usage: uv run fill_fillable_fields.py <input.pdf> <field_values.json> <output.pdf>")
    fill_pdf_fields(*sys.argv[1:])
