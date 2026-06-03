"""
Generate sample garage estimation slips and FIR reports as PDFs for ClaimIntel testing.

Places generated files directly into the relevant claim directories:
  data/claims/{claim_id}/docs/estimate/
  data/claims/{claim_id}/docs/fir/

Usage:
    python scripts/generate_sample_docs.py                # Generate all
    python scripts/generate_sample_docs.py --estimates    # Estimates only
    python scripts/generate_sample_docs.py --firs         # FIRs only

Run from project root.
"""

import argparse
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

try:
    from fpdf import FPDF
except ImportError:
    print("ERROR: fpdf2 not installed.  Run:  venv\\Scripts\\pip install fpdf2")
    sys.exit(1)

CLAIMS_DIR = os.path.join(PROJECT_ROOT, "data", "claims")


# ── Latin-1 sanitizer ─────────────────────────────────────────────────────────
def _s(text: str) -> str:
    return (str(text)
        .replace("—", " - ").replace("–", "-")
        .replace("‘", "'").replace("’", "'")
        .replace("“", '"').replace("”", '"')
        .replace("•", "-").replace("₹", "Rs.").replace("✓", "OK")
    )


# ── Garage Estimate data ──────────────────────────────────────────────────────
ESTIMATES = [
    {
        "filename": "EST-Rajesh-Kumar-Swift-Dzire.pdf",
        "claim_id": "CLM-2025-05-000001",
        "job_card": "JC-BLR-2025-4821",
        "job_date": "13 May 2025",
        "workshop": {
            "name": "Vijayanagar Auto Works Pvt. Ltd.",
            "address": "No. 14, 2nd Cross, HSR Layout Sector 2, Bengaluru - 560102",
            "gstin": "29AABCV1234F1Z5",
            "phone": "080-40221345",
            "email": "vjnagar.auto@gmail.com",
            "authorised": "Maruti Suzuki Authorised Service Partner",
        },
        "customer": {
            "name": "Rajesh Kumar",
            "vehicle": "Maruti Suzuki Swift Dzire VXI",
            "reg_no": "KA-01-MN-2345",
            "mileage": "41,230 km",
            "insurance": "Ganit Motors Insurance / POL-784512",
        },
        "items": [
            {"part": "Front Bumper Assembly (OEM)", "type": "Replace", "qty": 1, "unit": 8500, "source": "OEM"},
            {"part": "Bonnet Panel", "type": "Repair + Paint", "qty": 1, "unit": 12000, "source": "OEM"},
            {"part": "Front Grille (OEM)", "type": "Replace", "qty": 1, "unit": 3200, "source": "OEM"},
            {"part": "Headlight Assembly LH (OEM)", "type": "Replace", "qty": 1, "unit": 6800, "source": "OEM"},
            {"part": "Front Underbody Spoiler", "type": "Replace", "qty": 1, "unit": 1800, "source": "Aftermarket"},
            {"part": "Labour - Panel Beating & Denting", "type": "Labour", "qty": 1, "unit": 4500, "source": "-"},
            {"part": "Labour - Painting (2-coat oven finish)", "type": "Labour", "qty": 1, "unit": 3500, "source": "-"},
        ],
        "note": "Genuine front-end impact damage. All parts OEM wherever possible. Repair matches damage survey.",
        "is_fraud": False,
    },
    {
        "filename": "EST-Mohammed-Faiz-Innova-INFLATED.pdf",
        "claim_id": "CLM-2025-05-000002",
        "job_card": "JC-CHN-2025-1109",
        "job_date": "20 May 2025",
        "workshop": {
            "name": "Sri Rama Auto Repair Works",
            "address": "Plot 7-B, SIDCO Industrial Area, Ambattur, Chennai - 600098",
            "gstin": "33ZZZZR9999X1Z1",
            "phone": "044-26781234",
            "email": "srirama.auto@yahoo.com",
            "authorised": "Multi-Brand Workshop (Non-Empanelled)",
        },
        "customer": {
            "name": "Mohammed Faiz",
            "vehicle": "Toyota Innova Crysta GX 2.4 Diesel",
            "reg_no": "TN-07-CD-5678",
            "mileage": "28,540 km",
            "insurance": "Ganit Motors Insurance / POL-891234",
        },
        "items": [
            # Inflated prices — front doors should be ~14-16k OEM, quoted at 28k
            {"part": "Left Front Door Skin + Inner Panel (OEM)", "type": "Replace", "qty": 1, "unit": 28000, "source": "OEM"},
            {"part": "Left Rear Door Assembly (OEM)", "type": "Replace", "qty": 1, "unit": 26500, "source": "OEM"},
            {"part": "Rear Bumper (OEM)", "type": "Replace + Paint", "qty": 1, "unit": 18000, "source": "OEM"},
            {"part": "Left Rear Quarter Panel", "type": "Repair + Paint", "qty": 1, "unit": 22000, "source": "OEM"},
            {"part": "Left ORVM (OEM)", "type": "Replace", "qty": 1, "unit": 5500, "source": "OEM"},
            {"part": "Running Board LH (OEM)", "type": "Replace", "qty": 1, "unit": 8200, "source": "OEM"},
            {"part": "Labour - Panel Beating & Alignment", "type": "Labour", "qty": 1, "unit": 12000, "source": "-"},
            {"part": "Labour - Full Body Paint Blend", "type": "Labour", "qty": 1, "unit": 10000, "source": "-"},
            {"part": "Consumables (Primer, Polish, Masking)", "type": "Material", "qty": 1, "unit": 4800, "source": "-"},
        ],
        "note": "WARNING (for demo): This estimate is intentionally inflated by approx 70%+ above OEM rates. Not an empanelled workshop. Refer to fraud screening.",
        "is_fraud": True,
    },
    {
        "filename": "EST-Priya-Sharma-Honda-City.pdf",
        "claim_id": "CLM-2025-05-000003",
        "job_card": "JC-MUM-2025-7734",
        "job_date": "22 May 2025",
        "workshop": {
            "name": "K J Auto Service Center Pvt. Ltd.",
            "address": "Shop 4, Linking Road Service Lane, Bandra West, Mumbai - 400050",
            "gstin": "27AABCK5678G1Z3",
            "phone": "022-26521890",
            "email": "kjservice.bandra@hotmail.com",
            "authorised": "Honda Authorised Service Centre",
        },
        "customer": {
            "name": "Priya Sharma",
            "vehicle": "Honda City ZX CVT Petrol",
            "reg_no": "MH-02-AB-1234",
            "mileage": "22,115 km",
            "insurance": "Ganit Motors Insurance / POL-234567",
        },
        "items": [
            {"part": "Rear Bumper Assembly (OEM)", "type": "Replace", "qty": 1, "unit": 9800, "source": "OEM"},
            {"part": "Boot Lid (Tailgate Panel)", "type": "Repair + Paint", "qty": 1, "unit": 18500, "source": "OEM"},
            {"part": "Boot Lid Garnish (OEM)", "type": "Replace", "qty": 1, "unit": 3400, "source": "OEM"},
            {"part": "Rear Lamp Cluster RH (OEM)", "type": "Replace", "qty": 1, "unit": 6800, "source": "OEM"},
            {"part": "Rear Lamp Cluster LH (OEM)", "type": "Replace", "qty": 1, "unit": 6800, "source": "OEM"},
            {"part": "Rear Bumper Bracket & Clips", "type": "Replace", "qty": 1, "unit": 1200, "source": "OEM"},
            {"part": "Labour - Denting & Panel Work", "type": "Labour", "qty": 1, "unit": 5500, "source": "-"},
            {"part": "Labour - Painting & Polishing", "type": "Labour", "qty": 1, "unit": 3500, "source": "-"},
        ],
        "note": "Rear impact damage from stationary collision with truck. All repairs at OEM rate. Vehicle retained for 3 working days.",
        "is_fraud": False,
    },
    {
        "filename": "EST-Arjun-Mehta-Hyundai-Creta.pdf",
        "claim_id": "CLM-2026-05-000003",
        "job_card": "JC-CHN-2026-3301",
        "job_date": "21 May 2026",
        "workshop": {
            "name": "Hyundai Exclusive Service - Perungudi",
            "address": "12-A, OMR Old Mahabalipuram Rd, Perungudi, Chennai - 600096",
            "gstin": "33AABHH2345K1Z8",
            "phone": "044-40123456",
            "email": "hmsiexclusive.perungudi@hyundai.co.in",
            "authorised": "Hyundai Motor India Authorised Dealer Workshop",
        },
        "customer": {
            "name": "Arjun Mehta",
            "vehicle": "Hyundai Creta SX Turbo",
            "reg_no": "DL-05-XY-9876",
            "mileage": "18,765 km",
            "insurance": "Ganit Motors Insurance / POL-567890",
        },
        "items": [
            {"part": "Tailgate Outer Panel - Dent Repair", "type": "Repair + Paint", "qty": 1, "unit": 4500, "source": "OEM"},
            {"part": "Rear Bumper Lower Touch-up Paint", "type": "Paint", "qty": 1, "unit": 1800, "source": "OEM"},
            {"part": "Boot Lamp Lens Cover (OEM)", "type": "Replace", "qty": 1, "unit": 950, "source": "OEM"},
            {"part": "Labour - Minor Panel Beating", "type": "Labour", "qty": 1, "unit": 1500, "source": "-"},
            {"part": "Labour - Spot Painting", "type": "Labour", "qty": 1, "unit": 800, "source": "-"},
        ],
        "note": "Minor parking damage to tailgate. Very limited scope of work. Vehicle ready same day.",
        "is_fraud": False,
    },
    {
        "filename": "EST-Pooja-Nambiar-Renault-Kwid.pdf",
        "claim_id": "CLM-2026-05-000004",
        "job_card": "JC-CHN-2026-8812",
        "job_date": "27 May 2026",
        "workshop": {
            "name": "Chennai Multi-Brand Auto Repairs",
            "address": "Survey No. 45, ECR Kelabakkam, Chennai - 603103",
            "gstin": "33AAXCM6789P1Z2",
            "phone": "044-27654321",
            "email": "cmbar.kelabakkam@gmail.com",
            "authorised": "Multi-Brand Workshop",
        },
        "customer": {
            "name": "Pooja Nambiar",
            "vehicle": "Renault Kwid RXT 1.0 SCe",
            "reg_no": "KL-07-XY-9012",
            "mileage": "32,480 km",
            "insurance": "Ganit Motors Insurance / POL-223344",
        },
        "items": [
            {"part": "Rear Bumper Assembly (OEM)", "type": "Replace", "qty": 1, "unit": 12000, "source": "OEM"},
            {"part": "Trunk Lid / Dicky Door", "type": "Repair + Paint", "qty": 1, "unit": 18000, "source": "OEM"},
            {"part": "Rear Combination Lamp LH (OEM)", "type": "Replace", "qty": 1, "unit": 5500, "source": "OEM"},
            {"part": "Rear Combination Lamp RH (OEM)", "type": "Replace", "qty": 1, "unit": 5500, "source": "OEM"},
            {"part": "Wheel Arch Liner Rear", "type": "Repair", "qty": 1, "unit": 3500, "source": "Aftermarket"},
            {"part": "Rear Number Plate Bracket", "type": "Replace", "qty": 1, "unit": 800, "source": "Aftermarket"},
            {"part": "Labour - Body Repair", "type": "Labour", "qty": 1, "unit": 8000, "source": "-"},
            {"part": "Labour - Paint & Polish", "type": "Labour", "qty": 1, "unit": 4000, "source": "-"},
        ],
        "note": "Rear impact while parked. Scope matches customer complaint. Parts sourced locally for Kwid.",
        "is_fraud": False,
    },
]

