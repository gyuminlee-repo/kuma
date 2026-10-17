"""Offline synthetic contracts, not independent biological validation."""
from __future__ import annotations

from dataclasses import replace

import pytest

from kuma_core.kuro.residue_mapping import (
    AlignmentScoring, ConfidenceProvenance, LocalConfidence, PairwiseConfidence,
    PolymerRecord, ResidueId, ResidueMappingError, SiftsEvidence, SiftsResidue,
    confidence_diagnostics, map_residues, read_mmcif_polymer, sequence_sha256,
    validate_sifts_mapping,
)


def polymer(sequence: str, *, missing: tuple[int, ...] = ()) -> PolymerRecord:
    # Deliberately no arithmetic relationship between polymer and author numbers.
    ids = tuple(None if p in missing else ResidueId("2", "auth-A", 40 + p * 3)
                for p in range(1, len(sequence) + 1))
    return PolymerRecord(sequence, "synthetic complete polymer record", "frame-1", "2", "auth-A", ids)


def observations(record: PolymerRecord) -> dict[ResidueId, tuple[float, float, float]]:
    return {identity: (float(p), 0., 0.) for p, identity in enumerate(record.residues_by_position, 1)
            if identity is not None}


def provenance(record: PolymerRecord, metric: str) -> ConfidenceProvenance:
    return ConfidenceProvenance(metric, "synthetic explicit confidence field", record.frame_id,
                                sequence_sha256(record.sequence))


def test_exact_preserves_insertion_negative_author_number_model_chain() -> None:
    ids = (ResidueId("2", "chain-B", -3), ResidueId("2", "chain-B", 10),
           ResidueId("2", "chain-B", 10, "A"))
    record = PolymerRecord("ACD", "polymer-record", "frame", "2", "chain-B", ids)
    result = map_residues("ACD", record, {ids[0]: (0, 0, 0), ids[2]: (2, 0, 0)})
    assert tuple(r.residue_id for r in result.residues) == ids
    assert result.residues[1].missing_reason == "missing_ca"
    assert result.residues[1].coordinate is None
    assert result.identity_fraction == 1.0
    assert result.reference_coverage == 1.0
    assert result.coordinate_coverage == pytest.approx(2 / 3)


def test_exact_tagged_construct_keeps_polymer_offsets_separate() -> None:
    record = polymer("HHACDEKK")
    result = map_residues("ACDE", record, observations(record))
    assert [r.polymer_position for r in result.residues] == [3, 4, 5, 6]
    assert result.residues[0].residue_id == record.residues_by_position[2]


def test_truncated_polymer_preserves_reference_terminal_gaps() -> None:
    record = polymer("CDE")
    result = map_residues("ACDEF", record, observations(record))
    assert [r.polymer_position for r in result.residues] == [None, 1, 2, 3, None]
    assert [r.coordinate for r in result.residues][::4] == [None, None]
    assert result.reference_coverage == 3 / 5


def test_missing_identity_does_not_shrink_polymer_sequence() -> None:
    record = polymer("ACDE", missing=(2,))
    result = map_residues("ACDE", record, observations(record))
    assert result.residues[1].polymer_position == 2
    assert result.residues[1].missing_reason == "missing_residue_identity"
    assert result.residues[2].coordinate == (3., 0., 0.)


@pytest.mark.parametrize("allow_homolog", [False, True])
def test_ambiguous_exact_repeat_is_rejected(allow_homolog: bool) -> None:
    with pytest.raises(ResidueMappingError, match="Ambiguous repeated"):
        map_residues("AC", polymer("ACAC"), {}, allow_homolog=allow_homolog)


def test_homolog_requires_explicit_opt_in() -> None:
    with pytest.raises(ResidueMappingError, match="opt-in"):
        map_residues("ACDEFGHIK", polymer("ACDWFGHIK"), {})


def test_homolog_substitution_is_reported_without_identity_acceptance_cutoff() -> None:
    record = polymer("ACDWFGHIK")
    result = map_residues("ACDEFGHIK", record, observations(record), allow_homolog=True)
    assert result.method == "homolog_alignment"
    assert result.identity_fraction == pytest.approx(8 / 9)
    assert result.residues[3].polymer_aa == "W"
    assert result.residues[3].reference_aa == "E"
    assert result.scoring == AlignmentScoring()
    assert result.alignment_score is not None


def test_homolog_internal_gap_and_missing_ca_are_distinct() -> None:
    record = polymer("ACDEFGHIK")
    observed = observations(record)
    del observed[ResidueId("2", "auth-A", 58)]
    result = map_residues("ACDEWFGHIK", record, observed, allow_homolog=True)
    assert result.residues[4].polymer_position is None
    assert result.residues[4].coordinate is None
    assert result.residues[4].missing_reason == "alignment_gap"
    assert result.residues[6].polymer_position == 6
    assert result.residues[6].missing_reason == "missing_ca"
    assert result.residues[7].coordinate == (7., 0., 0.)


