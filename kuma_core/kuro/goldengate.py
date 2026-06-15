"""Golden Gate / Type IIS (BsaI etc.) site-directed mutagenesis primer design.

A generalized Golden Gate workflow (originally adapted from a reference mutation_tool),
offered in KURO as a second design method alongside overlap-extension SDM. Codon usage,
Tm, and the enzyme catalog are sourced from KURO's canonical infrastructure so any lab
can design with its own organism, vector junction, and enzyme.

Pipeline per single-AA substitution (e.g. ``G45A``):

1. Codon selection — enumerate target-AA codons by the selected organism's Kazusa
   preference (frequency descending, deterministic codon-string tiebreak) and pick the
   first that does NOT create a forbidden Type IIS site (BsaI/BsmBI/BbsI + reverse
   complement) inside the 5-codon (15 nt) window centred on the mutated codon.
2. Overhang selection — build the ``-1`` and ``+0`` candidate fusion sites of length
   ``overhang_len`` around the mutated codon, drop forbidden overhangs, then either
   pick the highest-fidelity candidate from the enzyme score table OR (when no table
   is bundled) fall back to a *functional unscored* overhang. Never emit a silent
   empty overhang; only zero surviving candidates yields ``no_valid_overhang``.
3. Primer assembly — ``left = prefix + rc(overhang) + rc(upstream)`` and
   ``right = prefix + overhang + downstream`` from the 21-codon context window.
4. Batch Tm normalisation — trim annealing regions from the 3' end so every Tm stays
   within ``min(initial Tm) + 4 C``, down to a 20 nt floor.

Design decisions (ralplan 2026-06-12-0645-bcdf, generalization revision):
- Tm uses ``sdm_engine.calc_sdm_tm`` (SantaLucia 1998, the SnapGene method), shared with
  the overlap-extension engine so both methods report a single consistent Tm.
- Codon preference comes from ``codon_table.get_codon_table(organism)`` (Kazusa). The
  selection order is frequency descending with a deterministic codon-string tiebreak,
  so it never depends on the JSON file's implicit ordering. ``CODON_TO_AA`` (universal
  genetic code) IS reused for translation.
"""

from __future__ import annotations

import csv
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from kuma_core.kuro.codon_table import CODON_TO_AA, get_codon_table
from kuma_core.kuro.overlap import reverse_complement
from kuma_core.kuro.sdm_engine import calc_sdm_tm

logger = logging.getLogger(__name__)

_RESOURCES = Path(__file__).parent / "resources"
_ENZYME_DB_PATH = _RESOURCES / "enzymes" / "typeIIS.json"
_FIDELITY_DIR = _RESOURCES / "overhang_fidelity"

MIN_ANNEALING_LENGTH = 20
GLOBAL_TM_WINDOW = 4.0  # batch ceiling = min(initial Tm) + this
TM_METHOD = "santalucia"

# Default forbidden internal sites: all bundled Type IIS recognition sites. Both the
# motif and its reverse complement are screened (rc handled in contains_forbidden_site).
DEFAULT_FORBIDDEN_SITES = ["GGTCTC", "CGTCTC", "GAAGAC"]
# Overhangs reserved for vector/destination junctions (default catalog convention).
DEFAULT_FORBIDDEN_OVERHANGS = ["AATG", "AGGT"]

_VALID_AA = set("ACDEFGHIKLMNPQRSTVWY*")

# Required fields for a Type IIS enzyme definition (built-in or custom).
_REQUIRED_ENZYME_FIELDS = ("name", "recognition", "cut_offset", "overhang_len", "prefix")


@dataclass
class Enzyme:
    """A Type IIS restriction enzyme definition from the bundled catalog."""

    name: str
    recognition: str
    cut_offset: tuple[int, int]
    overhang_len: int
    prefix: str
    fidelity_table: Optional[str] = None
    aliases: list[str] = field(default_factory=list)