# ── FIR data ──────────────────────────────────────────────────────────────────
FIRS = [
    {
        "filename": "FIR-Priya-Sharma-Honda-City.pdf",
        "claim_id": "CLM-2025-05-000003",
        "fir_no": "0245 / 2025",
        "district": "Mumbai Suburban",
        "police_station": "Bandra Police Station, H Division",
        "ps_address": "Bandra PS, Dr. Ambedkar Road, Bandra West, Mumbai - 400050",
        "date_filed": "21 May 2025",
        "date_filed_time": "11:30 hrs",
        "incident_date": "20 May 2025",
        "incident_time": "17:15 hrs",
        "incident_location": "Turner Road, near Bandra Station, Bandra West, Mumbai",
        "complainant": {
            "name": "Priya Sharma",
            "father": "Ramesh Sharma",
            "address": "15, Indiranagar 12th Main, Bengaluru - 560038 (Temporary: Flat 3B, Sharma Residency, Bandra West, Mumbai - 400050)",
            "phone": "9845012345",
            "occupation": "Software Engineer",
        },
        "vehicle": {"reg": "MH-02-AB-1234", "make": "Honda City ZX CVT", "colour": "Meteoroid Gray"},
        "accused_vehicle": "Unidentified Heavy Goods Vehicle (Truck) - Maharashtra registration, dark blue, partial plate MH 04 visible",
        "statement": (
            "The complainant states that on 20th May 2025 at approximately 17:15 hours she was "
            "driving her vehicle Honda City (MH-02-AB-1234) on Turner Road, Bandra West, Mumbai, "
            "and was stationary at a red traffic signal near Bandra Railway Station. "
            "At that time an unidentified truck coming from behind failed to stop in time "
            "and struck the rear of her vehicle with considerable force. The truck driver did not "
            "stop and fled the scene immediately. The complainant's vehicle sustained significant "
            "damage to the rear bumper, boot lid, and rear light clusters. No persons were "
            "physically injured. The complainant requests registration of FIR and appropriate "
            "action against the unidentified driver."
        ),
        "action": "Case registered under Sections 279, 338 IPC and Motor Vehicles Act 1988. Vehicle inspected at scene. Witness statements recorded from 2 bystanders (names on record).",
        "officer": "Sub-Inspector Satish Patil, Badge No. M-2341",
        "station_note": "Vehicle not seized. Complainant advised to produce RC, DL, and insurance documents.",
        "is_fraud": False,
    },
    {
        "filename": "FIR-Mohammed-Faiz-Innova-MISMATCH.pdf",
        "claim_id": "CLM-2025-05-000002",
        "fir_no": "1142 / 2025",
        "district": "Chennai (City)",
        "police_station": "Anna Nagar East Police Station",
        "ps_address": "Anna Nagar East PS, 7th Avenue, Anna Nagar, Chennai - 600040",
        "date_filed": "21 May 2025",
        "date_filed_time": "09:45 hrs",
        # NOTE: FIR says incident on 15 May — claim says 18 May (3-day mismatch — FRAUD SIGNAL)
        "incident_date": "15 May 2025",
        "incident_time": "23:30 hrs",
        # NOTE: FIR says OMR Road — claim says Outer Ring Road (location mismatch — FRAUD SIGNAL)
        "incident_location": "Old Mahabalipuram Road (OMR), near Sholinganallur IT Park, Chennai",
        "complainant": {
            "name": "Mohammed Faiz",
            "father": "Abdul Faiz",
            "address": "8, RT Nagar Main Road, Bengaluru - 560032",
            "phone": "9988776655",
            "occupation": "Business",
        },
        # NOTE: Vehicle reg in FIR is DIFFERENT from policy (TN07GH1234 vs TN07CD5678 — FRAUD SIGNAL)
        "vehicle": {"reg": "TN-07-GH-1234", "make": "Toyota Innova Crysta", "colour": "White"},
        "accused_vehicle": "Unknown vehicle - fled scene",
        "statement": (
            "The complainant states that on 15th May 2025 at approximately 23:30 hours his vehicle "
            "Toyota Innova (TN-07-GH-1234) was parked on the service lane of OMR Road near "
            "Sholinganallur when an unknown vehicle struck it from the side and fled. "
            "The complainant discovered the damage the following morning. He states no witnesses "
            "were present at the time of the incident. The vehicle sustained damage to the left "
            "side doors and rear panel. The complainant requests registration of FIR."
        ),
        "action": "Case registered. Vehicle not at scene during verification visit. FIR recorded based on complainant statement alone.",
        "officer": "Head Constable Murugan R., Badge No. C-7821",
        "station_note": "Note: Vehicle not produced for inspection at time of FIR filing. RC and insurance papers submitted by complainant photocopies only.",
        "is_fraud": True,
    },
    {
        "filename": "FIR-Arjun-Mehta-Hyundai-Creta.pdf",
        "claim_id": "CLM-2026-05-000003",
        "fir_no": "0378 / 2026",
        "district": "Kancheepuram",
        "police_station": "Perungudi Traffic Police Station",
        "ps_address": "Perungudi PS, 100 Feet Road, Perungudi, Chennai - 600096",
        "date_filed": "19 May 2026",
        "date_filed_time": "17:45 hrs",
        "incident_date": "19 May 2026",
        "incident_time": "16:30 hrs",
        "incident_location": "Near Ramanujan IT City Parking, Perungudi, Chennai",
        "complainant": {
            "name": "Arjun Mehta",
            "father": "Suresh Mehta",
            "address": "23, Whitefield Main Road, Bengaluru - 560066",
            "phone": "9900112233",
            "occupation": "IT Professional",
        },
        "vehicle": {"reg": "DL-05-XY-9876", "make": "Hyundai Creta SX Turbo", "colour": "Typhoon Silver"},
        "accused_vehicle": "Unidentified white hatchback, partial Tamil Nadu registration",
        "statement": (
            "The complainant states that on 19th May 2026 at approximately 16:30 hours his "
            "vehicle Hyundai Creta (DL-05-XY-9876) was parked in the designated parking area "
            "near Ramanujan IT City, Perungudi, Chennai. Upon returning from his office at "
            "approximately 16:30 hours he noticed fresh damage to the tailgate and rear bumper "
            "of his vehicle consistent with a low-speed rear impact. A bystander security guard "
            "(name on record) confirmed seeing a white hatchback reverse into the vehicle and "
            "leave without stopping. CCTV footage from the parking area requested but not yet "
            "retrieved at time of FIR filing."
        ),
        "action": "Case registered under Section 279 IPC. CCTV footage requisition sent to Ramanujan IT City security. Vehicle inspected on-site. Damage consistent with statement.",
        "officer": "Sub-Inspector Karunakaran P., Badge No. T-5512",
        "station_note": "Vehicle RC, DL, and insurance documents verified originals. Damage assessment photographs taken at scene.",
        "is_fraud": False,
    },
]


