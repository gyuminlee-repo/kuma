"""Multi-organism codon usage tables.

Tables are read from two directories, in this order: the bundled
``resources/codon_tables/*.json`` and the user directory returned by
``user_codon_dir()``. ``list_organisms`` globs both, so the available set is
whatever they hold rather than whatever this docstring says, and every file is
put through ``codon_import`` before it is offered. The bundled directory wins a
stem collision (R5) and a user file that fails validation is skipped rather than
emptying the list (R1); ``CodonTableRegistry.scan()`` reports both in
``failed``. A lookup does not glob; ``CodonTableRegistry._load`` opens
``<key>.json`` in the first directory that has it, so a table is reachable by
its exact file stem or by an alias, either from the hardcoded
``_ORGANISM_ALIASES`` or declared by a user table. The codon-to-amino-acid mapping is
not read from these files at all: ``CODON_TO_AA`` is NCBI genetic code 11 taken
from ``Bio.Data.CodonTable``. Today the shipped set is E. coli K-12,
B. subtilis 168, S. cerevisiae, H. sapiens and M. extorquens AM1. Provenance
differs per table and each one names its own in a ``source`` field (Kazusa
Codon Usage Database or NCBI RefSeq).

Frequencies are fraction of synonymous codons for each amino acid.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from Bio.Data import CodonTable as _BioCodonTable

from kuma_core.shared.config_paths import kuma_home
from kuma_core.shared.resource_path import resource_path as _resource_path
from kuma_core.kuro.codon_import import (
    ValidationContext,
    validate_codon_table_file,
)

_RESOURCES_DIR = _resource_path(
    "kuma_core.kuro", "resources/codon_tables", module_file=__file__
)

# V7 of the codon-table import spec: a table key is a lowercase identifier of 2
# to 32 characters starting with a letter. Applied at lookup time as well as at
# import time so that an organism string that matches no alias can never reach
# path construction in ``_load``.
_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")

# Table fields that say where the numbers came from. They are copied verbatim
# into the portable document (``_document_from_report``) and none of them is an
# input to ``canonical_digest``.
_TRACEABILITY_FIELDS = (
    "schema_version",
    "provenance",
    "counts",
    "n_cds",
    "assembly",
    "strain",
    "source_release",
)

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


def user_codon_dir() -> Path:
    """Directory holding user-installed codon tables.

    Resolved on every call rather than at import. ``kuma_home()`` reads ``HOME``
    and the sidecar RPC suite imports ``sidecar_kuro.core`` at collection time,
    so a directory frozen at import would be the developer's real home no matter
    what a fixture sets afterwards.
    """
    return kuma_home() / "kuro" / "codon_tables"


def _search_dirs() -> list[tuple[Path, bool]]:
    """Return ``(directory, is_builtin)`` in lookup order.

    The bundled directory comes first, which is rule R5: a user file whose stem
    collides with a shipped table never wins. ``_RESOURCES_DIR`` is read from
    the module global on each call so tests can redirect it.
    """
    return [(_RESOURCES_DIR, True), (user_codon_dir(), False)]


def _document_from_report(key: str, report, raw: dict | None = None) -> dict:
    """Rebuild the table as a self-contained JSON document.

    The workspace carries this block so a project opened on another machine
    still knows what codons produced its primers (design note section 8.2), and
    the install path writes it back into the user directory verbatim. It is
    therefore built from what the validator *normalised*, not from the bytes on
    disk: writing this document to ``<key>.json`` and validating it again has
    to return the same ``table_sha256``, which raw bytes carrying a rounding
    error or a "U" codon would not.

    The traceability fields (``provenance``, ``counts`` and the assembly
    labels) ride along unchanged. They do not enter ``canonical_digest``, which
    is the point: two documents that differ only in ``provenance.generated_at``
    still carry one ``table_sha256``, so the restore branches compare codons
    and not paperwork.
    """
    meta = report.metadata or {}
    raw = raw or {}
    document = {
        "key": key,
        "name": meta.get("name", key),
        "taxid": meta.get("taxid"),
        "source": meta.get("source", ""),
        "genetic_code": report.genetic_code,
        "aliases": list(report.aliases),
        "codons": {
            aa: [[codon, freq] for codon, freq in pairs]
            for aa, pairs in (report.table or {}).items()
        },
    }
    for field_name in _TRACEABILITY_FIELDS:
        if field_name in raw:
            document[field_name] = raw[field_name]
    return document


class CodonTableRegistry:
    """Registry for organism-specific codon usage tables.

    Loads JSON files on demand from the bundled resource directory and from the
    user directory, validates them through ``codon_import`` and caches them in
    memory. Follows the same pattern as PolymeraseRegistry.
    """

    def __init__(self) -> None:
        self._cache: dict[str, dict[str, list[tuple[str, float]]]] = {}
        self._metadata: dict[str, dict] = {}
        self._scan: dict | None = None
        self._alias_index: dict[str, str] | None = None

    # -- scanning ---------------------------------------------------------

    def refresh(self) -> None:
        """Drop every cached table, scan result and alias.

        The only invalidation point. ``handle_list_organisms`` calls it, which
        makes listing the organisms the refresh action for Phase 1 since no
        separate refresh RPC exists.
        """
        self._cache.clear()
        self._metadata.clear()
        self._scan = None
        self._alias_index = None

    def scan(self) -> dict:
        """Return ``{"organisms": [...], "failed": [...], "user_dir": str}``.

        Every file found in either search directory goes through the full
        validator. A user file that fails is skipped and recorded in ``failed``
        (R1) instead of taking the rest of the dropdown with it (D2); a user
        file shadowed by a bundled stem is recorded there too (R5).

        User stems are visited in sorted order, so when two of them claim the
        same alias the earlier one keeps it and the later one is rejected.
        """
        if self._scan is not None:
            return self._scan

        organisms: list[dict] = []
        failed: list[dict] = []
        builtin_keys: dict[str, str] = {}
        user_tables: dict[str, dict] = {}
        user_aliases: dict[str, str] = {}
        alias_index: dict[str, str] = dict(_ORGANISM_ALIASES)

        for directory, is_builtin in _search_dirs():
            if not directory.exists():
                continue
            stems = sorted(p.stem for p in directory.glob("*.json"))
            for path in sorted(directory.glob("*.json")):
                if not is_builtin and path.stem in builtin_keys:
                    failed.append({
                        "filename": path.name,
                        "code": "R5",
                        "reason": (
                            f"{path.name} is shadowed by the built-in table "
                            f"'{path.stem}' and was not loaded. Rename it to "
                            f"{path.stem}_lab.json to use it."
                        ),
                        "findings": [
                            {
                                "code": "R5",
                                "params": {
                                    "filename": path.name,
                                    "stem": path.stem,
                                },
                            }
                        ],
                    })
                    continue
                ctx = ValidationContext(
                    is_builtin=is_builtin,
                    builtin_keys=builtin_keys,
                    builtin_aliases=dict(_ORGANISM_ALIASES),
                    existing_user_tables=user_tables,
                    existing_user_aliases=user_aliases,
                    sibling_stems=tuple(stems),
                )
                report = validate_codon_table_file(path, ctx)
                if not report.ok:
                    failed.append({
                        "filename": path.name,
                        "code": report.errors[0].code,
                        "reason": "; ".join(f.detail for f in report.errors),
                        # Every error, not just the first: ``reason`` already
                        # joins them all in English, so localizing from
                        # ``code`` alone would drop the rest of the sentence.
                        "findings": [
                            {"code": f.code, "params": f.params}
                            for f in report.errors
                        ],
                    })
                    continue
                key = report.key or path.stem
                meta = report.metadata or {}
                raw = _read_json(path)
                entry = {
                    "key": key,
                    "name": meta.get("name", key),
                    "taxid": meta.get("taxid"),
                    "source": "builtin" if is_builtin else "user",
                    "aliases": list(report.aliases),
                    "cds_count": _cds_count(raw),
                    "table_sha256": report.table_sha256,
                    "warnings": [
                        {"code": f.code, "params": f.params}
                        for f in report.warnings
                    ],
                    # N1/N2/N4 were previously produced and then dropped here,
                    # which left their ten locales unreachable from any
                    # production path. They say what the import silently
                    # changed (U->T, lowercase codons, counts adopted), which
                    # is exactly what an operator needs to see once.
                    "normalizations": [
                        {"code": f.code, "params": f.params}
                        for f in report.normalizations
                    ],
                    "document": _document_from_report(key, report, raw),
                }
                organisms.append(entry)
                if is_builtin:
                    builtin_keys[key] = entry["name"]
                else:
                    user_tables[key] = {"name": entry["name"]}
                    for alias in report.aliases:
                        user_aliases.setdefault(alias, key)
                for alias in report.aliases:
                    alias_index.setdefault(alias, key)
                alias_index.setdefault(key, key)

        self._alias_index = alias_index
        self._scan = {
            "organisms": organisms,
            "failed": failed,
            "user_dir": str(user_codon_dir()),
        }
        return self._scan

    def alias_index(self) -> dict[str, str]:
        """Alias -> key, built-in aliases plus the aliases of loaded tables."""
        if self._alias_index is None:
            self.scan()
        return self._alias_index or {}

    # -- lookup -----------------------------------------------------------

    def _resolve_key(self, organism: str) -> str:
        """Resolve an organism name to its canonical JSON key.

        Raises:
            ValueError: If *organism* matches no alias and is not itself a
                usable table key (V7). Rejecting here keeps anything that is
                not a plain lowercase identifier out of the filename ``_load``
                builds.
        """
        key = organism.strip().lower()
        resolved = _ORGANISM_ALIASES.get(key, key)
        if not _KEY_RE.match(resolved):
            raise ValueError(
                f"Unknown organism: '{organism}'. Use lowercase letters, "
                f"digits and underscore, 2 to 32 characters, starting with a "
                f"letter."
            )
        return resolved

    def _find(self, key: str) -> tuple[Path, bool] | None:
        for directory, is_builtin in _search_dirs():
            candidate = directory / f"{key}.json"
            if candidate.exists():
                return candidate, is_builtin
        return None

    def _load(self, key: str) -> dict[str, list[tuple[str, float]]]:
        """Load and validate one codon table, bundled or user-installed."""
        found = self._find(key)
        if found is None:
            available = self.list_organisms()
            raise ValueError(
                f"Unknown organism: '{key}'. "
                f"Available: {', '.join(available)}"
            )
        json_path, is_builtin = found
        report = validate_codon_table_file(
            json_path,
            ValidationContext(is_builtin=is_builtin),
        )
        if not report.ok:
            reasons = "; ".join(f.detail for f in report.errors)
            raise ValueError(
                f"The codon table '{key}' is installed but could not be "
                f"loaded: {reasons}"
            )
        self._metadata[key] = dict(report.metadata or {})
        self._metadata[key]["table_sha256"] = report.table_sha256
        return report.table or {}

    def get_codon_table(
        self, organism: str = "ecoli"
    ) -> dict[str, list[tuple[str, float]]]:
        """Return the codon usage table for the given organism.

        A fresh dict of fresh lists is returned on every call. The cached
        object used to be handed out directly, which made any caller that
        edited it in place rewrite the table for the whole process.

        Args:
            organism: Organism name or alias (case-insensitive).

        Returns:
            Dict mapping amino acid to list of (codon, frequency) tuples.

        Raises:
            ValueError: If the organism is not found or the file fails
                validation.
        """
        key = self._resolve_key(organism)
        if key not in self._cache:
            self._cache[key] = self._load(key)
        return {aa: list(pairs) for aa, pairs in self._cache[key].items()}

    def describe(self, organism: str) -> dict:
        """Return what identifies the table *organism* resolves to.

        Loading is forced rather than assumed: ``_metadata`` is only populated
        by ``_load``, and the design handler asks for this right after it has
        already validated the organism, so a cached hit costs nothing and a
        cold one is the same read the design is about to do anyway.

        Returns:
            ``{"key", "name", "source", "path", "table_sha256"}``. ``source``
            is ``"builtin"`` or ``"user"``; ``path`` is the file that was read.

        Raises:
            ValueError: If *organism* resolves to no installed table.
        """
        key = self._resolve_key(organism)
        if key not in self._cache:
            self._cache[key] = self._load(key)
        found = self._find(key)
        if found is None:  # pragma: no cover - _load would have raised first
            raise ValueError(f"Unknown organism: '{organism}'.")
        path, is_builtin = found
        meta = self._metadata.get(key, {})
        return {
            "key": key,
            "name": meta.get("name", key),
            "source": "builtin" if is_builtin else "user",
            "path": str(path),
            "table_sha256": meta.get("table_sha256"),
        }

    def list_organisms(self) -> list[str]:
        """Return the canonical keys of every table that validated."""
        return [entry["key"] for entry in self.scan()["organisms"]]

    def list_organisms_detailed(self) -> list[dict]:
        """Return organism info with display names for UI dropdowns."""
        return self.scan()["organisms"]


def _read_json(path: Path) -> dict:
    """Parse *path* as a JSON object, or return ``{}``.

    The file has already been validated by the time this runs, so a failure
    here means it changed underneath us. Both callers degrade to "unknown"
    rather than failing the whole scan over it.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _cds_count(data: dict) -> int | None:
    """Best-effort coding-sequence count for a table, or None."""
    provenance = data.get("provenance")
    if isinstance(provenance, dict):
        value = provenance.get("cds_counted")
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    value = data.get("n_cds")
    return value if isinstance(value, int) and not isinstance(value, bool) else None


