"""A claim must be adjudicated against ITS OWN policy.

Every consumer resolved the policy with `get_policy_by_phone(claim["phone"])`,
which returns the FIRST row matching that number, while `claim["policy_no"]` —
recorded at filing — went unread. `get_policy_by_no` did not exist at all.

One household with two cars on one registered mobile is entirely ordinary in
India. The demo data has 15 policies with 15 distinct phones, which is the only
reason this never surfaced.
"""
import pytest

import storage


CAR_A = {"policy_no": "POL-AAA111", "phone": "9000000001", "customer_name": "R Kumar",
         "vehicle_make": "Maruti", "vehicle_model": "Alto K10", "vehicle_year": "2015",
         "coverage_type": "Third Party", "sum_insured": "150000", "engine_cc": "796",
         "policy_start": "2019-01-01", "policy_end": "2020-01-01",
         "voluntary_deductible": "0", "ncb_pct": "0", "add_ons": ""}
CAR_B = {"policy_no": "POL-BBB222", "phone": "9000000001", "customer_name": "R Kumar",
         "vehicle_make": "Kia", "vehicle_model": "Seltos HTX Plus", "vehicle_year": "2022",
         "coverage_type": "Comprehensive", "sum_insured": "950000", "engine_cc": "1497",
         "policy_start": "2024-08-15", "policy_end": "2027-08-15",
         "voluntary_deductible": "0", "ncb_pct": "20", "add_ons": "zero_dep"}


@pytest.fixture
def household(monkeypatch):
    """Two vehicles, one registered mobile. CAR_A is listed first."""
    monkeypatch.setattr(storage, "get_all_policies", lambda: [CAR_A, CAR_B])


def test_the_claims_own_policy_number_wins(household):
    claim = {"claim_id": "CLM-1", "policy_no": "POL-BBB222", "phone": "9000000001"}
    assert storage.get_policy_for_claim(claim)["policy_no"] == "POL-BBB222"


def test_the_phone_lookup_alone_returns_the_wrong_car(household):
    """Documents the defect: the phone resolves to whichever policy is listed
    first, which is not necessarily the one the claim was filed against."""
    assert storage.get_policy_by_phone("9000000001")["policy_no"] == "POL-AAA111"


@pytest.mark.parametrize("field, a, b", [
    ("coverage_type", "Third Party", "Comprehensive"),
    ("sum_insured", "150000", "950000"),
    ("engine_cc", "796", "1497"),
    ("vehicle_year", "2015", "2022"),
    ("add_ons", "", "zero_dep"),
    ("policy_end", "2020-01-01", "2027-08-15"),
])
def test_every_money_field_would_have_come_from_the_wrong_car(household, field, a, b):
    """Each of these decides real money: cover admissibility, the total-loss
    threshold and IDV cap, the compulsory deductible, the depreciation slab,
    whether Zero-Dep applies, and whether the policy was even in force."""
    claim = {"claim_id": "CLM-1", "policy_no": "POL-BBB222", "phone": "9000000001"}
    assert storage.get_policy_by_phone(claim["phone"])[field] == a      # wrong
    assert storage.get_policy_for_claim(claim)[field] == b              # right


def test_a_third_party_policy_would_have_been_used_for_an_own_damage_claim(household):
    """The sharpest consequence: the eligibility gate's scope-of-cover hard stop
    is decided on coverage_type. Resolving by phone hands it CAR_A's Third Party
    cover for a claim filed on CAR_B's Comprehensive policy — or the reverse,
    admitting an own-damage claim on a policy that does not cover it."""
    from services import coverage as cov
    claim = {"claim_id": "CLM-1", "policy_no": "POL-BBB222", "phone": "9000000001",
             "claim_type": "Motor - Own Damage"}
    kind = cov.classify_claim_type(claim)
    wrong = cov.classify_coverage(storage.get_policy_by_phone(claim["phone"]))
    right = cov.classify_coverage(storage.get_policy_for_claim(claim))
    assert cov.is_covered(wrong, kind) is False      # would have been rejected
    assert cov.is_covered(right, kind) is True       # is actually covered


def test_an_expired_sibling_policy_would_have_failed_a_live_claim(household):
    """CAR_A lapsed in 2020; CAR_B runs to 2027. A 2026 loss on CAR_B would be
    repudiated as 'policy expired' against the wrong vehicle's dates."""
    claim = {"claim_id": "CLM-1", "policy_no": "POL-BBB222", "phone": "9000000001"}
    assert storage.get_policy_by_phone(claim["phone"])["policy_end"] < "2026-08-20"
    assert storage.get_policy_for_claim(claim)["policy_end"] > "2026-08-20"


def test_falls_back_to_phone_when_the_policy_number_is_unknown(household):
    """Older claims filed before policy_no was reliable must still resolve."""
    assert storage.get_policy_for_claim({"phone": "9000000001"})["policy_no"] == "POL-AAA111"


def test_returns_none_when_neither_identifier_matches(household):
    assert storage.get_policy_for_claim({"policy_no": "NOPE", "phone": "0000"}) is None


def test_lookup_is_case_and_whitespace_tolerant(household):
    assert storage.get_policy_by_no("  pol-bbb222 ")["policy_no"] == "POL-BBB222"


def test_no_claim_path_still_resolves_a_policy_by_phone():
    """GET /api/customers/lookup is pre-claim — the phone IS the identifier
    there, so that one caller is correct and must keep working."""
    import inspect
    import main
    assert "get_policy_by_phone" in inspect.getsource(main.lookup_customer)


def test_no_claim_context_caller_still_uses_the_phone_lookup():
    """Nothing that HAS a claim may resolve by phone any more."""
    import os
    import re
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    offenders = []
    for dirpath, _d, files in os.walk(os.path.join(root, "backend")):
        if "__pycache__" in dirpath:
            continue
        for name in files:
            if not name.endswith(".py") or name == "storage.py":
                continue
            full = os.path.join(dirpath, name)
            for i, line in enumerate(open(full, encoding="utf-8"), 1):
                if line.lstrip().startswith("#"):
                    continue
                # by-phone resolution that reads a phone OFF a claim/row dict
                if re.search(r"get_policy_by_phone\(\s*\w+\.get\(", line):
                    offenders.append(f"{os.path.relpath(full, root)}:{i}")
    assert not offenders, (
        f"these resolve a claim's policy by phone instead of policy_no: {offenders}")
