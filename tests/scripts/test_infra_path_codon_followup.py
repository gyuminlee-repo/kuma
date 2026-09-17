import gzip
import itertools
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from kuma_core.kuro import codon_table


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("portable", [False, True])
@pytest.mark.parametrize("override", [None, "", "explicit", "trailing", "root"])
def test_benchmark_paths_when_workspace_is_inferred_or_overridden(
    tmp_path: Path, portable: bool, override: str | None,
) -> None:
    # Given an actual checkout or a portable copy and a cheap executable boundary.
    runner = ROOT / "benchmark/run_isps_260820.sh"
    workspace = ROOT.parent.parent
    if portable:
        workspace = tmp_path / "portable workspace"
        runner_copy = workspace / "cc/renamed checkout/benchmark" / runner.name
        runner_copy.parent.mkdir(parents=True)
        shutil.copyfile(runner, runner_copy)
        runner = runner_copy
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "python3"
    stub.write_text(
        '#!/bin/sh\nprintf "%s\\n" "$1" "$ISPS_DF_TEST" '
        '"$ISPS_RESULTS_DIR" "$ISPS_OUT_SUFFIX"\n', encoding="utf-8",
    )
    stub.chmod(0o755)
    env = os.environ.copy()
    env.pop("WORKSPACE_ROOT", None)
    env["PATH"] = str(bin_dir) + os.pathsep + env["PATH"]
    if override is not None:
        env["WORKSPACE_ROOT"] = {
            "": "",
            "explicit": str(tmp_path / "explicit workspace"),
            "trailing": str(tmp_path / "explicit workspace") + "/",
            "root": "/",
        }[override]
    expected = Path(env["WORKSPACE_ROOT"]) if override else workspace

    # When the real shell script runs from an unrelated working directory.
    result = subprocess.run(
        ["bash", str(runner)], cwd=tmp_path, env=env,
        capture_output=True, text=True, timeout=10, check=False,
    )

    # Then only the expensive benchmark is stubbed; exported paths remain observable.
    print(result.stdout, end="")
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout.splitlines() == [
        str(runner.with_name("isps_strategy_comparison.py")),
        str(expected / "020.admin/projects/070.KUMA_elements/999.kuma_record_input/df_test.csv"),
        str(expected / "cc/kuma/benchmark/results"),
        "_260820",
    ]


@pytest.mark.parametrize("compressed", [False, True])
@pytest.mark.parametrize("scenario", ["sparse", "known", "all_codons", "filtered"])
def test_codon_cli_when_input_has_known_counts(
    tmp_path: Path, compressed: bool, scenario: str,
) -> None:
    # Given known counts, including absent groups and a rounding tie in Leu.
    all_codons = {"".join(c) for c in itertools.product("ACGT", repeat=3)}
    sequences = {
        "sparse": "ATGTAA",
        "known": "ATG" + "GCT" * 2 + "GCC" + "CTG" * 101 + "CTA" * 100 + "TAA",
        "all_codons": "".join(sorted(all_codons)),
        "filtered": "",
    }
    rejected = (
        ">pseudo [pseudo=true]\nATGTAA\n>partial [partial=5prime]\nATGTAA\n"
        ">short\nAT\n>ambiguous\nATNTAA\n"
    )
    fasta = rejected
    if sequences[scenario]:
        fasta = ">accepted\n" + sequences[scenario].lower() + "\n" + rejected
    source = tmp_path / "input.fna"
    source.write_bytes(gzip.compress(fasta.encode()) if compressed else fasta.encode())
    output = tmp_path / "generated/table.json"
    command = [
        sys.executable, str(ROOT / "scripts/build_codon_table.py"), str(source),
        "--name", "Synthetic", "--taxid", "1", "--transl-table", "11",
        "--assembly", "synthetic", "--strain", "test", "--source", "test",
        "--source-release", "test", "--out", str(output),
    ]

    # When the real CLI parses, counts, normalizes, and writes its output.
    result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)

    # Then emitted bytes and counts satisfy the documented contract.
    print(result.stderr, end="")
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    text = output.read_text(encoding="utf-8")
    data = json.loads(text)
    rows = data["codons"]
    flat = {codon: fraction for entries in rows.values() for codon, fraction in entries}
    assert len(flat) == sum(map(len, rows.values())) == 64
    assert set(flat) == all_codons
    assert data["n_cds"] == int(bool(sequences[scenario]))
    assert f"{len(sequences[scenario]) // 3} codons counted" in result.stderr
    assert "pseudo=1 partial=1 length_not_multiple_of_3=1 non_ACGT=1" in result.stderr
    for entries in rows.values():
        assert all(0 <= fraction <= 1 for _, fraction in entries)
        assert sum(fraction for _, fraction in entries) == pytest.approx(
            1 if any(fraction for _, fraction in entries) else 0, abs=0.03,
        )
    if scenario == "sparse":
        assert flat["ATG"] == flat["TAA"] == 1
        assert sum(flat.values()) == 2
        assert '["GCT", 0.00]' in text
    if scenario == "known":
        assert flat["GCT"] == 0.67
        assert flat["GCC"] == 0.33
        assert rows["L"][:2] == [["CTG", 0.5], ["CTA", 0.5]]
    if scenario == "filtered":
        assert set(flat.values()) == {0}
    repeated = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
    assert repeated.returncode == 0, repeated.stderr
    assert output.read_text(encoding="utf-8") == text


@pytest.mark.parametrize("sequence", ["ATGTAA", "ATN", "all"])
@pytest.mark.parametrize("consumer", ["registry", "best", "closest", "pool", "fraction"])
def test_registry_consumers_reject_unobserved_usage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sequence: str, consumer: str,
) -> None:
    source = tmp_path / "input.fna"
    dna = "".join("".join(c) for c in itertools.product("ACGT", repeat=3)) if sequence == "all" else sequence
    source.write_text(f">synthetic\n{dna}\n", encoding="utf-8")
    output = tmp_path / "synthetic.json"
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/build_codon_table.py"), str(source),
         "--name", "Synthetic", "--taxid", "1", "--transl-table", "11",
         "--assembly", "synthetic", "--strain", "test", "--source", "test",
         "--source-release", "test", "--out", str(output)],
        capture_output=True, text=True, timeout=10, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert sum(map(len, json.loads(output.read_text())["codons"].values())) == 64
    monkeypatch.setattr(codon_table, "_RESOURCES_DIR", tmp_path)
    monkeypatch.setattr(codon_table, "_registry", codon_table.CodonTableRegistry())
    calls = {
        "registry": lambda: codon_table.get_codon_table("synthetic"),
        "best": lambda: codon_table.best_codon("A", "synthetic"),
        "closest": lambda: codon_table.closest_codon("ATG", "A", "synthetic"),
        "pool": lambda: codon_table.mt_codons_for_design("ATG", "A", organism="synthetic"),
        "fraction": lambda: codon_table.codon_usage_fraction("GCA", "synthetic"),
    }
    if sequence == "all":
        assert calls[consumer]()
        assert codon_table.best_codon("A", "synthetic") == "GCA"
        assert codon_table.codon_usage_fraction("GCA", "synthetic") == 0.25
    else:
        for _ in range(2):
            with pytest.raises(ValueError, match="unavailable.*A"):
                observed = calls[consumer]()
                print(f"unsafe {consumer}: {observed}")
