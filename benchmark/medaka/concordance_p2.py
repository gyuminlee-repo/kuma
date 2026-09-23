"""Concordance measurement: mame vs medaka for all bc20 wells (partition p2).

NOTE: "처리할 well: undefined" was a templating failure in the orchestrator.
No partition manifest or sibling concordance_p1/p3.tsv was found in the job
directory. All 96 bc20 wells are processed as partition p2.
"""
from __future__ import annotations

import csv
import os
import subprocess
import sys
from pathlib import Path

# The original run imported kuma_core from the kuma-indel-flag branch checkout,
# which no longer exists. Default is this repository root.
sys.path.insert(0, os.environ.get("KUMA_REPO", str(Path(__file__).resolve().parents[2])))

import edlib
import numpy as np
from kuma_core.mame.ingest.align import align_reads_with_stats
from kuma_core.mame.ingest.consensus import call_consensus_with_metrics
from kuma_core.mame.ingest.well_consensus import _read_reference_seq


def _required_path(env_name: str) -> Path:
    """Read an input location from the environment instead of a hardcoded path."""
    value = os.environ.get(env_name)
    if not value:
        sys.exit(f"set {env_name} (see benchmark/medaka/README.md)")
    return Path(value)


REF_FASTA = _required_path("MEDAKA_BENCH_REF_FASTA")
DEMUX_BC20 = _required_path("MEDAKA_BENCH_DEMUX_BC20")
WELL_SUMMARY = _required_path("MEDAKA_BENCH_WELL_SUMMARY")
OUTDIR = Path(os.environ.get("MEDAKA_BENCH_OUT", "medaka_bench_out"))
OUTDIR.mkdir(parents=True, exist_ok=True)
TMP_DIR = OUTDIR / "tmp_p2"
MEDAKA_DIR = OUTDIR / "medaka_p2"
TSV_OUT = OUTDIR / "concordance_p2.tsv"
LOG_OUT = OUTDIR / "concordance_p2_run.log"

SUBSAMPLE_CAP = 300
MIN_MAPPED = 30
_rng = np.random.default_rng(42)


def log(msg: str) -> None:
    print(msg, flush=True)
    with LOG_OUT.open("a") as f:
        f.write(msg + "\n")


def load_well_summary() -> dict[str, dict]:
    """Returns {well_name: {mapped_reads, classification, max_indel_event_fraction}}."""
    result = {}
    with WELL_SUMMARY.open() as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for row in reader:
            well = row["well"]
            result[well] = {
                "mapped_reads": int(row["mapped_reads"]),
                "classification": row["classification"],
                "max_indel_event_fraction": float(row["max_indel_event_fraction"]),
            }
    return result


def load_fasta_reads(fasta_path: Path) -> list[tuple[str, str]]:
    reads = []
    rid = None
    seq_parts: list[str] = []
    with fasta_path.open() as fh:
        for line in fh:
            line = line.rstrip()
            if line.startswith(">"):
                if rid is not None and seq_parts:
                    reads.append((rid, "".join(seq_parts)))
                rid = line[1:].split()[0]
                seq_parts = []
            else:
                seq_parts.append(line)
    if rid is not None and seq_parts:
        reads.append((rid, "".join(seq_parts)))
    return reads


def subsample(reads: list[tuple[str, str]], cap: int) -> list[tuple[str, str]]:
    if len(reads) <= cap:
        return reads
    indices = _rng.choice(len(reads), size=cap, replace=False)
    return [reads[i] for i in sorted(indices)]


def edlib_nw(query: str, ref: str) -> int:
    r = edlib.align(
        query, ref,
        mode="NW", task="distance",
        additionalEqualities=[
            ("N", "A"), ("N", "C"), ("N", "G"), ("N", "T"), ("N", "N"),
        ],
    )
    return r["editDistance"]


def write_fasta(path: Path, reads: list[tuple[str, str]]) -> None:
    with path.open("w") as fh:
        for rid, seq in reads:
            fh.write(f">{rid}\n{seq}\n")


def run_mame(well_name: str, reads: list[tuple[str, str]], ref_seq: str) -> tuple[str, float] | None:
    """Returns (consensus_seq, max_indel_event_fraction) or None."""
    sampled = subsample(reads, SUBSAMPLE_CAP)
    alignments, _ = align_reads_with_stats(
        reads=sampled,
        reference_fasta=REF_FASTA,
        preset="map-ont",
        min_mapq=25,
        require_full_span=True,
    )
    if len(alignments) < MIN_MAPPED:
        log(f"  [{well_name}] SKIP: {len(alignments)} mapped < {MIN_MAPPED}")
        return None
    cc = call_consensus_with_metrics(alignments, ref_seq, min_depth=3)
    return cc.consensus_seq, cc.max_indel_event_fraction


