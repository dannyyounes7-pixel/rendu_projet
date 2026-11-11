from io import BytesIO
from pathlib import Path

import pytest
from botocore.exceptions import ClientError

import s3_client
from generate_csv import generate_csv_files
from processing import charger_csv_depuis_s3


def test_upload_csv_uses_environment_and_transactions_bucket(tmp_path, monkeypatch):
    local_csv = tmp_path / "sample.csv"
    local_csv.write_text("montant\n12.50\n", encoding="utf-8")
    upload_args = []

    class FakeS3Client:
        def upload_file(self, local_path, bucket, key):
            upload_args.append((local_path, bucket, key))

    client_args = {}

    def fake_boto3_client(service_name, **kwargs):
        client_args["service_name"] = service_name
        client_args.update(kwargs)
        return FakeS3Client()

    monkeypatch.setenv("S3_ENDPOINT", "http://minio.test:9000")
    monkeypatch.setenv("S3_ACCESS_KEY", "test-access")
    monkeypatch.setenv("S3_SECRET_KEY", "test-secret")
    monkeypatch.setattr(s3_client.boto3, "client", fake_boto3_client)

    s3_client.upload_csv(local_csv, "uploaded.csv")

    assert client_args == {
        "service_name": "s3",
        "endpoint_url": "http://minio.test:9000",
        "aws_access_key_id": "test-access",
        "aws_secret_access_key": "test-secret",
        "region_name": "us-east-1",
    }
    assert upload_args == [(str(local_csv), "transactions", "uploaded.csv")]
    assert local_csv.exists()


def test_generate_csv_files_uploads_each_generated_file(tmp_path, monkeypatch):
    uploaded = []

    def fake_upload(local_path, file_name):
        uploaded.append((Path(local_path), file_name))

    monkeypatch.setattr(s3_client, "upload_csv", fake_upload)

    generated_paths = generate_csv_files(tmp_path)

    assert uploaded == [(path, path.name) for path in generated_paths]
    assert len(generated_paths) == 3


def test_telecharger_csv_retries_with_increasing_delays(monkeypatch):
    class FakeS3Client:
        def __init__(self):
            self.attempts = 0

        def get_object(self, **kwargs):
            self.attempts += 1
            if self.attempts < 3:
                raise ClientError(
                    {"Error": {"Code": "NoSuchKey", "Message": "not ready"}},
                    "GetObject",
                )
            return {"Body": BytesIO(b"montant\n42.00\n")}

    client = FakeS3Client()
    delays = []
    monkeypatch.setattr(s3_client, "_create_s3_client", lambda: client)
    monkeypatch.setattr(s3_client.time, "sleep", delays.append)

    assert s3_client.telecharger_csv("sample.csv") == b"montant\n42.00\n"
    assert client.attempts == 3
    assert delays == [1.0, 2.0]


def test_telecharger_csv_raises_after_three_retries(monkeypatch):
    class FakeS3Client:
        def __init__(self):
            self.attempts = 0

        def get_object(self, **kwargs):
            self.attempts += 1
            raise ClientError(
                {"Error": {"Code": "NoSuchKey", "Message": "missing"}},
                "GetObject",
            )

    client = FakeS3Client()
    delays = []
    monkeypatch.setattr(s3_client, "_create_s3_client", lambda: client)
    monkeypatch.setattr(s3_client.time, "sleep", delays.append)

    with pytest.raises(ClientError):
        s3_client.telecharger_csv("missing.csv")

    assert client.attempts == 4
    assert delays == [1.0, 2.0, 4.0]


def test_charger_csv_depuis_s3_parses_downloaded_bytes(monkeypatch):
    content = (
        b"datetime_transaction,iban_origine,pays_source,banque_source,"
        b"iban_destinataire,pays_destinataire,montant\n"
        b"2026-01-01T10:00:00,FR_SOURCE,FR,Banque A,DE_DEST,DE,42.00\n"
    )
    requested_keys = []

    def fake_download(file_name):
        requested_keys.append(file_name)
        return content

    monkeypatch.setattr(s3_client, "telecharger_csv", fake_download)

    transactions = charger_csv_depuis_s3("daily/sample.csv")

    assert requested_keys == ["daily/sample.csv"]
    assert transactions == [
        {
            "datetime_transaction": "2026-01-01T10:00:00",
            "iban_origine": "FR_SOURCE",
            "pays_source": "FR",
            "banque_source": "Banque A",
            "iban_destinataire": "DE_DEST",
            "pays_destinataire": "DE",
            "montant": "42.00",
        }
    ]


def test_french_s3_function_names_delegate_to_existing_operations(monkeypatch):
    monkeypatch.setattr(s3_client, "telecharger_csv", lambda name: name.encode("utf-8"))
    monkeypatch.setattr(s3_client, "list_csv_files", lambda: ["a.csv", "b.csv"])

    assert s3_client.telecharger_csv("transactions/a.csv") == b"transactions/a.csv"
    assert s3_client.lister_csv() == ["a.csv", "b.csv"]


def test_list_transaction_files_returns_csv_and_png(monkeypatch):
    class FakePaginator:
        def paginate(self, **kwargs):
            assert kwargs == {"Bucket": "transactions"}
            return [
                {
                    "Contents": [
                        {"Key": "daily/transactions.csv"},
                        {"Key": "receipts/receipt.PNG"},
                        {"Key": "notes.txt"},
                    ]
                }
            ]

    class FakeS3Client:
        def get_paginator(self, operation):
            assert operation == "list_objects_v2"
            return FakePaginator()

    monkeypatch.setattr(s3_client, "_create_s3_client", FakeS3Client)

    assert s3_client.list_transaction_files() == [
        "daily/transactions.csv",
        "receipts/receipt.PNG",
    ]