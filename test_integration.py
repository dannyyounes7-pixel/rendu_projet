import hashlib
import json
import os
import uuid
from datetime import datetime
from decimal import Decimal

import pytest

import database
import pipeline
from csv_io import load_transactions
from generate_csv import generate_csv_files
from processing import (
    sum_by_banque_source,
    sum_by_iban_destinataire,
    sum_by_iban_origine,
    transactions_over_amount,
)


def test_pipeline_checks_s3_and_skips_processed_keys_before_download(monkeypatch):
    pending_transaction = {
        "datetime_transaction": "2026-01-01T10:00:00",
        "iban_origine": "FR_SOURCE",
        "pays_source": "FR",
        "banque_source": "Banque A",
        "iban_destinataire": "DE_DEST",
        "pays_destinataire": "DE",
        "montant": "6100.00",
    }
    events = []
    inserted = []

    class FakeConnection:
        def close(self):
            pass

    monkeypatch.setattr(
        pipeline,
        "check_s3_accessible",
        lambda: events.append("check_s3"),
    )
    monkeypatch.setattr(
        pipeline,
        "list_transaction_files",
        lambda: events.append("list") or ["done.csv", "pending.csv"],
    )
    monkeypatch.setattr(pipeline, "connect", FakeConnection)
    monkeypatch.setattr(pipeline, "initialize_schema", lambda connection: None)
    monkeypatch.setattr(
        pipeline,
        "is_file_name_processed",
        lambda connection, name: name == "done.csv",
    )
    monkeypatch.setattr(pipeline, "is_file_processed", lambda connection, digest: False)

    def load_from_s3(file_name):
        events.append(f"download:{file_name}")
        return [pending_transaction]

    def save_results(**kwargs):
        inserted.append(kwargs)
        return True

    monkeypatch.setattr(pipeline, "charger_csv_depuis_s3", load_from_s3)
    monkeypatch.setattr(pipeline, "insert_file_results", save_results)

    pipeline.run_pipeline()

    assert events[:2] == ["check_s3", "list"]
    assert "download:done.csv" not in events
    assert "download:pending.csv" in events
    assert len(inserted) == 1
    assert inserted[0]["file_name"] == "pending.csv"


def test_pipeline_processes_unhandled_png_and_skips_processed_image(monkeypatch):
    receipt_transaction = {
        "datetime_transaction": "2026-04-12T09:30:00",
        "iban_origine": "FR7630006000011234567890189",
        "pays_source": "FR",
        "banque_source": "Banque Atlas",
        "iban_destinataire": "BE68539007547034",
        "pays_destinataire": "BE",
        "montant": "6200.00",
    }
    downloaded = []
    inserted = []

    class FakeConnection:
        def close(self):
            pass

    monkeypatch.setattr(pipeline, "check_s3_accessible", lambda: None)
    monkeypatch.setattr(
        pipeline,
        "list_transaction_files",
        lambda: ["receipts/already_done.png", "receipts/new_receipt.png"],
    )
    monkeypatch.setattr(pipeline, "connect", FakeConnection)
    monkeypatch.setattr(pipeline, "initialize_schema", lambda connection: None)
    monkeypatch.setattr(
        pipeline,
        "is_file_name_processed",
        lambda connection, name: name.endswith("already_done.png"),
    )
    monkeypatch.setattr(pipeline, "is_file_processed", lambda connection, digest: False)

    def fake_download(file_name):
        downloaded.append(file_name)
        return b"png-image-bytes"

    def fake_ocr(image_path):
        assert image_path.read_bytes() == b"png-image-bytes"
        return receipt_transaction

    monkeypatch.setattr(pipeline, "telecharger_fichier", fake_download)
    monkeypatch.setattr(pipeline, "extraire_transaction_depuis_image", fake_ocr)
    monkeypatch.setattr(
        pipeline,
        "insert_file_results",
        lambda **kwargs: inserted.append(kwargs) or True,
    )

    pipeline.run_pipeline()

    assert downloaded == ["receipts/new_receipt.png"]
    assert len(inserted) == 1
    assert inserted[0]["file_name"] == "receipts/new_receipt.png"
    assert inserted[0]["totals_by_source_iban"] == {
        "FR7630006000011234567890189": Decimal("6200.00")
    }
    assert inserted[0]["flagged_transactions"] == [receipt_transaction]


def test_insert_retries_psycopg2_errors_with_backoff_and_stops_for_existing_file(
    monkeypatch,
):
    import psycopg2

    class FakeConnection:
        def __init__(self):
            self.rollbacks = 0
            self.closed = False

        def rollback(self):
            self.rollbacks += 1

        def close(self):
            self.closed = True

    connection = FakeConnection()
    replacement_connections = []
    insert_once = iter(
        [psycopg2.OperationalError("temporary"), psycopg2.OperationalError("temporary"), True]
    )
    calls = []

    def fake_insert(*args):
        calls.append(args)
        result = next(insert_once)
        if isinstance(result, Exception):
            raise result
        return result

    def new_connection():
        replacement = FakeConnection()
        replacement_connections.append(replacement)
        return replacement

    delays = []
    monkeypatch.setattr(database, "_insert_file_results_once", fake_insert)
    monkeypatch.setattr(database.time, "sleep", delays.append)

    result = database.insert_file_results(
        connection,
        "sample.csv",
        "a" * 64,
        {},
        {},
        {},
        [],
        connection_factory=new_connection,
    )

    assert result is True
    assert len(calls) == 3
    assert calls[0][0] is connection
    assert calls[1][0] is replacement_connections[0]
    assert calls[2][0] is replacement_connections[1]
    assert connection.rollbacks == 1
    assert replacement_connections[0].rollbacks == 1
    assert all(item.closed for item in replacement_connections)
    assert delays == [1.0, 2.0]

    calls.clear()
    delays.clear()
    monkeypatch.setattr(database, "_insert_file_results_once", lambda *args: False)

    assert database.insert_file_results(connection, "sample.csv", "a" * 64, {}, {}, {}, []) is False
    assert delays == []
    assert len(calls) == 0


