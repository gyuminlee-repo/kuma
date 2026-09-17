"""Normalisation and validation for codon usage tables.

Implements the rule set of the codon-table import design note (section 6):
errors V1-V30, warnings V31-V35 and normalisations N1-N4. Every rule number
appears in this module and in ``tests/test_codon_import.py`` so a finding can be
traced back to the clause that motivated it.

Three properties the caller can rely on.

**Everything runs, everything is reported.** A file is never rejected on the
first violation; the report carries every finding so a lab user fixes the file
once instead of N times.

**Rule gating is explicit.** Section 6 wants all rules run, yet a single
malformed codon must not surface as three unrelated errors. The dependency
order below is the whole of it and nothing else short-circuits:

- V1-V6 are fatal at file level; nothing after them runs.
- V7 failing means the key is unusable, so V8/V9/V10 do not run.
- V15 failing means the declared code is unsupported, so V16 does not run.
- A codon whose length is wrong reports V20 and is not also reported as V19.
- If any codon failed V19/V20 the codon-set checks V16 and V18 do not run,
  because a bad spelling would otherwise re-appear as "missing codon".
- V18 runs only when V17 passes: a missing amino acid takes its codons with it.
- Within one amino acid, a frequency failing V21 suppresses V22/V23/V24 for
  that amino acid, and V24 (all-zero) suppresses V22/V23 for it as well.
- V23 is only considered when V22 passed; V27 only when V25 and V26 passed.
- An alias reported under V29 is not also reported under V30.

**Nothing is written.** Validation is pure; the caller decides what to install.

The canonical digest ``table_sha256`` is the sha256 of
``json.dumps({"genetic_code": gc, "codons": codons}, sort_keys=True,
separators=(",", ":"))`` over the *normalised* table, with ``gc`` defaulting to
11. Provenance and timestamps are deliberately outside it so that re-annotating
a file does not change its scientific identity.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from Bio.Data import CodonTable as _BioCodonTable

__all__ = [
    "Finding",
    "ValidationContext",
    "ValidationReport",
    "MESSAGE_CODES",
    "SUPPORTED_SCHEMA_VERSION",
    "LOW_CDS_WARN_THRESHOLD",
    "LOW_CODON_COUNT_WARN_THRESHOLD",
    "canonical_digest",
    "validate_codon_table_data",
    "validate_codon_table_file",
]

# --- tunable constants -----------------------------------------------------

SUPPORTED_SCHEMA_VERSION = 1
MAX_FILE_BYTES = 1_000_000

# V31 low-sample warning thresholds.
#
# THESE ARE OPERATING CHOICES, NOT LITERATURE CONSTANTS. No published threshold
# separates a representative codon table from an unrepresentative one. The
# design note proposed 50 CDS / 10,000 codons from the observation that Kazusa
# entries are often built from a handful of coding sequences (its M. extorquens
# entry is 102 CDS, its E. coli K-12 entry 14), but the values themselves have
# no source. They are named here rather than inlined so a measured threshold can
# replace them in one place.
LOW_CDS_WARN_THRESHOLD = 50
LOW_CODON_COUNT_WARN_THRESHOLD = 10_000

# V22 reject band and V23 warn band for the per-amino-acid frequency sum.
# The reject band is read from the target, not invented here:
# tests/test_codon_table.py already asserts 0.95 <= total <= 1.05 over every
# shipped table. Narrowing it to +-0.02 would make this validator reject
# hsapiens.json, whose serine group sums to 0.97.
SUM_REJECT_BAND = (0.95, 1.05)
SUM_WARN_BAND = (0.96, 1.04)

# V27 tamper detection: how far a stored fraction may sit from the one its own
# count implies before the file is treated as hand-edited.
COUNT_FRACTION_TOLERANCE = 0.005

_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
_CODON_RE = re.compile(r"^[ACGT]{3}$")

_AMINO_ACIDS = frozenset("ACDEFGHIKLMNPQRSTVWY*")

# NCBI genetic codes kuma accepts (V15). Codes 1 and 11 assign codons
# identically and differ only in start codons; every other DNA table in
# Biopython assigns at least one codon differently, which would change how kuma
# reads wild-type codons rather than only which codon it prefers.
SUPPORTED_GENETIC_CODES = (1, 11)
DEFAULT_GENETIC_CODE = 11

# Top-level fields a table may carry. The five beyond the design note's list
# (assembly, strain, n_cds, transl_table, source_release) are shipped by
# bsubtilis.json and mextorquens.json today, so treating them as unknown would
# make V35 fire on kuma's own tables.
_KNOWN_TOP_LEVEL = frozenset({
    "schema_version", "key", "name", "taxid", "genetic_code", "aliases",
    "source", "provenance", "counts", "codons",
    "assembly", "strain", "n_cds", "transl_table", "source_release",
})

# Every message code this module can emit, in rule order. The frontend keeps a
# lookup object keyed by exactly these strings.
MESSAGE_CODES: tuple[str, ...] = tuple(
    [f"V{i}" for i in range(1, 36)] + [f"N{i}" for i in range(1, 5)]
)


def _code_table(gc: int) -> dict[str, str]:
    t = _BioCodonTable.unambiguous_dna_by_id[gc]
    mapping = dict(t.forward_table)
    for stop in t.stop_codons:
        mapping[stop] = "*"
    return mapping


# --- report types ----------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    """One rule outcome.

    ``params`` keys are exactly the ``{{placeholder}}`` names the design note's
    message table uses for this code, so the UI can interpolate without knowing
    anything about this module.
    """

    code: str
    params: dict[str, Any] = field(default_factory=dict)
    detail: str = ""


@dataclass
class ValidationContext:
    """Everything a rule needs that is not inside the file being checked."""

    is_builtin: bool = False
    # key -> display name of the tables that ship with kuma (V9).
    builtin_keys: dict[str, str] = field(default_factory=dict)
    # alias -> key of the hardcoded alias map (V30).
    builtin_aliases: dict[str, str] = field(default_factory=dict)
    # key -> {"name", "date", "sha8"} of already installed user tables
    # (V10, V29, V30).
    existing_user_tables: dict[str, dict] = field(default_factory=dict)
    # alias -> key contributed by already accepted user tables (V29, V30).
    existing_user_aliases: dict[str, str] = field(default_factory=dict)
    # File stems sitting next to this one, used for the case-collision rule V11.
    sibling_stems: tuple[str, ...] = ()
    overwrite: bool = False


@dataclass
class ValidationReport:
    """Outcome of one validation pass.

    ``checks_performed`` and ``codons_examined`` exist so a caller can tell a
    clean file apart from a validator that examined nothing.
    """

    stem: str
    key: str | None = None
    errors: list[Finding] = field(default_factory=list)
    warnings: list[Finding] = field(default_factory=list)
    normalizations: list[Finding] = field(default_factory=list)
    checks_performed: int = 0
    codons_examined: int = 0
    table: dict[str, list[tuple[str, float]]] | None = None
    # Amino acids whose frequencies were already rejected (V21/V24). V34 skips
    # them: a group reported as unusable must not also be reported as "some
    # codon here is never chosen".
    _suppressed_aas: set = field(default_factory=set)
    metadata: dict[str, Any] | None = None
    aliases: tuple[str, ...] = ()
    genetic_code: int = DEFAULT_GENETIC_CODE
    table_sha256: str | None = None

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def error_codes(self) -> list[str]:
        return [f.code for f in self.errors]

    @property
    def warning_codes(self) -> list[str]:
        return [f.code for f in self.warnings]

    def _err(self, code: str, detail: str, **params: Any) -> None:
        self.errors.append(Finding(code, params, detail))

    def _warn(self, code: str, detail: str, **params: Any) -> None:
        self.warnings.append(Finding(code, params, detail))

    def _norm(self, code: str, detail: str, **params: Any) -> None:
        self.normalizations.append(Finding(code, params, detail))


def canonical_digest(
    codons: dict[str, list[tuple[str, float]]], genetic_code: int
) -> str:
    """Return the canonical sha256 of a normalised table. See module docstring."""
    payload = {
        "genetic_code": genetic_code,
        "codons": {
            aa: [[c, f] for c, f in pairs] for aa, pairs in codons.items()
        },
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# --- file level (V1-V6) ----------------------------------------------------


def validate_codon_table_file(
    path: Path | str, context: ValidationContext | None = None
) -> ValidationReport:
    """Validate the file at *path*, applying V1-V6 before the data rules."""
    path = Path(path)
    context = context or ValidationContext()
    report = ValidationReport(stem=path.stem)

    report.checks_performed += 1  # V1
    if path.suffix.lower() != ".json":
        report._err(
            "V1",
            f"A codon table must be a .json file. You selected {path.suffix}.",
            ext=path.suffix or "(none)",
        )
        return report

    report.checks_performed += 1  # V2
    try:
        size = path.stat().st_size
    except OSError as exc:
        report.checks_performed += 1  # V6
        report._err(
            "V6",
            f"Could not read the file ({exc}).",
            reason=str(exc),
        )
        return report
    if size > MAX_FILE_BYTES:
        report._err(
            "V2",
            f"This file is {size} bytes; a codon table is a few kilobytes.",
            size=f"{size} bytes",
        )
        return report

    report.checks_performed += 1  # V6
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        report._err(
            "V6",
            f"Could not read the file ({exc}). Save it with UTF-8 encoding "
            f"and check file permissions.",
            reason=str(exc),
        )
        return report

    report.checks_performed += 1  # V3
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        report._err(
            "V3",
            f"This file is not valid JSON (line {exc.lineno}, column "
            f"{exc.colno}): {exc.msg}.",
            line=exc.lineno,
            col=exc.colno,
            detail_msg=exc.msg,
        )
        return report

    return validate_codon_table_data(
        data, stem=path.stem, context=context, _report=report
    )


# --- data level (V4-V35, N1-N4) --------------------------------------------


def validate_codon_table_data(
    data: Any,
    stem: str,
    context: ValidationContext | None = None,
    _report: ValidationReport | None = None,
) -> ValidationReport:
    """Validate an already parsed table body."""
    context = context or ValidationContext()
    report = _report if _report is not None else ValidationReport(stem=stem)

    report.checks_performed += 1  # V4
    if not isinstance(data, dict):
        report._err(
            "V4",
            f"A codon table must be a JSON object, not a "
            f"{type(data).__name__}.",
            type=type(data).__name__,
        )
        return report

    report.checks_performed += 1  # V5
    schema_version = data.get("schema_version", 1)
    if not isinstance(schema_version, int) or isinstance(schema_version, bool) \
            or schema_version > SUPPORTED_SCHEMA_VERSION:
        report._err(
            "V5",
            f"This table needs a newer kuma (schema_version "
            f"{schema_version}; this build supports up to "
            f"{SUPPORTED_SCHEMA_VERSION}).",
            n=schema_version,
            max=SUPPORTED_SCHEMA_VERSION,
        )
        return report

    _check_identity(data, stem, context, report)
    genetic_code = _check_genetic_code(data, context, report)
    normalised = _check_codons(data, genetic_code, context, report)
    _check_counts(data, normalised, report)
    _check_aliases(data, stem, context, report)
    _check_traceability(data, normalised, context, report)

    if report.ok and normalised is not None:
        report.table = normalised
        report.genetic_code = genetic_code or DEFAULT_GENETIC_CODE
        report.table_sha256 = canonical_digest(normalised, report.genetic_code)
        report.metadata = {
            "name": data.get("name", stem),
            "taxid": data.get("taxid"),
            "source": data.get("source", ""),
        }
        aliases = data.get("aliases") or []
        report.aliases = tuple(
            str(a).strip().lower() for a in aliases if str(a).strip()
        )
    return report


def _check_identity(
    data: dict, stem: str, ctx: ValidationContext, report: ValidationReport
) -> None:
    key = data.get("key", stem)

    report.checks_performed += 1  # V7
    key_ok = isinstance(key, str) and bool(_KEY_RE.match(key))
    if not key_ok:
        report._err(
            "V7",
            f"Table key '{key}' is not usable. Use lowercase letters, digits "
            f"and underscore, 2 to 32 characters, starting with a letter.",
            key=key,
        )
    else:
        report.key = key
        report.checks_performed += 1  # V8
        if key != stem:
            report._err(
                "V8",
                f"The file is named {stem}.json but declares key '{key}'.",
                stem=stem,
                key=key,
            )
        if not ctx.is_builtin:
            report.checks_performed += 1  # V9
            if key in ctx.builtin_keys:
                report._err(
                    "V9",
                    f"'{key}' is a built-in table ({ctx.builtin_keys[key]}) "
                    f"and cannot be replaced.",
                    key=key,
                    name=ctx.builtin_keys[key],
                )
            else:
                report.checks_performed += 1  # V10
                existing = ctx.existing_user_tables.get(key)
                if existing is not None and not ctx.overwrite:
                    report._err(
                        "V10",
                        f"'{key}' already exists ({existing.get('name', key)}).",
                        key=key,
                        name=existing.get("name", key),
                        date=existing.get("date", ""),
                        sha8=existing.get("sha8", ""),
                    )

    report.checks_performed += 1  # V11
    clashes = [
        s for s in ctx.sibling_stems
        if s != stem and s.lower() == stem.lower()
    ]
    if clashes:
        kept = sorted([stem, *clashes])[0]
        report._err(
            "V11",
            f"{stem}.json and {clashes[0]}.json produce the same key on "
            f"case-insensitive file systems. Only {kept} was loaded.",
            kept=kept,
        )

    report.checks_performed += 1  # V12
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        report._err(
            "V12",
            "This table has no display name.",
        )

    report.checks_performed += 1  # V13
    taxid = data.get("taxid")
    if taxid is not None and (
        not isinstance(taxid, int) or isinstance(taxid, bool) or taxid <= 0
    ):
        report._err(
            "V13",
            f"taxid must be an NCBI taxonomy id or left empty, not {taxid!r}.",
            value=taxid,
        )


def _check_genetic_code(
    data: dict, ctx: ValidationContext, report: ValidationReport
) -> int | None:
    # transl_table is the spelling kuma's own RefSeq-derived tables use.
    declared = data.get("genetic_code", data.get("transl_table"))

    report.checks_performed += 1  # V14
    if declared is None:
        # Bundled tables are exempt: they carry standard assignments and V16
        # confirms it, so a warning here would fire on kuma's own files.
        if not ctx.is_builtin:
            report._warn(
                "V14",
                f"No genetic code was declared. Assuming NCBI table "
                f"{DEFAULT_GENETIC_CODE} (bacterial).",
                n=DEFAULT_GENETIC_CODE,
            )
        return DEFAULT_GENETIC_CODE

    report.checks_performed += 1  # V15
    if not isinstance(declared, int) or isinstance(declared, bool) \
            or declared not in SUPPORTED_GENETIC_CODES:
        report._err(
            "V15",
            f"kuma supports NCBI genetic code 1 and 11 only. This table "
            f"declares {declared}. A non-standard code changes how kuma reads "
            f"wild-type codons, not just codon preference, so it cannot be "
            f"imported as a frequency table alone.",
            n=declared,
        )
        return None
    return declared


def _check_codons(
    data: dict,
    genetic_code: int | None,
    ctx: ValidationContext,
    report: ValidationReport,
) -> dict[str, list[tuple[str, float]]] | None:
    codons = data.get("codons")
    report.checks_performed += 1  # V17 (AA key set)
    if not isinstance(codons, dict):
        report._err(
            "V17",
            "Expected 21 amino acid entries including the stop '*'.",
            missing=sorted(_AMINO_ACIDS),
            extra=[],
        )
        return None

    present = set(codons)
    missing = sorted(_AMINO_ACIDS - present)
    extra = sorted(present - _AMINO_ACIDS)
    aa_set_ok = not missing and not extra
    if not aa_set_ok:
        report._err(
            "V17",
            f"Expected 21 amino acid entries including the stop '*'. "
            f"Missing: {missing}. Unexpected: {extra}.",
            missing=missing,
            extra=extra,
        )

    # N1/N2/N3 + V19/V20, per codon.
    normalised: dict[str, list[tuple[str, float]]] = {}
    spelling_failed = False
    n_uppercased = 0
    n_rna = 0
    for aa in sorted(present):
        pairs = codons[aa]
        if not isinstance(pairs, list):
            report._err(
                "V19",
                f"Codon list for {aa} is not a list.",
                codon=repr(pairs),
            )
            spelling_failed = True
            continue
        out: list[tuple[str, float]] = []
        for entry in pairs:
            if not isinstance(entry, (list, tuple)) or len(entry) != 2:
                report._err(
                    "V19",
                    f"Malformed codon entry {entry!r} under {aa}.",
                    codon=repr(entry),
                )
                spelling_failed = True
                continue
            raw, freq = entry
            report.codons_examined += 1
            codon = str(raw).strip()  # N3
            if codon != str(raw):
                pass  # N3 is silent by design
            upper = codon.upper()
            if upper != codon:
                n_uppercased += 1
            codon = upper
            if "U" in codon:
                n_rna += 1
                codon = codon.replace("U", "T")  # N1
            report.checks_performed += 1  # V20
            if len(codon) != 3:
                report._err(
                    "V20",
                    f"'{codon}' is {len(codon)} letters. A codon is exactly 3.",
                    codon=codon,
                    n=len(codon),
                )
                spelling_failed = True
                continue
            report.checks_performed += 1  # V19
            if not _CODON_RE.match(codon):
                report._err(
                    "V19",
                    f"'{codon}' is not a DNA codon.",
                    codon=codon,
                )
                spelling_failed = True
                continue
            out.append((codon, freq))
        normalised[aa] = out

    if n_rna:
        report._norm(
            "N1",
            f"RNA codons were converted to DNA (U to T), {n_rna} codons.",
            n=n_rna,
        )
    if n_uppercased:
        report._norm(
            "N2",
            f"{n_uppercased} codon(s) were lowercase and have been converted "
            f"to uppercase.",
            n=n_uppercased,
        )

    if not spelling_failed:
        # V16: codon -> AA assignment against the declared genetic code.
        if genetic_code is not None:
            mapping = _code_table(genetic_code)
            for aa, pairs in normalised.items():
                for codon, _ in pairs:
                    report.checks_performed += 1  # V16
                    expected = mapping.get(codon)
                    if expected is not None and expected != aa:
                        report._err(
                            "V16",
                            f"Codon {codon} is listed under {aa}, but genetic "
                            f"code {genetic_code} translates it as {expected}.",
                            codon=codon,
                            declared=aa,
                            n=genetic_code,
                            expected=expected,
                        )

        if aa_set_ok:
            report.checks_performed += 1  # V18
            flat = [c for pairs in normalised.values() for c, _ in pairs]
            all_codons = {
                a + b + c
                for a in "ACGT" for b in "ACGT" for c in "ACGT"
            }
            miss = sorted(all_codons - set(flat))
            dup = sorted({c for c in flat if flat.count(c) > 1})
            if miss or dup or len(flat) != 64:
                report._err(
                    "V18",
                    f"Expected all 64 codons exactly once. Missing: {miss}. "
                    f"Duplicated: {dup}.",
                    missing=miss,
                    dup=dup,
                )

    _check_frequencies(normalised, report)
    return normalised


def _check_frequencies(
    normalised: dict[str, list[tuple[str, float]]], report: ValidationReport
) -> None:
    for aa in sorted(normalised):
        pairs = normalised[aa]
        bad_value = False
        for codon, freq in pairs:
            report.checks_performed += 1  # V21
            if isinstance(freq, bool) or not isinstance(freq, (int, float)) \
                    or math.isnan(float(freq)) or math.isinf(float(freq)) \
                    or not (0.0 <= float(freq) <= 1.0):
                report._err(
                    "V21",
                    f"Frequency for {codon} is {freq!r}. It must be a number "
                    f"between 0 and 1.",
                    codon=codon,
                    value=freq,
                )
                bad_value = True
        if bad_value or not pairs:
            report._suppressed_aas.add(aa)
            continue
        report.checks_performed += 1  # V24
        if max(float(f) for _, f in pairs) == 0.0:
            report._err(
                "V24",
                f"Every codon for {aa} has frequency 0, so kuma cannot "
                f"choose one.",
                aa=aa,
            )
            report._suppressed_aas.add(aa)
            continue
        total = sum(float(f) for _, f in pairs)
        report.checks_performed += 1  # V22
        if not (SUM_REJECT_BAND[0] <= total <= SUM_REJECT_BAND[1]):
            report._err(
                "V22",
                f"Frequencies for {aa} add up to {total:.3f}, not 1.",
                aa=aa,
                sum=round(total, 4),
            )
            continue
        report.checks_performed += 1  # V23
        if not (SUM_WARN_BAND[0] <= total <= SUM_WARN_BAND[1]):
            report._warn(
                "V23",
                f"Frequencies for {aa} add up to {total:.3f}. This is within "
                f"tolerance but suggests a rounded or incomplete source.",
                aa=aa,
                sum=round(total, 4),
            )


def _check_counts(
    data: dict,
    normalised: dict[str, list[tuple[str, float]]] | None,
    report: ValidationReport,
) -> None:
    counts = data.get("counts")
    if counts is None or normalised is None:
        return
    report.checks_performed += 1  # V25 group
    if not isinstance(counts, dict):
        report._err("V25", "counts must be an object.", codon="counts",
                    value=type(counts).__name__)
        return

    parsed: dict[str, list[tuple[str, int]]] = {}
    # Every codon name seen under counts, valid value or not. V26 asks whether
    # the two blocks describe the same codons; a bad value is V25's business.
    seen_codons: set[str] = set()
    bad_count = False
    for aa in sorted(counts):
        entries = counts[aa]
        out: list[tuple[str, int]] = []
        if not isinstance(entries, list):
            report._err("V25", f"counts for {aa} is not a list.",
                        codon=aa, value=repr(entries))
            bad_count = True
            continue
        for entry in entries:
            if not isinstance(entry, (list, tuple)) or len(entry) != 2:
                report._err("V25", f"Malformed count entry {entry!r}.",
                            codon=repr(entry), value=repr(entry))
                bad_count = True
                continue
            codon, value = str(entry[0]).strip().upper().replace("U", "T"), entry[1]
            seen_codons.add(codon)
            report.checks_performed += 1  # V25
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                report._err(
                    "V25",
                    f"Count for {codon} is {value!r}. Counts must be "
                    f"non-negative whole numbers.",
                    codon=codon,
                    value=value,
                )
                bad_count = True
                continue
            out.append((codon, value))
        parsed[aa] = out

    report.checks_performed += 1  # V26
    count_codons = seen_codons
    table_codons = {c for pairs in normalised.values() for c, _ in pairs}
    if count_codons != table_codons:
        diff = sorted(count_codons ^ table_codons)
        report._err(
            "V26",
            f"counts and codons list different codons: {diff}.",
            diff=diff,
        )
        return
    if bad_count:
        return

    recomputed: dict[str, dict[str, float]] = {}
    for aa, pairs in parsed.items():
        total = sum(v for _, v in pairs)
        if total <= 0:
            continue
        recomputed[aa] = {c: v / total for c, v in pairs}

    worst = 0.0
    for aa, pairs in normalised.items():
        implied = recomputed.get(aa)
        if not implied:
            continue
        for codon, stored in pairs:
            if not isinstance(stored, (int, float)) or isinstance(stored, bool):
                continue
            report.checks_performed += 1  # V27
            computed = implied[codon]
            dev = abs(float(stored) - computed)
            worst = max(worst, dev)
            if dev > COUNT_FRACTION_TOLERANCE:
                report._err(
                    "V27",
                    f"The stored frequency for {codon} is {stored} but its "
                    f"count implies {computed:.4f}. One of the two was edited "
                    f"by hand.",
                    codon=codon,
                    stored=stored,
                    computed=round(computed, 4),
                )

    if report.ok:
        # N4: counts are authoritative once they agree with the stored values.
        for aa, pairs in list(normalised.items()):
            implied = recomputed.get(aa)
            if not implied:
                continue
            normalised[aa] = [(c, implied[c]) for c, _ in pairs]
        report._norm(
            "N4",
            "Frequencies were recomputed from the codon counts.",
        )


def _check_aliases(
    data: dict, stem: str, ctx: ValidationContext, report: ValidationReport
) -> None:
    aliases = data.get("aliases")
    if aliases is None:
        return
    report.checks_performed += 1  # V28 group
    if not isinstance(aliases, list):
        report._err("V28", "aliases must be a list of strings.", alias=repr(aliases))
        return
    own_key = report.key or stem
    known_keys = set(ctx.builtin_keys) | set(ctx.existing_user_tables)
    for raw in aliases:
        report.checks_performed += 1  # V28
        alias = str(raw).strip().lower()
        if not alias:
            report._err("V28", "An alias cannot be empty.", alias="")
            continue
        report.checks_performed += 1  # V29
        if alias in known_keys and alias != own_key:
            report._err(
                "V29",
                f"Alias '{alias}' is already the key of {alias}.",
                alias=alias,
                other=alias,
            )
            continue
        report.checks_performed += 1  # V30
        other = ctx.builtin_aliases.get(alias) or ctx.existing_user_aliases.get(alias)
        if other is not None and other != own_key:
            report._err(
                "V30",
                f"Alias '{alias}' already points to {other}.",
                alias=alias,
                other=other,
            )


def _check_traceability(
    data: dict,
    normalised: dict[str, list[tuple[str, float]]] | None,
    ctx: ValidationContext,
    report: ValidationReport,
) -> None:
    provenance = data.get("provenance")

    report.checks_performed += 1  # V31
    if isinstance(provenance, dict):
        cds = provenance.get("cds_counted")
        codon_count = provenance.get("codon_count")
        low_cds = isinstance(cds, int) and cds < LOW_CDS_WARN_THRESHOLD
        low_codons = (
            isinstance(codon_count, int)
            and codon_count < LOW_CODON_COUNT_WARN_THRESHOLD
        )
        if low_cds or low_codons:
            report._warn(
                "V31",
                f"This table was built from {cds} coding sequences "
                f"({codon_count} codons). That is a small sample.",
                cds=cds,
                codons=codon_count,
            )

    # V32/V33 are exempt for bundled tables: they carry no provenance block and
    # their aliases live in the hardcoded _ORGANISM_ALIASES map.
    if not ctx.is_builtin:
        report.checks_performed += 1  # V32
        if provenance is None:
            report._warn(
                "V32",
                "This table records no provenance. kuma will store it, but a "
                "run made with it cannot say where the numbers came from.",
            )
        report.checks_performed += 1  # V33
        if not data.get("aliases"):
            report._warn(
                "V33",
                f"No aliases. kuma will not auto-select this organism when "
                f"you load a sequence annotated as "
                f"'{data.get('name', report.stem)}'.",
                name=data.get("name", report.stem),
            )

    # V34 is exempt for bundled tables as well. Measured fact, 2026-09-17:
    # mextorquens.json lists TTA at fraction 0.0, so warning here would fire on
    # a table kuma ships. The design note (section 6.8) exempted only V32/V33
    # because it was written when four tables shipped and none had a zero.
    if not ctx.is_builtin and normalised:
        report.checks_performed += 1  # V34
        zeros = sorted(
            codon
            for aa, pairs in normalised.items()
            if aa not in report._suppressed_aas
            for codon, freq in pairs
            if isinstance(freq, (int, float)) and not isinstance(freq, bool)
            and float(freq) == 0.0
        )
        if zeros:
            report._warn(
                "V34",
                f"{len(zeros)} codon(s) have frequency 0 and will never be "
                f"chosen: {zeros}.",
                n=len(zeros),
                list=zeros,
            )

    report.checks_performed += 1  # V35
    unknown = sorted(set(data) - _KNOWN_TOP_LEVEL)
    if unknown:
        report._warn(
            "V35",
            f"Ignoring unrecognised field(s): {unknown}.",
            list=unknown,
        )
