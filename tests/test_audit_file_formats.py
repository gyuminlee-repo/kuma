import os
import shutil
import subprocess
from pathlib import Path

import pytest

from kuma_core.kuro.structure_file import load_structure_file
from kuma_core.shared.output_hash import write_output_checksum


@pytest.mark.skipif(os.name != "posix", reason="POSIX filename contract")
@pytest.mark.parametrize("name", ["normal.csv", "space name.csv", "with\\slash.csv", "with\nnewline.csv", "with\rcarriage.csv"])
def test_checksum_matches_gnu_escaping(tmp_path: Path, name: str) -> None:
    checker = shutil.which("sha256sum")
    if checker is None:
        pytest.skip("GNU sha256sum unavailable")
    output = tmp_path / name
    output.write_bytes(b"contents\n")

    checksum = write_output_checksum(output)

    expected = subprocess.run([checker, "--", name], cwd=tmp_path, capture_output=True, check=True)
    assert checksum.read_bytes() == expected.stdout
    verified = subprocess.run([checker, "--check", checksum.name], cwd=tmp_path, capture_output=True, check=False)
    assert verified.returncode == 0, verified.stderr


@pytest.mark.parametrize("position", [0, 3, 8])
def test_mmcif_group_column_uses_header_position(tmp_path: Path, position: int) -> None:
    columns = [
        ("id", "1"), ("label_atom_id", "CA"), ("label_comp_id", "MET"),
        ("label_asym_id", "A"), ("label_seq_id", "1"),
        ("Cartn_x", "1.0"), ("Cartn_y", "2.0"), ("Cartn_z", "3.0"),
    ]
    columns.insert(position, ("group_PDB", "ATOM"))
    text = "data_audit\nloop_\n" + "\n".join("_atom_site." + key for key, _ in columns)
    text += "\n" + " ".join(value for _, value in columns) + "\n#\n"
    path = tmp_path / "model.cif"
    path.write_text(text, encoding="utf-8")

    loaded = load_structure_file(path)

    assert loaded.sequence == "M"
    assert loaded.ca_coords == [None, (1.0, 2.0, 3.0)]
