"""Per-clone GenBank vector maps: the parent vector with one SDM mutation applied.

Each designed mutation becomes one clone, and each clone gets its own ``.gb``
file: the full parent vector (backbone included) with the mutant codon spliced
in, every original feature kept, and a ``misc_feature`` labelled with the
mutation at the changed codon. The files are meant to be opened one by one in
SnapGene or Benchling.

The reference is parsed once and the mutations are applied in memory. Codon
coordinates come straight from :class:`Mutation.codon_start`, which the design
step computed against the same file (``design._build_mutation``), so nothing is
re-derived here.

Only codon substitutions reach this module: ``parse_mutation_notation`` accepts
``^[A-Z]\\d+[A-Z]$`` and nothing else, so no feature coordinate ever has to
move. A codon of any length other than three is refused per clone rather than
shifted.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from pathlib import Path

from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqFeature import FeatureLocation, SeqFeature

from kuma_core.kuro.mutation import Mutation
from kuma_core.shared.run_manifest import compute_input_sha256

VECTORMAP_DIR_SUFFIX = "_vectormaps"

# GenBank LOCUS names are at most 16 characters and Biopython refuses longer
# ones once the line overflows, so the name is always built here rather than
# inherited from the parsed record (a SnapGene file reads as "ORIGDB|GenBank").
_LOCUS_NAME_MAX = 16
_UNSAFE = re.compile(r"[^A-Za-z0-9_]")
_WELL_RE = re.compile(r"^([A-Za-z])(\d{1,2})$")

_GENBANK_SUFFIXES = {".gb", ".gbk", ".gbff"}


@dataclass(frozen=True)
class VectormapClone:
    """One clone: the forward-primer well it sits in and the mutation it carries."""

    well: str
    mutation: Mutation


def vectormaps_dir_for(target_dir: Path) -> Path:
    """Where the vector maps for an export go: a sibling of the bundle folder.

    Kept outside ``target_dir`` so the bundle folder still holds exactly the
    files ``EXPORT_ALL_BUNDLE`` declares. The one place the name is derived, so
    a later split into rounds (``<prefix>_R1``) only has to pass a different
    ``target_dir``.
    """
    return target_dir.parent / f"{target_dir.name}{VECTORMAP_DIR_SUFFIX}"


def padded_well(well: str) -> str:
    """``A1`` -> ``A01`` so the files sort in plate order in a file dialog."""
    m = _WELL_RE.match(well.strip())
    if not m:
        return _UNSAFE.sub("_", well)
    return f"{m.group(1).upper()}{int(m.group(2)):02d}"


def vectormap_filename(prefix: str, well: str, mutation_raw: str) -> str:
    return f"{prefix}_{padded_well(well)}_{_UNSAFE.sub('_', mutation_raw)}.gb"


def _locus_name(well: str, mutation_raw: str) -> str:
    return _UNSAFE.sub("_", f"{padded_well(well)}_{mutation_raw}")[:_LOCUS_NAME_MAX]


def read_reference(path: Path):
    """Parse the parent vector with its features, the way ``load_sequence`` picks it.

    GenBank: the first record, as ``_load_genbank`` does. SnapGene ``.dna``:
    Biopython's snapgene parser, which keeps features, CDS translations and
    the circular topology.
    """
    suffix = path.suffix.lower()
    if suffix in _GENBANK_SUFFIXES:
        with open(path, encoding="utf-8", errors="replace") as fh:
            record = next(SeqIO.parse(fh, "genbank"), None)
        if record is None:
            raise ValueError(f"No records found in GenBank file: {path.name}")
        return record
    if suffix == ".dna":
        return SeqIO.read(path, "snapgene")
    raise ValueError(
        f"Vector maps need an annotated reference (.gb/.gbk/.gbff/.dna), got {path.name}"
    )


def _fix_translations(record, mutation: Mutation) -> None:
    """Keep CDS ``/translation`` qualifiers true after the substitution.

    A forward, single-span CDS whose frame puts the changed codon on a whole
    residue has that residue replaced, after checking it was the wild type.
    Any other CDS overlapping the codon loses its translation qualifier: a
    viewer recomputes it, and a stale one would state the wrong protein.
    """
    cs = mutation.codon_start
    for feat in record.features:
        if feat.type != "CDS" or "translation" not in feat.qualifiers:
            continue
        loc = feat.location
        if loc is None or not (loc.start <= cs and cs + 3 <= loc.end):
            continue
        simple = len(getattr(loc, "parts", [loc])) == 1
        if simple and loc.strand in (1, None):
            frame = int(feat.qualifiers.get("codon_start", ["1"])[0]) - 1
            offset = cs - int(loc.start) - frame
            translation = feat.qualifiers["translation"][0]
            if offset >= 0 and offset % 3 == 0:
                idx = offset // 3
                if idx < len(translation) and translation[idx] == mutation.wt_aa:
                    feat.qualifiers["translation"] = [
                        translation[:idx] + mutation.mt_aa + translation[idx + 1:]
                    ]
                    continue
        del feat.qualifiers["translation"]


def build_clone_record(base, clone: VectormapClone):
    """Return a new record: *base* with the clone's codon substituted and marked."""
    mut = clone.mutation
    if len(mut.wt_codon) != 3 or len(mut.mt_codon) != 3:
        raise ValueError(
            f"{mut.raw}: only codon substitutions are supported "
            f"(wt {mut.wt_codon!r}, mt {mut.mt_codon!r})"
        )
    seq = str(base.seq)
    cs = mut.codon_start
    if cs < 0 or cs + 3 > len(seq):
        raise ValueError(f"{mut.raw}: codon at {cs} lies outside the {len(seq)} bp reference")
    found = seq[cs:cs + 3].upper()
    if found != mut.wt_codon.upper():
        raise ValueError(
            f"{mut.raw}: reference has {found} at {cs + 1}..{cs + 3}, "
            f"design expected {mut.wt_codon.upper()}"
        )

    rec = copy.deepcopy(base)
    rec.seq = Seq(seq[:cs] + mut.mt_codon.upper() + seq[cs + 3:])
    _fix_translations(rec, mut)
    rec.features.append(
        SeqFeature(
            FeatureLocation(cs, cs + 3, strand=1),
            type="misc_feature",
            qualifiers={
                "label": [mut.raw],
                "note": [
                    f"KURO SDM {mut.wt_aa}{mut.position}{mut.mt_aa} "
                    f"{mut.wt_codon.upper()}>{mut.mt_codon.upper()}, well {clone.well}"
                ],
            },
        )
    )
    name = _locus_name(clone.well, mut.raw)
    rec.name = name
    rec.id = name
    parent = base.description or base.name or "parent vector"
    rec.description = f"{parent} {mut.raw} (well {padded_well(clone.well)})"
    rec.annotations.setdefault("molecule_type", "DNA")
    return rec


