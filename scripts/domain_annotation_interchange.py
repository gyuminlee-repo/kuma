#!/usr/bin/env python3
"""Experimental local interchange; no Chainsaw execution or application state edits."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kuma_core.kuro.domain_annotation import (
    DomainAnnotationError, MAX_RESULT_BYTES, decode_domain_result, prepare_domain_input,
)
from kuma_core.kuro.prediction_bundle import PredictionBundleError, load_prediction_bundle


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("export", "inspect"))
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--model", required=True, help="Exact structure member ID from bundle inspection")
    parser.add_argument("--chain", required=True)
    parser.add_argument("--reference-file", type=Path, required=True, help="Plain uppercase protein sequence, no FASTA header")
    parser.add_argument("--output-directory", type=Path, help="New directory for input.pdb and input.manifest.json")
    parser.add_argument("--result", type=Path, help="External kuma-chainsaw-result-v1 JSON envelope")
    args = parser.parse_args(argv)
    try:
        with args.reference_file.open("rb") as stream:
            reference_raw = stream.read(16385)
        if len(reference_raw) > 16384:
            raise DomainAnnotationError("Reference file exceeds limit")
        reference = reference_raw.decode("utf-8").strip()
        context = load_prediction_bundle(args.bundle, args.model, args.chain, reference)
        if context.structure_format != "pdb":
            raise DomainAnnotationError("Interchange v1 supports ColabFold PDB only; mmCIF/AF3 is not validated")
        prepared = prepare_domain_input(context.structure_text, context.mapping.polymer, reference,
                                        source_sha256=context.structure_sha256)
        if args.operation == "export":
            if args.output_directory is None or args.result is not None:
                raise DomainAnnotationError("Export requires --output-directory and no --result")
            # Never overwrite an existing export or mix different jobs' files.
            args.output_directory.mkdir(parents=False, exist_ok=False)
            (args.output_directory / "input.pdb").write_text(prepared.normalized_pdb, encoding="utf-8", newline="\n")
            (args.output_directory / "input.manifest.json").write_text(
                json.dumps(prepared.manifest(), indent=2) + "\n", encoding="utf-8", newline="\n")
            print(json.dumps({"status": "exported_only", "binding_sha256": prepared.binding_sha256,
                              "residues": len(prepared.residues), "prediction_executed": False}))
        else:
            if args.result is None or args.output_directory is not None:
                raise DomainAnnotationError("Inspect requires --result and no --output-directory")
            with args.result.open("rb") as stream:
                raw = stream.read(MAX_RESULT_BYTES + 1)
            if len(raw) > MAX_RESULT_BYTES:
                raise DomainAnnotationError("Result exceeds size limit")
            # Re-prepare from current bundle/reference: old exports never authorize new inputs.
            annotation = decode_domain_result(raw.decode("utf-8"), prepared,
                                               current_binding_sha256=prepared.binding_sha256)
            print(json.dumps(asdict(annotation), allow_nan=False))
        return 0
    except (OSError, UnicodeError, ValueError, PredictionBundleError, DomainAnnotationError) as exc:
        print(f"Domain interchange refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
