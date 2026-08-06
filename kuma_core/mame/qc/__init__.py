"""Post-hoc quality checks that run AFTER classification, on the result set itself.

Distinct from the pre-flight guards in ``kuma_core.mame.io`` (which reject a
malformed workbook before a run starts): everything here inspects a finished
run's own verdicts for a signature no single-well check can see.
"""

from kuma_core.mame.qc.mapping_integrity import (
    MappingIntegrityReport,
    WellObservation,
    check_mapping_integrity,
    observations_from_verdicts,
)

__all__ = [
    "MappingIntegrityReport",
    "WellObservation",
    "check_mapping_integrity",
    "observations_from_verdicts",
]