def write_vectormaps(
    reference_path: Path,
    clones: list[VectormapClone],
    out_dir: Path,
    prefix: str,
    *,
    expected_sha256: str | None = None,
    expected_sequence: str | None = None,
) -> dict:
    """Write one ``.gb`` per clone into *out_dir*.

    ``expected_sha256`` is the reference digest recorded at design time. When
    it no longer matches the file, the codon coordinates may describe bytes
    that are gone, so nothing is written and ``skipped_reason`` says why.
    ``expected_sequence`` is the template the session holds; a parsed record
    that differs from it is refused the same way.

    Each clone is written in its own try, so one failure never stops the rest.
    Returns ``{"output_dir", "success", "failed", "skipped_reason", "sha_checked"}``.
    """
    result: dict = {
        "output_dir": str(out_dir),
        "success": [],
        "failed": [],
        "skipped_reason": None,
        "sha_checked": expected_sha256 is not None,
    }
    if expected_sha256 is not None:
        try:
            actual = compute_input_sha256(reference_path)
        except OSError as exc:
            result["skipped_reason"] = f"reference unreadable: {exc}"
            return result
        if actual != expected_sha256:
            result["skipped_reason"] = (
                f"reference {reference_path.name} changed after design "
                f"(sha256 {actual[:12]} != {expected_sha256[:12]})"
            )
            return result
    try:
        base = read_reference(reference_path)
    except Exception as exc:  # noqa: BLE001 -- reported, not raised
        result["skipped_reason"] = f"reference unreadable: {exc}"
        return result
    if expected_sequence is not None and str(base.seq).upper() != expected_sequence.upper():
        result["skipped_reason"] = (
            f"reference {reference_path.name} no longer matches the designed template"
        )
        return result

    out_dir.mkdir(parents=True, exist_ok=True)
    for clone in clones:
        name = vectormap_filename(prefix, clone.well, clone.mutation.raw)
        try:
            rec = build_clone_record(base, clone)
            SeqIO.write(rec, out_dir / name, "genbank")
            result["success"].append(name)
        except Exception as exc:  # noqa: BLE001 -- intentionally aggregating per clone
            result["failed"].append({"path": name, "reason": str(exc)})
    return result
