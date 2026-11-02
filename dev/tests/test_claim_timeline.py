"""IRDAI service-standard timeline — breaches, pending measurement, and the
guarantee that this module never invents money.
"""

from datetime import datetime, timedelta

import pytest

from services import claim_timeline as ct

NOW = datetime(2026, 8, 18, 12, 0, 0)


def _claim(**over):
    base = {
        "claim_amount": "54280",
        "created_at": "2026-08-14",
        "intimation_at": "2026-08-14T10:00:00",
        "surveyor_appointed_at": "",
        "survey_report_at": "",
        "decision_at": "",
    }
    base.update(over)
    return base


def _by_key(tl, key):
    return next(m for m in tl["milestones"] if m["key"] == key)


# ── The happy path ────────────────────────────────────────────────────────────

def test_all_milestones_inside_their_limits_is_compliant():
    tl = ct.build_timeline(_claim(
        surveyor_appointed_at="2026-08-14T18:00:00",   # +8 h   (limit 24 h)
        survey_report_at="2026-08-16T10:00:00",        # +40 h  (limit 15 d)
        decision_at="2026-08-17T10:00:00",             # +24 h  (limit 7 d)
    ), now=NOW)
    assert tl["compliant"] is True
    assert tl["breaches"] == []
    assert tl["breach_count"] == 0
    assert all(m["status"] in ("recorded", "met") for m in tl["milestones"])


# ── Each individual breach ────────────────────────────────────────────────────

def test_surveyor_appointed_after_24_hours_is_a_breach():
    tl = ct.build_timeline(_claim(
        surveyor_appointed_at="2026-08-16T10:00:00",   # +48 h
    ), now=NOW)
    m = _by_key(tl, "surveyor_appointed")
    assert m["breach"] is True
    assert m["status"] == "breached"
    assert "surveyor_appointed" in {b["key"] for b in tl["breaches"]}
    assert tl["compliant"] is False


def test_survey_report_after_15_days_is_a_breach():
    tl = ct.build_timeline(_claim(
        surveyor_appointed_at="2026-08-14T12:00:00",
        survey_report_at="2026-09-01T12:00:00",        # +18 days
    ), now=datetime(2026, 9, 2, 12, 0, 0))
    assert _by_key(tl, "survey_report")["breach"] is True
    assert tl["compliant"] is False


def test_settlement_more_than_7_days_after_the_report_is_a_breach():
    tl = ct.build_timeline(_claim(
        surveyor_appointed_at="2026-08-14T12:00:00",
        survey_report_at="2026-08-15T12:00:00",
        decision_at="2026-08-30T12:00:00",             # +15 days
    ), now=datetime(2026, 8, 31, 12, 0, 0))
    assert _by_key(tl, "settled")["breach"] is True
    assert tl["compliant"] is False


# ── Pending milestones measure against NOW ────────────────────────────────────

def test_a_pending_milestone_measures_elapsed_against_now():
    """A claim sitting undecided must show a LIVE breach, not a blank row."""
    tl = ct.build_timeline(_claim(), now=NOW)          # intimated 4 days ago
    m = _by_key(tl, "surveyor_appointed")
    assert m["at"] is None
    assert m["status"] == "pending_breached"
    assert m["breach"] is True
    assert m["elapsed_hours"] == pytest.approx(98.0, abs=0.1)
    assert m["progress_pct"] == 100                    # clamped, never overflows


def test_a_pending_milestone_inside_its_limit_is_pending_not_breached():
    tl = ct.build_timeline(_claim(intimation_at="2026-08-18T06:00:00"), now=NOW)
    m = _by_key(tl, "surveyor_appointed")
    assert m["status"] == "pending"
    assert m["breach"] is False
    assert m["progress_pct"] == 25                     # 6 h of 24 h


def test_progress_pct_never_exceeds_100():
    tl = ct.build_timeline(_claim(intimation_at="2026-01-01T00:00:00"), now=NOW)
    assert all((m["progress_pct"] or 0) <= 100 for m in tl["milestones"])


# ── Tri-state compliance ──────────────────────────────────────────────────────

def test_compliance_is_none_while_the_chain_is_incomplete_and_clean():
    """Half-finished is not compliant — it is not yet decidable."""
    tl = ct.build_timeline(_claim(
        intimation_at="2026-08-18T10:00:00",
        surveyor_appointed_at="2026-08-18T11:00:00",   # met, rest pending & clean
    ), now=NOW)
    assert tl["compliant"] is None
    assert tl["breaches"] == []


def test_a_breach_beats_incompleteness():
    tl = ct.build_timeline(_claim(), now=NOW)
    assert tl["compliant"] is False


# ── Fallbacks ─────────────────────────────────────────────────────────────────

def test_missing_intimation_falls_back_to_created_at_and_flags_date_only():
    tl = ct.build_timeline(_claim(intimation_at=""), now=NOW)
    m = _by_key(tl, "intimation")
    assert m["at"] == "2026-08-14T00:00:00"
    assert m.get("precision") == "date_only"


def test_a_claim_with_no_timestamps_at_all_does_not_raise():
    tl = ct.build_timeline({}, now=NOW)
    assert tl["milestones"]
    assert tl["compliant"] in (None, False)


def test_decision_falls_back_to_the_stored_adjuster_timestamp():
    tl = ct.build_timeline(
        _claim(surveyor_appointed_at="2026-08-14T12:00:00",
               survey_report_at="2026-08-15T12:00:00"),
        {"adjuster_decision": {"timestamp": "2026-08-16 09:30"}},
        now=NOW)
    assert _by_key(tl, "settled")["at"] == "2026-08-16T09:30:00"


# ── Surveyor threshold reuses config ──────────────────────────────────────────

def test_surveyor_requirement_reads_the_config_threshold(monkeypatch):
    monkeypatch.setattr(ct, "SURVEYOR_THRESHOLD", 10_000)
    assert ct.build_timeline(_claim(claim_amount="54280"), now=NOW)["surveyor_required"] is True
    monkeypatch.setattr(ct, "SURVEYOR_THRESHOLD", 1_000_000)
    assert ct.build_timeline(_claim(claim_amount="54280"), now=NOW)["surveyor_required"] is False


def test_a_non_numeric_claim_amount_does_not_raise():
    tl = ct.build_timeline(_claim(claim_amount="Pending AI"), now=NOW)
    assert tl["surveyor_required"] is False


# ── The guarantee ─────────────────────────────────────────────────────────────

def test_no_penalty_or_interest_key_is_ever_emitted():
    """Decision: this module flags breaches, it never turns them into rupees.

    Enforced against future drift — adding a per-day penalty to a payout is a
    policy-administration call, and getting it wrong mis-pays a real customer.
    """
    tl = ct.build_timeline(_claim(surveyor_appointed_at="2026-08-17T10:00:00"), now=NOW)

    banned = ("penalty", "interest", "compensation", "payable")

    def walk(node, path="root"):
        if isinstance(node, dict):
            for k, v in node.items():
                assert not any(b in str(k).lower() for b in banned), f"{path}.{k}"
                walk(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")

    walk(tl)


def test_the_deployment_caveat_is_always_present():
    """Never let the panel imply a licensed surveyor was involved."""
    tl = ct.build_timeline(_claim(), now=NOW)
    assert "not a licensed" in tl["deployment_note"].lower()
    assert "stands in for" in _by_key(tl, "surveyor_appointed")["label"]
    assert "stands in for" in _by_key(tl, "survey_report")["label"]
