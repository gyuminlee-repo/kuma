"""EVOLVEpro variant selection and diversity optimization.

Provides CSV loading, domain-aware selection, and Pareto diversity
selection for EVOLVEpro-predicted SDM variants.
"""

from __future__ import annotations

import csv
import math
import re
import statistics
from pathlib import Path

from kuro.alphafold import pairwise_ca_distance, ca_max_dist

_POS_RE = re.compile(r"[A-Z](\d+)[A-Z]")
_SINGLE_POS_RE = re.compile(r"^[A-Z](\d+)[A-Z]$")

# ---------------------------------------------------------------------------
# Grantham distance lookup table (Grantham 1974, Science 185:862-864)
# Keyed by frozenset of two single-letter amino acid codes.
# ---------------------------------------------------------------------------
_GRANTHAM: dict[frozenset, int] = {
    frozenset({"A", "R"}): 112, frozenset({"A", "N"}): 111, frozenset({"A", "D"}): 126,
    frozenset({"A", "C"}): 195, frozenset({"A", "Q"}): 91,  frozenset({"A", "E"}): 107,
    frozenset({"A", "G"}): 60,  frozenset({"A", "H"}): 86,  frozenset({"A", "I"}): 94,
    frozenset({"A", "L"}): 96,  frozenset({"A", "K"}): 106, frozenset({"A", "M"}): 84,
    frozenset({"A", "F"}): 113, frozenset({"A", "P"}): 27,  frozenset({"A", "S"}): 99,
    frozenset({"A", "T"}): 58,  frozenset({"A", "W"}): 148, frozenset({"A", "Y"}): 112,
    frozenset({"A", "V"}): 64,
    frozenset({"R", "N"}): 86,  frozenset({"R", "D"}): 96,  frozenset({"R", "C"}): 180,
    frozenset({"R", "Q"}): 43,  frozenset({"R", "E"}): 54,  frozenset({"R", "G"}): 125,
    frozenset({"R", "H"}): 29,  frozenset({"R", "I"}): 97,  frozenset({"R", "L"}): 102,
    frozenset({"R", "K"}): 26,  frozenset({"R", "M"}): 91,  frozenset({"R", "F"}): 97,
    frozenset({"R", "P"}): 103, frozenset({"R", "S"}): 110, frozenset({"R", "T"}): 71,
    frozenset({"R", "W"}): 101, frozenset({"R", "Y"}): 77,  frozenset({"R", "V"}): 96,
    frozenset({"N", "D"}): 23,  frozenset({"N", "C"}): 139, frozenset({"N", "Q"}): 46,
    frozenset({"N", "E"}): 42,  frozenset({"N", "G"}): 80,  frozenset({"N", "H"}): 68,
    frozenset({"N", "I"}): 149, frozenset({"N", "L"}): 153, frozenset({"N", "K"}): 94,
    frozenset({"N", "M"}): 142, frozenset({"N", "F"}): 158, frozenset({"N", "P"}): 91,
    frozenset({"N", "S"}): 46,  frozenset({"N", "T"}): 65,  frozenset({"N", "W"}): 174,
    frozenset({"N", "Y"}): 143, frozenset({"N", "V"}): 133,
    frozenset({"D", "C"}): 154, frozenset({"D", "Q"}): 61,  frozenset({"D", "E"}): 45,
    frozenset({"D", "G"}): 94,  frozenset({"D", "H"}): 81,  frozenset({"D", "I"}): 168,
    frozenset({"D", "L"}): 172, frozenset({"D", "K"}): 101, frozenset({"D", "M"}): 160,
    frozenset({"D", "F"}): 177, frozenset({"D", "P"}): 108, frozenset({"D", "S"}): 65,
    frozenset({"D", "T"}): 85,  frozenset({"D", "W"}): 181, frozenset({"D", "Y"}): 160,
    frozenset({"D", "V"}): 152,
    frozenset({"C", "Q"}): 154, frozenset({"C", "E"}): 170, frozenset({"C", "G"}): 159,
    frozenset({"C", "H"}): 174, frozenset({"C", "I"}): 198, frozenset({"C", "L"}): 198,
    frozenset({"C", "K"}): 202, frozenset({"C", "M"}): 196, frozenset({"C", "F"}): 205,
    frozenset({"C", "P"}): 169, frozenset({"C", "S"}): 112, frozenset({"C", "T"}): 149,
    frozenset({"C", "W"}): 215, frozenset({"C", "Y"}): 194, frozenset({"C", "V"}): 192,
    frozenset({"Q", "E"}): 29,  frozenset({"Q", "G"}): 87,  frozenset({"Q", "H"}): 24,
    frozenset({"Q", "I"}): 109, frozenset({"Q", "L"}): 113, frozenset({"Q", "K"}): 53,
    frozenset({"Q", "M"}): 101, frozenset({"Q", "F"}): 116, frozenset({"Q", "P"}): 76,
    frozenset({"Q", "S"}): 68,  frozenset({"Q", "T"}): 42,  frozenset({"Q", "W"}): 130,
    frozenset({"Q", "Y"}): 99,  frozenset({"Q", "V"}): 96,
    frozenset({"E", "G"}): 98,  frozenset({"E", "H"}): 40,  frozenset({"E", "I"}): 134,
    frozenset({"E", "L"}): 138, frozenset({"E", "K"}): 56,  frozenset({"E", "M"}): 126,
    frozenset({"E", "F"}): 140, frozenset({"E", "P"}): 93,  frozenset({"E", "S"}): 80,
    frozenset({"E", "T"}): 65,  frozenset({"E", "W"}): 152, frozenset({"E", "Y"}): 122,
    frozenset({"E", "V"}): 121,
    frozenset({"G", "H"}): 98,  frozenset({"G", "I"}): 135, frozenset({"G", "L"}): 138,
    frozenset({"G", "K"}): 127, frozenset({"G", "M"}): 127, frozenset({"G", "F"}): 153,
    frozenset({"G", "P"}): 42,  frozenset({"G", "S"}): 56,  frozenset({"G", "T"}): 59,
    frozenset({"G", "W"}): 184, frozenset({"G", "Y"}): 147, frozenset({"G", "V"}): 109,
    frozenset({"H", "I"}): 94,  frozenset({"H", "L"}): 99,  frozenset({"H", "K"}): 32,
    frozenset({"H", "M"}): 87,  frozenset({"H", "F"}): 100, frozenset({"H", "P"}): 77,
    frozenset({"H", "S"}): 89,  frozenset({"H", "T"}): 47,  frozenset({"H", "W"}): 115,
    frozenset({"H", "Y"}): 83,  frozenset({"H", "V"}): 84,
    frozenset({"I", "L"}): 5,   frozenset({"I", "K"}): 102, frozenset({"I", "M"}): 10,
    frozenset({"I", "F"}): 21,  frozenset({"I", "P"}): 95,  frozenset({"I", "S"}): 142,
    frozenset({"I", "T"}): 89,  frozenset({"I", "W"}): 61,  frozenset({"I", "Y"}): 33,
    frozenset({"I", "V"}): 29,
    frozenset({"L", "K"}): 107, frozenset({"L", "M"}): 15,  frozenset({"L", "F"}): 22,
    frozenset({"L", "P"}): 98,  frozenset({"L", "S"}): 145, frozenset({"L", "T"}): 92,
    frozenset({"L", "W"}): 61,  frozenset({"L", "Y"}): 36,  frozenset({"L", "V"}): 32,
    frozenset({"K", "M"}): 95,  frozenset({"K", "F"}): 102, frozenset({"K", "P"}): 103,
    frozenset({"K", "S"}): 121, frozenset({"K", "T"}): 78,  frozenset({"K", "W"}): 110,
    frozenset({"K", "Y"}): 85,  frozenset({"K", "V"}): 97,
    frozenset({"M", "F"}): 28,  frozenset({"M", "P"}): 87,  frozenset({"M", "S"}): 135,
    frozenset({"M", "T"}): 81,  frozenset({"M", "W"}): 67,  frozenset({"M", "Y"}): 36,
    frozenset({"M", "V"}): 21,
    frozenset({"F", "P"}): 114, frozenset({"F", "S"}): 155, frozenset({"F", "T"}): 103,
    frozenset({"F", "W"}): 40,  frozenset({"F", "Y"}): 22,  frozenset({"F", "V"}): 50,
    frozenset({"P", "S"}): 74,  frozenset({"P", "T"}): 38,  frozenset({"P", "W"}): 147,
    frozenset({"P", "Y"}): 110, frozenset({"P", "V"}): 68,
    frozenset({"S", "T"}): 58,  frozenset({"S", "W"}): 177, frozenset({"S", "Y"}): 144,
    frozenset({"S", "V"}): 124,
    frozenset({"T", "W"}): 128, frozenset({"T", "Y"}): 92,  frozenset({"T", "V"}): 69,
    frozenset({"W", "Y"}): 37,  frozenset({"W", "V"}): 88,
    frozenset({"Y", "V"}): 55,
}


