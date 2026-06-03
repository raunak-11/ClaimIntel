"""
Generate synthetic motor insurance policy PDFs for ClaimIntel knowledge base.

Usage:
    python scripts/generate_policy_pdfs.py                 # Generate all 5 policies
    python scripts/generate_policy_pdfs.py --policy POL-784512  # Single policy
    python scripts/generate_policy_pdfs.py --output-dir custom/path

Run from project root.
"""

import argparse
import os
import sys
from datetime import date, timedelta

# ---------------------------------------------------------------------------
# Ensure project root on path so we can import config
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

try:
    from fpdf import FPDF
except ImportError:
    print("ERROR: fpdf2 not installed. Run:  venv\\Scripts\\pip install fpdf2")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Policy data definitions
# ---------------------------------------------------------------------------
POLICIES = [
    {
        "policy_no": "POL-784512",
        "insured_name": "Rajesh Kumar",
        "phone": "9876543210",
        "address": "42, MG Road, Koramangala, Bangalore — 560034",
        "dob": "15/06/1985",
        "vehicle_make": "Maruti Suzuki",
        "vehicle_model": "Swift Dzire VXI",
        "registration_no": "KA-01-MK-7845",
        "chassis_no": "MA3FJEB1S00123456",
        "engine_no": "K12MN1234567",
        "year_of_manufacture": 2020,
        "fuel_type": "Petrol",
        "colour": "Pearl Arctic White",
        "coverage_type": "Comprehensive",
        "idv": 650000,
        "od_premium": 14200,
        "tp_premium": 3478,
        "total_premium": 18500,
        "policy_start": "2024-04-01",
        "policy_end": "2025-03-31",
        "ncb_percent": 20,
        "voluntary_deductible": 2500,
        "add_ons": ["Zero Depreciation", "Roadside Assistance", "Engine Protection"],
        "nominee": "Sunita Kumar",
        "prior_claims": 0,
        "notes": "Long-standing customer. Clean driving record. NCB applicable.",
    },
    {
        "policy_no": "POL-234567",
        "insured_name": "Priya Sharma",
        "phone": "9845012345",
        "address": "15, Indiranagar 12th Main, Bangalore — 560038",
        "dob": "22/09/1990",
        "vehicle_make": "Honda",
        "vehicle_model": "City ZX CVT",
        "registration_no": "KA-03-NG-2345",
        "chassis_no": "MAKGM5530NH000234",
        "engine_no": "L15Z71234567",
        "year_of_manufacture": 2023,
        "fuel_type": "Petrol",
        "colour": "Meteoroid Gray Metallic",
        "coverage_type": "Comprehensive",
        "idv": 1200000,
        "od_premium": 26500,
        "tp_premium": 5500,
        "total_premium": 32000,
        "policy_start": "2024-01-15",
        "policy_end": "2025-01-14",
        "ncb_percent": 0,
        "voluntary_deductible": 5000,
        "add_ons": ["Zero Depreciation", "Return to Invoice", "Key Replacement", "Personal Accident Cover ₹15L"],
        "nominee": "Ramesh Sharma",
        "prior_claims": 0,
        "notes": "New-to-brand customer. No prior claims.",
    },
    {
        "policy_no": "POL-891234",
        "insured_name": "Mohammed Faiz",
        "phone": "9988776655",
        "address": "8, RT Nagar Main Road, Bangalore — 560032",
        "dob": "10/03/1988",
        "vehicle_make": "Toyota",
        "vehicle_model": "Innova Crysta GX 2.4",
        "registration_no": "KA-04-HB-8912",
        "chassis_no": "MBJFZ29GXP4008912",
        "engine_no": "2GD5654321",
        "year_of_manufacture": 2019,
        "fuel_type": "Diesel",
        "colour": "Avant-Garde Bronze",
        "coverage_type": "Comprehensive",
        "idv": 1600000,
        "od_premium": 39800,
        "tp_premium": 8200,
        "total_premium": 48000,
        "policy_start": "2025-04-10",   # NEW POLICY — fraud indicator
        "policy_end": "2026-04-09",
        "ncb_percent": 0,
        "voluntary_deductible": 2500,
        "add_ons": ["Roadside Assistance"],
        "nominee": "Fatima Faiz",
        "prior_claims": 0,
        "notes": "Policy issued 10-Apr-2025. First policy with us. No pre-inception vehicle survey conducted as IDV below survey threshold at time of issue.",
    },
    {
        "policy_no": "POL-345678",
        "insured_name": "Kavitha Reddy",
        "phone": "9123456789",
        "address": "77, Jayanagar 4th Block, Bangalore — 560041",
        "dob": "05/12/1992",
        "vehicle_make": "Tata",
        "vehicle_model": "Nexon EV Max Long Range",
        "registration_no": "KA-05-EF-3456",
        "chassis_no": "MAT608651NB345678",
        "engine_no": "EV-TRQ8765432",
        "year_of_manufacture": 2023,
        "fuel_type": "Electric",
        "colour": "Flame Red",
        "coverage_type": "Comprehensive (EV Specialised)",
        "idv": 1500000,
        "od_premium": 30200,
        "tp_premium": 7800,
        "total_premium": 38000,
        "policy_start": "2023-08-20",
        "policy_end": "2024-08-19",
        "ncb_percent": 0,
        "voluntary_deductible": 5000,
        "add_ons": ["Zero Depreciation", "Battery Guard (up to ₹8,50,000)", "Roadside Assistance 24x7", "Charging Equipment Cover"],
        "nominee": "Venkateswara Reddy",
        "prior_claims": 0,
        "notes": "EV policy. Battery Guard add-on covers battery pack replacement up to ₹8,50,000 per incident. HV safety protocol surcharge applies to all EV claims.",
    },
    {
        "policy_no": "POL-567890",
        "insured_name": "Arjun Mehta",
        "phone": "9900112233",
        "address": "23, Whitefield Main Road, Bangalore — 560066",
        "dob": "30/07/1982",
        "vehicle_make": "Hyundai",
        "vehicle_model": "Creta SX(O) Turbo",
        "registration_no": "KA-53-MQ-5678",
        "chassis_no": "MALAM51BLNM567890",
        "engine_no": "G4FJN8765432",
        "year_of_manufacture": 2022,
        "fuel_type": "Petrol",
        "colour": "Typhoon Silver",
        "coverage_type": "Comprehensive",
        "idv": 1400000,
        "od_premium": 28600,
        "tp_premium": 6400,
        "total_premium": 35000,
        "policy_start": "2024-06-01",
        "policy_end": "2025-05-31",
        "ncb_percent": 25,
        "voluntary_deductible": 3000,
        "add_ons": ["Zero Depreciation", "Consumables Cover", "Tyre Protection", "Personal Accident Cover Rs.20L"],
        "nominee": "Deepa Mehta",
        "prior_claims": 1,
        "notes": "1 prior claim in 2023 (minor dent, Rs.18,000). NCB partially retained.",
    },
    # ── 10 new customers ──────────────────────────────────────────────────────
    {
        "policy_no": "POL-112233",
        "insured_name": "Aditya Nair",
        "phone": "9567890123",
        "address": "14, Palarivattom Junction, Ernakulam, Kochi - 682025",
        "dob": "03/11/1991",
        "vehicle_make": "Kia",
        "vehicle_model": "Seltos HTX Plus",
        "registration_no": "KL-14-BC-7890",
        "chassis_no": "KNAGC4134N7123456",
        "engine_no": "G4FGE5012345",
        "year_of_manufacture": 2022,
        "fuel_type": "Petrol",
        "colour": "Glacier White Pearl",
        "coverage_type": "Comprehensive",
        "idv": 950000,
        "od_premium": 19500,
        "tp_premium": 5500,
        "total_premium": 25500,
        "policy_start": "2024-08-15",
        "policy_end": "2027-08-14",
        "ncb_percent": 0,
        "voluntary_deductible": 2500,
        "add_ons": ["Zero Depreciation", "Roadside Assistance 24x7", "Personal Accident Cover Rs.15L"],
        "nominee": "Sreelakshmi Nair",
        "prior_claims": 0,
        "notes": "New customer, first vehicle insurance. No prior claims history.",
    },
    {
        "policy_no": "POL-445566",
        "insured_name": "Meera Iyer",
        "phone": "8890123456",
        "address": "7, Saraswathipuram, Mysuru - 570009",
        "dob": "17/04/1995",
        "vehicle_make": "Maruti Suzuki",
        "vehicle_model": "Baleno Alpha",
        "registration_no": "KA-03-GH-4567",
        "chassis_no": "MA3EWDE1S0L456789",
        "engine_no": "K12CN3456789",
        "year_of_manufacture": 2020,
        "fuel_type": "Petrol",
        "colour": "Nexa Blue",
        "coverage_type": "Comprehensive",
        "idv": 480000,
        "od_premium": 9500,
        "tp_premium": 3478,
        "total_premium": 13400,
        "policy_start": "2023-11-01",
        "policy_end": "2026-10-31",
        "ncb_percent": 20,
        "voluntary_deductible": 2000,
        "add_ons": ["Zero Depreciation", "Roadside Assistance"],
        "nominee": "Krishnamurthy Iyer",
        "prior_claims": 0,
        "notes": "Renewal customer. NCB 20% applied. Clean claims record since inception.",
    },
    {
        "policy_no": "POL-778899",
        "insured_name": "Vikram Singh",
        "phone": "9234567890",
        "address": "12, C-Scheme, Ajmer Road, Jaipur - 302001",
        "dob": "09/02/1978",
        "vehicle_make": "BMW",
        "vehicle_model": "3 Series 320d Luxury Line",
        "registration_no": "RJ-14-JK-1234",
        "chassis_no": "WBA5R31050FJ12345",
        "engine_no": "N47D20C1234567",
        "year_of_manufacture": 2021,
        "fuel_type": "Diesel",
        "colour": "Alpine White",
        "coverage_type": "Comprehensive",
        "idv": 3500000,
        "od_premium": 68000,
        "tp_premium": 8200,
        "total_premium": 80000,
        "policy_start": "2023-05-20",
        "policy_end": "2026-05-19",
        "ncb_percent": 0,
        "voluntary_deductible": 10000,
        "add_ons": ["Zero Depreciation", "Return to Invoice", "Engine Protection", "Key Replacement", "Personal Accident Cover Rs.25L"],
        "nominee": "Kavya Singh",
        "prior_claims": 0,
        "notes": "High-value vehicle. Mandatory pre-inspection completed. Dealer workshop only (BMW Jaipur Service). IDV based on current market valuation.",
    },
    {
        "policy_no": "POL-221144",
        "insured_name": "Sunita Patel",
        "phone": "8765432109",
        "address": "38, Naranpura, Near Vijay Cross Road, Ahmedabad - 380013",
        "dob": "25/06/1988",
        "vehicle_make": "Tata",
        "vehicle_model": "Altroz XZ Plus",
        "registration_no": "GJ-01-LM-5678",
        "chassis_no": "MAT624351N1234567",
        "engine_no": "1.2REV6782345",
        "year_of_manufacture": 2022,
        "fuel_type": "Petrol",
        "colour": "Downtown Red",
        "coverage_type": "Comprehensive",
        "idv": 620000,
        "od_premium": 13500,
        "tp_premium": 3478,
        "total_premium": 17500,
        "policy_start": "2024-02-28",
        "policy_end": "2027-02-27",
        "ncb_percent": 0,
        "voluntary_deductible": 2000,
        "add_ons": ["Zero Depreciation", "Roadside Assistance", "Consumables Cover"],
        "nominee": "Mahesh Patel",
        "prior_claims": 0,
        "notes": "No prior claims. Vehicle primarily used for city commute.",
    },
    {
        "policy_no": "POL-334455",
        "insured_name": "Ravi Shankar",
        "phone": "7890123456",
        "address": "55, Koregaon Park, Pune - 411001",
        "dob": "14/03/1975",
        "vehicle_make": "Honda",
        "vehicle_model": "Amaze VX CVT",
        "registration_no": "MH-12-NO-9012",
        "chassis_no": "MAKGN9540KH901234",
        "engine_no": "L12B29012345",
        "year_of_manufacture": 2019,
        "fuel_type": "Petrol",
        "colour": "Radiant Red Metallic",
        "coverage_type": "Comprehensive",
        "idv": 545000,
        "od_premium": 11000,
        "tp_premium": 3478,
        "total_premium": 15000,
        "policy_start": "2023-09-10",
        "policy_end": "2026-09-09",
        "ncb_percent": 35,
        "voluntary_deductible": 2500,
        "add_ons": ["Roadside Assistance", "Personal Accident Cover Rs.15L"],
        "nominee": "Padma Shankar",
        "prior_claims": 0,
        "notes": "Long-standing customer. NCB 35% applied. Vehicle used for daily office commute.",
    },
    {
        "policy_no": "POL-667788",
        "insured_name": "Anjali Gupta",
        "phone": "9012345678",
        "address": "4/C, Shyambazar Street, Kolkata - 700004",
        "dob": "22/08/2000",
        "vehicle_make": "Maruti Suzuki",
        "vehicle_model": "Alto K10 VXI",
        "registration_no": "WB-02-PQ-3456",
        "chassis_no": "MA3CAHE1S8M345678",
        "engine_no": "K10BM3456789",
        "year_of_manufacture": 2018,
        "fuel_type": "Petrol",
        "colour": "Silky Silver",
        "coverage_type": "Third Party",
        "idv": 185000,
        "od_premium": 0,
        "tp_premium": 2470,
        "total_premium": 2900,
        "policy_start": "2025-12-05",
        "policy_end": "2026-12-04",
        "ncb_percent": 0,
        "voluntary_deductible": 0,
        "add_ons": [],
        "nominee": "Suresh Gupta",
        "prior_claims": 0,
        "notes": "Third Party Only policy. Own damage not covered. Vehicle is 6+ years old. Customer opted for TP-only due to age of vehicle.",
    },
    {
        "policy_no": "POL-990011",
        "insured_name": "Deepak Joshi",
        "phone": "8123456789",
        "address": "22, Vijay Nagar, Near Bombay Hospital, Indore - 452010",
        "dob": "07/05/1983",
        "vehicle_make": "Mahindra",
        "vehicle_model": "Scorpio N Z8 L",
        "registration_no": "MP-09-RS-7890",
        "chassis_no": "MABZS6BJ9P7890123",
        "engine_no": "mHawk140P7890",
        "year_of_manufacture": 2023,
        "fuel_type": "Diesel",
        "colour": "Burnt Sienna",
        "coverage_type": "Comprehensive",
        "idv": 1450000,
        "od_premium": 30000,
        "tp_premium": 8200,
        "total_premium": 39000,
        "policy_start": "2025-03-15",
        "policy_end": "2026-03-14",
        "ncb_percent": 0,
        "voluntary_deductible": 5000,
        "add_ons": ["Zero Depreciation", "Engine Protection", "Roadside Assistance 24x7"],
        "nominee": "Rekha Joshi",
        "prior_claims": 0,
        "notes": "Policy issued March 2025. New vehicle at inception. No pre-inspection required.",
    },
    {
        "policy_no": "POL-556677",
        "insured_name": "Shalini Menon",
        "phone": "9345678901",
        "address": "18, RS Puram, 4th Street, Coimbatore - 641002",
        "dob": "11/12/1986",
        "vehicle_make": "Volkswagen",
        "vehicle_model": "Polo Comfortline 1.0 MPI",
        "registration_no": "TN-09-TU-1234",
        "chassis_no": "WVWZZZ6RZHY123456",
        "engine_no": "CHY1234567",
        "year_of_manufacture": 2018,
        "fuel_type": "Petrol",
        "colour": "Reflex Silver",
        "coverage_type": "Comprehensive",
        "idv": 380000,
        "od_premium": 8200,
        "tp_premium": 2470,
        "total_premium": 11200,
        "policy_start": "2024-07-22",
        "policy_end": "2027-07-21",
        "ncb_percent": 50,
        "voluntary_deductible": 2000,
        "add_ons": ["Roadside Assistance"],
        "nominee": "Suresh Menon",
        "prior_claims": 0,
        "notes": "Loyal customer - 6th consecutive renewal. NCB at maximum 50%. Vehicle is 6 years old but well-maintained.",
    },
    {
        "policy_no": "POL-889900",
        "insured_name": "Rohit Verma",
        "phone": "7012345678",
        "address": "9, Gomti Nagar Extension, Lucknow - 226010",
        "dob": "18/09/1987",
        "vehicle_make": "MG",
        "vehicle_model": "Hector Plus Super 1.5T",
        "registration_no": "UP-32-VW-5678",
        "chassis_no": "LSJA24U07N5678901",
        "engine_no": "15T4CYL5678901",
        "year_of_manufacture": 2023,
        "fuel_type": "Petrol",
        "colour": "Candy White",
        "coverage_type": "Comprehensive",
        "idv": 1600000,
        "od_premium": 34000,
        "tp_premium": 8200,
        "total_premium": 43000,
        "policy_start": "2026-04-01",
        "policy_end": "2027-03-31",
        "ncb_percent": 0,
        "voluntary_deductible": 5000,
        "add_ons": ["Zero Depreciation", "Return to Invoice", "Engine Protection", "Roadside Assistance 24x7"],
        "nominee": "Priya Verma",
        "prior_claims": 0,
        "notes": "NEW POLICY issued 01-Apr-2026 (less than 60 days old). No pre-inception survey conducted. First policy with us.",
    },
    {
        "policy_no": "POL-223344",
        "insured_name": "Pooja Nambiar",
        "phone": "9654321087",
        "address": "6, Nadakkave, Kozhikode - 673011",
        "dob": "28/01/1993",
        "vehicle_make": "Renault",
        "vehicle_model": "Kwid RXT 1.0 SCe",
        "registration_no": "KL-07-XY-9012",
        "chassis_no": "MEEHM1BAK78901234",
        "engine_no": "D4FCE8901234",
        "year_of_manufacture": 2021,
        "fuel_type": "Petrol",
        "colour": "Moonlight Silver",
        "coverage_type": "Comprehensive",
        "idv": 340000,
        "od_premium": 7500,
        "tp_premium": 3478,
        "total_premium": 11400,
        "policy_start": "2023-03-18",
        "policy_end": "2026-03-17",
        "ncb_percent": 20,
        "voluntary_deductible": 1000,
        "add_ons": ["Roadside Assistance"],
        "nominee": "Rajan Nambiar",
        "prior_claims": 0,
        "notes": "Second renewal. NCB 20% applicable. Primary vehicle for family use.",
    },
]

