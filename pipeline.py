"""Generate, process, and persist the deterministic transaction CSV files."""

import hashlib
import json
import tempfile
from pathlib import Path

from database import (
    connect,
    initialize_schema,
    insert_file_results,
    is_file_name_processed,
    is_file_processed,
)
from processing import (
    charger_csv_depuis_s3,
    sum_by_banque_source,
    sum_by_iban_destinataire,
    sum_by_iban_origine,
    transactions_over_amount,
)
from ocr_processing import OCRExtractionError, extraire_transaction_depuis_image
from s3_client import check_s3_accessible, list_transaction_files, telecharger_fichier


def _transactions_sha256(transactions) -> str:
    canonical_data = json.dumps(
        transactions,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical_data).hexdigest()


def run_pipeline() -> None:
    """Process unhandled CSV objects from MinIO and persist their results."""
    check_s3_accessible()
    transaction_files = list_transaction_files()
    connection = connect()
    try:
        initialize_schema(connection)
    finally:
        connection.close()

    for file_name in transaction_files:
        connection = connect()
        try:
            if is_file_name_processed(connection, file_name):
                print(f"Déjà traité, ignoré : {file_name}")
                continue

            if file_name.lower().endswith(".csv"):
                transactions = charger_csv_depuis_s3(file_name)
                sha256 = _transactions_sha256(transactions)
            elif file_name.lower().endswith(".png"):
                image_bytes = telecharger_fichier(file_name)
                sha256 = hashlib.sha256(image_bytes).hexdigest()
                with tempfile.TemporaryDirectory() as temporary_directory:
                    image_path = Path(temporary_directory) / Path(file_name).name
                    image_path.write_bytes(image_bytes)
                    try:
                        transactions = [extraire_transaction_depuis_image(image_path)]
                    except OCRExtractionError as error:
                        print(f"OCR impossible pour {file_name}: {error}")
                        continue
            else:
                continue

            if is_file_processed(connection, sha256):
                print(f"Contenu déjà traité, ignoré : {file_name}")
                continue

            inserted = insert_file_results(
                connection=connection,
                file_name=file_name,
                sha256=sha256,
                totals_by_source_iban=sum_by_iban_origine(transactions),
                totals_by_bank=sum_by_banque_source(transactions),
                totals_by_recipient_iban=sum_by_iban_destinataire(transactions),
                flagged_transactions=transactions_over_amount(transactions),
                connection_factory=connect,
            )
            if inserted:
                print(f"Traité et enregistré : {file_name}")
            else:
                print(f"Déjà traité par une autre exécution : {file_name}")
        finally:
            connection.close()


if __name__ == "__main__":
    run_pipeline()