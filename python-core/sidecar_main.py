"""JSON-RPC 2.0 dispatcher for KURO sidecar.

Communicates via stdin/stdout with the Tauri host.
Protocol: one JSON object per line (newline-delimited JSON).
"""

import csv
import datetime
import json
import logging
import os
import threading
import traceback
from dataclasses import dataclass, field, fields as dc_fields, replace as dc_replace
import re
import sys
import tempfile
from pathlib import Path

# Ensure kuro package is importable
_SCRIPT_DIR = Path(__file__).parent.resolve()
_PROJECT_ROOT = _SCRIPT_DIR.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from kuro.sdm_engine import (
    GeneInfo,
    SdmPrimerResult,
    design_single_sdm,
    design_sdm_primers,
    evaluate_custom_primer,
    load_fasta,
    load_sequence,
)
from kuro.mutation import Mutation, parse_mutation_notation
from kuro.codon_table import CODON_TO_AA, best_codon, CodonTableRegistry
from kuro.polymerase import PolymeraseRegistry
from kuro.plate_mapper import (
    PlateMapping,
    deduplicate_reverse,
    export_plate_excel,
    export_idt_csv,
    export_twist_csv,
    generate_plate_map,
)
from kuro.evolvepro import load_evolvepro_csv

_poly_registry = PolymeraseRegistry()
_codon_registry = CodonTableRegistry()

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("sidecar")

_CRASH_LOG_MAX = 50


def _get_crash_log_path() -> Path:
    """Return the crash log path (~/.kuro/crash.log)."""
    kuro_dir = Path.home() / ".kuro"
    kuro_dir.mkdir(parents=True, exist_ok=True)
    return kuro_dir / "crash.log"


def _append_crash_log(method: str, params_summary: str, tb: str) -> None:
    """Append an error entry to the local crash log file (FIFO, max 50 entries)."""
    try:
        log_path = _get_crash_log_path()
        entry = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "method": method,
            "params": params_summary[:200],
            "traceback": tb[:2000],
        }
        # Read existing entries
        entries: list[dict] = []
        if log_path.exists():
            try:
                raw = log_path.read_text(encoding="utf-8").strip()
                if raw:
                    entries = json.loads(raw)
            except (json.JSONDecodeError, OSError):
                entries = []
        entries.append(entry)
        # FIFO: keep only the newest entries
        while len(entries) > _CRASH_LOG_MAX:
            entries.pop(0)
        log_path.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass  # crash logging itself must never raise


_ALLOWED_FASTA_EXTENSIONS = {".fa", ".fasta", ".fna", ".dna", ".gb", ".gbff", ".gbk"}
_ALLOWED_CSV_EXTENSIONS = {".csv", ".tsv", ".txt"}
_ALLOWED_EXCEL_EXTENSIONS = {".xlsx"}
_VALID_DNA_BASES = re.compile(r"^[ATGC]+$")

# Lazy SSL context (created once on first use, avoids slow startup)
_ssl_ctx = None
def _get_ssl_ctx():
    global _ssl_ctx
    if _ssl_ctx is None:
        import ssl
        _ssl_ctx = ssl.create_default_context()
    return _ssl_ctx

# --- Cancel event for long-running operations ---
_cancel_event = threading.Event()

# --- Session state ---
@dataclass
class SidecarState:
    """Mutable session state shared across RPC handlers."""
    results: list[SdmPrimerResult] = field(default_factory=list)
    candidates: dict[str, list[SdmPrimerResult]] = field(default_factory=dict)
    plate_mappings: list[PlateMapping] = field(default_factory=list)
    dedup_info: dict[str, list[str]] = field(default_factory=dict)
    template: tuple[str, str] = ("", "")  # (fasta_path, sequence)
    esm_embedding: list[list[float]] | None = None  # per-residue ESM-2 vectors

_state = SidecarState()

_SWAP_FIELDS = {
    "fwd": ["forward_seq", "forward_binding", "tm_fwd", "fwd_len", "gc_fwd"],
    "rev": ["reverse_seq", "reverse_binding", "tm_rev", "rev_len", "gc_rev"],
}


_stdout_lock = threading.Lock()


def _send(obj: dict) -> None:
    """Write a JSON object to stdout (one line). Thread-safe."""
    line = json.dumps(obj, ensure_ascii=False)
    with _stdout_lock:
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

    # Block path traversal: reject paths containing '..'
    if ".." in Path(filepath).parts:
        raise FileNotFoundError(f"Path traversal is not allowed: {filepath}")

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

    if ".." in Path(filepath).parts:
        raise FileNotFoundError(f"Path traversal is not allowed: {filepath}")

    if Path(filepath).is_symlink():
        raise FileNotFoundError(f"Symbolic links are not allowed: {filepath}")

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
    """Load a sequence file and return sequence info with gene annotations."""
    filepath = params.get("filepath")
    resolved = _validate_filepath(filepath, allowed_extensions=_ALLOWED_FASTA_EXTENSIONS)

    if not resolved.exists():
        raise FileNotFoundError(f"File not found: {filepath}")

    header, sequence, genes = load_sequence(resolved)
    _state.template = (str(resolved), sequence)
    _state.esm_embedding = None  # clear stale embedding from previous template

    return {
        "header": header,
        "seq_length": len(sequence),
        "genes": [
            {
                "gene": g.gene,
                "product": g.product,
                "cds_start": g.cds_start,
                "cds_end": g.cds_end,
                "aa_length": g.aa_length,
                "organism": g.organism,
                "translation": g.translation,
                "uniprot_accession": g.uniprot_accession,
            }
            for g in genes
        ],
    }


