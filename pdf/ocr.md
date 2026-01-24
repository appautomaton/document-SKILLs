# OCR Processing Guide

Extract text from scanned PDFs and image-based documents using Tesseract OCR.

## Quick Start

```python
import pytesseract
from pdf2image import convert_from_path

# Convert PDF pages to images
images = convert_from_path("scanned.pdf")

# Extract text from each page
for i, image in enumerate(images):
    text = pytesseract.image_to_string(image)
    print(f"Page {i+1}:\n{text}\n")
```

## Image Preprocessing

Preprocessing significantly improves OCR accuracy on low-quality scans:

```python
from PIL import Image, ImageEnhance, ImageFilter

def preprocess_for_ocr(image):
    """Optimize image for better OCR accuracy."""
    # Convert to grayscale
    image = image.convert("L")

    # Increase contrast
    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(2.0)

    # Denoise
    image = image.filter(ImageFilter.MedianFilter())

    # Sharpen
    image = image.filter(ImageFilter.SHARPEN)

    return image

# Usage
image = Image.open("scanned_page.png")
processed = preprocess_for_ocr(image)
text = pytesseract.image_to_string(processed)
```

## Language Support

```python
# English (default)
text = pytesseract.image_to_string(image, lang="eng")

# Spanish
text = pytesseract.image_to_string(image, lang="spa")

# Multiple languages
text = pytesseract.image_to_string(image, lang="eng+spa+fra")
```

## Complete OCR Pipeline

```python
import pytesseract
from pdf2image import convert_from_path
from PIL import ImageEnhance, ImageFilter

def preprocess_for_ocr(image):
    image = image.convert("L")
    image = ImageEnhance.Contrast(image).enhance(2.0)
    image = image.filter(ImageFilter.MedianFilter())
    image = image.filter(ImageFilter.SHARPEN)
    return image

def ocr_pdf(pdf_path, output_path, lang="eng"):
    """OCR a PDF and save extracted text."""
    images = convert_from_path(pdf_path, dpi=300)
    full_text = []

    for i, image in enumerate(images, 1):
        print(f"Processing page {i}/{len(images)}")
        processed = preprocess_for_ocr(image)
        text = pytesseract.image_to_string(processed, lang=lang)
        full_text.append(f"--- Page {i} ---\n{text}\n")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(full_text))

    print(f"Saved to {output_path}")

# Usage
ocr_pdf("scanned_document.pdf", "extracted_text.txt")
```

## Installation

### Python packages

```bash
pip install pytesseract pdf2image pillow
```

### Tesseract OCR engine

**macOS:**
```bash
brew install tesseract
```

**Ubuntu/Debian:**
```bash
sudo apt-get install tesseract-ocr
```

**Additional languages:**
```bash
# macOS
brew install tesseract-lang

# Ubuntu
sudo apt-get install tesseract-ocr-spa tesseract-ocr-fra tesseract-ocr-deu
```

### Poppler (required by pdf2image)

**macOS:**
```bash
brew install poppler
```

**Ubuntu/Debian:**
```bash
sudo apt-get install poppler-utils
```

## Best Practices

1. **Use 300 DPI** for conversion: `convert_from_path(pdf, dpi=300)`
2. **Preprocess images** - grayscale, contrast, denoise, sharpen
3. **Specify language** when document is not English
4. **Validate output** - OCR is not 100% accurate, especially on poor quality scans
5. **Cache results** to avoid re-processing large documents

## Troubleshooting

### "Tesseract not found"

Ensure Tesseract is installed and in PATH:
```bash
which tesseract
tesseract --version
```

### Poor accuracy

1. Increase DPI (try 300 or 400)
2. Apply preprocessing pipeline
3. Check if correct language is specified
4. Original scan quality may be too low

### Memory issues with large PDFs

Process pages one at a time:
```python
from pdf2image import convert_from_path

for i, image in enumerate(convert_from_path("large.pdf", dpi=200)):
    text = pytesseract.image_to_string(preprocess_for_ocr(image))
    # Process immediately, don't accumulate all pages
```
