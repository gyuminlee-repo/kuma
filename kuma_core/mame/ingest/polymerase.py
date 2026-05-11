"""polymerase -- Polymerase salt/concentration profiles for Tm-based primer design.

Used by :mod:`kuma_core.mame.ingest.barcode_package` to supply salt concentrations
to ``primer3.calc_tm``.  Intentionally separate from ``kuma_core.kuro.polymerase``
to avoid cross-layer coupling.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PolymeraseProfile:
    name: str
    mv_conc: float
    dv_conc: float
    dntp_conc: float
    dna_conc: float
    tm_method: str = "santalucia"
    salt_corrections_method: str = "santalucia"


POLYMERASE_PROFILES: dict[str, PolymeraseProfile] = {
    "Q5": PolymeraseProfile(
        "Q5",
        mv_conc=50.0,
        dv_conc=3.0,
        dntp_conc=0.2,
        dna_conc=250.0,
    ),
    "Taq": PolymeraseProfile(
        "Taq",
        mv_conc=50.0,
        dv_conc=1.5,
        dntp_conc=0.2,
        dna_conc=250.0,
    ),
    "Phusion": PolymeraseProfile(
        "Phusion",
        mv_conc=50.0,
        dv_conc=1.5,
        dntp_conc=0.2,
        dna_conc=250.0,
    ),
}


def get_profile(name: str) -> PolymeraseProfile:
    """Return the PolymeraseProfile for *name*.

    Raises
    ------
    ValueError
        If *name* is not a known polymerase.
    """
    if name not in POLYMERASE_PROFILES:
        raise ValueError(
            f"Unknown polymerase '{name}'. Available: {list(POLYMERASE_PROFILES)}"
        )
    return POLYMERASE_PROFILES[name]


__all__ = ["PolymeraseProfile", "POLYMERASE_PROFILES", "get_profile"]
