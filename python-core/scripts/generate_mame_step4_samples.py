#!/usr/bin/env python3
"""Regenerate the bundled MAME sample set as one coherent campaign.

Every file this writes describes the same plate: the EGFP reference in
``src-tauri/samples/mame/reference.fasta``, ten designed variants, and the
placement kuma computes for them. Nothing here is hand-authored, so the sample
set cannot drift into the state it shipped in, where the expected-mutation
positions were numbered against a different protein than the reference and no
combination of step 4 inputs could finish a build.

What it writes, all under ``src-tauri/samples/mame/``:

* ``03_mame_expected_mutations.xlsx`` - the designed variant list. Positions are
  numbered against the shipped reference and every ``wt_aa`` is read off it, so
  the list cannot claim a residue the sequence does not carry.
* ``sample_analysis_result.json`` - the Analyze screen fixture, produced by a
  real in-process pipeline run over synthetic consensus FASTA. No FASTQ and no
  MinKNOW run folder is bundled: a raw nanopore run is large and the app only
  needs the result to show one.
* ``13_mame_verdict.xlsx`` - the Analyze workbook from that same run. Step 4
  requires a verdict workbook and had none, which is why the sample data could
  not reach a finished build.
* ``06_mame_plate_layout.xlsx`` - the placement, one well per variant.
* ``07_mame_activity_long.csv`` / ``.xlsx`` - well-labeled long format already
  relative to wild-type.
* ``14_mame_activity_long_raw.csv`` - the same measurements unnormalised, with
  the ``WT_1``..``WT_3`` rows that ``activity_scale="raw"`` divides by.
* ``15_mame_activity_variant.csv`` - variant-labeled long format, the branch
  that needs no plate layout at all.
* ``10_mame_gc_prenormalised.xlsx`` - GC sheet already relative to wild-type.
* ``11_mame_gc_fid_round1_raw.xlsx`` - raw Agilent FID report.
* ``09_mame_agilent_rep_batch.xlsx`` - variant-labeled confirmation report.
* ``12_mame_agilent_numeric_index.xlsx`` - numeric-ID confirmation report, whose
  identifier count now matches the plate order it is decoded against.

Usage::

    PYTHONPATH=.:python-core python python-core/scripts/generate_mame_step4_samples.py

The script is re-runnable and overwrites each file. It verifies what it wrote by
running every step 4 input branch through ``build_evolvepro_input`` and refuses
to leave a sample behind that its own parser rejects.
"""

from __future__ import annotations

import json
import logging
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_PYTHON_CORE = _SCRIPT_DIR.parent
_REPO_ROOT = _PYTHON_CORE.parent