def handle_parse_mutations_text(params: dict) -> dict:
    """Parse mutation text (one per line) and validate format.

    Returns dict with 'parsed' list and 'errors' list for failed lines.
    """
    text = params.get("text", "")
    if not text.strip():
        raise ValueError("No mutations provided")

    parsed = []
    errors = []
    for line_num, line in enumerate(text.strip().split("\n"), 1):
        line = line.strip()
        if not line:
            continue
        # Remove comments
        if line.startswith("#"):
            continue

        try:
            wt_aa, position, mt_aa = parse_mutation_notation(line)
            parsed.append(
                {
                    "raw": line,
                    "wt_aa": wt_aa,
                    "position": position,
                    "mt_aa": mt_aa,
                }
            )
        except (ValueError, IndexError) as e:
            errors.append({"line": line_num, "raw": line, "reason": str(e)})

    return {"parsed": parsed, "errors": errors}


def handle_design_sdm_primers(params: dict) -> dict:
    """Design SDM primers for a batch of mutations."""
    # Clear previous state to free memory
    _state.results = []
    _state.candidates = {}
    _state.plate_mappings = []
    _state.dedup_info = {}

    fasta_path = params.get("fasta_path")
    if not fasta_path:
        raise ValueError("fasta_path is required")

    try:
        target_start = int(params.get("target_start", 0))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid target_start: {exc}") from exc
    if target_start < 0:
        raise ValueError(f"target_start must be non-negative, got {target_start}")

    mutations_input = params.get("mutations_csv_or_text", "")
    polymerase = params.get("polymerase", "Q5")
    overlap_len = int(params.get("overlap_len", 20))
    codon_strategy = params.get("codon_strategy", "closest")
    if codon_strategy not in ("closest", "optimal"):
        raise ValueError(f"Invalid codon_strategy: '{codon_strategy}'. Must be 'closest' or 'optimal'.")
    organism = params.get("organism", "ecoli")
    # Validate organism is known
    available_organisms = _codon_registry.list_organisms()
    if organism not in available_organisms:
        raise ValueError(f"Unknown organism: '{organism}'. Available: {', '.join(available_organisms)}")

    _raw_fwd = params.get("tm_fwd_target")
    _raw_rev = params.get("tm_rev_target")
    _raw_ov = params.get("tm_overlap_target")
    tm_fwd_target = float(_raw_fwd) if _raw_fwd else None
    tm_rev_target = float(_raw_rev) if _raw_rev else None
    tm_overlap_target = float(_raw_ov) if _raw_ov else None

    # Validate Tm ranges (20-80°C)
    for label, val in [("tm_fwd_target", tm_fwd_target), ("tm_rev_target", tm_rev_target), ("tm_overlap_target", tm_overlap_target)]:
        if val is not None and not (20 <= val <= 80):
            raise ValueError(f"{label} must be between 20 and 80°C, got {val}")

    gc_min = float(params.get("gc_min", 40))
    gc_max = float(params.get("gc_max", 60))

    fwd_len_min = int(params.get("fwd_len_min", 18))
    fwd_len_max = int(params.get("fwd_len_max", 45))
    rev_len_min = int(params.get("rev_len_min", 18))
    rev_len_max = int(params.get("rev_len_max", 30))

    # Validate primer length ranges
    for label, lo, hi in [("fwd", fwd_len_min, fwd_len_max), ("rev", rev_len_min, rev_len_max)]:
        if not (1 <= lo <= hi <= 100):
            raise ValueError(f"{label}_len_min ({lo}) must be <= {label}_len_max ({hi}), both in 1-100")

    # Validate GC% range (0-100%)
    if not (0 <= gc_min <= 100) or not (0 <= gc_max <= 100):
        raise ValueError(f"gc_min/gc_max must be between 0 and 100, got {gc_min}/{gc_max}")
    if gc_min >= gc_max:
        raise ValueError(f"gc_min ({gc_min}) must be less than gc_max ({gc_max})")

    if not 15 <= overlap_len <= 40:
        raise ValueError(f"overlap_len must be 15-40, got {overlap_len}")

    resolved_fasta = _validate_filepath(
        fasta_path, allowed_extensions=_ALLOWED_FASTA_EXTENSIONS
    )

    # Determine if input is text or CSV path
    mutations_csv_path: Path
    temp_csv = None
    temp_csv_name: str = ""
    lines: list[str] = []

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

        fd, temp_csv_name = tempfile.mkstemp(suffix=".csv")
        if hasattr(os, "fchmod"):
            os.fchmod(fd, 0o600)
        temp_csv = open(fd, mode="w", newline="")
        writer = csv.writer(temp_csv)
        writer.writerow(["mutation"])
        for line in lines:
            writer.writerow([line.strip()])
        temp_csv.close()
        mutations_csv_path = Path(temp_csv_name)

    try:
        _cancel_event.clear()

        def _on_progress(i: int, total: int, mutation_raw: str) -> None:
            pct = 10 + int(70 * i / max(total, 1))
            _progress(pct, f"Designing {mutation_raw} ({i+1}/{total})...")

        _progress(10, "Designing SDM primers...")
        results, all_cands, engine_failures = design_sdm_primers(
            fasta_path=resolved_fasta,
            target_start=target_start,
            mutations_csv=mutations_csv_path,
            polymerase=polymerase,
            overlap_len=overlap_len,
            codon_strategy=codon_strategy,
            tm_fwd_target=tm_fwd_target,
            tm_rev_target=tm_rev_target,
            tm_overlap_target=tm_overlap_target,
            gc_min=gc_min,
            gc_max=gc_max,
            fwd_len_min=fwd_len_min,
            fwd_len_max=fwd_len_max,
            rev_len_min=rev_len_min,
            rev_len_max=rev_len_max,
            on_progress=_on_progress,
            cancel_check=_cancel_event.is_set,
            organism=organism,
        )
    finally:
        if temp_csv is not None:
            os.unlink(temp_csv_name)

    if _cancel_event.is_set():
        _cancel_event.clear()
        return {"results": [], "success_count": 0, "total_count": 0,
                "failed_mutations": [], "cancelled": True}

    _state.results = results
    _state.candidates = all_cands
    _progress(80, "Generating plate map...")

    # Auto-generate plate map (Fwd/Rev separate plates)
    fwd_map, rev_map = generate_plate_map(results, deduplicate_rev=True)
    _state.plate_mappings = fwd_map + rev_map
    _state.dedup_info = deduplicate_reverse(results)

    _progress(100, "Design complete")

    # Build failure list from engine + input line tracking
    is_text_input = not os.path.isfile(mutations_input)
    input_lines = lines if is_text_input else []
    total_mutations = len(results) + len(engine_failures)
    if is_text_input:
        total_mutations = max(total_mutations, len(input_lines))

    failed: list[dict] = []
    for idx, (mut_name, reason) in enumerate(engine_failures.items()):
        # Find rank from input lines if available
        rank = next((i + 1 for i, l in enumerate(input_lines) if l == mut_name), idx + len(results) + 1)
        failed.append({"mutation": mut_name, "rank": rank, "reason": reason})

    return {
        "results": [
            _serialize_result_with_counts(r) for r in results
        ],
        "success_count": len(results),
        "total_count": total_mutations,
        "failed_mutations": failed,
    }