# Module-level singleton
_registry = CodonTableRegistry()


def get_registry() -> CodonTableRegistry:
    """Return the process-wide registry.

    One instance, deliberately. The sidecar used to build its own, so the
    dropdown and the design gate answered from one registry while the codon
    lookups inside the design engine answered from another (D1).
    """
    return _registry


# Module-level constant for E. coli K-12 codon usage (exported and used in tests)
ECOLI_CODON_USAGE: dict[str, list[tuple[str, float]]] = _registry.get_codon_table("ecoli")

# Standard genetic code: codon -> amino acid.
#
# NCBI genetic code 11 (bacterial/plant plastid), read from Biopython rather
# than derived from ecoli.json. The derived form made a data edit to one
# frequency table silently redefine the genetic code for the whole app, which
# is not a property any frequency table should carry.
#
# ``forward_table`` holds 61 sense codons and no stop entries; the three stop
# codons live in a separate ``stop_codons`` list. They are merged back in as
# "*" because mutation.py and sdm_engine.py both look stop codons up here and
# a None would turn into a wild-type mismatch or an "X" translation.
#
# Code 11 and code 1 assign codons identically and differ only in start codons,
# so this constant is equally correct for either.
_STANDARD_CODE = _BioCodonTable.unambiguous_dna_by_id[11]
CODON_TO_AA: dict[str, str] = dict(_STANDARD_CODE.forward_table)
for _stop in _STANDARD_CODE.stop_codons:
    CODON_TO_AA[_stop] = "*"


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
    known alias, or ``None`` for blank or unsupported values.

    **No longer side-effect-free.** The alias map now includes the aliases
    declared by user-installed tables, so the first call scans the codon-table
    directories and the result is cached for the life of the process. Only
    ``CodonTableRegistry.refresh()`` invalidates it, which is what the Refresh
    action in the UI triggers. A table dropped into the folder after the first
    call is therefore not auto-detected until a refresh.

    Args:
        annotation: Raw organism annotation string (e.g. ``"Escherichia coli"``).

    Returns:
        Canonical organism key or ``None``.
    """
    if not annotation or not annotation.strip():
        return None
    key = annotation.strip().lower()
    return _registry.alias_index().get(key)


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
