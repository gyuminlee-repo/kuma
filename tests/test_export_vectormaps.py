"""Per-clone GenBank vector maps written beside the export_all bundle.

The maps are read back with Biopython and checked against the parent vector:
same length, the mutant codon where the design put it, every original feature
still there, the topology kept, and the folder a sibling of the bundle rather
than a child of it (the bundle canary lists that folder with ``iterdir``).
"""

import hashlib
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from Bio import SeqIO

import sidecar_kuro.core as _core
from kuma_core.kuro.overlap import OverlapWindow
from kuma_core.kuro.plate_mapper import PlateMapping
from kuma_core.kuro.sdm_engine import SdmPrimerResult
from kuma_core.kuro.vectormap import (
    VectormapClone,
    padded_well,
    vectormaps_dir_for,
    write_vectormaps,
)
from sidecar_kuro.handlers.design import _build_mutation
from sidecar_kuro.handlers.export import EXPORT_ALL_FILE_SUFFIXES, handle_export_all

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PLASMID = ROOT / "src-tauri" / "samples" / "sample_plasmid.gb"  # circular, EGFP CDS 61..780
PSHCE = ROOT / "fixtures" / "pSHCE-dmpR.gb"  # dmpR CDS 1791..3482, no topology

EGFP_START = 60  # 0-based start of the EGFP CDS in sample_plasmid.gb
EGFP_MUTATIONS = ("K4A", "G5W", "T10S")


def _seq(path: Path) -> str:
    return str(SeqIO.read(path, "genbank").seq).upper()


def _clones(path: Path, target_start: int, raws, wells=("A1", "B1", "C1")):
    seq = _seq(path)
    return [
        VectormapClone(well=w, mutation=_build_mutation(raw, seq, target_start, "ecoli"))
        for w, raw in zip(wells, raws)
    ]


def _feature_keys(record) -> list[tuple]:
    return sorted(
        (f.type, int(f.location.start), int(f.location.end), f.location.strand)
        for f in record.features
    )


def test_maps_carry_the_mutation_and_keep_the_vector(tmp_path):
    parent = SeqIO.read(SAMPLE_PLASMID, "genbank")
    clones = _clones(SAMPLE_PLASMID, EGFP_START, EGFP_MUTATIONS)
    target_dir = tmp_path / "Run_20260923"
    target_dir.mkdir()
    out_dir = vectormaps_dir_for(target_dir)

    res = write_vectormaps(SAMPLE_PLASMID, clones, out_dir, target_dir.name)

    assert res["failed"] == [] and res["skipped_reason"] is None
    # (e) sibling of the bundle folder, not inside it
    assert out_dir.parent == target_dir.parent
    assert out_dir.name == "Run_20260923_vectormaps"
    assert list(target_dir.iterdir()) == []
    assert sorted(p.name for p in out_dir.iterdir()) == sorted(res["success"])
    assert res["success"][0] == "Run_20260923_A01_K4A.gb"

    for clone, name in zip(clones, res["success"]):
        rec = SeqIO.read(out_dir / name, "genbank")
        mut = clone.mutation
        cs = mut.codon_start
        # (a) length unchanged
        assert len(rec) == len(parent)
        # (b) the mutant codon where the design put it, nothing else changed
        assert str(rec.seq)[cs:cs + 3] == mut.mt_codon
        assert str(rec.seq)[:cs] == str(parent.seq)[:cs]
        assert str(rec.seq)[cs + 3:] == str(parent.seq)[cs + 3:]
        cds = next(f for f in rec.features if f.type == "CDS")
        assert str(cds.extract(rec.seq).translate())[mut.position - 1] == mut.mt_aa
        assert cds.qualifiers["translation"][0][mut.position - 1] == mut.mt_aa
        # (c) every original feature kept, plus one marker at the codon
        added = [f for f in rec.features if f.qualifiers.get("label") == [mut.raw]]
        assert len(added) == 1
        assert (int(added[0].location.start), int(added[0].location.end)) == (cs, cs + 3)
        kept = [f for f in rec.features if f is not added[0]]
        assert _feature_keys(SimpleNamespace(features=kept)) == _feature_keys(parent)
        # (d) circular topology kept, LOCUS name within 16 characters
        assert rec.annotations["topology"] == "circular"
        assert len(rec.name) <= 16


def test_linear_reference_without_translation(tmp_path):
    parent = SeqIO.read(PSHCE, "genbank")
    clones = _clones(PSHCE, 1790, ("P2A", "I3V"))
    res = write_vectormaps(PSHCE, clones, tmp_path / "x_vectormaps", "x")
    assert res["failed"] == [] and len(res["success"]) == 2
    rec = SeqIO.read(tmp_path / "x_vectormaps" / res["success"][1], "genbank")
    assert len(rec) == len(parent)
    assert str(rec.seq)[clones[1].mutation.codon_start:][:3] == clones[1].mutation.mt_codon
    assert rec.annotations.get("topology", "linear") == "linear"
    assert "translation" not in next(f for f in rec.features if f.type == "CDS").qualifiers


