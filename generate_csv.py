"""Generate three deterministic CSV files containing financial transactions."""

import csv
from pathlib import Path
from typing import Union


CSV_FIELDS = (
    "datetime_transaction",
    "iban_origine",
    "pays_source",
    "banque_source",
    "iban_destinataire",
    "pays_destinataire",
    "montant",
)

TRANSACTIONS = (
    (
        ("2026-01-05T09:15:00", "FR7630006000011234567890189", "FR", "Banque Atlas", "BE68539007547034", "BE", "1250.00"),
        ("2026-01-05T11:40:00", "FR7630006000011234567890189", "FR", "Banque Atlas", "DE89370400440532013000", "DE", "6200.00"),
        ("2026-01-06T14:05:00", "DE91100000000123456789", "DE", "NordBank", "FR1420041010050500013M02606", "FR", "875.50"),
        ("2026-01-07T08:30:00", "GB29NWBK60161331926819", "GB", "Westminster Bank", "ES9121000418450200051332", "ES", "5100.00"),
        ("2026-01-07T16:20:00", "DE91100000000123456789", "DE", "NordBank", "BE68539007547034", "BE", "2400.00"),
    ),
    (
        ("2026-02-02T10:00:00", "FR7630006000011234567890189", "FR", "Banque Atlas", "IT60X0542811101000000123456", "IT", "3200.00"),
        ("2026-02-03T13:25:00", "ES9121000418450200051332", "ES", "Iberia Finance", "DE89370400440532013000", "DE", "7400.00"),
        ("2026-02-04T09:10:00", "GB29NWBK60161331926819", "GB", "Westminster Bank", "FR1420041010050500013M02606", "FR", "4999.99"),
        ("2026-02-05T15:45:00", "IT60X0542811101000000123456", "IT", "Banca Centro", "BE68539007547034", "BE", "5600.00"),
        ("2026-02-06T12:15:00", "ES9121000418450200051332", "ES", "Iberia Finance", "IT60X0542811101000000123456", "IT", "1800.00"),
    ),
    (
        ("2026-03-01T08:00:00", "DE91100000000123456789", "DE", "NordBank", "ES9121000418450200051332", "ES", "6150.00"),
        ("2026-03-02T10:35:00", "IT60X0542811101000000123456", "IT", "Banca Centro", "FR1420041010050500013M02606", "FR", "950.00"),
        ("2026-03-03T17:50:00", "FR7630006000011234567890189", "FR", "Banque Atlas", "DE89370400440532013000", "DE", "2800.00"),
        ("2026-03-04T11:05:00", "ES9121000418450200051332", "ES", "Iberia Finance", "BE68539007547034", "BE", "12500.00"),
        ("2026-03-05T14:30:00", "GB29NWBK60161331926819", "GB", "Westminster Bank", "IT60X0542811101000000123456", "IT", "2300.00"),
    ),
)


def generate_csv_files(
    output_directory: Union[str, Path] = Path(__file__).parent,
    upload_to_s3: bool = True,
) -> list[Path]:
    """Write three fixed CSV files and upload them unless explicitly disabled."""
    output_path = Path(output_directory)
    output_path.mkdir(parents=True, exist_ok=True)
    generated_paths = []

    for file_number, rows in enumerate(TRANSACTIONS, start=1):
        csv_path = output_path / f"transactions_{file_number}.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(CSV_FIELDS)
            writer.writerows(rows)
        generated_paths.append(csv_path)

    if upload_to_s3:
        from s3_client import upload_csv

        for csv_path in generated_paths:
            upload_csv(csv_path, csv_path.name)

    return generated_paths


if __name__ == "__main__":
    for generated_path in generate_csv_files():
        print(generated_path)