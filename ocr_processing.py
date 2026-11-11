"""Extract and validate transactions from OCR-readable receipt images."""

import os
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TypedDict, Union

import pytesseract
from PIL import Image


class Transaction(TypedDict):
    datetime_transaction: str
    iban_origine: str
    pays_source: str
    banque_source: str
    iban_destinataire: str
    pays_destinataire: str
    montant: str


class OCRExtractionError(ValueError):
    """Raised when required receipt data is missing or unreadable by OCR."""


FIELD_LABELS = (
    "datetime_transaction",
    "iban_origine",
    "banque_source",
    "iban_destinataire",
    "montant",
)


def _read_field(text: str, field_name: str) -> str:
    label_pattern = re.escape(field_name).replace(r"\_", r"[\s_-]*")
    other_labels = "|".join(
        re.escape(label).replace(r"\_", r"[\s_-]*")
        for label in FIELD_LABELS
        if label != field_name
    )
    match = re.search(
        rf"{label_pattern}\s*[:=]?\s*(.*?)"
        rf"(?=\s+(?:{other_labels})\b|$)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match or not match.group(1).strip(" \t\r\n:="):
        raise OCRExtractionError(
            f"Champ '{field_name}' absent ou mal reconnu par l'OCR."
        )
    return re.sub(r"\s+", " ", match.group(1)).strip(" \t\r\n:=")


def _normalize_iban(value: str, field_name: str) -> str:
    iban = re.sub(r"\s+", "", value).upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", iban):
        raise OCRExtractionError(
            f"Champ '{field_name}' invalide ou mal reconnu: {value!r}."
        )
    return iban


def _normalize_amount(value: str) -> str:
    amount = re.sub(r"[^\d.,-]", "", value)
    if "," in amount and "." in amount:
        if amount.rfind(",") > amount.rfind("."):
            amount = amount.replace(".", "").replace(",", ".")
        else:
            amount = amount.replace(",", "")
    elif "," in amount:
        amount = amount.replace(",", ".")

    try:
        parsed_amount = Decimal(amount)
    except InvalidOperation as error:
        raise OCRExtractionError(
            f"Champ 'montant' invalide ou mal reconnu: {value!r}."
        ) from error
    if not parsed_amount.is_finite() or parsed_amount < 0:
        raise OCRExtractionError(
            f"Champ 'montant' invalide ou mal reconnu: {value!r}."
        )
    return f"{parsed_amount:.2f}"


def extraire_transaction_depuis_image(
    chemin_image: Union[str, Path],
) -> Transaction:
    """OCR a receipt and return a normalized transaction or a clear error."""
    tesseract_cmd = os.getenv("TESSERACT_CMD")
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    try:
        with Image.open(chemin_image) as image:
            text = pytesseract.image_to_string(image)
    except (OSError, pytesseract.TesseractNotFoundError) as error:
        raise OCRExtractionError(f"Impossible de lire l'image ou Tesseract: {error}") from error

    datetime_text = _read_field(text, "datetime_transaction")
    try:
        transaction_datetime = datetime.fromisoformat(datetime_text)
    except ValueError as error:
        raise OCRExtractionError(
            f"Champ 'datetime_transaction' invalide ou mal reconnu: {datetime_text!r}."
        ) from error

    source_iban = _normalize_iban(_read_field(text, "iban_origine"), "iban_origine")
    recipient_iban = _normalize_iban(
        _read_field(text, "iban_destinataire"), "iban_destinataire"
    )
    bank_name = _read_field(text, "banque_source")
    amount = _normalize_amount(_read_field(text, "montant"))

    return {
        "datetime_transaction": transaction_datetime.isoformat(),
        "iban_origine": source_iban,
        "pays_source": source_iban[:2],
        "banque_source": bank_name,
        "iban_destinataire": recipient_iban,
        "pays_destinataire": recipient_iban[:2],
        "montant": amount,
    }