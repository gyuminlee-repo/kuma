"""JANUS liquid handler deck policy, shared by KURO and MAME.

The instrument-native worksheet is a single sheet ("primer_mapping file") of
eight columns, transcribed from the workbook the lab imports
("Project3_seeding mapping file (JANUS).xlsx"). One row is one transfer: what is
moved, which plate it is aspirated from and at which well, which plate it is
dispensed into and at which well, and how much.

The two rack columns carry plate NAMES, not deck numbers, because the JANUS
software matches labware by name rather than by deck position. A name also
cannot collide the way numbers could, which is how the older sheet ended up
addressing a source plate and the destination with the same number.

The sheet has no liquid class column at all. ``JanusDeck.liquid_class`` is still
recorded because an operator sets it and it describes how the run was pipetted,
but nothing writes it to a file.

The values here are lab convention rather than anything this repository
measures. They used to live as literals repeated across three KURO writers and
one MAME writer, so a single edit could leave the CSV, the XLSX and the
on-screen preview describing different physical runs with nothing to catch it.
"""

from __future__ import annotations

from dataclasses import dataclass

# Instrument-native worksheet header, transcribed from the mapping sheet of
# "Project3_seeding mapping file (JANUS).xlsx". This replaces a nine column
# header transcribed from the older "Project2-2. primer dispensing (JANUS).xlsx",
# which carried a liquid class in its third column and named "Dsp. Rack" twice;
# a nine column sheet found in the wild is that older workbook, not a bug here.
# Pinned against tests/fixtures/liquid_handler/reference_format.json by
# tests/mame/test_janus_policy.py and
# tests/test_plate_mapper_reference_format.py; the literal lives in production
# code because production code must not read from tests/.
JANUS_DEVICE_HEADER: list[str] = [
    "name",
    "type",
    "no",
    "Asp. Rack",
    "Asp. Posi",
    "Dsp. Rack",
    "Dsp. Posi",
    "volume",
]


@dataclass(frozen=True)
class JanusDeck:
    """Which plate holds what, and how the robot is told to pipette it.

    Every field is a lab convention. This repository holds no primary
    measurement that fixes any of these values, so they are recorded here as the
    convention the lab works to rather than as a derived result.
    """

    # Plate names as written into ``Asp. Rack`` / ``Dsp. Rack``. The columns are
    # still headed "Rack", but the instrument matches labware by name, so these
    # are the names printed on the plates rather than deck slot numbers. KURO
    # takes them from the layout sheet of the workbook it exports; MAME generates
    # them from the plates a run actually used.
    fwd_rack: str
    rev_rack: str
    dest_rack: str

    # Recorded with the run, written nowhere. The eight column sheet has no
    # liquid class column and the file format is followed exactly, so this value
    # no longer reaches the instrument. It stays on the deck because MAME still
    # collects it from the operator and KURO still carries the lab standard, and
    # dropping the field would discard that record rather than relocate it.
    liquid_class: str

    # ``type`` column: labels the transferred material on the instrument sheet.
    sample_type: str


# KURO primer dispensing deck. The three plate names are the ones the lab writes
# on the layout sheet of "Project2-2. primer dispensing (JANUS).xlsx" for these
# same plates, and are already what KURO writes into the layout sheet of the
# workbook it exports, so the mapping sheet and the layout sheet finally call
# each plate by one name. The new instrument workbook has no layout sheet of its
# own, which is why these three names keep that older provenance. MAME cites the
# same convention for its cell stock pick, generating names from the plates a
# run actually used instead of fixing them here.
KURO_PRIMER_DECK = JanusDeck(
    fwd_rack="fw plate",
    rev_rack="rv plate",
    dest_rack="PCR mixture plate",
    liquid_class="Oligo 5pmol/ul",
    sample_type="primer",
)
