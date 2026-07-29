"""Track-2: IspS real-measured-data retrospective (plan Phase 3).

Uses LOCAL provenance files (no Z-drive dependency):
- SCANEER co-evolution scores: ``foldcrit/data/ispS_provenance/scaneer_sci_sispS.tsv``
  (cols Residue, AA1=wt, AA2=mut, SCI); variant = ``AA1 + Residue + AA2`` e.g. "L219W".
- GC-FID round-1 measured activity: ``.../231024_round1_screening.xlsx`` sheet
  ``Sorted`` (col 'AA mut' e.g. "V550L", col 'Relative peak area' = measured
  activity, ~93 round-1 variants). Sheet 'Well - AA mut' gives the well->mutation
  map and is used only to cross-check the variant strings.

This is a QUALITATIVE real-world anchor (small pool, single round); no statistical
power claim. The retrospective compares SCANEER-only round-1 (R1=SCANEER SCI rank)
against greedy / random / diversity R2+ acquisition over the known-activity variants,
in the documented rho~0.092 weak-signal regime. The 혜민 combinatorial double/triple
data needed for the decisive epistatic retrospective is ABSENT locally;
``combinatorial_data_readiness_spec`` defines the schema/format that data must supply.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

_SORTED_SHEET = "Sorted"
_WELL_SHEET = "Well - AA mut"
_AA_MUT_RE = re.compile(r"^([A-Z])(\d+)([A-Z])$")


# ---------------------------------------------------------------------------
# Existing loaders (unchanged)
# ---------------------------------------------------------------------------

def load_scaneer_sci(tsv_path: str | Path) -> pd.DataFrame:
    """Return DataFrame[variant, residue, wt, mut, scaneer_sci] from the SCANEER tsv."""
    df = pd.read_csv(tsv_path, sep="\t")
    df.columns = [c.strip().strip('"') for c in df.columns]
    need = {"Residue", "AA1", "AA2", "SCI"}
    if not need.issubset(df.columns):
        raise ValueError(f"SCANEER tsv missing {need - set(df.columns)} in {tsv_path}")
    out = pd.DataFrame(
        {
            "variant": df["AA1"].astype(str) + df["Residue"].astype(str) + df["AA2"].astype(str),
            "residue": df["Residue"].astype(int),
            "wt": df["AA1"].astype(str),
            "mut": df["AA2"].astype(str),
            "scaneer_sci": pd.to_numeric(df["SCI"], errors="coerce"),
        }
    )
    return out.dropna(subset=["scaneer_sci"]).reset_index(drop=True)


def load_isps_measured(xlsx_path: str | Path) -> pd.DataFrame:
    """Return DataFrame[variant, well, relative_peak_area] for ALL measured wells.

    The 'Sorted' sheet names only the top ~18 hits in its 'AA mut' column but has a
    well id and 'Relative peak area' for every measured well (~93). The 'Well - AA
    mut' sheet maps every well -> (wt, residue, mut). We join on well to recover the
    full set; the direct 'AA mut' label (when present) cross-checks the well map.
    """
    # Well -> variant map from 'Well - AA mut' (no header: Well, AA1, pos, AA2).
    wmap_raw = pd.read_excel(xlsx_path, sheet_name=_WELL_SHEET, header=None)
    well_to_variant: dict[str, str] = {}
    for _, r in wmap_raw.iterrows():
        well, wt, pos, mut = r[0], r[1], r[2], r[3]
        if pd.isna(well) or pd.isna(wt) or pd.isna(pos) or pd.isna(mut):
            continue
        variant = f"{str(wt).strip()}{int(pos)}{str(mut).strip()}"
        if _AA_MUT_RE.match(variant):
            well_to_variant[str(well).strip()] = variant

    raw = pd.read_excel(xlsx_path, sheet_name=_SORTED_SHEET, header=0)
    raw.columns = [str(c).strip() for c in raw.columns]
    act_col = next((c for c in raw.columns if "relative" in c.lower() and "peak" in c.lower()), None)
    mut_col = next((c for c in raw.columns if str(c).strip().lower() in ("aa mut", "aamut", "mut", "variant")), None)
    if act_col is None:
        raise ValueError(f"'Sorted' sheet missing relative-peak-area column (have {list(raw.columns)})")
    # Detect the well column: values look like a plate well (letter + 1-2 digits).
    well_re = re.compile(r"^[A-Pa-p]\d{1,2}$")

    def _is_well_col(col: pd.Series) -> bool:
        vals = col.dropna().astype(str).str.strip()
        return (not vals.empty) and bool((vals.str.match(well_re)).mean() > 0.5)

    well_col = next((c for c in raw.columns if _is_well_col(raw[c])), None)

    rows = []
    cross_checked = 0
    for _, r in raw.iterrows():
        act = pd.to_numeric(r[act_col], errors="coerce")
        if pd.isna(act):
            continue
        well = str(r[well_col]).strip() if well_col is not None else None
        direct = str(r[mut_col]).strip() if mut_col is not None else ""
        variant = None
        if _AA_MUT_RE.match(direct):
            variant = direct
            if well in well_to_variant and well_to_variant[well] == direct:
                cross_checked += 1
        elif well in well_to_variant:
            variant = well_to_variant[well]
        if variant is None:
            continue  # WT / control / unmapped
        rows.append({"variant": variant, "well": well, "relative_peak_area": float(act)})
    if not rows:
        raise ValueError(f"no measured single-sub variants parsed from {xlsx_path}")
    df = pd.DataFrame(rows).drop_duplicates(subset=["variant"]).reset_index(drop=True)
    df.attrs["cross_checked_labels"] = cross_checked
    return df


def join_isps(measured: pd.DataFrame, sci: pd.DataFrame) -> pd.DataFrame:
    """Left-join measured activity with SCANEER SCI on variant.

    Returns DataFrame[variant, relative_peak_area, scaneer_sci, has_sci].
    """
    merged = measured.merge(
        sci[["variant", "scaneer_sci"]], on="variant", how="left"
    )
    merged["has_sci"] = merged["scaneer_sci"].notna()
    return merged


def load_isps_track2(
    provenance_dir: str | Path,
    sci_filename: str = "scaneer_sci_sispS.tsv",
    screening_filename: str = "231024_round1_screening.xlsx",
) -> pd.DataFrame:
    """Convenience: load + join from a provenance directory."""
    d = Path(provenance_dir)
    sci = load_scaneer_sci(d / sci_filename)
    measured = load_isps_measured(d / screening_filename)
    return join_isps(measured, sci)


# ---------------------------------------------------------------------------
# Phase C helpers
# ---------------------------------------------------------------------------

def _parse_residue_num(variant: str) -> int | None:
    """Extract residue number from a single-mut variant string e.g. 'L219W' -> 219."""
    m = _AA_MUT_RE.match(variant)
    return int(m.group(2)) if m else None


def _greedy_maximin(
    candidates: list[str],
    revealed_residues: set[int],
    batch: int,
) -> list[str]:
    """Select `batch` variants by greedy maximin on residue position.

    Maximises the minimum residue-position distance to already-revealed residues,
    spreading selections across distinct protein regions.  Firewall-safe: uses
    only residue positions (from variant name), never measured activities.
    """
    selected: list[str] = []
    res_map = {v: (_parse_residue_num(v) or 0) for v in candidates}
    current_res = set(revealed_residues)
    remaining = list(candidates)

    for _ in range(min(batch, len(remaining))):
        if not current_res:
            # No reference residues yet: take alphabetically first for determinism
            pick = min(remaining)
        else:
            pick = max(
                remaining,
                key=lambda v: min(abs(res_map[v] - r) for r in current_res),
            )
        selected.append(pick)
        remaining.remove(pick)
        current_res.add(res_map[pick])

    return selected


# ---------------------------------------------------------------------------
# Phase C: single-mut retrospective
# ---------------------------------------------------------------------------

def retrospective_single_mut(
    merged_df: pd.DataFrame,
    *,
    n_seed: int = 12,
    batch: int = 10,
    rounds: int = 4,
    seed: int = 0,
) -> dict[str, Any]:
    """Leak-aware retrospective on single-mut IspS measurements.

    Simulates an AL campaign over ``merged_df`` (columns: variant,
    relative_peak_area, scaneer_sci, has_sci) using three SCANEER-only
    acquisition policies that require no ESM-2 embeddings.

    Round structure
    ---------------
    R1 (seed): select ``n_seed`` variants by descending SCANEER SCI —
        shared across all policies; reveal their measured activities.
    R2 .. rounds-1: each policy independently selects ``batch`` candidates
        from the *unrevealed* pool using only activities of *already-revealed*
        variants (firewall).

    Policies
    --------
    ``scaneer_greedy``
        Fit OLS surrogate (scaneer_sci -> revealed relative_peak_area) on the
        current revealed set; score unrevealed by predicted activity; pick top-N.
    ``random``
        Uniform random sample from unrevealed (seeded for reproducibility).
    ``diversity``
        Greedy maximin on residue position: maximise spread across sequence
        positions.  Uses variant name only — never measured activity.

    Returns
    -------
    dict with keys: n_variants, n_hits, hit_cutoff, spearman_rho,
    spearman_p, n_rounds, n_seed, batch, policies.
    ``policies`` maps each policy name to:
        recall_at_hits, best_activity, n_revealed, rounds_selected.

    Notes
    -----
    - Spearman rho is reported AS-IS; the pre-registered value is ~0.092
      (weak-signal regime, n=93).  The retrospective may show diversity
      does not materially outperform greedy or random — that is an honest result.
    - Variants without SCANEER SCI (has_sci=False) receive score -inf for
      SCANEER-based policies (last priority) and are treated normally by
      random and diversity policies.
    """
    rng = np.random.default_rng(seed)

    df = merged_df.copy().reset_index(drop=True)
    oracle: dict[str, float] = dict(zip(df["variant"], df["relative_peak_area"]))

    # Top-10% hit set by measured activity (the "gold standard" for recall)
    hit_cutoff = float(df["relative_peak_area"].quantile(0.90))
    hit_set = set(df[df["relative_peak_area"] >= hit_cutoff]["variant"])
    n_hits = len(hit_set)

    # Spearman rho on variants with SCANEER SCI
    sci_df = df.dropna(subset=["scaneer_sci"])
    if len(sci_df) >= 3:
        rho_val, p_val = spearmanr(sci_df["scaneer_sci"], sci_df["relative_peak_area"])
        rho: float | None = float(rho_val)
        pval: float | None = float(p_val)
    else:
        rho, pval = None, None

    all_variants = list(df["variant"])
    # SCANEER score map: -inf for missing SCI (last priority)
    sci_map: dict[str, float] = {
        v: float(s) if pd.notna(s) else float("-inf")
        for v, s in zip(df["variant"], df["scaneer_sci"])
    }

    # R1 seed (shared): top n_seed by SCANEER SCI; ties broken by variant name
    sorted_by_sci = sorted(
        all_variants, key=lambda v: (-sci_map.get(v, float("-inf")), v)
    )
    seed_batch = sorted_by_sci[: min(n_seed, len(all_variants))]

    policy_results: dict[str, Any] = {}

    for policy in ("scaneer_greedy", "random", "diversity"):
        revealed: list[str] = list(seed_batch)
        rounds_selected: list[list[str]] = [list(seed_batch)]

        for _round in range(1, rounds):
            revealed_set = set(revealed)
            candidates = [v for v in all_variants if v not in revealed_set]
            if not candidates:
                break
            n_pick = min(batch, len(candidates))

            if policy == "scaneer_greedy":
                # ---- FIREWALL: surrogate trained on revealed activities ONLY ----
                rev_sci = df.loc[df["variant"].isin(revealed_set), :].dropna(
                    subset=["scaneer_sci"]
                )
                if len(rev_sci) >= 2:
                    sci_arr = rev_sci["scaneer_sci"].values
                    act_arr = rev_sci["relative_peak_area"].values
                    coeffs = np.polyfit(sci_arr, act_arr, 1)
                    slope, intercept = float(coeffs[0]), float(coeffs[1])
                else:
                    # Not enough revealed data: fall back to SCI rank
                    slope, intercept = 1.0, 0.0
                # Score by predicted activity; missing-SCI variants -> LAST priority
                # regardless of the surrogate slope sign (robust in the rho~0.092 regime
                # where OLS on the SCI-ranked seed can yield a negative slope).
                def _pred(v: str, _slope: float = slope, _intercept: float = intercept) -> float:
                    s = sci_map[v]
                    return float("-inf") if s == float("-inf") else _slope * s + _intercept

                picks = sorted(candidates, key=lambda v: -_pred(v))[:n_pick]

            elif policy == "random":
                idx = rng.choice(len(candidates), size=n_pick, replace=False)
                picks = [candidates[i] for i in sorted(idx)]

            elif policy == "diversity":
                # ---- FIREWALL: uses only residue positions, never activities ----
                revealed_residues: set[int] = set()
                for v in revealed:
                    r = _parse_residue_num(v)
                    if r is not None:
                        revealed_residues.add(r)
                picks = _greedy_maximin(candidates, revealed_residues, n_pick)

            revealed.extend(picks)
            rounds_selected.append(picks)

        # Metrics
        final_revealed_set = set(revealed)
        recall = (
            len(final_revealed_set & hit_set) / len(hit_set) if hit_set else 0.0
        )
        best_act = max(
            (oracle[v] for v in revealed if v in oracle), default=float("-inf")
        )
        policy_results[policy] = {
            "recall_at_hits": float(recall),
            "best_activity": float(best_act),
            "n_revealed": len(revealed),
            "rounds_selected": rounds_selected,
        }

    return {
        "n_variants": len(df),
        "n_hits": n_hits,
        "hit_cutoff": hit_cutoff,
        "spearman_rho": rho,
        "spearman_p": pval,
        "n_rounds": rounds,
        "n_seed": n_seed,
        "batch": batch,
        "policies": policy_results,
    }


# ---------------------------------------------------------------------------
# Combinatorial data-readiness spec (no fabricated data)
# ---------------------------------------------------------------------------

def combinatorial_data_readiness_spec() -> dict[str, Any]:
    """Return a structured spec for the 혜민 combinatorial IspS dataset.

    This function DOES NOT fabricate data.  The combinatorial double/triple
    mutation screening data is CURRENTLY ABSENT from the local provenance
    directory.  This spec documents what that dataset must provide to run the
    Phase B-style decisive combinatorial retrospective.
    """
    return {
        "status": "DATA_ABSENT",
        "currently_absent": True,
        "description": (
            "Specification for the 혜민 combinatorial IspS dataset needed to run "
            "the Phase B decisive combinatorial retrospective.  As of writing, "
            "only 93 single-mutation round-1 variants are present locally.  "
            "This spec defines the required schema and format for the missing data."
        ),
        # ---- Required columns ----
        "required_columns": [
            "mutant",           # str, colon-separated single-sub tokens e.g. 'A12G:K45R'
            "measured_activity",  # float, relative peak area normalised to WT=1.0
            "round_index",      # int, 0-based round (0=seed, 1=R2, ...)
        ],
        "optional_columns": [
            "well",             # str, plate well ID for cross-reference
            "batch_id",         # str, plate/replicate batch identifier
            "wt_control_area",  # float, WT GC-FID peak area on same plate (for normalisation)
        ],
        # ---- Mutant string format ----
        "mutant_format": {
            "description": (
                "Colon-separated single-substitution tokens, each in the format "
                "'WTposMAA' (wt amino-acid letter, 1-based residue number, mutant "
                "amino-acid letter).  Example: 'A12G:K45R' for double mutant at "
                "positions 12 and 45.  Single mutants use no colon: 'V550L'."
            ),
            "separator": ":",
            "token_regex": r"^[A-Z]\d+[A-Z]$",
            "double_example": "A12G:K45R",
            "triple_example": "A12G:K45R:L219W",
            "single_example": "V550L",
        },
        "permutation_invariant": True,
        "permutation_invariant_note": (
            "All colon-separated tokens MUST be sorted by residue position before "
            "storage to guarantee permutation invariance: 'K45R:A12G' is canonicalised "
            "to 'A12G:K45R'.  Downstream join and deduplication depend on this."
        ),
        # ---- Round / batch structure ----
        "round_structure": {
            "r1_seed_batch": {
                "description": "Initial seed batch selected by SCANEER SCI (top-N by co-evolution score).",
                "min_variants": 50,
                "mutation_orders": "mix of single, double, triple",
            },
            "r2_plus_batches": {
                "description": "AL-guided subsequent rounds; each round reveals measured activities.",
                "min_variants_per_round": 50,
                "min_rounds": 2,
            },
        },
        # ---- Counts ----
        "min_combinatorial_genotypes_per_round": 50,
        "min_mutation_orders": 2,
        "max_mutation_order_expected": 3,
        # ---- Normalisation and firewall ----
        "normalization": (
            "relative_peak_area must be normalised to the WT control on the same "
            "plate/batch (WT = 1.0).  Multi-plate datasets require per-plate "
            "normalisation before concatenation."
        ),
        "firewall_requirement": (
            "Round R+1 selection must depend only on activities revealed in rounds "
            "<= R.  The measured_activity of unrevealed variants must never appear "
            "in the surrogate training set or acquisition scoring at round R."
        ),
        # ---- What is currently available ----
        "currently_available": {
            "single_mut_variants": 93,
            "rounds": 1,
            "source": "231024_round1_screening.xlsx",
            "note": (
                "Only single-mutation round-1 data is present.  Combinatorial "
                "double/triple mutation data from 혜민's follow-up screening is "
                "absent from the local foldcrit/data/ispS_provenance/ directory."
            ),
        },
    }


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------

def _find_provenance() -> Path | None:
    """Walk up from this file's location to foldcrit/data/ispS_provenance."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        cand = parent / "foldcrit" / "data" / "ispS_provenance"
        if cand.is_dir():
            return cand
    return None


