"""JSON-RPC 2.0 dispatcher for EvolveProprimer sidecar.

Communicates via stdin/stdout with the Tauri host.
Protocol: one JSON object per line (newline-delimited JSON).
"""

import csv
import json
import logging
import os
import re
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

# Ensure evolveprimer package is importable
_SCRIPT_DIR = Path(__file__).parent.resolve()
_PROJECT_ROOT = _SCRIPT_DIR.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from evolveprimer.sdm_engine import (
    SdmPrimerResult,
    design_sdm_primers,
    export_results_tsv,
    load_fasta,
)
from evolveprimer.mutation import parse_mutation_notation
from evolveprimer.polymerase import PolymeraseRegistry
from evolveprimer.plate_mapper import (
    PlateMapping,
    deduplicate_reverse,
    export_plate_excel,
    generate_plate_map,
)

_poly_registry = PolymeraseRegistry()

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("sidecar")

_ALLOWED_FASTA_EXTENSIONS = {".fa", ".fasta", ".fna", ".fas", ".seq", ".dna"}
_ALLOWED_CSV_EXTENSIONS = {".csv", ".tsv", ".txt"}
_ALLOWED_TSV_EXTENSIONS = {".tsv", ".txt", ".csv"}
_ALLOWED_EXCEL_EXTENSIONS = {".xlsx"}

# --- Global state ---
_last_results: list[SdmPrimerResult] = []
_last_plate_mappings: list[PlateMapping] = []


def _send(obj: dict) -> None:
    """Write a JSON object to stdout (one line)."""
    line = json.dumps(obj, ensure_ascii=False)
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def _ok(req_id, result) -> None:
    _send({"jsonrpc": "2.0", "id": req_id, "result": result})


def _error(req_id, code: int, message: str) -> None:
    _send(
        {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}
    )


def _progress(value: int, message: str = "") -> None:
    _send(
        {
            "jsonrpc": "2.0",
            "method": "progress",
            "params": {"value": value, "message": message},
        }
    )


def _validate_filepath(
    filepath: str | None, *, allowed_extensions: set[str] | None = None
) -> Path:
    """Validate and resolve a file path."""
    if not filepath:
        raise FileNotFoundError("filepath is required")

    resolved = Path(filepath).resolve()

    if Path(filepath).is_symlink():
        raise FileNotFoundError(f"Symbolic links are not allowed: {filepath}")

    if resolved.is_dir():
        raise FileNotFoundError(f"Path is a directory, not a file: {filepath}")

    if allowed_extensions is not None:
        ext = resolved.suffix.lower()
        if ext not in allowed_extensions:
            raise ValueError(
                f"Unsupported file extension '{ext}'. Allowed: {sorted(allowed_extensions)}"
            )

    return resolved


def _validate_output_path(
    filepath: str | None, *, allowed_extensions: set[str]
) -> Path:
    """Validate an output file path (file may not exist yet)."""
    if not filepath:
        raise FileNotFoundError("filepath is required")

    resolved = Path(filepath).resolve()

    if not resolved.parent.exists():
        raise FileNotFoundError(
            f"Parent directory does not exist: {resolved.parent}"
        )

    ext = resolved.suffix.lower()
    if ext not in allowed_extensions:
        raise ValueError(
            f"Unsupported file extension '{ext}'. Allowed: {sorted(allowed_extensions)}"
        )

    return resolved


# --- RPC handlers ---


_POLYMERASE_META = {
    "Benchling": {"manufacturer": "SantaLucia 1998", "fidelity": "standard"},
    "Q5": {"manufacturer": "NEB", "fidelity": "high"},
    "Phusion": {"manufacturer": "Thermo", "fidelity": "high"},
    "Taq": {"manufacturer": "Various", "fidelity": "low"},
    "DreamTaq": {"manufacturer": "Thermo", "fidelity": "low"},
    "KOD": {"manufacturer": "Toyobo", "fidelity": "high"},
}


def handle_list_polymerases(_params: dict) -> list[dict]:
    """Return available polymerase profiles."""
    if _poly_registry is None:
        return [
            {"name": "Q5", "manufacturer": "NEB", "fidelity": "high"},
        ]

    names = _poly_registry.list_names()
    result = []
    for name in names:
        meta = _POLYMERASE_META.get(name, {"manufacturer": "", "fidelity": ""})
        result.append(
            {
                "name": name,
                "manufacturer": meta["manufacturer"],
                "fidelity": meta["fidelity"],
            }
        )
    return result


