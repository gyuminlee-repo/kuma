"""Multi-organism codon usage tables.

The tables themselves live in ``resources/codon_tables/*.json`` and that
directory is the source of truth: ``CodonTableRegistry`` globs it at run time,
so the shipped set is whatever it holds rather than whatever this docstring
says. Today that is E. coli K-12, B. subtilis 168, S. cerevisiae, H. sapiens
and M. extorquens AM1. Provenance differs per table and each one names its own
in a ``source`` field (Kazusa Codon Usage Database or NCBI RefSeq).

Frequencies are fraction of synonymous codons for each amino acid.
"""

from __future__ import annotations

import json
from pathlib import Path

_RESOURCES_DIR = Path(__file__).parent / "resources" / "codon_tables"

# Organism aliases: user-facing key -> JSON filename (without .json)
_ORGANISM_ALIASES: dict[str, str] = {
    "ecoli": "ecoli",
    "e. coli": "ecoli",
    "e.coli": "ecoli",
    "escherichia coli": "ecoli",
    "bsubtilis": "bsubtilis",
    "b. subtilis": "bsubtilis",
    "b.subtilis": "bsubtilis",
    "bacillus subtilis": "bsubtilis",
    "scerevisiae": "scerevisiae",
    "s. cerevisiae": "scerevisiae",
    "s.cerevisiae": "scerevisiae",
    "saccharomyces cerevisiae": "scerevisiae",
    "yeast": "scerevisiae",
    "hsapiens": "hsapiens",
    "h. sapiens": "hsapiens",
    "h.sapiens": "hsapiens",
    "homo sapiens": "hsapiens",
    "human": "hsapiens",
    # Methylorubrum and Methylobacterium are competing genus assignments for
    # this organism and public databases are split between them, so both
    # spellings resolve to the same table.
    "mextorquens": "mextorquens",
    "m. extorquens": "mextorquens",
    "m.extorquens": "mextorquens",
    "methylorubrum extorquens": "mextorquens",
    "methylorubrum extorquens am1": "mextorquens",
    "methylobacterium extorquens": "mextorquens",
    "methylobacterium extorquens am1": "mextorquens",
}


class CodonTableRegistry:
    """Registry for organism-specific codon usage tables.

    Loads JSON files from kuma_core.kuro/resources/codon_tables/ on demand and
    caches them in memory. Follows the same pattern as PolymeraseRegistry.
    """

    def __init__(self) -> None:
        self._cache: dict[str, dict[str, list[tuple[str, float]]]] = {}
        self._metadata: dict[str, dict] = {}

    def _resolve_key(self, organism: str) -> str:
        """Resolve an organism name to its canonical JSON key."""
        key = organism.strip().lower()
        resolved = _ORGANISM_ALIASES.get(key, key)
        return resolved

    def _load(self, key: str) -> dict[str, list[tuple[str, float]]]:
        """Load a codon table JSON file and convert to dict."""
        json_path = _RESOURCES_DIR / f"{key}.json"
        if not json_path.exists():
            available = self.list_organisms()
            raise ValueError(
                f"Unknown organism: '{key}'. "
                f"Available: {', '.join(available)}"
            )
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        self._metadata[key] = {
            "name": data.get("name", key),
            "taxid": data.get("taxid"),
            "source": data.get("source", ""),
        }
        table: dict[str, list[tuple[str, float]]] = {}
        for aa, codons in data["codons"].items():
            table[aa] = [(codon, freq) for codon, freq in codons]
        return table

    def get_codon_table(
        self, organism: str = "ecoli"
    ) -> dict[str, list[tuple[str, float]]]:
        """Return the codon usage table for the given organism.

        Args:
            organism: Organism name or alias (case-insensitive).

        Returns:
            Dict mapping amino acid to list of (codon, frequency) tuples.

        Raises:
            ValueError: If the organism is not found.
        """
        key = self._resolve_key(organism)
        if key not in self._cache:
            self._cache[key] = self._load(key)
        return self._cache[key]

    def list_organisms(self) -> list[str]:
        """Return canonical organism keys (JSON filenames without extension)."""
        keys: list[str] = []
        if _RESOURCES_DIR.exists():
            for p in sorted(_RESOURCES_DIR.glob("*.json")):
                keys.append(p.stem)
        return keys

    def list_organisms_detailed(self) -> list[dict]:
        """Return organism info with display names for UI dropdowns."""
        result: list[dict] = []
        for key in self.list_organisms():
            # Ensure metadata is loaded
            if key not in self._metadata:
                self.get_codon_table(key)
            meta = self._metadata.get(key, {})
            result.append({
                "key": key,
                "name": meta.get("name", key),
                "taxid": meta.get("taxid"),
            })
        return result