def _grantham_dist(variant: str) -> int:
    """Grantham distance for a single-mutation variant string (e.g. 'A42V').

    Returns 0 for synonymous, 215 (max) for unknown pairs.
    """
    m = _SINGLE_POS_RE.match(variant)
    if not m:
        return 215
    wt, mt = variant[0], variant[-1]
    if wt == mt:
        return 0
    return _GRANTHAM.get(frozenset({wt, mt}), 215)


def _rho_from_cumulative(cumulative: int) -> float:
    """Estimated Spearman ρ based on cumulative EVOLVEpro data points.

    Derived from published benchmarks:
    - ≤96 → 0.40 (Yang et al. 2019, Nature Methods; ~24 pts extrapolated)
    - ≤192 → 0.50 (ProteinGym average; ~96 pts)
    - ≤384 → 0.60 (iScience 2025; ~200 pts)
    - 385+ → 0.70 (Wu et al. 2019, PNAS; ≥384 pts)
    """
    if cumulative <= 96:
        return 0.40
    elif cumulative <= 192:
        return 0.50
    elif cumulative <= 384:
        return 0.60
    else:
        return 0.70


def sigma_adaptive_params(evolvepro_round: int, round_size: int) -> tuple[float, float]:
    """Compute pool K and entropy_weight from EVOLVEpro round information.

    Uses UCB-style exploration: K = K_max * (1 - ρ), where ρ is predicted
    model quality and K_max ≈ 0.833 (calibrated so K=0.50 at ρ=0.40).

    Returns
    -------
    tuple[float, float]
        (K, entropy_weight) — K controls the σ-adaptive pool threshold;
        entropy_weight controls position-entropy bonus in Pareto selection.
    """
    cumulative = evolvepro_round * round_size
    rho = _rho_from_cumulative(cumulative)
    # Lookup table matches calibration (K_max=5/6 rounded to nearest 0.05)
    k_map = {0.40: 0.50, 0.50: 0.40, 0.60: 0.30, 0.70: 0.25}
    ew_map = {0.40: 0.30, 0.50: 0.25, 0.60: 0.20, 0.70: 0.15}
    return k_map[rho], ew_map[rho]


