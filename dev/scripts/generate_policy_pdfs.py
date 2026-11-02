"""Render data/kb/policies/POL-*.pdf from policies.csv — one source of truth.

WHY THIS EXISTS
Three problems collapse into one missing script.

1. The PDFs had drifted from the CSV, and the drift landed on the demo. The
   shipped POL-112233.pdf named "Aditya Nair" while policies.csv says "Vijay M";
   POL-445566.pdf named "Meera Iyer" against "Rohit Madeshiya". Those are Case 1
   and Case 2 — the two policies the live demo actually uses. Agent 4 retrieves
   these documents through RAG and quotes them, so it was quoting the wrong
   customer's policy back at the adjudicator. Reg numbers, premiums and
   deductibles had drifted too (POL-112233 read KL-14-BC-7890 against the CSV's
   TN12AJ1603), and one policy period spanned three years while calling itself
   "12 months". Tracked as changelog open item #3.

2. The `add_ons` column added in this remediation has to reach the policy
   DOCUMENT, not just the CSV. Otherwise the RAG context Agent 4 quotes
   contradicts what settlement_calc actually applies — the document would be
   silent about a Zero-Depreciation cover that is waiving real money.

3. `dev/scripts/generate_policy_pdfs.py` was referenced by the README and by
   `data/kb/policies/`'s provenance while not existing, so a fresh clone could
   not rebuild them at all.

The scope of cover drives the document's content, not just a label: a
liability-only policy must not print own-damage sections, or the retrieved text
would tell Agent 4 the opposite of what the eligibility gate enforces.

USAGE
    python dev/scripts/generate_policy_pdfs.py            # all policies
    python dev/scripts/generate_policy_pdfs.py POL-112233 # one
Rebuild the vectorstore afterwards so RAG serves the new text:
    python dev/scripts/build_vectorstore.py
"""

from __future__ import annotations

import csv
import os
import sys
from datetime import datetime

from fpdf import FPDF

# dev/scripts/<file>.py -> repo root is three levels up (was two, before
# scripts/ moved under dev/).
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "backend"))

POLICIES_CSV = os.path.join(ROOT, "data", "policies.csv")
OUT_DIR = os.path.join(ROOT, "data", "kb", "policies")

INSURER = "GANIT MOTORS INSURANCE CO. LTD."
INSURER_META = "CIN: U66022KA2010PLC052345  |  IRDAI Reg No: 145"

DARK_BLUE = (17, 62, 110)
LIGHT_BLUE_BG = (223, 236, 249)
GREY_TEXT = (90, 90, 90)
RED = (170, 30, 30)


def _s(text) -> str:
    """fpdf2 core fonts are Latin-1 only — sanitise before every write."""
    if text is None:
        return ""
    t = str(text)
    for a, b in (("—", "-"), ("–", "-"), ("→", "->"),
                 ("₹", "Rs. "), ("’", "'"), ("“", '"'),
                 ("”", '"'), ("•", "*")):
        t = t.replace(a, b)
    return t.encode("latin-1", "replace").decode("latin-1")


def _inr(v) -> str:
    try:
        return f"Rs. {int(float(v)):,}"
    except (TypeError, ValueError):
        return "Rs. 0"


class PolicyPDF(FPDF):
    def __init__(self, policy_no: str):
        super().__init__()
        self.policy_no = policy_no
        self.set_auto_page_break(auto=True, margin=18)

    def header(self):
        self.set_font("Helvetica", "B", 8)
        self.set_text_color(*GREY_TEXT)
        self.cell(0, 6, _s(f"{INSURER}  |  {INSURER_META}"),
                  align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def footer(self):
        self.set_y(-14)
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(*GREY_TEXT)
        self.cell(0, 5, _s(f"Policy: {self.policy_no}  |  Page {self.page_no()}/{{nb}}  |  "
                           f"Computer-generated document. Valid without signature."),
                  align="C")


def _bar(pdf: PolicyPDF, title: str) -> None:
    pdf.ln(2)
    pdf.set_fill_color(*DARK_BLUE)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 9.5)
    pdf.cell(0, 7, _s(f"  {title}"), fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(1.5)


def _kv(pdf: PolicyPDF, label: str, value: str, alt: bool = False) -> None:
    pdf.set_fill_color(*(LIGHT_BLUE_BG if alt else (255, 255, 255)))
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(*GREY_TEXT)
    pdf.cell(62, 6, _s(f"  {label}"), fill=True)
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 6, _s(value), fill=True, new_x="LMARGIN", new_y="NEXT")


