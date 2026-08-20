"""
Extraction schemas for the GaniParser document path (services/gani_parser.py).

Container format mirrors GaniParser's own `eval_schemas.SCHEMAS`
({"instructions": ..., "fields": ...}) so the two stay recognisably the same
product, but the FIELD SHAPES are this project's, not GaniParser's:

  - GaniParser ships 12 schemas (Cheque, Aadhaar, PAN, Invoice, medical, ...)
    and NONE of them are motor documents. These four are new.
  - GaniParser's closest analogue to a garage estimate is `Invoice`, which
    flattens line items into "Line Item 1 - Description" ... and CAPS THEM AT
    THREE. A garage estimate routinely has 10-20 lines and settlement_calc.py
    sums all of them, so adopting that shape would silently under-count the
    repair basis. We keep the nested `line_items` array instead.

Every key below matches what the existing Groq prompts in
services/document_parser.py already emit, because both paths write the same
parsed_{doc_type}.json and the same consumers read it (fraud_intelligence.py's
reg/name matching, pricing_engine.py, the Documents tab, the PDF report). A key
renamed here is a fraud check that silently stops firing.
"""

_COMMON_RULES = (
    "- Use the provided JSON schema to structure the extracted data.\n"
    "- Include only the fields in the schema; no extra fields.\n"
    "- If a field is not present in the text, return null.\n"
    "- Return strictly JSON, no markdown fences, no commentary.\n"
    "- Do not create nested JSON beyond the schema provided.\n"
    "- Dates must be normalised to YYYY-MM-DD.\n"
    "- The input is OCR output and may contain recognition errors. Extract what is\n"
    "  actually written; if a value is garbled or absent, return null rather than\n"
    "  guessing at a plausible-looking one — a confidently wrong value is worse\n"
    "  than a missing one.\n"
)

# Authenticity is deliberately ABSENT from every schema below. These prompts are
# fed OCR TEXT, and OCR has already discarded every visual signal forgery
# detection depends on — mismatched fonts, a stamp with unnaturally perfect
# edges, a template that doesn't match the standard Indian layout. Asking a text
# model to judge authenticity from OCR output would produce confident nonsense
# and feed it straight into FC-28, which weights an authenticity flag heavily.
# It is therefore a separate IMAGE call —
# grounding_client.assess_document_authenticity(), merged in by gani_parser.py.