# Module-level singleton
_registry = CodonTableRegistry()

# Module-level constant for E. coli K-12 codon usage (exported and used in tests)
ECOLI_CODON_USAGE: dict[str, list[tuple[str, float]]] = _registry.get_codon_table("ecoli")

# Standard genetic code: codon -> amino acid
# Built from E. coli table (genetic code is universal; frequencies vary by organism)
CODON_TO_AA: dict[str, str] = {}
for _aa, _codons in ECOLI_CODON_USAGE.items():
    for _codon, _ in _codons:
        CODON_TO_AA[_codon] = _aa


# Minimum synonymous usage fraction a codon must carry to enter the design pool
# (mt_codons_for_design).
#
# THIS IS AN OPERATING CHOICE, NOT A LITERATURE CONSTANT. No published threshold
# separates a usable codon from a rare one. 0.10 was picked from a measurement
# over this repository's fixture material (81 mutations x 2 polymerases x 2
# overlap modes x 5 organisms), as the lowest floor that removed every rare
# landing outright. Change it here and nowhere else; every consumer reads this
# name.
#
# What it buys: without a floor the widened pool is free to pick a codon the
# host barely uses, because the rest of the penalty scores Tm, GC and nucleotide
# changes and is blind to usage. A soft usage term biases but cannot forbid: the
# widened pool with USAGE_WEIGHT at 4.0 and no floor still put 34.8% of
# M. extorquens winners below 0.10, two of them on a codon that organism never
# uses at all. With the floor, winners below 0.10 go to zero on all five shipped
# organisms.
#
# What it costs: 7 designs of 1,620 that the unfiltered widened pool could
# satisfy are lost, every one of them a design whose only surviving primer used
# a sub-floor codon. Against what shipped before the pool widened the net is
# still +21 (22 rescued, 1 lost). It also buys back some primer quality: the
# floor forces a worse-scoring primer on 36 designs, up to 22 penalty units on
# the worst, which is B. subtilis Pro banned at 0.09, one point under the line.
# For M. extorquens, the most skewed of the five tables, the floor collapses 3
# of the 20 amino acids to a single usable codon (Cys->TGC, Phe->TTC, Ile->ATC)
# and drops the mean pool from 3.05 to 1.80 codons per amino acid; the other
# four organisms land at 2.80-2.90. That is the organism's codon bias showing
# through, not a defect.
CODON_USAGE_FLOOR = 0.10


def get_codon_table(
    organism: str = "ecoli",
) -> dict[str, list[tuple[str, float]]]:
    """Return the codon usage table for the given organism.

    Module-level convenience function wrapping CodonTableRegistry.
    """
    return _registry.get_codon_table(organism)


def resolve_organism_key(annotation: str | None) -> str | None:
    """Resolve a sequence annotation to a canonical supported organism key.

    Returns the canonical key (e.g. ``"ecoli"``) when *annotation* maps to a
    known alias, or ``None`` for blank or unsupported values.  Side-effect-free.

    Args:
        annotation: Raw organism annotation string (e.g. ``"Escherichia coli"``).

    Returns:
        Canonical organism key or ``None``.
    """
    if not annotation or not annotation.strip():
        return None
    key = annotation.strip().lower()
    return _ORGANISM_ALIASES.get(key)


def best_codon(aa: str, organism: str = "ecoli") -> str:
    """Return the most frequently used codon for an amino acid.

    Args:
        aa: Single-letter amino acid code (uppercase).
        organism: Organism name or alias (default: "ecoli").

    Returns:
        Most frequent codon (uppercase DNA).

    Raises:
        ValueError: If amino acid code is invalid.
    """
    aa = aa.upper()
    table = _registry.get_codon_table(organism)
    if aa not in table:
        raise ValueError(f"Invalid amino acid: {aa}")
    codons = table[aa]
    return max(codons, key=lambda x: x[1])[0]


def closest_codon(wt_codon: str, target_aa: str, organism: str = "ecoli") -> str:
    """Return the codon for target_aa with minimum hamming distance to wt_codon.

    Among codons with the same minimum distance, prefer higher usage frequency
    for the specified organism. If closest == optimal, returns the optimal codon.
    """
    wt_codon = wt_codon.upper()
    target_aa = target_aa.upper()
    table = _registry.get_codon_table(organism)
    if target_aa not in table:
        raise ValueError(f"Invalid amino acid: {target_aa}")

    def hamming(a: str, b: str) -> int:
        return sum(c1 != c2 for c1, c2 in zip(a, b))

    codons = table[target_aa]
    # Sort by: hamming distance (asc), then frequency (desc)
    ranked = sorted(codons, key=lambda x: (hamming(wt_codon, x[0]), -x[1]))
    return ranked[0][0]