def handle_load_fasta(params: dict) -> dict:
    """Load a FASTA file and return sequence info."""
    filepath = params.get("filepath")
    resolved = _validate_filepath(filepath, allowed_extensions=_ALLOWED_FASTA_EXTENSIONS)

    if not resolved.exists():
        raise FileNotFoundError(f"File not found: {filepath}")

    header, sequence = load_fasta(resolved)

    # Find all ATG positions and estimate ORF length for each
    stop_codons = {"TAA", "TAG", "TGA"}
    atg_positions = []
    orf_lengths = []
    for i in range(len(sequence) - 2):
        if sequence[i : i + 3] == "ATG":
            atg_positions.append(i)
            # Scan downstream in-frame for first stop codon
            orf_len = 0
            for j in range(i + 3, len(sequence) - 2, 3):
                codon = sequence[j : j + 3]
                if codon in stop_codons:
                    orf_len = j - i
                    break
            else:
                orf_len = len(sequence) - i  # no stop found
            orf_lengths.append(orf_len)
            if len(atg_positions) >= 50:
                break

    return {
        "header": header,
        "seq_length": len(sequence),
        "atg_positions": atg_positions,
        "orf_lengths": orf_lengths,
    }


def handle_parse_mutations_text(params: dict) -> list[dict]:
    """Parse mutation text (one per line) and validate format."""
    text = params.get("text", "")
    if not text.strip():
        raise ValueError("No mutations provided")

    parsed = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        # Remove comments
        if line.startswith("#"):
            continue

        wt_aa, position, mt_aa = parse_mutation_notation(line)
        parsed.append(
            {
                "raw": line,
                "wt_aa": wt_aa,
                "position": position,
                "mt_aa": mt_aa,
            }
        )

    return parsed


def handle_design_sdm_primers(params: dict) -> dict:
    """Design SDM primers for a batch of mutations."""
    global _last_results, _last_plate_mappings

    fasta_path = params.get("fasta_path")
    if not fasta_path:
        raise ValueError("fasta_path is required")

    try:
        target_start = int(params.get("target_start", 0))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid target_start: {exc}") from exc

    mutations_input = params.get("mutations_csv_or_text", "")
    polymerase = params.get("polymerase", "Q5")
    overlap_len = int(params.get("overlap_len", 20))

    if not 15 <= overlap_len <= 40:
        raise ValueError(f"overlap_len must be 15-40, got {overlap_len}")

    resolved_fasta = _validate_filepath(
        fasta_path, allowed_extensions=_ALLOWED_FASTA_EXTENSIONS
    )

    # Determine if input is text or CSV path
    mutations_csv_path: Path
    temp_csv = None

    if os.path.isfile(mutations_input):
        mutations_csv_path = _validate_filepath(
            mutations_input, allowed_extensions=_ALLOWED_CSV_EXTENSIONS
        )
    else:
        # Text input: write to temp CSV
        lines = [
            l.strip()
            for l in mutations_input.strip().split("\n")
            if l.strip() and not l.strip().startswith("#")
        ]
        if not lines:
            raise ValueError("No mutations provided")

        temp_csv = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, newline=""
        )
        writer = csv.writer(temp_csv)
        writer.writerow(["mutation"])
        for line in lines:
            writer.writerow([line.strip()])
        temp_csv.close()
        mutations_csv_path = Path(temp_csv.name)

    try:
        _progress(10, "Designing SDM primers...")
        results = design_sdm_primers(
            fasta_path=resolved_fasta,
            target_start=target_start,
            mutations_csv=mutations_csv_path,
            polymerase=polymerase,
            overlap_len=overlap_len,
        )
    finally:
        if temp_csv is not None:
            os.unlink(temp_csv.name)

    _last_results = results
    _progress(80, "Generating plate map...")

    # Auto-generate plate map
    _last_plate_mappings = generate_plate_map(results, deduplicate_rev=True)

    _progress(100, "Design complete")

    total_mutations = len(
        [
            l
            for l in mutations_input.strip().split("\n")
            if l.strip() and not l.strip().startswith("#")
        ]
    ) if not os.path.isfile(mutations_input) else len(results)

    return {
        "results": [_serialize_result(r) for r in results],
        "success_count": len(results),
        "total_count": max(total_mutations, len(results)),
    }


