"""Bounded exact-frame single-site adapter; no functional ranking or homology.

The first UI path accepts one canonical PDB model/chain with contiguous positive
author numbers. Unsupported residue identities fail instead of being flattened.
Coordinate correspondence is checked here. Structural confidence is applied
only where the file states it: an AlphaFold model stores per-residue pLDDT in
the B-factor column, while an experimental B-factor is not a confidence score.

Those filters decide what may be selected, not what the selection is compared
with: the reported score Top-N is taken from every scored substitution in the
input, and its members that spatial selection could not use are named.
"""
from __future__ import annotations

import hashlib
import logging
import math
import re
import sys
from collections import Counter

from kuma_core.kuro.alphafold import _THREE_TO_ONE
from kuma_core.kuro.interface import reference_structure_overlap

# AlphaFold DB colours pLDDT < 50 as "very low" confidence (Jumper et al. 2021,
# Nature 596:583; AlphaFold DB FAQ). Such regions are often disordered and their
# coordinates are not a placement, so they must not count as spatial spread.
PLDDT_VERY_LOW = 50.0
# Caller-declared origin: the file was downloaded from AlphaFold DB, whose PDB
# files store per-residue pLDDT in the B-factor column.
SOURCE_ALPHAFOLD_DB = "alphafold_db"
# Caller-declared origin: a kuma ESMFold prediction of the reference, whose
# B-factor column holds pLDDT rescaled to 0-100 (esmfold.normalise_plddt_scale).
SOURCE_ESMFOLD = "esmfold"
_PLDDT_SOURCES = (SOURCE_ALPHAFOLD_DB, SOURCE_ESMFOLD)

logger = logging.getLogger(__name__)


def _is_alphafold_model(pdb_text: str) -> bool:
    """AlphaFold DB PDB files title themselves "ALPHAFOLD ... PREDICTION FOR".

    Only the TITLE records are read. A file without that title, experimental
    or unlabelled, is not treated as AlphaFold, so its B-factors are never read
    as pLDDT unless the caller declares an AlphaFold DB source.
    """
    title = " ".join(line[10:].strip() for line in pdb_text.splitlines() if line.startswith("TITLE "))
    return "ALPHAFOLD" in title.upper() and "PREDICTION" in title.upper()


