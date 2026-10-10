"""Bounded exact-frame single-site adapter; no functional ranking or homology.

The first UI path accepts one canonical PDB model/chain with contiguous positive
author numbers. Unsupported residue identities fail instead of being flattened.
This checks coordinate correspondence, not biological structural confidence.
"""
from __future__ import annotations

import hashlib
import math
import re
import sys
from collections import Counter

from kuma_core.kuro.alphafold import _THREE_TO_ONE
from kuma_core.kuro.interface import exact_reference_offset


def exact_pdb_context(pdb_text: str, reference: str, accession: str) -> dict:
    reference = reference.strip().rstrip("*")
    residues: dict[int, tuple[str, tuple[float, float, float] | None]] = {}
    chains: set[str] = set()
    models = 0
    model_id = 1
    for line in pdb_text.splitlines():
        if line.startswith("MODEL "):
            models += 1
            if models > 1:
                raise ValueError("Strict spatial selection requires one PDB model")
            try:
                model_id = int(line[10:14])
            except ValueError as exc:
                raise ValueError("Malformed PDB model identity") from exc
        if not line.startswith("ATOM  ") or line[12:16].strip() != "CA":
            continue
        if len(line) < 54 or line[16].strip() or line[26].strip():
            raise ValueError("Strict spatial selection does not support alternate/insertion identities")
        chains.add(line[21])
        try:
            position = int(line[22:26])
            coordinate = tuple(float(line[a:b]) for a, b in ((30, 38), (38, 46), (46, 54)))
        except ValueError as exc:
            raise ValueError("Malformed PDB C-alpha record") from exc
        if position < 1 or position in residues:
            raise ValueError("Strict spatial selection requires unique positive residue numbers")
        aa = _THREE_TO_ONE.get(line[17:20].strip(), "X")
        if aa == "X":
            raise ValueError("Strict spatial selection requires standard amino-acid identities")
        xyz = (coordinate[0], coordinate[1], coordinate[2])
        residues[position] = (aa, xyz if all(math.isfinite(x) for x in xyz) else None)
    if len(chains) != 1 or not residues or sorted(residues) != list(range(1, len(residues) + 1)):
        raise ValueError("Strict spatial selection requires one chain with contiguous numbering from 1")
    sequence = "".join(residues[p][0] for p in sorted(residues))
    offset = exact_reference_offset(sequence, reference)
    if offset is None:
        raise ValueError("Strict spatial selection requires a unique exact reference placement")
    chain = next(iter(chains))
    mapping = [
        {"reference_position": p, "structure_position": p + offset,
         "chain_id": chain, "model_id": model_id, "insertion_code": "", "coordinate": residues[p + offset][1]}
        for p in range(1, len(reference) + 1) if residues[p + offset][1] is not None
    ]
    return {
        "schema_version": 1, "source_accession": accession,
        "source_sha256": hashlib.sha256(pdb_text.encode()).hexdigest(),
        "reference_sha256": hashlib.sha256(reference.encode()).hexdigest(),
        "coordinate_frame": "reference", "mapping": mapping, "pdb_text": pdb_text,
        "selection_policy": "single-site-full-pool-fps-v1",
    }