def _serialize_result(r: SdmPrimerResult, candidate_count: int | None = None) -> dict:
    """Serialize a single SdmPrimerResult for JSON-RPC."""
    overlap_len = len(r.overlap_window.sequence)
    result = {
        "mutation": r.mutation.raw,
        "aa_position": r.mutation.position,
        "codon_pos": r.mutation.codon_start,
        "forward_seq": r.forward_seq,
        "reverse_seq": r.reverse_seq,
        "fwd_len": r.fwd_len,
        "rev_len": r.rev_len,
        "overlap_len": overlap_len,
        "tm_no_fwd": round(r.tm_fwd, 1),
        "tm_no_rev": round(r.tm_rev, 1),
        "tm_overlap": round(r.tm_overlap, 1),
        "tm_condition_met": r.tm_condition_met,
        "tolerance_used": r.tolerance_used,
        "tolerance_fwd": round(r.tolerance_fwd, 1),
        "tolerance_rev": round(r.tolerance_rev, 1),
        "has_offtarget": r.has_offtarget,
        "offtarget_fwd": [
            {"position": h.position, "strand": h.strand, "match_seq": h.match_seq, "tm": h.tm, "match_length": h.match_length}
            for h in r.offtarget_fwd
        ],
        "offtarget_rev": [
            {"position": h.position, "strand": h.strand, "match_seq": h.match_seq, "tm": h.tm, "match_length": h.match_length}
            for h in r.offtarget_rev
        ],
        "penalty": round(r.penalty, 1),
        "gc_fwd": round(r.gc_fwd, 1),
        "gc_rev": round(r.gc_rev, 1),
        "wt_codon": r.mutation.wt_codon,
        "mt_codon": r.mutation.mt_codon,
        "overlap_seq": r.overlap_window.sequence,
        "hairpin_tm_fwd": round(r.hairpin_tm_fwd, 1),
        "hairpin_tm_rev": round(r.hairpin_tm_rev, 1),
        "homodimer_tm_fwd": round(r.homodimer_tm_fwd, 1),
        "homodimer_tm_rev": round(r.homodimer_tm_rev, 1),
        "hairpin_dg_fwd": round(r.hairpin_dg_fwd, 2),
        "hairpin_dg_rev": round(r.hairpin_dg_rev, 2),
        "homodimer_dg_fwd": round(r.homodimer_dg_fwd, 2),
        "homodimer_dg_rev": round(r.homodimer_dg_rev, 2),
        "synthesis_score_fwd": r.synthesis_score_fwd,
        "synthesis_score_rev": r.synthesis_score_rev,
        "warnings": r.warnings,
    }
    if candidate_count is not None:
        result["candidate_count"] = candidate_count
    return result


def _count_unique_fwd_rev(candidates: list[SdmPrimerResult]) -> tuple[int, int]:
    """Count unique forward and reverse sequences among candidates."""
    fwd_seqs = {c.forward_seq for c in candidates}
    rev_seqs = {c.reverse_seq for c in candidates}
    return len(fwd_seqs), len(rev_seqs)


def _serialize_result_with_counts(r: SdmPrimerResult) -> dict:
    """Serialize result with fwd/rev candidate counts."""
    cands = _state.candidates.get(r.mutation.raw, [])
    result = _serialize_result(r, len(cands))
    fwd_count, rev_count = _count_unique_fwd_rev(cands) if cands else (0, 0)
    result["candidate_fwd_count"] = fwd_count
    result["candidate_rev_count"] = rev_count
    return result


