"""Load DLD open-data transaction CSVs into the Transaction table.

Usage:
    python manage.py ingest_dld_transactions data/dld_csv --truncate
"""
import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.ingestion.models import Transaction

OFFPLAN_MAP = {"Off-Plan": True, "Ready": False}
FREEHOLD_MAP = {"Free Hold": True, "Non Free Hold": False}
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def _clean(value):
    value = (value or "").strip()
    return value


def _to_decimal(value):
    value = _clean(value)
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _to_int(value):
    value = _clean(value)
    if not value:
        return None
    try:
        return int(Decimal(value))
    except (InvalidOperation, ValueError):
        return None


def _to_datetime(value):
    value = _clean(value)
    if not value:
        return None
    try:
        return datetime.strptime(value, DATE_FORMAT)
    except ValueError:
        return None


def row_to_transaction(row):
    return Transaction(
        transaction_number=_clean(row.get("TRANSACTION_NUMBER")),
        instance_date=_to_datetime(row.get("INSTANCE_DATE")),
        group=_clean(row.get("GROUP_EN")),
        procedure=_clean(row.get("PROCEDURE_EN")),
        is_offplan=OFFPLAN_MAP.get(_clean(row.get("IS_OFFPLAN_EN"))),
        is_freehold=FREEHOLD_MAP.get(_clean(row.get("IS_FREE_HOLD_EN"))),
        usage=_clean(row.get("USAGE_EN")),
        area=_clean(row.get("AREA_EN")),
        property_type=_clean(row.get("PROP_TYPE_EN")),
        property_subtype=_clean(row.get("PROP_SB_TYPE_EN")),
        transaction_value=_to_decimal(row.get("TRANS_VALUE")),
        procedure_area=_to_decimal(row.get("PROCEDURE_AREA")),
        actual_area=_to_decimal(row.get("ACTUAL_AREA")),
        rooms=_clean(row.get("ROOMS_EN")),
        parking=_clean(row.get("PARKING")),
        nearest_metro=_clean(row.get("NEAREST_METRO_EN")),
        nearest_mall=_clean(row.get("NEAREST_MALL_EN")),
        nearest_landmark=_clean(row.get("NEAREST_LANDMARK_EN")),
        total_buyer=_to_int(row.get("TOTAL_BUYER")),
        total_seller=_to_int(row.get("TOTAL_SELLER")),
        master_project=_clean(row.get("MASTER_PROJECT_EN")),
        project=_clean(row.get("PROJECT_EN")),
    )


class Command(BaseCommand):
    help = (
        "Load Dubai Land Department open-data transaction CSV(s) into the "
        "Transaction table as structured rows (no embeddings)."
    )

    def add_arguments(self, parser):
        parser.add_argument("path", type=str, help="Path to a CSV file or a folder containing CSV files.")
        parser.add_argument("--batch-size", type=int, default=5000, help="Rows per bulk_create batch (default: 5000).")
        parser.add_argument(
            "--truncate",
            action="store_true",
            help="Delete all existing Transaction rows before loading, for an idempotent full reload.",
        )

    def handle(self, *args, **options):
        path = Path(options["path"])
        if path.is_dir():
            csv_paths = sorted(path.glob("*.csv"))
        elif path.is_file():
            csv_paths = [path]
        else:
            raise CommandError(f"{path} is not a file or directory.")

        if not csv_paths:
            raise CommandError(f"No CSV files found at {path}.")

        if options["truncate"]:
            deleted, _ = Transaction.objects.all().delete()
            self.stdout.write(f"Deleted {deleted} existing Transaction row(s).")

        batch_size = options["batch_size"]
        for csv_path in csv_paths:
            self._ingest_one(csv_path, batch_size)

    def _ingest_one(self, csv_path, batch_size):
        self.stdout.write(f"Loading {csv_path.name}...")
        batch = []
        total = 0
        with open(csv_path, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                batch.append(row_to_transaction(row))
                if len(batch) >= batch_size:
                    Transaction.objects.bulk_create(batch)
                    total += len(batch)
                    self.stdout.write(f"  ...{total} row(s)")
                    batch = []
            if batch:
                Transaction.objects.bulk_create(batch)
                total += len(batch)

        self.stdout.write(self.style.SUCCESS(f"  Loaded {total} row(s) from {csv_path.name}."))