def _position_filter_with_tiebreak(
    rows: list[tuple[str, float]],
    max_per_position: int,
    score_tie_pct: float = 0.02,
) -> list[tuple[str, float]]:
    """Filter at most *max_per_position* variants per residue.

    When the top variant at a position is within *score_tie_pct* (2 %) of the
    next candidate, Grantham distance is used as a tie-breaker — preferring
    the more conservative (smaller-distance) amino acid substitution.

    Parameters
    ----------
    rows : list[tuple[str, float]]
        (variant, y_pred) pairs, pre-sorted by y_pred descending.
    max_per_position : int
        Maximum variants allowed per position.
    score_tie_pct : float
        Relative score difference threshold for applying Grantham tie-break.

    Returns
    -------
    list[tuple[str, float]]
        Filtered and re-sorted rows.
    """
    from collections import defaultdict

    pos_groups: dict[int, list[tuple[str, float]]] = defaultdict(list)
    no_pos: list[tuple[str, float]] = []

    for variant, y in rows:
        m = _SINGLE_POS_RE.match(variant)
        if m:
            pos_groups[int(m.group(1))].append((variant, y))
        else:
            no_pos.append((variant, y))

    filtered: list[tuple[str, float]] = []

    for candidates in pos_groups.values():
        if len(candidates) <= max_per_position:
            filtered.extend(candidates)
            continue

        selected: list[tuple[str, float]] = []
        remaining = list(candidates)  # already sorted desc by y_pred

        while len(selected) < max_per_position and remaining:
            top_score = remaining[0][1]
            abs_top = abs(top_score)

            if abs_top < 1e-9:
                tie_group = [r for r in remaining if abs(r[1]) < 1e-9]
            else:
                tie_group = [
                    r for r in remaining
                    if (top_score - r[1]) / abs_top <= score_tie_pct
                ]

            if len(tie_group) <= 1:
                best = remaining[0]
            else:
                # Conservative substitution first, then alphabetical
                best = min(tie_group, key=lambda r: (_grantham_dist(r[0]), r[0]))

            selected.append(best)
            remaining = [r for r in remaining if r[0] != best[0]]

        filtered.extend(selected)

    filtered.extend(no_pos)
    filtered.sort(key=lambda r: r[1], reverse=True)
    return filtered