def _para(pdf: PolicyPDF, text: str, size: float = 8, italic: bool = False) -> None:
    pdf.set_font("Helvetica", "I" if italic else "", size)
    pdf.set_text_color(0, 0, 0)
    pdf.multi_cell(0, 4.6, _s(text), new_x="LMARGIN", new_y="NEXT")


# IMT GR.9 — the schedule settlement_calc._depreciation_pct implements. Printed
# here because settlement_calc's own comment says it is "the same table printed
# in the generated policy PDFs"; until this script existed, it was not.
DEPRECIATION_ROWS = [
    ("Not exceeding 6 months", "Nil"),
    ("Exceeding 6 months, not exceeding 1 year", "5%"),
    ("Exceeding 1 year, not exceeding 2 years", "10%"),
    ("Exceeding 2 years, not exceeding 3 years", "15%"),
    ("Exceeding 3 years, not exceeding 4 years", "25%"),
    ("Exceeding 4 years, not exceeding 5 years", "35%"),
    ("Exceeding 5 years, not exceeding 10 years", "40%"),
    ("Exceeding 10 years", "50%"),
]

EXCLUSIONS = [
    "Damage caused while driving under the influence of alcohol or drugs.",
    "Damage while driving without a valid driving licence for the class of vehicle.",
    "Consequential loss, depreciation, wear and tear, and mechanical or electrical breakdown.",
    "Damage arising from use of the vehicle outside the geographical area stated.",
    "Damage while the vehicle is used for a purpose not permitted by the policy "
    "(hire or reward, racing, speed testing, or carriage of goods against the permit).",
    "Loss or damage arising from war, mutiny, nuclear risk or a similar peril.",
    "Consumables (engine oil, coolant, brake fluid, primer, polish, nuts and bolts and "
    "similar items) unless the Consumables Cover add-on is in force.",
]

CLAIM_PROCEDURE = [
    "Intimate the claim to the insurer immediately, and in any event within 48 hours "
    "of the incident.",
    "Lodge an FIR with the police for theft, third-party injury or death, and for "
    "hit-and-run incidents.",
    "Do not commence repairs before the surveyor's inspection, except to the extent "
    "necessary to move the vehicle to safety.",
    "Submit the claim form, this policy, the registration certificate, the driving "
    "licence of the person driving at the time, and the repair estimate.",
    "A surveyor is appointed for claims above Rs. 50,000 as required by IRDAI.",
]


def _months_between(start: str, end: str) -> str:
    try:
        s = datetime.strptime(start[:10], "%Y-%m-%d")
        e = datetime.strptime(end[:10], "%Y-%m-%d")
        months = round((e - s).days / 30.44)
        return f"{months} months"
    except (TypeError, ValueError):
        return "term as stated"