EXCLUSIONS = [
    "Damage caused while driving under the influence of alcohol or drugs.",
    "Damage to tyres and tubes unless the vehicle is damaged simultaneously.",
    "Damage arising out of mechanical or electrical breakdown.",
    "Consequential loss, depreciation in value, wear and tear.",
    "Loss or damage caused by an unlicensed driver.",
    "Damage outside the geographical area of India.",
    "War, invasion, acts of foreign enemies, civil war, rebellion, or nuclear perils.",
    "Contractual liability of any kind.",
    "Damage to vehicle used for hire, reward, or racing.",
    "Electrical or mechanical failure not resulting from an accident.",
]

CLAIM_PROCEDURE = [
    ("Step 1 — Immediate Action",
     "Inform us within 24 hours of any accident/theft. Call our 24x7 Claims Helpline: 1800-XXX-XXXX or use the ClaimIntel mobile app."),
    ("Step 2 — FIR (where required)",
     "For theft, total loss, third-party bodily injury, or accident involving unknown vehicles — file an FIR with the nearest police station immediately."),
    ("Step 3 — Document Collection",
     "Collect: Driving Licence (original), RC Book, Policy Document, FIR copy (if applicable), Damage photos (minimum 6 images from all angles)."),
    ("Step 4 — Vehicle Survey",
     "Do not move or repair the vehicle until our surveyor inspects it. For claims above ₹50,000, a licensed surveyor will inspect within 48 hours."),
    ("Step 5 — Workshop",
     "Take the vehicle only to an empanelled workshop for cashless settlement. A list of 450+ partner garages is available on our app."),
    ("Step 6 — Settlement",
     "Claims below ₹50,000: settled within 7 working days. Claims above ₹50,000: settled within 15 working days after surveyor report submission."),
]