def _position_entropy(pool: list[tuple[str, float]]) -> dict[int, float]:
    """Shannon entropy of y_pred distribution at each position.

    Positions with many competitive mutations (high entropy) are uncertain —
    multiple amino acid changes appear similarly beneficial. Entropy-guided
    selection prioritises exploring these positions over positions dominated
    by a single standout mutation.

    Returns
    -------
    dict[int, float]
        Normalised per-position entropy (0–1), keyed by 1-based position.
    """
    pos_scores: dict[int, list[float]] = {}
    for variant, y in pool:
        m = _POS_RE.search(variant)
        if not m:
            continue
        pos = int(m.group(1))
        pos_scores.setdefault(pos, []).append(max(y, 0.0))

    raw: dict[int, float] = {}
    for pos, scores in pos_scores.items():
        total = sum(scores)
        if total <= 0:
            raw[pos] = 0.0
            continue
        probs = [s / total for s in scores if s > 0]
        raw[pos] = -sum(p * math.log2(p) for p in probs if p > 0)

    max_h = max(raw.values()) if raw else 1.0
    if max_h == 0:
        return {p: 0.0 for p in raw}
    return {p: h / max_h for p, h in raw.items()}


# Flexible column name resolution — first match wins
VARIANT_COLUMNS = ["variant", "variants", "mutation", "mutations", "mutant", "mutation_list"]
SCORE_COLUMNS = ["y_pred", "property_value", "predicted_fitness", "fitness", "score", "DMS_score"]


