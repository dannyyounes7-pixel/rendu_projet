"""Pure functions for aggregating and filtering financial transactions."""

from collections import defaultdict
import csv
from decimal import Decimal
from io import BytesIO, TextIOWrapper
from typing import Dict, Iterable, List, Mapping, Union, cast


Transaction = Mapping[str, object]
Amount = Union[str, int, float, Decimal]


def charger_csv_depuis_s3(nom_fichier: str) -> List[Transaction]:
    """Download a CSV from MinIO and return its rows without local file I/O."""
    from s3_client import telecharger_csv

    csv_bytes = telecharger_csv(nom_fichier)
    with TextIOWrapper(BytesIO(csv_bytes), encoding="utf-8", newline="") as csv_stream:
        return cast(List[Transaction], list(csv.DictReader(csv_stream)))


def _as_decimal(value: Amount) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _sum_by(transactions: Iterable[Transaction], field: str) -> Dict[str, Decimal]:
    totals: Dict[str, Decimal] = defaultdict(Decimal)
    for transaction in transactions:
        key = str(transaction[field])
        totals[key] += _as_decimal(transaction["montant"])  # type: ignore[arg-type]
    return dict(totals)


def sum_by_iban_origine(transactions: List[Transaction]) -> Dict[str, Decimal]:
    """Return the total amount sent by each source IBAN."""
    return _sum_by(transactions, "iban_origine")


def sum_by_banque_source(transactions: List[Transaction]) -> Dict[str, Decimal]:
    """Return the total amount sent through each source bank."""
    return _sum_by(transactions, "banque_source")


def sum_by_iban_destinataire(transactions: List[Transaction]) -> Dict[str, Decimal]:
    """Return the total amount received by each destination IBAN."""
    return _sum_by(transactions, "iban_destinataire")


def transactions_over_amount(
    transactions: List[Transaction], threshold: Amount = Decimal("5000")
) -> List[Transaction]:
    """Return transactions whose amount is strictly greater than threshold."""
    limit = _as_decimal(threshold)
    return [
        transaction
        for transaction in transactions
        if _as_decimal(transaction["montant"]) > limit  # type: ignore[arg-type]
    ]