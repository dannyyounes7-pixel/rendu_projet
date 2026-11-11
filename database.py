"""PostgreSQL connection and transaction-result persistence via psycopg2."""

import os
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Mapping, Sequence, Union

import psycopg2


Transaction = Mapping[str, object]
Amount = Union[str, int, float, Decimal]
MAX_INSERT_RETRIES = 3
INSERT_RETRY_BASE_DELAY_SECONDS = 1.0


def connect():
    """Connect using DATABASE_URL or the standard PG* environment variables."""
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return psycopg2.connect(database_url)

    return psycopg2.connect(
        dbname=os.getenv("PGDATABASE", "transactions"),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD"),
        host=os.getenv("PGHOST", "localhost"),
        port=os.getenv("PGPORT", "5432"),
    )


def initialize_schema(connection, schema_path: Union[str, Path, None] = None) -> None:
    """Create the result tables from schema.sql if they do not exist yet."""
    sql_path = Path(schema_path) if schema_path else Path(__file__).with_name("schema.sql")
    with connection:
        with connection.cursor() as cursor:
            cursor.execute(sql_path.read_text(encoding="utf-8"))


def is_file_processed(connection, sha256: str) -> bool:
    """Check whether a CSV with this content hash has already been processed."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM fichiers_traites WHERE empreinte_sha256 = %s",
            (sha256,),
        )
        return cursor.fetchone() is not None


def is_file_name_processed(connection, file_name: str) -> bool:
    """Check whether an object key has already been recorded in the database."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM fichiers_traites WHERE nom_fichier = %s LIMIT 1",
            (file_name,),
        )
        return cursor.fetchone() is not None


def insert_file_results(
    connection,
    file_name: str,
    sha256: str,
    totals_by_source_iban: Mapping[str, Amount],
    totals_by_bank: Mapping[str, Amount],
    totals_by_recipient_iban: Mapping[str, Amount],
    flagged_transactions: Sequence[Transaction],
    connection_factory=None,
) -> bool:
    """Retry atomic result insertion up to three times after psycopg2 errors.

    Delays grow exponentially between attempts. Return False if the same file
    content has already been recorded, including after an uncertain commit.
    """
    active_connection = connection
    owns_connection = False
    try:
        for attempt in range(MAX_INSERT_RETRIES + 1):
            try:
                if attempt > 0 and connection_factory is not None:
                    if owns_connection:
                        active_connection.close()
                    active_connection = connection_factory()
                    owns_connection = True
                return _insert_file_results_once(
                    active_connection,
                    file_name,
                    sha256,
                    totals_by_source_iban,
                    totals_by_bank,
                    totals_by_recipient_iban,
                    flagged_transactions,
                )
            except psycopg2.Error:
                try:
                    active_connection.rollback()
                except psycopg2.Error:
                    pass
                if attempt == MAX_INSERT_RETRIES:
                    raise
                time.sleep(INSERT_RETRY_BASE_DELAY_SECONDS * (2**attempt))
    finally:
        if owns_connection:
            active_connection.close()


def _insert_file_results_once(
    connection,
    file_name: str,
    sha256: str,
    totals_by_source_iban: Mapping[str, Amount],
    totals_by_bank: Mapping[str, Amount],
    totals_by_recipient_iban: Mapping[str, Amount],
    flagged_transactions: Sequence[Transaction],
) -> bool:
    """Atomically record the marker and all results unless the hash exists."""
    with connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO fichiers_traites (nom_fichier, empreinte_sha256)
                   VALUES (%s, %s)
                   ON CONFLICT (empreinte_sha256) DO NOTHING
                   RETURNING id""",
                (file_name, sha256),
            )
            inserted_file = cursor.fetchone()
            if inserted_file is None:
                return False

            file_id = inserted_file[0]
            cursor.executemany(
                """INSERT INTO sommes_par_iban_origine
                   (fichier_id, iban_origine, montant_total) VALUES (%s, %s, %s)""",
                [
                    (file_id, iban, _as_decimal(amount))
                    for iban, amount in totals_by_source_iban.items()
                ],
            )
            cursor.executemany(
                """INSERT INTO sommes_par_banque
                   (fichier_id, banque_source, montant_total) VALUES (%s, %s, %s)""",
                [
                    (file_id, bank, _as_decimal(amount))
                    for bank, amount in totals_by_bank.items()
                ],
            )
            cursor.executemany(
                """INSERT INTO sommes_recues_par_iban
                   (fichier_id, iban_destinataire, montant_total) VALUES (%s, %s, %s)""",
                [
                    (file_id, iban, _as_decimal(amount))
                    for iban, amount in totals_by_recipient_iban.items()
                ],
            )
            cursor.executemany(
                """INSERT INTO transactions_flaggees
                   (fichier_id, datetime_transaction, iban_origine, pays_source,
                    banque_source, iban_destinataire, pays_destinataire, montant)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                [
                    (
                        file_id,
                        datetime.fromisoformat(str(transaction["datetime_transaction"])),
                        str(transaction["iban_origine"]),
                        str(transaction["pays_source"]),
                        str(transaction["banque_source"]),
                        str(transaction["iban_destinataire"]),
                        str(transaction["pays_destinataire"]),
                        _as_decimal(transaction["montant"]),
                    )
                    for transaction in flagged_transactions
                ],
            )

    return True


def _as_decimal(value: Amount) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))