def load_evolvepro_csv(
    filepath: str | Path,
    top_n: int = 96,
    max_per_position: int = 0,
    domains: list[dict] | None = None,
    domain_diversity: bool = False,
    domain_strategy: str = "proportional",
    domain_overlap_policy: str = "first",
    linker_handling: str = "include",
    domain_quota_min: int = 1,
    pareto_diversity: bool = False,
    entropy_weight: float = 0.0,
    pool_multiplier: float = 2.0,
    distance_mode: str = "auto",
    ca_coords: list[tuple[float, float, float] | None] | None = None,
    evolvepro_round: int = 0,
    round_size: int = 96,
) -> dict:
    """Load EVOLVEpro df_test.csv and return selected variants.

    Parameters
    ----------
    filepath : str | Path
        Path to the EVOLVEpro CSV. Variant column is detected from
        VARIANT_COLUMNS (first match). Score column from SCORE_COLUMNS.
    top_n : int
        Maximum number of variants to select.
    max_per_position : int
        Max mutations per amino acid position (0 = no limit).
    domains : list[dict] | None
        Domain boundary dicts with 'name', 'start', 'end' keys.
    domain_diversity : bool
        Enable domain-aware quota selection.
    domain_strategy : str
        'proportional' or 'equal' quota strategy.
    pareto_diversity : bool
        Enable Pareto fitness-diversity selection.

    Returns
    -------
    dict
        Keys: variants, y_preds, total_count, selected_count,
        filtered_count, domain_stats, pareto_replaced.
    """
    filepath = str(filepath)

    rows: list[tuple[str, float]] = []
    with open(filepath, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        columns = reader.fieldnames or []

        variant_col = next((c for c in VARIANT_COLUMNS if c in columns), None)
        if variant_col is None:
            raise ValueError(
                f"EVOLVEpro CSV must have a variant column. "
                f"Supported: {VARIANT_COLUMNS}. Found: {columns}"
            )
        score_col = next((c for c in SCORE_COLUMNS if c in columns), None)

        for row in reader:
            variant = row.get(variant_col, "").strip()
            if not variant:
                continue
            try:
                y_pred = float(row[score_col]) if score_col and row.get(score_col) else 0.0
            except (ValueError, TypeError):
                y_pred = 0.0
            rows.append((variant, y_pred))

    has_score = score_col is not None
    if has_score:
        rows.sort(key=lambda r: r[1], reverse=True)

    # top_n <= 0 means "all variants" (no limit)
    if top_n <= 0:
        top_n = len(rows)

    # σ-adaptive pool: derive K and entropy_weight from EVOLVEpro round
    sigma_pool_size: int | None = None
    if evolvepro_round > 0 and has_score and len(rows) >= 2:
        k_auto, entropy_weight = sigma_adaptive_params(evolvepro_round, round_size)
        scores = [y for _, y in rows]
        try:
            sigma = statistics.stdev(scores)
        except statistics.StatisticsError:
            sigma = 0.0
        anchor_idx = min(top_n - 1, len(rows) - 1)
        anchor = rows[anchor_idx][1]
        threshold = anchor - k_auto * sigma
        adaptive_count = sum(1 for _, y in rows if y >= threshold)
        sigma_pool_size = max(top_n, adaptive_count)

    # Pool variants: all variants in the effective pool (before position/diversity filters)
    if sigma_pool_size is not None:
        effective_pool = sigma_pool_size
    elif pareto_diversity:
        effective_pool = min(len(rows), max(top_n, int(top_n * pool_multiplier)))
    else:
        effective_pool = top_n
    pool_variants = [v for v, _ in rows[:effective_pool]]

    # Position diversity filter (with Grantham tie-break)
    pre_filter_count = len(rows)
    if max_per_position > 0:
        rows = _position_filter_with_tiebreak(rows, max_per_position)

    domain_info = domains or []
    domain_stats = None
    pareto_replaced = 0

    if domain_diversity and domain_info and pareto_diversity:
        selected, domain_stats = domain_aware_select(
            rows, domain_info, top_n, domain_strategy,
            domain_overlap_policy=domain_overlap_policy,
            linker_handling=linker_handling,
            domain_quota_min=domain_quota_min,
            use_pareto=True, ca_coords=ca_coords,
            entropy_weight=entropy_weight,
            pool_multiplier=pool_multiplier,
            pool_size_override=sigma_pool_size,
            distance_mode=distance_mode,
        )
    elif domain_diversity and domain_info:
        selected, domain_stats = domain_aware_select(
            rows, domain_info, top_n, domain_strategy,
            domain_overlap_policy=domain_overlap_policy,
            linker_handling=linker_handling,
            domain_quota_min=domain_quota_min,
        )
    elif pareto_diversity:
        selected, pareto_replaced = pareto_diversity_select(
            rows, top_n, pool_multiplier=pool_multiplier,
            pool_size_override=sigma_pool_size,
            ca_coords=ca_coords,
            entropy_weight=entropy_weight,
            distance_mode=distance_mode,
        )
    else:
        selected = rows[:top_n]

    position_filter_removed = pre_filter_count - len(rows)
    domain_selected = len(selected) if (domain_diversity and domain_info) else None
    pareto_exchanges = pareto_replaced if pareto_diversity else None

    return {
        "variants": [v for v, _ in selected],
        "y_preds": [round(y, 4) for _, y in selected],
        "total_count": pre_filter_count,
        "selected_count": len(selected),
        "filtered_count": position_filter_removed,
        "domain_stats": domain_stats,
        "pareto_replaced": pareto_exchanges,
        "pool_variants": pool_variants,
        "step_stats": {
            "position_filter_removed": position_filter_removed,
            "domain_selected": domain_selected,
            "pareto_exchanges": pareto_exchanges,
        },
    }


def domain_aware_select(
    rows: list[tuple[str, float]],
    domains: list[dict],
    top_n: int,
    strategy: str = "proportional",
    domain_overlap_policy: str = "first",
    linker_handling: str = "include",
    domain_quota_min: int = 1,
    use_pareto: bool = False,
    ca_coords: list[tuple[float, float, float] | None] | None = None,
    entropy_weight: float = 0.0,
    pool_multiplier: float = 2.0,
    pool_size_override: int | None = None,
    distance_mode: str = "auto",
) -> tuple[list[tuple[str, float]], dict]:
    """Domain-based quota Top-N selection.

    PI instruction: structure-aware domain-diversified selection.

    Parameters
    ----------
    rows : list[tuple[str, float]]
        (variant, y_pred) pairs, pre-sorted by y_pred descending.
    domains : list[dict]
        Domain dicts with 'name', 'start', 'end'.
    top_n : int
        Target selection count.
    strategy : str
        'proportional' or 'equal'.
    use_pareto : bool
        Apply Pareto diversity within each domain.

    Returns
    -------
    tuple[list, dict]
        (selected rows, per-domain stats dict).
    """
    if not domains or top_n <= 0:
        return rows[:top_n], {}

    # Map each variant to a domain.
    domain_bins: dict[str, list[tuple[str, float]]] = {d["name"]: [] for d in domains}
    domain_bins["linker"] = []

    for variant, y in rows:
        m = _POS_RE.search(variant)
        if not m:
            if linker_handling != "exclude":
                domain_bins["linker"].append((variant, y))
            continue
        pos = int(m.group(1))
        matched = [d for d in domains if d["start"] <= pos <= d["end"]]
        assigned = False
        if matched:
            if domain_overlap_policy == "largest":
                chosen = max(matched, key=lambda d: d["end"] - d["start"])
            else:
                chosen = matched[0]
            domain_bins[chosen["name"]].append((variant, y))
            assigned = True
        if not assigned:
            if linker_handling != "exclude":
                domain_bins["linker"].append((variant, y))

    # Calculate quotas.
    domain_names = [d["name"] for d in domains]
    quota_names = list(domain_names)
    if linker_handling == "separate-bin" and domain_bins["linker"]:
        quota_names.append("linker")

    if strategy == "equal":
        n_domains = len(quota_names)
        base_quota = top_n // n_domains if n_domains else 0
        remainder = top_n % n_domains if n_domains else 0
        quotas = {}
        for i, name in enumerate(quota_names):
            quotas[name] = base_quota + (1 if i < remainder else 0)
    else:  # proportional
        total_length = sum(d["end"] - d["start"] + 1 for d in domains)
        if linker_handling == "separate-bin":
            total_length += max(len(domain_bins["linker"]), 0)
        if total_length == 0:
            return rows[:top_n], {}
        raw_quotas = {
            d["name"]: (d["end"] - d["start"] + 1) / total_length * top_n
            for d in domains
        }
        if linker_handling == "separate-bin":
            raw_quotas["linker"] = len(domain_bins["linker"]) / total_length * top_n
        quotas = {name: int(q) for name, q in raw_quotas.items()}
        # Distribute rounding remainders by largest fractional part
        allocated = sum(quotas.values())
        leftover = top_n - allocated
        if leftover > 0:
            frac = sorted(
                raw_quotas.items(),
                key=lambda kv: kv[1] - int(kv[1]),
                reverse=True,
            )
            for name, _ in frac[:leftover]:
                quotas[name] += 1

    if domain_quota_min > 0:
        for name in quota_names:
            if domain_bins.get(name):
                quotas[name] = max(quotas.get(name, 0), domain_quota_min)

    # Select within each domain by y_pred order (rows already sorted)
    selected: list[tuple[str, float]] = []
    selected_set: set[str] = set()
    stats: dict[str, dict] = {}
    remaining_capacity = 0

    for name in quota_names:
        quota = quotas[name]
        candidates = domain_bins.get(name, [])
        if use_pareto and quota > 1 and len(candidates) > 1:
            picked, _ = pareto_diversity_select(
                candidates, quota,
                pool_multiplier=pool_multiplier,
                pool_size_override=pool_size_override,
                ca_coords=ca_coords,
                entropy_weight=entropy_weight,
                distance_mode=distance_mode,
            )
        else:
            picked = candidates[:quota]
        for v, y in picked:
            if v not in selected_set:
                selected.append((v, y))
                selected_set.add(v)
        actual = len(picked)
        stats[name] = {"quota": quota, "selected": actual}
        if actual < quota:
            remaining_capacity += quota - actual

    # Redistribute remaining capacity from under-filled domains
    if remaining_capacity > 0:
        unpicked: list[tuple[str, float]] = []
        for name in quota_names:
            for v, y in domain_bins.get(name, []):
                if v not in selected_set:
                    unpicked.append((v, y))
        if linker_handling != "exclude" and linker_handling != "separate-bin":
            for v, y in domain_bins["linker"]:
                if v not in selected_set:
                    unpicked.append((v, y))
        unpicked.sort(key=lambda r: r[1], reverse=True)
        for v, y in unpicked[:remaining_capacity]:
            if v not in selected_set:
                selected.append((v, y))
                selected_set.add(v)

    # Fill any remaining slots if total selected < top_n
    if len(selected) < top_n and linker_handling != "exclude":
        for v, y in domain_bins["linker"]:
            if len(selected) >= top_n:
                break
            if v not in selected_set:
                selected.append((v, y))
                selected_set.add(v)

    return selected[:top_n], stats


def pareto_diversity_select(
    rows: list[tuple[str, float]],
    top_n: int,
    pool_multiplier: float = 2.0,
    pool_size_override: int | None = None,
    ca_coords: list[tuple[float, float, float] | None] | None = None,
    entropy_weight: float = 0.0,
    distance_mode: str = "auto",
) -> tuple[list[tuple[str, float]], int]:
    """MODIFY-style Pareto fitness-diversity selection (greedy maximin).

    Selects variants that maximize minimum position distance to
    already-selected set, breaking ties by y_pred.
    Prevents clustering of mutations at nearby positions.

    When *ca_coords* is provided, real 3D Euclidean Cα distance from
    AlphaFold structures is used instead of simple 1-D position distance.
    Falls back to 1-D distance for positions without Cα coordinates.

    When *entropy_weight* > 0, the selection score blends spatial diversity
    with per-position entropy of y_pred (uncertainty-guided exploration).
    Positions where many mutations score similarly (high Shannon entropy)
    are prioritised, helping escape local optima in the fitness landscape.
    A weight of 0.3 gives a mild bias; 0.7 strongly favours uncertain positions.

    Parameters
    ----------
    rows : list[tuple[str, float]]
        (variant, y_pred) pairs, pre-sorted by y_pred descending.
    top_n : int
        Target selection count.
    pool_multiplier : float
        Candidate pool size = top_n * pool_multiplier.
    ca_coords : list[tuple[float, float, float] | None] | None
        1-based AlphaFold Cα coordinates (None entries = missing residues).
    entropy_weight : float
        Blend weight for position entropy (0 = pure maximin, 1 = pure entropy).

    Returns
    -------
    tuple[list, int]
        (selected rows, replaced count vs pure Top-N).
    """
    if top_n <= 0 or not rows:
        return rows[:top_n], 0

    if pool_size_override is not None:
        pool_size = min(len(rows), max(top_n, pool_size_override))
    else:
        pool_size = min(len(rows), max(top_n, int(top_n * pool_multiplier)))
    pool = rows[:pool_size]

    # Extract positions for distance calculation
    positions: list[int] = []
    for variant, _ in pool:
        m = _POS_RE.search(variant)
        positions.append(int(m.group(1)) if m else -1)

    # Find max position for normalization (1D fallback)
    valid_pos = [p for p in positions if p >= 0]
    max_pos = max(valid_pos) if valid_pos else 1

    # Precompute max Cα distance for normalization (avoids repeated O(N²))
    use_3d = distance_mode == "3d" or (distance_mode == "auto" and ca_coords is not None)
    _ca_max = ca_max_dist(ca_coords) if use_3d and ca_coords else 1.0

    # Per-position entropy (computed once over full pool)
    pos_entropy: dict[int, float] = _position_entropy(pool) if entropy_weight > 0 else {}

    selected_indices: list[int] = [0]  # seed: best fitness
    selected_set = {0}

    for _ in range(min(top_n, len(pool)) - 1):
        best_idx = -1
        best_score = -float("inf")
        best_y = -float("inf")

        for i in range(len(pool)):
            if i in selected_set:
                continue
            pos_i = positions[i]
            if pos_i < 0:
                min_dist = 1.0  # unknown position = treat as maximally distant
            elif use_3d and ca_coords and pos_i >= 1:
                # AlphaFold 3D Cα distance (real structural space)
                min_dist = min(
                    pairwise_ca_distance(ca_coords, pos_i, positions[j], _ca_max)
                    if positions[j] >= 1
                    else 1.0
                    for j in selected_indices
                )
            else:
                # Fallback: 1D position distance
                min_dist = min(
                    abs(pos_i - positions[j]) / max_pos if positions[j] >= 0 else 1.0
                    for j in selected_indices
                )

            if entropy_weight > 0:
                ent = pos_entropy.get(pos_i, 0.0) if pos_i >= 0 else 0.0
                score = (1.0 - entropy_weight) * min_dist + entropy_weight * ent
            else:
                score = min_dist

            y_i = pool[i][1]
            if (score > best_score) or (score == best_score and y_i > best_y):
                best_idx = i
                best_score = score
                best_y = y_i

        if best_idx < 0:
            break
        selected_indices.append(best_idx)
        selected_set.add(best_idx)

    selected = [pool[i] for i in selected_indices]

    # Count how many differ from pure Top-N
    top_n_set = {v for v, _ in pool[:top_n]}
    replaced = sum(1 for v, _ in selected if v not in top_n_set)

    return selected, replaced
