"""The conditions a MAME run was executed under, as written into the workbook.

A result workbook names plates, wells and verdicts. Until this module existed it
said nothing about what produced them: which reference the reads were graded
against, which window of it was translated, and which thresholds turned a pile
of reads into PASS or LOWDEPTH. Those live only in the session that ran the
analysis, so two workbooks from the same plate under different settings are
indistinguishable a week later, and nobody can say whether a result may be
compared with the previous round.

Nothing here is computed. ``run_analyze`` already receives every value as an
argument; this only carries them to the sheet in one piece so the writer does
not grow a parameter per threshold.

The reference is identified by the hash of the PARSED sequence, not of the file
bytes. The same molecule re-saved under another name or wrapped at a different
line width is the same reference, and a byte hash would report two comparable
runs as incomparable.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from kuma_core.mame.compare.verdict import _MIXED_CONFIDENT_DEPTH_FACTOR

#: What a threshold that is switched off is written as. An empty cell would be
#: indistinguishable from a value that failed to be recorded, which is the
#: defect this sheet exists to close.
DISABLED = "disabled"


@dataclass(frozen=True)
class AnalysisConditions:
    """Parameters one MAME analyze run was executed with."""

    reference_file: str
    reference_length: int
    reference_sha256: str
    cds_start: int
    cds_end: int
    mode: str
    ingest_mode: str
    min_read_count: int | None
    max_consensus_n_fraction: float | None
    min_file_size_kb: float
    many_cutoff: int

    @classmethod
    def build(
        cls,
        *,
        reference_path: Path,
        reference_seq: str,
        cds_start: int,
        cds_end: int,
        mode: str,
        ingest_mode: str,
        min_read_count: int | None,
        max_consensus_n_fraction: float | None,
        min_file_size_kb: float,
        many_cutoff: int,
    ) -> "AnalysisConditions":
        return cls(
            reference_file=reference_path.name,
            reference_length=len(reference_seq),
            reference_sha256=hashlib.sha256(
                reference_seq.encode("ascii", errors="replace")
            ).hexdigest(),
            cds_start=cds_start,
            cds_end=cds_end,
            mode=mode,
            ingest_mode=ingest_mode,
            min_read_count=min_read_count,
            max_consensus_n_fraction=max_consensus_n_fraction,
            min_file_size_kb=min_file_size_kb,
            many_cutoff=many_cutoff,
        )

    def rows(self) -> list[tuple[str, str]]:
        """Key/value rows for the ``__kuma_meta__`` sheet.

        Every value is a string: openpyxl round-trips a number as a number, and
        a reader comparing two workbooks cell by cell would then have to know
        which keys are numeric before it could compare them.
        """
        mixed_floor = (
            str(self.min_read_count * _MIXED_CONFIDENT_DEPTH_FACTOR)
            if self.min_read_count is not None
            else DISABLED
        )
        return [
            ("reference_file", self.reference_file),
            ("reference_length", str(self.reference_length)),
            ("reference_sha256", self.reference_sha256),
            ("coding_window", f"{self.cds_start}-{self.cds_end}"),
            ("mode", self.mode),
            ("ingest_mode", self.ingest_mode),
            (
                "min_read_count",
                DISABLED if self.min_read_count is None else str(self.min_read_count),
            ),
            (
                "max_consensus_n_fraction",
                DISABLED
                if self.max_consensus_n_fraction is None
                else str(self.max_consensus_n_fraction),
            ),
            ("min_file_size_kb", str(self.min_file_size_kb)),
            ("many_cutoff", str(self.many_cutoff)),
            # Read from the classifier rather than restated here: a second copy
            # of the factor would keep reporting the old multiple after the
            # classifier moved to a new one, which is worse than no row.
            (
                "mixed_confident_depth_factor",
                str(_MIXED_CONFIDENT_DEPTH_FACTOR),
            ),
            ("mixed_confident_read_count", mixed_floor),
        ]


__all__ = ["AnalysisConditions", "DISABLED"]