def run_medaka(well_name: str, reads: list[tuple[str, str]]) -> str | None:
    """Returns medaka consensus sequence or None on failure."""
    medaka_outdir = MEDAKA_DIR / well_name
    medaka_outdir.mkdir(parents=True, exist_ok=True)
    consensus_fasta = medaka_outdir / "consensus.fasta"

    tmp_fasta = TMP_DIR / f"{well_name}.fasta"
    sampled = subsample(reads, SUBSAMPLE_CAP)
    write_fasta(tmp_fasta, sampled)

    log_path = medaka_outdir / "medaka.log"
    cmd = [
        "mamba", "run", "-n", "medaka",
        "medaka_consensus",
        "-i", str(tmp_fasta),
        "-d", str(REF_FASTA),
        "-o", str(medaka_outdir),
        "-f",
        "-t", "4",
    ]
    try:
        with log_path.open("w") as logf:
            proc = subprocess.run(cmd, stdout=logf, stderr=subprocess.STDOUT, timeout=600)
        if proc.returncode != 0:
            log(f"  [{well_name}] medaka FAILED rc={proc.returncode}")
            return None
    except subprocess.TimeoutExpired:
        log(f"  [{well_name}] medaka TIMEOUT")
        return None

    if not consensus_fasta.exists():
        log(f"  [{well_name}] medaka: consensus.fasta missing")
        return None

    return _read_reference_seq(consensus_fasta)


def main() -> None:
    # clear log
    LOG_OUT.write_text("")

    log("=== concordance_p2 start ===")
    log(f"NOTE: well list was undefined; processing all bc20 wells")

    ref_seq = _read_reference_seq(REF_FASTA)
    log(f"ref len={len(ref_seq)}")

    well_summary = load_well_summary()

    # get bc20 well fasta files
    fasta_files = sorted(
        f for f in DEMUX_BC20.glob("*.fasta")
        if f.name != "consensus_all_dna.fasta"
    )
    log(f"bc20 wells: {len(fasta_files)}")

    # write TSV header
    with TSV_OUT.open("w") as tsv:
        tsv.write(
            "well\tclassification\tmapped_reads\t"
            "mame_len\tmedaka_len\t"
            "ed_mame_medaka\tmame_ed_wt\tmedaka_ed_wt\t"
            "max_indel_event_fraction\tconcordant\n"
        )

    n_processed = 0
    n_medaka_fail = 0

    for fpath in fasta_files:
        well_inner = fpath.stem  # e.g. "1_5"
        well_key = f"bc20_{well_inner}"
        log(f"\nProcessing {well_key}")

        # get metadata from well_summary
        meta = well_summary.get(well_key)
        if meta is None:
            log(f"  SKIP: {well_key} not in well_summary.tsv")
            continue

        classification = meta["classification"]
        mapped_reads = meta["mapped_reads"]
        max_indel_frac = meta["max_indel_event_fraction"]

        # load reads
        reads = load_fasta_reads(fpath)
        log(f"  {len(reads)} reads loaded, mapped_reads={mapped_reads}, class={classification}")

        # mame consensus
        mame_result = run_mame(well_inner, reads, ref_seq)
        if mame_result is None:
            log(f"  SKIP: mame failed or insufficient mapped reads")
            continue
        mame_seq, mame_max_indel = mame_result
        mame_len = len(mame_seq)
        mame_ed_wt = edlib_nw(mame_seq, ref_seq)
        log(f"  mame: len={mame_len}, max_indel_frac={mame_max_indel:.4f}, mame_ed_wt={mame_ed_wt}")

        # medaka consensus
        medaka_seq = run_medaka(well_inner, reads)
        if medaka_seq is None:
            n_medaka_fail += 1
            note = "medaka_fail"
            log(f"  medaka FAIL ({n_medaka_fail} total) - skipping well")
            continue

        medaka_len = len(medaka_seq)
        medaka_ed_wt = edlib_nw(medaka_seq, ref_seq)
        ed_mame_medaka = edlib_nw(mame_seq, medaka_seq)
        concordant = ed_mame_medaka <= 2

        log(f"  medaka: len={medaka_len}, medaka_ed_wt={medaka_ed_wt}, ed_mame_medaka={ed_mame_medaka}, concordant={concordant}")

        # append to TSV immediately (crash-safe)
        with TSV_OUT.open("a") as tsv:
            tsv.write(
                f"{well_key}\t{classification}\t{mapped_reads}\t"
                f"{mame_len}\t{medaka_len}\t"
                f"{ed_mame_medaka}\t{mame_ed_wt}\t{medaka_ed_wt}\t"
                f"{max_indel_frac:.4f}\t{concordant}\n"
            )

        n_processed += 1
        log(f"  written to TSV (n_processed={n_processed})")

    log(f"\n=== Done: n_processed={n_processed}, n_medaka_fail={n_medaka_fail} ===")
    print(f"FINAL: n_processed={n_processed}, n_medaka_fail={n_medaka_fail}")


if __name__ == "__main__":
    main()
