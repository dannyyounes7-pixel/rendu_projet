"""CSV input helpers. Keep file access separate from pure transaction processing."""

import csv
from pathlib import Path
from typing import Dict, List, Union


def load_transactions(csv_path: Union[str, Path]) -> List[Dict[str, str]]:
    """Load transactions from a CSV file; values remain strings as read."""
    with Path(csv_path).open("r", newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))