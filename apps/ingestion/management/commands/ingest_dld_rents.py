"""Load DLD open-data Ejari rent-contract CSVs into the Rent table.

DLD's rent exports are split into overlapping date-range files with no
contract-number column, so the same contract can legitimately appear more
than once across the input files (or even within one, if re-downloaded).
Each row is hashed (sha256 of its normalized field values) into `row_hash`,
and loading uses bulk_create(ignore_conflicts=True) against Rent's unique
constraint on that field — duplicate rows are silently skipped rather than
loaded twice, whether they collide within a file, across files, or against
rows already in the table from a previous run.

Usage:
    python manage.py ingest_dld_rents data/dld_csv/rents-*.csv --truncate
"""
import csv
import hashlib
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.ingestion.models import Rent

FREEHOLD_MAP = {"Free Hold": True, "Non Free Hold": False}
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
ROW_FIELDS = (
    "REGISTRATION_DATE", "START_DATE", "END_DATE", "VERSION_EN", "AREA_EN",
    "CONTRACT_AMOUNT", "ANNUAL_AMOUNT", "IS_FREE_HOLD_EN", "ACTUAL_AREA",
    "PROP_TYPE_EN", "PROP_SUB_TYPE_EN", "ROOMS", "USAGE_EN", "NEAREST_METRO_EN",
    "NEAREST_MALL_EN", "NEAREST_LANDMARK_EN", "PARKING", "TOTAL_PROPERTIES",
    "MASTER_PROJECT_EN", "PROJECT_EN",
)


def _clean(value):
    return (value or "").strip()


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
        parsed = datetime.strptime(value, DATE_FORMAT)
    except ValueError:
        return None
    return timezone.make_aware(parsed)


def row_hash(row):
    normalized = "|".join(_clean(row.get(field)) for field in ROW_FIELDS)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def row_to_rent(row):
    return Rent(
        row_hash=row_hash(row),
        registration_date=_to_datetime(row.get("REGISTRATION_DATE")),
        start_date=_to_datetime(row.get("START_DATE")),
        end_date=_to_datetime(row.get("END_DATE")),
        version=_clean(row.get("VERSION_EN")),
        area=_clean(row.get("AREA_EN")),
        contract_amount=_to_decimal(row.get("CONTRACT_AMOUNT")),
        annual_amount=_to_decimal(row.get("ANNUAL_AMOUNT")),
        is_freehold=FREEHOLD_MAP.get(_clean(row.get("IS_FREE_HOLD_EN"))),
        actual_area=_to_decimal(row.get("ACTUAL_AREA")),
        property_type=_clean(row.get("PROP_TYPE_EN")),
        property_subtype=_clean(row.get("PROP_SUB_TYPE_EN")),
        rooms=_clean(row.get("ROOMS")),
        usage=_clean(row.get("USAGE_EN")),
        nearest_metro=_clean(row.get("NEAREST_METRO_EN")),
        nearest_mall=_clean(row.get("NEAREST_MALL_EN")),
        nearest_landmark=_clean(row.get("NEAREST_LANDMARK_EN")),
        parking=_clean(row.get("PARKING")),
        total_properties=_to_int(row.get("TOTAL_PROPERTIES")),
        master_project=_clean(row.get("MASTER_PROJECT_EN")),
        project=_clean(row.get("PROJECT_EN")),
    )


class Command(BaseCommand):
    help = (
        "Load Dubai Land Department open-data Ejari rent-contract CSV(s) into "
        "the Rent table as structured rows, deduping contracts that appear in "
        "more than one overlapping date-range export."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "paths", nargs="+", type=str,
            help="One or more paths to CSV files, and/or folders containing CSV files.",
        )
        parser.add_argument("--batch-size", type=int, default=5000, help="Rows per bulk_create batch (default: 5000).")
        parser.add_argument(
            "--truncate",
            action="store_true",
            help="Delete all existing Rent rows before loading, for an idempotent full reload.",
        )

    def handle(self, *args, **options):
        csv_paths = []
        for raw_path in options["paths"]:
            path = Path(raw_path)
            if path.is_dir():
                csv_paths.extend(sorted(path.glob("*.csv")))
            elif path.is_file():
                csv_paths.append(path)
            else:
                raise CommandError(f"{path} is not a file or directory.")

        if not csv_paths:
            raise CommandError(f"No CSV files found at {options['paths']}.")

        if options["truncate"]:
            deleted, _ = Rent.objects.all().delete()
            self.stdout.write(f"Deleted {deleted} existing Rent row(s).")

        batch_size = options["batch_size"]
        total_loaded = 0
        total_seen = 0
        for csv_path in csv_paths:
            loaded, seen = self._ingest_one(csv_path, batch_size)
            total_loaded += loaded
            total_seen += seen

        skipped = total_seen - total_loaded
        self.stdout.write(
            self.style.SUCCESS(
                f"Done. {total_loaded} row(s) loaded, {skipped} duplicate row(s) skipped "
                f"out of {total_seen} row(s) read."
            )
        )

    def _ingest_one(self, csv_path, batch_size):
        self.stdout.write(f"Loading {csv_path.name}...")
        batch = []
        seen = 0
        # bulk_create(ignore_conflicts=True) always returns len(batch) objects
        # regardless of how many hit the row_hash conflict, so a before/after
        # count of the table is the reliable way to know how many were
        # actually inserted. Counted once per file (not per batch) so this
        # stays O(files) rather than O(batches) full-table scans.
        before = Rent.objects.count()
        with open(csv_path, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                seen += 1
                batch.append(row_to_rent(row))
                if len(batch) >= batch_size:
                    Rent.objects.bulk_create(batch, ignore_conflicts=True)
                    self.stdout.write(f"  ...{seen} row(s) read")
                    batch = []
            if batch:
                Rent.objects.bulk_create(batch, ignore_conflicts=True)

        loaded = Rent.objects.count() - before
        self.stdout.write(self.style.SUCCESS(f"  {csv_path.name}: {loaded}/{seen} row(s) loaded."))
        return loaded, seen