@dataclass
class GoldenGateResult:
    """Golden Gate primer design result for a single mutation.

    Mirrors the GG-specific output contract. It deliberately does NOT carry an
    ``overlap_window`` (the overlap-extension ``SdmPrimerResult`` field); the sidecar
    maps this into the shared wire model via a dedicated serializer.
    """

    mutation: str
    status: str  # "success" | "no_valid_codon" | "no_valid_overhang"
    aa_position: int
    codon_pos: int
    source_aa: str
    target_aa: str
    wt_codon: str
    mt_codon: str = ""
    selected_codon_usage: Optional[float] = None
    enzyme: str = ""
    overhang: str = ""
    overhang_position: str = ""  # "-1" | "0" | ""
    overhang_score: Optional[int] = None
    forward_seq: str = ""  # right primer (5'->3'), forward-direction PCR
    reverse_seq: str = ""  # left primer (5'->3'), reverse-direction PCR
    left_annealing: str = ""
    right_annealing: str = ""
    left_tm: Optional[float] = None
    right_tm: Optional[float] = None
    screening_window: str = ""
    context_window: str = ""
    context_truncated: bool = False
    tm_method: str = TM_METHOD
    design_method: str = "goldengate"
    warnings: list[str] = field(default_factory=list)
    evaluated_codons: list[dict] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Resource loading
# --------------------------------------------------------------------------- #


def _enzyme_from_dict(e: dict) -> Enzyme:
    """Build and validate an ``Enzyme`` from a raw dict (built-in or custom).

    Raises ``ValueError``/``TypeError`` on missing or malformed fields so a single
    bad custom entry can be isolated by the caller rather than poisoning the catalog.
    """
    if not isinstance(e, dict):
        raise TypeError("Enzyme definition must be an object")
    for fld in _REQUIRED_ENZYME_FIELDS:
        if fld not in e:
            raise ValueError(f"Missing required enzyme field: {fld!r}")
    name = e["name"]
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Enzyme 'name' must be a non-empty string")
    recognition = e["recognition"]
    if not isinstance(recognition, str) or not recognition or any(c not in "ACGT" for c in recognition.upper()):
        raise ValueError("Enzyme 'recognition' must be a non-empty A/C/G/T string")
    cut_offset = e["cut_offset"]
    if not isinstance(cut_offset, (list, tuple)) or len(cut_offset) != 2:
        raise ValueError("Enzyme 'cut_offset' must be a 2-element list")
    overhang_len = e["overhang_len"]
    if isinstance(overhang_len, bool) or not isinstance(overhang_len, int) or overhang_len <= 0:
        raise ValueError("Enzyme 'overhang_len' must be a positive integer")
    prefix = e["prefix"]
    if not isinstance(prefix, str) or not prefix:
        raise ValueError("Enzyme 'prefix' must be a non-empty string")
    return Enzyme(
        name=name.strip(),
        recognition=recognition.upper(),
        cut_offset=(int(cut_offset[0]), int(cut_offset[1])),
        overhang_len=int(overhang_len),
        prefix=prefix.upper(),
        fidelity_table=e.get("fidelity_table"),
        aliases=list(e.get("aliases", [])),
    )


def _load_custom_enzymes(path: Path) -> dict[str, Enzyme]:
    """Load user-defined enzymes with per-file and per-entry fault isolation.

    A corrupt file or an individual invalid entry is logged and skipped; the rest
    (and the built-in catalog) survive. ``load_enzyme_db`` is a hot path for both
    design and listing, so one bad entry must never take down the whole catalog.
    """
    custom: dict[str, Enzyme] = {}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        logger.warning("Ignoring corrupt custom enzyme file %s: %s", path, exc)
        return custom
    if not isinstance(data, list):
        logger.warning("Custom enzyme file %s is not a JSON array; ignoring", path)
        return custom
    for entry in data:
        try:
            enz = _enzyme_from_dict(entry)
        except (ValueError, TypeError, KeyError) as exc:
            logger.warning("Skipping invalid custom enzyme entry in %s: %s", path, exc)
            continue
        custom[enz.name] = enz
    return custom


