"""One-time fixup: give ingested RERA Document rows human-readable titles.

ingest_pdfs sets Document.title to the source PDF's filename stem (e.g.
"book", "issues_40270i"), which is fine as a unique key but useless in a
generated report's citation table. This command renames titles to what the
document actually is, read from its own text (law/decree/circular number
and subject) — matched by source_url's filename stem rather than the
current title, so it's safe to re-run after a document has already been
renamed (or reingested, which resets title but not source_url's stem).

Usage:
    python manage.py rename_rera_documents
"""
from pathlib import Path

from django.core.management.base import BaseCommand

from apps.ingestion.models import Document

# filename stem (as ingested from data/rera_pdfs/<stem>.pdf) -> human title.
TITLES = {
    "book": "RERA Legislation Handbook (2019 Edition)",
    "broker_and_tenant": "Lease Brokerage Agreement (Broker–Tenant)",
    "compliance-with-law-no-8-of-2007-regarding-the-marketing-of-real-estate-projects":
        "RERA Circular 02-2025 - Compliance with Law No. 8 of 2007 (Real Estate Project Marketing)",
    "compliance_with_the_provisions_of_law_no_8_of_2007_concerning_real_estate_development_escrow_acc":
        "RERA Circular 01-2026 - Law No. 8 of 2007 (Real Estate Development Escrow Accounts)",
    "direction-for-general-regulation-2010":
        "Direction for General Regulation Concerning Jointly Owned Properties (2010)",
    "emirates_book_valuation_standards_en": "Dubai Real Estate Valuation Guide (First Edition, 2025)",
    "issues_40270i": "RERA Circular 2/2014 - Timeshare Contracting Terms",
    "onwer_and_broker": "Lease Brokerage Agreement (Owner–Broker)",
    "property_viewing_agreement - Copy": "Property Viewing Agreement",
    "regulations_governing_communication_with_property_owners_and_the_prohibition_of_cold_callings":
        "RERA Circular 02-2026 - Communication with Property Owners & Prohibition of Cold Calling",
    "rental-increase-decree-43-in-dubai": "Decree No. 43 of 2013 - Rent Increase Determination",
    "tenancyguideen": "RERA Tenancy Guide (EJARI)",
    "tr01-survey-manual-sign_2022-04-26": "TR01 Survey Manual - Signage Requirements (2022)",
    "إلزامية-استخدام-ارقام-الهواتف-المسجلة-في-سجل-الوسطاء":
        "RERA Circular 01-2023 - Mandatory Use of Registered Broker Phone Numbers",
    "الإعلانات-من-خلال-المنصات-العقارية":
        "RERA Notice (Aug 2022) - Advertisements via Real Estate Platforms",
    "الاعلانات-العقارية-والحملات-الترويجية":
        "RERA Circular 01-2020 - Real Estate Advertisements & Promotional Campaigns",
    "الشروط-والاحكام-الخاصة-بالإعلانات-العقارية-1":
        "RERA Circular 02-2022 - Terms & Conditions for Real Estate Advertisements",
    "الشروط-والاحكام-الخاصة-بالتسويق-العقاري-على-المنصات-1":
        "RERA Circular 03-2022 - Terms & Conditions for Real Estate Marketing on Platforms",
    "النماذج-الموحدة-الخاصة-بالتأجير":
        "RERA Circular 21-2016 - Standard Forms for Leasing",
    "تطبيق-نظام-رمز-القارئ-السريع-_-qr-code-بالنسبة-للإعلانات-العقارية":
        "RERA Circular 02-2023 - QR Code Requirement for Real Estate Advertisements",
    "تعديل-شروط-تصريح-تسويق-عقارات-من-خارج-دولة":
        "RERA Circular 02-2018 - Amending Terms of Overseas Property Marketing Permit",
    "ربط-التصاريح-العقارية-بعقد-التسويق-الالكتروني":
        "RERA Circular 01-2022 - Linking Real Estate Permits to Electronic Marketing Contracts",
    "قرار-مجلس-الوزراء-رقم-134-لسنة-2025-في-شأن-اللائحة-التنفيذية-للمرسوم-بقانون-اتحادي-رقم-10-لسنة-2025-في-شأن-مواجهة-جرائم-غسل-الأموال-ومكافحة-ت":
        "Cabinet Resolution No. 134 of 2025 - Executive Regulations for AML/CFT Federal Decree-Law No. 10 of 2025",
    "قرار-مجلس-الوزراء-رقم-71-لسنة-2024-بشأن-تنظيم-المخالفات-والجزاءات-الإدارية-التي-توقع-على-المخالفين-لإجراءات-مواجهة-غسل-الأموال-ومكافحة-ت":
        "Cabinet Resolution No. 71 of 2024 - Administrative Violations & Penalties (AML/CFT)",
    "متابعة-تشكيل-لجان-الملاك-لمشاريع-الملكية-المشتركة":
        "RERA Notice (Nov 2021) - Owners' Committees for Jointly Owned Property Projects",
    "مرسوم-بقانون-اتحادي-رقم-10-لسنة-2025-في-شأن-مواجهة-جرائم-غسل-الأموال-ومكافحة-تمويل-الإرهاب-وتمويل-انتشار-التسلح":
        "Federal Decree-Law No. 10 of 2025 - Anti-Money Laundering & Counter-Terrorism Financing",
}


class Command(BaseCommand):
    help = "Rename ingested RERA Document rows from raw PDF filenames to human-readable titles."

    def handle(self, *args, **options):
        renamed = 0
        unchanged = 0
        unmatched_stems = []

        documents_by_stem = {}
        for document in Document.objects.all():
            stem = Path(document.source_url).stem if document.source_url else None
            if stem:
                documents_by_stem.setdefault(stem, []).append(document)

        for stem, new_title in TITLES.items():
            documents = documents_by_stem.pop(stem, [])
            if not documents:
                unmatched_stems.append(stem)
                continue
            for document in documents:
                if document.title == new_title:
                    unchanged += 1
                    continue
                old_title = document.title
                document.title = new_title
                document.save(update_fields=["title"])
                renamed += 1
                self.stdout.write(f"  {old_title!r} -> {new_title!r}")

        self.stdout.write(self.style.SUCCESS(
            f"Renamed {renamed} document(s), {unchanged} already up to date."
        ))
        if unmatched_stems:
            self.stdout.write(self.style.WARNING(
                f"{len(unmatched_stems)} title(s) in TITLES had no matching Document: {unmatched_stems}"
            ))
        if documents_by_stem:
            self.stdout.write(self.style.WARNING(
                f"{len(documents_by_stem)} ingested Document(s) have no entry in TITLES (left as-is): "
                f"{list(documents_by_stem.keys())}"
            ))
