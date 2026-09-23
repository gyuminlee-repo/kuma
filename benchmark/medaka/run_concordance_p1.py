"""Concordance analysis: mame vs medaka for bc20 wells (partition p1).

Assumptions:
- partition p1 = demux_bc20 (task spec says well reads path is demux_bc20)
- 47-well balanced sample described in state.json; but since well list is
  undefined (variable substitution failed), we process ALL bc20 wells in
  well_summary.tsv (95 wells with mapped_reads data)
- mame consensus is reference-pinned (always 1683 bp)
- N treated as wildcard in edlib per harness pattern
- concordant = ed_mame_medaka <= 2
"""
from __future__ import annotations

import csv
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

# The original run imported kuma_core from the kuma-indel-flag branch checkout,
# which no longer exists. Default is this repository root.
KUMA_BRANCH = Path(os.environ.get("KUMA_REPO", Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(KUMA_BRANCH))

from kuma_core.mame.ingest.align import align_reads_with_stats
from kuma_core.mame.ingest.consensus import call_consensus_with_metrics
from kuma_core.mame.ingest.well_consensus import _read_reference_seq

import edlib


def _required_path(env_name: str) -> Path:
    """Read an input location from the environment instead of a hardcoded path."""
    value = os.environ.get(env_name)
    if not value:
        sys.exit(f"set {env_name} (see benchmark/medaka/README.md)")
    return Path(value)


# --- constants ---
DEMUX_DIR = _required_path("MEDAKA_BENCH_DEMUX_BC20")
REF_FASTA = _required_path("MEDAKA_BENCH_REF_FASTA")
WELL_SUMMARY_TSV = _required_path("MEDAKA_BENCH_WELL_SUMMARY")
OUT_DIR = Path(os.environ.get("MEDAKA_BENCH_OUT", "medaka_bench_out"))
OUT_DIR.mkdir(parents=True, exist_ok=True)
TMP_DIR = OUT_DIR / "tmp_p1"
MEDAKA_DIR = OUT_DIR / "medaka_p1"
LOG_FILE = OUT_DIR / "run_concordance_p1.log"
OUT_TSV = OUT_DIR / "concordance_p1.tsv"

SUBSAMPLE_CAP = 300
MIN_MAPPED_READS = 30
MEDAKA_MODEL = "r1041_e82_400bps_sup_v5.2.0"
MEDAKA_TIMEOUT = 600  # seconds

_rng = np.random.default_rng(42)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE), mode="w"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


# --- helpers reused from harness ---

def load_fasta_reads(fasta_path: Path) -> list[tuple[str, str]]:
    reads: list[tuple[str, str]] = []
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
    """NW edit distance with N as wildcard."""
    r = edlib.align(
        query, ref,
        mode="NW", task="distance",
        additionalEqualities=[
            ("N", "A"), ("N", "C"), ("N", "G"), ("N", "T"), ("N", "N"),
        ],
    )
    return r["editDistance"]


# --- per-well mame consensus ---

def get_mame_consensus(
    well_name: str,
    reads: list[tuple[str, str]],
    ref_seq: str,
) -> tuple[str, float] | None:
    """Return (consensus_seq, max_indel_event_fraction) or None if failed."""
    sampled = subsample(reads, SUBSAMPLE_CAP)
    # write subsampled fasta to tmp
    tmp_fasta = TMP_DIR / f"{well_name}.fasta"
    with tmp_fasta.open("w") as fh:
        for rid, seq in sampled:
            fh.write(f">{rid}\n{seq}\n")

    alignments, _stats = align_reads_with_stats(
        reads=sampled,
        reference_fasta=REF_FASTA,
        preset="map-ont",
        min_mapq=25,
        require_full_span=True,
    )
    n_mapped = len(alignments)
    log.info("Well %s: %d subsampled -> %d mapped", well_name, len(sampled), n_mapped)
    if n_mapped < MIN_MAPPED_READS:
        log.warning("Well %s: %d mapped < %d threshold", well_name, n_mapped, MIN_MAPPED_READS)
        return None

    cc = call_consensus_with_metrics(alignments, ref_seq, min_depth=3)
    return cc.consensus_seq, cc.max_indel_event_fraction


# --- per-well medaka consensus ---

def get_medaka_consensus(well_name: str) -> str | None:
    """Run medaka_consensus on the subsampled fasta. Return seq or None."""
    tmp_fasta = TMP_DIR / f"{well_name}.fasta"
    if not tmp_fasta.exists():
        log.error("Medaka input fasta missing: %s", tmp_fasta)
        return None

    medaka_out = MEDAKA_DIR / well_name
    medaka_out.mkdir(parents=True, exist_ok=True)
    log_path = medaka_out / "medaka.log"

    cmd = [
        "mamba", "run", "-n", "medaka",
        "medaka_consensus",
        "-i", str(tmp_fasta),
        "-d", str(REF_FASTA),
        "-o", str(medaka_out),
        "-m", MEDAKA_MODEL,
        "-f",
    ]
    log.info("Medaka cmd: %s", " ".join(cmd))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=MEDAKA_TIMEOUT)
    except subprocess.TimeoutExpired:
        log.error("Medaka timeout for well %s", well_name)
        with log_path.open("w") as fh:
            fh.write("TIMEOUT\n")
        return None

    with log_path.open("w") as fh:
        fh.write(proc.stdout + "\n" + proc.stderr)

    if proc.returncode != 0:
        log.error("Medaka rc=%d for well %s: %s", proc.returncode, well_name, proc.stderr[-300:])
        return None

    consensus_fasta = medaka_out / "consensus.fasta"
    if not consensus_fasta.exists():
        log.error("Medaka output missing for well %s", well_name)
        return None

    medaka_seq = _read_reference_seq(consensus_fasta)
    return medaka_seq


