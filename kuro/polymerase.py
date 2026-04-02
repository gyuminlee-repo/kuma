"""Polymerase profile models and registry.

Self-contained — no external primerbench dependency.
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class PolymeraseProfile:
    """Parameter set for a specific DNA polymerase."""

    name: str
    tm_method: str          # "breslauer" or "santalucia"
    salt_correction: str    # "schildkraut", "santalucia", "owczarzy"
    opt_tm: float
    min_tm: float
    max_tm: float
    opt_size: int
    min_size: int
    max_size: int
    min_gc: float
    max_gc: float
    salt_monovalent: float  # mM
    salt_divalent: float    # mM (Mg2+)
    dntp_conc: float        # mM
    dna_conc: float         # nM
    max_tm_diff: float      # max Tm difference between F/R
    # Asymmetric Tm targets (optional; fall back to opt_tm if not set)
    opt_tm_fwd: float | None = None     # Forward non-overlap Tm target
    opt_tm_rev: float | None = None     # Reverse non-overlap Tm target
    opt_tm_overlap: float | None = None  # Overlap region Tm target
    min_3prime_dist: int = 0             # Min distance from mutation to 3' end of overlap


def _resource_path(relative_path: str) -> Path:
    """Get absolute path to a resource file.

    Works both in development and when frozen by PyInstaller.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS) / "kuro"
    else:
        base = Path(__file__).parent
    return base / relative_path


def _dict_to_profile(data: dict) -> PolymeraseProfile:
    """Convert a JSON dict to a PolymeraseProfile dataclass."""
    return PolymeraseProfile(
        name=data["name"],
        tm_method=data["tm_method"],
        salt_correction=data["salt_correction"],
        opt_tm=float(data["opt_tm"]),
        min_tm=float(data["min_tm"]),
        max_tm=float(data["max_tm"]),
        opt_size=int(data["opt_size"]),
        min_size=int(data["min_size"]),
        max_size=int(data["max_size"]),
        min_gc=float(data["min_gc"]),
        max_gc=float(data["max_gc"]),
        salt_monovalent=float(data["salt_monovalent"]),
        salt_divalent=float(data["salt_divalent"]),
        dntp_conc=float(data["dntp_conc"]),
        dna_conc=float(data["dna_conc"]),
        max_tm_diff=float(data["max_tm_diff"]),
        opt_tm_fwd=float(data["opt_tm_fwd"]) if "opt_tm_fwd" in data else None,
        opt_tm_rev=float(data["opt_tm_rev"]) if "opt_tm_rev" in data else None,
        opt_tm_overlap=float(data["opt_tm_overlap"]) if "opt_tm_overlap" in data else None,
        min_3prime_dist=int(data.get("min_3prime_dist", 0)),
    )


BUILTIN_PATH = _resource_path("resources/polymerase_profiles.json")


class PolymeraseRegistry:
    """Manages built-in and optional custom polymerase profiles."""

    def __init__(self, custom_path: Path | None = None) -> None:
        self._profiles: dict[str, PolymeraseProfile] = {}
        self._custom_path = custom_path
        self._load_builtin()
        if custom_path and custom_path.exists():
            self._load_custom(custom_path)

    def _load_builtin(self) -> None:
        if not BUILTIN_PATH.exists():
            raise FileNotFoundError(
                f"Polymerase profiles not found: {BUILTIN_PATH}. "
                "Ensure kuro/resources/polymerase_profiles.json exists."
            )
        with open(BUILTIN_PATH) as f:
            data = json.load(f)
        for name, profile_data in data.items():
            self._profiles[name] = _dict_to_profile(profile_data)
        logger.info("Loaded %d polymerase profiles", len(data))

    def _load_custom(self, path: Path) -> None:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for entry in data:
            profile = _dict_to_profile(entry)
            self._profiles[profile.name] = profile

    def get(self, name: str) -> PolymeraseProfile:
        """Get a profile by name. Raises KeyError if not found."""
        if name not in self._profiles:
            available = ", ".join(sorted(self._profiles.keys()))
            raise KeyError(
                f"Polymerase '{name}' not found. Available: {available}"
            )
        return self._profiles[name]

    def list_names(self) -> list[str]:
        """Return sorted list of all profile names."""
        return sorted(self._profiles.keys())

    def save_custom(self, profile: PolymeraseProfile, path: Path | None = None) -> None:
        """Save or update a custom profile."""
        target = path or self._custom_path
        if target is None:
            raise ValueError("No custom profile path configured")

        existing: list[dict] = []
        if target.exists():
            with open(target, encoding="utf-8") as f:
                existing = json.load(f)

        data = asdict(profile)
        updated = False
        for i, entry in enumerate(existing):
            if entry["name"] == profile.name:
                existing[i] = data
                updated = True
                break
        if not updated:
            existing.append(data)

        with open(target, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)

        self._profiles[profile.name] = profile