# ── PDF Classes ───────────────────────────────────────────────────────────────

class EstimatePDF(FPDF):
    def __init__(self, data: dict):
        super().__init__()
        self.data = data
        self.set_margins(15, 22, 15)
        self.set_auto_page_break(auto=True, margin=20)

    def header(self):
        ws = self.data["workshop"]
        # Colored header band
        self.set_fill_color(16, 78, 139)
        self.rect(0, 0, 210, 22, 'F')
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(255, 255, 255)
        self.set_y(4)
        self.cell(0, 7, _s(ws["name"]), align="C", ln=True)
        self.set_font("Helvetica", "", 8)
        self.cell(0, 5, _s(f"{ws['address']}  |  Ph: {ws['phone']}  |  GSTIN: {ws['gstin']}"), align="C", ln=True)
        self.set_text_color(0, 0, 0)
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(120, 120, 120)
        ws = self.data["workshop"]
        self.cell(0, 5, _s(f"{ws['authorised']}  |  Page {self.page_no()}  |  E&OE - Subject to Workshop Terms & Conditions"), align="C")
        self.set_text_color(0, 0, 0)


class FIRPDF(FPDF):
    def __init__(self, data: dict):
        super().__init__()
        self.data = data
        self.set_margins(18, 22, 18)
        self.set_auto_page_break(auto=True, margin=20)

    def header(self):
        # Government header style
        self.set_fill_color(0, 84, 42)   # dark green (police)
        self.rect(0, 0, 210, 22, 'F')
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(255, 255, 255)
        self.set_y(4)
        self.cell(0, 6, "GOVERNMENT OF INDIA - INDIAN POLICE SERVICE", align="C", ln=True)
        self.set_font("Helvetica", "", 8)
        d = self.data
        self.cell(0, 5, _s(f"District: {d['district']}  |  {d['police_station']}"), align="C", ln=True)
        self.set_text_color(0, 0, 0)
        self.ln(3)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(120, 120, 120)
        self.cell(0, 5, _s(f"FIR No. {self.data['fir_no']}  |  {self.data['police_station']}  |  Page {self.page_no()}  |  Official Document - Not for Commercial Use"), align="C")
        self.set_text_color(0, 0, 0)


