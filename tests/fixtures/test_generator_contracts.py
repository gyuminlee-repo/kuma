import gzip
import importlib.util
from pathlib import Path
from types import ModuleType

import openpyxl
import pytest


def _load(relative: str) -> ModuleType:
    path = Path(__file__).resolve().parents[2] / relative
    spec = importlib.util.spec_from_file_location("fixture_generator", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def demo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    module = _load("fixtures/mame_demo/generate.py")
    for name, path in {
        "DEMO_ROOT": tmp_path,
        "CONSENSUS_ROOT": tmp_path / "consensus",
        "REFERENCE_PATH": tmp_path / "reference.fasta",
        "XLSX_PATH": tmp_path / "KURO_expected.xlsx",
    }.items():
        monkeypatch.setattr(module, name, path)
    return module


def test_demo_consensus_follows_workbook_wells(demo: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(demo, "_assign_cases", lambda n: [["PASS"] * 3 for _ in range(n)])
    demo.generate(force=True, n_mutants=9)
    workbook = openpyxl.load_workbook(demo.XLSX_PATH, read_only=True)
    try:
        wells: list[str] = []
        for row in workbook["Fwd List"].iter_rows(min_row=2, values_only=True):
            assert isinstance(row[0], str)
            wells.append(row[0])
    finally:
        workbook.close()
    labels = [f"{ord(well[0]) - ord('A') + 1}_{int(well[1:])}" for well in wells]
    mutants = demo._build_mutants(9)
    cases = demo._assign_cases(9)
    for index, label in enumerate(labels):
        for nb_index, nb in enumerate(demo._NBS):
            path = demo.CONSENSUS_ROOT / nb / f"{label}.fasta"
            assert path.exists(), (label, nb)
            sequence = "".join(path.read_text().splitlines()[1:])
            assert sequence == demo._mutate_cds(demo._REFERENCE_CDS, mutants[index], cases[index][nb_index])


def test_demo_force_shrink_removes_only_obsolete_well_files(demo: ModuleType) -> None:
    demo.generate(force=True, n_mutants=9)
    unrelated = demo.CONSENSUS_ROOT / "NB01" / "notes.txt"
    unrelated.write_text("keep")
    demo.generate(force=True, n_mutants=2)
    for nb in demo._NBS:
        assert {path.name for path in (demo.CONSENSUS_ROOT / nb).glob("*.fasta")} == {
            "1_1.fasta", "2_1.fasta", "3_1.fasta",
        }
    assert unrelated.read_text() == "keep"


def test_fastq_gzip_is_byte_stable_across_names_and_clock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load("tests/fixtures/mame/_make_fixture.py")
    first, second = tmp_path / "first.gz", tmp_path / "second.gz"
    monkeypatch.setattr("time.time", lambda: 1000)
    module.write_fastq_gz(first, module.build_reads())
    monkeypatch.setattr("time.time", lambda: 2000)
    module.write_fastq_gz(second, module.build_reads())
    assert first.read_bytes() == second.read_bytes()
    expected = "".join(f"@{name}\n{seq}\n+\n{'I' * len(seq)}\n" for name, seq in module.build_reads())
    assert gzip.decompress(first.read_bytes()).decode() == expected
