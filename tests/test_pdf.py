"""The pdf skill's scripts, run as an agent runs them, against generated forms."""

import importlib.util
import json
import re
from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf import Transformation
from pypdf.generic import RectangleObject
from reportlab.pdfgen import canvas

from conftest import ROOT

SCRIPTS = "pdf/scripts"
CJK_FONTS = [
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
]


def make_form(path):
    """A fillable form: text, checkbox, radio group, two combo boxes, a list box."""
    c = canvas.Canvas(str(path), pagesize=(612, 792))
    f = c.acroForm
    c.drawString(50, 700, "Name:")
    f.textfield(name="name", x=120, y=690, width=200, height=20)
    c.drawString(50, 650, "Adult:")
    f.checkbox(name="adult", x=120, y=645, size=14)
    c.drawString(50, 600, "Color:")
    f.radio(name="color", value="red", selected=False, x=120, y=595, size=14)
    f.radio(name="color", value="blue", selected=False, x=160, y=595, size=14)
    f.choice(name="state", options=["CA", "NY", "TX"], value="CA", x=120, y=545, width=100, height=20)
    f.choice(name="size", options=[("Small", "S"), ("Large", "L")], value="S", x=120, y=495, width=100, height=20)
    f.listbox(name="fruit", options=["apple", "pear"], value="apple", x=120, y=410, width=100, height=40)
    c.save()
    return path


def make_flat_form(path, rotate=0, offset=None):
    """A flat form whose entry area is a solid red box, displayed upright whatever /Rotate is.

    `offset` moves the page box away from (0, 0), content and all, so the page looks the same.
    """
    c = canvas.Canvas(str(path), pagesize=(612, 792))
    c.drawString(100, 715, "Name:")
    c.setFillColorRGB(1, 0, 0)
    c.rect(150, 700, 250, 30, stroke=0, fill=1)
    c.save()
    writer = PdfWriter(clone_from=str(path))
    page = writer.pages[0]
    if rotate:
        # Turn the content against the rotation, so the page still displays upright.
        page.rotate(-rotate)
        page.transfer_rotation_to_content()
        page.rotate(rotate)
    if offset:
        dx, dy = offset
        page.add_transformation(Transformation().translate(dx, dy))
        box = page.mediabox
        page.mediabox = page.cropbox = RectangleObject(
            [box.left + dx, box.bottom + dy, box.right + dx, box.top + dy]
        )
    writer.write(path)
    return path


def render(run, pdf, out_dir):
    result = run(f"{SCRIPTS}/convert_pdf_to_images.py", pdf, out_dir)
    assert result.code == 0, result.err
    return Image.open(Path(out_dir) / "page_1.png").convert("RGB")


def pixels(image, box, test):
    px = image.load()
    return [(x, y) for y in range(box[1], box[3]) for x in range(box[0], box[2]) if test(px[x, y])]


def is_dark(p):
    return max(p) < 100


def is_red(p):
    return p[0] > 200 and p[1] < 60 and p[2] < 60


def bbox(points):
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return [min(xs), min(ys), max(xs) + 1, max(ys) + 1]


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False))
    return path


@pytest.fixture
def form(tmp_path):
    return make_form(tmp_path / "form.pdf")


@pytest.fixture
def field_info(run, tmp_path, form):
    assert run(f"{SCRIPTS}/extract_form_field_info.py", form, tmp_path / "info.json").code == 0
    return {f["field_id"]: f for f in json.loads((tmp_path / "info.json").read_text())}


# Fillable forms


def test_choice_options_keep_whole_values(field_info):
    assert field_info["state"]["choice_options"] == [
        {"value": v, "text": v} for v in ("CA", "NY", "TX")
    ]
    assert field_info["size"]["choice_options"] == [
        {"value": "S", "text": "Small"}, {"value": "L", "text": "Large"},
    ]
    assert [o["value"] for o in field_info["color"]["radio_options"]] == ["/red", "/blue"]


def fill(run, tmp_path, form, values):
    path = write_json(tmp_path / "values.json", [{"page": 1, **v} for v in values])
    return run(f"{SCRIPTS}/fill_fillable_fields.py", form, path, tmp_path / "filled.pdf")