def _make_smoke_frame(n: int = 20, rng_seed: int = 42) -> pd.DataFrame:
    """Generate a clearly-labeled SYNTHETIC merged frame for smoke testing.

    NOT real IspS data.  Used only to validate the retrospective logic
    without requiring the provenance directory.
    """
    rng = np.random.default_rng(rng_seed)
    # Spread residues across a plausible IspS range (1-560)
    residues = sorted(rng.choice(range(50, 560), size=n, replace=False).tolist())
    aa_pool = "ACDEFGHIKLMNPQRSTVWY"
    rows = []
    for i, pos in enumerate(residues):
        wt = aa_pool[i % len(aa_pool)]
        mt = aa_pool[(i + 3) % len(aa_pool)]
        if wt == mt:
            mt = aa_pool[(i + 5) % len(aa_pool)]
        sci = float(rng.uniform(0.5, 5.0))
        # Weak positive correlation with SCI (rho ~ 0.2) + noise
        activity = float(max(0.01, 0.2 * sci + rng.normal(1.0, 0.4)))
        rows.append({
            "variant": f"{wt}{pos}{mt}",
            "well": f"A{i+1}",
            "relative_peak_area": activity,
            "scaneer_sci": sci,
            "has_sci": True,
            "_synthetic": True,  # clearly labeled, not real data
        })
    return pd.DataFrame(rows)


