import tempfile
from pathlib import Path

import pytest
from sidecar_kuro import core
from sidecar_kuro.handlers.design import handle_design_sdm_primers


def test_busy_design_leaves_no_mutation_csv() -> None:
    with tempfile.TemporaryDirectory(prefix="kuma-audit-busy-") as directory:
        previous_tempdir = tempfile.tempdir
        tempfile.tempdir = directory
        event = core._begin_design_job()
        try:
            with pytest.raises(ValueError, match="already in progress"):
                handle_design_sdm_primers({
                    "fasta_path": str(Path("fixtures/pSHCE-dmpR.gb").resolve()),
                    "mutations_csv_or_text": "A1G",
                })
            leaked = list(Path(directory).glob("*.csv"))
            print("mutation CSVs after rejected request:", len(leaked))
            assert not leaked, "Busy rejection must clean its temporary mutation CSV"
            with pytest.raises(ValueError, match="already in progress"):
                core._begin_design_job()
        finally:
            core._finish_design_job(event)
            tempfile.tempdir = previous_tempdir