# ---------------------------------------------------------------------------
# PDF generation
# ---------------------------------------------------------------------------
class PolicyPDF(FPDF):
    """Custom FPDF subclass with header/footer."""

    def __init__(self, policy: dict):
        super().__init__()
        self.policy = policy
        self.set_margins(20, 20, 20)
        self.set_auto_page_break(auto=True, margin=20)

    def header(self):
        self.set_fill_color(30, 58, 138)   # dark indigo
        self.rect(0, 0, 210, 18, 'F')
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(255, 255, 255)
        self.set_y(5)
        self.cell(0, 8, "GANIT MOTORS INSURANCE CO. LTD.  |  CIN: U66022KA2010PLC052345  |  IRDAI Reg No: 145", align="C")
        self.set_text_color(0, 0, 0)
        self.ln(14)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(120, 120, 120)
        self.cell(0, 5, f"Policy: {self.policy['policy_no']}  |  Page {self.page_no()}/{{nb}}  |  This is a computer-generated document. Valid without signature.", align="C")
        self.set_text_color(0, 0, 0)

    @staticmethod
    def _s(text: str) -> str:
        """Sanitize text for fpdf2 latin-1 / Helvetica encoding."""
        return (str(text)
            .replace('—', ' - ').replace('–', '-')
            .replace('’', "'").replace('‘', "'")
            .replace('“', '"').replace('”', '"')
            .replace('•', '-').replace('·', '-')
            .replace('→', '->').replace('✓', 'OK')
            .replace('₹', 'Rs.')
        )

    def section_title(self, title: str):
        self.ln(4)
        self.set_fill_color(224, 231, 255)   # indigo-100
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(30, 58, 138)
        self.cell(0, 8, f"  {self._s(title)}", ln=True, fill=True)
        self.set_text_color(0, 0, 0)
        self.ln(2)

    def kv_row(self, key: str, value: str, bold_value: bool = False):
        # Content area = 210 - 20(L) - 20(R) = 170mm; key=70, value=100
        self.set_font("Helvetica", "", 9)
        self.set_text_color(80, 80, 80)
        self.cell(70, 6, self._s(key) + ":", ln=False)
        if bold_value:
            self.set_font("Helvetica", "B", 9)
        self.set_text_color(20, 20, 20)
        self.multi_cell(100, 6, self._s(str(value)))

    def kv_row_pair(self, k1: str, v1: str, k2: str, v2: str):
        """Two key-value pairs on one line."""
        self.set_font("Helvetica", "", 9)
        self.set_text_color(80, 80, 80)
        self.cell(40, 6, self._s(k1) + ":", ln=False)
        self.set_text_color(20, 20, 20)
        self.set_font("Helvetica", "B", 9)
        self.cell(50, 6, self._s(str(v1)), ln=False)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(80, 80, 80)
        self.cell(40, 6, self._s(k2) + ":", ln=False)
        self.set_text_color(20, 20, 20)
        self.set_font("Helvetica", "B", 9)
        self.cell(0, 6, self._s(str(v2)), ln=True)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(0, 0, 0)


