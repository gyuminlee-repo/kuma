"""JSON-RPC 2.0 dispatcher for KURO sidecar.

Communicates via stdin/stdout with the Tauri host.
Protocol: one JSON object per line (newline-delimited JSON).
"""

import csv
import json
import logging
import os
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
    design_sdm_primers,
    evaluate_custom_primer,
    load_fasta,
    load_sequence,
)
from kuro.mutation import parse_mutation_notation
from kuro.polymerase import PolymeraseRegistry
from kuro.plate_mapper import (
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

_ALLOWED_FASTA_EXTENSIONS = {".dna", ".gb", ".gbff", ".gbk"}
_ALLOWED_CSV_EXTENSIONS = {".csv", ".tsv", ".txt"}
_ALLOWED_EXCEL_EXTENSIONS = {".xlsx"}
_VALID_DNA_BASES = re.compile(r"^[ATGC]+$")

# --- Session state ---
@dataclass
class SidecarState:
    """Mutable session state shared across RPC handlers."""
    results: list[SdmPrimerResult] = field(default_factory=list)
    candidates: dict[str, list[SdmPrimerResult]] = field(default_factory=dict)
    plate_mappings: list[PlateMapping] = field(default_factory=list)
    dedup_info: dict[str, list[str]] = field(default_factory=dict)
    template: tuple[str, str] = ("", "")  # (fasta_path, sequence)

_state = SidecarState()

# Legacy aliases for backward compat during transition
_last_results = _state.results
_last_candidates = _state.candidates
_last_plate_mappings = _state.plate_mappings
_last_dedup_info = _state.dedup_info
_last_template = _state.template

_SWAP_FIELDS = {
    "fwd": ["forward_seq", "forward_binding", "tm_fwd", "fwd_len", "gc_fwd"],
    "rev": ["reverse_seq", "reverse_binding", "tm_rev", "rev_len", "gc_rev"],
}


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
    """Load a sequence file and return sequence info with gene annotations."""
    global _last_template
    filepath = params.get("filepath")
    resolved = _validate_filepath(filepath, allowed_extensions=_ALLOWED_FASTA_EXTENSIONS)

    if not resolved.exists():
        raise FileNotFoundError(f"File not found: {filepath}")

    header, sequence, genes = load_sequence(resolved)
    _last_template = (str(resolved), sequence)

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
    global _last_results, _last_candidates, _last_plate_mappings, _last_dedup_info, _last_template

    # Clear previous state to free memory
    _last_results = []
    _last_candidates = {}
    _last_plate_mappings = []
    _last_dedup_info = {}

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

    fwd_len_min = int(params.get("fwd_len_min", 12))
    fwd_len_max = int(params.get("fwd_len_max", 45))
    rev_len_min = int(params.get("rev_len_min", 12))
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
        )
    finally:
        if temp_csv is not None:
            os.unlink(temp_csv.name)

    _last_results = results
    _last_candidates = all_cands
    _progress(80, "Generating plate map...")

    # Auto-generate plate map (Fwd/Rev separate plates)
    fwd_map, rev_map = generate_plate_map(results, deduplicate_rev=True)
    _last_plate_mappings = fwd_map + rev_map
    _last_dedup_info = deduplicate_reverse(results)

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
    cands = _last_candidates.get(r.mutation.raw, [])
    result = _serialize_result(r, len(cands))
    fwd_count, rev_count = _count_unique_fwd_rev(cands) if cands else (0, 0)
    result["candidate_fwd_count"] = fwd_count
    result["candidate_rev_count"] = rev_count
    return result


def handle_get_plate_map(_params: dict) -> dict:
    """Return the plate map from last design."""
    if not _last_results:
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
            for m in _last_plate_mappings
        ],
        "dedup_info": _last_dedup_info,
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
        if not _last_results:
            raise ValueError("No design available")
        mappings = _last_plate_mappings
        rev_groups = _last_dedup_info

    export_plate_excel(mappings, resolved, rev_groups=rev_groups)
    return {"success": True, "filepath": str(resolved)}