def test_homolog_equally_optimal_different_correspondences_reject() -> None:
    with pytest.raises(ResidueMappingError, match="Equally optimal"):
        map_residues("ACAAAGT", polymer("ACAAGT"), {}, allow_homolog=True)


def test_homolog_bounded_search_never_accepts_unchecked_ambiguity() -> None:
    with pytest.raises(ResidueMappingError, match="uniqueness unproven"):
        map_residues("ACAAAGT", polymer("ACAAGT"), {}, allow_homolog=True, max_optimal_alignments=1)
    with pytest.raises(ResidueMappingError, match="cell limit"):
        map_residues("ACD", polymer("ACE"), {}, allow_homolog=True, max_alignment_cells=3)


@pytest.mark.parametrize("sequence", ["", "AXD", "acD", "AC*", "A C", "ABJZ"])
def test_unknown_or_normalization_requiring_sequence_rejects(sequence: str) -> None:
    with pytest.raises(ResidueMappingError, match="unambiguous"):
        polymer(sequence)


def test_duplicate_and_cross_frame_polymer_identities_reject() -> None:
    identity = ResidueId("2", "A", 1)
    with pytest.raises(ResidueMappingError, match="Duplicate"):
        PolymerRecord("AC", "source", "frame", "2", "A", (identity, identity))
    with pytest.raises(ResidueMappingError, match="different model or chain"):
        PolymerRecord("A", "source", "frame", "1", "A", (identity,))


def test_observations_cannot_inject_another_chain_or_nonfinite_geometry() -> None:
    record = polymer("AC")
    with pytest.raises(ResidueMappingError, match="no explicit identity"):
        map_residues("AC", record, {ResidueId("2", "other", 43): (0, 0, 0)})
    for bad in (float("nan"), float("inf"), -float("inf")):
        with pytest.raises(ResidueMappingError, match="finite"):
            map_residues("AC", record, {ResidueId("2", "auth-A", 43): (bad, 0, 0)})


def sifts_input(reference: str, record: PolymerRecord) -> tuple[SiftsEvidence, list[SiftsResidue]]:
    evidence = SiftsEvidence("https://ftp.ebi.ac.uk/pub/databases/msd/sifts/xml/1abc.xml.gz",
                             "synthetic test fixture; no retrieval", "a" * 64, "P12345",
                             sequence_sha256(reference), sequence_sha256(record.sequence), record.frame_id)
    records = [SiftsResidue(i, i, identity, reference[i - 1], record.sequence[i - 1])
               for i, identity in enumerate(record.residues_by_position, 1) if identity is not None]
    return evidence, records


def test_explicit_sifts_rows_validate_substitution_and_preserve_omissions() -> None:
    record = polymer("AGT")
    evidence, rows = sifts_input("ACT", record)
    rows = rows[1:]  # No offset expansion to fill this missing SIFTS row.
    result = validate_sifts_mapping("ACT", record, observations(record), rows,
                                   reference_accession="P12345", evidence=evidence)
    assert result.residues[0].missing_reason == "missing_sifts_record"
    assert result.residues[0].coordinate is None
    assert result.residues[1].polymer_aa == "G"
    assert result.sifts_evidence == evidence
    assert result.identity_fraction == 0.5


@pytest.mark.parametrize("field,value", [
    ("frame_id", "other"), ("reference_accession", "Q99999"),
    ("reference_sha256", "b" * 64), ("polymer_sha256", "c" * 64),
    ("source_sha256", "unknown"), ("source_version", ""),
    ("source_url", "https://www.ebi.ac.uk.evil.example/sifts/data"),
    ("source_url", "https://example.com/sifts/data"),
])
def test_sifts_mismatched_or_missing_provenance_rejects(field: str, value: str) -> None:
    record = polymer("AC")
    evidence, rows = sifts_input("AC", record)
    with pytest.raises(ResidueMappingError):
        validate_sifts_mapping("AC", record, {}, rows, reference_accession="P12345",
                               evidence=replace(evidence, **{field: value}))


@pytest.mark.parametrize("change", ["duplicate", "wrong_aa", "wrong_insertion", "out_of_range", "empty"])
def test_sifts_invalid_residue_rows_reject(change: str) -> None:
    record = polymer("AC")
    evidence, rows = sifts_input("AC", record)
    if change == "duplicate":
        rows.append(rows[0])
    elif change == "wrong_aa":
        rows[0] = replace(rows[0], reference_aa="G")
    elif change == "wrong_insertion":
        rows[0] = replace(rows[0], residue_id=replace(rows[0].residue_id, insertion_code="A"))
    elif change == "out_of_range":
        rows[0] = replace(rows[0], reference_position=0)
    else:
        rows = []
    with pytest.raises(ResidueMappingError):
        validate_sifts_mapping("AC", record, {}, rows, reference_accession="P12345", evidence=evidence)