def _s(text: str) -> str:
    """Sanitize text for fpdf2 latin-1 / Helvetica encoding."""
    return (str(text)
        .replace('—', ' - ')   # em dash
        .replace('–', '-')     # en dash
        .replace('’', "'")     # right single quote
        .replace('‘', "'")     # left single quote
        .replace('“', '"')     # left double quote
        .replace('”', '"')     # right double quote
        .replace('•', '-')     # bullet
        .replace('·', '-')     # middle dot
        .replace('→', '->')    # arrow right
        .replace('–', '-')     # en dash
        .replace('✓', 'OK')    # check mark
        .replace('₹', 'Rs.')   # rupee sign
    )


def _fmt_inr(amount: int) -> str:
    return f"Rs. {amount:,}"


def generate_pdf(policy: dict, output_dir: str) -> str:
    pdf = PolicyPDF(policy)
    pdf.alias_nb_pages()

    # -----------------------------------------------------------------------
    # PAGE 1 — Policy Schedule
    # -----------------------------------------------------------------------
    pdf.add_page()

    # Hero header box
    pdf.set_fill_color(238, 242, 255)
    pdf.rect(20, 20, 170, 28, 'F')
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(30, 58, 138)
    pdf.set_y(23)
    pdf.cell(0, 8, "MOTOR INSURANCE POLICY SCHEDULE", align="C", ln=True)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, f"Policy No.: {policy['policy_no']}   |   {policy['coverage_type'].upper()}", align="C", ln=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(8)

    # Policy validity banner
    pdf.set_fill_color(34, 197, 94)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 7, f"   POLICY PERIOD:  {policy['policy_start']}  to  {policy['policy_end']}   (12 months)", fill=True, ln=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    # Policyholder details
    pdf.section_title("SECTION A — POLICYHOLDER INFORMATION")
    pdf.kv_row("Name of Insured", policy["insured_name"], bold_value=True)
    pdf.kv_row("Date of Birth", policy["dob"])
    pdf.kv_row("Mobile Number", policy["phone"])
    pdf.kv_row("Registered Address", policy["address"])
    pdf.kv_row("Nominee", policy["nominee"])
    pdf.ln(2)

    # Vehicle details
    pdf.section_title("SECTION B — VEHICLE DETAILS")
    pdf.kv_row_pair("Make", policy["vehicle_make"], "Model", policy["vehicle_model"])
    pdf.kv_row_pair("Reg. Number", policy["registration_no"], "Year of Mfg.", str(policy["year_of_manufacture"]))
    pdf.kv_row_pair("Fuel Type", policy["fuel_type"], "Colour", policy["colour"])
    pdf.kv_row("Chassis Number", policy["chassis_no"])
    pdf.kv_row("Engine Number", policy["engine_no"])
    pdf.ln(2)

    # Coverage details
    pdf.section_title("SECTION C — COVERAGE & PREMIUM SUMMARY")
    pdf.kv_row_pair(
        "Insured Declared Value (IDV)", _fmt_inr(policy["idv"]),
        "Coverage Type", policy["coverage_type"]
    )
    pdf.kv_row_pair(
        "Own Damage Premium", _fmt_inr(policy["od_premium"]),
        "Third Party Premium", _fmt_inr(policy["tp_premium"])
    )
    pdf.kv_row_pair(
        "Total Annual Premium", _fmt_inr(policy["total_premium"]),
        "NCB Discount", f"{policy['ncb_percent']}%"
    )
    pdf.kv_row("Voluntary Deductible", _fmt_inr(policy["voluntary_deductible"]))
    pdf.kv_row("Compulsory Deductible", "Rs. 1,000 (per IRDAI mandate)")
    pdf.ln(2)

    # Add-ons
    pdf.section_title("SECTION D — ADD-ON COVERS")
    for addon in policy["add_ons"]:
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(8, 6, "*", ln=False)   # bullet (ascii)
        pdf.cell(0, 6, _s(addon), ln=True)
    if not policy["add_ons"]:
        pdf.set_font("Helvetica", "I", 9)
        pdf.cell(0, 6, "No add-on covers selected.", ln=True)
    pdf.ln(2)

    # Notes
    if policy.get("notes"):
        pdf.section_title("UNDERWRITER NOTES")
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(80, 80, 80)
        pdf.multi_cell(0, 6, _s(policy["notes"]))
        pdf.set_text_color(0, 0, 0)

    # -----------------------------------------------------------------------
    # PAGE 2 — Coverage Details
    # -----------------------------------------------------------------------
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(30, 58, 138)
    pdf.cell(0, 8, "COVERAGE DETAILS & CONDITIONS", align="C", ln=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    pdf.section_title("OWN DAMAGE COVERAGE (Section I)")
    own_damage_items = [
        ("Accidental Damage", f"Up to IDV ({_fmt_inr(policy['idv'])}) after deductibles"),
        ("Fire and Explosion", "Covered - Full IDV"),
        ("Natural Calamities", "Covered - Flood, Earthquake, Cyclone, Hailstorm, Lightning"),
        ("Theft / Total Loss", f"Up to IDV ({_fmt_inr(policy['idv'])})"),
        ("Transit Damage", "Covered during road, rail, inland waterway, air or elevator transit"),
        ("Malicious Acts / Riot", "Covered"),
    ]
    if policy["fuel_type"] == "Electric":
        own_damage_items.append(("Battery Pack (EV)", "Covered under Battery Guard add-on up to Rs. 8,50,000"))
        own_damage_items.append(("Charging Equipment", "Covered under Charging Equipment add-on"))

    for item, detail in own_damage_items:
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(70, 6, _s(item), ln=False)
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(100, 6, _s(detail))

    pdf.ln(3)
    pdf.section_title("THIRD PARTY LIABILITY (Section II - Mandatory)")
    tp_items = [
        ("Third Party Bodily Injury", "Unlimited as per Motor Vehicles Act, 1988"),
        ("Third Party Property Damage", "Up to Rs. 7,50,000 per incident"),
        ("Personal Accident - Owner-Driver", "Rs. 15,00,000 (compulsory cover)"),
    ]
    for item, detail in tp_items:
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(70, 6, _s(item), ln=False)
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(100, 6, _s(detail))

    pdf.ln(3)
    pdf.section_title("DEDUCTIBLE SCHEDULE")
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(170, 6,
        f"Compulsory Deductible: Rs. 1,000 (IRDAI Mandate)\n"
        f"Voluntary Deductible: {_fmt_inr(policy['voluntary_deductible'])} (selected by insured)\n"
        f"Total Deductible Per Claim: {_fmt_inr(1000 + policy['voluntary_deductible'])}"
    )

    pdf.ln(3)
    pdf.section_title("DEPRECIATION SCHEDULE (IRDAI — Per Part Replacement)")
    depr_data = [
        ("0 to 6 months", "0%"), ("6 to 12 months", "5%"), ("1 to 2 years", "10%"),
        ("2 to 3 years", "15%"), ("3 to 4 years", "25%"), ("4 to 5 years", "35%"), ("Above 5 years", "50%"),
    ]
    for period, rate in depr_data:
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(80, 5, period, ln=False)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(0, 5, rate, ln=True)

    if "Zero Depreciation" in policy["add_ons"]:
        pdf.ln(2)
        pdf.set_fill_color(187, 247, 208)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(0, 7, "   ZERO DEPRECIATION ADD-ON ACTIVE - No depreciation deducted on parts replacement.", fill=True, ln=True)

    # -----------------------------------------------------------------------
    # PAGE 3 — Exclusions & Claim Procedure
    # -----------------------------------------------------------------------
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(30, 58, 138)
    pdf.cell(0, 8, "EXCLUSIONS AND CLAIM PROCEDURE", align="C", ln=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    pdf.section_title("SECTION III - EXCLUSIONS (What is NOT Covered)")
    for i, excl in enumerate(EXCLUSIONS, 1):
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(8, 6, f"{i}.", ln=False)
        pdf.multi_cell(162, 6, _s(excl))   # 170 - 8 = 162mm remaining
    pdf.ln(3)

    pdf.section_title("SECTION IV - HOW TO FILE A CLAIM")
    for step_title, step_body in CLAIM_PROCEDURE:
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(30, 58, 138)
        pdf.cell(170, 7, _s(step_title), ln=True)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(40, 40, 40)
        pdf.multi_cell(170, 6, _s(step_body))
        pdf.ln(1)

    pdf.set_text_color(0, 0, 0)
    pdf.ln(2)

    pdf.section_title("IMPORTANT CONTACT INFORMATION")
    pdf.kv_row("24x7 Claims Helpline", "1800-XXX-XXXX (Toll Free)")
    pdf.kv_row("Grievance Redressal", "grievance@ganitinsurance.in")
    pdf.kv_row("Workshop Locator", "www.ganitinsurance.in/garages or ClaimIntel App")
    pdf.kv_row("IRDAI Grievance Portal", "www.igms.irda.gov.in | Helpline: 155255")

    # -----------------------------------------------------------------------
    # Output
    # -----------------------------------------------------------------------
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, f"{policy['policy_no']}.pdf")
    pdf.output(out_path)
    return out_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Generate synthetic insurance policy PDFs for ClaimIntel KB.")
    parser.add_argument("--policy", metavar="POLICY_NO", help="Generate only the specified policy (e.g. POL-784512)")
    parser.add_argument("--output-dir", default=None, help="Output directory (default: data/kb/policies/)")
    args = parser.parse_args()

    # Default output dir relative to project root
    default_out = os.path.join(PROJECT_ROOT, "data", "kb", "policies")
    output_dir = args.output_dir or default_out

    targets = POLICIES
    if args.policy:
        targets = [p for p in POLICIES if p["policy_no"] == args.policy]
        if not targets:
            print(f"ERROR: Policy '{args.policy}' not found. Available: {[p['policy_no'] for p in POLICIES]}")
            sys.exit(1)

    print(f"Generating {len(targets)} policy PDF(s) -> {output_dir}")
    for policy in targets:
        path = generate_pdf(policy, output_dir)
        print(f"  OK  {policy['policy_no']}  ({policy['insured_name']})  ->  {path}")

    print(f"\nDone. {len(targets)} PDF(s) written.")


if __name__ == "__main__":
    main()
