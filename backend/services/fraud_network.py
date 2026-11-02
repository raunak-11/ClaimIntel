"""
Cross-claimant fraud-ring / network detection for ClaimIntel (FC-30).

garage_intel.py (FC-24) and historical_fraud_intel.py (FC-25-27) each check
ONE attribute in isolation — same garage, same claimant phone, same
telematics signature — and only within the current claim's own history.
Neither builds a GRAPH connecting DIFFERENT claimants to each other, so the
highest-value, most realistic organized-fraud pattern in Indian motor
insurance (a garage + tout network running staged collisions across several
unrelated-looking claimants) is invisible to this system by construction —
every existing check is per-claim or per-single-attribute.

This module builds a lightweight co-occurrence graph per investigation: for
the current claim, scan every OTHER investigated claim (storage.get_all_claims()
+ result.json) whose incident falls within a rolling window of this claim's
incident date, and connect two claims when they share EITHER:
  - the same nominated garage/workshop, or
  - a THIRD-PARTY vehicle registration mentioned in the free-text description
    (regex-extracted; the claimant's own registered vehicle is excluded so a
    plate match is never just "two people who happen to drive the same car").
The current claim is flagged when it connects to >= 2 OTHER distinct
claimants (by phone) within the window — a single shared garage/plate is
common and not itself a ring signal; two or more is the pattern.

Scope note: the original design (see docs/newupdates.md item #20) also connects
claims on witness name. No document prompt or the free-text description
parser currently extracts a witness-name field — that's a document_parser.py
/ FIR-prompt schema change, not a graph change, and is left for that item.
Adding it later is ~5 lines here once the field exists (one more node type
in `_claim_nodes` + one more `reasons.append(...)` in `build_claim_network`).
"""

import re
from datetime import datetime, timedelta

import storage

# How far before/after this claim's incident date to look for connected
# claimants. 90 days mirrors the "rolling 30-90 day window" the audit called
# for — wide enough to catch a slow-running ring, narrow enough that two
# claimants sharing a garage two years apart isn't treated as the same ring.
WINDOW_DAYS = 90

# Loose Indian vehicle-registration pattern: 2 letters (state), 1-2 digits
# (RTO code), 1-3 letters (series), 3-4 digits (number) — with optional
# spaces/hyphens between groups, e.g. "MH12AB1234", "DL-05-XY-9876".
_PLATE_RE = re.compile(r"\b([A-Z]{2}\s?-?\s?\d{1,2}\s?-?\s?[A-Z]{1,3}\s?-?\s?\d{3,4})\b")


def _norm(s: str | None) -> str:
    return " ".join((s or "").strip().lower().split())


def _norm_plate(s: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def _norm_phone(s: str | None) -> str:
    return (s or "").strip().replace(" ", "").replace("-", "")


def _claim_own_plate(claim: dict) -> str:
    """The claimant's OWN registered vehicle's plate, parsed from the
    'Make Model (REG123)' vehicle string — excluded from third-party
    plate matching so a plate match is never just claimant-vs-self."""
    m = re.search(r"\(([A-Z0-9 \-]+)\)", (claim.get("vehicle") or "").upper())
    return _norm_plate(m.group(1)) if m else ""


def _third_party_plates(claim: dict, docs: dict | None = None) -> set[str]:
    """Vehicle registrations mentioned in this claim's description or parsed
    FIR that are NOT the claimant's own vehicle — candidate third-party
    plates for cross-claim matching."""
    own_plate = _claim_own_plate(claim)
    text = claim.get("description") or ""
    fir = (docs or {}).get("fir") or {}
    if fir.get("vehicle_reg_in_fir"):
        text = f"{text} {fir['vehicle_reg_in_fir']}"
    found = {_norm_plate(m) for m in _PLATE_RE.findall(text.upper())}
    return {p for p in found if len(p) >= 8 and p != own_plate}


def _incident_date(claim: dict):
    try:
        return datetime.strptime((claim.get("incident_date") or "")[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def build_claim_network(claim: dict, docs: dict | None = None) -> dict:
    """Cross-claimant network scan for the current claim.

    Returns {status: pass|flag|na, detail, connected_claimants, edges}.
    `edges` is a list of {claim_ids, claimant, reasons} — kept in the result
    for the UI/analytics layer even when status is "pass", so an adjuster can
    see a single (below-threshold) link without it being called out as a flag.
    """
    claim_id = claim.get("claim_id")
    own_phone = _norm_phone(claim.get("phone"))
    inc_date = _incident_date(claim)
    if not inc_date:
        return {"status": "na", "detail": "Incident date unavailable — network window cannot be computed.",
                "connected_claimants": [], "edges": []}

    garage = _norm(claim.get("garage_workshop_name"))
    plates = _third_party_plates(claim, docs)
    if not garage and not plates:
        return {"status": "na",
                "detail": "No garage or third-party vehicle registration to cross-reference for a network scan.",
                "connected_claimants": [], "edges": []}

    window_start = inc_date - timedelta(days=WINDOW_DAYS)
    window_end = inc_date + timedelta(days=WINDOW_DAYS)

    connected: dict[str, dict] = {}   # phone -> {claim_ids: set, reasons: set, claimant: str}
    for c in storage.get_all_claims():
        cid = c.get("claim_id")
        if not cid or cid == claim_id:
            continue
        other_phone = _norm_phone(c.get("phone"))
        if not other_phone or other_phone == own_phone:
            continue  # same claimant re-filing is a frequency signal (FC-02/FC-09), not a ring

        other_date = _incident_date(c)
        if not other_date or not (window_start <= other_date <= window_end):
            continue

        reasons: list[str] = []
        other_garage = _norm(c.get("garage_workshop_name"))
        if garage and other_garage and other_garage == garage:
            reasons.append(f"same garage ('{c.get('garage_workshop_name')}')")

        other_plates = _third_party_plates(c)
        shared_plates = plates & other_plates
        if shared_plates:
            reasons.append(f"shared third-party vehicle reg ({', '.join(sorted(shared_plates))})")

        if reasons:
            entry = connected.setdefault(
                other_phone, {"claim_ids": set(), "reasons": set(), "claimant": c.get("claimant", "")}
            )
            entry["claim_ids"].add(cid)
            entry["reasons"].update(reasons)

    if not connected:
        return {
            "status": "pass",
            "detail": f"No shared garage or third-party vehicle registration links to other claimants "
                      f"within a {WINDOW_DAYS}-day window.",
            "connected_claimants": [], "edges": [],
        }

    edges = [
        {"claim_ids": sorted(v["claim_ids"]), "claimant": v["claimant"], "reasons": sorted(v["reasons"])}
        for v in connected.values()
    ]

    if len(connected) >= 2:
        names = ", ".join(sorted({v["claimant"] or "unknown claimant" for v in connected.values()}))
        return {
            "status": "flag",
            "detail": (
                f"Network pattern: this claim's garage/third-party vehicle links to {len(connected)} "
                f"OTHER distinct claimants ({names}) within a {WINDOW_DAYS}-day window — possible "
                f"organized ring (staged-collision or workshop network, FS-002/FS-004), not an isolated claim."
            ),
            "connected_claimants": sorted(connected.keys()),
            "edges": edges,
        }

    v = next(iter(connected.values()))
    return {
        "status": "pass",
        "detail": (
            f"Linked to 1 other claimant ({v['claimant'] or 'unknown claimant'}) via "
            f"{'; '.join(sorted(v['reasons']))} within the {WINDOW_DAYS}-day window — below the "
            f"2-claimant ring threshold."
        ),
        "connected_claimants": list(connected.keys()),
        "edges": edges,
    }
