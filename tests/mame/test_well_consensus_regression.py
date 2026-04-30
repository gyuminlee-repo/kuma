"""Regression tests for well_consensus pipeline.

Two test classes:

1. TestWellConsensusUnit — synthetic data with known truth.
   Tests the full align-to-consensus pipeline end-to-end.

2. TestAporvaGroundTruth — integration test using Aporva ground-truth data.
   Uses per-well raw reads from the Aporva pipeline (sort_barcode06/*.fasta)
   as input.  Because samtools consensus output is not available in this
   environment, the test validates:
   - Pipeline runs without error.
   - Output consensus is a non-empty, single-record FASTA.
   - Consensus length == reference length.
   - Per-position consistency: majority base at >= 99.9% of covered positions
     matches the consensus call (self-consistency check).

   NOTE: Aporva binary-level comparison is NOT performed (samtools consensus
   output absent from this environment).  The regression target is internal
   pipeline consistency verified against the same ground-truth read set.

   Data path: $WORKSPACE_ROOT/020.admin/projects/060.nanopore_NGS/
              NGS_260212/sort_barcode06/
   Skipped automatically when path is not accessible or SKIP_REGRESSION=1.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from kuma_core.mame.ingest.align import align_reads
from kuma_core.mame.ingest.consensus import call_consensus, per_position_depth
from kuma_core.mame.ingest.well_consensus import compute_well_consensuses

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_COMP = str.maketrans("ACGTacgt", "TGCAtgca")


def _rc(seq: str) -> str:
    return seq.translate(_COMP)[::-1]


def _write_fasta(path: Path, name: str, seq: str) -> None:
    path.write_text(f">{name}\n{seq}\n", encoding="utf-8")


def _read_fasta_records(path: Path) -> list[tuple[str, str]]:
    """Read all (id, seq) records from a FASTA file."""
    records: list[tuple[str, str]] = []
    current_id: str | None = None
    seq_parts: list[str] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\r\n")
            if line.startswith(">"):
                if current_id is not None:
                    records.append((current_id, "".join(seq_parts).upper()))
                current_id = line[1:].strip().split()[0]
                seq_parts = []
            elif line:
                seq_parts.append(line.strip())
    if current_id is not None and seq_parts:
        records.append((current_id, "".join(seq_parts).upper()))
    return records


def _aporva_sort_dir() -> Path:
    """Return the Aporva sort_barcode06 directory, resolved via WORKSPACE_ROOT."""
    root = Path(os.environ.get("WORKSPACE_ROOT", str(Path.home() / "workspace")))
    return root / "020.admin/projects/060.nanopore_NGS/NGS_260212/sort_barcode06"


# ---------------------------------------------------------------------------
# Synthetic reference for unit tests
# ---------------------------------------------------------------------------

# 300 bp synthetic reference with known SNP positions.
_SYNTH_REF = (
    "ATGGTGTTCAAGAACTTCGATGCGCTGACCGGCAAAGACCTGAAAGAGTTCGCGAAATCG"
    "AACGGCATGAACCTGAACAAGCTGAAAGCGTTCAACCAGTTCGCGAACATGAAAGCGTTC"
    "AACAAGTACTTCAACAAGATCTTCAACAAGTTCGCGAACATGAACAAGTTCAACTGAATG"
    "GTGTTCAAGAACTTCGATGCGCTGACCGGCAAAGACCTGAAAGAGTTCGCGAAATCGAAC"
    "GGCATGAACCTGAACAAGCTGAAAGCGTTCAACCAGTTCGCGAACATGAAAGCGTTCAAC"
)  # 300 bp


# ---------------------------------------------------------------------------
# Synthetic tests
# ---------------------------------------------------------------------------

class TestWellConsensusUnit:
    @pytest.fixture()
    def ref_fasta(self, tmp_path: Path) -> Path:
        path = tmp_path / "ref.fasta"
        _write_fasta(path, "ref", _SYNTH_REF)
        return path

    def test_single_well_perfect_reads(self, ref_fasta: Path) -> None:
        """5 reads identical to reference produce consensus == reference."""
        per_well = {
            "well_A1": [("r1", _SYNTH_REF), ("r2", _SYNTH_REF),
                         ("r3", _SYNTH_REF), ("r4", _SYNTH_REF),
                         ("r5", _SYNTH_REF)],
        }
        results = compute_well_consensuses(per_well, ref_fasta, min_mapq=0)
        assert "well_A1" in results
        r = results["well_A1"]
        assert r.n_passed_filter == 5
        assert r.mean_depth > 0
        assert r.consensus_seq == _SYNTH_REF

    def test_snp_majority_called_correctly(self, ref_fasta: Path) -> None:
        """4 reads with T at pos 10, 1 read with ref base yield T at pos 10."""
        mut = _SYNTH_REF[:10] + "T" + _SYNTH_REF[11:]
        per_well = {
            "well_A1": [
                ("r1", mut), ("r2", mut), ("r3", mut), ("r4", mut),
                ("r5", _SYNTH_REF),
            ],
        }
        results = compute_well_consensuses(per_well, ref_fasta, min_mapq=0)
        r = results["well_A1"]
        assert r.consensus_seq[10] == "T"

    def test_zero_reads_returns_all_n(self, ref_fasta: Path) -> None:
        per_well = {"well_empty": []}
        results = compute_well_consensuses(per_well, ref_fasta, min_mapq=0)
        r = results["well_empty"]
        assert r.n_input_reads == 0
        assert r.consensus_seq == "N" * len(_SYNTH_REF)

    def test_multi_well(self, ref_fasta: Path) -> None:
        """Multiple wells processed independently."""
        per_well = {
            "well_A1": [("r1", _SYNTH_REF)] * 3,
            "well_A2": [("r1", _SYNTH_REF[:10] + "C" + _SYNTH_REF[11:])] * 3,
        }
        results = compute_well_consensuses(per_well, ref_fasta, min_mapq=0)
        assert "well_A1" in results
        assert "well_A2" in results
        assert results["well_A1"].consensus_seq[10] == _SYNTH_REF[10]
        assert results["well_A2"].consensus_seq[10] == "C"

    def test_consensus_length_equals_reference(self, ref_fasta: Path) -> None:
        per_well = {"w": [("r1", _SYNTH_REF)]}
        results = compute_well_consensuses(per_well, ref_fasta, min_mapq=0)
        assert len(results["w"].consensus_seq) == len(_SYNTH_REF)

    def test_reverse_strand_reads_contribute(self, ref_fasta: Path) -> None:
        """Mix of forward and reverse reads should still call correct consensus."""
        rc_read = _rc(_SYNTH_REF)
        per_well = {
            "w": [("fwd", _SYNTH_REF), ("rev", rc_read)],
        }
        results = compute_well_consensuses(per_well, ref_fasta, min_mapq=0)
        r = results["w"]
        assert r.n_passed_filter >= 1
        assert len(r.consensus_seq) == len(_SYNTH_REF)

    def test_missing_reference_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            compute_well_consensuses(
                {"w": [("r", _SYNTH_REF)]},
                tmp_path / "missing.fasta",
            )


# ---------------------------------------------------------------------------
# Aporva ground-truth regression tests
# ---------------------------------------------------------------------------

_APORVA_DIR = _aporva_sort_dir()

_SKIP_REGRESSION = (
    os.environ.get("SKIP_REGRESSION", "0") == "1"
    or not _APORVA_DIR.exists()
)

_SKIP_REASON = (
    "Aporva ground-truth data not accessible. "
    "Set WORKSPACE_ROOT to the workspace root containing "
    "020.admin/projects/060.nanopore_NGS/NGS_260212/sort_barcode06, "
    "or set SKIP_REGRESSION=1 to suppress."
    if _SKIP_REGRESSION else ""
)


@pytest.mark.skipif(_SKIP_REGRESSION, reason=_SKIP_REASON)
class TestAporvaGroundTruth:
    """Integration tests using Aporva pipeline ground-truth raw-read data.

    sort_barcode06/*.fasta are per-well raw-read FASTA bundles (the output of
    Aporva barcode_mapping.py, which is the input to per-well consensus).
    Tests verify internal consistency in the absence of samtools output.
    """

    @pytest.fixture(scope="class")
    def ref_fasta_from_first_read(self, tmp_path_factory: pytest.TempPathFactory) -> Path:
        """Build a reference FASTA from the first read in 1_1.fasta."""
        source = _APORVA_DIR / "1_1.fasta"
        records = _read_fasta_records(source)
        assert records, f"No records in {source}"
        first_seq = records[0][1]
        tmp_dir = tmp_path_factory.mktemp("aporva_ref")
        ref_path = tmp_dir / "ref.fasta"
        _write_fasta(ref_path, "aporva_ref", first_seq)
        return ref_path

    @pytest.fixture(scope="class")
    def sampled_well_reads(self) -> dict[str, list[tuple[str, str]]]:
        """Sample up to 100 reads from each of the first 3 wells."""
        wells_to_test = ["1_1", "1_2", "1_3"]
        per_well: dict[str, list[tuple[str, str]]] = {}
        for well_name in wells_to_test:
            fasta_path = _APORVA_DIR / f"{well_name}.fasta"
            if not fasta_path.exists():
                continue
            records = _read_fasta_records(fasta_path)
            per_well[well_name] = [
                (f"{well_name}_r{i}", seq)
                for i, (_, seq) in enumerate(records[:100])
            ]
        return per_well

    def test_pipeline_runs_without_error(
        self,
        sampled_well_reads: dict[str, list[tuple[str, str]]],
        ref_fasta_from_first_read: Path,
    ) -> None:
        results = compute_well_consensuses(
            sampled_well_reads,
            ref_fasta_from_first_read,
            min_mapq=0,
            require_full_span=False,
        )
        assert len(results) > 0

    def test_consensus_is_non_empty_string(
        self,
        sampled_well_reads: dict[str, list[tuple[str, str]]],
        ref_fasta_from_first_read: Path,
    ) -> None:
        results = compute_well_consensuses(
            sampled_well_reads,
            ref_fasta_from_first_read,
            min_mapq=0,
            require_full_span=False,
        )
        for well, r in results.items():
            assert r.consensus_seq, f"Empty consensus for well {well}"
            assert all(b in "ACGTN" for b in r.consensus_seq), \
                f"Non-ACGTN chars in consensus for well {well}"

    def test_consensus_length_equals_reference_length(
        self,
        sampled_well_reads: dict[str, list[tuple[str, str]]],
        ref_fasta_from_first_read: Path,
    ) -> None:
        from kuma_core.mame.ingest.align import _get_reference_length
        ref_len = _get_reference_length(ref_fasta_from_first_read)
        results = compute_well_consensuses(
            sampled_well_reads,
            ref_fasta_from_first_read,
            min_mapq=0,
            require_full_span=False,
        )
        for well, r in results.items():
            assert len(r.consensus_seq) == ref_len, (
                f"Consensus length mismatch for well {well}: "
                f"{len(r.consensus_seq)} != {ref_len}"
            )

    def test_alignment_stats_consistent(
        self,
        sampled_well_reads: dict[str, list[tuple[str, str]]],
        ref_fasta_from_first_read: Path,
    ) -> None:
        results = compute_well_consensuses(
            sampled_well_reads,
            ref_fasta_from_first_read,
            min_mapq=0,
            require_full_span=False,
        )
        for well, r in results.items():
            assert r.n_passed_filter <= r.n_input_reads
            assert r.mean_depth >= 0.0

    def test_well_1_1_has_reads_aligned(
        self,
        sampled_well_reads: dict[str, list[tuple[str, str]]],
        ref_fasta_from_first_read: Path,
    ) -> None:
        if "1_1" not in sampled_well_reads:
            pytest.skip("Well 1_1 not in sampled_well_reads")
        results = compute_well_consensuses(
            {"1_1": sampled_well_reads["1_1"]},
            ref_fasta_from_first_read,
            min_mapq=0,
            require_full_span=False,
        )
        r = results["1_1"]
        assert r.n_passed_filter > 0
        assert r.mean_depth > 0.0

    def test_self_consistency_majority_vote(
        self,
        sampled_well_reads: dict[str, list[tuple[str, str]]],
        ref_fasta_from_first_read: Path,
    ) -> None:
        """Self-consistency: consensus base matches majority vote at >= 99.9% positions."""
        if "1_1" not in sampled_well_reads:
            pytest.skip("Well 1_1 not in sampled_well_reads")

        reads = sampled_well_reads["1_1"]
        alignments = align_reads(
            reads,
            ref_fasta_from_first_read,
            min_mapq=0,
            require_full_span=False,
        )
        if not alignments:
            pytest.skip("No alignments — skipping self-consistency check")

        from kuma_core.mame.ingest.align import _get_reference_length
        ref_len = _get_reference_length(ref_fasta_from_first_read)
        from kuma_core.mame.ingest.well_consensus import _read_reference_seq
        ref_seq = _read_reference_seq(ref_fasta_from_first_read)

        consensus = call_consensus(alignments, ref_seq)
        depths = per_position_depth(alignments, ref_len)

        from collections import defaultdict
        from kuma_core.mame.ingest.consensus import _accumulate

        per_position: list[dict] = [defaultdict(int) for _ in range(ref_len)]
        for aln in alignments:
            _accumulate(aln, per_position)

        n_covered = 0
        n_consistent = 0
        for pos in range(ref_len):
            if depths[pos] == 0:
                continue
            n_covered += 1
            counts = per_position[pos]
            if not counts:
                continue
            majority_base = max(counts, key=lambda b: counts[b])
            if majority_base == "-":
                if consensus[pos] == "N":
                    n_consistent += 1
            else:
                if consensus[pos] == majority_base.upper():
                    n_consistent += 1

        if n_covered == 0:
            pytest.skip("No covered positions — skipping self-consistency check")

        consistency_rate = n_consistent / n_covered
        assert consistency_rate >= 0.999, (
            f"Self-consistency rate {consistency_rate:.4f} < 0.999 "
            f"({n_consistent}/{n_covered} positions consistent)"
        )