def test_confidence_absent_is_unknown_even_when_coordinates_exist() -> None:
    record = polymer("AC")
    result = confidence_diagnostics(map_residues("AC", record, observations(record)), reference_pairs=[(1, 2)])
    assert result.plddt_by_reference == (None, None)
    assert result.mean_plddt is None
    assert result.plddt_known_count == 0
    assert result.pae_by_reference_pair == ((1, 2, None),)
    assert result.interdomain_confidence == "not_assessed"


def test_high_plddt_cannot_establish_interdomain_confidence() -> None:
    record = polymer("AC")
    mapping = map_residues("AC", record, {})
    result = confidence_diagnostics(mapping, plddt=LocalConfidence((99., 99.), provenance(record, "plddt")),
                                    reference_pairs=[(1, 2)])
    assert result.mean_plddt == 99.
    assert result.pae_by_reference_pair == ((1, 2, None),)
    assert result.interdomain_confidence == "not_assessed"


def test_confidence_remaps_full_polymer_and_preserves_direction_missing_values() -> None:
    record = polymer("ACD")
    mapping = map_residues("WACDG", record, {})
    plddt = LocalConfidence((90., None, 10.), provenance(record, "plddt"))
    pae = PairwiseConfidence(((0., 1., 20.), (9., 0., None), (30., 2., 0.)), provenance(record, "pae"))
    result = confidence_diagnostics(mapping, plddt=plddt, pae=pae,
                                    reference_pairs=[(2, 4), (4, 2), (3, 4), (1, 2)])
    assert result.plddt_by_reference == (None, 90., None, 10., None)
    assert result.mean_plddt == 50.
    assert (result.plddt_known_count, result.plddt_total_count) == (2, 5)
    assert result.pae_by_reference_pair == ((2, 4, 20.), (4, 2, 30.), (3, 4, None), (1, 2, None))


@pytest.mark.parametrize("field,value", [("metric", "experimental_b_factor"), ("source", ""),
                                         ("frame_id", "other"), ("polymer_sha256", "a" * 64)])
def test_confidence_requires_explicit_matching_provenance(field: str, value: str) -> None:
    record = polymer("AC")
    plddt = LocalConfidence((90., 90.), replace(provenance(record, "plddt"), **{field: value}))
    with pytest.raises(ResidueMappingError, match="provenance"):
        confidence_diagnostics(map_residues("AC", record, {}), plddt=plddt)


@pytest.mark.parametrize("values", [(float("nan"), 90.), (-1., 90.), (101., 90.), (90.,)])
def test_invalid_confidence_values_and_lengths_reject(values: tuple[float, ...]) -> None:
    record = polymer("AC")
    with pytest.raises(ResidueMappingError):
        confidence_diagnostics(map_residues("AC", record, {}),
                               plddt=LocalConfidence(values, provenance(record, "plddt")))


def test_pae_requires_square_nonnegative_finite_matrix() -> None:
    record = polymer("AC")
    for matrix in (((0., 1.),), ((0., 1.), (-1., 0.)), ((0., 1.), (float("inf"), 0.))):
        with pytest.raises(ResidueMappingError):
            confidence_diagnostics(map_residues("AC", record, {}),
                                   pae=PairwiseConfidence(matrix, provenance(record, "pae")))


CIF_PREFIX = """data_synthetic
loop_
_struct_asym.id
_struct_asym.entity_id
A 1
B 2
#
loop_
_entity_poly_seq.entity_id
_entity_poly_seq.num
_entity_poly_seq.mon_id
1 1 ALA
1 2 CYS
1 3 ASP
1 4 GLU
2 1 TRP
#
loop_
_atom_site.label_asym_id
_atom_site.pdbx_PDB_model_num
_atom_site.label_seq_id
_atom_site.auth_asym_id
_atom_site.auth_seq_id
_atom_site.pdbx_PDB_ins_code
_atom_site.label_comp_id
_atom_site.label_atom_id
_atom_site.label_alt_id
_atom_site.Cartn_x
_atom_site.Cartn_y
_atom_site.Cartn_z
_atom_site.B_iso_or_equiv
"""
CIF_ATOMS = """A 2 1 author-B -3 ? ALA CA . 1 2 3 99
A 2 3 author-B 10 ? ASP N . 4 5 6 99
A 2 4 author-B 10 A GLU CA . 7 8 9 99
A 1 1 author-B -3 ? ALA CA . 91 92 93 99
B 2 1 other 1 ? TRP CA . 81 82 83 99
#
"""
CIF_SCHEME = """loop_
_pdbx_poly_seq_scheme.asym_id
_pdbx_poly_seq_scheme.seq_id
_pdbx_poly_seq_scheme.pdb_seq_num
_pdbx_poly_seq_scheme.pdb_strand_id
_pdbx_poly_seq_scheme.pdb_ins_code
A 1 -3 author-B .
A 2 8 author-B .
A 3 10 author-B .
A 4 10 author-B A
#
"""


