"""
Generate test FIR reports and garage estimation slips for ClaimIntel testing.
Outputs directly to:  tests/FIR/  and  tests/Garage Slip/

Date rules applied (today = 05 June 2026):
  - 4 FIRs have incident dates within 6 days of today  (May 30 - June 5 2026)
  - 2 FIRs have older but valid incident dates           (May 11 and May 15 2026)
  - 2 FIRs are kept as intentional fraud/mismatch demos (unchanged)
  - Garage slips are dated 1-2 days after their FIR incident date

Fraud/mismatch demos (kept as-is):
  - Mohammed_Faiz_FIR_Mismatch_Demo  - wrong reg / location / date vs claim
  - Rohit_Verma_FIR_Mismatch_Demo    - incident date BEFORE policy start

Usage:
    python scripts/generate_test_docs.py
    python scripts/generate_test_docs.py --firs
    python scripts/generate_test_docs.py --garages

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

TESTS_DIR   = os.path.join(PROJECT_ROOT, "tests")
FIR_DIR     = os.path.join(TESTS_DIR, "FIR")
GARAGE_DIR  = os.path.join(TESTS_DIR, "Garage Slip")


def _s(text: str) -> str:
    return (str(text)
        .replace("—", " - ").replace("–", "-")
        .replace("‘", "'").replace("’", "'")
        .replace("“", '"').replace("”", '"')
        .replace("•", "-").replace("₹", "Rs.").replace("✓", "OK")
    )


# ---------------------------------------------------------------------------
# FIR DATA
# ---------------------------------------------------------------------------
# 4 within 6 days of today (June 5 2026): Rajesh Jun 2, Kavitha Jun 1,
#                                          Deepak May 31, Arjun Jun 3
# 2 outside 6 days but valid:             Priya May 15, Pooja May 11
# 2 kept as fraud demos:                  Mohammed Faiz, Rohit Verma
# ---------------------------------------------------------------------------

FIRS = [
    # ── 1. Rajesh Kumar (within 6 days — June 2) ─────────────────────────────
    {
        "filename": "Rajesh_Kumar_FIR.pdf",
        "fir_no": "0189 / 2026",
        "district": "Bengaluru Traffic",
        "police_station": "HSR Layout Traffic Police Station",
        "date_filed": "03 June 2026",
        "date_filed_time": "10:30 hrs",
        "incident_date": "02 June 2026",
        "incident_time": "19:05 hrs",
        "incident_location": "Outer Ring Road near Agara Junction, Bengaluru",
        "complainant": {
            "name": "Rajesh Kumar",
            "father": "Mahesh Kumar",
            "address": "HSR Layout, Bengaluru - 560102",
            "phone": "9876543210",
            "occupation": "Private Employee",
        },
        "vehicle": {
            "reg": "KA-01-MN-2345",
            "make": "Maruti Suzuki Swift Dzire",
            "colour": "Pearl Arctic White",
        },
        "accused_vehicle": "Unknown two-wheeler rider - left scene before details could be recorded",
        "statement": (
            "The complainant states that on 02 June 2026 at approximately 19:05 hours he was "
            "driving his Maruti Suzuki Swift Dzire bearing registration KA-01-MN-2345 on Outer "
            "Ring Road near Agara Junction. A two-wheeler abruptly changed lanes and brushed the "
            "front left side of the car, causing damage to the front bumper, grille and left "
            "headlamp area. The rider left the spot before details could be taken. No bodily "
            "injury was reported."
        ),
        "action": (
            "Case entered as road traffic accident property damage. Complainant produced RC, "
            "DL and insurance copy. Scene photographs reviewed."
        ),
        "station_note": (
            "Documents verified at station. Photographs attached for insurance claim reference."
        ),
        "officer": "Sub-Inspector Naveen Gowda, Badge No. B-1934",
        "is_fraud": False,
    },

    # ── 2. Kavitha Reddy (within 6 days — June 1) ────────────────────────────
    {
        "filename": "Kavitha_Reddy_FIR.pdf",
        "fir_no": "0276 / 2026",
        "district": "Hyderabad",
        "police_station": "Madhapur Police Station",
        "date_filed": "02 June 2026",
        "date_filed_time": "14:15 hrs",
        "incident_date": "01 June 2026",
        "incident_time": "12:35 hrs",
        "incident_location": "Near Cyber Towers, Hitec City, Hyderabad",
        "complainant": {
            "name": "Kavitha Reddy",
            "father": "Narasimha Reddy",
            "address": "Madhapur, Hyderabad - 500081",
            "phone": "9123456789",
            "occupation": "Business Analyst",
        },
        "vehicle": {
            "reg": "AP-09-EF-3456",
            "make": "Tata Nexon EV Max",
            "colour": "Signature Teal Blue",
        },
        "accused_vehicle": "Public transport bus - route and registration not identified at time of filing",
        "statement": (
            "The complainant states that while proceeding slowly in traffic near Cyber Towers on "
            "01 June 2026, a public transport bus moved from the adjoining lane and scraped the "
            "right side of her Tata Nexon EV Max bearing AP-09-EF-3456. The vehicle sustained "
            "damage to the right front door, right rear door and ORVM. The bus continued ahead "
            "due to traffic congestion and could not be stopped immediately."
        ),
        "action": (
            "FIR registered for property damage. CCTV request sent to Cyber Towers traffic "
            "surveillance unit. Vehicle photographs collected."
        ),
        "station_note": (
            "Vehicle documents verified. CCTV response pending from Cyber Towers traffic "
            "surveillance unit."
        ),
        "officer": "Assistant Sub-Inspector G. Prasad, Badge No. H-4412",
        "is_fraud": False,
    },

    # ── 3. Deepak Joshi (within 6 days — May 31) ─────────────────────────────
    {
        "filename": "Deepak_Joshi_FIR.pdf",
        "fir_no": "0611 / 2026",
        "district": "Indore",
        "police_station": "Vijay Nagar Police Station",
        "date_filed": "01 June 2026",
        "date_filed_time": "09:20 hrs",
        "incident_date": "31 May 2026",
        "incident_time": "22:40 hrs",
        "incident_location": "AB Road service lane near C21 Mall, Indore",
        "complainant": {
            "name": "Deepak Joshi",
            "father": "Ramesh Joshi",
            "address": "Vijay Nagar, Indore - 452010",
            "phone": "8123456789",
            "occupation": "Contractor",
        },
        "vehicle": {
            "reg": "MP-09-RS-7890",
            "make": "Mahindra Scorpio N Z8 L",
            "colour": "Napoli Black",
        },
        "accused_vehicle": "Unknown goods carrier vehicle",
        "statement": (
            "The complainant states that his Mahindra Scorpio N bearing MP-09-RS-7890 was parked "
            "on the AB Road service lane near C21 Mall. On returning at approximately 22:40 hours "
            "on 31 May 2026 he found the rear bumper, tailgate lower trim and left tail lamp "
            "damaged. A nearby shopkeeper stated that a goods carrier reversed into the parked "
            "vehicle and left without stopping."
        ),
        "action": (
            "Case registered under relevant provisions for rash and negligent driving causing "
            "property damage. Nearby CCTV footage requisitioned."
        ),
        "station_note": (
            "Shopkeeper witness statement noted. Vehicle photographs and document copies received."
        ),
        "officer": "Sub-Inspector Priyanka Verma, Badge No. I-3340",
        "is_fraud": False,
    },

    # ── 4. Pooja Nambiar (outside 6 days — May 11, no FIR change) ────────────
    {
        "filename": "Pooja_Nambiar_FIR.pdf",
        "fir_no": "0433 / 2026",
        "district": "Ernakulam",
        "police_station": "Kakkanad Police Station",
        "date_filed": "12 May 2026",
        "date_filed_time": "13:10 hrs",
        "incident_date": "11 May 2026",
        "incident_time": "18:25 hrs",
        "incident_location": "Near Kakkanad signal, Infopark Expressway, Kochi",
        "complainant": {
            "name": "Pooja Nambiar",
            "father": "Vijay Nambiar",
            "address": "Kakkanad, Kochi - 682030",
            "phone": "9654321087",
            "occupation": "Teacher",
        },
        "vehicle": {
            "reg": "KL-07-XY-9012",
            "make": "Renault Kwid RXT",
            "colour": "Moonlight Silver",
        },
        "accused_vehicle": "Private cab - driver left before formal exchange of details",
        "statement": (
            "The complainant states that on 11 May 2026 her Renault Kwid bearing KL-07-XY-9012 "
            "was struck from the rear by a private cab while waiting near Kakkanad signal. The "
            "vehicle sustained rear bumper, tailgate and rear lamp damage. The cab driver "
            "initially stopped but left before formal exchange of details, citing urgent duty."
        ),
        "action": (
            "Case registered. Traffic camera footage requested from Infopark Expressway control room."
        ),
        "station_note": (
            "Complainant advised to share any cab details or dashcam footage if later recovered."
        ),
        "officer": "Sub-Inspector R. Menon, Badge No. K-2281",
        "is_fraud": False,
    },

    # ── 5. Priya Sharma (outside 6 days — May 15 2026, updated from 2025) ────
    {
        "filename": "Priya_Sharma_FIR.pdf",
        "fir_no": "0245 / 2026",
        "district": "Mumbai Suburban",
        "police_station": "Bandra Police Station, H Division",
        "date_filed": "16 May 2026",
        "date_filed_time": "11:30 hrs",
        "incident_date": "15 May 2026",
        "incident_time": "17:15 hrs",
        "incident_location": "Turner Road, near Bandra Station, Bandra West, Mumbai",
        "complainant": {
            "name": "Priya Sharma",
            "father": "Ramesh Sharma",
            "address": (
                "15, Indiranagar 12th Main, Bengaluru - 560038 "
                "(Temporary: Flat 3B, Sharma Residency, Bandra West, Mumbai - 400050)"
            ),
            "phone": "9845012345",
            "occupation": "Software Engineer",
        },
        "vehicle": {
            "reg": "MH-02-AB-1234",
            "make": "Honda City ZX CVT",
            "colour": "Meteoroid Gray",
        },
        "accused_vehicle": (
            "Unidentified Heavy Goods Vehicle (Truck) - Maharashtra registration, "
            "dark blue, partial plate MH 04 visible"
        ),
        "statement": (
            "The complainant states that on 15th May 2026 at approximately 17:15 hours she was "
            "driving her vehicle Honda City (MH-02-AB-1234) on Turner Road, Bandra West, Mumbai, "
            "and was stationary at a red traffic signal near Bandra Railway Station. At that time "
            "an unidentified truck coming from behind failed to stop in time and struck the rear "
            "of her vehicle with considerable force. The truck driver did not stop and fled the "
            "scene immediately. The complainant's vehicle sustained significant damage to the rear "
            "bumper, boot lid, and rear light clusters. No persons were physically injured. The "
            "complainant requests registration of FIR and appropriate action against the "
            "unidentified driver."
        ),
        "action": (
            "Case registered under Sections 279, 338 IPC and Motor Vehicles Act 1988. Vehicle "
            "inspected at scene. Witness statements recorded from 2 bystanders (names on record)."
        ),
        "station_note": (
            "Vehicle not seized. Complainant advised to produce RC, DL, and insurance documents."
        ),
        "officer": "Sub-Inspector Satish Patil, Badge No. M-2341",
        "is_fraud": False,
    },

    # ── 6. Mohammed Faiz — MISMATCH DEMO (kept as-is) ────────────────────────
    # Intentional mismatches: wrong reg no, wrong location, wrong date vs claim
    # Incident May 15 2025 is only 44 days after policy start Apr 1 2025
    # (triggers new-policy-syndrome flag in Agent 2)
    {
        "filename": "Mohammed_Faiz_FIR_Mismatch_Demo.pdf",
        "fir_no": "1142 / 2025",
        "district": "Chennai (City)",
        "police_station": "Anna Nagar East Police Station",
        "date_filed": "21 May 2025",
        "date_filed_time": "09:45 hrs",
        "incident_date": "15 May 2025",
        "incident_time": "23:30 hrs",
        "incident_location": "Old Mahabalipuram Road (OMR), near Sholinganallur IT Park, Chennai",
        "complainant": {
            "name": "Mohammed Faiz",
            "father": "Abdul Faiz",
            "address": "8, RT Nagar Main Road, Bengaluru - 560032",
            "phone": "9988776655",
            "occupation": "Business",
        },
        "vehicle": {
            "reg": "TN-07-GH-1234",          # mismatch: policy vehicle is TN-07-CD-5678
            "make": "Toyota Innova Crysta",
            "colour": "White",
        },
        "accused_vehicle": "Unknown vehicle - fled scene",
        "statement": (
            "The complainant states that on 15th May 2025 at approximately 23:30 hours his "
            "vehicle Toyota Innova (TN-07-GH-1234) was parked on the service lane of OMR Road "
            "near Sholinganallur when an unknown vehicle struck it from the side and fled. "
            "The complainant discovered the damage the following morning. He states no witnesses "
            "were present at the time of the incident. The vehicle sustained damage to the left "
            "side doors and rear panel. The complainant requests registration of FIR."
        ),
        "action": (
            "Case registered. Vehicle not at scene during verification visit. FIR recorded "
            "based on complainant statement alone."
        ),
        "station_note": (
            "Note: Vehicle not produced for inspection at time of FIR filing. RC and insurance "
            "papers submitted by complainant photocopies only."
        ),
        "officer": "Head Constable Murugan R., Badge No. C-7821",
        "is_fraud": True,
        "fraud_note": (
            "[FOR DEMO PURPOSES ONLY] This FIR contains intentional mismatches for fraud "
            "detection testing: (1) Incident date in FIR is 15 May 2025 but claim states "
            "18 May 2025 (3-day mismatch). (2) Location in FIR is OMR Road but claim states "
            "Outer Ring Road. (3) Vehicle reg in FIR is TN-07-GH-1234 but policy vehicle "
            "is TN-07-CD-5678."
        ),
    },

    # ── 7. Arjun Mehta (within 6 days — June 3) ──────────────────────────────
    {
        "filename": "Arjun_Mehta_FIR.pdf",
        "fir_no": "0378 / 2026",
        "district": "Kancheepuram",
        "police_station": "Perungudi Traffic Police Station",
        "date_filed": "04 June 2026",
        "date_filed_time": "17:45 hrs",
        "incident_date": "03 June 2026",
        "incident_time": "16:30 hrs",
        "incident_location": "Near Ramanujan IT City Parking, Perungudi, Chennai",
        "complainant": {
            "name": "Arjun Mehta",
            "father": "Suresh Mehta",
            "address": "23, Whitefield Main Road, Bengaluru - 560066",
            "phone": "9900112233",
            "occupation": "IT Professional",
        },
        "vehicle": {
            "reg": "DL-05-XY-9876",
            "make": "Hyundai Creta SX Turbo",
            "colour": "Typhoon Silver",
        },
        "accused_vehicle": "Unidentified white hatchback, partial Tamil Nadu registration",
        "statement": (
            "The complainant states that on 3rd June 2026 at approximately 16:30 hours his "
            "vehicle Hyundai Creta (DL-05-XY-9876) was parked in the designated parking area "
            "near Ramanujan IT City, Perungudi, Chennai. Upon returning from his office he "
            "noticed fresh damage to the tailgate and rear bumper of his vehicle consistent with "
            "a low-speed rear impact. A bystander security guard (name on record) confirmed "
            "seeing a white hatchback reverse into the vehicle and leave without stopping. "
            "CCTV footage from the parking area requested but not yet retrieved at time of "
            "FIR filing."
        ),
        "action": (
            "Case registered under Section 279 IPC. CCTV footage requisition sent to Ramanujan "
            "IT City security. Vehicle inspected on-site. Damage consistent with statement."
        ),
        "station_note": (
            "Vehicle RC, DL, and insurance documents verified originals. Damage assessment "
            "photographs taken at scene."
        ),
        "officer": "Sub-Inspector Karunakaran P., Badge No. T-5512",
        "is_fraud": False,
    },

    # ── 8. Rohit Verma — MISMATCH DEMO (incident June 1, filed June 2) ─────────
    {
        "filename": "Rohit_Verma_FIR_Mismatch_Demo.pdf",
        "fir_no": "0087 / 2026",
        "district": "Nagpur",
        "police_station": "Sitabuldi Police Station",
        "date_filed": "02 June 2026",
        "date_filed_time": "11:05 hrs",
        "incident_date": "01 June 2026",
        "incident_time": "20:10 hrs",
        "incident_location": "Ajni Square, Nagpur",
        "complainant": {
            "name": "Rohit Verma",
            "father": "Vikas Verma",
            "address": "Sitabuldi, Nagpur - 440012",
            "phone": "7012345678",
            "occupation": "Sales Manager",
        },
        "vehicle": {
            "reg": "MH-28-BQ-2255",
            "make": "Hyundai Venue SX",
            "colour": "Polar White",
        },
        "accused_vehicle": "Unknown car - no witness available at filing time",
        "statement": (
            "The complainant states that on 1st June 2026 at approximately 20:10 hours his "
            "Hyundai Venue bearing MH-28-BQ-2255 was hit by an unknown car near Ajni Square. "
            "He reports damage to the front bumper, bonnet edge and right headlamp. The "
            "complainant filed this report for insurance purposes and stated that no injury occurred."
        ),
        "action": (
            "FIR registered based on complainant statement. No witness available at the time "
            "of filing."
        ),
        "station_note": (
            "Vehicle not inspected at scene. FIR recorded from statement and photographs "
            "submitted later."
        ),
        "officer": "Head Constable A. Deshmukh, Badge No. N-9910",
        "is_fraud": True,
        "fraud_note": (
            "[FOR DEMO PURPOSES ONLY] This FIR intentionally supports mismatch testing: "
            "incident timing, location confidence, and vehicle inspection evidence should be "
            "cross-checked against the claim and uploaded photographs."
        ),
    },
]


# ---------------------------------------------------------------------------
# GARAGE SLIP DATA
# ---------------------------------------------------------------------------
# Rajesh Kumar:   garage June 4 2026  (2 days after June 2 FIR incident)
# Mohammed Faiz:  garage May 20 2025  (KEPT — 5 days after May 15 incident)
# Priya Sharma:   garage May 17 2026  (2 days after May 15 FIR incident)
# Arjun Mehta:    garage June 5 2026  (2 days after June 3 FIR incident)
# Pooja Nambiar:  garage May 13 2026  (2 days after May 11 FIR incident)
# ---------------------------------------------------------------------------

GARAGES = [
    # ── 1. Rajesh Kumar — updated to June 4 2026 ─────────────────────────────
    {
        "filename": "Rajesh_Kumar_Garage_Estimate.pdf",
        "job_card": "JC-BLR-2026-4821",
        "job_date": "04 June 2026",
        "workshop": {
            "name": "Vijayanagar Auto Works Pvt. Ltd.",
            "address": "No. 14, 2nd Cross, HSR Layout Sector 2, Bengaluru - 560102",
            "phone": "080-40221345",
            "gstin": "29AABCV1234F1Z5",
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
            {"part": "Front Bumper Assembly (OEM)", "type": "Replace",        "qty": 1, "unit": 8500,  "source": "OEM"},
            {"part": "Bonnet Panel",                "type": "Repair + Paint", "qty": 1, "unit": 12000, "source": "OEM"},
            {"part": "Front Grille (OEM)",          "type": "Replace",        "qty": 1, "unit": 3200,  "source": "OEM"},
            {"part": "Headlight Assembly LH (OEM)", "type": "Replace",        "qty": 1, "unit": 6800,  "source": "OEM"},
            {"part": "Front Underbody Spoiler",     "type": "Replace",        "qty": 1, "unit": 1800,  "source": "Aftermarket"},
            {"part": "Labour - Panel Beating & Denting",        "type": "Labour", "qty": 1, "unit": 4500, "source": "-"},
            {"part": "Labour - Painting (2-coat oven finish)",  "type": "Labour", "qty": 1, "unit": 3500, "source": "-"},
        ],
        "note": "Genuine front-end impact damage. All parts OEM wherever possible. Repair matches damage survey.",
        "is_fraud": False,
    },

    # ── 2. Mohammed Faiz — KEPT as-is (inflated demo) ─────────────────────────
    {
        "filename": "Mohammed_Faiz_Garage_Estimate_Inflated_Demo.pdf",
        "job_card": "JC-CHN-2025-1109",
        "job_date": "20 May 2025",
        "workshop": {
            "name": "Sri Rama Auto Repair Works",
            "address": "Plot 7-B, SIDCO Industrial Area, Ambattur, Chennai - 600098",
            "phone": "044-26781234",
            "gstin": "33ZZZZR9999X1Z1",
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
            {"part": "Left Front Door Skin + Inner Panel (OEM)", "type": "Replace",        "qty": 1, "unit": 28000, "source": "OEM"},
            {"part": "Left Rear Door Assembly (OEM)",            "type": "Replace",        "qty": 1, "unit": 26500, "source": "OEM"},
            {"part": "Rear Bumper (OEM)",                        "type": "Replace + Paint","qty": 1, "unit": 18000, "source": "OEM"},
            {"part": "Left Rear Quarter Panel",                  "type": "Repair + Paint", "qty": 1, "unit": 22000, "source": "OEM"},
            {"part": "Left ORVM (OEM)",                          "type": "Replace",        "qty": 1, "unit": 5500,  "source": "OEM"},
            {"part": "Running Board LH (OEM)",                   "type": "Replace",        "qty": 1, "unit": 8200,  "source": "OEM"},
            {"part": "Labour - Panel Beating & Alignment",       "type": "Labour",         "qty": 1, "unit": 12000, "source": "-"},
            {"part": "Labour - Full Body Paint Blend",           "type": "Labour",         "qty": 1, "unit": 10000, "source": "-"},
            {"part": "Consumables (Primer, Polish, Masking)",    "type": "Material",       "qty": 1, "unit": 4800,  "source": "-"},
        ],
        "note": "WARNING (for demo): This estimate is intentionally inflated by approx 70%+ above OEM rates. Not an empanelled workshop. Refer to fraud screening.",
        "is_fraud": True,
    },

    # ── 3. Priya Sharma — updated to May 17 2026 ─────────────────────────────
    {
        "filename": "Priya_Sharma_Garage_Estimate.pdf",
        "job_card": "JC-MUM-2026-7734",
        "job_date": "17 May 2026",
        "workshop": {
            "name": "K J Auto Service Center Pvt. Ltd.",
            "address": "Shop 4, Linking Road Service Lane, Bandra West, Mumbai - 400050",
            "phone": "022-26521890",
            "gstin": "27AABCK5678G1Z3",
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
            {"part": "Rear Bumper Assembly (OEM)",   "type": "Replace",        "qty": 1, "unit": 9800,  "source": "OEM"},
            {"part": "Boot Lid (Tailgate Panel)",    "type": "Repair + Paint", "qty": 1, "unit": 18500, "source": "OEM"},
            {"part": "Boot Lid Garnish (OEM)",       "type": "Replace",        "qty": 1, "unit": 3400,  "source": "OEM"},
            {"part": "Rear Lamp Cluster RH (OEM)",   "type": "Replace",        "qty": 1, "unit": 6800,  "source": "OEM"},
            {"part": "Rear Lamp Cluster LH (OEM)",   "type": "Replace",        "qty": 1, "unit": 6800,  "source": "OEM"},
            {"part": "Rear Bumper Bracket & Clips",  "type": "Replace",        "qty": 1, "unit": 1200,  "source": "OEM"},
            {"part": "Labour - Denting & Panel Work","type": "Labour",         "qty": 1, "unit": 5500,  "source": "-"},
            {"part": "Labour - Painting & Polishing","type": "Labour",         "qty": 1, "unit": 3500,  "source": "-"},
        ],
        "note": "Rear impact damage from stationary collision with truck. All repairs at OEM rate. Vehicle retained for 3 working days.",
        "is_fraud": False,
    },

    # ── 4. Arjun Mehta — updated to June 5 2026 ──────────────────────────────
    {
        "filename": "Arjun_Mehta_Garage_Estimate.pdf",
        "job_card": "JC-CHN-2026-3301",
        "job_date": "05 June 2026",
        "workshop": {
            "name": "Hyundai Exclusive Service - Perungudi",
            "address": "12-A, OMR Old Mahabalipuram Rd, Perungudi, Chennai - 600096",
            "phone": "044-40123456",
            "gstin": "33AABHH2345K1Z8",
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
            {"part": "Tailgate Outer Panel - Dent Repair",  "type": "Repair + Paint", "qty": 1, "unit": 4500, "source": "OEM"},
            {"part": "Rear Bumper Lower Touch-up Paint",    "type": "Paint",          "qty": 1, "unit": 1800, "source": "OEM"},
            {"part": "Boot Lamp Lens Cover (OEM)",          "type": "Replace",        "qty": 1, "unit": 950,  "source": "OEM"},
            {"part": "Labour - Minor Panel Beating",        "type": "Labour",         "qty": 1, "unit": 1500, "source": "-"},
            {"part": "Labour - Spot Painting",              "type": "Labour",         "qty": 1, "unit": 800,  "source": "-"},
        ],
        "note": "Minor parking damage to tailgate. Very limited scope of work. Vehicle ready same day.",
        "is_fraud": False,
    },

    # ── 5. Rohit Verma — June 3 2026 (2 days after June 1 incident) ──────────
    {
        "filename": "Rohit_Verma_Garage_Estimate.pdf",
        "job_card": "JC-NGP-2026-5521",
        "job_date": "03 June 2026",
        "workshop": {
            "name": "Hyundai Authorised Service - Nagpur",
            "address": "Plot 12, MIDC Hingna Road, Nagpur - 440016",
            "phone": "0712-40123456",
            "gstin": "27AABHN1234M1Z4",
            "authorised": "Hyundai Motor India Authorised Dealer Workshop",
        },
        "customer": {
            "name": "Rohit Verma",
            "vehicle": "Hyundai Venue SX 1.2 Petrol",
            "reg_no": "MH-28-BQ-2255",
            "mileage": "24,310 km",
            "insurance": "Ganit Motors Insurance / POL-889900",
        },
        "items": [
            {"part": "Front Bumper Assembly (OEM)",       "type": "Replace",        "qty": 1, "unit": 7500,  "source": "OEM"},
            {"part": "Bonnet Panel",                     "type": "Repair + Paint", "qty": 1, "unit": 9000,  "source": "OEM"},
            {"part": "Front Grille (OEM)",               "type": "Replace",        "qty": 1, "unit": 2500,  "source": "OEM"},
            {"part": "Right Headlamp Assembly (OEM)",    "type": "Replace",        "qty": 1, "unit": 8000,  "source": "OEM"},
            {"part": "Labour - Panel Beating & Denting", "type": "Labour",         "qty": 1, "unit": 3500,  "source": "-"},
            {"part": "Labour - Painting (2-coat)",       "type": "Labour",         "qty": 1, "unit": 3000,  "source": "-"},
        ],
        "note": "Front-end impact damage. All parts OEM. Vehicle ready in 4 working days.",
        "is_fraud": False,
    },

    # ── 6. Pooja Nambiar — updated to May 13 2026 ────────────────────────────
    {
        "filename": "Pooja_Nambiar_Garage_Estimate.pdf",
        "job_card": "JC-KOC-2026-8812",
        "job_date": "13 May 2026",
        "workshop": {
            "name": "Popular Vehicles & Services Pvt. Ltd.",
            "address": "NH-66, Kakkanad, Kochi - 682030",
            "phone": "0484-29876543",
            "gstin": "32AABCP1234D1Z9",
            "authorised": "Renault Authorised Service Centre",
        },
        "customer": {
            "name": "Pooja Nambiar",
            "vehicle": "Renault Kwid RXT 1.0 SCe",
            "reg_no": "KL-07-XY-9012",
            "mileage": "32,480 km",
            "insurance": "Ganit Motors Insurance / POL-223344",
        },
        "items": [
            {"part": "Rear Bumper Assembly (OEM)",          "type": "Replace",        "qty": 1, "unit": 12000, "source": "OEM"},
            {"part": "Trunk Lid / Dicky Door",              "type": "Repair + Paint", "qty": 1, "unit": 18000, "source": "OEM"},
            {"part": "Rear Combination Lamp LH (OEM)",      "type": "Replace",        "qty": 1, "unit": 5500,  "source": "OEM"},
            {"part": "Rear Combination Lamp RH (OEM)",      "type": "Replace",        "qty": 1, "unit": 5500,  "source": "OEM"},
            {"part": "Wheel Arch Liner Rear",               "type": "Repair",         "qty": 1, "unit": 3500,  "source": "Aftermarket"},
            {"part": "Rear Number Plate Bracket",           "type": "Replace",        "qty": 1, "unit": 800,   "source": "Aftermarket"},
            {"part": "Labour - Body Repair",                "type": "Labour",         "qty": 1, "unit": 8000,  "source": "-"},
            {"part": "Labour - Paint & Polish",             "type": "Labour",         "qty": 1, "unit": 4000,  "source": "-"},
        ],
        "note": "Rear impact while parked. Scope matches customer complaint. Vehicle brought to Kochi service centre.",
        "is_fraud": False,
    },
]


# ---------------------------------------------------------------------------
# PDF CLASSES
# ---------------------------------------------------------------------------

class GaragePDF(FPDF):
    def __init__(self, data: dict):
        super().__init__()
        self.data = data
        self.set_margins(15, 22, 15)
        self.set_auto_page_break(auto=True, margin=20)

    def header(self):
        ws = self.data["workshop"]
        self.set_fill_color(16, 78, 139)
        self.rect(0, 0, 210, 22, "F")
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(255, 255, 255)
        self.set_y(4)
        self.cell(0, 7, _s(ws["name"]), align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 8)
        self.cell(
            0, 5,
            _s(f"{ws['address']}  |  Ph: {ws['phone']}  |  GSTIN: {ws['gstin']}"),
            align="C", new_x="LMARGIN", new_y="NEXT",
        )
        self.set_text_color(0, 0, 0)
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(120, 120, 120)
        ws = self.data["workshop"]
        self.cell(
            0, 5,
            _s(f"{ws['authorised']}  |  Page {self.page_no()}  |  E&OE - Subject to Workshop Terms & Conditions"),
            align="C",
        )
        self.set_text_color(0, 0, 0)


class FIRPDF(FPDF):
    def __init__(self, data: dict):
        super().__init__()
        self.data = data
        self.set_margins(18, 22, 18)
        self.set_auto_page_break(auto=True, margin=20)

    def header(self):
        self.set_fill_color(0, 84, 42)
        self.rect(0, 0, 210, 22, "F")
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(255, 255, 255)
        self.set_y(4)
        self.cell(0, 6, "GOVERNMENT OF INDIA - INDIAN POLICE SERVICE", align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 8)
        d = self.data
        self.cell(
            0, 5,
            _s(f"District: {d['district']}  |  {d['police_station']}"),
            align="C", new_x="LMARGIN", new_y="NEXT",
        )
        self.set_text_color(0, 0, 0)
        self.ln(3)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(120, 120, 120)
        self.cell(
            0, 5,
            _s(
                f"FIR No. {self.data['fir_no']}  |  "
                f"{self.data['police_station']}  |  "
                f"Page {self.page_no()}  |  Official Document - Not for Commercial Use"
            ),
            align="C",
        )
        self.set_text_color(0, 0, 0)


# ---------------------------------------------------------------------------
# GENERATOR FUNCTIONS
# ---------------------------------------------------------------------------

def generate_garage(data: dict, output_path: str):
    pdf = GaragePDF(data)
    pdf.add_page()

    # Title
    pdf.set_fill_color(232, 244, 255)
    pdf.rect(15, 26, 180, 12, "F")
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(16, 78, 139)
    pdf.set_y(28)
    pdf.cell(0, 8, "VEHICLE REPAIR ESTIMATION SLIP", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    # Job card + date row
    pdf.set_fill_color(245, 245, 245)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(90, 7, _s(f"Job Card No.:  {data['job_card']}"), fill=True, border=1, new_x="RIGHT", new_y="TOP")
    pdf.cell(90, 7, _s(f"Date:  {data['job_date']}"),         fill=True, border=1, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    # Customer details
    cust = data["customer"]
    pdf.set_fill_color(250, 250, 252)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(30, 58, 138)
    pdf.cell(0, 7, "  CUSTOMER & VEHICLE DETAILS", fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)

    def kv(k, v, w_k=55):
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(80, 80, 80)
        pdf.cell(w_k, 6, _s(k) + ":", new_x="RIGHT", new_y="TOP", border="B")
        pdf.set_text_color(20, 20, 20)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(180 - w_k, 6, _s(str(v)), new_x="LMARGIN", new_y="NEXT", border="B")
        pdf.set_text_color(0, 0, 0)

    kv("Customer Name",        cust["name"])
    kv("Vehicle",              cust["vehicle"])
    kv("Registration No.",     cust["reg_no"])
    kv("Odometer Reading",     cust["mileage"])
    kv("Insurance / Policy No.", cust["insurance"])
    pdf.ln(4)

    # Table header
    pdf.set_fill_color(16, 78, 139)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(8,  7, "#",                    fill=True, border=1, align="C",  new_x="RIGHT", new_y="TOP")
    pdf.cell(77, 7, "Part / Service Description", fill=True, border=1,       new_x="RIGHT", new_y="TOP")
    pdf.cell(24, 7, "Work Type",            fill=True, border=1,             new_x="RIGHT", new_y="TOP")
    pdf.cell(10, 7, "Qty",                  fill=True, border=1, align="C",  new_x="RIGHT", new_y="TOP")
    pdf.cell(24, 7, "Source",               fill=True, border=1, align="C",  new_x="RIGHT", new_y="TOP")
    pdf.cell(27, 7, "Amount (Rs.)",         fill=True, border=1, align="R",  new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)

    subtotal = 0
    for i, item in enumerate(data["items"], 1):
        pdf.set_font("Helvetica", "", 8.5)
        fill = (i % 2 == 0)
        pdf.set_fill_color(247, 249, 255) if fill else pdf.set_fill_color(255, 255, 255)
        amount = item["qty"] * item["unit"]
        subtotal += amount
        pdf.cell(8,  6.5, str(i),              fill=fill, border=1, align="C",  new_x="RIGHT", new_y="TOP")
        pdf.cell(77, 6.5, _s(item["part"]),    fill=fill, border=1,             new_x="RIGHT", new_y="TOP")
        pdf.cell(24, 6.5, _s(item["type"]),    fill=fill, border=1,             new_x="RIGHT", new_y="TOP")
        pdf.cell(10, 6.5, str(item["qty"]),    fill=fill, border=1, align="C",  new_x="RIGHT", new_y="TOP")
        pdf.cell(24, 6.5, item["source"],      fill=fill, border=1, align="C",  new_x="RIGHT", new_y="TOP")
        pdf.cell(27, 6.5, f"{amount:,}",       fill=fill, border=1, align="R",  new_x="LMARGIN", new_y="NEXT")

    # Totals
    pdf.ln(2)
    cgst  = round(subtotal * 0.09)
    sgst  = round(subtotal * 0.09)
    total = subtotal + cgst + sgst
    content_w = pdf.w - pdf.l_margin - pdf.r_margin

    def total_row(label, amount, bold=False):
        lw, aw = 42, 30
        pdf.set_x(pdf.w - pdf.r_margin - lw - aw)
        pdf.set_font("Helvetica", "B" if bold else "", 9)
        if bold:
            pdf.set_fill_color(232, 244, 255)
            pdf.cell(lw, 6.5, _s(label),              fill=True, border=1, new_x="RIGHT", new_y="TOP")
            pdf.cell(aw, 6.5, f"Rs. {amount:,}",      fill=True, border=1, align="R", new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.cell(lw, 6.5, _s(label),              border=1, new_x="RIGHT", new_y="TOP")
            pdf.cell(aw, 6.5, f"Rs. {amount:,}",      border=1, align="R", new_x="LMARGIN", new_y="NEXT")

    total_row("Sub-Total",  subtotal)
    total_row("CGST @ 9%",  cgst)
    total_row("SGST @ 9%",  sgst)
    total_row("GRAND TOTAL", total, bold=True)

    pdf.ln(4)
    if data.get("note"):
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(90, 90, 90)
        pdf.multi_cell(0, 5.5, _s(f"Note: {data['note']}"))
        pdf.set_text_color(0, 0, 0)

    if pdf.will_page_break(32):
        pdf.add_page()
    else:
        pdf.ln(6)

    # Signatures
    ws = data["workshop"]
    col_gap = 12
    col_w   = (content_w - col_gap) / 2
    y       = pdf.get_y()
    lx      = pdf.l_margin
    rx      = pdf.l_margin + col_w + col_gap

    pdf.set_draw_color(90, 90, 90)
    pdf.set_line_width(0.25)
    pdf.line(lx + 2, y + 11, lx + col_w - 2, y + 11)
    pdf.line(rx + 2, y + 11, rx + col_w - 2, y + 11)

    pdf.set_font("Helvetica", "BI", 10)
    pdf.set_text_color(25, 25, 25)
    pdf.set_xy(lx + 4, y + 4)
    pdf.cell(col_w - 8, 5, _s(f"Sd/- {cust['name']}"), align="C")
    pdf.set_xy(rx + 4, y + 4)
    pdf.cell(col_w - 8, 5, _s(f"Sd/- {ws['name']}"),   align="C")

    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(0, 0, 0)
    pdf.set_xy(lx, y + 13)
    pdf.cell(col_w, 5, "Customer Signature")
    pdf.set_xy(rx, y + 13)
    pdf.cell(col_w, 5, "Authorised Signatory")

    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(120, 120, 120)
    pdf.set_xy(lx, y + 18)
    pdf.cell(col_w, 5, _s(f"({cust['name']})"))
    pdf.set_xy(rx, y + 18)
    pdf.cell(col_w, 5, _s(f"({ws['name']})"))
    pdf.set_text_color(0, 0, 0)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    pdf.output(output_path)
    return total


def generate_fir(data: dict, output_path: str):
    pdf = FIRPDF(data)
    pdf.add_page()

    # Title
    pdf.set_fill_color(240, 247, 240)
    pdf.rect(18, 27, 174, 11, "F")
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(0, 84, 42)
    pdf.set_y(29)
    pdf.cell(0, 7, "FIRST INFORMATION REPORT (FIR)", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)

    # FIR header fields
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(240, 247, 240)
    pdf.cell(58,  7, _s(f"FIR No.:  {data['fir_no']}"), border=1, fill=True, new_x="RIGHT", new_y="TOP")
    pdf.cell(116, 7, _s(f"Date & Time Filed:  {data['date_filed']}  {data['date_filed_time']}"), border=1, fill=True, new_x="LMARGIN", new_y="NEXT")
    ps_short = data["police_station"].split(",")[0]
    pdf.cell(174, 7, _s(f"Police Station:  {ps_short}"), border=1, fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    CONTENT_W = pdf.w - pdf.l_margin - pdf.r_margin

    def section(title: str):
        pdf.ln(2)
        pdf.set_fill_color(0, 84, 42)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(0, 7, _s(f"  {title}"), fill=True, new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
        pdf.ln(1)

    def fkv(k, v, w_k=60):
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(80, 80, 80)
        pdf.cell(w_k, 6, _s(k) + ":", new_x="RIGHT", new_y="TOP")
        pdf.set_text_color(20, 20, 20)
        pdf.set_font("Helvetica", "B", 9)
        pdf.multi_cell(CONTENT_W - w_k, 6, _s(str(v)), new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)

    # Section 1
    section("SECTION 1 - COMPLAINANT INFORMATION")
    comp = data["complainant"]
    fkv("Name of Complainant",       comp["name"])
    fkv("Father's / Husband's Name", comp["father"])
    fkv("Address",                   comp["address"])
    fkv("Mobile Number",             comp["phone"])
    fkv("Occupation",                comp["occupation"])

    # Section 2
    section("SECTION 2 - INCIDENT DETAILS")
    fkv("Date of Incident",           data["incident_date"])
    fkv("Time of Incident",           data["incident_time"])
    fkv("Place / Location of Incident", data["incident_location"])
    fkv("Nature of Incident",         "Motor Vehicle Accident - Hit and Run / Damage to Property")

    # Section 3
    section("SECTION 3 - VEHICLE DETAILS")
    v = data["vehicle"]
    fkv("Registration Number",        v["reg"])
    fkv("Make / Model",               v["make"])
    fkv("Colour",                     v["colour"])
    fkv("Accused / Offending Vehicle", data["accused_vehicle"])

    # Section 4
    section("SECTION 4 - STATEMENT OF FACTS")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(30, 30, 30)
    pdf.multi_cell(0, 5.5, _s(data["statement"]))
    pdf.set_text_color(0, 0, 0)

    # Section 5
    section("SECTION 5 - ACTION TAKEN / NOTES")
    fkv("Action Taken",        data["action"])
    fkv("Station Note",        data["station_note"])
    fkv("Investigating Officer", data["officer"])

    # Fraud / mismatch demo box
    if data.get("is_fraud"):
        pdf.ln(4)
        pdf.set_fill_color(255, 240, 240)
        pdf.set_draw_color(200, 0, 0)
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(180, 0, 0)
        fraud_note = data.get("fraud_note", "[FOR DEMO PURPOSES ONLY]")
        pdf.multi_cell(0, 6, _s(fraud_note), border=1)
        pdf.set_text_color(0, 0, 0)
        pdf.set_draw_color(0, 0, 0)

    if pdf.will_page_break(34):
        pdf.add_page()
    else:
        pdf.ln(8)

    # Signatures
    col_gap     = 12
    col_w       = (CONTENT_W - col_gap) / 2
    y           = pdf.get_y()
    lx          = pdf.l_margin
    rx          = pdf.l_margin + col_w + col_gap
    officer_name = data["officer"].split(",")[0]

    pdf.set_draw_color(90, 90, 90)
    pdf.set_line_width(0.25)
    pdf.line(lx + 2, y + 11, lx + col_w - 2, y + 11)
    pdf.line(rx + 2, y + 11, rx + col_w - 2, y + 11)

    pdf.set_font("Helvetica", "BI", 10)
    pdf.set_text_color(25, 25, 25)
    pdf.set_xy(lx + 4, y + 4)
    pdf.cell(col_w - 8, 5, _s(f"Sd/- {comp['name']}"),   align="C")
    pdf.set_xy(rx + 4, y + 4)
    pdf.cell(col_w - 8, 5, _s(f"Sd/- {officer_name}"),   align="C")

    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(0, 0, 0)
    pdf.set_xy(lx, y + 13)
    pdf.cell(col_w, 5, "Complainant Signature")
    pdf.set_xy(rx, y + 13)
    pdf.cell(col_w, 5, "Station Officer Signature & Stamp")

    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(120, 120, 120)
    pdf.set_xy(lx, y + 18)
    pdf.cell(col_w, 5, _s(f"({comp['name']})"))
    pdf.set_xy(rx, y + 18)
    pdf.cell(col_w, 5, _s(f"({officer_name})"))
    pdf.set_text_color(0, 0, 0)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    pdf.output(output_path)


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate test FIR and garage estimate PDFs for ClaimIntel."
    )
    parser.add_argument("--firs",    action="store_true", help="Generate FIR PDFs only")
    parser.add_argument("--garages", action="store_true", help="Generate garage estimate PDFs only")
    args = parser.parse_args()

    do_firs    = args.firs    or (not args.firs and not args.garages)
    do_garages = args.garages or (not args.firs and not args.garages)

    if do_firs:
        print("\n--- Generating FIR Reports ---")
        for fir in FIRS:
            out  = os.path.join(FIR_DIR, fir["filename"])
            generate_fir(fir, out)
            tag  = " [MISMATCH DEMO - KEEP AS-IS]" if fir["is_fraud"] else ""
            print(f"  OK  {fir['filename']}  incident: {fir['incident_date']}{tag}")

    if do_garages:
        print("\n--- Generating Garage Estimate Slips ---")
        for g in GARAGES:
            out   = os.path.join(GARAGE_DIR, g["filename"])
            total = generate_garage(g, out)
            tag   = " [INFLATED DEMO - KEEP AS-IS]" if g["is_fraud"] else ""
            print(f"  OK  {g['filename']}  date: {g['job_date']}  total: Rs. {total:,}{tag}")

    print(f"\nDone. Files written to tests/FIR/ and tests/Garage Slip/")


if __name__ == "__main__":
    main()