def handle_get_plate_map(_params: dict) -> dict:
    """Return the plate map from last design."""
    if not _state.results:
        raise ValueError("No design available. Run design_sdm_primers first.")

    return {
        "mappings": [
            {
                "well": m.well,
                "primer_name": m.primer_name,
                "sequence": m.sequence,
                "primer_type": m.primer_type,
                "mutation": m.mutation,
            }
            for m in _state.plate_mappings
        ],
        "dedup_info": _state.dedup_info,
    }


def handle_export_excel(params: dict) -> dict:
    """Export plate map to Excel.

    Accepts optional 'mappings' and 'dedup_info' from the frontend to reflect
    the current UI state (sorted order, custom additions from failed mutations).
    Falls back to backend state when not provided (CLI usage).
    """
    filepath = params.get("filepath")
    resolved = _validate_output_path(
        filepath, allowed_extensions=_ALLOWED_EXCEL_EXTENSIONS
    )

    mappings_data = params.get("mappings")
    dedup_data = params.get("dedup_info")

    if mappings_data:
        if not isinstance(mappings_data, list):
            raise ValueError("mappings must be a list")
        required_fields = {"well", "primer_name", "sequence", "primer_type", "mutation"}
        mappings = []
        for i, m in enumerate(mappings_data):
            if not isinstance(m, dict):
                raise ValueError(f"mappings[{i}] must be an object")
            missing = required_fields - m.keys()
            if missing:
                raise ValueError(f"mappings[{i}] missing fields: {sorted(missing)}")
            # Only pass fields that PlateMapping accepts
            valid_keys = {f.name for f in dc_fields(PlateMapping)}
            filtered = {k: v for k, v in m.items() if k in valid_keys}
            mappings.append(PlateMapping(**filtered))
        rev_groups = dedup_data or {}
    else:
        if not _state.results:
            raise ValueError("No design available")
        mappings = _state.plate_mappings
        rev_groups = _state.dedup_info

    export_plate_excel(mappings, resolved, rev_groups=rev_groups)
    return {"success": True, "filepath": str(resolved)}


def handle_load_evolvepro_csv(params: dict) -> dict:
    """Load EVOLVEpro df_test.csv, sort by y_pred descending, return top-N variants."""
    filepath = params.get("filepath", "")
    if not filepath:
        raise ValueError("filepath is required")
    resolved = _validate_filepath(filepath, allowed_extensions=_ALLOWED_CSV_EXTENSIONS)

    return load_evolvepro_csv(
        filepath=str(resolved),
        top_n=int(params.get("top_n", 96)),
        max_per_position=int(params.get("max_per_position", 0)),
        domains=params.get("domains", []),
        domain_diversity=params.get("domain_diversity", False),
        domain_strategy=params.get("domain_strategy", "proportional"),
        pareto_diversity=params.get("pareto_diversity", False),
        entropy_weight=float(params.get("entropy_weight", 0.0)),
        esm_embedding=_state.esm_embedding,
    )


def handle_get_alternatives(params: dict) -> dict:
    """Return all candidates for a specific mutation."""
    mutation = params.get("mutation", "")
    if not mutation:
        raise ValueError("mutation is required")
    candidates = _state.candidates.get(mutation, [])
    return {
        "mutation": mutation,
        "candidates": [_serialize_result(c) for c in candidates],
    }


def handle_swap_primer(params: dict) -> dict:
    """Swap the selected primer for a mutation with a different candidate."""
    mutation = params.get("mutation", "")
    candidate_idx = int(params.get("candidate_idx", 0))
    swap_type = params.get("swap_type", "both")  # "both", "fwd", "rev"

    candidates = _state.candidates.get(mutation)
    if not candidates:
        raise ValueError(f"No candidates for mutation: {mutation}")
    if candidate_idx < 0 or candidate_idx >= len(candidates):
        raise ValueError(f"Invalid candidate index: {candidate_idx}")

    source = candidates[candidate_idx]

    if swap_type == "both":
        new_best = source
    else:
        current = next((r for r in _state.results if r.mutation.raw == mutation), None)
        if not current:
            raise ValueError(f"No current result for mutation: {mutation}")
        swap_dict = {f: getattr(source, f) for f in _SWAP_FIELDS[swap_type]}
        new_best = dc_replace(current, **swap_dict)

    target_pos = new_best.mutation.position
    for i, r in enumerate(_state.results):
        if r.mutation.raw == mutation:
            _state.results[i] = new_best
        elif swap_type in ("rev", "both") and r.mutation.position == target_pos:
            # Propagate reverse to same-position mutations
            _state.results[i] = dc_replace(
                r,
                reverse_seq=new_best.reverse_seq,
                reverse_binding=new_best.reverse_binding,
                tm_rev=new_best.tm_rev,
                rev_len=new_best.rev_len,
                gc_rev=new_best.gc_rev,
            )
    return _serialize_result_with_counts(new_best)


