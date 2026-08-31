"""The bundled samples are one campaign, KURO through MAME.

``Help > Load Sample Data`` opens KURO on a plasmid and a round-0 EVOLVEpro
prediction, and MAME on a plate, a verdict workbook and a set of activity
measurements. Nothing forced those two halves to describe the same experiment,
and for a long time they did not: KURO predicted substitutions at one set of
positions while MAME scored a different set entirely, so the demo showed a
campaign nobody could have run.

Each test below states one link of that chain and reads the shipped bytes to
check it. They read the files rather than
``python-core/scripts/generate_mame_step4_samples.py`` on purpose: the generator
is what should produce a coherent set, and these are what ships.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

import pytest
import python_calamine
from Bio import SeqIO
from Bio.Seq import Seq

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SAMPLES = _REPO_ROOT / "src-tauri" / "samples"
_MAME = _SAMPLES / "mame"

#: ``F28A`` style: reference residue, position, substitution.
_VARIANT = re.compile(r"^([A-Z])(\d+)([A-Z])$")


def _sheet(path: Path, index: int = 0) -> list[list]:
    workbook = python_calamine.CalamineWorkbook.from_path(str(path))
    return list(workbook.get_sheet_by_index(index).to_python())


def _sheet_with(path: Path, *columns: str) -> tuple[list[str], list[list]]:
    """The first sheet carrying every named column, with its header lowered."""
    workbook = python_calamine.CalamineWorkbook.from_path(str(path))
    for index in range(len(workbook.sheet_names)):
        rows = _sheet(path, index)
        if not rows:
            continue
        header = [str(cell).strip().lower() for cell in rows[0]]
        if all(column in header for column in columns):
            return header, rows
    raise AssertionError(f"{path.name} has no sheet carrying {columns}")


@pytest.fixture(scope="module")
def reference_protein() -> str:
    cds = "".join(
        line.strip()
        for line in (_MAME / "reference.fasta").read_text(encoding="utf-8").splitlines()
        if line and not line.startswith(">")
    )
    return str(Seq(cds).translate()).rstrip("*")


@pytest.fixture(scope="module")
def predictions() -> dict[str, float]:
    with (_SAMPLES / "sample_evolvepro.csv").open(encoding="utf-8") as handle:
        return {
            row["variant"].strip(): float(row["y_pred"])
            for row in csv.DictReader(handle)
        }


@pytest.fixture(scope="module")
def designed() -> list[tuple[str, int, str]]:
    """``(mutant_id, position, wt_aa)`` for the designed rows, control excluded."""
    header, rows = _sheet_with(
        _MAME / "03_mame_expected_mutations.xlsx", "mutant_id", "position", "wt_aa"
    )
    out: list[tuple[str, int, str]] = []
    for row in rows[1:]:
        name = str(row[header.index("mutant_id")]).strip()
        if not name or name.upper() == "WT":
            continue
        out.append(
            (
                name,
                int(float(row[header.index("position")])),
                str(row[header.index("wt_aa")]).strip(),
            )
        )
    return out


def test_the_two_halves_describe_one_protein(reference_protein):
    """KURO designs primers against the plasmid; MAME scores against the FASTA.

    A campaign is only one campaign if those are the same coding sequence. They
    are two files, so nothing but this makes them agree.
    """
    record = next(SeqIO.parse(str(_SAMPLES / "sample_plasmid.gb"), "genbank"))
    coding = [f for f in record.features if f.type == "CDS"]
    assert coding, "the sample plasmid carries no CDS feature"
    plasmid = str(Seq(str(coding[0].extract(record.seq))).translate()).rstrip("*")

    assert plasmid == reference_protein, (
        f"the plasmid CDS translates to {len(plasmid)} residues and the MAME "
        f"reference to {len(reference_protein)}; the demo would design primers "
        "against one protein and score reads against another"
    )


def test_every_designed_variant_was_a_predicted_candidate(designed, predictions):
    """The plate holds what the round-0 prediction proposed, nothing else.

    A variant on the plate that the prediction never named has no reason to be
    in the campaign: nobody chose it and no primer was designed for it.
    """
    unpredicted = [name for name, _, _ in designed if name not in predictions]

    assert not unpredicted, (
        f"{len(unpredicted)} of {len(designed)} designed variants are absent "
        f"from sample_evolvepro.csv: {unpredicted}"
    )


def test_the_designed_variants_are_the_best_predicted_that_could_be_built(
    designed, predictions, tmp_path
):
    """Selection is by prediction rank, minus what KURO cannot design.

    Running the design engine rather than trusting a list of known failures:
    a candidate's primers stop designing when a polymerase profile or a Tm rule
    moves, and a hard-coded failure list would keep asserting the old answer.
    Skipping a candidate is only defensible when its primers do not design, so
    that is the thing checked.
    """
    from kuma_core.kuro.sdm_engine import design_sdm_primers

    record = next(SeqIO.parse(str(_SAMPLES / "sample_plasmid.gb"), "genbank"))
    cds_start = int([f for f in record.features if f.type == "CDS"][0].location.start)
    ranked = sorted(predictions, key=lambda name: predictions[name], reverse=True)

    mutations = tmp_path / "mutations.csv"
    mutations.write_text(
        "mutation\n" + "".join(f"{name}\n" for name in ranked), encoding="utf-8"
    )
    results, _candidates, _failed = design_sdm_primers(
        fasta_path=_SAMPLES / "sample_plasmid.gb",
        target_start=cds_start,
        mutations_csv=mutations,
        polymerase="KOD",
    )
    buildable = {str(result.mutation.raw) for result in results}

    chosen = [name for name, _, _ in designed]
    expected = [name for name in ranked if name in buildable][: len(chosen)]

    assert sorted(chosen) == sorted(expected), (
        f"the plate holds {sorted(chosen)}; the best {len(chosen)} predicted "
        f"candidates KURO can build are {sorted(expected)}"
    )
    unbuildable = [name for name in chosen if name not in buildable]
    assert not unbuildable, (
        f"{unbuildable} are on the plate but KURO designs no primers for them, "
        "so the campaign could not have made them"
    )


def test_every_designed_row_names_the_residue_the_reference_carries(
    designed, reference_protein
):
    """A stated ``wt_aa`` that the sequence does not hold is a mis-numbered list.

    This is the check that the previous sample set failed: its positions were
    numbered against a different protein, so wells were scored against residues
    the reference never had.
    """
    wrong = []
    for name, position, wt_aa in designed:
        match = _VARIANT.match(name)
        assert match, f"{name} is not single-substitution notation"
        actual = (
            reference_protein[position - 1]
            if position <= len(reference_protein)
            else "(past the end)"
        )
        if actual != wt_aa or match.group(1) != wt_aa:
            wrong.append(f"{name} states {wt_aa}{position}, reference holds {actual}")

    assert not wrong, "\n".join(wrong)


def test_the_plate_holds_exactly_the_designed_variants(designed):
    rows = _sheet(_MAME / "06_mame_plate_layout.xlsx")
    layout = {
        str(row[0]).strip()
        for row in rows[1:]
        if str(row[0]).strip() and str(row[0]).strip().upper() != "WT"
    }

    assert layout == {name for name, _, _ in designed}, (
        f"the layout holds {sorted(layout)} and the design list "
        f"{sorted(name for name, _, _ in designed)}"
    )


def test_the_verdict_workbook_scores_exactly_those_variants(designed):
    """Step 4 reads its NGS evidence here, keyed by variant.

    A verdict workbook naming other variants would gate out the whole plate,
    which is the shape a build failure takes rather than an error message.
    """
    header, rows = _sheet_with(_MAME / "13_mame_verdict.xlsx", "well_id", "mutant_id")
    column = header.index("mutant_id")
    scored = {
        str(row[column]).strip()
        for row in rows[1:]
        if len(row) > column and str(row[column]).strip() not in {"", "WT"}
    }

    assert scored == {name for name, _, _ in designed}, (
        f"the verdict workbook scores {sorted(scored)}"
    )


def test_the_step4_export_carries_exactly_the_final_pass_variants(designed):
    """The round closes where it opened, in the notation the next round reads.

    ``build_evolvepro_input`` (kuma_core/mame/activity/build_evolvepro_input.py)
    requires explicit FINAL PASS NGS evidence for every row it writes. The
    user rule this plate demonstrates (2026-08-31) is that nothing which is
    not PASS may ever be selected as a variant's FINAL (selected-replicate)
    representative, so every one of the 16 designed variants reads FINAL PASS
    and none is dropped here. The 7 non-PASS ``VerdictClass`` values this
    campaign also demonstrates (AMBIGUOUS/LOWDEPTH/WRONG_AA/MANY/FRAMESHIFT/
    MIXED/NO_CALL, see generate_mame_step4_samples.py's ``_TARGET_VERDICT``)
    still exist in the underlying 51-row verdict set, one per targeted
    (variant, native-barcode) well, but each of those variants also has two
    clean native barcodes, so the picker always resolves it to PASS at FINAL.
    The export is checked against the FINAL verdict actually read off
    13_mame_verdict.xlsx's "Final" sheet, not asserted independently of it.
    """
    header, rows = _sheet_with(_MAME / "13_mame_verdict.xlsx", "mutant_id", "verdict")
    mutant_col = header.index("mutant_id")
    verdict_col = header.index("verdict")
    pass_mutants = {
        str(row[mutant_col]).strip()
        for row in rows[1:]
        if len(row) > verdict_col
        and str(row[mutant_col]).strip().upper() not in {"", "WT"}
        and str(row[verdict_col]).strip() == "PASS"
    }
    assert pass_mutants, "no FINAL PASS variant found in 13_mame_verdict.xlsx"

    designed_names = {name for name, _, _ in designed}
    assert pass_mutants == designed_names, (
        "FINAL PASS mutants should be exactly the designed list (no variant "
        "should be selected as a non-PASS representative): "
        f"missing {sorted(designed_names - pass_mutants)}, "
        f"extra {sorted(pass_mutants - designed_names)}"
    )

    short = set()
    for name in pass_mutants:
        match = _VARIANT.match(name)
        assert match
        short.add(f"{match.group(2)}{match.group(3)}")

    rows = _sheet(_MAME / "08_mame_evolvepro_raw.xlsx")
    exported = {
        str(row[0]).strip()
        for row in rows[1:]
        if str(row[0]).strip() and str(row[0]).strip().upper() != "WT"
    }

    assert exported == short, f"the export carries {sorted(exported)}"
