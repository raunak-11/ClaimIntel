"""GaniParser document path — PII masking and the dual-value contract.

The invariant these guard: parsed documents stay CLEAR in memory (fraud checks
compare real registration numbers and holder names against the policy) and are
MASKED at every egress — disk, UI, PDF, and LLM prompts. Breaking either half is
silent: masking too much makes fraud checks stop firing, masking too little
leaks PII to a third-party LLM.
"""

from agents.fraud_intelligence import _run_fraud_checks
from services import gani_redaction as gr
from services.gani_schemas import SCHEMAS
from services.pii import build_llm_safe_text

DL = {
    "doc_type": "license", "holder_name": "Vijay Madeshiya",
    "dl_number": "DL0420110149646", "date_of_birth": "1988-03-14",
    "valid_till": "2032-01-01", "vehicle_classes": ["LMV"],
}
RC = {
    "doc_type": "rc", "reg_no": "MH 12 AB 1234", "owner_name": "Vijay Madeshiya",
    "chassis_no": "MA3EYD1S1NB123456", "engine_no": "K12MN1234567",
}
ESTIMATE = {
    "doc_type": "estimate", "gstin": "27AAECS1234F1Z5", "total_estimate_inr": 50386,
    "workshop_address": "12 MG Road, Pune",
    "line_items": [{"part": "FRT BPR ASSY", "type": "Replace", "amount": 18000}],
}


def test_identifiers_masked_for_display():
    out = gr.redact_parsed(DL, "license")
    assert out["dl_number"] != DL["dl_number"]
    assert out["dl_number"].startswith("DL") and out["dl_number"].endswith("46")
    assert gr.redact_parsed(RC, "rc")["chassis_no"] != RC["chassis_no"]
    assert gr.redact_parsed(ESTIMATE, "estimate")["gstin"] != ESTIMATE["gstin"]


def test_vehicle_registration_is_never_masked():
    """Operationally required — FC-20/FC-29 match it against the policy, and it
    is already on the policy record. Same call services/pii.py documents."""
    assert gr.redact_parsed(RC, "rc", for_llm=True)["reg_no"] == "MH 12 AB 1234"


def test_names_clear_for_display_but_masked_for_the_llm():
    assert gr.redact_parsed(DL, "license")["holder_name"] == "Vijay Madeshiya"
    assert gr.redact_parsed(DL, "license", for_llm=True)["holder_name"] == "Vijay M."


def test_redaction_never_mutates_the_caller_s_dict():
    """The clear original is what fraud checks read; mutating it in place would
    mask the values they compare."""
    gr.redact_parsed(DL, "license", for_llm=True)
    gr.redact_docs({"license": DL, "rc": RC}, for_llm=True)
    assert DL["dl_number"] == "DL0420110149646"
    assert RC["owner_name"] == "Vijay Madeshiya"


def test_non_string_fields_survive_masking():
    """settlement_calc sums line_items and total_estimate_inr — coercing them to
    masked strings would break the repair-basis arithmetic."""
    out = gr.redact_parsed(ESTIMATE, "estimate")
    assert out["total_estimate_inr"] == 50386
    assert out["line_items"][0]["amount"] == 18000
    assert gr.redact_parsed(DL, "license")["vehicle_classes"] == ["LMV"]


def test_redact_docs_passes_through_non_document_entries():
    docs = {"license": DL, "dashcam_frames": ["a.jpg"], "telematics": {"gps": 1}}
    out = gr.redact_docs(docs)
    assert out["dashcam_frames"] == ["a.jpg"]
    assert out["telematics"] == {"gps": 1}


def test_known_pii_masked_inside_free_text_before_a_prompt():
    """Fraud-check details quote real values (FC-29 names the DL holder), and
    those strings are concatenated into the fraud and settlement prompts."""
    claim = {"claimant": "Vijay Madeshiya", "phone": "9567890123"}
    docs = {"license": DL, "rc": RC, "estimate": ESTIMATE}
    text = "DL holder 'Vijay Madeshiya' mismatch; DL0420110149646 expired; GSTIN 27AAECS1234F1Z5"
    out = build_llm_safe_text(text, claim, docs)
    assert "Vijay Madeshiya" not in out
    assert "DL0420110149646" not in out
    assert "27AAECS1234F1Z5" not in out
    assert "Vijay M." in out


def test_fraud_checks_still_fire_on_clear_documents():
    """The regression that the dual-value model exists to prevent: FC-29 must
    still detect a wrong-vehicle RC."""
    claim = {
        "claim_id": "CLM-TEST", "claimant": "Vijay Madeshiya", "phone": "9567890123",
        "vehicle": "Maruti Swift (MH 12 AB 1234)", "policy_no": "POL-1",
        "incident_date": "2026-07-01", "claim_type": "Own Damage",
        "description": "rear-ended", "claim_amount": 50386,
    }
    wrong_rc = dict(RC, reg_no="KA 05 ZZ 9999")
    checks, _ = _run_fraud_checks(claim, {}, {"license": DL, "rc": wrong_rc, "estimate": ESTIMATE})
    fc29 = next(c for c in checks if c["id"] == "FC-29")
    assert fc29["status"] == "flag"
    assert "KA 05 ZZ 9999" in fc29["detail"]


def test_every_schema_field_the_fraud_checks_read_is_present():
    """A key renamed in gani_schemas is a fraud check that silently stops
    firing, because the GaniParser path would emit a name nothing reads."""
    for doc_type, required in (
        ("rc", ("reg_no", "owner_name")),
        ("license", ("holder_name", "valid_till", "dl_number")),
        ("fir", ("vehicle_reg_in_fir", "fir_number")),
        ("estimate", ("total_estimate_inr", "line_items")),
    ):
        fields = SCHEMAS[doc_type]["fields"]
        for key in required:
            assert f'"{key}"' in fields, f"{doc_type}.{key} missing from schema"