def handle_evaluate_primer(params: dict) -> dict:
    """Evaluate a user-provided primer pair."""
    mutation = params.get("mutation", "custom")
    fasta_path = params.get("fasta_path")
    forward_seq = params.get("forward_seq", "").strip().upper()
    reverse_seq = params.get("reverse_seq", "").strip().upper()
    overlap_len = int(params.get("overlap_len", 20))

    if not fasta_path:
        raise ValueError("fasta_path is required")
    if not forward_seq or not reverse_seq:
        raise ValueError("Both forward_seq and reverse_seq are required")

    # Validate primer sequences: ATGC only, max 150bp
    for label, seq in [("forward_seq", forward_seq), ("reverse_seq", reverse_seq)]:
        if not _VALID_DNA_BASES.match(seq):
            raise ValueError(f"{label} must contain only A, T, G, C characters")
        if len(seq) > 150:
            raise ValueError(f"{label} exceeds 150bp limit (got {len(seq)}bp)")

    resolved = _validate_filepath(fasta_path, allowed_extensions=_ALLOWED_FASTA_EXTENSIONS)

    # Use cached template if same file
    cached_path, cached_seq = _state.template
    if cached_seq and cached_path == str(resolved):
        template = cached_seq
    else:
        _header, template, _genes = load_sequence(resolved)

    result = evaluate_custom_primer(
        fwd_seq=forward_seq,
        rev_seq=reverse_seq,
        template=template,
        mutation_raw=mutation,
        overlap_len=overlap_len,
    )
    return _serialize_result(result)


