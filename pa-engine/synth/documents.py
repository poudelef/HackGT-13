"""Fictional fallback documents and synthetic chart text. Not published insurer material."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

POLICY_FOOTER = "FICTIONAL FALLBACK POLICY. NOT A PUBLISHED INSURER DOCUMENT."
PATIENT_FOOTER = "SYNTHETIC TEST DATA. NOT A REAL PATIENT."

CLINICAL_PAGES = [
    [
        "Northwind Mutual",
        "Clinical policy",
        "Medical policy for lumbar spine imaging",
        "Policy number: MP-IMG-014",
        "Effective Date: 01/01/2026",
        "Plan: Open Access PPO",
        "Coverage criteria for medically necessary imaging.",
        "Indications are listed in the next section.",
    ],
    [
        "4. Coverage criteria",
        "All of the following must be documented.",
        "4.1 Diagnosis of lumbar radiculopathy (M54.16) is documented.",
        "4.2 A neurological symptom is documented in the clinical note.",
        "4.3 Symptoms have been present for at least 6 weeks.",
        "4.4 The patient must not have had lumbar surgery in the past 6 months.",
        "4.5 At least 6 weeks of physical therapy in the past 6 months, unless contraindicated.",
        "5. Coding",
        "This policy applies to MRI lumbar spine without contrast (72148).",
    ],
    [
        "6. Definitions",
        "Medically necessary care matches the documented symptoms.",
        "7. References",
        "Criteria in this clinical policy were reviewed for publication.",
    ],
]

BENEFIT_PAGES = [
    [
        "Northwind Mutual",
        "Summary of Benefits",
        "Evidence of coverage",
        "Plan: Open Access PPO",
        "Effective Date: 01/01/2026",
        "What you pay is listed with in-network cost sharing.",
        "Copayment and coinsurance are in the benefits chart.",
    ],
    [
        "Benefits chart",
        "Service: Advanced imaging MRI 72148 | You pay: 20% coinsurance | Authorization: Prior authorization required",
        "Service: Office visit | You pay: $20 copayment | Authorization: No prior authorization required",
        "In-network benefits apply to the rows above.",
    ],
]

DRUG_PAGES = [
    [
        "Northwind Mutual",
        "Prior authorization criteria",
        "Plan: Open Access PPO",
        "Effective Date: 01/01/2026",
        "Drug name, covered uses, exclusion criteria, and age restrictions follow.",
        "Required medical information and prescriber restrictions may apply.",
        "Coverage duration is stated on the drug block.",
    ],
    [
        "Drug: Northpine",
        "Covered uses: Documented diagnosis J45.40.",
        "Age restrictions: 18 years or older.",
        "Coverage duration: 12 months.",
    ],
]

NOTE_BODY = (
    "Neurological symptom documented: patient reports numbness in the left foot since August. "
    "No lumbar surgery in the past 6 months."
)

WITHHELD_BODY = (
    "Completed 7 weeks of physical therapy for lumbar radiculopathy. "
    "Last session was September 20, 2026."
)

REFERRAL_DISPLAY = "Physical therapy referral"


def write_pdf(path: Path, pages: list[list[str]], footer: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pen = canvas.Canvas(str(path), pagesize=letter)
    for index, lines in enumerate(pages, start=1):
        y = 740
        for line in lines:
            pen.setFont("Times-Roman", 11)
            pen.drawString(48, y, line)
            y -= 18
        pen.setFont("Times-Roman", 8)
        pen.drawString(48, 42, footer)
        pen.drawString(48, 28, f"Printed page {index}")
        pen.showPage()
    pen.save()
