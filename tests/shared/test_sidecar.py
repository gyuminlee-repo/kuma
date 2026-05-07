import json

import pytest

from kuma_core.shared.sidecar import (
    append_crash_log,
    validate_dirpath,
    validate_filepath,
    validate_output_path,
)


def test_validate_filepath_accepts_existing_file(tmp_path):
    path = tmp_path / "input.fa"
    path.write_text(">x\nATGC\n", encoding="utf-8")

    assert validate_filepath(str(path), allowed_extensions={".fa"}) == path.resolve()


def test_validate_filepath_rejects_missing_file_by_default(tmp_path):
    with pytest.raises(FileNotFoundError, match="File does not exist"):
        validate_filepath(str(tmp_path / "missing.fa"))


def test_validate_filepath_can_skip_existence_check(tmp_path):
    missing = tmp_path / "missing.fa"

    assert validate_filepath(str(missing), must_exist=False) == missing.resolve()


def test_validate_dirpath_rejects_file(tmp_path):
    path = tmp_path / "not-a-dir"
    path.write_text("x", encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="Path is not a directory"):
        validate_dirpath(str(path))


def test_validate_output_path_requires_existing_parent(tmp_path):
    output = tmp_path / "missing" / "out.xlsx"

    with pytest.raises(FileNotFoundError, match="Parent directory does not exist"):
        validate_output_path(str(output), allowed_extensions={".xlsx"})


def test_append_crash_log_keeps_newest_entries(tmp_path):
    log_path = tmp_path / "sidecar" / "crash.log"

    for i in range(3):
        append_crash_log(log_path, f"method_{i}", "params", "traceback", max_entries=2)

    entries = json.loads(log_path.read_text(encoding="utf-8"))
    assert [entry["method"] for entry in entries] == ["method_1", "method_2"]
