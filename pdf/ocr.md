# OCR for scanned PDFs

A PDF needs OCR when `pdftotext` or `page.extract_text()` returns little or nothing for pages that visibly contain text. This needs the Tesseract engine (`brew install tesseract`, or `apt-get install tesseract-ocr`), plus language data for anything other than English (`brew install tesseract-lang`, or for example `apt-get install tesseract-ocr-chi-sim`). Check with `tesseract --list-langs`.

Run with `uv run --with pytesseract --with pdf2image --with Pillow ocr.py`. Pages are rendered and recognised one at a time, so memory stays flat on long documents:

```python
import pytesseract
from pdf2image import convert_from_path, pdfinfo_from_path
from PIL import ImageFilter, ImageOps


def clean(image):
    """Greyscale, stretch contrast, remove speckle: helps on poor scans, rarely hurts on good ones."""
    return ImageOps.autocontrast(ImageOps.grayscale(image)).filter(ImageFilter.MedianFilter(3))


def ocr_pdf(path, lang="eng", dpi=300):
    pages = pdfinfo_from_path(path)["Pages"]
    for n in range(1, pages + 1):
        image = convert_from_path(path, dpi=dpi, first_page=n, last_page=n)[0]
        yield n, pytesseract.image_to_string(clean(image), lang=lang)


with open("scanned.txt", "w", encoding="utf-8") as out:
    for n, text in ocr_pdf("scanned.pdf", lang="eng"):
        out.write(f"--- Page {n} ---\n{text}\n")
```

## Getting good results

- **Resolution.** 300 dpi suits ordinary body text. Go to 400 for small print. Below 200, accuracy drops sharply.
- **Language.** Pass every language on the page, e.g. `lang="chi_sim+eng"`. Recognising Chinese text with the English model produces confident-looking nonsense.
- **Layout.** Tesseract guesses the layout of each page. For a single block or column, `config="--psm 6"` often reads better. For sparse text such as forms, try `--psm 11`.
- **Positions.** `pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)` returns every word with its box and a confidence from 0 to 100. Use it to locate text or to flag words below about 60 for checking.
- **Searchable PDF.** `pytesseract.image_to_pdf_or_hocr(image, extension="pdf")` returns a one-page PDF with an invisible text layer. Combine the pages with pypdf's `PdfWriter.append`.

OCR output always contains errors. Spot-check it against the page images before relying on numbers, names or dates.