def _print_retrospective(result: dict, label: str = "IspS single-mut retrospective") -> None:
    """Print a human-readable summary of retrospective_single_mut output."""
    print(f"\n{'=' * 60}")
    print(f"  {label}")
    print(f"{'=' * 60}")
    print(f"  Variants: {result['n_variants']}   Hits (top-10%): {result['n_hits']}")
    rho = result.get("spearman_rho")
    pval = result.get("spearman_p")
    rho_str = f"{rho:.4f}" if rho is not None else "n/a"
    p_str = f", p={pval:.3g}" if pval is not None else ""
    print(f"  SCANEER-activity Spearman rho: {rho_str}{p_str}  (weak-signal regime)")
    print(f"  Rounds: {result['n_rounds']}  Seed: {result['n_seed']}  Batch: {result['batch']}")
    print()
    print(f"  {'Policy':<20}  {'recall@hits':>11}  {'best_activity':>13}  {'n_revealed':>10}")
    print(f"  {'-'*20}  {'-'*11}  {'-'*13}  {'-'*10}")
    for pol, pdata in result["policies"].items():
        print(
            f"  {pol:<20}  {pdata['recall_at_hits']:>11.3f}"
            f"  {pdata['best_activity']:>13.4f}"
            f"  {pdata['n_revealed']:>10}"
        )
    print()


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``python -m al.track2_isps``.

    Exits 0 on success.  The ``--smoke`` flag runs a fully self-contained
    test on a labeled-synthetic frame; it does NOT require the provenance
    directory and never fabricates real IspS data.
    """
    parser = argparse.ArgumentParser(
        prog="al.track2_isps",
        description="IspS Phase-C retrospective (single-mut) + combinatorial data-readiness spec.",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help=(
            "Run a self-contained smoke test on a labeled-synthetic frame "
            "(does not require provenance dir); exits 0."
        ),
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        metavar="DIR",
        help="Directory to write retrospective.json (default: results/qa/g003 relative to cwd).",
    )
    parser.add_argument(
        "--n-seed", type=int, default=12, help="Seed batch size (default: 12)."
    )
    parser.add_argument(
        "--batch", type=int, default=10, help="Variants per AL round (default: 10)."
    )
    parser.add_argument(
        "--rounds", type=int, default=4, help="Total rounds including seed (default: 4)."
    )
    args = parser.parse_args(argv)

    if args.smoke:
        # ---- Smoke mode: fully synthetic, no external files needed ----
        print("[smoke] Running self-contained smoke test on SYNTHETIC data (not real IspS).")
        frame = _make_smoke_frame(n=20, rng_seed=42)
        result = retrospective_single_mut(
            frame, n_seed=5, batch=4, rounds=3, seed=0
        )
        spec = combinatorial_data_readiness_spec()
        _print_retrospective(result, label="[SYNTHETIC smoke] single-mut retrospective")
        assert spec["status"] == "DATA_ABSENT", "spec status wrong"
        assert spec["currently_absent"] is True, "spec absent flag wrong"
        print("[smoke] combinatorial_data_readiness_spec OK  (DATA_ABSENT confirmed)")
        print("[smoke] PASS — exit 0")
        return 0

    # ---- Default mode: real provenance ----
    prov = _find_provenance()
    if prov is None:
        print(
            "WARNING: foldcrit/data/ispS_provenance/ not found — "
            "cannot run real retrospective.  Use --smoke for a self-contained run."
        )
        return 0

    print(f"Loading IspS provenance from: {prov}")
    merged = load_isps_track2(prov)
    print(f"  Loaded {len(merged)} variants  (has_sci: {merged['has_sci'].sum()})")

    result = retrospective_single_mut(
        merged,
        n_seed=args.n_seed,
        batch=args.batch,
        rounds=args.rounds,
        seed=0,
    )
    spec = combinatorial_data_readiness_spec()

    _print_retrospective(result, label="IspS single-mut retrospective (real data, n=93)")

    print("--- Combinatorial data-readiness spec ---")
    print(f"  Status: {spec['status']}")
    print(f"  Required columns: {spec['required_columns']}")
    print(f"  Mutant format: {spec['mutant_format']['double_example']}")
    print(f"  Min combinatorial genotypes/round: {spec['min_combinatorial_genotypes_per_round']}")
    print()

    # Write JSON
    out_dir = Path(args.out_dir) if args.out_dir else Path.cwd() / "results" / "qa" / "g003"
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {"retrospective": result, "combinatorial_spec": spec}

    # Make rounds_selected JSON-serializable (list of lists of str — already is)
    out_path = out_dir / "retrospective.json"
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)
    print(f"Wrote: {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
