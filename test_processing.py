from decimal import Decimal

from processing import (
    sum_by_banque_source,
    sum_by_iban_destinataire,
    sum_by_iban_origine,
    transactions_over_amount,
)


TRANSACTIONS = [
    {
        "datetime_transaction": "2026-01-01T09:00:00",
        "iban_origine": "FR_SOURCE_A",
        "pays_source": "FR",
        "banque_source": "Banque A",
        "iban_destinataire": "DE_DEST_A",
        "pays_destinataire": "DE",
        "montant": "100.00",
    },
    {
        "datetime_transaction": "2026-01-01T10:00:00",
        "iban_origine": "FR_SOURCE_A",
        "pays_source": "FR",
        "banque_source": "Banque A",
        "iban_destinataire": "IT_DEST_A",
        "pays_destinataire": "IT",
        "montant": "6000.00",
    },
    {
        "datetime_transaction": "2026-01-01T11:00:00",
        "iban_origine": "ES_SOURCE_B",
        "pays_source": "ES",
        "banque_source": "Banque B",
        "iban_destinataire": "DE_DEST_A",
        "pays_destinataire": "DE",
        "montant": "4900.00",
    },
]


def test_sum_by_iban_origine():
    assert sum_by_iban_origine(TRANSACTIONS) == {
        "FR_SOURCE_A": Decimal("6100.00"),
        "ES_SOURCE_B": Decimal("4900.00"),
    }


def test_sum_by_banque_source():
    assert sum_by_banque_source(TRANSACTIONS) == {
        "Banque A": Decimal("6100.00"),
        "Banque B": Decimal("4900.00"),
    }


def test_sum_by_iban_destinataire():
    assert sum_by_iban_destinataire(TRANSACTIONS) == {
        "DE_DEST_A": Decimal("5000.00"),
        "IT_DEST_A": Decimal("6000.00"),
    }


def test_transactions_over_amount_is_strictly_greater_than_threshold():
    assert transactions_over_amount(TRANSACTIONS) == [TRANSACTIONS[1]]


def test_processing_does_not_mutate_input():
    original = [transaction.copy() for transaction in TRANSACTIONS]

    sum_by_iban_origine(TRANSACTIONS)
    sum_by_banque_source(TRANSACTIONS)
    sum_by_iban_destinataire(TRANSACTIONS)
    transactions_over_amount(TRANSACTIONS)

    assert TRANSACTIONS == original