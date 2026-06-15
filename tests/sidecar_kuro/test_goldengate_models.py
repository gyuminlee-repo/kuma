"""L2: Golden Gate (Type IIS) sidecar wire-model contract.

Asserts the additive Golden Gate fields on DesignSdmPrimersParams /
SdmPrimerResultModel keep the overlap-extension path byte-identical:
overlap result rows must OMIT the Golden Gate fields (WorkspaceModel exclude_none),
while goldengate rows carry them.
"""
from __future__ import annotations

from sidecar_kuro.models import DesignSdmPrimersParams, SdmPrimerResultModel

_OVERLAP_BASE = dict(
    mutation="Q5A", aa_position=5, codon_pos=12, forward_seq="A", reverse_seq="T",
    fwd_len=1, rev_len=1, overlap_len=18, tm_no_fwd=60.0, tm_no_rev=60.0,
    tm_overlap=42.0, tm_condition_met=True, tolerance_used=4.0, has_offtarget=False,
    penalty=0.0, gc_fwd=50.0, gc_rev=50.0, wt_codon="CAG", mt_codon="GCG", overlap_seq="ACGT",
)

_GG_FIELDS = ("overhang", "overhang_score", "overhang_position", "enzyme", "design_method", "tm_method")


def test_params_default_to_overlap():
    p = DesignSdmPrimersParams(fasta_path="x.fa")
    assert p.design_method == "overlap"
    assert p.enzyme is None


def test_params_accept_goldengate():
    p = DesignSdmPrimersParams(fasta_path="x.fa", design_method="goldengate", enzyme="BsaI")
    assert p.design_method == "goldengate"
    assert p.enzyme == "BsaI"


def test_overlap_result_omits_goldengate_fields():
    d = SdmPrimerResultModel(**_OVERLAP_BASE).to_rpc_dict()
    for f in _GG_FIELDS:
        assert f not in d, f


def test_goldengate_result_carries_fields():
    d = SdmPrimerResultModel(
        **_OVERLAP_BASE,
        overhang="ATGG", overhang_score=678, overhang_position="0",
        enzyme="BsaI", design_method="goldengate", tm_method="santalucia",
    ).to_rpc_dict()
    assert d["overhang"] == "ATGG"
    assert d["overhang_score"] == 678
    assert d["overhang_position"] == "0"
    assert d["enzyme"] == "BsaI"
    assert d["design_method"] == "goldengate"
    assert d["tm_method"] == "santalucia"


def test_serialize_goldengate_maps_into_wire_model():
    from kuma_core.kuro.goldengate import design_goldengate
    from sidecar_kuro.handlers.design import _serialize_goldengate

    # Tiny CDS M K R * with R3K; engine returns a GoldenGateResult.
    out = design_goldengate("ATGAAACGTTAA", "MKR*", ["R3K"], enzyme="BsaI")
    assert len(out) == 1
    d = _serialize_goldengate(out[0]).to_rpc_dict()
    # Shared required fields are populated...
    assert d["mutation"] == "R3K"
    assert d["forward_seq"] and d["reverse_seq"]
    assert d["fwd_len"] == len(d["forward_seq"])
    # ...and the Golden Gate provenance fields are carried.
    assert d["design_method"] == "goldengate"
    assert d["tm_method"] == "santalucia"
    assert d["enzyme"] == "BsaI"
    if out[0].status == "success":
        assert d["overhang"] and len(d["overhang"]) == 4
