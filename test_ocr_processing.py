import pytest
from PIL import Image

import ocr_processing
from ocr_processing import OCRExtractionError, extraire_transaction_depuis_image


VALID_RECEIPT_TEXT = """TRANSACTION RECEIPT
datetime_transaction 2026-04-12 09:30:00
iban_origine FR7630006000011234567890189
banque_source Banque Atlas
iban_destinataire BE68539007547034
montant 1.250,00 EUR
"""


def _create_image(path):
    Image.new("RGB", (10, 10), "white").save(path, format="PNG")


def test_extract_transaction_normalizes_receipt_fields(tmp_path, monkeypatch):
    image_path = tmp_path / "receipt.png"
    _create_image(image_path)
    monkeypatch.setattr(ocr_processing.pytesseract, "image_to_string", lambda image: VALID_RECEIPT_TEXT)

    transaction = extraire_transaction_depuis_image(image_path)

    assert transaction == {
        "datetime_transaction": "2026-04-12T09:30:00",
        "iban_origine": "FR7630006000011234567890189",
        "pays_source": "FR",
        "banque_source": "Banque Atlas",
        "iban_destinataire": "BE68539007547034",
        "pays_destinataire": "BE",
        "montant": "1250.00",
    }


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("iban_origine", "FR??INVALID"),
        ("montant", "EUR ???"),
        ("datetime_transaction", "not-a-date"),
    ],
)
def test_unrecognized_fields_raise_actionable_error(tmp_path, monkeypatch, field, bad_value):
    image_path = tmp_path / "receipt.png"
    _create_image(image_path)
    text = VALID_RECEIPT_TEXT.replace(
        next(line for line in VALID_RECEIPT_TEXT.splitlines() if line.startswith(field)),
        f"{field} {bad_value}",
    )
    monkeypatch.setattr(ocr_processing.pytesseract, "image_to_string", lambda image: text)

    with pytest.raises(OCRExtractionError, match=field):
        extraire_transaction_depuis_image(image_path)


def test_missing_ocr_field_raises_actionable_error(tmp_path, monkeypatch):
    image_path = tmp_path / "receipt.png"
    _create_image(image_path)
    text = VALID_RECEIPT_TEXT.replace("montant 1.250,00 EUR\n", "")
    monkeypatch.setattr(ocr_processing.pytesseract, "image_to_string", lambda image: text)

    with pytest.raises(OCRExtractionError, match="montant"):
        extraire_transaction_depuis_image(image_path)