SCHEMAS: dict[str, dict[str, str]] = {
    "estimate": {
        "instructions": (
            "You are a motor insurance analyst reading a garage repair estimation slip.\n"
            + _COMMON_RULES
            + "- Retrieve EVERY line item without omission; do not truncate the list.\n"
            "- `type` must be one of: Replace, Repair, Paint, Labour. Pick the closest match.\n"
            "- `amount` and `total_estimate_inr` are numbers in INR: digits only, no currency\n"
            "  symbol, no thousands separators. Use 0 if genuinely absent.\n"
            "- Garage slips use heavy shorthand (e.g. 'FRT BPR ASSY'). Copy the part name\n"
            "  through exactly as printed; normalisation happens downstream.\n"
        ),
        "fields": """{
  "doc_type": "garage_estimate",
  "workshop_name": null,
  "workshop_address": null,
  "gstin": null,
  "total_estimate_inr": 0,
  "line_items": [{"part": "", "type": "Replace|Repair|Paint|Labour", "amount": 0}],
  "date_issued": null,
  "vehicle_reg_mentioned": null
}""",
    },
    "fir": {
        "instructions": (
            "You are a motor insurance analyst reading an Indian First Information Report (FIR).\n"
            + _COMMON_RULES
            + "- An FIR states two distinct dates: when the report was FILED and when the\n"
            "  incident OCCURRED. Keep them in their own fields; do not conflate them.\n"
            "- Vehicle registration numbers must be copied exactly as printed, including\n"
            "  spacing and hyphens as they appear.\n"
            "- `statutory_sections` lists the statute and section numbers the FIR is\n"
            "  registered under, exactly as printed (e.g. 'Section 279 IPC',\n"
            "  'Section 184 MV Act'). Return an empty list if none are stated.\n"
        ),
        "fields": """{
  "doc_type": "fir",
  "fir_number": null,
  "police_station": null,
  "date_filed": null,
  "incident_date_in_fir": null,
  "incident_location_in_fir": null,
  "vehicle_reg_in_fir": null,
  "complainant_name_in_fir": null,
  "statutory_sections": []
}""",
    },
    "license": {
        "instructions": (
            "You are a motor insurance KYC analyst reading an Indian Driving Licence.\n"
            + _COMMON_RULES
            + "- `vehicle_classes` is a list of the licence's vehicle class codes as printed\n"
            "  (e.g. LMV, MCWG, TRANS). Return an empty list if none are legible.\n"
            "- Do not confuse the date of birth with the issue date or the validity date.\n"
        ),
        "fields": """{
  "doc_type": "license",
  "holder_name": null,
  "dl_number": null,
  "date_of_birth": null,
  "valid_till": null,
  "vehicle_classes": [],
  "issuing_authority": null
}""",
    },
    # ClaimIntel's own hard-copy claim form (services/claim_form.py) — the
    # customer handwrites it, photographs/scans it, and the New Claim screen
    # auto-fills from this extraction (POST /api/claims/extract-form). Unlike
    # the four supporting documents above, this parse happens BEFORE the claim
    # exists, its output goes straight back to the person who wrote the form,
    # and nothing is persisted — so nulls here are harmless: the customer just
    # fills that field by hand in the UI instead.
    "claim_form": {
        "instructions": (
            "You are a motor insurance intake analyst reading a HANDWRITTEN motor\n"
            "insurance claim form (ClaimIntel's standard single-page form). The printed\n"
            "template text and the handwritten answers are mixed together in the OCR output.\n"
            + _COMMON_RULES
            + "- CHECKBOXES: a marked checkbox appears in the OCR as a stray mark — 'X', 'x',\n"
            "  'V', '/' or a tick-like fragment — on or immediately next to the option's\n"
            "  printed label (e.g. a line reading 'X Own Damage'). An option with no such\n"
            "  mark is unticked. If no option is marked, return null.\n"
            "- `type_of_loss` must be exactly one of: Own Damage, Theft, Third Party.\n"
            "- `incident_time` is 24-hour 'HH:MM'. The form writes the time next to AM/PM\n"
            "  checkboxes — apply the marked meridiem (e.g. '3:20' + PM -> '15:20').\n"
            "- `driver_relation` must be one of: Owner, Paid Driver, Relative/Friend.\n"
            "- `police_reported` is true/false from the Yes/No boxes, null if unmarked.\n"
            "- `estimated_repair_cost_inr` is a number in INR: digits only, no currency\n"
            "  symbol, no thousands separators. Use 0 if genuinely absent.\n"
            "- `description` is the customer's handwritten accident narrative, joined\n"
            "  across its ruled lines into one string, exactly as written.\n"
            "- NEVER return printed template text as a value: field labels, the italic\n"
            "  hints (DD/MM/YYYY, HH:MM, 'road / area / city...'), the declaration\n"
            "  paragraph and the footer are part of the blank form, not answers.\n"
        ),
        "fields": """{
  "doc_type": "claim_form",
  "policy_no": null,
  "insured_name": null,
  "mobile": null,
  "email": null,
  "vehicle_reg": null,
  "incident_date": null,
  "incident_time": null,
  "incident_location": null,
  "type_of_loss": null,
  "description": null,
  "workshop_name": null,
  "estimated_repair_cost_inr": 0,
  "driver_name": null,
  "driver_dl_number": null,
  "driver_relation": null,
  "police_reported": null,
  "fir_number": null,
  "police_station": null
}""",
    },
    "rc": {
        "instructions": (
            "You are a motor insurance KYC analyst reading an Indian vehicle Registration\n"
            "Certificate (RC).\n"
            + _COMMON_RULES
            + "- `hypothecated_to` is the bank/financier named in a 'Financer' or\n"
            "  'Hypothecation' field. Return null if the RC shows no financer at all —\n"
            "  null here means the vehicle is owned outright, so do not invent a value.\n"
            "- Chassis and engine numbers are often printed only in part; return whatever\n"
            "  is legible rather than nothing.\n"
            "- `reg_date` is the vehicle DATE OF REGISTRATION. It drives the depreciation"
            " slab on every claim, so extract it whenever it is legible.\n"
            "  An RC lays its fields out in TWO COLUMNS, which in a PDF text layer arrives"
            " as both LABELS first and then both VALUES:\n"
            "      Date of Registration\n"
            "      Registration Valid Upto\n"
            "      15-06-2022\n"
            "      15-06-2037\n"
            "  Pair them by POSITION - the first value belongs to the first label."
            " Return the REGISTRATION date (the earlier one), never the Valid Upto"
            " expiry date.\n"
            "  Indian RCs print dd-mm-yyyy, so 15-06-2022 is 2022-06-15, not 2022-15-06."
            " The same two-column pairing applies to Chassis / Engine Number.\n"
        ),
        "fields": """{
  "doc_type": "rc",
  "reg_no": null,
  "owner_name": null,
  "maker_model": null,
  "reg_date": null,
  "chassis_no": null,
  "engine_no": null,
  "fuel_type": null,
  "hypothecated_to": null
}""",
    },
}
