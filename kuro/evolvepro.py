"""EVOLVEpro variant selection and diversity optimization.

Provides CSV loading, domain-aware selection, and Pareto diversity
selection for EVOLVEpro-predicted SDM variants.
"""

from __future__ import annotations

import csv
import math
import re
from pathlib import Path

from kuro.esm_embeddings import pairwise_esm_distance

_POS_RE = re.compile(r"[A-Z](\d+)[A-Z]")
_SINGLE_POS_RE = re.compile(r"^[A-Z](\d+)[A-Z]$")


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
    pareto_diversity: bool = False,
    entropy_weight: float = 0.0,
    esm_embedding: list[list[float]] | None = None,
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

    # Position diversity filter
    pre_filter_count = len(rows)
    if max_per_position > 0:
        pos_count: dict[int, int] = {}
        filtered: list[tuple[str, float]] = []
        for variant, y in rows:
            m = _SINGLE_POS_RE.match(variant)
            pos = int(m.group(1)) if m else -1
            count = pos_count.get(pos, 0)
            if pos == -1 or count < max_per_position:
                filtered.append((variant, y))
                pos_count[pos] = count + 1
        rows = filtered

    domain_info = domains or []
    domain_stats = None
    pareto_replaced = 0

    if domain_diversity and domain_info and pareto_diversity:
        selected, domain_stats = domain_aware_select(
            rows, domain_info, top_n, domain_strategy,
            use_pareto=True, esm_embedding=esm_embedding,
            entropy_weight=entropy_weight,
        )
    elif domain_diversity and domain_info:
        selected, domain_stats = domain_aware_select(
            rows, domain_info, top_n, domain_strategy,
        )
    elif pareto_diversity:
        selected, pareto_replaced = pareto_diversity_select(
            rows, top_n, esm_embedding=esm_embedding,
            entropy_weight=entropy_weight,
        )
    else:
        selected = rows[:top_n]

    return {
        "variants": [v for v, _ in selected],
        "y_preds": [round(y, 4) for _, y in selected],
        "total_count": pre_filter_count,
        "selected_count": len(selected),
        "filtered_count": pre_filter_count - len(rows),
        "domain_stats": domain_stats,
        "pareto_replaced": pareto_replaced if pareto_diversity else None,
    }


def domain_aware_select(
    rows: list[tuple[str, float]],
    domains: list[dict],
    top_n: int,
    strategy: str = "proportional",
    use_pareto: bool = False,
    esm_embedding: list[list[float]] | None = None,
    entropy_weight: float = 0.0,
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

    # Map each variant to a domain (first match wins on overlap)
    domain_bins: dict[str, list[tuple[str, float]]] = {d["name"]: [] for d in domains}
    domain_bins["linker"] = []

    for variant, y in rows:
        m = _POS_RE.search(variant)
        if not m:
            domain_bins["linker"].append((variant, y))
            continue
        pos = int(m.group(1))
        assigned = False
        for d in domains:
            if d["start"] <= pos <= d["end"]:
                domain_bins[d["name"]].append((variant, y))
                assigned = True
                break
        if not assigned:
            domain_bins["linker"].append((variant, y))

    # Calculate quotas (linker gets no dedicated quota)
    domain_names = [d["name"] for d in domains]
    if strategy == "equal":
        n_domains = len(domain_names)
        base_quota = top_n // n_domains if n_domains else 0
        remainder = top_n % n_domains if n_domains else 0
        quotas = {}
        for i, name in enumerate(domain_names):
            quotas[name] = base_quota + (1 if i < remainder else 0)
    else:  # proportional
        total_length = sum(d["end"] - d["start"] + 1 for d in domains)
        if total_length == 0:
            return rows[:top_n], {}
        raw_quotas = {
            d["name"]: (d["end"] - d["start"] + 1) / total_length * top_n
            for d in domains
        }
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

    # Select within each domain by y_pred order (rows already sorted)
    selected: list[tuple[str, float]] = []
    selected_set: set[str] = set()
    stats: dict[str, dict] = {}
    remaining_capacity = 0

    for name in domain_names:
        quota = quotas[name]
        candidates = domain_bins.get(name, [])
        if use_pareto and quota > 1 and len(candidates) > 1:
            picked, _ = pareto_diversity_select(
                candidates, quota,
                esm_embedding=esm_embedding,
                entropy_weight=entropy_weight,
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
        for name in domain_names:
            for v, y in domain_bins.get(name, []):
                if v not in selected_set:
                    unpicked.append((v, y))
        for v, y in domain_bins["linker"]:
            if v not in selected_set:
                unpicked.append((v, y))
        unpicked.sort(key=lambda r: r[1], reverse=True)
        for v, y in unpicked[:remaining_capacity]:
            if v not in selected_set:
                selected.append((v, y))
                selected_set.add(v)

    # Fill any remaining slots if total selected < top_n
    if len(selected) < top_n:
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
    esm_embedding: list[list[float]] | None = None,
    entropy_weight: float = 0.0,
) -> tuple[list[tuple[str, float]], int]:
    """MODIFY-style Pareto fitness-diversity selection (greedy maximin).

    Selects variants that maximize minimum position distance to
    already-selected set, breaking ties by y_pred.
    Prevents clustering of mutations at nearby positions.

    When *esm_embedding* is provided, cosine distance in the ESM-2
    representation space is used instead of simple 1-D position distance.
    Falls back to 1-D distance for positions outside the embedding range.

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
    esm_embedding : list[list[float]] | None
        Per-residue ESM-2 embedding vectors (1-based indexing via helper).
    entropy_weight : float
        Blend weight for position entropy (0 = pure maximin, 1 = pure entropy).

    Returns
    -------
    tuple[list, int]
        (selected rows, replaced count vs pure Top-N).
    """
    if top_n <= 0 or not rows:
        return rows[:top_n], 0

    pool_size = min(len(rows), max(top_n, int(top_n * pool_multiplier)))
    pool = rows[:pool_size]

    # Extract positions for distance calculation
    positions: list[int] = []
    for variant, _ in pool:
        m = _POS_RE.search(variant)
        positions.append(int(m.group(1)) if m else -1)

    # Find max position for normalization
    valid_pos = [p for p in positions if p >= 0]
    max_pos = max(valid_pos) if valid_pos else 1

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
            elif esm_embedding and pos_i >= 1:
                # ESM-2 structural distance (cosine in embedding space)
                min_dist = min(
                    pairwise_esm_distance(esm_embedding, pos_i, positions[j])
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
