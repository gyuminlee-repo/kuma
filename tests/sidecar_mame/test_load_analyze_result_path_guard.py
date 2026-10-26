"""``load_analyze_result`` may not turn its payload into a write primitive.

``output_path`` arrives in the payload and lands in ``state.last_output_path``.
``apply_selection_overrides`` later hands that value to
``_rewrite_result_workbook``, which saves a workbook over it. Neither RPC takes
a file argument from the operator, so before the guard those two calls together
wrote an ``.xlsx`` at any path the payload named.

The accepting cases matter as much as the rejecting ones: the restore paths in
``src/hooks/useAutosaveHydration.ts`` replay a path the original run recorded,
not one an operator just picked, so a blank value and a folder that has since
moved both have to keep working.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from sidecar_mame.core import get_state, reset_state, set_last_analyze
from sidecar_mame.handlers.load import handle_load_analyze_result


def _load(output_path: str) -> dict:
    return handle_load_analyze_result(
        {"verdicts": [], "replicates": [], "output_path": output_path}
    )


# autouse: every test in this module needs a cold ``SidecarState``, and the
# rejecting tests assert on ``last_output_path`` left over from a previous one.
# Nothing references the name on purpose; ``--setup-show`` confirms it runs for
# all six tests.
@pytest.fixture(autouse=True)
def _clean_state():
    reset_state()
    yield
    reset_state()


def test_reload_refuses_a_path_that_is_not_a_workbook(tmp_path: Path) -> None:
    """The one rule that makes the rewrite target a workbook and nothing else.

    A rewrite writes an ``.xlsx`` body, so without the extension rule the
    payload could aim that body at any existing file name.
    """
    target = tmp_path / "authorized_keys"
    target.write_text("keep me", encoding="utf-8")

    set_last_analyze([], [], "", run_meta=None)
    with pytest.raises(ValueError, match="Unsupported file extension"):
        _load(str(target))

    # The refusal happens before state is touched, so a rejected reload cannot
    # leave the sidecar pointing at the path it just refused.
    assert get_state().last_output_path == ""
    assert target.read_text(encoding="utf-8") == "keep me"


def test_reload_refuses_path_traversal(tmp_path: Path) -> None:
    sub = tmp_path / "project"
    sub.mkdir()
    with pytest.raises(FileNotFoundError, match="traversal"):
        _load(f"{sub}{os.sep}..{os.sep}escaped.xlsx")


def test_reload_refuses_a_symlinked_workbook(tmp_path: Path) -> None:
    real = tmp_path / "real.xlsx"
    real.write_bytes(b"original")
    link = tmp_path / "link.xlsx"
    try:
        link.symlink_to(real)
    except (OSError, NotImplementedError):  # pragma: no cover - Windows w/o privilege
        pytest.skip("symlinks are not available on this platform")

    with pytest.raises(FileNotFoundError, match="Symbolic links"):
        _load(str(link))


def test_reload_keeps_a_blank_output_path() -> None:
    """``injectSnapshotResultsIntoSidecar`` sends ``""`` when none was recorded.

    ``fromPortablePath(projectPath, "")`` returns ``""``, and every writer
    already reads an empty ``last_output_path`` as "nothing to rewrite". A
    rejection here would break that restore and guard nothing.
    """
    ack = _load("")
    assert ack["restored"] is True
    assert get_state().last_output_path == ""


def test_reload_accepts_a_workbook_whose_folder_has_moved(tmp_path: Path) -> None:
    """A replayed path is historical, so its parent may legitimately be gone.

    ``src/lib/mame/resultSnapshot.ts`` persists the analyze response verbatim,
    absolute ``output_path`` included, so a project opened after a move carries
    a parent that does not exist here. The restore has to survive it: the
    verdicts are the thing being recovered, and ``_rewrite_result_workbook``
    already reports a gone folder on its own.
    """
    missing = tmp_path / "moved-away" / "out.xlsx"
    assert not missing.parent.exists()

    ack = _load(str(missing))
    assert ack["restored"] is True
    # ``resolve`` because that is what the guard stores, and on macOS the
    # pytest temp root sits under a symlinked ``/var``.
    assert get_state().last_output_path == str(missing.resolve())


def test_reload_stores_the_resolved_path_analyze_would_have_stored(
    tmp_path: Path,
) -> None:
    """``handle_analyze`` stores ``str(_validate_output_path(...))``.

    A reload has to leave state in that same form, or the two ways of arriving
    at the same run disagree about what the output path is.
    """
    workbook = tmp_path / "result.xlsx"
    workbook.write_bytes(b"prior")

    _load(f"{tmp_path}{os.sep}.{os.sep}result.xlsx")
    assert get_state().last_output_path == str(workbook.resolve())
