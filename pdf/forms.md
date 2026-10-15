# Filling PDF forms

`<skill>` is this skill's directory; run every command from the user's working directory. Start by finding out which kind of form you have:

```bash
uv run <skill>/scripts/check_fillable_fields.py form.pdf
```

A form with fillable fields is filled through those fields. A flat form, such as a scan or a printed form saved as PDF, is filled by placing text at boxes you locate on images of its pages. Either way, finish by rendering the result and looking at it, because every step before that can succeed while a value lands in the wrong place.

## Fillable forms

**1. List the fields.**

```bash
uv run <skill>/scripts/extract_form_field_info.py form.pdf field_info.json
```

Each entry has `field_id`, `type`, `page` (1-based) and `rect` (PDF points). Each type adds the values it accepts:

| type | Accepted values |
|---|---|
| `text` | any string |
| `checkbox` | `checked_value` (often `"/Yes"` or `"/On"`) or `unchecked_value` (`"/Off"`) |
| `radio_group` | one `value` from `radio_options`, e.g. `"/blue"` |
| `choice` | a `value` or `text` from `choice_options` |

**2. Match fields to their labels.** Field ids are often meaningless, like `Text12` or `topmostSubform[0].Page1[0].f1_03[0]`, so look at where each field sits on the page:

```bash
uv run <skill>/scripts/convert_pdf_to_images.py form.pdf pages --fields field_info.json
```

Each `pages/page_<n>_fields.png` shows every field outlined in red and labelled with its id. Radio options are labelled `id=value`.

**3. Write `field_values.json`**, giving only the fields to fill:

```json
[
  {"field_id": "last_name", "page": 1, "value": "Simpson"},
  {"field_id": "over_18", "page": 1, "value": "/Yes"},
  {"field_id": "state", "page": 1, "value": "NY"}
]
```

**4. Fill.**

```bash
uv run <skill>/scripts/fill_fillable_fields.py form.pdf field_values.json filled.pdf
```

Every id, page and value is checked first. If anything is wrong, it lists every problem, writes nothing and exits with status 1.

**5. Look at the result.**

```bash
uv run <skill>/scripts/convert_pdf_to_images.py filled.pdf check
```

Check every page: each value sits in the intended field, the right boxes are ticked, and no text is cut off. Two known limits:

- **List boxes.** Multi-line list boxes are drawn without highlighting the chosen item, although the value is stored. Confirm it with `PdfReader("filled.pdf").get_fields()[field_id]["/V"]`.
- **Text in other scripts.** If any text is outside Western European characters, the script asks viewers to draw it with their own fonts, and the preview may not show it. Tell the user to check it in their viewer.

## Forms without fields

Here you place each value yourself, as text annotations at boxes you locate on page images.

**1. Render the pages.**

```bash
uv run <skill>/scripts/convert_pdf_to_images.py form.pdf pages
```

Note each page's printed size. `fields.json` needs it.

**2. Locate every field** on the images. For each field, give two boxes in image pixels, `[left, top, right, bottom]`: one around the printed label and one around the empty space where the value goes. The two must not overlap, and the entry box must be tall enough for the text. Common layouts:

- **Label inside a box** (`│ Name:          │`): the entry runs from the label to the box's right edge.
- **Label before a line** (`Email: ________`): the entry sits on the line, across its full width.
- **Label under a line** (signatures and dates): the entry sits above the line.
- **Label above a line**: the entry fills the space between the label and the line.
- **Checkboxes** (`Yes □  No □`): the entry box covers only the square, not its label. The text is `"X"`.

**3. Write `fields.json`:**

```json
{
  "pages": [{"page_number": 1, "image_width": 773, "image_height": 1000}],
  "form_fields": [
    {
      "page_number": 1,
      "description": "Applicant's last name",
      "field_label": "Last name",
      "label_bounding_box": [30, 125, 95, 142],
      "entry_bounding_box": [100, 125, 280, 142],
      "entry_text": {"text": "Johnson", "font_size": 12, "font_color": "000000"}
    },
    {
      "page_number": 1,
      "description": "Over 18: Yes",
      "field_label": "Yes",
      "label_bounding_box": [100, 525, 132, 540],
      "entry_bounding_box": [140, 525, 155, 540],
      "entry_text": {"text": "X"}
    }
  ]
}
```

In `entry_text`, `font_size` defaults to 12 and `font_color` to black. For text outside Western European characters, add `"font_file"` with the path of a TrueType font that covers it. Without one, a few common system fonts are tried.

**4. Check the boxes**, automatically and then by eye:

```bash
uv run <skill>/scripts/check_bounding_boxes.py fields.json form.pdf
uv run <skill>/scripts/create_validation_image.py 1 fields.json pages/page_1.png pages/check_1.png
```

The first reports overlapping boxes and entry boxes too short for their font. The second draws entry boxes in red and label boxes in blue. Look at each validation image:

- Red boxes cover only empty space, never printed text.
- Blue boxes cover the labels.
- On checkboxes, the red box is centred on the square.

Fix `fields.json` and repeat until both checks are clean.

**5. Fill.**

```bash
uv run <skill>/scripts/fill_pdf_form_with_annotations.py form.pdf fields.json filled.pdf
```

Text that is too wide for its box is shrunk to fit, with a warning; a warning usually means the box is too small. The script refuses image sizes that don't match the page, which happens when an image came from another tool or from a different page.

**6. Look at the result**, exactly as in step 5 of the fillable path. Every value must sit inside its space, upright and readable. If one is off, correct its box in `fields.json` and fill again from the original `form.pdf`.

## Flattening

```bash
uv run <skill>/scripts/flatten_form.py filled.pdf final.pdf
```

This draws the filled values into the page content, so they can't be edited and look the same in every viewer. It handles both kinds of form. Flatten when the user is sending a finished form or wants it locked, and before merging forms whose field names might clash. Look at the filled file first; a flattened mistake can only be fixed by filling the original again.

## Converting coordinates by hand

Field rects are in PDF points, origin bottom-left. Page images are in pixels, origin top-left, showing the page as displayed: cropped, and rotated by `/Rotate`. To convert between the two, for example to point at a field's location on an image:

```bash
uv run <skill>/scripts/pdf_coords.py form.pdf 1 773x1000 --to-image 120,690,320,710
uv run <skill>/scripts/pdf_coords.py form.pdf 1 773x1000 --to-pdf 100,125,280,142
```
