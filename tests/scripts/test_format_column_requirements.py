"""The hand-written column requirements still name columns the code requires.

`src/data/formatColumnRequirements.json` is the one part of the file-shape help
nobody generates: a sequencing summary belongs to the run and a round result
workbook is assembled by the operator, so the app ships no sample of either and
there are no rows to lift. What is shown instead is the list of columns the
reader has to provide, and a list like that rots exactly the way a copied table
does. Each entry cites the source that requires it, and this test asserts every
name still appears there.

Matching on the literal is deliberately loose: it catches a renamed column,
which is the failure that would leave the operator preparing a file the reader
rejects. It does not prove the source still requires the column, which is what
the citation in the JSON is for.
"""

from __future__ import annotations

import json
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REQUIREMENTS = _REPO_ROOT / "src" / "data" / "formatColumnRequirements.json"

#: Named here rather than read from the JSON so that dropping an entry is a
#: failure and not a silent shrinking of what the test covers.
EXPECTED_IDS = {"sequencingSummary", "advisoryRoundXlsx"}


def _requirements() -> dict[str, dict[str, list[str] | str]]:
    payload = json.loads(_REQUIREMENTS.read_text(encoding="utf-8"))
    return payload["requirements"]


def test_every_required_column_appears_in_the_source_it_cites() -> None:
    requirements = _requirements()
    assert set(requirements) == EXPECTED_IDS
    checked = 0
    for entry_id, entry in requirements.items():
        source = _REPO_ROOT / str(entry["source"])
        assert source.is_file(), f"{entry_id}: {entry['source']} is gone"
        text = source.read_text(encoding="utf-8")
        columns = entry["columns"]
        assert isinstance(columns, list) and columns, f"{entry_id}: no columns"
        for column in columns:
            assert f'"{column}"' in text, (
                f"{entry_id}: column {column!r} is not named in {entry['source']}"
            )
            checked += 1
    assert checked == 6


def test_no_entry_carries_sample_values() -> None:
    """Columns only. A row here would be a measurement that came from nowhere."""
    for entry_id, entry in _requirements().items():
        assert set(entry) == {"source", "columns"}, f"{entry_id}: unexpected field"