VALUES = [
    {"field_id": "name", "value": "Homer Simpson"},
    {"field_id": "adult", "value": "/Yes"},
    {"field_id": "color", "value": "/blue"},
    {"field_id": "state", "value": "NY"},
    {"field_id": "size", "value": "Large"},  # display text is accepted
]


def radio_marks(image):
    """Dark pixels inside the red and blue radio buttons, at the converter's scale."""
    scale = image.height / 792
    box = lambda x: [int(x * scale) + 3, int((792 - 609) * scale) + 3, int((x + 14) * scale) - 3, int((792 - 595) * scale) - 3]
    return len(pixels(image, box(120), is_dark)), len(pixels(image, box(160), is_dark))


def test_fill_fillable_stores_values_and_shows_the_radio_choice(run, tmp_path, form):
    result = fill(run, tmp_path, form, VALUES)
    assert result.code == 0, result.out
    filled = tmp_path / "filled.pdf"
    stored = {k: v.get("/V") for k, v in PdfReader(filled).get_fields().items()}
    assert stored | {"fruit": None} == {
        "name": "Homer Simpson", "adult": "/Yes", "color": "/blue", "state": "NY", "size": "L", "fruit": None,
    }
    red, blue = radio_marks(render(run, filled, tmp_path / "check"))
    assert blue > red + 10, "the selected radio button is not drawn in poppler"


def test_fill_fillable_reports_every_error_and_writes_nothing(run, tmp_path, form):
    result = fill(run, tmp_path, form, [
        {"field_id": "state", "value": "ZZ"},
        {"field_id": "missing", "value": "x"},
        {"field_id": "adult", "value": "yes"},
    ])
    assert result.code == 1
    assert "ZZ" in result.out and "missing" in result.out and "checkbox" in result.out
    assert not (tmp_path / "filled.pdf").exists()


def test_flatten_draws_values_and_removes_fields(run, tmp_path, form):
    assert fill(run, tmp_path, form, VALUES).code == 0
    flat = tmp_path / "flat.pdf"
    assert run(f"{SCRIPTS}/flatten_form.py", tmp_path / "filled.pdf", flat).code == 0
    reader = PdfReader(flat)
    assert not reader.get_fields() and "/Annots" not in reader.pages[0]
    assert "Homer Simpson" in reader.pages[0].extract_text()
    red, blue = radio_marks(render(run, flat, tmp_path / "flat_img"))
    assert blue > red + 10, "flattening lost the radio selection"


def test_field_overlay_images(run, tmp_path, form):
    result = run(f"{SCRIPTS}/extract_form_field_info.py", form, tmp_path / "info.json")
    result = run(f"{SCRIPTS}/convert_pdf_to_images.py", form, tmp_path / "pages", "--fields", tmp_path / "info.json")
    assert result.code == 0 and (tmp_path / "pages" / "page_1_fields.png").exists()


# Converting pages


def test_convert_creates_missing_dirs_and_renders_only_requested_pages(run, tmp_path):
    c = canvas.Canvas(str(tmp_path / "long.pdf"))
    for n in range(5):
        c.drawString(72, 720, f"page {n + 1}")
        c.showPage()
    c.save()
    out = tmp_path / "a" / "b"
    result = run(f"{SCRIPTS}/convert_pdf_to_images.py", tmp_path / "long.pdf", out, "--pages", "2-3")
    assert result.code == 0, result.err
    assert sorted(p.name for p in out.iterdir()) == ["page_2.png", "page_3.png"]
    assert re.search(r"page 2: .*page_2\.png \(\d+x1000\)", result.out)


# Forms without fields


