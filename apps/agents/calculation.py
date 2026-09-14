"""Calculation agent: deterministic ROI/yield math over ingested DLD Transaction data.

No LLM calls here — every figure is computed directly from Transaction rows
with plain arithmetic (Avg/Count aggregates, simple compounding). Where the
data can't support a confident estimate (too few comparable transactions, no
rent data ingested, price history spanning too few years), the corresponding
result is flagged as unavailable with a clear message instead of guessed.
"""
from dataclasses import dataclass

from django.db.models import Avg, Count, F
from django.db.models.functions import ExtractYear

from apps.ingestion.models import Transaction

# Minimum comparable Sales transactions required before an average is trusted.
MIN_SAMPLE_SIZE = 20
# Minimum distinct calendar years (each meeting MIN_YEAR_SAMPLE_SIZE) required
# to fit a price trend for ROI projection.
MIN_TREND_YEARS = 2
MIN_YEAR_SAMPLE_SIZE = 10


@dataclass
class PricePerSqft:
    available: bool
    value: float | None = None
    sample_size: int = 0
    message: str = ""


@dataclass
class RentalYield:
    available: bool
    value: float | None = None
    message: str = ""


@dataclass
class ROIEstimate:
    available: bool
    years: int = 0
    annual_growth_rate: float | None = None
    total_roi_pct: float | None = None
    projected_value: float | None = None
    message: str = ""


@dataclass
class PropertyAnalysis:
    area: str
    property_type: str
    purchase_price: float | None
    price_per_sqft: PricePerSqft
    rental_yield: RentalYield
    roi: ROIEstimate


class CalculationAgent:
    """Deterministic ROI/yield calculations over the Transaction table."""

    def __init__(self, min_sample_size=MIN_SAMPLE_SIZE, min_trend_years=MIN_TREND_YEARS,
                 min_year_sample_size=MIN_YEAR_SAMPLE_SIZE):
        self.min_sample_size = min_sample_size
        self.min_trend_years = min_trend_years
        self.min_year_sample_size = min_year_sample_size

    def analyze(self, area=None, property_type=None, purchase_price=None,
                transaction_id=None, years=5):
        """Analyze a property's price/sqft, rental yield, and ROI over `years`.

        Either pass `area` + `property_type` directly, or `transaction_id` to
        derive them (and, if `purchase_price` is omitted, the purchase price)
        from an existing Transaction row. `purchase_price` may be supplied
        alongside `transaction_id` to override that row's transaction_value.
        """
        if transaction_id is not None:
            try:
                reference = Transaction.objects.get(pk=transaction_id)
            except Transaction.DoesNotExist:
                raise ValueError(f"No Transaction found with id={transaction_id}.")
            area = area or reference.area
            property_type = property_type or reference.property_type
            if purchase_price is None:
                purchase_price = float(reference.transaction_value) if reference.transaction_value else None

        if not area or not property_type:
            raise ValueError(
                "Must provide either (area and property_type) or transaction_id."
            )

        comparables = Transaction.objects.filter(
            group="Sales",
            area__iexact=area,
            property_type__iexact=property_type,
            transaction_value__isnull=False,
            actual_area__isnull=False,
        ).exclude(actual_area=0)

        price_per_sqft = self._price_per_sqft(comparables, area, property_type)
        rental_yield = self._rental_yield(area, property_type)
        roi = self._roi(comparables, area, property_type, purchase_price, years)

        return PropertyAnalysis(
            area=area,
            property_type=property_type,
            purchase_price=purchase_price,
            price_per_sqft=price_per_sqft,
            rental_yield=rental_yield,
            roi=roi,
        )

    def _price_per_sqft(self, comparables, area, property_type):
        stats = comparables.annotate(ppsf=F("transaction_value") / F("actual_area")).aggregate(
            avg_ppsf=Avg("ppsf"), n=Count("id")
        )
        n = stats["n"] or 0
        if n < self.min_sample_size:
            return PricePerSqft(
                available=False,
                sample_size=n,
                message=(
                    f"Only {n} comparable Sales transaction(s) found for "
                    f"area='{area}', property_type='{property_type}' — need at "
                    f"least {self.min_sample_size} to report a confident average."
                ),
            )
        return PricePerSqft(available=True, value=float(stats["avg_ppsf"]), sample_size=n)

    def _rental_yield(self, area, property_type):
        rent_groups_exist = (
            Transaction.objects.filter(group__icontains="rent").exists()
            or Transaction.objects.filter(procedure__icontains="rent").exists()
        )
        if not rent_groups_exist:
            return RentalYield(
                available=False,
                message=(
                    "No rent contract data has been ingested (the Transaction "
                    "table currently holds only Sales/Mortgage/Gifts records) — "
                    "rental yield cannot be estimated without it."
                ),
            )
        # Rent data is present in the schema; a real yield calculation would
        # go here (avg annual rent / avg sale price for comparable units).
        return RentalYield(
            available=False,
            message="Rent data is present but rental-yield calculation is not yet implemented.",
        )

    def _roi(self, comparables, area, property_type, purchase_price, years):
        yearly = (
            comparables.annotate(year=ExtractYear("instance_date"), ppsf=F("transaction_value") / F("actual_area"))
            .values("year")
            .annotate(avg_ppsf=Avg("ppsf"), n=Count("id"))
            .order_by("year")
        )
        qualifying_years = [row for row in yearly if row["year"] is not None and row["n"] >= self.min_year_sample_size]

        if len(qualifying_years) < self.min_trend_years:
            return ROIEstimate(
                available=False,
                years=years,
                message=(
                    f"Price history for area='{area}', property_type='{property_type}' "
                    f"covers only {len(qualifying_years)} calendar year(s) with at least "
                    f"{self.min_year_sample_size} sales — need at least {self.min_trend_years} "
                    "years of data to fit a price trend, so ROI cannot be estimated confidently."
                ),
            )

        first_year, last_year = qualifying_years[0], qualifying_years[-1]
        span = last_year["year"] - first_year["year"]
        first_ppsf, last_ppsf = float(first_year["avg_ppsf"]), float(last_year["avg_ppsf"])

        if span <= 0 or first_ppsf <= 0:
            return ROIEstimate(
                available=False,
                years=years,
                message="Price history does not span multiple distinct years — cannot fit a trend.",
            )

        annual_growth_rate = (last_ppsf / first_ppsf) ** (1 / span) - 1
        total_roi_pct = ((1 + annual_growth_rate) ** years - 1) * 100
        projected_value = purchase_price * (1 + annual_growth_rate) ** years if purchase_price else None

        return ROIEstimate(
            available=True,
            years=years,
            annual_growth_rate=annual_growth_rate,
            total_roi_pct=total_roi_pct,
            projected_value=projected_value,
            message=(
                f"Based on price/sqft trend from {first_year['year']} to {last_year['year']} "
                f"({span} year span) — treat as approximate given the limited history."
            ),
        )


def analyze_property(area=None, property_type=None, purchase_price=None, transaction_id=None, years=5):
    """Module-level convenience wrapper around CalculationAgent().analyze()."""
    return CalculationAgent().analyze(
        area=area, property_type=property_type, purchase_price=purchase_price,
        transaction_id=transaction_id, years=years,
    )