def handle_load_evolvepro_csv(params: dict) -> dict:
    """Load EVOLVEpro df_test.csv, sort by y_pred descending, return top-N variants."""
    filepath = params.get("filepath", "")
    if not filepath:
        raise ValueError("filepath is required")
    resolved = _validate_filepath(filepath, allowed_extensions=_ALLOWED_CSV_EXTENSIONS)
    filepath = str(resolved)

    top_n = int(params.get("top_n", 96))
    max_per_pos = int(params.get("max_per_position", 0))

    rows: list[tuple[str, float]] = []
    with open(filepath, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        columns = reader.fieldnames or []
        if "variant" not in columns:
            raise ValueError(
                "EVOLVEpro CSV must have a 'variant' column. "
                f"Found columns: {columns}"
            )
        has_ypred = "y_pred" in columns
        for row in reader:
            variant = row.get("variant", "").strip()
            if not variant:
                continue
            y_pred = float(row["y_pred"]) if has_ypred and row.get("y_pred") else 0.0
            rows.append((variant, y_pred))

    if has_ypred:
        rows.sort(key=lambda r: r[1], reverse=True)

    # Position diversity filter: limit mutations per amino acid position
    pre_filter_count = len(rows)
    if max_per_pos > 0:
        _pos_re = re.compile(r"^[A-Z](\d+)[A-Z]$")
        pos_count: dict[int, int] = {}
        filtered: list[tuple[str, float]] = []
        for variant, y in rows:
            m = _pos_re.match(variant)
            pos = int(m.group(1)) if m else -1
            count = pos_count.get(pos, 0)
            if pos == -1 or count < max_per_pos:
                filtered.append((variant, y))
                pos_count[pos] = count + 1
        rows = filtered

    selected = rows[:top_n]
    return {
        "variants": [v for v, _ in selected],
        "y_preds": [round(y, 4) for _, y in selected],
        "total_count": pre_filter_count,
        "selected_count": len(selected),
        "filtered_count": pre_filter_count - len(rows),
    }


def handle_get_alternatives(params: dict) -> dict:
    """Return all candidates for a specific mutation."""
    mutation = params.get("mutation", "")
    if not mutation:
        raise ValueError("mutation is required")
    candidates = _last_candidates.get(mutation, [])
    return {
        "mutation": mutation,
        "candidates": [_serialize_result(c) for c in candidates],
    }


def handle_swap_primer(params: dict) -> dict:
    """Swap the selected primer for a mutation with a different candidate."""
    global _last_results
    mutation = params.get("mutation", "")
    candidate_idx = int(params.get("candidate_idx", 0))
    swap_type = params.get("swap_type", "both")  # "both", "fwd", "rev"

    candidates = _last_candidates.get(mutation)
    if not candidates:
        raise ValueError(f"No candidates for mutation: {mutation}")
    if candidate_idx < 0 or candidate_idx >= len(candidates):
        raise ValueError(f"Invalid candidate index: {candidate_idx}")

    source = candidates[candidate_idx]

    if swap_type == "both":
        new_best = source
    else:
        current = next((r for r in _last_results if r.mutation.raw == mutation), None)
        if not current:
            raise ValueError(f"No current result for mutation: {mutation}")
        swap_dict = {f: getattr(source, f) for f in _SWAP_FIELDS[swap_type]}
        new_best = dc_replace(current, **swap_dict)

    target_pos = new_best.mutation.position
    for i, r in enumerate(_last_results):
        if r.mutation.raw == mutation:
            _last_results[i] = new_best
        elif swap_type in ("rev", "both") and r.mutation.position == target_pos:
            # Propagate reverse to same-position mutations
            _last_results[i] = dc_replace(
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
    cached_path, cached_seq = _last_template
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


# --- Dispatcher ---

_METHODS = {
    "list_polymerases": handle_list_polymerases,
    "load_fasta": handle_load_fasta,
    "parse_mutations_text": handle_parse_mutations_text,
    "design_sdm_primers": handle_design_sdm_primers,
    "load_evolvepro_csv": handle_load_evolvepro_csv,
    "get_plate_map": handle_get_plate_map,
    "get_alternatives": handle_get_alternatives,
    "swap_primer": handle_swap_primer,
    "export_excel": handle_export_excel,
    "evaluate_primer": handle_evaluate_primer,
    "save_workspace": handle_save_workspace,
    "load_workspace": handle_load_workspace,
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
        sys.stderr.reconfigure(encoding="utf-8")

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
