"""Build a deterministic public EGFP MinKNOW fixture for guide captures."""
from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

import openpyxl

from kuma_core.mame.io.variant_list import read_variant_source
from kuma_core.mame.layout import build_draft_layout


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scratch", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    samples = root / "src-tauri/samples/mame"
    reference = "".join(
        line.strip() for line in (samples / "reference.fasta").read_text().splitlines()
        if not line.startswith(">")
    )
    expected_path = samples / "03_mame_expected_mutations.xlsx"
    source = read_variant_source(expected_path)
    draft = build_draft_layout(
        source.expected, wt_ordinal=source.wt_ordinal,
        wells=source.wells, wt_well=source.wt_well,
    )
    mutations = {mutation.mutant_id: mutation for mutation in source.expected}
    barcode_sheet = openpyxl.load_workbook(
        samples / "04_mame_custom_barcodes.xlsx", data_only=True
    ).active
    if barcode_sheet is None:
        raise ValueError("04_mame_custom_barcodes.xlsx has no active sheet")
    primers = {
        str(name): str(sequence).upper()
        for name, sequence in barcode_sheet.iter_rows(min_row=2, values_only=True)
    }
    run = args.scratch / "synthetic_egfp_run"
    directory = run / "fastq_pass/barcode01"
    directory.mkdir(parents=True, exist_ok=False)
    records = []
    complement = str.maketrans("ACGT", "TGCA")
    # Like test_analyze_raw_run._build_read: forward oligo + reference
    # amplicon + reverse-complement reverse oligo, with perfect Phred-40 reads.
    with gzip.open(directory / "synthetic.fastq.gz", "wt") as stream:
        for well, sample in draft.layout.items():
            amplicon = reference
            if sample in mutations:
                mutation = mutations[sample]
                offset = (mutation.position - 1) * 3
                if reference[offset:offset + 3] != mutation.wt_codon:
                    raise ValueError(f"{sample}: reference codon at {mutation.position} is not {mutation.wt_codon}")
                amplicon = reference[:offset] + mutation.mt_codon + reference[offset + 3:]
            row = "ABCDEFGH".index(well[0]) + 1
            column = int(well[1:])
            read = primers[f"egfp_f_{column}"] + amplicon + primers[
                f"egfp_r_{row}"
            ].translate(complement)[::-1]
            for replicate in range(120):
                stream.write(
                    f"@synthetic_{well}_{sample}_{replicate}\n{read}\n+\n"
                    + "I" * len(read) + "\n"
                )
            records.append({"well": well, "sample": sample, "reads": 120})
    manifest = {
        "builder": "scripts/build_guide_synthetic_run.py",
        "reference": "src-tauri/samples/mame/reference.fasta",
        "expected": "src-tauri/samples/mame/03_mame_expected_mutations.xlsx",
        "barcodes": "src-tauri/samples/mame/04_mame_custom_barcodes.xlsx",
        "algorithm": "column-major public draft; exact mutant codon substitution; "
                     "fwd oligo + mutated CDS + reverse-complement rev oligo; Q40",
        "wells": records,
        "total_reads": len(records) * 120,
        "run_dir": str(run),
    }
    (args.scratch / "provenance.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
