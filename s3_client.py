"""Read and write CSV objects in the local MinIO transactions bucket."""

import os
import time
from pathlib import Path
from typing import List, Union

import boto3
from botocore.exceptions import BotoCoreError, ClientError


BUCKET_NAME = "transactions"
MAX_DOWNLOAD_RETRIES = 3
DOWNLOAD_RETRY_BASE_DELAY_SECONDS = 1.0


def _create_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=os.getenv("S3_ENDPOINT", "http://localhost:9000"),
        aws_access_key_id=os.getenv("S3_ACCESS_KEY", "transactions"),
        aws_secret_access_key=os.getenv(
            "S3_SECRET_KEY", "transactions-local-secret"
        ),
        region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
    )


def upload_csv(chemin_local: Union[str, Path], nom_fichier: str) -> None:
    """Upload one local CSV using the S3 settings from the environment."""
    local_path = Path(chemin_local)
    if not local_path.is_file():
        raise FileNotFoundError(f"CSV file not found: {local_path}")

    _create_s3_client().upload_file(str(local_path), BUCKET_NAME, nom_fichier)


def check_s3_accessible() -> None:
    """Raise the underlying boto3 error if the bucket cannot be reached."""
    _create_s3_client().head_bucket(Bucket=BUCKET_NAME)


def list_csv_files() -> List[str]:
    """Return all CSV object keys in the bucket, including nested keys."""
    client = _create_s3_client()
    paginator = client.get_paginator("list_objects_v2")
    csv_keys = []
    for page in paginator.paginate(Bucket=BUCKET_NAME):
        csv_keys.extend(
            item["Key"]
            for item in page.get("Contents", [])
            if item["Key"].lower().endswith(".csv")
        )
    return csv_keys


def list_transaction_files() -> List[str]:
    """Return CSV and PNG object keys from the transaction bucket."""
    client = _create_s3_client()
    paginator = client.get_paginator("list_objects_v2")
    transaction_keys = []
    for page in paginator.paginate(Bucket=BUCKET_NAME):
        transaction_keys.extend(
            item["Key"]
            for item in page.get("Contents", [])
            if item["Key"].lower().endswith((".csv", ".png"))
        )
    return transaction_keys


def lister_csv() -> List[str]:
    """Return CSV object keys from the transactions bucket."""
    return list_csv_files()


def telecharger_fichier(nom_fichier: str) -> bytes:
    """Return an S3 object's bytes, retrying up to three times on failure."""
    for attempt in range(MAX_DOWNLOAD_RETRIES + 1):
        try:
            response = _create_s3_client().get_object(
                Bucket=BUCKET_NAME,
                Key=nom_fichier,
            )
            with response["Body"] as body:
                return body.read()
        except (BotoCoreError, ClientError, OSError):
            if attempt == MAX_DOWNLOAD_RETRIES:
                raise
            time.sleep(DOWNLOAD_RETRY_BASE_DELAY_SECONDS * (2**attempt))

    raise RuntimeError("CSV download failed without an exception")


def telecharger_csv(nom_fichier: str) -> bytes:
    """Return CSV content in memory, retrying up to three times on failure."""
    return telecharger_fichier(nom_fichier)


def download_csv(nom_fichier: str) -> bytes:
    """Backward-compatible English alias for telecharger_csv."""
    return telecharger_csv(nom_fichier)