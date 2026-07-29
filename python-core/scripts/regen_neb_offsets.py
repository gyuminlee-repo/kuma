"""Regenerate the NEB Tm offset calibration table.

REQUIRES NETWORK. Calls the live NEB Tm API (tmapi.neb.com) for each product
and sample sequence, then fits a linear offset model

    offset_degC = c0 + c1*len + c2*gc_percent

against primer3.calc_tm(ref_config) and writes the result back into
kuma_core/kuro/resources/neb_tm_offsets.json. Documentation / reproduction
utility — not part of the design path. Run manually when recalibrating.

    .venv/bin/python python-core/scripts/regen_neb_offsets.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import primer3

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from kuma_core.kuro.neb_tm import neb_api_tm  # noqa: E402

OFFSETS_PATH = REPO_ROOT / "kuma_core" / "kuro" / "resources" / "neb_tm_offsets.json"
FIXTURE_PATH = REPO_ROOT / "fixtures" / "pSHCE-dmpR.fa"


def _gc_percent(seq: str) -> float:
    if not seq:
        return 0.0
    gc = sum(1 for c in seq.upper() if c in "GC")
    return gc / len(seq) * 100


def _load_template() -> str:
    parts: list[str] = []
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith(">"):
                parts.append(line)
    return "".join(parts).upper()


def _sample_seqs(template: str) -> list[str]:
    """Substrings of len 17-39 with GC 40-60% sampled across the template."""
    samples: list[str] = []
    seen: set[str] = set()
    step = max(1, len(template) // 200)
    for length in range(17, 40, 2):
        for start in range(0, len(template) - length + 1, step):
            seq = template[start:start + length]
            if 40.0 <= _gc_percent(seq) <= 60.0 and seq not in seen:
                seen.add(seq)
                samples.append(seq)
    return samples


def _fit_product(product: str, ref_config: dict, seqs: list[str]) -> tuple[list[float], float, float]:
    rows: list[list[float]] = []
    offsets: list[float] = []
    for seq in seqs:
        neb = neb_api_tm(seq, product)
        p3 = primer3.calc_tm(seq, **ref_config)
        rows.append([1.0, float(len(seq)), _gc_percent(seq)])
        offsets.append(neb - p3)
    a = np.array(rows)
    b = np.array(offsets)
    coef, _residuals, _rank, _sv = np.linalg.lstsq(a, b, rcond=None)
    pred = a @ coef
    resid = b - pred
    return [round(float(c), 4) for c in coef], float(np.max(np.abs(resid))), float(np.std(resid))


def main() -> None:
    with open(OFFSETS_PATH, encoding="utf-8") as f:
        table = json.load(f)

    template = _load_template()
    seqs = _sample_seqs(template)
    sys.stdout.write(f"Sampled {len(seqs)} sequences from {FIXTURE_PATH.name}\n")

    for product, entry in table["products"].items():
        coef, resid_max, resid_std = _fit_product(product, entry["ref_config"], seqs)
        entry["coef"] = coef
        entry["residual_max_degC"] = round(resid_max, 3)
        entry["residual_std_degC"] = round(resid_std, 3)
        sys.stdout.write(f"{product}: coef={coef} resid_max={resid_max:.3f}\n")

    table["_meta"]["n_samples"] = len(seqs)
    with open(OFFSETS_PATH, "w", encoding="utf-8") as f:
        json.dump(table, f, indent=2, ensure_ascii=False)
        f.write("\n")
    sys.stdout.write(f"Wrote {OFFSETS_PATH}\n")


if __name__ == "__main__":
    main()