def codon_usage_fraction(codon: str, organism: str = "ecoli") -> float:
    """Return the synonymous usage fraction *codon* carries in *organism*.

    The design penalty scores a codon by how rarely the host uses it, so the
    number is fetched once per candidate codon and carried to the scoring site
    rather than looked up there.

    Args:
        codon: 3-letter DNA codon (case-insensitive).
        organism: Organism name or alias (default: "ecoli").

    Returns:
        Fraction of that amino acid's codons, 0.0-1.0.

    Raises:
        ValueError: If the codon is not in the genetic code.
    """
    codon = codon.upper()
    aa = CODON_TO_AA.get(codon)
    if aa is None:
        raise ValueError(f"Invalid codon: {codon}")
    for c, freq in _registry.get_codon_table(organism)[aa]:
        if c == codon:
            return freq
    return 0.0


def mt_codons_for_design(
    wt_codon: str,
    target_aa: str,
    strategy: str = "closest",
    organism: str = "ecoli",
) -> list[str]:
    """Return every usable mutant codon for *target_aa*, best-ordered first.

    The pool is every synonymous codon for the target amino acid except the WT
    codon, minus the ones the host uses less often than CODON_USAGE_FLOOR.
    Ordering is fixed: hamming distance from the WT codon ascending, then usage
    fraction descending, then the codon itself ascending, which makes the list
    deterministic across runs and across organisms with equal fractions.

    The WT codon is dropped because re-emitting it is not a mutation. That only
    applies to a silent request (mt_aa == wt_aa); for a missense request the WT
    codon encodes a different amino acid and is not in the pool anyway.

    ``strategy`` is accepted and ignored. It used to order a two-element
    [closest, optimal] list, and there is no longer a two-element list to
    order: the caller now hands the whole pool to design_single_sdm, which
    ranks every survivor of the tolerance sweep by penalty, and usage enters
    that penalty directly (sdm_engine.USAGE_WEIGHT). Pool order only breaks
    exact penalty ties. The parameter stays because removing it would break
    design_single_sdm, diagnose_sdm_failure, the sidecar request model, the
    TypeScript design input and a persisted workspace field, none of which
    belong in a change to the codon pool.

    Args:
        wt_codon: The wild-type codon being replaced.
        target_aa: Single-letter code of the amino acid to encode.
        strategy: Accepted and ignored; see above.
        organism: Organism for codon frequency lookup.

    Returns:
        Non-empty list of distinct uppercase codons.

    Raises:
        ValueError: If the amino acid code is invalid.
    """
    wt = wt_codon.upper()
    target_aa = target_aa.upper()
    table = _registry.get_codon_table(organism)
    if target_aa not in table:
        raise ValueError(f"Invalid amino acid: {target_aa}")

    def ordered(pairs: list[tuple[str, float]]) -> list[str]:
        return [
            codon
            for codon, _ in sorted(
                pairs,
                key=lambda cf: (
                    sum(a != b for a, b in zip(wt, cf[0])),
                    -cf[1],
                    cf[0],
                ),
            )
        ]

    non_wt = [(c, f) for c, f in table[target_aa] if c != wt]
    above_floor = [(c, f) for c, f in non_wt if f >= CODON_USAGE_FLOOR]
    if above_floor:
        return ordered(above_floor)
    if non_wt:
        # A missense request cannot reach here: the fractions of one amino acid
        # sum to 1 over at most six codons, so its most-used codon is at least
        # 0.167 and clears the floor. Only a silent request can, by removing
        # that codon as the WT one. Returning the sub-floor remainder beats
        # refusing to design, and it is the one path on which a winner may sit
        # below the floor.
        return ordered(non_wt)
    # Met and Trp have a single codon, so a silent request for either leaves
    # nothing once the WT codon is dropped. Emitting it keeps the historical
    # behaviour (a zero-change "mutant" codon) rather than failing the design.
    return [wt]


def codon_to_aa(codon: str) -> str:
    """Translate a DNA codon to its amino acid.

    Args:
        codon: 3-letter DNA codon (uppercase).

    Returns:
        Single-letter amino acid code.

    Raises:
        ValueError: If codon is invalid.
    """
    codon = codon.upper()
    if codon not in CODON_TO_AA:
        raise ValueError(f"Invalid codon: {codon}")
    return CODON_TO_AA[codon]