def build_policy_pdf(row: dict) -> bytes:
    from services import coverage as cov

    policy_no = row["policy_no"]
    add_ons = cov.parse_add_ons(row)
    add_on_labels = cov.add_on_labels(row)
    cover_class = cov.classify_coverage(row)
    is_tp_only = cover_class == cov.COVER_THIRD_PARTY

    try:
        si = int(float(row.get("sum_insured") or 0))
    except (TypeError, ValueError):
        si = 0
    try:
        cc = int(float(row.get("engine_cc") or 0))
    except (TypeError, ValueError):
        cc = 0
    comp_ded = 2000 if cc > 1500 else 1000
    try:
        vol_ded = int(float(row.get("voluntary_deductible") or 0))
    except (TypeError, ValueError):
        vol_ded = 0

    pdf = PolicyPDF(policy_no)
    pdf.alias_nb_pages()

    # ── Page 1 — schedule ────────────────────────────────────────────────────
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "MOTOR INSURANCE POLICY SCHEDULE", align="C",
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*DARK_BLUE)
    pdf.cell(0, 6, _s(f"Policy No.: {policy_no}   |   "
                      f"{(row.get('coverage_type') or 'Comprehensive').upper()}"),
             align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 6, _s(f"POLICY PERIOD: {row.get('policy_start')} to {row.get('policy_end')}  "
                      f"({_months_between(row.get('policy_start'), row.get('policy_end'))})"),
             align="C", new_x="LMARGIN", new_y="NEXT")

    _bar(pdf, "SECTION A  -  POLICYHOLDER INFORMATION")
    _kv(pdf, "Name of Insured", row.get("customer_name"), alt=True)
    _kv(pdf, "Registered Mobile", row.get("phone"))

    _bar(pdf, "SECTION B  -  VEHICLE DETAILS")
    for i, (lbl, val) in enumerate([
        ("Make", row.get("vehicle_make")),
        ("Model", row.get("vehicle_model")),
        ("Registration Number", row.get("vehicle_reg_no")),
        ("Year of Manufacture", row.get("vehicle_year")),
        ("Engine Capacity", f"{cc} cc" if cc else "Electric / not stated"),
        ("Fuel Type", "Electric" if cc == 0 else "Petrol"),
    ]):
        _kv(pdf, lbl, val, alt=(i % 2 == 0))

    _bar(pdf, "SECTION C  -  COVERAGE & PREMIUM SUMMARY")
    rows_c = [("Coverage Type", row.get("coverage_type"))]
    if is_tp_only:
        rows_c.append(("Insured Declared Value (IDV)",
                       "Not applicable - liability-only cover"))
    else:
        rows_c.append(("Insured Declared Value (IDV)", _inr(si)))
    rows_c += [
        ("Total Annual Premium", _inr(row.get("annual_premium"))),
        ("No-Claim Bonus", f"{row.get('ncb_pct') or 0}%"),
        ("Compulsory Deductible", _inr(comp_ded) + " (IRDAI mandate)"),
        ("Voluntary Deductible", _inr(vol_ded)),
    ]
    for i, (lbl, val) in enumerate(rows_c):
        _kv(pdf, lbl, val, alt=(i % 2 == 0))

    _bar(pdf, "SECTION D  -  ADD-ON COVERS")
    if add_on_labels:
        for lbl in add_on_labels:
            _para(pdf, f"  *  {lbl}")
    else:
        _para(pdf, "  No add-on covers are in force under this policy.", italic=True)

    # ── Page 2 — what is covered, deductibles, depreciation ──────────────────
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "COVERAGE DETAILS & CONDITIONS", align="C",
             new_x="LMARGIN", new_y="NEXT")

    if is_tp_only:
        # A liability-only policy must not describe own-damage cover, or the
        # retrieved text contradicts the eligibility gate.
        _bar(pdf, "SCOPE OF COVER  -  THIRD PARTY LIABILITY ONLY")
        _para(pdf,
              "This is a liability-only (Act) policy issued under Section 146 of the Motor "
              "Vehicles Act, 1988. It indemnifies the insured against legal liability to THIRD "
              "PARTIES only.")
        _para(pdf, "")
        _para(pdf, "NOT COVERED: loss of or damage to the insured vehicle itself, from any "
                   "cause whatsoever, including accident, fire, theft and natural perils. "
                   "An own-damage or theft claim is not admissible under this policy.")
        _bar(pdf, "THIRD PARTY LIABILITY (Section II - Mandatory)")
        _kv(pdf, "Third Party Bodily Injury / Death",
            "Unlimited, as awarded by the Motor Accident Claims Tribunal", alt=True)
        _kv(pdf, "Third Party Property Damage", "Up to Rs. 7,50,000 (statutory limit)")
    else:
        _bar(pdf, "OWN DAMAGE COVERAGE (Section I)")
        _kv(pdf, "Accidental Damage", f"Up to IDV ({_inr(si)}) after deductibles", alt=True)
        _kv(pdf, "Fire, Explosion, Self-ignition, Lightning", f"Up to IDV ({_inr(si)})")
        _kv(pdf, "Burglary, Housebreaking, Theft", f"Up to IDV ({_inr(si)})", alt=True)
        _kv(pdf, "Natural Perils (flood, storm, earthquake)", f"Up to IDV ({_inr(si)})")
        _kv(pdf, "Total Loss", "IDV less policy deductibles; the salvage is retained by the "
                               "insurer unless otherwise agreed in writing", alt=True)
        _bar(pdf, "THIRD PARTY LIABILITY (Section II - Mandatory)")
        _kv(pdf, "Third Party Bodily Injury / Death",
            "Unlimited, as awarded by the Motor Accident Claims Tribunal", alt=True)
        _kv(pdf, "Third Party Property Damage", "Up to Rs. 7,50,000 (statutory limit)")

    _bar(pdf, "DEDUCTIBLE SCHEDULE")
    _kv(pdf, "Compulsory Deductible", f"{_inr(comp_ded)} (IRDAI mandate, "
                                      f"{'above' if cc > 1500 else 'up to'} 1500 cc)", alt=True)
    _kv(pdf, "Voluntary Deductible", f"{_inr(vol_ded)} (selected by the insured)")
    _kv(pdf, "Total Deductible Per Claim", _inr(comp_ded + vol_ded), alt=True)

    if not is_tp_only:
        _bar(pdf, "DEPRECIATION SCHEDULE (IRDAI / IMT GR.9  -  per part replaced)")
        for i, (age, pct) in enumerate(DEPRECIATION_ROWS):
            _kv(pdf, age, pct, alt=(i % 2 == 0))
        _para(pdf, "")
        _para(pdf, "Material-wise rates override the age schedule: glass - nil; rubber, nylon, "
                   "plastic parts, tyres, tubes and batteries - 50%; fibre-glass components - 30%.",
              size=7.5, italic=True)

        if cov.ADD_ON_ZERO_DEP in add_ons:
            pdf.ln(1)
            pdf.set_text_color(*RED)
            _para(pdf, "ZERO DEPRECIATION ADD-ON IN FORCE - depreciation is not deducted on "
                       "parts replaced, EXCEPT tyres, tubes and batteries, which remain "
                       "subject to 50% depreciation under the standard add-on exclusion.",
                  size=8)
            pdf.set_text_color(0, 0, 0)

        pdf.ln(1)
        if cov.ADD_ON_CONSUMABLES in add_ons:
            pdf.set_text_color(*RED)
            _para(pdf, "CONSUMABLES COVER IN FORCE - engine oil, coolant, brake fluid, primer, "
                       "polish, nuts, bolts and similar consumables are payable.", size=8)
            pdf.set_text_color(0, 0, 0)
        else:
            _para(pdf, "Consumables are NOT covered under this policy (see Exclusion 7).",
                  size=8, italic=True)

    if cov.ADD_ON_NCB_PROTECT in add_ons:
        pdf.ln(1)
        pdf.set_text_color(*RED)
        _para(pdf, "NCB PROTECT IN FORCE - the No-Claim Bonus is retained at its current slab "
                   "notwithstanding an admitted claim.", size=8)
        pdf.set_text_color(0, 0, 0)

    # ── Page 3 — exclusions and procedure ────────────────────────────────────
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "EXCLUSIONS AND CLAIM PROCEDURE", align="C",
             new_x="LMARGIN", new_y="NEXT")

    _bar(pdf, "SECTION III  -  EXCLUSIONS (what is NOT covered)")
    for i, item in enumerate(EXCLUSIONS, 1):
        _para(pdf, f"{i}.  {item}")
        pdf.ln(0.6)

    _bar(pdf, "SECTION IV  -  CLAIM PROCEDURE")
    for i, item in enumerate(CLAIM_PROCEDURE, 1):
        _para(pdf, f"{i}.  {item}")
        pdf.ln(0.6)

    _bar(pdf, "SECTION V  -  GRIEVANCE REDRESSAL")
    _para(pdf, "A complaint may be made to the insurer's Grievance Officer. If the complaint is "
               "not resolved within 30 days, or the response is unsatisfactory, the insured may "
               "approach the Insurance Ombudsman under the IRDAI grievance-redressal framework.")

    return bytes(pdf.output())


def main() -> int:
    wanted = {a.strip().upper() for a in sys.argv[1:]}
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(POLICIES_CSV, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    from services import coverage as cov

    written = 0
    for row in rows:
        if wanted and row["policy_no"].upper() not in wanted:
            continue
        path = os.path.join(OUT_DIR, f"{row['policy_no']}.pdf")
        with open(path, "wb") as out:
            out.write(build_policy_pdf(row))
        written += 1
        add_ons = ", ".join(cov.add_on_labels(row)) or "none"
        print(f"  {row['policy_no']}  {row['customer_name']:<20.20} "
              f"{row.get('coverage_type', ''):<14} add-ons: {add_ons}")

    print(f"\n{written} policy PDF(s) written to data/kb/policies/")
    print("Rebuild the vectorstore so RAG serves the new text: "
          "python dev/scripts/build_vectorstore.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
