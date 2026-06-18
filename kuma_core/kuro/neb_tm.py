"""NEB Tm scaling for SDM primer design.

NEB polymerases (Q5/Phusion/Taq/Q5 SDM) report Tm on the NEB Tm Calculator
scale. This module reproduces that scale offline from a committed calibration
table (resources/neb_tm_offsets.json):

    neb_tm = primer3.calc_tm(seq, **ref_config) + (c0 + c1*len(seq) + c2*gc_percent)

The design path uses neb_estimated_tm (no network). neb_api_tm calls the live
NEB Tm API and is for regeneration / optional verification only - never the
design path.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

import primer3

from .polymerase import _resource_path

_OFFSETS: dict[str, Any] | None = None

_NEB_API_BASE = "https://tmapi.neb.com/tm"
_NEB_API_TIMEOUT = 10  # seconds


def _load_offsets() -> dict[str, Any]:
    """Load and cache the committed NEB Tm offset table."""
    global _OFFSETS
    if _OFFSETS is None:
        path = _resource_path("resources/neb_tm_offsets.json")
        with open(path, encoding="utf-8") as f:
            _OFFSETS = json.load(f)
    return _OFFSETS


def _gc_percent(seq: str) -> float:
    """GC percentage (0-100). Matches the convention the table was fit with."""
    if not seq:
        return 0.0
    gc = seq.count("G") + seq.count("C") + seq.count("g") + seq.count("c")
    return gc / len(seq) * 100


def neb_product_for(profile_name: str) -> str | None:
    """Map a polymerase profile name to a NEB product key, or None if non-NEB."""
    offsets = _load_offsets()
    return offsets["product_map"].get(profile_name)


def neb_estimated_tm(seq: str, product: str) -> float:
    """Estimate NEB-scale Tm offline from the committed calibration table.

    neb_tm = primer3.calc_tm(seq, **ref_config) + (c0 + c1*len + c2*gc_percent)

    Design-path only; no network access.
    """
    offsets = _load_offsets()
    entry = offsets["products"][product]
    ref_config = entry["ref_config"]
    c0, c1, c2 = entry["coef"]
    base = primer3.calc_tm(seq, **ref_config)
    gc = _gc_percent(seq)
    return base + (c0 + c1 * len(seq) + c2 * gc)


def neb_api_tm(seq: str, product: str, conc: float = 0.5) -> float:
    """Fetch Tm from the live NEB Tm API.

    Regeneration / optional verification ONLY - must not be called on the
    design path. Raises RuntimeError on any network/parse failure.
    """
    url = f"{_NEB_API_BASE}/{product}/{conc}/{seq}/{seq}/?fmt=long"
    try:
        with urllib.request.urlopen(url, timeout=_NEB_API_TIMEOUT) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"NEB Tm API request failed for {product}: {exc}") from exc
    except (ValueError, KeyError) as exc:
        raise RuntimeError(f"NEB Tm API response parse failed for {product}: {exc}") from exc
    return float(payload["data"]["p1"][0]["tm"])