def test_insert_stops_after_three_retries(monkeypatch):
    import psycopg2

    class FakeConnection:
        def rollback(self):
            pass

    attempts = []
    delays = []

    def fail_insert(*args):
        attempts.append(args)
        raise psycopg2.OperationalError("temporary")

    monkeypatch.setattr(database, "_insert_file_results_once", fail_insert)
    monkeypatch.setattr(database.time, "sleep", delays.append)

    with pytest.raises(psycopg2.OperationalError):
        database.insert_file_results(FakeConnection(), "sample.csv", "a" * 64, {}, {}, {}, [])

    assert len(attempts) == 4
    assert delays == [1.0, 2.0, 4.0]


def test_pipeline_persists_exact_csv_results_in_postgres(tmp_path, monkeypatch):
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set TEST_DATABASE_URL to a dedicated PostgreSQL test database")

    psycopg2 = pytest.importorskip("psycopg2")
    from psycopg2 import sql

    schema_name = f"pytest_{uuid.uuid4().hex}"
    admin_connection = psycopg2.connect(database_url)
    admin_connection.autocommit = True
    with admin_connection.cursor() as cursor:
        cursor.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema_name)))

    def connect_to_test_schema():
        return psycopg2.connect(
            database_url,
            options=f"-c search_path={schema_name}",
        )

    monkeypatch.setattr(pipeline, "connect", connect_to_test_schema)

    try:
        csv_paths = generate_csv_files(tmp_path, upload_to_s3=False)
        expected_by_hash = {}
        transactions_by_name = {}
        for csv_path in csv_paths:
            transactions = load_transactions(csv_path)
            canonical_data = json.dumps(
                transactions,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            file_hash = hashlib.sha256(canonical_data).hexdigest()
            transactions_by_name[csv_path.name] = transactions
            expected_by_hash[file_hash] = {
                "file_name": csv_path.name,
                "source_iban": sum_by_iban_origine(transactions),
                "bank": sum_by_banque_source(transactions),
                "recipient_iban": sum_by_iban_destinataire(transactions),
                "flagged": transactions_over_amount(transactions),
            }

        monkeypatch.setattr(pipeline, "check_s3_accessible", lambda: None)
        monkeypatch.setattr(
            pipeline,
            "list_csv_files",
            lambda: [csv_path.name for csv_path in csv_paths],
        )
        monkeypatch.setattr(
            pipeline,
            "charger_csv_depuis_s3",
            transactions_by_name.__getitem__,
        )

        pipeline.run_pipeline()
        pipeline.run_pipeline()

        connection = connect_to_test_schema()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id, nom_fichier, empreinte_sha256 FROM fichiers_traites"
                )
                processed_files = cursor.fetchall()
                assert len(processed_files) == len(csv_paths)

                for file_id, file_name, file_hash in processed_files:
                    expected = expected_by_hash[file_hash.strip()]
                    assert file_name == expected["file_name"]

                    cursor.execute(
                        """SELECT iban_origine, montant_total
                           FROM sommes_par_iban_origine WHERE fichier_id = %s""",
                        (file_id,),
                    )
                    assert dict(cursor.fetchall()) == expected["source_iban"]

                    cursor.execute(
                        """SELECT banque_source, montant_total
                           FROM sommes_par_banque WHERE fichier_id = %s""",
                        (file_id,),
                    )
                    assert dict(cursor.fetchall()) == expected["bank"]

                    cursor.execute(
                        """SELECT iban_destinataire, montant_total
                           FROM sommes_recues_par_iban WHERE fichier_id = %s""",
                        (file_id,),
                    )
                    assert dict(cursor.fetchall()) == expected["recipient_iban"]

                    cursor.execute(
                        """SELECT datetime_transaction, iban_origine, pays_source,
                                  banque_source, iban_destinataire, pays_destinataire, montant
                           FROM transactions_flaggees WHERE fichier_id = %s
                           ORDER BY datetime_transaction""",
                        (file_id,),
                    )
                    actual_flagged = cursor.fetchall()
                    expected_flagged = [
                        (
                            datetime.fromisoformat(str(transaction["datetime_transaction"])),
                            transaction["iban_origine"],
                            transaction["pays_source"],
                            transaction["banque_source"],
                            transaction["iban_destinataire"],
                            transaction["pays_destinataire"],
                            Decimal(str(transaction["montant"])),
                        )
                        for transaction in expected["flagged"]
                    ]
                    assert actual_flagged == expected_flagged
        finally:
            connection.close()
    finally:
        with admin_connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema_name))
            )
        admin_connection.close()