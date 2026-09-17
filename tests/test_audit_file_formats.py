import os
import shutil
import subprocess
from pathlib import Path

import pytest

from kuma_core.kuro.structure_file import load_structure_file
from kuma_core.shared.output_hash import write_output_checksum


def _checker_escapes_carriage_return(checker: str, tmp_path: Path) -> bool:
    """Observe what this machine's checker does with a CR in a name.

    GNU coreutils escapes "\\" and "\n" in every version the tests can meet;
    src/digest.c added '\r' to that set in 9.0. Deployed checkers therefore
    disagree, and the disagreement is observed here by running the checker,
    never by asking the product what it would write. Were the product asked,
    this test would only confirm that the product agrees with itself.
    """
    probe_dir = tmp_path / "probe"
    probe_dir.mkdir()
    probe = probe_dir / "probe\rname"
    probe.write_bytes(b"probe\n")
    observed = subprocess.run(
        [checker, "--", probe.name], cwd=probe_dir, capture_output=True, check=True
    ).stdout
    return observed.startswith(b"\\")


@pytest.mark.skipif(os.name != "posix", reason="POSIX filename contract")
@pytest.mark.parametrize("name", ["normal.csv", "space name.csv", "with\\slash.csv", "with\nnewline.csv", "with\rcarriage.csv"])
def test_checksum_matches_gnu_escaping(tmp_path: Path, name: str) -> None:
    checker = shutil.which("sha256sum")
    if checker is None:
        pytest.skip("GNU sha256sum unavailable")
    output = tmp_path / name
    output.write_bytes(b"contents\n")

    checksum = write_output_checksum(output)

    raw = checksum.read_bytes()
    reference = subprocess.run([checker, "--", name], cwd=tmp_path, capture_output=True, check=True).stdout
    # Digest equality holds in every coreutils era: strip the escape marker and
    # read the field ahead of the two-space separator on both lines.
    assert raw.lstrip(b"\\").split(b"  ", 1)[0] == reference.lstrip(b"\\").split(b"  ", 1)[0]

    # The name field is pinned to the form both eras verify: "\\" and "\n"
    # escaped, CR left literal. Built here from the parameter rather than from
    # the product, so a product that reverts to the 9.x-only form fails.
    escaped_name = name.replace("\\", "\\\\").replace("\n", "\\n")
    marker = b"\\" if escaped_name != name else b""
    digest = reference.lstrip(b"\\").split(b"  ", 1)[0]
    assert raw == marker + digest + b"  " + escaped_name.encode("utf-8") + b"\n"

    # Byte identity with the checker's own output is asserted wherever the two
    # eras agree, which is every name without a CR, plus every name at all when
    # the checker predates the 9.0 escape.
    if "\r" not in name or not _checker_escapes_carriage_return(checker, tmp_path):
        assert raw == reference

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
