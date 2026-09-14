"""Report-generator agent: renders CalculationAgent + ComplianceAgent output
as a professional PDF investment report via ReportLab.

Takes already-computed PropertyAnalysis / ComplianceAssessment objects
rather than re-running those agents itself — this agent's only job is
layout/formatting, so it stays decoupled from how a scenario was built or
which data sources fed the other two agents.
"""
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.utils.text import slugify
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

# Reuses CalculationAgent's own thresholds/constants in the Methodology
# section, so a reader sees exactly what "confident" meant for these figures.
from apps.agents.calculation import (
    MIN_SAMPLE_SIZE, MIN_TREND_YEARS, MIN_YEAR_SAMPLE_SIZE, SQM_PER_SQFT, CalculationAgent,
)
from apps.agents.compliance import ComplianceAgent

NAVY = colors.HexColor("#1B2A4A")
GOLD = colors.HexColor("#B8860B")
LIGHT_GREY = colors.HexColor("#F2F2F2")
MID_GREY = colors.HexColor("#666666")
RED = colors.HexColor("#B00020")
GREEN = colors.HexColor("#1E7A34")

VERDICT_COLORS = {
    "violation": RED,
    "compliant": GREEN,
    "unclear": GOLD,
}


def _styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="ReportTitle", parent=styles["Title"], textColor=NAVY, fontSize=22, spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="ReportSubtitle", parent=styles["Normal"], textColor=MID_GREY, fontSize=11,
        alignment=TA_CENTER, spaceAfter=18,
    ))
    styles.add(ParagraphStyle(
        name="SectionHeading", parent=styles["Heading2"], textColor=NAVY, fontSize=14,
        spaceBefore=18, spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name="Body", parent=styles["Normal"], fontSize=10, leading=14,
    ))
    styles.add(ParagraphStyle(
        name="Note", parent=styles["Normal"], fontSize=9, leading=13, textColor=MID_GREY,
        fontName="Helvetica-Oblique",
    ))
    styles.add(ParagraphStyle(
        name="Small", parent=styles["Normal"], fontSize=8.5, leading=12, textColor=MID_GREY,
    ))
    return styles


def _metric_table(rows, styles):
    """A 2-column Metric/Value table with light banding."""
    data = [[Paragraph(f"<b>{label}</b>", styles["Body"]), Paragraph(value, styles["Body"])] for label, value in rows]
    table = Table(data, colWidths=[2.3 * inch, 4.2 * inch])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, LIGHT_GREY]),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return table


def _section_rule():
    return HRFlowable(width="100%", thickness=0.75, color=GOLD, spaceAfter=10)


def _money(value):
    return f"AED {value:,.0f}" if value is not None else "—"