# --- load well metadata ---

def load_well_summary() -> dict[str, dict]:
    """Load bc20 wells from well_summary.tsv. Returns {well_key -> row_dict}."""
    result = {}
    with WELL_SUMMARY_TSV.open() as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for row in reader:
            w = row["well"]
            if w.startswith("bc20_"):
                result[w] = row
    return result


# --- main ---

def main() -> None:
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    MEDAKA_DIR.mkdir(parents=True, exist_ok=True)

    log.info("=== Concordance p1 start (bc20 wells) ===")
    ref_seq = _read_reference_seq(REF_FASTA)
    log.info("Reference length: %d", len(ref_seq))

    well_meta = load_well_summary()
    log.info("bc20 wells in summary: %d", len(well_meta))

    # enumerate well fasta files
    well_fastas = sorted(
        f for f in DEMUX_DIR.glob("*.fasta")
        if f.name != "consensus_all_dna.fasta"
    )
    log.info("bc20 fasta files: %d", len(well_fastas))

    rows: list[dict] = []
    n_medaka_fail = 0
    n_processed = 0

    for fasta_path in well_fastas:
        inner_well = fasta_path.stem   # e.g. "1_5"
        well_key = f"bc20_{inner_well}"  # e.g. "bc20_1_5"

        meta = well_meta.get(well_key)
        if meta is None:
            log.warning("Well %s not in summary, skipping", well_key)
            continue

        classification = meta["classification"]
        mapped_reads = int(meta["mapped_reads"])
        max_indel_event_fraction = float(meta["max_indel_event_fraction"])

        log.info("--- Processing %s (class=%s, mapped=%d) ---",
                 well_key, classification, mapped_reads)

        reads = load_fasta_reads(fasta_path)
        if not reads:
            log.warning("No reads in %s, skipping", fasta_path)
            continue

        # mame consensus
        result = get_mame_consensus(inner_well, reads, ref_seq)
        if result is None:
            log.warning("mame consensus failed for %s, skipping", well_key)
            continue

        mame_seq, _ = result
        mame_len = len(mame_seq)

        # medaka consensus
        medaka_seq = get_medaka_consensus(inner_well)
        if medaka_seq is None:
            n_medaka_fail += 1
            rows.append({
                "well": well_key,
                "classification": classification,
                "mapped_reads": mapped_reads,
                "mame_len": mame_len,
                "medaka_len": -1,
                "ed_mame_medaka": -1,
                "mame_ed_wt": edlib_nw(mame_seq, ref_seq),
                "medaka_ed_wt": -1,
                "max_indel_event_fraction": max_indel_event_fraction,
                "concordant": False,
                "note": "medaka_fail",
            })
            n_processed += 1
            continue

        medaka_len = len(medaka_seq)
        ed_mame_medaka = edlib_nw(mame_seq, medaka_seq)
        mame_ed_wt = edlib_nw(mame_seq, ref_seq)
        medaka_ed_wt = edlib_nw(medaka_seq, ref_seq)
        concordant = ed_mame_medaka <= 2

        log.info(
            "Well %s: mame_len=%d medaka_len=%d ed_mame_medaka=%d "
            "mame_ed_wt=%d medaka_ed_wt=%d concordant=%s",
            well_key, mame_len, medaka_len, ed_mame_medaka,
            mame_ed_wt, medaka_ed_wt, concordant,
        )

        rows.append({
            "well": well_key,
            "classification": classification,
            "mapped_reads": mapped_reads,
            "mame_len": mame_len,
            "medaka_len": medaka_len,
            "ed_mame_medaka": ed_mame_medaka,
            "mame_ed_wt": mame_ed_wt,
            "medaka_ed_wt": medaka_ed_wt,
            "max_indel_event_fraction": max_indel_event_fraction,
            "concordant": concordant,
            "note": "",
        })
        n_processed += 1

    # write TSV
    fieldnames = [
        "well", "classification", "mapped_reads",
        "mame_len", "medaka_len",
        "ed_mame_medaka", "mame_ed_wt", "medaka_ed_wt",
        "max_indel_event_fraction", "concordant",
    ]
    with OUT_TSV.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, delimiter="\t",
                                extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    log.info("TSV written: %s (%d rows)", OUT_TSV, len(rows))

    # write JSON summary
    summary = {
        "partition": "p1",
        "n_processed": n_processed,
        "n_medaka_fail": n_medaka_fail,
        "n_concordant": sum(1 for r in rows if r["concordant"]),
        "wells": rows,
    }
    (OUT_DIR / "concordance_p1.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    log.info("=== Done. n_processed=%d n_medaka_fail=%d ===",
             n_processed, n_medaka_fail)

    print(f"SUMMARY n_processed={n_processed} n_medaka_fail={n_medaka_fail}")
    print(f"TSV: {OUT_TSV}")


if __name__ == "__main__":
    main()