def select_single_sites(rows: list[tuple[str, float]], reference: str, context: dict,
                        count: int, excluded_ranges: list[dict] | None = None) -> tuple[list[tuple[str, float]], dict]:
    """Explicit site or variant budget, configured rank direction, existing FPS.

    No functional annotation is an input. Count is explicit and never silently
    reduced. Unsupported multi-site rows reject this opt-in path as a whole.
    """
    from kuma_core.kuro.evolvepro import structural_diversity_select

    if type(count) is not int or count <= 0:
        raise ValueError("Strict spatial selection requires a positive explicit count")
    budget = context.get("budget_mode", "unique_sites")
    cap = context.get("site_cap")
    if budget not in ("unique_sites", "distinct_variants"):
        raise ValueError("Unknown strict spatial budget mode")
    if cap is not None and (type(cap) is not int or cap < 1):
        raise ValueError("Site cap must be a positive integer or null")
    if budget == "unique_sites" and cap is not None:
        raise ValueError("Explicit site cap requires distinct-variant budget mode")
    reference = reference.strip().rstrip("*")
    coordinate_map = {}
    for m in context["mapping"]:
        position, coordinate = m["reference_position"], m["coordinate"]
        if type(position) is not int or not 1 <= position <= len(reference) or position in coordinate_map:
            raise ValueError("Mapping requires unique valid reference positions")
        if coordinate is not None:
            if not isinstance(coordinate, (tuple, list)) or len(coordinate) != 3 or any(
                isinstance(x, bool) or not isinstance(x, (int, float)) for x in coordinate
            ):
                raise ValueError("Mapping coordinates must contain three numeric components")
            if not all(math.isfinite(x) for x in coordinate):
                coordinate = None
        coordinate_map[position] = coordinate
    eligible: dict[int, list[tuple[str, float]]] = {}
    excluded: list[dict] = []
    seen: dict[str, float] = {}
    for variant, score in rows:
        match = re.fullmatch(r"([ACDEFGHIKLMNPQRSTVWY])([1-9]\d*)([ACDEFGHIKLMNPQRSTVWY])", variant)
        if not match:
            raise ValueError("Strict spatial selection supports single-site substitutions only")
        if variant in seen:
            if seen[variant] != score:
                raise ValueError("Conflicting duplicate variant scores in strict spatial input")
            continue
        seen[variant] = score
        position = int(match[2])
        if not 1 <= position <= len(reference) or reference[position - 1] != match[1]:
            raise ValueError(f"Variant {variant} does not match the reference identity")
        reason = None
        if match[1] == match[3]:
            reason = "unchanged_amino_acid"
        elif not math.isfinite(score):
            reason = "nonfinite_score"
        elif any(r["start"] <= position <= r["end"] for r in excluded_ranges or []):
            reason = "explicit_exclusion"
        elif coordinate_map.get(position) is None:
            reason = "missing_or_nonfinite_coordinate"
        if reason:
            excluded.append({"variant": variant, "reason": reason})
            continue
        eligible.setdefault(position, []).append((variant, score))
    positions = sorted(eligible)
    limit = 1 if budget == "unique_sites" else cap
    candidates: list[tuple[str, float, int]] = []
    for position in positions:
        ranked = sorted(eligible[position], key=lambda row: (-row[1], row[0]))
        candidates.extend((v, score, position) for v, score in ranked[:limit])
    if count > len(candidates):
        unit = "eligible unique sites" if budget == "unique_sites" else "eligible variant capacity"
        raise ValueError(f"Strict spatial count {count} exceeds {len(candidates)} {unit}")
    # Dense indices keep the existing selector's parser independent of sparse
    # reference numbering. The certificate retains actual reference identities.
    candidates.sort(key=lambda row: (-row[1], row[2], row[0]))
    encoded = [(f"A{i}G", score) for i, (_, score, _) in enumerate(candidates, 1)]
    decoded = {v: candidates[i] for i, (v, _) in enumerate(encoded)}
    known: list[tuple[float, float, float]] = [
        (coordinate_map[p][0], coordinate_map[p][1], coordinate_map[p][2]) for _, _, p in candidates
    ]
    coordinates: list[tuple[float, float, float] | None] = [None, *known]
    span = math.dist(tuple(min(c[a] for c in known) for a in range(3)),
                     tuple(max(c[a] for c in known) for a in range(3)))
    if not math.isfinite(span) or span > math.sqrt(sys.float_info.max / 4):
        raise ValueError("Coordinate span exceeds safe squared-distance arithmetic")
    selected, _ = structural_diversity_select(
        encoded, count,
        ca_coords=coordinates, anchor_variants=(), kappa=0.,
    )
    selected_positions = [decoded[v][2] for v, _ in selected]
    result = [(decoded[v][0], decoded[v][1]) for v, _ in selected]
    if len(result) != count or len({v for v, _ in result}) != count:
        raise ValueError("Strict spatial selector returned incomparable cardinality")
    selected_sites = sorted(set(selected_positions))
    site_min = min((math.dist(coordinate_map[a], coordinate_map[b])
                    for i, a in enumerate(selected_sites) for b in selected_sites[i + 1:]), default=None)
    variant_min = 0. if len(selected_sites) < count else site_min
    eligible_count = sum(map(len, eligible.values()))
    capacity_reduction = eligible_count - len(candidates)
    comparison = _selection_comparison(
        candidates, [decoded[v] for v, _ in selected], coordinate_map,
        score_available=context.get("score_available", True),
        score_order=context.get("score_order", "desc"),
    )
    report = {**context, "selected_variants": [v for v, _ in result],
              "budget_mode": budget, "site_cap": cap,
              "selection_policy": ("single-site-full-pool-fps-v1" if budget == "unique_sites"
                                   else "distinct-variant-full-pool-fps-v1"),
              "selected_positions": selected_positions, "eligible_positions": positions,
              "eligible_site_count": len(positions), "requested_count": count,
              "eligible_variant_count": eligible_count, "variant_capacity": len(candidates),
              "selected_variant_count": count, "selected_site_count": len(selected_sites),
              "site_multiplicities": [{"reference_position": p, "variant_count": selected_positions.count(p)}
                                      for p in selected_sites],
              "geometry_variant_min_pair_distance": variant_min,
              "geometry_site_min_pair_distance": site_min,
              "comparison": comparison,
              "excluded": excluded, "input_variant_count": len(rows),
              "same_site_collapsed": capacity_reduction if budget == "unique_sites" else 0,
              "site_cap_excluded_count": capacity_reduction if budget == "distinct_variants" else 0}
    return result, report