def load_enzyme_db(
    path: Path | None = None,
    custom_path: Path | None = None,
) -> dict[str, Enzyme]:
    """Load the Type IIS enzyme catalog keyed by name.

    Built-in enzymes load from the bundled JSON. When ``custom_path`` points at an
    existing file, user-defined enzymes are merged in (same name overrides built-in).
    A corrupt custom file or an invalid entry is skipped (logged), never raised.
    """
    raw = json.loads((path or _ENZYME_DB_PATH).read_text(encoding="utf-8"))
    out: dict[str, Enzyme] = {}
    for e in raw:
        out[e["name"]] = _enzyme_from_dict(e)
    if custom_path is not None and Path(custom_path).is_file():
        out.update(_load_custom_enzymes(custom_path))
    return out


def save_custom_enzyme(enzyme: dict, path: Path) -> Enzyme:
    """Validate and persist a custom Type IIS enzyme (append or update by name).

    Mirrors the custom-polymerase persistence pattern but validates the definition
    before writing so a malformed enzyme never reaches the catalog file.
    """
    enz = _enzyme_from_dict(enzyme)
    existing: list[dict] = []
    if Path(path).exists():
        try:
            loaded = json.loads(Path(path).read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                existing = loaded
        except (json.JSONDecodeError, OSError):
            existing = []
    record = {
        "name": enz.name,
        "aliases": list(enz.aliases),
        "recognition": enz.recognition,
        "cut_offset": list(enz.cut_offset),
        "overhang_len": enz.overhang_len,
        "prefix": enz.prefix,
        "fidelity_table": enz.fidelity_table,
    }
    updated = False
    for i, e in enumerate(existing):
        if isinstance(e, dict) and e.get("name") == enz.name:
            existing[i] = record
            updated = True
            break
    if not updated:
        existing.append(record)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
    return enz


def get_enzyme(name: str, db: dict[str, Enzyme] | None = None) -> Enzyme:
    db = db if db is not None else load_enzyme_db()
    if name not in db:
        raise ValueError(f"Unknown Type IIS enzyme: {name!r} (have {sorted(db)})")
    return db[name]


def load_overhang_scores(enzyme: Enzyme) -> dict[str, int]:
    """Load the on-target ligation-fidelity table for an enzyme.

    Returns an empty dict when no table is bundled (triggers functional unscored
    overhang selection in ``select_overhang``).
    """
    if not enzyme.fidelity_table:
        return {}
    path = _FIDELITY_DIR / enzyme.fidelity_table
    if not path.is_file():
        return {}
    scores: dict[str, int] = {}
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames or "overhang" not in reader.fieldnames or "Score" not in reader.fieldnames:
            raise ValueError(f"Fidelity table must have 'overhang' and 'Score' columns: {path}")
        for row in reader:
            scores[row["overhang"].strip().upper()] = int(row["Score"])
    return scores


# --------------------------------------------------------------------------- #
# Core helpers
# --------------------------------------------------------------------------- #


def _codon_priority(target_aa: str, organism: str) -> list[tuple[str, float]]:
    """Return target-AA codons in deterministic selection priority.

    Priority = usage frequency descending; ties broken by codon string ascending so
    selection never depends on the codon-table JSON's implicit ordering.
    """
    table = get_codon_table(organism)
    codons = table.get(target_aa)
    if not codons:
        raise ValueError(f"No codons for amino acid {target_aa!r} in organism {organism!r}.")
    return sorted(codons, key=lambda cf: (-cf[1], cf[0]))


def translate_dna(dna: str) -> str:
    """Translate a CDS to protein; unknown/partial codons map to 'X'."""
    return "".join(CODON_TO_AA.get(dna[i:i + 3], "X") for i in range(0, len(dna), 3))


def contains_forbidden_site(window: str, forbidden_sites: list[str]) -> tuple[bool, list[str]]:
    """Screen a window for forbidden motifs and their reverse complements."""
    hits: list[str] = []
    seen: set[str] = set()
    for site in forbidden_sites:
        rc_site = reverse_complement(site)
        if site in window and site not in seen:
            hits.append(site)
            seen.add(site)
        if rc_site != site and rc_site in window:
            tag = f"{site} (reverse-complement: {rc_site})"
            if tag not in seen:
                hits.append(tag)
                seen.add(tag)
    return bool(hits), hits


def _validate_prefix_geometry(prefix: str, enzyme: Enzyme) -> list[str]:
    """Warn when a junction prefix won't position the Type IIS cut at the overhang.

    A valid prefix contains the recognition site (or its reverse complement) followed
    by exactly ``cut_offset[0]`` spacer nt, so the enzyme cuts right where the overhang
    begins. Catalog prefixes satisfy this; an arbitrary override may not. Design still
    proceeds — the warning is surfaced to the user.
    """
    warnings: list[str] = []
    up = prefix.upper()
    rec = enzyme.recognition.upper()
    rc = reverse_complement(rec)
    idx = up.find(rec)
    site = rec
    if idx < 0:
        idx = up.find(rc)
        site = rc
    if idx < 0:
        warnings.append(
            f"Prefix does not contain the {enzyme.name} recognition site ({rec}); "
            "the primers may not be cut by the enzyme."
        )
        return warnings
    spacer = len(up) - (idx + len(site))
    if spacer != enzyme.cut_offset[0]:
        warnings.append(
            f"Prefix spacer after the recognition site is {spacer} nt but {enzyme.name} "
            f"cuts {enzyme.cut_offset[0]} nt downstream; the overhang may be misaligned."
        )
    return warnings


def select_overhang(
    mutated_dna: str,
    codon_start: int,
    overhang_scores: dict[str, int],
    forbidden_overhangs: list[str],
    overhang_len: int = 4,
) -> dict:
    """Pick the fusion-site overhang around the mutated codon.

    Generates the ``-1`` (one nt before the codon) and ``+0`` (codon start)
    candidates of width ``overhang_len``. Forbidden overhangs are dropped.

    Selection:
      - With a fidelity table: highest Score; ties prefer ``-1`` (catalog default).
      - Without a table (degrade): first surviving candidate, ties prefer ``-1``,
        ``overhang_score=None``. Never returns a silent empty overhang.
      - Zero surviving candidates: empty overhang, status handled by caller.
    """
    forbidden = set(forbidden_overhangs)
    candidates: list[dict] = []
    for label, start in (("-1", codon_start - 1), ("0", codon_start)):
        if start < 0 or start + overhang_len > len(mutated_dna):
            continue
        seq = mutated_dna[start:start + overhang_len]
        candidates.append({
            "label": label,
            "sequence": seq,
            "score": overhang_scores.get(seq),
            "start": start,
            "passes_forbidden": seq not in forbidden,
        })

    passing = [c for c in candidates if c["passes_forbidden"]]
    scorable = [c for c in passing if c["score"] is not None]

    if scorable:
        best = sorted(scorable, key=lambda c: (-c["score"], c["label"] != "-1"))[0]
    elif passing:
        # Functional unscored degrade: prefer the -1 candidate on ties.
        best = sorted(passing, key=lambda c: c["label"] != "-1")[0]
    else:
        return {
            "overhang": "",
            "overhang_position": "",
            "overhang_score": None,
            "overhang_start": -1,
            "candidates": candidates,
            "ok": False,
        }
    return {
        "overhang": best["sequence"],
        "overhang_position": best["label"],
        "overhang_score": best["score"],
        "overhang_start": best["start"],
        "candidates": candidates,
        "ok": True,
    }


def build_primers(
    context_window: str,
    context_start_nt: int,
    overhang: str,
    overhang_start_nt: int,
    prefix: str,
) -> dict:
    """Assemble left/right primers and pre-trim annealing regions."""
    rel_start = overhang_start_nt - context_start_nt
    rel_end = rel_start + len(overhang)
    if not overhang or rel_start < 0 or rel_end > len(context_window):
        return {
            "forward_seq": "", "reverse_seq": "",
            "left_annealing": "", "right_annealing": "",
            "left_tm": None, "right_tm": None,
        }
    upstream = context_window[:rel_start]
    downstream = context_window[rel_end:]
    left_annealing = reverse_complement(upstream)
    right_annealing = downstream
    return {
        "reverse_seq": prefix + reverse_complement(overhang) + left_annealing,
        "forward_seq": prefix + overhang + right_annealing,
        "left_annealing": left_annealing,
        "right_annealing": right_annealing,
        "left_tm": round(calc_sdm_tm(left_annealing), 2) if left_annealing else None,
        "right_tm": round(calc_sdm_tm(right_annealing), 2) if right_annealing else None,
    }


def _trim_annealing(sequence: str, tm_max: float) -> tuple[str, Optional[float]]:
    if not sequence:
        return "", None
    trimmed = sequence
    while len(trimmed) > MIN_ANNEALING_LENGTH and calc_sdm_tm(trimmed) > tm_max:
        trimmed = trimmed[:-1]
    return trimmed, round(calc_sdm_tm(trimmed), 2)


def apply_global_tm_trim(results: list[GoldenGateResult], prefix: str) -> list[GoldenGateResult]:
    """Trim every successful annealing region to a shared Tm ceiling.

    Ceiling = min(all initial left/right Tm) + GLOBAL_TM_WINDOW, floored at
    MIN_ANNEALING_LENGTH. Rebuilds the primers from the trimmed regions.
    """
    tms = [
        v
        for r in results if r.status == "success"
        for v in (r.left_tm, r.right_tm) if v is not None
    ]
    if not tms:
        return results
    ceiling = round(min(tms) + GLOBAL_TM_WINDOW, 2)
    for r in results:
        if r.status != "success":
            continue
        left_trim, left_tm = _trim_annealing(r.left_annealing, ceiling)
        right_trim, right_tm = _trim_annealing(r.right_annealing, ceiling)
        r.left_annealing, r.right_annealing = left_trim, right_trim
        r.left_tm, r.right_tm = left_tm, right_tm
        r.reverse_seq = prefix + reverse_complement(r.overhang) + left_trim
        r.forward_seq = prefix + r.overhang + right_trim
    return results


# --------------------------------------------------------------------------- #
# Per-mutation design
# --------------------------------------------------------------------------- #


def _parse_mutation(mutation: str) -> tuple[str, int, str]:
    m = re.fullmatch(r"([A-Z\*])(\d+)([A-Z\*])", mutation.upper())
    if not m:
        raise ValueError(f"Invalid mutation format: {mutation}")
    return m.group(1), int(m.group(2)), m.group(3)


def design_single_goldengate(
    dna: str,
    protein: str,
    mutation: str,
    enzyme: Enzyme,
    overhang_scores: dict[str, int],
    forbidden_sites: list[str],
    forbidden_overhangs: list[str],
    organism: str = "ecoli",
    prefix: str | None = None,
) -> GoldenGateResult:
    """Design Golden Gate primers for one mutation (pre global-Tm-trim)."""
    eff_prefix = prefix if prefix is not None else enzyme.prefix
    source_aa, pos1, target_aa = _parse_mutation(mutation)
    if pos1 < 1 or pos1 > len(protein):
        raise ValueError(f"Mutation position {pos1} outside protein length {len(protein)}")
    if protein[pos1 - 1] != source_aa:
        raise ValueError(
            f"Source AA mismatch at {pos1}: protein has {protein[pos1 - 1]}, mutation says {source_aa}"
        )
    if target_aa not in _VALID_AA:
        raise ValueError(f"Unsupported target amino acid: {target_aa}")

    codon_index = pos1 - 1
    codon_start = codon_index * 3
    wt_codon = dna[codon_start:codon_start + 3]
    n_codons = len(dna) // 3

    evaluated: list[dict] = []
    for candidate, usage in _codon_priority(target_aa, organism):
        mutated = f"{dna[:codon_start]}{candidate}{dna[codon_start + 3:]}"
        scan_start = max(0, codon_index - 2) * 3
        scan_end = min(n_codons, codon_index + 3) * 3
        window = mutated[scan_start:scan_end]
        bad, hits = contains_forbidden_site(window, forbidden_sites)
        evaluated.append({"codon": candidate, "usage": usage, "passes": not bad, "hits": hits, "window": window})
        if bad:
            continue

        ctx_start_codon = max(0, codon_index - 10)
        ctx_end_codon = min(n_codons, codon_index + 11)
        ctx_start_nt = ctx_start_codon * 3
        ctx_window = mutated[ctx_start_nt:ctx_end_codon * 3]
        truncated = ctx_start_codon != codon_index - 10 or ctx_end_codon != codon_index + 11

        ov = select_overhang(mutated, codon_start, overhang_scores, forbidden_overhangs, enzyme.overhang_len)
        result = GoldenGateResult(
            mutation=mutation.upper(), status="success", aa_position=pos1, codon_pos=codon_start,
            source_aa=source_aa, target_aa=target_aa, wt_codon=wt_codon, mt_codon=candidate,
            selected_codon_usage=usage, enzyme=enzyme.name,
            overhang=ov["overhang"], overhang_position=ov["overhang_position"],
            overhang_score=ov["overhang_score"], screening_window=window,
            context_window=ctx_window, context_truncated=truncated, evaluated_codons=evaluated,
        )
        if not ov["ok"]:
            result.status = "no_valid_overhang"
            result.warnings.append("No valid overhang candidate around the mutated codon.")
            return result
        primers = build_primers(ctx_window, ctx_start_nt, ov["overhang"], ov["overhang_start"], eff_prefix)
        result.forward_seq = primers["forward_seq"]
        result.reverse_seq = primers["reverse_seq"]
        result.left_annealing = primers["left_annealing"]
        result.right_annealing = primers["right_annealing"]
        result.left_tm = primers["left_tm"]
        result.right_tm = primers["right_tm"]
        if ov["overhang_score"] is None and overhang_scores:
            result.warnings.append("Selected overhang not present in fidelity table (unscored).")
        return result

    return GoldenGateResult(
        mutation=mutation.upper(), status="no_valid_codon", aa_position=pos1, codon_pos=codon_start,
        source_aa=source_aa, target_aa=target_aa, wt_codon=wt_codon, evaluated_codons=evaluated,
        warnings=["No target-AA codon avoids all forbidden Type IIS sites."],
    )


def design_goldengate(
    dna: str,
    protein: str,
    mutations: list[str],
    enzyme: str = "BsaI",
    forbidden_sites: list[str] | None = None,
    forbidden_overhangs: list[str] | None = None,
    enzyme_db: dict[str, Enzyme] | None = None,
    organism: str = "ecoli",
    prefix_override: str | None = None,
) -> list[GoldenGateResult]:
    """Design Golden Gate primers for a batch of independent mutations.

    Each mutation is evaluated against the original DNA; batch Tm trimming is applied
    across all successful results.
    """
    _validate_dna_protein(dna, protein)
    enz = get_enzyme(enzyme, enzyme_db)
    scores = load_overhang_scores(enz)
    sites = list(forbidden_sites) if forbidden_sites is not None else list(DEFAULT_FORBIDDEN_SITES)
    overhangs = list(forbidden_overhangs) if forbidden_overhangs is not None else list(DEFAULT_FORBIDDEN_OVERHANGS)
    eff_prefix = prefix_override if prefix_override is not None else enz.prefix
    prefix_warnings = _validate_prefix_geometry(eff_prefix, enz) if prefix_override is not None else []
    results = [
        design_single_goldengate(dna, protein, m, enz, scores, sites, overhangs, organism=organism, prefix=eff_prefix)
        for m in mutations
    ]
    for r in results:
        r.warnings.extend(prefix_warnings)
    return apply_global_tm_trim(results, eff_prefix)


def _validate_dna_protein(dna: str, protein: str) -> None:
    """Validate a CDS against its protein (reference validate_inputs semantics)."""
    if any(c not in "ACGT" for c in dna) or len(dna) % 3 != 0:
        raise ValueError("DNA must contain only A/C/G/T and have length divisible by 3.")
    translated = translate_dna(dna)
    if not (translated == protein or (translated.endswith("*") and translated[:-1] == protein)):
        raise ValueError("Translated DNA does not match the provided protein sequence.")


def extract_cds(template: str, start: int) -> str:
    """Extract a CDS from a full template at ``start`` (must be ATG) through the
    first in-frame stop codon (inclusive), or to the end of the template.

    Lets the Golden Gate engine (which works on a pure CDS) be driven from a KURO
    full-template + ``target_start`` input.
    """
    if template[start:start + 3] != "ATG":
        raise ValueError(f"Expected ATG at position {start}, found {template[start:start + 3]!r}.")
    codons: list[str] = []
    i = start
    while i + 3 <= len(template):
        codon = template[i:i + 3]
        codons.append(codon)
        if codon in ("TAA", "TAG", "TGA"):
            break
        i += 3
    return "".join(codons)


def design_goldengate_batch(
    dna: str,
    protein: str,
    mutations: list[str],
    enzyme: str = "BsaI",
    forbidden_sites: list[str] | None = None,
    forbidden_overhangs: list[str] | None = None,
    enzyme_db: dict[str, Enzyme] | None = None,
    organism: str = "ecoli",
    prefix_override: str | None = None,
) -> tuple[list[GoldenGateResult], dict[str, str]]:
    """Fault-tolerant batch design for the sidecar handler.

    Validates the DNA<->protein contract once, then designs each mutation
    independently. Per-mutation problems (bad notation, source mismatch, no valid
    codon/overhang) are collected into ``failed`` instead of aborting the batch.
    Returns ``(successful_results, failed_reasons)`` with batch Tm trimming applied.
    """
    _validate_dna_protein(dna, protein)
    enz = get_enzyme(enzyme, enzyme_db)
    scores = load_overhang_scores(enz)
    sites = list(forbidden_sites) if forbidden_sites is not None else list(DEFAULT_FORBIDDEN_SITES)
    overhangs = list(forbidden_overhangs) if forbidden_overhangs is not None else list(DEFAULT_FORBIDDEN_OVERHANGS)
    eff_prefix = prefix_override if prefix_override is not None else enz.prefix
    prefix_warnings = _validate_prefix_geometry(eff_prefix, enz) if prefix_override is not None else []

    results: list[GoldenGateResult] = []
    failed: dict[str, str] = {}
    for m in mutations:
        try:
            r = design_single_goldengate(
                dna, protein, m, enz, scores, sites, overhangs, organism=organism, prefix=eff_prefix
            )
        except ValueError as exc:
            failed[m] = str(exc)
            continue
        if r.status == "success":
            r.warnings.extend(prefix_warnings)
            results.append(r)
        else:
            failed[m] = r.warnings[0] if r.warnings else r.status
    apply_global_tm_trim(results, eff_prefix)
    return results, failed


def export_goldengate_tsv(
    results: list[GoldenGateResult],
    output_path: Path,
    enzyme: str = "BsaI",
) -> None:
    """Export Golden Gate results to TSV with method/Tm provenance header.

    The leading ``# design_method=`` / ``# enzyme=`` / ``# tm_method=`` comment lines
    make the policy self-documenting: both Golden Gate and overlap-extension report Tm
    via SantaLucia 1998 (the SnapGene method).
    """
    fieldnames = [
        "Mutation", "WT_Codon", "MT_Codon", "Enzyme",
        "Overhang", "Overhang_Position", "Overhang_Score",
        "Forward_Primer", "Reverse_Primer",
        "Left_Annealing", "Right_Annealing", "Left_Tm", "Right_Tm",
        "Status", "Warnings",
    ]
    with open(output_path, "w", newline="", encoding="utf-8") as fh:
        fh.write("# design_method=goldengate\n")
        fh.write(f"# enzyme={enzyme}\n")
        fh.write(f"# tm_method={TM_METHOD}\n")
        writer = csv.DictWriter(fh, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        for r in results:
            writer.writerow({
                "Mutation": r.mutation,
                "WT_Codon": r.wt_codon,
                "MT_Codon": r.mt_codon,
                "Enzyme": r.enzyme,
                "Overhang": r.overhang,
                "Overhang_Position": r.overhang_position,
                "Overhang_Score": "" if r.overhang_score is None else r.overhang_score,
                "Forward_Primer": r.forward_seq,
                "Reverse_Primer": r.reverse_seq,
                "Left_Annealing": r.left_annealing,
                "Right_Annealing": r.right_annealing,
                "Left_Tm": "" if r.left_tm is None else f"{r.left_tm:.2f}",
                "Right_Tm": "" if r.right_tm is None else f"{r.right_tm:.2f}",
                "Status": r.status,
                "Warnings": "; ".join(r.warnings) if r.warnings else "",
            })