# ── PDF generators ────────────────────────────────────────────────────────────

def generate_estimate(data: dict, output_path: str):
    pdf = EstimatePDF(data)
    pdf.add_page()

    # Title box
    pdf.set_fill_color(232, 244, 255)
    pdf.rect(15, 26, 180, 12, 'F')
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(16, 78, 139)
    pdf.set_y(28)
    pdf.cell(0, 8, "VEHICLE REPAIR ESTIMATION SLIP", align="C", ln=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    # Two-column header: Job Card No + Date
    ws = data["workshop"]
    pdf.set_fill_color(245, 245, 245)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(90, 7, _s(f"Job Card No.:  {data['job_card']}"), fill=True, border=1, ln=False)
    pdf.cell(90, 7, _s(f"Date:  {data['job_date']}"), fill=True, border=1, ln=True)
    pdf.ln(3)

    # Customer & Vehicle details box
    cust = data["customer"]
    pdf.set_fill_color(250, 250, 252)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(30, 58, 138)
    pdf.cell(0, 7, "  CUSTOMER & VEHICLE DETAILS", fill=True, ln=True)
    pdf.set_text_color(0, 0, 0)

    def kv(k, v, w_k=55, w_v=125):
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(80, 80, 80)
        pdf.cell(w_k, 6, _s(k) + ":", ln=False, border="B")
        pdf.set_text_color(20, 20, 20)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(w_v, 6, _s(str(v)), ln=True, border="B")
        pdf.set_text_color(0, 0, 0)

    kv("Customer Name", cust["name"])
    kv("Vehicle", cust["vehicle"])
    kv("Registration No.", cust["reg_no"])
    kv("Odometer Reading", cust["mileage"])
    kv("Insurance / Policy No.", cust["insurance"])
    pdf.ln(4)

    # Line items table header
    pdf.set_fill_color(16, 78, 139)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(8, 7, "#", fill=True, border=1, align="C", ln=False)
    pdf.cell(77, 7, "Part / Service Description", fill=True, border=1, ln=False)
    pdf.cell(24, 7, "Work Type", fill=True, border=1, ln=False)
    pdf.cell(10, 7, "Qty", fill=True, border=1, align="C", ln=False)
    pdf.cell(24, 7, "Source", fill=True, border=1, align="C", ln=False)
    pdf.cell(27, 7, "Amount (Rs.)", fill=True, border=1, align="R", ln=True)
    pdf.set_text_color(0, 0, 0)

    subtotal = 0
    for i, item in enumerate(data["items"], 1):
        pdf.set_font("Helvetica", "", 8.5)
        fill = (i % 2 == 0)
        pdf.set_fill_color(247, 249, 255) if fill else pdf.set_fill_color(255, 255, 255)
        pdf.cell(8, 6.5, str(i), fill=fill, border=1, align="C", ln=False)
        pdf.cell(77, 6.5, _s(item["part"]), fill=fill, border=1, ln=False)
        pdf.cell(24, 6.5, _s(item["type"]), fill=fill, border=1, ln=False)
        pdf.cell(10, 6.5, str(item["qty"]), fill=fill, border=1, align="C", ln=False)
        pdf.cell(24, 6.5, item["source"], fill=fill, border=1, align="C", ln=False)
        amount = item["qty"] * item["unit"]
        pdf.cell(27, 6.5, f"{amount:,}", fill=fill, border=1, align="R", ln=True)
        subtotal += amount

    # Totals section
    pdf.ln(2)
    cgst = round(subtotal * 0.09)
    sgst = round(subtotal * 0.09)
    total = subtotal + cgst + sgst

    def total_row(label, amount, bold=False):
        pdf.set_font("Helvetica", "B" if bold else "", 9)
        w = 30
        pdf.cell(170 - w, 6.5, "", ln=False)
        if bold:
            pdf.set_fill_color(232, 244, 255)
            pdf.cell(w, 6.5, _s(label), fill=True, border=1, ln=False)
            pdf.cell(0, 6.5, _s(f"Rs. {amount:,}"), fill=True, border=1, align="R", ln=True)
        else:
            pdf.cell(w, 6.5, _s(label), border=1, ln=False)
            pdf.cell(0, 6.5, _s(f"Rs. {amount:,}"), border=1, align="R", ln=True)

    total_row("Sub-Total", subtotal)
    total_row("CGST @ 9%", cgst)
    total_row("SGST @ 9%", sgst)
    total_row("GRAND TOTAL", total, bold=True)

    pdf.ln(4)
    # Note
    if data.get("note"):
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(90, 90, 90)
        pdf.multi_cell(0, 5.5, _s(f"Note: {data['note']}"))
        pdf.set_text_color(0, 0, 0)

    pdf.ln(6)
    # Signature lines
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(90, 5, "Customer Signature: ______________________", ln=False)
    pdf.cell(90, 5, "Authorised Signatory: ______________________", ln=True)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(90, 5, f"({cust['name']})", ln=False)
    pdf.cell(90, 5, _s(f"({ws['name']})"), ln=True)
    pdf.set_text_color(0, 0, 0)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    pdf.output(output_path)
    return output_path, total


def generate_fir(data: dict, output_path: str):
    pdf = FIRPDF(data)
    pdf.add_page()

    # Title
    pdf.set_fill_color(240, 247, 240)
    pdf.rect(18, 27, 174, 11, 'F')
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(0, 84, 42)
    pdf.set_y(29)
    pdf.cell(0, 7, "FIRST INFORMATION REPORT (FIR)", align="C", ln=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)

    # FIR header box: No / Year / PS
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(240, 247, 240)
    pdf.cell(58, 7, _s(f"FIR No.:  {data['fir_no']}"), border=1, fill=True, ln=False)
    pdf.cell(58, 7, _s(f"Police Station:  {data['police_station'].split(',')[0]}"), border=1, fill=True, ln=False)
    pdf.cell(58, 7, _s(f"Date & Time Filed:  {data['date_filed']}  {data['date_filed_time']}"), border=1, fill=True, ln=True)
    pdf.ln(3)

    def section(title: str):
        pdf.ln(2)
        pdf.set_fill_color(0, 84, 42)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(0, 7, _s(f"  {title}"), fill=True, ln=True)
        pdf.set_text_color(0, 0, 0)
        pdf.ln(1)

    CONTENT_W = 174  # 210 - 18(L) - 18(R)

    def fkv(k, v, w_k=60):
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(80, 80, 80)
        pdf.cell(w_k, 6, _s(k) + ":", ln=False)
        pdf.set_text_color(20, 20, 20)
        pdf.set_font("Helvetica", "B", 9)
        pdf.multi_cell(CONTENT_W - w_k, 6, _s(str(v)))
        pdf.set_text_color(0, 0, 0)

    # Section 1: Complainant
    section("SECTION 1 — COMPLAINANT INFORMATION")
    comp = data["complainant"]
    fkv("Name of Complainant", comp["name"])
    fkv("Father's / Husband's Name", comp["father"])
    fkv("Address", comp["address"])
    fkv("Mobile Number", comp["phone"])
    fkv("Occupation", comp["occupation"])

    # Section 2: Incident Details
    section("SECTION 2 — INCIDENT DETAILS")
    fkv("Date of Incident", data["incident_date"])
    fkv("Time of Incident", data["incident_time"])
    fkv("Place / Location of Incident", data["incident_location"])
    fkv("Nature of Incident", "Motor Vehicle Accident — Hit and Run / Damage to Property")

    # Section 3: Vehicle
    section("SECTION 3 — VEHICLE DETAILS")
    v = data["vehicle"]
    fkv("Registration Number", v["reg"])
    fkv("Make / Model", v["make"])
    fkv("Colour", v["colour"])
    fkv("Accused / Offending Vehicle", data["accused_vehicle"])

    # Section 4: Statement
    section("SECTION 4 — STATEMENT OF FACTS")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(30, 30, 30)
    pdf.multi_cell(0, 5.5, _s(data["statement"]))
    pdf.set_text_color(0, 0, 0)

    # Section 5: Action & Notes
    section("SECTION 5 — ACTION TAKEN / NOTES")
    fkv("Action Taken", data["action"])
    fkv("Station Note", data["station_note"])
    fkv("Investigating Officer", data["officer"])

    # Mismatch warning for demo
    if data.get("is_fraud"):
        pdf.ln(4)
        pdf.set_fill_color(255, 240, 240)
        pdf.set_draw_color(200, 0, 0)
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(180, 0, 0)
        pdf.multi_cell(0, 6, _s(
            "[FOR DEMO PURPOSES ONLY] "
            "This FIR contains intentional mismatches for fraud detection testing: "
            "(1) Incident date in FIR is 15 May 2025 but claim states 18 May 2025 (3-day mismatch). "
            "(2) Location in FIR is OMR Road but claim states Outer Ring Road. "
            "(3) Vehicle reg in FIR is TN-07-GH-1234 but policy vehicle is TN-07-CD-5678."
        ), border=1)
        pdf.set_text_color(0, 0, 0)
        pdf.set_draw_color(0, 0, 0)

    pdf.ln(8)
    # Signatures
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(87, 5, "Complainant Signature: ______________________", ln=False)
    pdf.cell(87, 5, "Station Officer Signature & Stamp: ____________", ln=True)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(87, 5, _s(f"({comp['name']})"), ln=False)
    pdf.cell(87, 5, _s(f"({data['officer'].split(',')[0]})"), ln=True)
    pdf.set_text_color(0, 0, 0)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    pdf.output(output_path)
    return output_path


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate sample estimation slips and FIR PDFs for ClaimIntel.")
    parser.add_argument("--estimates", action="store_true", help="Generate estimate PDFs only")
    parser.add_argument("--firs", action="store_true", help="Generate FIR PDFs only")
    args = parser.parse_args()

    do_estimates = args.estimates or (not args.estimates and not args.firs)
    do_firs = args.firs or (not args.estimates and not args.firs)

    if do_estimates:
        print("\n--- Generating Garage Estimation Slips ---")
        for est in ESTIMATES:
            out = os.path.join(CLAIMS_DIR, est["claim_id"], "docs", "estimate", est["filename"])
            _, total = generate_estimate(est, out)
            fraud_tag = " [INFLATED - FRAUD DEMO]" if est["is_fraud"] else ""
            print(f"  OK  {est['claim_id']} / {est['filename']}  ->  Total Rs. {total:,}{fraud_tag}")

    if do_firs:
        print("\n--- Generating FIR Reports ---")
        for fir in FIRS:
            out = os.path.join(CLAIMS_DIR, fir["claim_id"], "docs", "fir", fir["filename"])
            generate_fir(fir, out)
            fraud_tag = " [MISMATCHED - FRAUD DEMO]" if fir["is_fraud"] else ""
            print(f"  OK  {fir['claim_id']} / {fir['filename']}{fraud_tag}")

    print(f"\nDone. PDFs written to data/claims/{{claim_id}}/docs/{{estimate|fir}}/")
    print("Run investigations to see the cross-checks in action.")


if __name__ == "__main__":
    main()