def _finite_mean(values: list[float]) -> float | None:
    """Keep diagnostics JSON-safe even when finite score arithmetic overflows."""
    try:
        value = math.fsum(v / len(values) for v in values)
    except OverflowError:
        return None
    return value if math.isfinite(value) else None


def _selection_comparison(candidates: list[tuple[str, float, int]],
                          selected: list[tuple[str, float, int]], coordinate_map: dict,
                          *, score_available: bool, score_order: str) -> dict:
    """Describe the same effective pool without changing the selection policy.

    Candidates are already sorted by configured rank, position and variant ID,
    after validity, budget and cap handling. Coverage weights each eligible site
    once. Raw-score means undo the loader's ascending-order sign inversion;
    the direction-aware gap is a mean-score difference, never a fitness claim.
    """
    if score_order not in ("asc", "desc"):
        raise ValueError("Unknown configured score direction")
    ranks: dict[str, float] = {}
    i = 0
    while i < len(candidates):
        end = i + 1
        while end < len(candidates) and candidates[end][1] == candidates[i][1]:
            end += 1
        for variant, _, _ in candidates[i:end]:
            ranks[variant] = (i + 1 + end) / 2.
        i = end
    positions = sorted({p for _, _, p in candidates})

    def profile(rows: list[tuple[str, float, int]]) -> dict:
        multiplicity = Counter(p for _, _, p in rows)
        sites = sorted(multiplicity)
        nearest = [min(math.dist(coordinate_map[p], coordinate_map[q]) for q in sites)
                   for p in positions]
        mean = _finite_mean([score for _, score, _ in rows]) if score_available else None
        return {
            "variant_count": len(rows), "site_count": len(sites),
            "max_variants_per_site": max(multiplicity.values()),
            "minimum_site_distance": min((math.dist(coordinate_map[a], coordinate_map[b])
                for index, a in enumerate(sites) for b in sites[index + 1:]), default=None),
            "coverage_mean_distance": math.fsum(d / len(nearest) for d in nearest),
            "coverage_max_distance": max(nearest),
            "score_mean": -mean if mean is not None and score_order == "asc" else mean,
            "mean_score_rank": _finite_mean([ranks[v] for v, _, _ in rows]) if score_available else None,
        }

    selected_profile = profile(selected)
    baseline_rows = candidates[:len(selected)]
    baseline = profile(baseline_rows) if score_available else None
    gap = None
    if baseline is not None and baseline["score_mean"] is not None and selected_profile["score_mean"] is not None:
        difference = baseline["score_mean"] - selected_profile["score_mean"]
        if score_order == "asc":
            difference = -difference
        if math.isfinite(difference) and difference >= 0:
            gap = difference
    selected_ids = {v for v, _, _ in selected}
    return {
        "baseline": "configured-score-top-n",
        "universe": "eligible-variants-after-budget-and-cap-policy",
        "candidate_site_count": len(positions), "score_available": score_available,
        "selected": selected_profile, "top_n": baseline,
        "top_n_variants": [v for v, _, _ in baseline_rows] if score_available else None,
        "top_n_overlap_count": sum(v in selected_ids for v, _, _ in baseline_rows) if score_available else None,
        "score_gap_to_top_n": gap,
    }