@pytest.mark.parametrize("rotate,offset", [
    (0, None), (90, None), (180, None), (270, None),
    (0, (-50, -100)), (90, (-50, -100)), (270, (30, -60)),
])
def test_annotation_lands_upright_inside_its_box(run, tmp_path, rotate, offset):
    pdf = make_flat_form(tmp_path / "flat.pdf", rotate, offset)
    page = render(run, pdf, tmp_path / "pages")
    target = bbox(pixels(page, [0, 0, page.width, page.height], is_red))
    fields = write_json(tmp_path / "fields.json", {
        "pages": [{"page_number": 1, "image_width": page.width, "image_height": page.height}],
        "form_fields": [{
            "page_number": 1, "description": "name",
            "entry_bounding_box": [target[0] + 3, target[1] + 3, target[2] - 3, target[3] - 3],
            "entry_text": {"text": "LONG NAME HERE"},
        }],
    })
    result = run(f"{SCRIPTS}/fill_pdf_form_with_annotations.py", pdf, fields, tmp_path / "filled.pdf")
    assert result.code == 0, result.out
    annotation = PdfReader(tmp_path / "filled.pdf").pages[0]["/Annots"][0].get_object()
    assert "/AP" in annotation, "no appearance stream: rendering is left to each viewer"

    filled = render(run, tmp_path / "filled.pdf", tmp_path / "out")
    inside = pixels(filled, target, is_dark)
    assert len(inside) > 100, "the text is not inside the box"
    text = bbox(inside)
    assert text[2] - text[0] > 3 * (text[3] - text[1]), "the text is not horizontal as displayed"
    assert text[0] - target[0] < target[2] - text[2], "the text is not upright (left-aligned) as displayed"


def test_annotation_refuses_an_image_size_that_does_not_match_the_page(run, tmp_path):
    pdf = make_flat_form(tmp_path / "flat.pdf")
    fields = write_json(tmp_path / "fields.json", {
        "pages": [{"page_number": 1, "image_width": 1000, "image_height": 1000}],
        "form_fields": [{"page_number": 1, "description": "x", "entry_bounding_box": [10, 10, 200, 40],
                         "entry_text": {"text": "x"}}],
    })
    result = run(f"{SCRIPTS}/fill_pdf_form_with_annotations.py", pdf, fields, tmp_path / "out.pdf")
    assert result.code == 1 and "1000x1000" in result.out
    assert not (tmp_path / "out.pdf").exists()


@pytest.mark.skipif(not any(Path(f).exists() for f in CJK_FONTS), reason="no CJK TrueType font installed")
def test_annotation_draws_chinese_text(run, tmp_path):
    pdf = make_flat_form(tmp_path / "flat.pdf")
    page = render(run, pdf, tmp_path / "pages")
    target = bbox(pixels(page, [0, 0, page.width, page.height], is_red))
    fields = write_json(tmp_path / "fields.json", {
        "pages": [{"page_number": 1, "image_width": page.width, "image_height": page.height}],
        "form_fields": [{"page_number": 1, "description": "name",
                         "entry_bounding_box": [target[0] + 3, target[1] + 3, target[2] - 3, target[3] - 3],
                         "entry_text": {"text": "张三丰"}}],
    })
    assert run(f"{SCRIPTS}/fill_pdf_form_with_annotations.py", pdf, fields, tmp_path / "filled.pdf").code == 0
    assert len(pixels(render(run, tmp_path / "filled.pdf", tmp_path / "out"), target, is_dark)) > 100


# Coordinates


@pytest.mark.parametrize("rotate", [0, 90, 180, 270])
def test_pdf_coords_round_trip(run, tmp_path, rotate):
    pdf = make_flat_form(tmp_path / "p.pdf", rotate, (-50, -100))
    box = PdfReader(pdf).pages[0].cropbox
    rect = [float(box.left) + 100, float(box.bottom) + 200, float(box.left) + 350, float(box.bottom) + 230]
    to_image = run(f"{SCRIPTS}/pdf_coords.py", pdf, 1, "800x1000", "--to-image", ",".join(map(str, rect)))
    image_box = json.loads(to_image.out)
    assert all(0 <= v <= 1000 for v in image_box), image_box
    back = run(f"{SCRIPTS}/pdf_coords.py", pdf, 1, "800x1000", "--to-pdf", ",".join(map(str, image_box)))
    assert json.loads(back.out) == pytest.approx(rect, abs=0.05)