def test_changed_reference_is_refused(tmp_path):
    """A digest that no longer matches the file writes nothing at all."""
    ref = tmp_path / "ref.gb"
    shutil.copy(SAMPLE_PLASMID, ref)
    design_sha = hashlib.sha256(ref.read_bytes()).hexdigest()
    clones = _clones(ref, EGFP_START, EGFP_MUTATIONS)
    ref.write_bytes(ref.read_bytes().replace(b"DEFINITION", b"DEFINITION edited", 1))

    out_dir = tmp_path / "run_vectormaps"
    res = write_vectormaps(ref, clones, out_dir, "run", expected_sha256=design_sha)

    assert res["success"] == []
    assert "changed after design" in res["skipped_reason"]
    assert not out_dir.exists()


def test_one_bad_clone_does_not_stop_the_rest(tmp_path):
    good = _clones(SAMPLE_PLASMID, EGFP_START, ("K4A", "T10S"), wells=("A1", "A2"))
    seq = _seq(SAMPLE_PLASMID)
    wrong_frame = _build_mutation("K4A", seq, EGFP_START, "ecoli")
    wrong_frame.codon_start += 3  # now points at G5, whose codon is not AAG
    clones = [good[0], VectormapClone("A3", wrong_frame), good[1]]

    res = write_vectormaps(SAMPLE_PLASMID, clones, tmp_path / "v", "run")

    assert res["success"] == ["run_A01_K4A.gb", "run_A02_T10S.gb"]
    assert [f["path"] for f in res["failed"]] == ["run_A03_K4A.gb"]
    assert "design expected" in res["failed"][0]["reason"]


def test_padded_well():
    assert padded_well("A1") == "A01"
    assert padded_well("H12") == "H12"


def _result(mut) -> SdmPrimerResult:
    # Only .mutation matters to the vector maps; the primer fields are filler.
    return SdmPrimerResult(
        mutation=mut,
        forward_seq="AAATTTCCCGGG", reverse_seq="CCCGGGAAATTT",
        forward_binding="AAATTT", reverse_binding="CCCGGG",
        overlap_window=OverlapWindow(sequence="AAATTTCCC", start=0, end=9, codon_offset=3),
        tm_fwd=60.0, tm_rev=58.0, tm_overlap=55.0, tm_condition_met=True,
    )


@pytest.fixture
def _session(tmp_path):
    ref = tmp_path / "parent.gb"
    shutil.copy(SAMPLE_PLASMID, ref)
    seq = _seq(ref)
    muts = [_build_mutation(r, seq, EGFP_START, "ecoli") for r in ("K4A", "G5W")]
    with _core._state_lock:
        _core._state.template = (str(ref), seq)
        _core._state.design_provenance = {
            "fasta_path": str(ref),
            "fasta_sha256": hashlib.sha256(ref.read_bytes()).hexdigest(),
        }
        _core._state.results = [_result(m) for m in muts]
        _core._state.dedup_info = {}
        _core._state.plate_mappings = [
            PlateMapping(well=w, primer_name=f"{m.raw}_{t[0]}", sequence="ATCG",
                         primer_type=t, mutation=m.raw)
            for w, m in (("A1", muts[0]), ("B1", muts[1]))
            for t in ("forward", "reverse")
        ]
    yield ref
    with _core._state_lock:
        _core._state.template = ("", "")
        _core._state.design_provenance = None
        _core._state.results = []
        _core._state.plate_mappings = []
        _core._state.dedup_info = {}


def test_export_all_writes_the_sibling_folder_only_when_asked(tmp_path, _session):
    out = tmp_path / "out"
    base = {"output_dir": str(out), "project_name": "VM", "fwd_plate_name": "F1",
            "rev_plate_name": "R1"}

    off = handle_export_all(dict(base))
    assert "vectormaps" not in off
    assert not vectormaps_dir_for(Path(off["output_dir"])).exists()

    on = handle_export_all({**base, "vectormaps": True})
    target_dir = Path(on["output_dir"])
    vm = on["vectormaps"]
    assert vm["skipped_reason"] is None and vm["sha_checked"] is True
    assert vm["failed"] == []
    assert vm["success"] == [f"{target_dir.name}_A01_K4A.gb", f"{target_dir.name}_B01_G5W.gb"]
    assert Path(vm["output_dir"]) == target_dir.parent / f"{target_dir.name}_vectormaps"
    # The bundle folder holds files only: the canary's iterdir sees no new entry.
    assert all(p.is_file() for p in target_dir.iterdir())
    assert {p.name for p in target_dir.iterdir()} <= {
        f"{target_dir.name}_{s}" for s in EXPORT_ALL_FILE_SUFFIXES
    }


def test_export_all_refuses_a_reference_edited_after_design(tmp_path, _session):
    _session.write_bytes(_session.read_bytes() + b"\n")
    res = handle_export_all({"output_dir": str(tmp_path / "out"), "project_name": "VM",
                             "fwd_plate_name": "F1", "rev_plate_name": "R1",
                             "vectormaps": True})
    vm = res["vectormaps"]
    assert vm["success"] == [] and "changed after design" in vm["skipped_reason"]
    assert not Path(vm["output_dir"]).exists()
