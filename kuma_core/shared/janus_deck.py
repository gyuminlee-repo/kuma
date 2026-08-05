"""JANUS liquid handler deck policy, shared by KURO and MAME.

The instrument-native worksheet is a fixed 9 column layout, and the values that
fill the deck columns (which rack holds what, which liquid class the robot
pipettes with) are lab convention rather than anything this repository measures.
Both facts used to live as literals repeated across three KURO writers and one
MAME writer, so a single edit could leave the CSV, the XLSX and the on-screen
preview describing different physical runs with nothing to catch it.

Nothing here changes instrument behaviour: ``KURO_PRIMER_DECK`` carries exactly
the values KURO wrote before this module existed.
"""

from __future__ import annotations

from dataclasses import dataclass

# Instrument-native worksheet header, transcribed from the workbook the lab
# imports ("Project2-2. primer dispensing (JANUS).xlsx"). ``Dsp. Rack`` twice is
# in the source workbook, not a transcription slip, and the third column carries
# a liquid/labware class string rather than a rack number.
# Pinned against tests/fixtures/liquid_handler/reference_format.json by
# tests/mame/test_janus_device_format.py and
# tests/test_plate_mapper_reference_format.py; the literal lives in production
# code because production code must not read from tests/.
JANUS_DEVICE9_HEADER: list[str] = [
    "name",
    "type",
    "Dsp. Rack",
    "no",
    "Asp. Rack",
    "Asp. Posi",
    "Dsp. Rack",
    "Dsp. Posi",
    "volume",
]


@dataclass(frozen=True)
class JanusDeck:
    """Which rack holds what, and how the robot is told to pipette it.

    Every field is a lab convention. This repository holds no primary
    measurement that fixes any of these values, so they are recorded here as the
    convention KURO has always written rather than as a derived result.
    """

    # Rack numbers as written into ``Asp. Rack`` / ``Dsp. Rack``. Lab convention
    # for primer dispensing: the two source plates take the first rack numbers
    # in forward-then-reverse order and the destination takes the next one.
    fwd_rack: int
    rev_rack: int
    dest_rack: int

    # Written into the third column (``Dsp. Rack`` in the workbook header, which
    # in practice carries a liquid/labware class string). The liquid class drives
    # the pipetting behaviour of the robot, so this is a lab-set value, not a
    # value this repository derives from anything.
    liquid_class: str

    # ``type`` column: labels the transferred material on the instrument sheet.
    sample_type: str


# KURO primer dispensing deck. These are the values KURO wrote before this
# module existed (formerly hardcoded in ``export_janus_mapping_csv``, the XLSX
# "primer_mapping file" sheet writer, and the sidecar preview builder). Sourced
# from lab convention, not from a measurement in this repository. MAME cites the
# same convention for its cell-stock pick, deriving rack numbers from the plates
# a run actually used instead of fixing them here.
KURO_PRIMER_DECK = JanusDeck(
    fwd_rack=1,
    rev_rack=2,
    dest_rack=3,
    liquid_class="Oligo 5pmol/ul",
    sample_type="primer",
)