def handle_save_workspace(params: dict) -> dict:
    """Save workspace JSON to file."""
    filepath = params.get("filepath")
    data = params.get("data")
    if not filepath or data is None:
        raise ValueError("filepath and data are required")
    resolved = _validate_output_path(filepath, allowed_extensions={".json"})
    with open(resolved, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return {"success": True, "filepath": str(resolved)}


def handle_load_workspace(params: dict) -> dict:
    """Load workspace JSON from file."""
    filepath = params.get("filepath")
    resolved = _validate_filepath(filepath, allowed_extensions={".json"})
    if not resolved.exists():
        raise FileNotFoundError(f"File not found: {filepath}")
    file_size = resolved.stat().st_size
    if file_size > 50 * 1024 * 1024:
        raise ValueError(f"Workspace file too large: {file_size / 1024 / 1024:.1f} MB (max 50 MB)")
    with open(resolved, encoding="utf-8") as f:
        data = json.load(f)

    # Validate loaded workspace structure
    if not isinstance(data, dict):
        raise ValueError("Workspace file must contain a JSON object")
    if "results" in data:
        if not isinstance(data["results"], list):
            raise ValueError("Workspace 'results' must be an array")
        if len(data["results"]) > 10_000:
            raise ValueError(f"Workspace contains {len(data['results'])} results, exceeding 10,000 limit")

    return data


def handle_retry_failed(params: dict) -> dict:
    """Retry designing primers for a single failed mutation with custom parameters."""
    mutation_raw = params.get("mutation", "").strip()
    if not mutation_raw:
        raise ValueError("mutation is required")

    fasta_path = params.get("fasta_path")
    if not fasta_path:
        raise ValueError("fasta_path is required")
    resolved_fasta = _validate_filepath(fasta_path, allowed_extensions=_ALLOWED_FASTA_EXTENSIONS)

    target_start = int(params.get("target_start", 0))
    overlap_len = int(params.get("overlap_len", 20))
    codon_strategy = params.get("codon_strategy", "closest")
    organism = params.get("organism", "ecoli")

    tm_fwd = float(params.get("tm_fwd_target", 62))
    tm_rev = float(params.get("tm_rev_target", 58))
    tm_ov = float(params.get("tm_overlap_target", 42))
    gc_min = float(params.get("gc_min", 40))
    gc_max = float(params.get("gc_max", 60))
    fwd_len_min = int(params.get("fwd_len_min", 18))
    fwd_len_max = int(params.get("fwd_len_max", 45))
    rev_len_min = int(params.get("rev_len_min", 18))
    rev_len_max = int(params.get("rev_len_max", 30))
    num_return = int(params.get("num_return", 10))

    # Load template
    _header, sequence, _genes = load_sequence(resolved_fasta)

    # Parse mutation
    wt_aa, position, mt_aa = parse_mutation_notation(mutation_raw)
    codon_start = target_start + (position - 1) * 3
    wt_codon = sequence[codon_start:codon_start + 3]
    actual_aa = CODON_TO_AA.get(wt_codon)
    if actual_aa != wt_aa:
        raise ValueError(f"WT amino acid mismatch: expected {wt_aa} at position {position}, but codon {wt_codon} encodes {actual_aa}")
    mt_codon = best_codon(mt_aa, organism)

    mut = Mutation(
        raw=mutation_raw, wt_aa=wt_aa, position=position, mt_aa=mt_aa,
        codon_start=codon_start, wt_codon=wt_codon, mt_codon=mt_codon,
    )

    # Build polymerase profile with custom Tm targets
    profile = dc_replace(_poly_registry.get("Benchling"),
                         opt_tm_fwd=tm_fwd, opt_tm_rev=tm_rev, opt_tm_overlap=tm_ov)

    candidates = design_single_sdm(
        sequence, mut, profile, overlap_len,
        num_return=num_return, codon_strategy=codon_strategy,
        gc_min=gc_min, gc_max=gc_max,
        fwd_len_min=fwd_len_min, fwd_len_max=fwd_len_max,
        rev_len_min=rev_len_min, rev_len_max=rev_len_max,
        organism=organism,
    )

    return {
        "candidates": [_serialize_result_with_counts(c) for c in candidates],
        "count": len(candidates),
    }


def handle_fetch_domains(params: dict) -> dict:
    """Fetch protein domain boundaries from InterPro/Pfam via UniProt accession."""
    accession = params.get("accession", "").strip()
    if not accession:
        raise ValueError("UniProt accession is required")
    if not re.match(r"^[A-Za-z0-9_-]{1,20}$", accession):
        raise ValueError(f"Invalid UniProt accession format: {accession}")

    # Try Pfam first, then fall back to full InterPro
    endpoints = [
        (
            f"https://www.ebi.ac.uk/interpro/api/entry/pfam/protein/uniprot/{accession}?format=json",
            "pfam",
        ),
        (
            f"https://www.ebi.ac.uk/interpro/api/entry/interpro/protein/uniprot/{accession}?format=json",
            "interpro",
        ),
    ]

    import urllib.request as _urllib_req

    for url, db_label in endpoints:
        try:
            req = _urllib_req.Request(
                url,
                headers={"Accept": "application/json"},
            )
            with _urllib_req.urlopen(req, context=_get_ssl_ctx(), timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            domains: list[dict] = []
            protein_length = 0

            for entry in data.get("results", []):
                meta = entry.get("metadata", {})
                entry_acc = meta.get("accession", "")
                entry_name = meta.get("name", "")

                for protein in entry.get("proteins", []):
                    prot_len = protein.get("protein_length", 0)
                    if prot_len > protein_length:
                        protein_length = prot_len

                    for loc in protein.get("entry_protein_locations", []):
                        for frag in loc.get("fragments", []):
                            domains.append({
                                "name": entry_name,
                                "id": entry_acc,
                                "start": int(frag["start"]),
                                "end": int(frag["end"]),
                                "db": db_label,
                            })

            if domains:
                domains.sort(key=lambda d: d["start"])
                return {
                    "accession": accession,
                    "domains": domains,
                    "source": "interpro_api",
                    "protein_length": protein_length,
                }
        except Exception:
            continue

    # Both endpoints failed or returned no domains
    return {
        "accession": accession,
        "domains": [],
        "source": "error",
        "error_msg": f"No domain data found for {accession}",
    }


def _sequence_identity(seq_a: str, seq_b: str) -> float:
    """Calculate percent identity between two protein sequences.

    Strips trailing stop codons (*), then checks for exact or substring
    match before falling back to positional comparison.
    """
    seq_a = seq_a.rstrip("*").strip()
    seq_b = seq_b.rstrip("*").strip()
    if not seq_a or not seq_b:
        return 0.0
    if seq_a == seq_b:
        return 100.0
    # One sequence is a contiguous substring of the other (e.g. signal peptide trimming)
    if seq_a in seq_b or seq_b in seq_a:
        return 100.0
    matches = sum(1 for a, b in zip(seq_a, seq_b) if a == b)
    return round(matches / max(len(seq_a), len(seq_b)) * 100, 1)


def handle_search_uniprot(params: dict) -> dict:
    """Search UniProt for matching proteins via BLAST + optional direct lookup.

    Primary: BLAST the translation against UniProt Swiss-Prot via EBI BLAST API.
    Secondary: direct fetch if known_accession is provided.
    """
    gene_name = params.get("gene_name", "").strip()
    organism = params.get("organism", "").strip()
    translation = params.get("translation", "").strip()
    known_accession = params.get("known_accession", "").strip()

    if not translation and not known_accession:
        raise ValueError("translation or known_accession is required")
    if known_accession and not re.match(r"^[A-Za-z0-9_-]{1,20}$", known_accession):
        raise ValueError(f"Invalid UniProt accession format: {known_accession}")

    import urllib.request as _urllib_req
    import urllib.parse as _urllib_parse
    import time as _time

    candidates: list[dict] = []
    auto_selected: str | None = None
    last_error: str = ""

    def _fetch_json(url: str) -> tuple[dict | None, str]:
        try:
            req = _urllib_req.Request(url, headers={"Accept": "application/json"})
            with _urllib_req.urlopen(req, context=_get_ssl_ctx(), timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8")), ""
        except Exception as exc:
            logger.warning("UniProt fetch failed: %s — %s", url, exc)
            return None, f"{type(exc).__name__}: {exc}"

    def _fetch_text(url: str) -> tuple[str, str]:
        try:
            req = _urllib_req.Request(url)
            with _urllib_req.urlopen(req, context=_get_ssl_ctx(), timeout=30) as resp:
                return resp.read().decode("utf-8").strip(), ""
        except Exception as exc:
            return "", f"{type(exc).__name__}: {exc}"

    seen_accessions: set[str] = set()

    # 1) Direct fetch by known accession
    if known_accession:
        data, err = _fetch_json(
            f"https://rest.uniprot.org/uniprotkb/{known_accession}?format=json"
        )
        if err:
            last_error = err
        if data and "primaryAccession" in data:
            seq_data = data.get("sequence", {})
            uni_seq = seq_data.get("value", "") if isinstance(seq_data, dict) else ""
            identity = _sequence_identity(translation, uni_seq) if translation else 0.0
            gene_names = [
                gn["geneName"]["value"]
                for gn in data.get("genes", [])
                if gn.get("geneName", {}).get("value")
            ]
            acc = data["primaryAccession"]
            candidates.append({
                "accession": acc,
                "name": ", ".join(gene_names) if gene_names else known_accession,
                "organism": data.get("organism", {}).get("scientificName", ""),
                "length": seq_data.get("length", 0) if isinstance(seq_data, dict) else 0,
                "identity": identity,
            })
            seen_accessions.add(acc)
            if identity == 100.0:
                auto_selected = acc

    # 2) BLAST search using protein sequence via EBI NCBI BLAST API
    if translation and not auto_selected:
        try:
            blast_data = _urllib_parse.urlencode({
                # TODO(security): Replace with user-configured email — hardcoded
                # placeholder violates EBI Terms of Use. Read from app config or
                # prompt user on first BLAST run.
                "email": "kuro-app@example.com",
                "program": "blastp",
                "database": "uniprotkb_swissprot",
                "stype": "protein",
                "sequence": translation.rstrip("*"),
            }).encode()
            submit_req = _urllib_req.Request(
                "https://www.ebi.ac.uk/Tools/services/rest/ncbiblast/run",
                data=blast_data,
                method="POST",
            )
            with _urllib_req.urlopen(submit_req, context=_get_ssl_ctx(), timeout=30) as resp:
                job_id = resp.read().decode().strip()

            # Poll for completion (max ~60s)
            status_text = ""
            for _ in range(20):
                # Cancel-aware sleep: check every 0.5s instead of blocking 3s
                for _ in range(6):
                    if _cancel_event.is_set():
                        _cancel_event.clear()
                        return {"candidates": candidates, "error": "Cancelled"}
                    _time.sleep(0.5)
                status_text, _ = _fetch_text(
                    f"https://www.ebi.ac.uk/Tools/services/rest/ncbiblast/status/{job_id}"
                )
                if status_text == "FINISHED":
                    break
                if status_text in ("FAILURE", "ERROR", "NOT_FOUND"):
                    raise RuntimeError(f"BLAST job failed: {status_text}")

            if status_text == "FINISHED":
                result_data, err = _fetch_json(
                    f"https://www.ebi.ac.uk/Tools/services/rest/ncbiblast/result/{job_id}/json"
                )
                if err:
                    last_error = err
                if result_data:
                    for hit in result_data.get("hits", [])[:10]:
                        # hit_acc is like "SP:Q50L36" or just accession
                        raw_acc = hit.get("hit_acc", "")
                        acc = raw_acc.split(":")[-1] if ":" in raw_acc else raw_acc
                        if acc in seen_accessions:
                            continue
                        seen_accessions.add(acc)
                        hsps = hit.get("hit_hsps", [])
                        blast_identity = hsps[0].get("hsp_identity", 0.0) if hsps else 0.0
                        # Parse organism from hit description: "... OS=Genus species ..."
                        hit_def = hit.get("hit_def", "")
                        os_m = re.search(r'\bOS=([^=]+?)(?:\s+\w+=|$)', hit_def)
                        hit_organism = os_m.group(1).strip() if os_m else ""
                        # Parse gene name
                        gn_m = re.search(r'\bGN=(\S+)', hit_def)
                        hit_gene = gn_m.group(1) if gn_m else ""
                        hit_len = hsps[0].get("hsp_hit_to", 0) if hsps else 0
                        candidates.append({
                            "accession": acc,
                            "name": hit_gene or acc,
                            "organism": hit_organism,
                            "length": hit_len,
                            "identity": blast_identity,
                        })
        except Exception as exc:
            logger.warning("BLAST search failed: %s", exc)
            last_error = f"BLAST: {type(exc).__name__}: {exc}"

    candidates.sort(key=lambda c: c["identity"], reverse=True)

    if candidates and candidates[0]["identity"] >= 95.0:
        auto_selected = candidates[0]["accession"]

    return {
        "candidates": candidates,
        "auto_selected": auto_selected,
        "error_detail": last_error or None,
    }


def handle_list_organisms(_params: dict) -> list[dict]:
    """Return available organism codon tables for the UI dropdown."""
    return _codon_registry.list_organisms_detailed()


_ALLOWED_ORDER_CSV_EXTENSIONS = {".csv"}


def handle_export_order(params: dict) -> dict:
    """Export primer order CSV in IDT or Twist format.

    Params:
        filepath: Output CSV path.
        format: "idt" or "twist".
        scale: IDT synthesis scale (default "25nm").
        purification: IDT purification (default "STD").
    """
    filepath = params.get("filepath")
    fmt = params.get("format", "idt").lower()
    if fmt not in ("idt", "twist"):
        raise ValueError(f"Invalid export format: '{fmt}'. Must be 'idt' or 'twist'.")

    resolved = _validate_output_path(
        filepath, allowed_extensions=_ALLOWED_ORDER_CSV_EXTENSIONS
    )

    if not _state.results:
        raise ValueError("No design available. Run design_sdm_primers first.")

    if fmt == "idt":
        scale = params.get("scale", "25nm")
        purification = params.get("purification", "STD")
        export_idt_csv(_state.results, resolved, scale=scale, purification=purification)
    else:
        export_twist_csv(_state.results, resolved)

    return {"success": True, "filepath": str(resolved), "format": fmt, "primer_count": len(_state.results) * 2}


def handle_fetch_esm_embedding(params: dict) -> dict:
    """Compute or fetch ESM-2 per-residue embedding.

    Accepts accession and/or sequence. Local inference is preferred
    when torch + fair-esm are installed; remote API is fallback.
    """
    accession = params.get("accession", "").strip()
    sequence = params.get("sequence", "").strip()
    if not accession and not sequence:
        raise ValueError("accession or sequence is required")

    from kuro.esm_embeddings import get_embedding

    embedding = get_embedding(accession=accession, sequence=sequence)

    if embedding is None:
        _state.esm_embedding = None
        return {"success": False, "error": "ESM-2 unavailable (install: pip install fair-esm torch)"}

    _state.esm_embedding = embedding
    return {
        "success": True,
        "accession": accession,
        "length": len(embedding),
        "dimension": len(embedding[0]) if embedding else 0,
    }


def handle_run_benchmark(params: dict) -> dict:
    """Run benchmark simulation on provided fitness landscape."""
    from kuro.benchmark import run_benchmark

    landscape_data = params.get("landscape", [])
    ground_truth = params.get("ground_truth", {})
    n_select = int(params.get("n_select", 95))
    strategies = params.get("strategies", ["topn", "random", "pareto"])

    if not landscape_data:
        raise ValueError("landscape data is required")

    landscape = [(v["variant"], v["fitness"]) for v in landscape_data]

    bench_results = run_benchmark(
        landscape, ground_truth, n_select, strategies=strategies
    )
    return {"results": bench_results}


# --- Dispatcher ---

_METHODS = {
    "list_polymerases": handle_list_polymerases,
    "list_organisms": handle_list_organisms,
    "load_fasta": handle_load_fasta,
    "parse_mutations_text": handle_parse_mutations_text,
    "design_sdm_primers": handle_design_sdm_primers,
    "load_evolvepro_csv": handle_load_evolvepro_csv,
    "get_plate_map": handle_get_plate_map,
    "get_alternatives": handle_get_alternatives,
    "swap_primer": handle_swap_primer,
    "export_excel": handle_export_excel,
    "export_order": handle_export_order,
    "evaluate_primer": handle_evaluate_primer,
    "retry_failed_mutation": handle_retry_failed,
    "save_workspace": handle_save_workspace,
    "load_workspace": handle_load_workspace,
    "fetch_domains": handle_fetch_domains,
    "search_uniprot": handle_search_uniprot,
    "fetch_esm_embedding": handle_fetch_esm_embedding,
    "run_benchmark": handle_run_benchmark,
    "cancel_design": lambda _: (_cancel_event.set(), {"cancelled": True})[1],
}


# Methods that run in a background thread to avoid blocking the main loop.
# These are long-running operations (network I/O, heavy computation).
_ASYNC_METHODS = {"search_uniprot", "fetch_esm_embedding", "fetch_domains", "run_benchmark"}


def _dispatch_handler(req_id: int | None, method: str, handler, params: dict) -> None:
    """Run a handler and send its JSON-RPC response. Used by both sync and threaded dispatch."""
    try:
        result = handler(params)
        _ok(req_id, result)
    except FileNotFoundError as exc:
        _append_crash_log(method, str(params)[:200], traceback.format_exc())
        _error(req_id, -32001, str(exc))
    except (KeyError, ValueError) as exc:
        _append_crash_log(method, str(params)[:200], traceback.format_exc())
        _error(req_id, -32602, str(exc))
    except Exception as exc:
        logger.exception("Unhandled error in %s", method)
        _append_crash_log(method, str(params)[:200], traceback.format_exc())
        _error(req_id, -32603, f"{type(exc).__name__}: {exc}")


def dispatch(request: dict) -> None:
    """Process a single JSON-RPC request."""
    req_id = request.get("id")
    method = request.get("method", "")
    params = request.get("params", {})

    handler = _METHODS.get(method)
    if handler is None:
        _error(req_id, -32601, f"Method not found: {method}")
        return

    if method in _ASYNC_METHODS:
        t = threading.Thread(
            target=_dispatch_handler, args=(req_id, method, handler, params), daemon=True
        )
        t.start()
        return

    _dispatch_handler(req_id, method, handler, params)


def _start_parent_watchdog() -> None:
    """Exit if parent process dies (prevents orphan sidecar on Windows)."""
    import time
    ppid = os.getppid()
    if ppid <= 1:
        return

    def _check() -> None:
        if sys.platform == "win32":
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.OpenProcess.restype = ctypes.c_void_p
            # Get parent handle at startup to avoid PID reuse false negatives
            SYNCHRONIZE = 0x00100000
            parent_handle = kernel32.OpenProcess(SYNCHRONIZE, False, ppid)
            if not parent_handle:
                return  # can't monitor
            while True:
                time.sleep(5)
                # WAIT_TIMEOUT=0x102, WAIT_OBJECT_0=0 (process exited)
                ret = kernel32.WaitForSingleObject(ctypes.c_void_p(parent_handle), 0)
                if ret == 0:  # WAIT_OBJECT_0 = parent exited
                    logger.info("Parent process %d died, exiting", ppid)
                    kernel32.CloseHandle(ctypes.c_void_p(parent_handle))
                    os._exit(0)
        else:
            while True:
                time.sleep(5)
                try:
                    os.kill(ppid, 0)
                except ProcessLookupError:
                    logger.info("Parent process %d died, exiting", ppid)
                    os._exit(0)
                except PermissionError:
                    pass  # process exists but different user

    t = threading.Thread(target=_check, daemon=True)
    t.start()


def main() -> None:
    """Main loop: read JSON-RPC requests from stdin, dispatch, respond on stdout."""
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    _start_parent_watchdog()
    logger.info("KURO sidecar started (pid=%d)", os.getpid())
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