def read_cif(text: str) -> tuple[PolymerRecord, dict[ResidueId, tuple[float, float, float]]]:
    return read_mmcif_polymer(text, source="synthetic mmCIF", frame_id="test-frame",
                              model_id="2", label_chain_id="A")


def test_mmcif_polymer_sequence_is_independent_of_observed_ca() -> None:
    record, observed = read_cif(CIF_PREFIX + CIF_ATOMS + CIF_SCHEME)
    assert record.sequence == "ACDE"
    assert record.label_chain_id == "A"
    assert record.chain_id == "author-B"
    assert record.model_id == "2"
    assert len(observed) == 2
    assert record.residues_by_position[1] == ResidueId("2", "author-B", 8)
    assert record.residues_by_position[2] == ResidueId("2", "author-B", 10)
    assert record.residues_by_position[3] == ResidueId("2", "author-B", 10, "A")
    result = map_residues("ACDE", record, observed)
    assert [r.coordinate for r in result.residues] == [(1., 2., 3.), None, None, (7., 8., 9.)]
    assert result.residues[1].missing_reason == "missing_ca"
    assert confidence_diagnostics(result).mean_plddt is None  # B-factor is not provenance.


def test_mmcif_no_scheme_leaves_unobserved_identity_unknown() -> None:
    record, observed = read_cif(CIF_PREFIX + CIF_ATOMS)
    assert record.sequence == "ACDE"
    assert record.residues_by_position[1] is None
    assert map_residues("ACDE", record, observed).residues[1].missing_reason == "missing_residue_identity"


def test_mmcif_scheme_original_author_numbers_do_not_replace_coordinate_numbering() -> None:
    # wwPDB auth_seq_num can differ from coordinate numbering or be unknown.
    scheme = CIF_SCHEME.replace("_pdbx_poly_seq_scheme.pdb_ins_code\n",
                                "_pdbx_poly_seq_scheme.pdb_ins_code\n_pdbx_poly_seq_scheme.auth_seq_num\n")
    for old, new in (("A 1 -3 author-B .", "A 1 -3 author-B . 101"),
                     ("A 2 8 author-B .", "A 2 8 author-B . ?"),
                     ("A 3 10 author-B .", "A 3 10 author-B . 103"),
                     ("A 4 10 author-B A", "A 4 10 author-B A 104")):
        scheme = scheme.replace(old, new)
    record, observed = read_cif(CIF_PREFIX + CIF_ATOMS + scheme)
    assert record.residues_by_position[0] == ResidueId("2", "author-B", -3)
    assert record.residues_by_position[1] == ResidueId("2", "author-B", 8)
    assert observed[ResidueId("2", "author-B", 10, "A")] == (7., 8., 9.)


def test_mmcif_chain_and_model_selection_are_explicit() -> None:
    text = CIF_PREFIX + CIF_ATOMS
    record, observed = read_mmcif_polymer(text, source="synthetic", frame_id="other-model",
                                         model_id="1", label_chain_id="A")
    assert tuple(observed.values()) == ((91., 92., 93.),)
    assert record.model_id == "1"
    with pytest.raises(ResidueMappingError, match="observed author chain"):
        read_mmcif_polymer(text, source="synthetic", frame_id="none", model_id="7", label_chain_id="A")
    with pytest.raises(ResidueMappingError, match="one polymer entity"):
        read_mmcif_polymer(text, source="synthetic", frame_id="none", model_id="2", label_chain_id="Z")


@pytest.mark.parametrize("original,replacement", [
    ("ALA CA . 1 2 3", "ALA CA A 1 2 3"),
    ("ALA CA . 1 2 3", "ALA CA . nan 2 3"),
    ("1 2 CYS", "1 2 UNK"),
    ("1 2 CYS", "1 1 CYS"),
    ("-3 ? ALA", "-3 ? GLY"),
    ("_entity_poly_seq.mon_id", "_entity_poly_seq.unsupported"),
    ("A 2 8 author-B .", "A 1 8 author-B ."),
    ("A 4 10 author-B A", "A 4 10 author-B B"),
])
def test_mmcif_unsupported_or_conflicting_inputs_fail_closed(original: str, replacement: str) -> None:
    text = CIF_PREFIX + CIF_ATOMS + CIF_SCHEME
    assert original in text
    with pytest.raises(ResidueMappingError):
        read_cif(text.replace(original, replacement))
