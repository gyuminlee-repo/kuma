"""Multi-organism codon usage tables (Kazusa DB).

Supports E. coli K-12, B. subtilis 168, S. cerevisiae, H. sapiens,
and M. extorquens AM1. Frequencies are fraction of synonymous codons
for each amino acid.
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
}


class CodonTableRegistry:
    """Registry for organism-specific codon usage tables.

    Loads JSON files from kuro/resources/codon_tables/ on demand and
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

# Backward-compatible constant: E. coli K-12 codon usage
ECOLI_CODON_USAGE: dict[str, list[tuple[str, float]]] = _registry.get_codon_table("ecoli")

# Standard genetic code: codon -> amino acid
# Built from E. coli table (genetic code is universal; frequencies vary by organism)
CODON_TO_AA: dict[str, str] = {}
for _aa, _codons in ECOLI_CODON_USAGE.items():
    for _codon, _ in _codons:
        CODON_TO_AA[_codon] = _aa


def get_codon_table(
    organism: str = "ecoli",
) -> dict[str, list[tuple[str, float]]]:
    """Return the codon usage table for the given organism.

    Module-level convenience function wrapping CodonTableRegistry.
    """
    return _registry.get_codon_table(organism)


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


def mt_codons_for_design(
    wt_codon: str,
    target_aa: str,
    strategy: str = "closest",
    organism: str = "ecoli",
) -> list[str]:
    """Return distinct mutant codons ordered by strategy.

    Args:
        strategy: "closest" (min nucleotide changes first) or
                  "optimal" (highest organism usage first).
        organism: Organism for codon frequency lookup.
    """
    optimal = best_codon(target_aa, organism)
    closest = closest_codon(wt_codon, target_aa, organism)
    if optimal == closest:
        return [optimal]
    if strategy == "optimal":
        return [optimal, closest]
    return [closest, optimal]


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
