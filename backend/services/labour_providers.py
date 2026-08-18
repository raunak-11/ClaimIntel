"""Labour-time data providers.

ClaimIntel has no OEM / CCC / Audatex / Mitchell estimating-database licence, so
standard repair times for this vehicle and this operation are simply not
available to it. Rather than hardcode invented times and let them drift into
looking authoritative, labour times come through this interface:

    LabourDataProvider
    ├── RuleBasedLabourProvider   [CURRENT]  — transparent config-driven baseline
    └── OEMLabourProvider         [FUTURE]   — stub; reports itself unavailable

Every time returned carries its own `source`, `confidence` and `version`, so a
downstream consumer can always tell an OEM-certified figure from a rule-based
one. `RuleBasedLabourProvider` never claims to be anything but
`rule_based_mvp` — nothing in this module fabricates OEM data.

Swapping in real data later means implementing `OEMLabourProvider.standard_hours`
and changing `get_provider()`; no caller changes.
"""

from __future__ import annotations

import json
import os
import threading
from abc import ABC, abstractmethod
from typing import Optional

from config import LABOUR_CONFIG_PATH


# ── Config loading (cached, hot-reloaded on mtime change) ──────────────────────

_lock = threading.Lock()
_cache: Optional[dict] = None
_cache_mtime: float = 0.0


def load_config(path: str | None = None) -> dict:
    """Read labour_config.json, re-reading it if the file changed on disk so an
    operator can retune rates without restarting the service."""
    global _cache, _cache_mtime
    path = path or LABOUR_CONFIG_PATH
    with _lock:
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            mtime = 0.0
        if _cache is not None and mtime == _cache_mtime:
            return _cache
        try:
            with open(path, "r", encoding="utf-8") as f:
                _cache = json.load(f)
            _cache_mtime = mtime
        except Exception:
            # A missing/corrupt config must not take the pipeline down — the
            # engine degrades to "labour not assessed" and says so.
            _cache = {}
            _cache_mtime = 0.0
        return _cache


def reset_config_cache() -> None:
    """Test hook — forces the next load_config() to re-read from disk."""
    global _cache, _cache_mtime
    with _lock:
        _cache = None
        _cache_mtime = 0.0


# ── Provider interface ─────────────────────────────────────────────────────────

class LabourTime:
    """One standard-time lookup result."""

    __slots__ = ("operation", "standard_hours", "source", "vehicle_applicability",
                 "confidence", "version", "is_default")

    def __init__(self, operation: str, standard_hours: float, source: str,
                 vehicle_applicability: str, confidence: float, version: str,
                 is_default: bool = False):
        self.operation = operation
        self.standard_hours = standard_hours
        self.source = source
        self.vehicle_applicability = vehicle_applicability
        self.confidence = confidence
        self.version = version
        # True when the category had no explicit entry and the generic default
        # baseline was used — the engine docks confidence for these.
        self.is_default = is_default

    def as_dict(self) -> dict:
        return {
            "operation": self.operation,
            "standard_hours": self.standard_hours,
            "source": self.source,
            "vehicle_applicability": self.vehicle_applicability,
            "confidence": self.confidence,
            "version": self.version,
        }


class LabourDataProvider(ABC):
    """Returns a standard time for (vehicle, part category, operation)."""

    name: str = "abstract"

    @abstractmethod
    def is_available(self) -> bool:
        ...

    @abstractmethod
    def standard_hours(self, vehicle: str, part_category: str,
                       operation: str) -> Optional[LabourTime]:
        ...


class RuleBasedLabourProvider(LabourDataProvider):
    """Config-driven baseline. Explicitly NOT manufacturer data."""

    name = "rule_based_mvp"

    def __init__(self, config: dict | None = None):
        self._config = config if config is not None else load_config()

    def is_available(self) -> bool:
        return bool(self._config.get("baseline_hours")
                    or self._config.get("default_baseline_hours"))

    def standard_hours(self, vehicle: str, part_category: str,
                       operation: str) -> Optional[LabourTime]:
        table = (self._config.get("baseline_hours") or {}).get(part_category) or {}
        defaults = self._config.get("default_baseline_hours") or {}

        hours = table.get(operation)
        is_default = hours is None
        if hours is None:
            hours = defaults.get(operation)
        if hours is None:
            return None

        return LabourTime(
            operation=operation,
            standard_hours=float(hours),
            source=self.name,
            # Rule-based times are category-level, not VIN-level. Saying so is
            # the point: it is what separates this from an OEM figure.
            vehicle_applicability=f"category:{part_category} (not vehicle-specific)",
            confidence=float((self._config.get("confidence") or {}).get("base", 0.8)),
            version=str(self._config.get("version", "0")),
            is_default=is_default,
        )


class OEMLabourProvider(LabourDataProvider):
    """Placeholder for a licensed OEM / estimating-database integration.

    Intentionally unimplemented. It exists so the wiring, the schema and the
    `source` plumbing are already in place when a real feed is licensed — and so
    that nothing in this codebase can accidentally present rule-based hours as
    manufacturer times.
    """

    name = "oem_database"

    def is_available(self) -> bool:
        return False

    def standard_hours(self, vehicle: str, part_category: str,
                       operation: str) -> Optional[LabourTime]:
        return None


def get_provider(config: dict | None = None) -> LabourDataProvider:
    """The active provider: OEM when a real one is ever connected, else rules."""
    oem = OEMLabourProvider()
    if oem.is_available():
        return oem
    return RuleBasedLabourProvider(config)
