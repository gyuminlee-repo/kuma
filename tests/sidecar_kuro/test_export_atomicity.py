"""Every KURO export the operator names is published by a staged rename.

PR #42 did this for MAME and recorded the KURO half as debt in
``_KNOWN_DIRECT_WRITERS``. The hazard is the same on this side: an order CSV, a
liquid-handler worklist or a plate workbook is read as instructions by whoever
opens the file the operator chose, and an interrupted ``open(path, "w")`` leaves
a truncated file that still carries that name.

Two properties per writer, mirroring ``tests/shared/test_audit_io_boundaries.py``
for the MAME exporters: a publish that fails leaves the previous file intact,
and the bytes land on a sibling stage so the target only ever appears whole.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from kuma_core.kuro import plate_mapper
from kuma_core.kuro.plate_mapper import PlateMapping
from kuma_core.shared import atomic_write


def _mappings() -> tuple[list[PlateMapping], list[PlateMapping]]:
    fwd = [
        PlateMapping(
            well="A1",
            primer_name="Q232A_F",
            sequence="ACGTACGTACGTACGTACGT",
            primer_type="forward",
            mutation="Q232A",
        )
    ]
    rev = [
        PlateMapping(
            well="A1",
            primer_name="Q232A_R",
            sequence="TGCATGCATGCATGCATGCA",
            primer_type="reverse",
            mutation="Q232A",
        )
    ]
    return fwd, rev


def _order_results() -> list:
    """The three attributes the order exporters read off a design result."""
    return [
        SimpleNamespace(
            mutation=SimpleNamespace(raw="Q232A"),
            forward_seq="ACGTACGTACGTACGTACGT",
            reverse_seq="TGCATGCATGCATGCATGCA",
        )
    ]


def _kuro_export_writers() -> list[tuple[str, object, str]]:
    """``(name, writer, suffix)`` for every exporter a KURO handler reaches.

    One entry per write site in ``kuma_core/kuro/plate_mapper.py`` plus the two
    the sidecar handlers perform themselves. Built as a list of callables taking
    only the output path so the two property tests below can share it, which is
    how the MAME side is arranged.
    """
    fwd, rev = _mappings()
    results = _order_results()
    return [
        (
            "plate_excel",
            lambda path: plate_mapper.export_plate_excel(fwd + rev, path),
            ".xlsx",
        ),
        ("idt_csv", lambda path: plate_mapper.export_idt_csv(results, path), ".csv"),
        ("twist_csv", lambda path: plate_mapper.export_twist_csv(results, path), ".csv"),
        (
            "echo_mapping_csv",
            lambda path: plate_mapper.export_echo_mapping_csv(fwd, rev, path),
            ".csv",
        ),
        (
            "echo_mapping_xlsx",
            lambda path: plate_mapper.export_echo_mapping_xlsx(fwd, rev, path),
            ".xlsx",
        ),
        (
            "janus_mapping_csv",
            lambda path: plate_mapper.export_janus_mapping_csv(fwd, rev, path),
            ".csv",
        ),
        (
            "janus_mapping_xlsx",
            lambda path: plate_mapper.export_janus_mapping_xlsx(fwd, rev, path),
            ".xlsx",
        ),
        (
            "macrogen_xls",
            lambda path: plate_mapper.export_macrogen_xls(
                fwd_primers=fwd,
                rev_primers=rev,
                fwd_plate_name="PlateF",
                rev_plate_name="PlateR",
                amount="25nm",
                purification="STD",
                output_path=str(path),
            ),
            ".xls",
        ),
        (
            "primers_fasta",
            lambda path: _export_primers_fasta(fwd + rev, path),
            ".fasta",
        ),
        (
            "benchmark_csv",
            lambda path: _export_benchmark_csv(path),
            ".csv",
        ),
        (
            "codon_table",
            lambda path: _export_codon_table(path),
            ".json",
        ),
    ]


def _export_primers_fasta(mappings, path: Path) -> None:
    from sidecar_kuro.handlers.export import _export_primers_fasta as writer

    writer(mappings, path)


def _export_benchmark_csv(path: Path) -> None:
    from sidecar_kuro.handlers.export import handle_export_benchmark_csv

    handle_export_benchmark_csv(
        {
            "filepath": str(path),
            "results": {"random": {"n_selected": 5, "hit_rate": 0.4}},
        }
    )


def _export_codon_table(path: Path) -> None:
    """Drive ``handle_export_codon_table`` against a table the registry reports.

    The handler exports the registry's normalised document rather than bytes on
    disk, so the installed ``ecoli`` table is the input with no fixture to set
    up. JSON because it is the one format whose body the handler builds itself.
    """
    from sidecar_kuro.handlers.codon import handle_export_codon_table

    handle_export_codon_table(
        {"key": "ecoli", "filepath": str(path), "format": "json"}
    )


_WRITERS = _kuro_export_writers()
_IDS = [entry[0] for entry in _WRITERS]


@pytest.mark.parametrize("name,writer,suffix", _WRITERS, ids=_IDS)
def test_kuro_export_publish_failure_keeps_previous_file(
    tmp_path, monkeypatch, name, writer, suffix
):
    """A failed publish leaves the previous export, not a truncated one.

    Before the staging change each of these opened the operator's path and
    wrote into it, so the same interruption replaced a good order file with a
    partial one under the name the lab reads.
    """
    output = tmp_path / f"previous{suffix}"
    output.write_bytes(b"PREVIOUS RUN")
    monkeypatch.setattr(
        atomic_write,
        "_replace_with_retry",
        lambda *_: (_ for _ in ()).throw(OSError("publish")),
    )
    with pytest.raises(OSError, match="publish"):
        writer(output)
    assert output.read_bytes() == b"PREVIOUS RUN"
    assert list(tmp_path.iterdir()) == [output]


@pytest.mark.parametrize("name,writer,suffix", _WRITERS, ids=_IDS)
def test_kuro_export_writes_a_sibling_stage_not_the_target(
    tmp_path, monkeypatch, name, writer, suffix
):
    """The bytes land on a sibling of the target, in the target's directory.

    Same directory so the publish is a rename rather than a cross-device copy,
    and the previous file still readable at the moment of the rename is what
    makes the swap invisible to a reader.
    """
    output = tmp_path / f"previous{suffix}"
    output.write_bytes(b"PREVIOUS RUN")
    seen: list[tuple[Path, Path]] = []
    real_replace = atomic_write._replace_with_retry

    def record(tmp_target, final_target):
        if Path(final_target) == output:
            seen.append((Path(tmp_target), Path(final_target)))
            assert Path(tmp_target) != output
            assert Path(tmp_target).parent == output.parent
            assert output.read_bytes() == b"PREVIOUS RUN"
        real_replace(tmp_target, final_target)

    monkeypatch.setattr(atomic_write, "_replace_with_retry", record)
    writer(output)
    assert len(seen) == 1
    assert output.read_bytes() != b"PREVIOUS RUN"


def _export_excel_params(path: Path) -> dict:
    """``handle_export_excel`` with the second pass switched on.

    ``mappings: []`` is the declared empty layout the handler honours, which
    keeps this about publishing rather than about plate layout. ``project_id``
    is what makes the handler reopen the workbook to add the meta sheet, and
    that second pass is the reason this handler could not be converted by
    pointing it at a staging writer.
    """
    return {"filepath": str(path), "mappings": [], "project_id": "P1"}


def test_export_excel_publishes_its_two_passes_once(tmp_path, monkeypatch):
    """The core writer and the openpyxl pass share one publish.

    ``export_plate_excel`` stages its own save, so leaving the handler alone
    would have published a workbook and then reopened the published file to add
    the report / benchmark / meta sheets. Between those two moments the name the
    operator chose holds a workbook missing those sheets, and if the second pass
    dies it holds a truncated one. One stage for the whole handler means the
    file appears once, complete.
    """
    from sidecar_kuro.handlers.export import handle_export_excel

    output = tmp_path / "plate.xlsx"
    output.write_bytes(b"PREVIOUS RUN")
    publishes: list[Path] = []
    real_replace = atomic_write._replace_with_retry

    def record(tmp_target, final_target):
        if Path(final_target) == output:
            publishes.append(Path(tmp_target))
            assert output.read_bytes() == b"PREVIOUS RUN"
        real_replace(tmp_target, final_target)

    monkeypatch.setattr(atomic_write, "_replace_with_retry", record)
    handle_export_excel(_export_excel_params(output))

    assert len(publishes) == 1
    assert output.read_bytes() != b"PREVIOUS RUN"
    import openpyxl

    assert "__kuma_meta__" in openpyxl.load_workbook(output).sheetnames


def test_export_excel_second_pass_failure_keeps_the_previous_workbook(
    tmp_path, monkeypatch
):
    """A failure after the core writer must not leave a half-built workbook.

    This is the case the handler could not reach before: the core writer had
    already published, so an error in the openpyxl pass left the operator's
    path holding a workbook without the meta sheet, or nothing at all.
    """
    from sidecar_kuro.handlers import export as export_handlers

    output = tmp_path / "plate.xlsx"
    output.write_bytes(b"PREVIOUS RUN")
    monkeypatch.setattr(
        export_handlers.openpyxl,
        "load_workbook",
        lambda *_, **__: (_ for _ in ()).throw(OSError("second pass")),
    )
    with pytest.raises(OSError, match="second pass"):
        export_handlers.handle_export_excel(_export_excel_params(output))

    assert output.read_bytes() == b"PREVIOUS RUN"
    assert not list(tmp_path.glob(".*.tmp*"))
