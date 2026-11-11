"""Extract raw text from an image to verify the Tesseract installation."""

import argparse
import os
from pathlib import Path

import pytesseract
from PIL import Image
from pytesseract import TesseractNotFoundError


def extract_text(image_path: Path) -> str:
    """Run Tesseract OCR on an image and return the unmodified text result."""
    tesseract_cmd = os.getenv("TESSERACT_CMD")
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    with Image.open(image_path) as image:
        return pytesseract.image_to_string(image)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="Path to an image to OCR")
    args = parser.parse_args()

    if not args.image.is_file():
        parser.error(f"Image file does not exist: {args.image}")

    try:
        print(extract_text(args.image), end="")
    except TesseractNotFoundError:
        parser.error(
            "Tesseract is not installed or is not in PATH. Install the system "
            "Tesseract OCR engine, or set TESSERACT_CMD to its executable path."
        )


if __name__ == "__main__":
    main()