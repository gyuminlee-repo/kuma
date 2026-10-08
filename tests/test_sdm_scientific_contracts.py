from pathlib import Path

from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqFeature import FeatureLocation, SeqFeature
from Bio.SeqRecord import SeqRecord

from kuma_core.kuro.mutation import Mutation, mutate_sequence
from kuma_core.kuro.polymerase import PolymeraseRegistry
from kuma_core.kuro.sdm_engine import (
    _design_full_overlap,
    design_single_sdm,
    diagnose_sdm_failure,
    load_sequence,
)


def test_full_overlap_reports_offtarget_failure() -> None:
    sequence = "ATG" + "GCT" * 100
    mutation = Mutation(
        raw="A31V", wt_aa="A", position=31, mt_aa="V",
        codon_start=90, wt_codon="GCT", mt_codon="GTT",
    )
    profile = PolymeraseRegistry().get("Q5")
    probe = _design_full_overlap(
        mutate_sequence(sequence, mutation), 90, "GTT", 62.0, 4.0,
        fwd_len_min=20, fwd_len_max=39, rev_len_min=20, rev_len_max=39,
    )
    assert probe is not None
    print("length-valid primer Tm", probe[2])
    assert 58.0 <= probe[2] <= 66.0
    results = design_single_sdm(
        sequence, mutation, profile, overlap_mode="full",
        fwd_len_min=20, fwd_len_max=39, rev_len_min=20, rev_len_max=39,
    )
    assert results == []
    reason = diagnose_sdm_failure(
        sequence, mutation, profile, overlap_mode="full",
        fwd_len_min=20, fwd_len_max=39, rev_len_min=20, rev_len_max=39,
    )
    print("diagnostic", reason)
    assert "off-target" in reason


def test_all_genes_belong_to_returned_template(tmp_path: Path) -> None:
    records: list[SeqRecord] = []
    for name, dna in [("FIRST", "ATGAAATAA"), ("SECOND", "ATGCCCTAA")]:
        record = SeqRecord(Seq(dna), id=name, name=name)
        record.annotations["molecule_type"] = "DNA"
        record.features.append(SeqFeature(
            FeatureLocation(0, len(dna), strand=1), type="CDS",
            qualifiers={"gene": [name]},
        ))
        records.append(record)
    path = tmp_path / "multiple.gb"
    with path.open("w", encoding="utf-8") as stream:
        SeqIO.write(records, stream, "genbank")
    _, sequence, genes = load_sequence(path)
    print("returned template", sequence)
    for gene in genes:
        actual = str(Seq(sequence[gene.cds_start:gene.cds_end]).translate(to_stop=True))
        print(gene.gene, "advertised", gene.translation, "template translation", actual)
        assert actual == gene.translation