def _serialize_result(r: SdmPrimerResult) -> dict:
    """Serialize a single SdmPrimerResult for JSON-RPC."""
    overlap_len = len(r.overlap_window.sequence)
    return {
        "mutation": r.mutation.raw,
        "codon_pos": r.mutation.codon_start,
        "forward_seq": r.forward_seq,
        "reverse_seq": r.reverse_seq,
        "fwd_len": r.fwd_len,
        "rev_len": r.rev_len,
        "overlap_len": overlap_len,
        "tm_no_fwd": round(r.tm_no_fwd, 1),
        "tm_no_rev": round(r.tm_no_rev, 1),
        "tm_overlap": round(r.tm_overlap, 1),
        "tm_condition_met": r.tm_condition_met,
        "tolerance_used": r.tolerance_used,
        "has_offtarget": r.has_offtarget,
        "penalty": round(r.penalty, 1),
        "gc_fwd": round(r.gc_fwd, 1),
        "gc_rev": round(r.gc_rev, 1),
        "wt_codon": r.mutation.wt_codon,
        "mt_codon": r.mutation.mt_codon,
        "overlap_seq": r.overlap_window.sequence,
        "warnings": r.warnings,
    }


def handle_get_plate_map(_params: dict) -> dict:
    """Return the plate map from last design."""
    if not _last_results:
        raise ValueError("No design available. Run design_sdm_primers first.")

    dedup_info = deduplicate_reverse(_last_results)
    dedup_serialized = {seq: names for seq, names in dedup_info.items()}

    return {
        "mappings": [
            {
                "well": m.well,
                "primer_name": m.primer_name,
                "sequence": m.sequence,
                "primer_type": m.primer_type,
                "mutation": m.mutation,
            }
            for m in _last_plate_mappings
        ],
        "dedup_info": dedup_serialized,
    }


def handle_export_tsv(params: dict) -> dict:
    """Export primer results to TSV."""
    if not _last_results:
        raise ValueError("No design available")

    filepath = params.get("filepath")
    resolved = _validate_output_path(
        filepath, allowed_extensions=_ALLOWED_TSV_EXTENSIONS
    )

    export_results_tsv(_last_results, resolved)
    return {"success": True, "filepath": str(resolved)}


def handle_export_excel(params: dict) -> dict:
    """Export plate map to Excel."""
    if not _last_results:
        raise ValueError("No design available")

    filepath = params.get("filepath")
    resolved = _validate_output_path(
        filepath, allowed_extensions=_ALLOWED_EXCEL_EXTENSIONS
    )

    export_plate_excel(_last_plate_mappings, resolved)
    return {"success": True, "filepath": str(resolved)}


# --- Dispatcher ---

_METHODS = {
    "list_polymerases": handle_list_polymerases,
    "load_fasta": handle_load_fasta,
    "parse_mutations_text": handle_parse_mutations_text,
    "design_sdm_primers": handle_design_sdm_primers,
    "get_plate_map": handle_get_plate_map,
    "export_tsv": handle_export_tsv,
    "export_excel": handle_export_excel,
}


def dispatch(request: dict) -> None:
    """Process a single JSON-RPC request."""
    req_id = request.get("id")
    method = request.get("method", "")
    params = request.get("params", {})

    handler = _METHODS.get(method)
    if handler is None:
        _error(req_id, -32601, f"Method not found: {method}")
        return

    try:
        result = handler(params)
        _ok(req_id, result)
    except FileNotFoundError as exc:
        _error(req_id, -32001, str(exc))
    except (KeyError, ValueError) as exc:
        _error(req_id, -32602, str(exc))
    except Exception as exc:
        logger.exception("Unhandled error in %s", method)
        _error(req_id, -32603, str(exc))


def main() -> None:
    """Main loop: read JSON-RPC requests from stdin, dispatch, respond on stdout."""
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdin.reconfigure(encoding="utf-8")

    logger.info("EvolveProprimer sidecar started (pid=%d)", os.getpid())
    _send({"jsonrpc": "2.0", "method": "ready", "params": {}})

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            _error(None, -32700, f"Parse error: {exc}")
            continue

        dispatch(request)

    logger.info("Sidecar stdin closed, exiting")


if __name__ == "__main__":
    main()