def test_pdf_coords_accepts_boxes_partly_off_the_page(run, tmp_path):
    pdf = make_flat_form(tmp_path / "p.pdf")
    result = run(f"{SCRIPTS}/pdf_coords.py", pdf, 1, "612x792", "--to-pdf", "-10,92,350,62")
    assert result.code == 0 and json.loads(result.out) == [-10, 700, 350, 730]


def test_pdf_coords_plain_page_is_a_scaled_flip(run, tmp_path):
    pdf = make_flat_form(tmp_path / "p.pdf")
    result = run(f"{SCRIPTS}/pdf_coords.py", pdf, 1, "612x792", "--to-pdf", "100,92,350,62")
    assert json.loads(result.out) == [100, 700, 350, 730]


# Checking boxes


def _messages(data, scales=None):
    spec = importlib.util.spec_from_file_location("cbb", ROOT / SCRIPTS / "check_bounding_boxes.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    import io
    return module.get_bounding_box_messages(io.StringIO(json.dumps(data)), scales)


def field(page=1, label=(10, 10, 50, 30), entry=(60, 10, 150, 30), **extra):
    return {"description": "f", "page_number": page, "label_bounding_box": list(label),
            "entry_bounding_box": list(entry), **extra}


@pytest.mark.parametrize("fields,outcome", [
    ([field(), field(label=(10, 40, 50, 60), entry=(60, 40, 150, 60))], "SUCCESS"),
    ([field(label=(10, 10, 60, 30), entry=(50, 10, 150, 30))], "intersection"),
    ([field(), field(label=(40, 20, 80, 40), entry=(160, 10, 250, 30))], "intersection"),
    ([field(), field(page=2)], "SUCCESS"),
    ([field(entry=(60, 10, 150, 20), entry_text={"font_size": 14})], "height"),
    ([field(entry_text={"font_size": 14})], "SUCCESS"),
    ([field(entry=(60, 10, 150, 20), entry_text={})], "height"),
    ([field(entry=(60, 10, 150, 20))], "SUCCESS"),
    ([field(label=(10, 10, 50, 30), entry=(50, 10, 150, 30))], "SUCCESS"),
])
def test_bounding_box_checks(fields, outcome):
    messages = _messages({"form_fields": fields})
    assert any(outcome in m for m in messages), messages
    assert (outcome == "SUCCESS") != any("FAILURE" in m for m in messages)


def test_bounding_box_messages_are_capped():
    messages = _messages({"form_fields": [field(entry=(20, 15, 60, 35)) for _ in range(25)]})
    assert any("Aborting" in m for m in messages) and len(messages) < 30


def test_bounding_box_height_uses_the_page_scale(run, tmp_path):
    pdf = make_flat_form(tmp_path / "p.pdf")  # 792 pt tall, so a 1000 px image is 1.26 px/pt
    fields = write_json(tmp_path / "fields.json", {
        "pages": [{"page_number": 1, "image_width": 773, "image_height": 1000}],
        "form_fields": [field(entry=(60, 10, 300, 24), entry_text={"font_size": 12})],
    })
    assert run(f"{SCRIPTS}/check_bounding_boxes.py", fields).code == 0
    result = run(f"{SCRIPTS}/check_bounding_boxes.py", fields, pdf)
    assert result.code == 1 and "15px" in result.out


def test_validation_image(run, tmp_path):
    pdf = make_flat_form(tmp_path / "p.pdf")
    render(run, pdf, tmp_path / "pages")
    fields = write_json(tmp_path / "fields.json", {"form_fields": [field()]})
    result = run(f"{SCRIPTS}/create_validation_image.py", 1, fields, tmp_path / "pages" / "page_1.png",
                 tmp_path / "check.png")
    assert result.code == 0 and "2 boxes" in result.out


# Hygiene


def test_every_dependency_has_a_version_floor():
    for script in (ROOT / SCRIPTS).glob("*.py"):
        header = re.search(r"# dependencies = \[(.*?)\]", script.read_text())
        assert header, f"{script.name} has no PEP 723 header"
        for dep in re.findall(r'"([^"]+)"', header.group(1)):
            assert ">=" in dep, f"{script.name}: {dep} has no minimum version"