def exact_pdb_context(pdb_text: str, reference: str, accession: str, *, source: str | None = None) -> dict:
    """``source=SOURCE_ALPHAFOLD_DB`` states the file came from AlphaFold DB.

    The declared origin decides pLDDT reading; the TITLE is only a cross-check.
    Without ``source`` the TITLE alone decides, as before.
    """
    if source not in (None, *_PLDDT_SOURCES):
        raise ValueError(f"Unknown strict spatial structure source: {source}")
    reference = reference.strip().rstrip("*")
    residues: dict[int, tuple[str, tuple[float, float, float] | None, float | None]] = {}
    titled = _is_alphafold_model(pdb_text)
    if source == SOURCE_ALPHAFOLD_DB and not titled:
        logger.warning("AlphaFold DB file %s has no recognised AlphaFold TITLE; "
                       "reading its B-factors as pLDDT because of the declared source", accession)
    alphafold = titled or source in _PLDDT_SOURCES
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
        plddt = None
        if alphafold:
            try:
                plddt = float(line[60:66])
            except ValueError as exc:
                raise ValueError("AlphaFold model has an unreadable pLDDT (B-factor) value") from exc
            if not 0. <= plddt <= 100.:
                raise ValueError("AlphaFold model pLDDT must lie between 0 and 100")
        residues[position] = (aa, xyz if all(math.isfinite(x) for x in xyz) else None, plddt)
    if len(chains) != 1 or not residues or sorted(residues) != list(range(1, len(residues) + 1)):
        raise ValueError("Strict spatial selection requires one chain with contiguous numbering from 1")
    sequence = "".join(residues[p][0] for p in sorted(residues))
    overlap = reference_structure_overlap(sequence, reference)
    if overlap is None:
        raise ValueError("Strict spatial selection requires a unique exact reference placement")
    offset = overlap["offset"]
    chain = next(iter(chains))
    mapping = [
        {"reference_position": p, "structure_position": p + offset,
         "chain_id": chain, "model_id": model_id, "insertion_code": "", "coordinate": residues[p + offset][1],
         "confidence": residues[p + offset][2]}
        for p in range(1, len(reference) + 1)
        if 1 <= p + offset <= len(residues) and residues[p + offset][1] is not None
    ]
    return {
        "schema_version": 1, "source_accession": accession,
        "source_sha256": hashlib.sha256(pdb_text.encode()).hexdigest(),
        "reference_sha256": hashlib.sha256(reference.encode()).hexdigest(),
        "coordinate_frame": "reference", "mapping": mapping, "pdb_text": pdb_text,
        "confidence_source": "alphafold_plddt" if alphafold else "unavailable",
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
    confidence_source = context.get("confidence_source", "unavailable")
    if confidence_source not in ("alphafold_plddt", "unavailable"):
        raise ValueError("Unknown coordinate confidence source")
    coordinate_map = {}
    low_confidence: set[int] = set()
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
        if confidence_source == "alphafold_plddt":
            plddt = m.get("confidence")
            if isinstance(plddt, bool) or not isinstance(plddt, (int, float)) or not math.isfinite(plddt):
                raise ValueError("AlphaFold mapping requires a numeric pLDDT per residue")
            if plddt < PLDDT_VERY_LOW:
                low_confidence.add(position)
    eligible: dict[int, list[tuple[str, float]]] = {}
    excluded: list[dict] = []
    # Everything that can be ranked by score: only an unchanged residue or a
    # score that is not a number keeps a row out. Reporting only, never selected from.
    scored: list[tuple[str, float, int]] = []
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
        elif position in low_confidence:
            reason = "low_confidence_coordinate"
        if reason not in ("unchanged_amino_acid", "nonfinite_score"):
            scored.append((variant, score, position))
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
        reasons = Counter(r["reason"] for r in excluded)
        detail = ", ".join(f"{reason}={n}" for reason, n in sorted(reasons.items())) or "none"
        raise ValueError(f"Strict spatial count {count} exceeds {len(candidates)} {unit} "
                         f"(excluded variants by reason: {detail})")
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
    pool = sorted(((v, score, p) for p, rows_at in eligible.items() for v, score in rows_at),
                  key=lambda row: (-row[1], row[2], row[0]))
    scored.sort(key=lambda row: (-row[1], row[2], row[0]))
    comparison = _selection_comparison(
        scored, pool, candidates, [decoded[v] for v, _ in selected], coordinate_map,
        {row["variant"]: row["reason"] for row in excluded},
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
              "coordinate_confidence": {
                  "source": confidence_source,
                  "threshold": PLDDT_VERY_LOW if confidence_source == "alphafold_plddt" else None,
                  "low_confidence_residue_count": len(low_confidence),
                  "excluded_variant_count": sum(r["reason"] == "low_confidence_coordinate" for r in excluded),
              },
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


def _selection_comparison(scored: list[tuple[str, float, int]], pool: list[tuple[str, float, int]],
                          candidates: list[tuple[str, float, int]],
                          selected: list[tuple[str, float, int]], coordinate_map: dict,
                          excluded_reasons: dict[str, str],
                          *, score_available: bool, score_order: str) -> dict:
    """Describe the selection against plain score ranking without changing it.

    ``scored`` holds every input variant that can be ranked: all of them except
    an unchanged residue or a non-finite score. Variants dropped for an explicit
    exclusion, a missing coordinate or a low-confidence coordinate are in it.
    ``pool`` holds the eligible variants (those filters applied) and
    ``candidates`` the subset left after the budget and per-site cap. All three
    are sorted by configured rank, position and variant ID.

    The primary baseline is the score Top-N of ``scored``, which is what a user
    gets by taking the N best predictions from the file. Its members that
    spatial selection could not use are listed in ``top_n_excluded`` with the
    reason. The Top-N of ``pool`` and of the per-site representatives are kept
    as secondary baselines. Ranks are taken in ``scored`` for every profile.

    Site and distance metrics use only the members with a trusted coordinate,
    i.e. the eligible ones, counted in ``spatial_variant_count``; with none of
    them the distances are null rather than zero. Coverage weights each
    eligible site once. Raw-score means undo the loader's ascending-order sign
    inversion; the direction-aware gap is a mean-score difference, never a
    fitness claim.
    """
    if score_order not in ("asc", "desc"):
        raise ValueError("Unknown configured score direction")
    ranks: dict[str, float] = {}
    i = 0
    while i < len(scored):
        end = i + 1
        while end < len(scored) and scored[end][1] == scored[i][1]:
            end += 1
        for variant, _, _ in scored[i:end]:
            ranks[variant] = (i + 1 + end) / 2.
        i = end
    positions = sorted({p for _, _, p in pool})
    usable = {v for v, _, _ in pool}

    def profile(rows: list[tuple[str, float, int]]) -> dict:
        multiplicity = Counter(p for v, _, p in rows if v in usable)
        sites = sorted(multiplicity)
        nearest = [min(math.dist(coordinate_map[p], coordinate_map[q]) for q in sites)
                   for p in positions] if sites else []
        mean = _finite_mean([score for _, score, _ in rows]) if score_available else None
        return {
            "variant_count": len(rows), "spatial_variant_count": sum(multiplicity.values()),
            "site_count": len(sites),
            "max_variants_per_site": max(multiplicity.values(), default=0),
            "minimum_site_distance": min((math.dist(coordinate_map[a], coordinate_map[b])
                for index, a in enumerate(sites) for b in sites[index + 1:]), default=None),
            "coverage_mean_distance": math.fsum(d / len(nearest) for d in nearest) if nearest else None,
            "coverage_max_distance": max(nearest, default=None),
            "score_mean": -mean if mean is not None and score_order == "asc" else mean,
            "mean_score_rank": _finite_mean([ranks[v] for v, _, _ in rows]) if score_available else None,
        }

    selected_profile = profile(selected)
    selected_ids = {v for v, _, _ in selected}

    def baseline(rows: list[tuple[str, float, int]]) -> dict:
        top = rows[:len(selected)]
        summary = profile(top) if score_available else None
        gap = None
        if summary is not None and summary["score_mean"] is not None and selected_profile["score_mean"] is not None:
            difference = summary["score_mean"] - selected_profile["score_mean"]
            if score_order == "asc":
                difference = -difference
            if math.isfinite(difference) and difference >= 0:
                gap = difference
        return {
            "top_n": summary,
            "top_n_variants": [v for v, _, _ in top] if score_available else None,
            "top_n_overlap_count": sum(v in selected_ids for v, _, _ in top) if score_available else None,
            "score_gap_to_top_n": gap,
        }

    return {
        "baseline": "configured-score-top-n",
        "universe": "input-variants-before-spatial-eligibility",
        "candidate_site_count": len(positions), "score_available": score_available,
        "selected": selected_profile, **baseline(scored),
        "top_n_excluded": [{"variant": v, "reason": excluded_reasons[v]}
                           for v, _, _ in scored[:len(selected)] if v in excluded_reasons] if score_available else None,
        "eligible_top_n": {
            "universe": "eligible-variants-before-budget-and-cap-policy", **baseline(pool),
        },
        "representative_top_n": {
            "universe": "eligible-variants-after-budget-and-cap-policy", **baseline(candidates),
        },
    }