for _p in [str(_REPO_ROOT), str(_PYTHON_CORE)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

SAMPLES = _REPO_ROOT / "src-tauri" / "samples" / "mame"
REFERENCE = SAMPLES / "reference.fasta"

#: Designed variants, numbered against the shipped reference.
#:
#: The reference is EGFP, which already carries the two substitutions that turn
#: wild-type avGFP into it (``F64L`` and ``S65T`` in avGFP numbering). Asking a
#: campaign to introduce those again is what the previous list did, and it is
#: not a mutation any primer can make. These ten are positions the reference
#: still holds the wild-type residue at, so each one is a substitution that can
#: actually be designed, ordered and sequenced.
#:
#: ``(position, mt_aa, mt_codon, note)``. ``wt_aa`` and ``wt_codon`` are read
#: off the reference rather than stated here, so a wrong position fails loudly
#: instead of shipping a list that disagrees with the sequence.
#:
#: Listed by ascending position, which is not cosmetic. The plate is filled in
#: file order by ``build_draft_layout``, while the numeric-ID decoder derives
#: its plate order from ``expected_variant_order``, which sorts by position. The
#: two agree only when the file is already sorted, and a sample set that
#: disagreed with itself would place a variant in one well and score it in
#: another. Keeping the list sorted is the sample-side half of that; the two
#: order sources still owe each other a reconciliation.
DESIGNED: tuple[tuple[int, str, str, str], ...] = (
    (67, "H", "CAC", "blue-shifted chromophore"),
    (100, "S", "TCC", "folding"),
    (148, "P", "CCC", "barrel turn"),
    (149, "D", "GAC", "barrel turn"),
    (154, "T", "ACG", "folding"),
    (164, "A", "GCG", "folding"),
    (168, "T", "ACC", "chromophore environment"),
    (204, "Y", "TAC", "yellow-shifted, stacks on the chromophore"),
    (206, "T", "ACC", "chromophore environment"),
    (207, "K", "AAG", "breaks the dimer interface"),
)

#: Activity relative to wild-type, per variant, as the demo reports it. Three
#: replicate measurements each, spread by a per-variant amount rather than a
#: single constant so a reader cannot mistake the spread for a fixed artefact.
ACTIVITY: dict[str, tuple[float, float, float]] = {
    "Y67H": (0.47, 0.44, 0.51),
    "T204Y": (2.29, 2.31, 2.33),
    "A207K": (1.20, 1.18, 1.21),
    "F100S": (1.51, 1.53, 1.56),
    "M154T": (1.84, 1.87, 1.86),
    "V164A": (1.63, 1.60, 1.66),
    "S148P": (0.88, 0.91, 0.86),
    "H149D": (1.05, 1.02, 1.09),
    "I168T": (3.11, 3.07, 3.13),
    "S206T": (1.34, 1.31, 1.37),
}

#: Wild-type replicates on the raw scale. Every raw value below is this mean
#: times the relative activity above, so the two long-format files state the
#: same measurements on two scales and can be compared against each other.
WT_RAW: tuple[float, float, float] = (1011.0, 962.0, 982.0)

#: Confirmation re-measurement, a subset re-run on the instrument. Values sit
#: close to but not on the primary numbers, which is what a repeat measurement
#: looks like and what the merge step exists to reconcile.
CONFIRMATION: dict[str, tuple[float, float]] = {
    "I168T": (3.18, 3.21),
    "T204Y": (2.26, 2.28),
    "M154T": (1.89, 1.91),
}


@dataclass(frozen=True)
class Variant:
    """One designed substitution, resolved against the reference."""

    mutant_id: str      # internal notation, e.g. "Y67H"
    position: int
    wt_aa: str
    mt_aa: str
    wt_codon: str
    mt_codon: str
    note: str

    @property
    def short(self) -> str:
        """EVOLVEpro notation, e.g. ``67H``."""
        return f"{self.position}{self.mt_aa}"


# ---------------------------------------------------------------------------
# reference
# ---------------------------------------------------------------------------

def read_reference_cds() -> str:
    lines = REFERENCE.read_text(encoding="utf-8").splitlines()
    return "".join(line.strip() for line in lines if line and not line.startswith(">"))


def translate(cds: str) -> str:
    from Bio.Seq import Seq

    return str(Seq(cds).translate())


def resolve_variants(cds: str) -> list[Variant]:
    """Bind each designed substitution to the residue the reference carries."""
    protein = translate(cds)
    resolved: list[Variant] = []
    for position, mt_aa, mt_codon, note in DESIGNED:
        if position > len(protein):
            raise ValueError(
                f"position {position} is past the end of the reference protein "
                f"({len(protein)} residues)"
            )
        wt_aa = protein[position - 1]
        if wt_aa == mt_aa:
            raise ValueError(
                f"position {position} already holds {mt_aa}: the reference "
                "carries this substitution, so it cannot be designed"
            )
        wt_codon = cds[(position - 1) * 3 : position * 3]
        resolved.append(
            Variant(
                mutant_id=f"{wt_aa}{position}{mt_aa}",
                position=position,
                wt_aa=wt_aa,
                mt_aa=mt_aa,
                wt_codon=wt_codon,
                mt_codon=mt_codon,
                note=note,
            )
        )
    return resolved


def apply_substitution(cds: str, variant: Variant) -> str:
    start = (variant.position - 1) * 3
    return cds[:start] + variant.mt_codon + cds[start + 3 :]


# ---------------------------------------------------------------------------
# 03 expected mutations
# ---------------------------------------------------------------------------

_EXPECTED_HEADER = [
    "mutant_id",
    "position",
    "wt_aa",
    "mt_aa",
    "wt_codon",
    "mt_codon",
    "group_id",
    "primer_set_ref",
    "notation_type",
    "status",
]


def write_expected_mutations(variants: list[Variant], path: Path) -> None:
    import openpyxl

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "expected_mutations"
    sheet.append(_EXPECTED_HEADER)
    for index, variant in enumerate(variants, 1):
        sheet.append(
            [
                variant.mutant_id,
                variant.position,
                variant.wt_aa,
                variant.mt_aa,
                variant.wt_codon,
                variant.mt_codon,
                f"G{index}",
                f"PS_{index:03d}",
                "single",
                "designed",
            ]
        )
    # The control row, last. It is an occupant rather than an annotation: the
    # plate reserves a well for it, and the row number it sits at is the well it
    # gets. A file without it places the control by default somewhere at the end
    # of the plate, which is a different plate than the one the operator wrote
    # down. It carries no residue, so its position reads as 0 and nothing
    # compares it.
    sheet.append(["WT", "n/a", "-", "-", "-", "-", "G0", "-", "wt", "control"])
    workbook.save(path)


# ---------------------------------------------------------------------------
# consensus FASTA, one well per occupant
# ---------------------------------------------------------------------------

def seq_to_token(seq: int) -> str:
    """``{reverse}_{forward}`` barcode token for a 1-based occupant index."""
    from kuma_core.mame.plate_geometry import DEFAULT_ADDRESSING

    row, col = DEFAULT_ADDRESSING.seq_to_rc(seq)
    return f"{row}_{col}"


_FASTA_STATS = (
    "depth=240 input_reads=240 aligned_reads=232 mapq_failed=5 span_failed=3 "
    "low_depth_positions=0 consensus_n_fraction=0.000 low_quality_bases=0 "
    "max_minor_allele_fraction=0.04 mixed_positions=0"
)


def build_consensus_dir(
    workdir: Path, cds: str, layout: dict[str, str], by_id: dict[str, Variant]
) -> Path:
    """One consensus FASTA per occupied well, named by that well's barcode."""
    from kuma_core.mame.plate_geometry import well_to_seq

    consensus = workdir / "consensus"
    native = consensus / "NB01"
    native.mkdir(parents=True)

    for well, sample in layout.items():
        token = seq_to_token(well_to_seq(well))
        sequence = cds if sample == "WT" else apply_substitution(cds, by_id[sample])
        (native / f"{token}.fasta").write_text(
            f">{token} {_FASTA_STATS}\n{sequence}\n", encoding="utf-8"
        )
    return consensus


# ---------------------------------------------------------------------------
# activity samples, all derived from the placement
# ---------------------------------------------------------------------------

def _variant_wells(layout: dict[str, str]) -> list[tuple[str, str]]:
    """``(well, mutant_id)`` for the occupied non-control wells, in plate order."""
    from kuma_core.mame.plate_geometry import well_to_seq

    wells = [(well, sample) for well, sample in layout.items() if sample != "WT"]
    return sorted(wells, key=lambda item: well_to_seq(item[0]))


def _wt_wells(layout: dict[str, str]) -> list[str]:
    from kuma_core.mame.plate_geometry import well_to_seq

    return sorted(
        (well for well, sample in layout.items() if sample == "WT"),
        key=well_to_seq,
    )


def write_plate_layout(layout: dict[str, str], path: Path) -> None:
    """The placement as the operator-facing layout sheet.

    One well per variant. A repeated well would name one variant twice, and both
    the layout reader and the verdict reader refuse that: a variant that sits in
    two wells has no single well for the NGS evidence to be attached to.
    """
    import openpyxl
    from kuma_core.mame.plate_geometry import well_to_seq

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "Plate Layout"
    sheet.append(["Mutant", "Well Pos."])
    for well in sorted(layout, key=well_to_seq):
        sheet.append([layout[well], well])
    workbook.save(path)


def write_long_relative(layout: dict[str, str], csv_path: Path, xlsx_path: Path) -> None:
    """Well-labeled long format, already relative to wild-type."""
    import openpyxl

    rows: list[tuple[str, str, float, int]] = []
    for well, mutant_id in _variant_wells(layout):
        for replicate, value in enumerate(ACTIVITY[mutant_id], 1):
            rows.append(("plate01", well, value, replicate))
    # The wild-type rows carry a ``WT_n`` label rather than their well, the same
    # spelling the raw file uses. On this scale they are already 1.0 and nothing
    # divides by them, but labelling them as an occupant would send them into
    # the well<->variant mapping, where the control well is deliberately absent.
    for replicate in (1, 2, 3):
        rows.append(("plate01", f"WT_{replicate}", 1.0, replicate))

    header = "plate_id,well_id,value,replicate_idx\n"
    body = "".join(f"{p},{w},{v},{r}\n" for p, w, v, r in rows)
    csv_path.write_text(header + body, encoding="utf-8")

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "activity"
    sheet.append(["plate_id", "well_id", "value", "replicate_idx"])
    for row in rows:
        sheet.append(list(row))
    workbook.save(xlsx_path)


def write_long_raw(layout: dict[str, str], path: Path) -> None:
    """The same measurements before normalisation.

    ``activity_scale="raw"`` divides each cohort by the mean of its own ``WT_n``
    rows, so those rows carry a wild-type label rather than a well: they are the
    denominator, not an occupant to be scored.
    """
    wt_mean = sum(WT_RAW) / len(WT_RAW)
    lines = ["plate_id,well_id,value,replicate_idx"]
    for index, value in enumerate(WT_RAW, 1):
        lines.append(f"plate01,WT_{index},{value:.1f},{index}")
    for well, mutant_id in _variant_wells(layout):
        for replicate, relative in enumerate(ACTIVITY[mutant_id], 1):
            lines.append(f"plate01,{well},{relative * wt_mean:.1f},{replicate}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_long_variant(path: Path) -> None:
    """Variant-labeled long format.

    The label is the variant itself, so this branch needs no plate layout and no
    well<->variant mapping: it states what was measured rather than where.
    """
    lines = ["variant,activity,replicate_idx"]
    for mutant_id, values in ACTIVITY.items():
        short = f"{mutant_id[1:-1]}{mutant_id[-1]}"
        for replicate, value in enumerate(values, 1):
            lines.append(f"{short},{value},{replicate}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_gc_prenormalised(layout: dict[str, str], path: Path) -> None:
    """GC sheet whose areas are already wild-type relative."""
    import openpyxl

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "GC_normalised"
    sheet.append(["Sample Name", "Area"])
    for well in _wt_wells(layout):
        sheet.append([well, 1.0])
    for well, mutant_id in _variant_wells(layout):
        sheet.append([well, round(sum(ACTIVITY[mutant_id]) / 3, 3)])
    workbook.save(path)


def _agilent_blocks(rows: list[tuple[str, float]], title: str, path: Path) -> None:
    """An Agilent FID report: one two-line block per injection.

    The shape is the instrument export, not a table: each injection restates the
    signal header, then its ``Area``/``Sample Name`` pair, then a ``Sum`` line.
    """
    import openpyxl

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = title
    for name, area in rows:
        sheet.append(["Signal:", "FID1B"])
        sheet.append(["Area", "Sample Name"])
        sheet.append([area, name])
        sheet.append(["Sum", area])
        sheet.append(["", ""])
    workbook.save(path)


def write_round1_raw(layout: dict[str, str], path: Path) -> None:
    """Raw FID areas, normalised downstream against this report's own WT block."""
    wt_mean = sum(WT_RAW) / len(WT_RAW)
    rows: list[tuple[str, float]] = [
        (f"WT{index}", value) for index, value in enumerate(WT_RAW, 1)
    ]
    for well, mutant_id in _variant_wells(layout):
        for relative in ACTIVITY[mutant_id]:
            rows.append((well, round(relative * wt_mean, 1)))
    _agilent_blocks(rows, "GC-FID round1 raw", path)


def write_confirmation_report(path: Path) -> None:
    """Variant-labeled re-measurement of a handful of wells."""
    wt_mean = sum(WT_RAW) / len(WT_RAW)
    rows: list[tuple[str, float]] = [
        (f"WT{index}", value) for index, value in enumerate(WT_RAW, 1)
    ]
    for mutant_id, values in CONFIRMATION.items():
        short = f"{mutant_id[1:-1]}{mutant_id[-1]}"
        for relative in values:
            rows.append((short, round(relative * wt_mean, 1)))
    _agilent_blocks(rows, "Agilent", path)


def _above_wt(layout: dict[str, str]) -> list[tuple[str, str]]:
    """``(well, mutant_id)`` for the wells the primary screen put above WT.

    A numeric-ID confirmation indexes this subset rather than the whole plate,
    because an instrument re-runs the hits and numbers what it was given.
    """
    return [
        (well, mutant_id)
        for well, mutant_id in _variant_wells(layout)
        if sum(ACTIVITY[mutant_id]) / 3 > 1.0
    ]


def write_numeric_confirmation(layout: dict[str, str], path: Path) -> None:
    """Numeric-ID re-measurement of the wells the primary put above wild-type.

    Its identifiers count the above-WT subset, not the plate: an identifier that
    indexes a different set than the decoder derives names the wrong variant,
    which is a silent relabelling rather than an error.
    """
    wt_mean = sum(WT_RAW) / len(WT_RAW)
    rows: list[tuple[str, float]] = [
        (f"WT{index}", value) for index, value in enumerate(WT_RAW, 1)
    ]
    for index, (_, mutant_id) in enumerate(_above_wt(layout), 1):
        for relative in ACTIVITY[mutant_id][:2]:
            rows.append((str(index), round(relative * wt_mean, 1)))
    _agilent_blocks(rows, "Agilent numeric confirmation", path)


def write_numeric_report(layout: dict[str, str], path: Path) -> None:
    """The same report with the instrument numbering the samples.

    The identifiers index the plate order rather than naming variants, so the
    count has to match the order it is decoded against. Shipping six identifiers
    for a ten-variant plate is what made the previous file undecodable under
    every order source.
    """
    wt_mean = sum(WT_RAW) / len(WT_RAW)
    rows: list[tuple[str, float]] = [
        (f"WT{index}", value) for index, value in enumerate(WT_RAW, 1)
    ]
    for index, (_, mutant_id) in enumerate(_variant_wells(layout), 1):
        for relative in ACTIVITY[mutant_id]:
            rows.append((str(index), round(relative * wt_mean, 1)))
    _agilent_blocks(rows, "Agilent numeric index", path)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from kuma_core.mame.io.variant_list import read_variant_source
    from kuma_core.mame.layout import build_draft_layout

    cds = read_reference_cds()
    variants = resolve_variants(cds)
    by_id = {variant.mutant_id: variant for variant in variants}
    print(f"reference: {REFERENCE.name}, {len(cds)} bp, {len(cds) // 3} residues")
    for variant in variants:
        print(f"  {variant.mutant_id:>6}  {variant.wt_codon}->{variant.mt_codon}  {variant.note}")

    expected_path = SAMPLES / "03_mame_expected_mutations.xlsx"
    write_expected_mutations(variants, expected_path)
    print(f"wrote {expected_path.relative_to(_REPO_ROOT)}")

    read = read_variant_source(expected_path)
    draft = build_draft_layout(read.expected, wt_ordinal=read.wt_ordinal)
    if draft.dropped_mutant_ids:
        raise SystemExit(f"placement dropped {draft.dropped_mutant_ids}")
    layout = dict(draft.layout)
    print(f"placement: {len(layout)} wells -> {layout}")

    with tempfile.TemporaryDirectory(prefix="mame_step4_samples_") as _tmp:
        workdir = Path(_tmp)
        consensus = build_consensus_dir(workdir, cds, layout, by_id)
        run_workbook = workdir / "analysis.xlsx"

        from kuma_core.mame.ingest import IngestMode
        from kuma_core.mame.pipeline import run_analyze

        verdicts, replicates = run_analyze(
            input_dir=consensus,
            reference_path=REFERENCE,
            expected_path=expected_path,
            output_path=run_workbook,
            cds_start=0,
            cds_end=len(cds),
            mode="amplicon",
            min_file_size_kb=0.0,
            min_read_count=None,
            max_consensus_n_fraction=None,
            many_cutoff=5,
            ingest_mode=IngestMode.BARCODE,
            well_layout=layout,
            scored_wells=set(layout),
        )
        print(f"analyze: {len(verdicts)} verdicts, {len(replicates)} replicates")

        verdict_path = SAMPLES / "13_mame_verdict.xlsx"
        shutil.copyfile(run_workbook, verdict_path)
        print(f"wrote {verdict_path.relative_to(_REPO_ROOT)}")

        write_result_fixture(verdicts, replicates, run_workbook)

    write_plate_layout(layout, SAMPLES / "06_mame_plate_layout.xlsx")
    write_long_relative(
        layout,
        SAMPLES / "07_mame_activity_long.csv",
        SAMPLES / "07_mame_activity_long.xlsx",
    )
    write_long_raw(layout, SAMPLES / "14_mame_activity_long_raw.csv")
    write_long_variant(SAMPLES / "15_mame_activity_variant.csv")
    write_gc_prenormalised(layout, SAMPLES / "10_mame_gc_prenormalised.xlsx")
    write_round1_raw(layout, SAMPLES / "11_mame_gc_fid_round1_raw.xlsx")
    write_confirmation_report(SAMPLES / "09_mame_agilent_rep_batch.xlsx")
    write_numeric_report(layout, SAMPLES / "12_mame_agilent_numeric_index.xlsx")
    write_numeric_confirmation(
        layout, SAMPLES / "16_mame_agilent_numeric_confirmation.xlsx"
    )
    print("wrote the activity sample set")


def write_result_fixture(verdicts, replicates, run_workbook: Path) -> None:
    """Serialise the Analyze screen fixture through the sidecar handlers.

    The handlers rather than a hand-built dict: a copy of their output goes
    stale silently, and a fixture that has lost a field shows the user a panel
    that cannot state what it is missing.
    """
    from sidecar_mame import core as sidecar_core
    from sidecar_mame.core import SidecarState, set_last_analyze
    from sidecar_mame.handlers.analyze import (
        _serialize_replicate,
        _serialize_verdict,
        _summarize,
    )
    from sidecar_mame.handlers.export import handle_get_plate_data
    from sidecar_mame.handlers.health import handle_get_run_health

    with sidecar_core._state_lock:
        sidecar_core._state = SidecarState()
    set_last_analyze(verdicts, replicates, str(run_workbook), run_meta=None)

    fixture = {
        "schema": 1,
        "verdicts": [_serialize_verdict(v) for v in verdicts],
        "replicates": [_serialize_replicate(r) for r in replicates],
        "summary": _summarize(verdicts),
        "wells": handle_get_plate_data({})["wells"],
        "runHealth": handle_get_run_health({}),
    }
    path = SAMPLES / "sample_analysis_result.json"
    path.write_text(json.dumps(fixture, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {path.relative_to(_REPO_ROOT)}: {fixture['summary']}")


def verify() -> None:
    """Run every step 4 input branch over what was just written.

    Existence is not the property that matters here. A sample file is only a
    sample if the parser it was written for accepts it, and the previous set
    shipped files that no combination of inputs could carry to a finished
    build. Each case below is one branch of the primary/confirmation contract,
    and a branch that raises stops the script rather than leaving the sample
    set in the state this function exists to rule out.
    """
    from kuma_core.mame.activity.build_evolvepro_input import build_evolvepro_input

    verdict = SAMPLES / "13_mame_verdict.xlsx"
    layout = SAMPLES / "06_mame_plate_layout.xlsx"
    expected = SAMPLES / "03_mame_expected_mutations.xlsx"

    cases: list[tuple[str, dict]] = [
        (
            "long format, well labels, already relative, with the layout sheet",
            {"activity_path": SAMPLES / "07_mame_activity_long.csv",
             "activity_scale": "relative_to_wt", "layout_xlsx": layout},
        ),
        (
            "long format, well labels, mapping taken from the verdict workbook",
            {"activity_path": SAMPLES / "07_mame_activity_long.csv",
             "activity_scale": "relative_to_wt"},
        ),
        (
            "long format, xlsx twin of the same measurements",
            {"activity_path": SAMPLES / "07_mame_activity_long.xlsx",
             "activity_scale": "relative_to_wt", "layout_xlsx": layout},
        ),
        (
            "long format, raw values divided by the WT rows",
            {"activity_path": SAMPLES / "14_mame_activity_long_raw.csv",
             "activity_scale": "raw", "layout_xlsx": layout},
        ),
        (
            "long format, variant labels, no plate layout involved",
            {"activity_path": SAMPLES / "15_mame_activity_variant.csv",
             "activity_scale": "relative_to_wt"},
        ),
        (
            "GC sheet, already relative",
            {"gc_data_xlsx": SAMPLES / "10_mame_gc_prenormalised.xlsx",
             "layout_xlsx": layout},
        ),
        (
            "raw Agilent report, normalised against its own WT block",
            {"round1_report_xlsx": SAMPLES / "11_mame_gc_fid_round1_raw.xlsx",
             "layout_xlsx": layout},
        ),
        (
            "numeric-ID report as the primary screen",
            {"numeric_report_xlsx": SAMPLES / "12_mame_agilent_numeric_index.xlsx",
             "layout_xlsx": layout, "expected_xlsx": expected},
        ),
        (
            "variant-labeled confirmation on top of the long format",
            {"activity_path": SAMPLES / "07_mame_activity_long.csv",
             "activity_scale": "relative_to_wt", "layout_xlsx": layout,
             "remeasure_report_xlsx": SAMPLES / "09_mame_agilent_rep_batch.xlsx"},
        ),
        # The design list is the order source here and the plate file is left
        # out, because a numeric confirmation accepts exactly one of the two.
        # The primary numeric case above takes both, so the two numeric paths
        # disagree about how many order sources they will hold; the samples pick
        # the spelling each one accepts rather than papering over that.
        (
            "numeric-ID confirmation on top of the long format",
            {"activity_path": SAMPLES / "07_mame_activity_long.csv",
             "activity_scale": "relative_to_wt",
             "expected_xlsx": expected,
             "remeasure_numeric_xlsx":
                 SAMPLES / "16_mame_agilent_numeric_confirmation.xlsx"},
        ),
    ]

    #: The first case is also the shipped example of what step 4 produces, so
    #: the example is the build rather than a picture of one.
    exported_example = SAMPLES / "08_mame_evolvepro_raw.xlsx"

    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="mame_step4_verify_") as _tmp:
        out_dir = Path(_tmp)
        for index, (label, kwargs) in enumerate(cases, 1):
            destination = out_dir / f"case{index:02d}.xlsx"
            try:
                result = build_evolvepro_input(
                    destination, verdict_xlsx=verdict, **kwargs
                )
            except Exception as exc:  # noqa: BLE001 - the report is the point
                failures.append(f"  FAIL {label}\n        {type(exc).__name__}: {exc}")
                continue
            print(
                f"  ok   {label}: {result.n_variants} variants"
                f"{', ' + str(len(result.warnings)) + ' warning(s)' if result.warnings else ''}"
            )
            for warning in result.warnings:
                print(f"         warning: {warning}")
            if index == 1:
                shutil.copyfile(destination, exported_example)
                print(f"         kept as {exported_example.name}")

    if failures:
        print("\n".join(failures))
        raise SystemExit(
            f"{len(failures)} of {len(cases)} step 4 branches refused the samples"
        )
    print(f"all {len(cases)} step 4 branches built from the bundled samples")


if __name__ == "__main__":
    main()
    verify()
