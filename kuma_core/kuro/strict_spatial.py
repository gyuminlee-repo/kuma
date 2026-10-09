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
    """One representative/site, configured rank direction, then existing FPS.

    No functional annotation is an input. Count is explicit and never silently
    reduced. Unsupported multi-site rows reject this opt-in path as a whole.
    """
    from kuma_core.kuro.evolvepro import structural_diversity_select

    if type(count) is not int or count <= 0:
        raise ValueError("Strict spatial selection requires a positive explicit count")
    reference = reference.strip().rstrip("*")
    coordinate_map = {m["reference_position"]: m["coordinate"] for m in context["mapping"]}
    representatives: dict[int, tuple[str, float]] = {}
    excluded: list[dict] = []
    seen: dict[str, float] = {}
    for variant, score in rows:
        match = re.fullmatch(r"([ACDEFGHIKLMNPQRSTVWY])(\d+)([ACDEFGHIKLMNPQRSTVWY])", variant)
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
        elif position not in coordinate_map:
            reason = "missing_or_nonfinite_coordinate"
        if reason:
            excluded.append({"variant": variant, "reason": reason})
            continue
        previous = representatives.get(position)
        if previous is None or (-score, variant) < (-previous[1], previous[0]):
            representatives[position] = (variant, score)
    if count > len(representatives):
        raise ValueError(f"Strict spatial count {count} exceeds {len(representatives)} eligible unique sites")
    positions = sorted(representatives)
    # Dense indices keep the existing selector's parser independent of sparse
    # reference numbering. The certificate retains actual reference identities.
    encoded = {p: f"A{i}G" for i, p in enumerate(positions, 1)}
    decoded = {encoded[p]: p for p in positions}
    known: list[tuple[float, float, float]] = [
        (coordinate_map[p][0], coordinate_map[p][1], coordinate_map[p][2]) for p in positions
    ]
    coordinates: list[tuple[float, float, float] | None] = [None, *known]
    span = math.dist(tuple(min(c[a] for c in known) for a in range(3)),
                     tuple(max(c[a] for c in known) for a in range(3)))
    if not math.isfinite(span) or span > math.sqrt(sys.float_info.max / 4):
        raise ValueError("Coordinate span exceeds safe squared-distance arithmetic")
    ordered = sorted(positions, key=lambda p: (-representatives[p][1], p))
    selected, _ = structural_diversity_select(
        [(encoded[p], representatives[p][1]) for p in ordered], count,
        ca_coords=coordinates, anchor_variants=(), kappa=0.,
    )
    selected_positions = [decoded[v] for v, _ in selected]
    result = [representatives[p] for p in selected_positions]
    if len(result) != count or len(set(selected_positions)) != count:
        raise ValueError("Strict spatial selector returned incomparable cardinality")
    report = {**context, "selected_variants": [v for v, _ in result],
              "selected_positions": selected_positions, "eligible_positions": positions,
              "eligible_site_count": len(positions), "requested_count": count,
              "excluded": excluded, "input_variant_count": len(rows),
              "same_site_collapsed": len(set(seen)) - len(excluded) - len(positions)}
    return result, report