class ReportAgent:
    """Renders a PDF investment report from CalculationAgent + ComplianceAgent output."""

    def __init__(self, output_dir=None):
        self.output_dir = Path(output_dir) if output_dir else Path(settings.MEDIA_ROOT) / "reports"

    def generate(self, property_analysis, compliance_assessment=None, output_path=None):
        """Render property_analysis (+ optional compliance_assessment) to a PDF.

        Returns the Path the PDF was written to.
        """
        if output_path is None:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            slug = slugify(f"{property_analysis.area}-{property_analysis.property_type}") or "property"
            output_path = self.output_dir / f"investment-report-{slug}-{stamp}.pdf"
        else:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

        styles = _styles()
        doc = SimpleDocTemplate(
            str(output_path), pagesize=A4,
            topMargin=0.85 * inch, bottomMargin=0.75 * inch,
            leftMargin=0.85 * inch, rightMargin=0.85 * inch,
            title=f"Investment Report — {property_analysis.area}",
        )

        story = []
        story += self._header(property_analysis, styles)
        story += self._overview_section(property_analysis, styles)
        story += self._price_section(property_analysis, styles)
        story += self._yield_section(property_analysis, styles)
        story += self._roi_section(property_analysis, styles)
        if compliance_assessment is not None:
            story += self._compliance_section(compliance_assessment, styles)
        story += self._methodology_section(styles)

        doc.build(story)
        return output_path

    def generate_for_property(self, area, property_type, purchase_price=None, years=5,
                               scenario=None, compliance_agent=None, output_path=None):
        """Convenience path: runs CalculationAgent (and, if scenario given, ComplianceAgent) then renders."""
        analysis = CalculationAgent().analyze(
            area=area, property_type=property_type, purchase_price=purchase_price, years=years,
        )
        assessment = None
        if scenario:
            assessment = (compliance_agent or ComplianceAgent()).check(scenario)
        return self.generate(analysis, assessment, output_path=output_path)

    # -- sections ----------------------------------------------------

    def _header(self, pa, styles):
        generated = datetime.now().strftime("%d %B %Y, %H:%M")
        return [
            Paragraph("Dubai Real Estate Investment Report", styles["ReportTitle"]),
            Paragraph(
                f"{pa.area} — {pa.property_type} &nbsp;|&nbsp; Generated {generated}",
                styles["ReportSubtitle"],
            ),
            _section_rule(),
        ]

    def _overview_section(self, pa, styles):
        rows = [
            ("Area", pa.area),
            ("Property Type", pa.property_type),
            ("Purchase Price", _money(pa.purchase_price)),
        ]
        return [
            Paragraph("Property Overview", styles["SectionHeading"]),
            _metric_table(rows, styles),
            Spacer(1, 4),
        ]

    def _price_section(self, pa, styles):
        pps = pa.price_per_sqft
        elements = [Paragraph("Price per Sqft (Sales Comparables)", styles["SectionHeading"])]
        if pps.available:
            rows = [
                ("Avg. Price / Sqft", f"AED {pps.value:,.0f}"),
                ("Comparable Sales", f"{pps.sample_size:,}"),
            ]
            elements.append(_metric_table(rows, styles))
        else:
            elements.append(Paragraph(f"<b>Not available.</b> {pps.message}", styles["Note"]))
        elements.append(Spacer(1, 4))
        return elements

    def _yield_section(self, pa, styles):
        ry = pa.rental_yield
        elements = [Paragraph("Rental Yield", styles["SectionHeading"])]
        if ry.available:
            rows = [
                ("Gross Rental Yield", f"{ry.value:.2f}%"),
                ("Comparable Rent Contracts", f"{ry.sample_size:,}"),
            ]
            elements.append(_metric_table(rows, styles))
            elements.append(Spacer(1, 4))
            elements.append(Paragraph(ry.message, styles["Note"]))
        else:
            elements.append(Paragraph(f"<b>Not available.</b> {ry.message}", styles["Note"]))
        elements.append(Spacer(1, 4))
        return elements

    def _roi_section(self, pa, styles):
        roi = pa.roi
        elements = [Paragraph(f"ROI Estimate ({roi.years}-Year Horizon)", styles["SectionHeading"])]
        if roi.available:
            rows = [
                ("Est. Annual Price Growth", f"{roi.annual_growth_rate * 100:.2f}%"),
                (f"Total ROI over {roi.years}y", f"{roi.total_roi_pct:.2f}%"),
            ]
            if roi.projected_value is not None:
                rows.append(("Projected Value", _money(roi.projected_value)))
            elements.append(_metric_table(rows, styles))
            elements.append(Spacer(1, 4))
            elements.append(Paragraph(roi.message, styles["Note"]))
        else:
            elements.append(Paragraph(f"<b>Not available.</b> {roi.message}", styles["Note"]))
        elements.append(Spacer(1, 4))
        return elements

    def _compliance_section(self, ca, styles):
        elements = [Paragraph("Compliance Assessment", styles["SectionHeading"])]
        elements.append(Paragraph(f"<b>Scenario:</b> {ca.scenario}", styles["Body"]))
        elements.append(Spacer(1, 6))

        verdict_color = VERDICT_COLORS.get(ca.verdict, MID_GREY)
        verdict_style = ParagraphStyle(
            name="Verdict", parent=styles["Body"], textColor=verdict_color, fontSize=12,
        )
        elements.append(Paragraph(f"<b>Verdict: {ca.verdict.upper()}</b>", verdict_style))
        elements.append(Spacer(1, 4))
        elements.append(Paragraph(ca.summary, styles["Body"]))
        elements.append(Spacer(1, 8))

        if ca.citations:
            header = ["#", "Article / Rule", "Source Document", "Relevance"]
            data = [header]
            for c in ca.citations:
                data.append([
                    str(c.source_number),
                    Paragraph(c.article_or_rule, styles["Small"]),
                    Paragraph(c.document_title, styles["Small"]),
                    Paragraph(c.relevance, styles["Small"]),
                ])
            table = Table(data, colWidths=[0.3 * inch, 1.5 * inch, 1.5 * inch, 3.2 * inch], repeatRows=1)
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GREY]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]))
            # Keep the (small, top_k-bounded) citations table intact rather than
            # letting ReportLab strand a lone row across a page break.
            elements.append(KeepTogether([table]))
        else:
            elements.append(Paragraph("No specific rule citations were returned for this scenario.", styles["Note"]))
        elements.append(Spacer(1, 4))
        return elements

    def _methodology_section(self, styles):
        elements = [
            Paragraph("Methodology &amp; Assumptions", styles["SectionHeading"]),
            Paragraph(
                "All figures in this report are computed deterministically from structured Dubai Land "
                "Department (DLD) open-data records — no figure is an LLM estimate or guess. Where the "
                "underlying data cannot support a confident result, the corresponding section is marked "
                "\"Not available\" with the specific reason, rather than presenting a guessed number.",
                styles["Body"],
            ),
            Spacer(1, 8),
            Paragraph(
                f"<b>Price per Sqft</b> is the average (Sales-group transaction value) / (sale area) across "
                f"comparable transactions matching the same area and property type, reported in AED/sqft "
                f"only when at least {MIN_SAMPLE_SIZE} comparable sales exist. DLD's ACTUAL_AREA field is "
                f"recorded in square meters; figures are converted to square feet by dividing by "
                f"{SQM_PER_SQFT} sqm/sqft.",
                styles["Body"],
            ),
            Spacer(1, 6),
            Paragraph(
                f"<b>Rental Yield</b> is (average annual rent per sqft) / (average sale price per sqft) "
                f"across matching Ejari rent contracts and sale comparables for the same area/property "
                f"type, reported only when at least {MIN_SAMPLE_SIZE} comparable rent contracts exist and "
                f"a confident price-per-sqft is available. Overlapping DLD rent-data exports were "
                f"deduplicated by contract fingerprint before this average was computed.",
                styles["Body"],
            ),
            Spacer(1, 6),
            Paragraph(
                f"<b>ROI Estimate</b> fits a compound annual growth rate to the average price/sqft across "
                f"calendar years with at least {MIN_YEAR_SAMPLE_SIZE} comparable sales, requiring at least "
                f"{MIN_TREND_YEARS} such years, then projects that rate forward over the stated horizon. "
                "This assumes historical price trends continue unchanged and does not account for "
                "transaction costs, financing, taxes, vacancy, or maintenance.",
                styles["Body"],
            ),
            Spacer(1, 6),
            Paragraph(
                "<b>Compliance Assessment</b>, where included, is generated by an LLM reasoning strictly "
                "over regulation excerpts retrieved (via embedding similarity search) from ingested RERA/DLD "
                "source documents. It reflects only what those excerpts state, is not a substitute for legal "
                "advice, and should be verified against the full, current regulation text before acting on it.",
                styles["Body"],
            ),
            Spacer(1, 10),
            Paragraph(
                "This report is generated for informational purposes only and does not constitute "
                "financial, investment, or legal advice.",
                styles["Small"],
            ),
        ]
        return elements


def generate_report(area, property_type, purchase_price=None, years=5, scenario=None, output_path=None):
    """Module-level convenience wrapper around ReportAgent().generate_for_property()."""
    return ReportAgent().generate_for_property(
        area=area, property_type=property_type, purchase_price=purchase_price,
        years=years, scenario=scenario, output_path=output_path,
    )
