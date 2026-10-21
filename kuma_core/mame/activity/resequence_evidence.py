"""Explicit same-clone links between independent NGS runs, never assay pooling."""

from pathlib import Path
from typing import Literal

import python_calamine
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .plate_layout_xlsx import _normalise_well
from .variant_notation import is_canonical_internal, to_evolvepro
from .verdict_ngs import parse_verdict_rows
from kuma_core.mame.export.nb_label import nb_label


class CloneEvidenceLink(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    relationship: Literal["same_clone", "measured_resequence_clone"]
    mutant_id: str = Field(min_length=1)
    original_well: str = ""
    original_plate: str = ""
    activity_well: str = ""
    resequence_well: str = Field(min_length=1)
    resequence_plate: str = Field(min_length=1)

    @model_validator(mode="after")
    def require_measurement_source(self) -> "CloneEvidenceLink":
        if self.relationship == "same_clone" and not (self.original_well and self.original_plate):
            raise ValueError("Same-clone evidence requires the original well and plate")
        if self.relationship == "measured_resequence_clone" and not self.activity_well:
            raise ValueError("Measured resequencing clones require an explicit activity well")
        return self


class ResequenceEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    original_verdict_xlsx: str
    verdict_xlsx: str
    links: list[CloneEvidenceLink] = Field(min_length=1)


def _copy_verdict(workbook: python_calamine.CalamineWorkbook, plate: str, well: str) -> str:
    """Read the explicitly named physical copy, including a failed final pick."""
    sheet = nb_label(plate)
    if sheet not in workbook.sheet_names:
        raise ValueError(f"Resequencing mapping names unknown plate {plate!r}")
    rows = workbook.get_sheet_by_name(sheet).to_python()
    header = [str(cell).strip().lower() for cell in rows[0]]
    if "well_id" not in header or "verdict" not in header:
        raise ValueError(f"Plate {plate!r} has no well/verdict evidence")
    wi, vi = header.index("well_id"), header.index("verdict")
    matches = {
        str(row[vi]).strip().upper()
        for row in rows[1:]
        if len(row) > max(wi, vi) and str(row[wi]).strip()
        and _normalise_well(str(row[wi])) == well
    }
    if len(matches) != 1:
        raise ValueError(f"Plate {plate!r}, well {well!r} has missing or conflicting evidence")
    return matches.pop()


def validate_resequence_links(evidence: ResequenceEvidence, original_path: str | Path) -> dict[str, str]:
    """Return variant -> activity well after validating every explicit link.

    Only uncertain original sequence calls can be rescued. A contradictory
    original sequence is never replaced just because a later run says PASS.
    """
    original = Path(original_path).resolve()
    repeated = Path(evidence.verdict_xlsx).resolve()
    if original != Path(evidence.original_verdict_xlsx).resolve() or original == repeated:
        raise ValueError("Resequencing evidence belongs to a different original run")
    books = [python_calamine.CalamineWorkbook.from_path(str(path)) for path in (original, repeated)]
    metadata = []
    for book in books:
        if "__kuma_meta__" not in book.sheet_names:
            raise ValueError("Resequencing requires recorded reference and coding-window provenance")
        metadata.append({str(row[0]): str(row[1]) for row in book.get_sheet_by_name("__kuma_meta__").to_python() if len(row) >= 2})
    for key in ("reference_sha256", "coding_window", "mode"):
        if not metadata[0].get(key) or metadata[0][key] != metadata[1].get(key):
            raise ValueError(f"Incompatible resequencing provenance: {key}")
    originals, repeats = parse_verdict_rows(original), parse_verdict_rows(repeated)
    mapped: dict[str, str] = {}
    used_sources: set[tuple[str, str]] = set()
    used_activity_wells: set[str] = set()
    for link in evidence.links:
        source_well = _normalise_well(
            link.original_well if link.relationship == "same_clone" else link.activity_well
        )
        repeat_well = _normalise_well(link.resequence_well)
        source, repeat = originals.get(source_well), repeats.get(repeat_well)
        if not is_canonical_internal(link.mutant_id):
            raise ValueError("Resequencing requires a full canonical mutant identity")
        if repeat is None or repeat.mutant_id != link.mutant_id:
            raise ValueError(f"Incompatible resequencing mutant identity: {link.mutant_id}")
        variant = to_evolvepro(link.mutant_id)
        repeat_key = (nb_label(link.resequence_plate), repeat_well)
        if variant in mapped or repeat_key in used_sources or source_well in used_activity_wells:
            raise ValueError("Duplicate clone mapping across resequencing runs")
        if link.relationship == "same_clone":
            if source is None or source.mutant_id != link.mutant_id:
                raise ValueError(f"Incompatible original clone identity: {link.mutant_id}")
            source_call = _copy_verdict(books[0], link.original_plate, source_well)
            if source.verdict == "CONFLICT" or source_call not in {"PASS", "LOWDEPTH", "NO_CALL", "AMBIGUOUS"}:
                raise ValueError(f"Contradictory original clone evidence: {link.mutant_id}")
            if source.selected_plate not in {"", "FAILED", nb_label(link.original_plate)}:
                raise ValueError("Activity clone differs from the original selected plate")
        repeat_call = _copy_verdict(books[1], link.resequence_plate, repeat_well)
        if repeat.verdict != "PASS" or repeat.failed or repeat.is_fallback or repeat.manual_confirmation or repeat_call != "PASS":
            raise ValueError(f"Resequencing requires an automatic PASS selection: {link.mutant_id}")
        if repeat.selected_plate != nb_label(link.resequence_plate):
            raise ValueError("Resequencing mapping is not the automatically selected clone")
        mapped[variant] = source_well
        used_sources.add(repeat_key)
        used_activity_wells.add(source_well)
    return mapped
