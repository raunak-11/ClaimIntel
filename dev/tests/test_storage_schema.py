"""CSV schema integrity — the invariants that silently corrupt data when broken.

Three separate files declare the claims-CSV column list: `storage.CSV_FIELDS`,
`scripts/reset_claims.py::CLAIMS_FIELDS`, and the header row of `data/claims.csv`
itself. Until now the only thing keeping them aligned was a comment reading
"Keep in sync if those change". These tests make that an enforced invariant.

The failure mode is silent, which is why it deserves tests rather than care:
`_ensure_csv()` only writes a header when the file is ABSENT, so widening
CSV_FIELDS against an existing file leaves a narrow header while `save_claim`
appends full-width rows. `csv.DictReader` then files every surplus value under
the `None` key, every subsequent read is shifted, and nothing raises.
"""

import csv
import importlib.util
import os

import pytest

import storage
from config import DATA_DIR

_SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")


def _load_script(name: str):
    """Import a file under scripts/ — it is not a package, so no plain import."""
    path = os.path.join(_SCRIPTS, f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ── Cross-file declarations must agree ────────────────────────────────────────

def test_reset_script_claims_fields_match_storage():
    """A reset that writes the wrong header corrupts every claim written after."""
    assert _load_script("reset_claims").CLAIMS_FIELDS == storage.CSV_FIELDS


def test_reset_script_token_fields_match_the_tracker():
    from services import token_tracker
    assert _load_script("reset_claims").TOKEN_USAGE_FIELDS == token_tracker.FIELDS


def test_policies_csv_header_matches_policy_fields():
    path = os.path.join(DATA_DIR, "policies.csv")
    with open(path, newline="", encoding="utf-8") as f:
        header = next(csv.reader(f))
    assert header == storage.POLICY_FIELDS


def test_claims_csv_header_matches_csv_fields():
    """The shipped claims.csv is header-only; it must still be the RIGHT header."""
    storage._ensure_csv()                      # migrates in place if stale
    with open(storage.CLAIMS_CSV, newline="", encoding="utf-8") as f:
        header = next(csv.reader(f))
    assert header == storage.CSV_FIELDS


# ── Migration ─────────────────────────────────────────────────────────────────

_OLD_HEADER = [
    "claim_id", "policy_no", "claimant", "phone", "vehicle",
    "claim_type", "incident_date", "incident_location", "claim_amount",
    "description", "status", "created_at",
    "garage_estimate_amount", "garage_workshop_name", "fir_number",
]


@pytest.fixture
def old_csv(tmp_path, monkeypatch):
    """A pre-migration claims.csv with one row, wired in as the live file."""
    path = tmp_path / "claims.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_OLD_HEADER)
        w.writeheader()
        w.writerow({
            "claim_id": "CLM-2026-08-000001", "policy_no": "POL-112233",
            "claimant": "enc:gAAAAABtest_ciphertext_must_survive==",
            "phone": "enc:gAAAAABtest_phone_ciphertext==",
            "vehicle": "Kia Seltos HTX Plus (TN12AJ1603)",
            "claim_type": "Motor - Own Damage", "incident_date": "2026-07-21T12:15",
            "incident_location": "Ulundurpet, Tamil Nadu", "claim_amount": "65400",
            "description": "front end damage", "status": "Approved",
            "created_at": "2026-08-14", "garage_estimate_amount": "54280",
            "garage_workshop_name": "Kia Authorised", "fir_number": "0511/2026",
        })
    monkeypatch.setattr(storage, "CLAIMS_CSV", str(path))
    return path


def test_an_old_claims_csv_is_widened_to_the_current_header(old_csv):
    assert storage._migrate_csv_header() is True
    with open(old_csv, newline="", encoding="utf-8") as f:
        assert next(csv.reader(f)) == storage.CSV_FIELDS


def test_migration_preserves_existing_values_and_blanks_the_new_columns(old_csv):
    storage._migrate_csv_header()
    with open(old_csv, newline="", encoding="utf-8") as f:
        row = next(csv.DictReader(f))
    assert row["claim_id"] == "CLM-2026-08-000001"
    assert row["garage_estimate_amount"] == "54280"
    assert row["fir_number"] == "0511/2026"
    for new_col in ("intimation_at", "surveyor_appointed_at",
                    "survey_report_at", "decision_at"):
        assert row[new_col] == ""


def test_migration_copies_encrypted_pii_verbatim(old_csv):
    """Never decrypt/re-encrypt: a rotated or absent key would destroy the column."""
    storage._migrate_csv_header()
    with open(old_csv, newline="", encoding="utf-8") as f:
        row = next(csv.DictReader(f))
    assert row["claimant"] == "enc:gAAAAABtest_ciphertext_must_survive=="
    assert row["phone"] == "enc:gAAAAABtest_phone_ciphertext=="


def test_migration_is_idempotent(old_csv):
    assert storage._migrate_csv_header() is True
    assert storage._migrate_csv_header() is False      # already current
    assert storage._migrate_csv_header() is False


def test_saving_after_migration_keeps_every_row_the_header_width(old_csv):
    """The corruption path: full-width rows under a narrow header."""
    storage._ensure_csv()
    storage.save_claim({"claim_id": "CLM-2026-08-000002", "policy_no": "POL-445566",
                        "claimant": "Test User", "phone": "9999999999"})
    with open(old_csv, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    width = len(storage.CSV_FIELDS)
    assert all(len(r) == width for r in rows), [len(r) for r in rows]
    with open(old_csv, newline="", encoding="utf-8") as f:
        assert all(None not in r for r in csv.DictReader(f)), "overflow under the None key"


def test_migration_survives_a_header_only_file(tmp_path, monkeypatch):
    path = tmp_path / "claims.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=_OLD_HEADER).writeheader()
    monkeypatch.setattr(storage, "CLAIMS_CSV", str(path))
    assert storage._migrate_csv_header() is True
    with open(path, newline="", encoding="utf-8") as f:
        assert next(csv.reader(f)) == storage.CSV_FIELDS


def test_migration_survives_a_completely_empty_file(tmp_path, monkeypatch):
    path = tmp_path / "claims.csv"
    path.write_text("", encoding="utf-8")
    monkeypatch.setattr(storage, "CLAIMS_CSV", str(path))
    storage._migrate_csv_header()               # must not raise on StopIteration
    with open(path, newline="", encoding="utf-8") as f:
        assert next(csv.reader(f)) == storage.CSV_FIELDS


def test_the_csv_lock_is_reentrant():
    """save_claim holds the lock and calls _ensure_csv, which takes it again.

    A plain threading.Lock deadlocks on that nesting; this is the guard against
    someone "simplifying" RLock back to Lock.
    """
    with storage._csv_lock:
        with storage._csv_lock:
            pass
