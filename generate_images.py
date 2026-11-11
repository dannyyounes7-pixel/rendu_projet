"""Generate deterministic PNG images of fictional financial receipts."""

import argparse
from pathlib import Path
from typing import List, Tuple

from PIL import Image, ImageDraw, ImageFont


RECEIPTS: Tuple[Tuple[str, str, str, str, str], ...] = (
    (
        "2026-04-12 09:30:00",
        "FR7630006000011234567890189",
        "Banque Atlas",
        "BE68539007547034",
        "1250.00 EUR",
    ),
    (
        "2026-04-13 14:05:00",
        "DE91100000000123456789",
        "NordBank",
        "FR1420041010050500013M02606",
        "6200.00 EUR",
    ),
    (
        "2026-04-14 11:45:00",
        "GB29NWBK60161331926819",
        "Westminster Bank",
        "ES9121000418450200051332",
        "875.50 EUR",
    ),
)

FIELD_NAMES = (
    "datetime_transaction",
    "iban_origine",
    "banque_source",
    "iban_destinataire",
    "montant",
)


def _load_font(size: int) -> ImageFont.ImageFont:
    font_candidates = (
        "C:/Windows/Fonts/arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    )
    for font_path in font_candidates:
        if Path(font_path).is_file():
            return ImageFont.truetype(font_path, size=size)
    return ImageFont.load_default()


def generate_receipts(output_directory: Path) -> List[Path]:
    """Create and return three deterministic receipt images in the directory."""
    output_directory.mkdir(parents=True, exist_ok=True)
    generated_paths = []
    title_font = _load_font(30)
    field_font = _load_font(22)
    label_font = _load_font(18)

    for index, values in enumerate(RECEIPTS, start=1):
        image = Image.new("RGB", (900, 520), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((30, 30, 870, 490), outline="#222222", width=2)
        draw.text((60, 55), "TRANSACTION RECEIPT", fill="#111111", font=title_font)
        draw.line((60, 105, 840, 105), fill="#777777", width=2)

        y_position = 135
        for field_name, value in zip(FIELD_NAMES, values):
            draw.text((60, y_position), field_name, fill="#444444", font=label_font)
            draw.text((360, y_position - 2), value, fill="#111111", font=field_font)
            y_position += 65

        image_path = output_directory / f"transaction_receipt_{index}.png"
        image.save(image_path, format="PNG")
        generated_paths.append(image_path)

    return generated_paths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).parent / "generated_receipts",
        help="Directory where the PNG receipts are saved",
    )
    args = parser.parse_args()

    for image_path in generate_receipts(args.output_dir):
        print(image_path)


if __name__ == "__main__":
    main()