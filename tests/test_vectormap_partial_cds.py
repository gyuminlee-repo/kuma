"""A CDS that overlaps only part of the changed codon loses its translation.

``_fix_translations`` skipped every CDS that did not contain the whole codon,
so a secondary CDS overlapping one or two of the three bases kept a
``/translation`` qualifier stating a protein the sequence no longer encodes.
"""
from __future__ import annotations

from Bio.Seq import Seq
from Bio.SeqFeature import CompoundLocation, FeatureLocation, SeqFeature
from Bio.SeqRecord import SeqRecord

from kuma_core.kuro.mutation import Mutation
from kuma_core.kuro.vectormap import VectormapClone, build_clone_record

_MUT = Mutation(
    raw="A2E", wt_aa="A", position=2, mt_aa="E",
    codon_start=3, wt_codon="GCT", mt_codon="GAA",
)


def _base(features: list[SeqFeature]) -> SeqRecord:
    record = SeqRecord(Seq("AAAGCTAAAAAA"), id="p", name="p")
    record.annotations["molecule_type"] = "DNA"
    record.features.extend(features)
    return record


def _cds(location, translation: str) -> SeqFeature:
    return SeqFeature(
        location, type="CDS",
        qualifiers={"translation": [translation], "codon_start": ["1"]},
    )


def _translations(record) -> list[list[str] | None]:
    return [f.qualifiers.get("translation") for f in record.features if f.type == "CDS"]


def test_partial_overlap_drops_the_stale_translation() -> None:
    """[4,10) shares two bases with the codon at [3,6): LK no longer holds."""
    record = build_clone_record(
        _base([_cds(FeatureLocation(4, 10, strand=1), "LK")]),
        VectormapClone(well="A01", mutation=_MUT),
    )
    assert str(record.seq) == "AAAGAAAAAAAA"
    assert _translations(record) == [None]


def test_reverse_strand_overlap_drops_the_translation() -> None:
    record = build_clone_record(
        _base([_cds(FeatureLocation(4, 10, strand=-1), "LK")]),
        VectormapClone(well="A01", mutation=_MUT),
    )
    assert _translations(record) == [None]


def test_joined_cds_overlapping_the_codon_drops_the_translation() -> None:
    location = CompoundLocation([
        FeatureLocation(0, 2, strand=1),
        FeatureLocation(5, 11, strand=1),
    ])
    record = build_clone_record(
        _base([_cds(location, "KK")]),
        VectormapClone(well="A01", mutation=_MUT),
    )
    assert _translations(record) == [None]


def test_in_frame_containing_cds_keeps_an_updated_translation() -> None:
    record = build_clone_record(
        _base([_cds(FeatureLocation(0, 12, strand=1), "KAKK")]),
        VectormapClone(well="A01", mutation=_MUT),
    )
    assert _translations(record) == [["KEKK"]]


def test_cds_away_from_the_codon_is_untouched() -> None:
    record = build_clone_record(
        _base([_cds(FeatureLocation(6, 12, strand=1), "KK")]),
        VectormapClone(well="A01", mutation=_MUT),
    )
    assert _translations(record) == [["KK"]]
