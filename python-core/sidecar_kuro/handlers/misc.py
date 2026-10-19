"""Handlers: polymerase list, organism list, EVOLVEpro CSV, benchmark."""

import csv
import hashlib
from dataclasses import asdict
from pathlib import Path

from kuma_core.kuro import codon_table as _codon_table
from kuma_core.kuro.evolvepro import load_evolvepro_csv
from kuma_core.kuro.polymerase import _dict_to_profile
from kuma_core.shared.resource_path import resource_path as _resource_path

import sidecar_kuro.core as _core
from sidecar_kuro.core import (
    _validate_filepath,
    _poly_registry,
    _CUSTOM_POLYMERASE_PATH,
    _get_cached_ca_coords,
    _get_cached_ca_seq,
    _esmfold_pdb_text,
)
from sidecar_kuro.models import (
    LoadEvolveproParams,
    PolymeraseProfileModel,
    PreviewEvolveproSourceParams,
    RunBenchmarkParams,
    SaveCustomPolymeraseResultModel,
)

# EVOLVEpro-specific table extensions: CSV, TSV, and XLSX.
# .txt is excluded intentionally (ambiguous delimiter, not supported for column mapping).
_ALLOWED_TABLE_EXTENSIONS = {".csv", ".tsv", ".xlsx", ".xls"}


_POLYMERASE_META = {
    "Benchling": {"manufacturer": "SantaLucia 1998", "fidelity": "standard"},
    "Q5": {"manufacturer": "NEB", "fidelity": "high"},
    "Phusion": {"manufacturer": "Thermo", "fidelity": "high"},
    "Taq": {"manufacturer": "Various", "fidelity": "low"},
    "DreamTaq": {"manufacturer": "Thermo", "fidelity": "low"},
    "KOD": {"manufacturer": "Toyobo", "fidelity": "high"},
    "TAKARA_GXL": {"manufacturer": "Takara", "fidelity": "high"},
    "Q5 SDM": {"manufacturer": "NEB", "fidelity": "high"},
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
                "proofreading": _poly_registry.get(name).proofreading,
            }
        )
    return result


def handle_get_polymerase_details(params: dict) -> dict:
    """Return full polymerase profile for the selected name."""
    name = params.get("name", "")
    profile = PolymeraseProfileModel.model_validate(asdict(_poly_registry.get(name)))
    return profile.to_rpc_dict()


def handle_save_custom_polymerase(params: dict) -> dict:
    """Persist a custom polymerase profile and keep it available after restart."""
    profile = _dict_to_profile(params)
    _CUSTOM_POLYMERASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _poly_registry.save_custom(profile, _CUSTOM_POLYMERASE_PATH)
    return SaveCustomPolymeraseResultModel(name=profile.name).to_rpc_dict()


_CODON_SEED_DIR = _resource_path(
    "kuma_core.kuro", "resources/codon_table_seeds", module_file=_codon_table.__file__
)
# Seed file names are kept verbatim. TEMPLATE keeps a .json.txt suffix so the
# *.json glob that finds real tables never picks the template up, and the
# M. extorquens AM1 seed keeps it for the same reason: it is a complete,
# ready-to-use table rather than a placeholder, and it installs only when the
# user renames it to mextorquens_am1.json. Seeding it is not installing it, so
# the organism dropdown is unchanged until that rename happens.
_CODON_SEED_FILES = (
    "README.txt",
    "TEMPLATE.json.txt",
    "mextorquens_am1.json.txt",
)


def ensure_user_codon_dir() -> Path:
    """Create the user codon-table folder and seed it, then return the path.

    "Open folder" has to land somewhere that exists even before the user has
    installed anything, so the folder and its two seed files are written on the
    first listing. An existing seed is never overwritten; the user may have
    edited it.
    """
    directory = _core.user_codon_dir()
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError:
        # A read-only home must not take the organism list down with it, and
        # the mkdir is the first thing that fails there. The path is still
        # returned so "Open folder" has something to show; the registry treats
        # a directory that does not exist the same as an empty one and the
        # bundled tables still list.
        return directory
    for name in _CODON_SEED_FILES:
        source = _CODON_SEED_DIR / name
        target = directory / name
        if source.exists() and not target.exists():
            try:
                target.write_text(
                    source.read_text(encoding="utf-8"), encoding="utf-8"
                )
            except OSError:
                # Same reason: a seed that cannot be written is not fatal.
                pass
    return directory


def handle_list_organisms(_params: dict) -> dict:
    """Return the organism codon tables, the ones that failed, and the folder.

    Phase 1 ships no separate refresh RPC, so this call *is* the refresh: it
    drops the registry caches first and re-reads both directories. The seed
    files are written on the way so that "Open folder" never lands the user in a
    folder that does not exist.

    Shape::

        {"organisms": [{key, name, taxid, source, aliases, cds_count,
                        table_sha256, warnings: [{code, params}],
                        normalizations: [{code, params}], document: {...}}],
         "failed":    [{filename, code, reason, findings: [{code, params}]}],
         "user_dir":  "<absolute path>"}

    ``taxid`` is nullable: an in-house strain may have no NCBI id.

    ``document`` is the whole table as a self-contained JSON object. The
    workspace embeds it so a project stays readable on a machine that never had
    the file (design note section 8.2), and the restore branches diff it
    amino acid by amino acid when the digests disagree. ``normalizations``
    reports what the import silently changed; it used to be computed and
    dropped here, which left N1/N2/N4 unreachable in every locale.
    """
    ensure_user_codon_dir()
    registry = _core.get_registry()
    registry.refresh()
    return registry.scan()


def _preview_csv(filepath: str, max_rows: int) -> dict:
    """Read headers and first max_rows data rows from a CSV or TSV file."""
    delimiter = "\t" if Path(filepath).suffix.lower() == ".tsv" else ","
    with open(filepath, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, delimiter=delimiter)
        headers = next(reader, [])
        rows = []
        for i, row in enumerate(reader):
            if i >= max_rows:
                break
            rows.append([str(c) for c in row])
    return {"sheets": [], "headers": headers, "rows": rows}


def _preview_xlsx(filepath: str, sheet_name: str | None, max_rows: int) -> dict:
    """Read sheet names, headers, and first max_rows rows from an XLSX file."""
    import openpyxl

    from itertools import islice

    wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
    try:
        sheet_names = wb.sheetnames
        if not sheet_names:
            return {"sheets": [], "headers": [], "rows": []}
        target = sheet_name if sheet_name is not None else sheet_names[0]
        if target not in sheet_names:
            raise ValueError(
                f"sheet '{target}' not found in {filepath}. "
                f"Available sheets: {sheet_names}"
            )
        rows = iter(wb[target].iter_rows(values_only=True))
        first = next(rows, ())
        headers = [str(c) if c is not None else "" for c in first]
        data_rows = [
            [str(c) if c is not None else "" for c in row]
            for row in islice(rows, max_rows)
        ]
        return {"sheets": sheet_names, "headers": headers, "rows": data_rows}
    finally:
        wb.close()


def _preview_xls(filepath: str, sheet_name: str | None, max_rows: int) -> dict:
    """Read sheet names, headers, and first max_rows rows from a legacy XLS file."""
    import xlrd

    wb = xlrd.open_workbook(filepath)
    sheet_names = wb.sheet_names()
    target = sheet_name if sheet_name is not None else sheet_names[0]
    if target not in sheet_names:
        raise ValueError(
            f"sheet '{target}' not found in {filepath}. "
            f"Available sheets: {sheet_names}"
        )

    ws = wb.sheet_by_name(target)
    if ws.nrows == 0:
        return {"sheets": sheet_names, "headers": [], "rows": []}

    headers = [str(c.value) if c.value is not None else "" for c in ws.row(0)]
    rows = []
    for ridx in range(1, min(ws.nrows, max_rows + 1)):
        rows.append([str(c.value) if c.value is not None else "" for c in ws.row(ridx)])
    return {"sheets": sheet_names, "headers": headers, "rows": rows}


def handle_preview_evolvepro_source(params: dict) -> dict:
    """Preview first rows and column headers of a CSV or XLSX EVOLVEpro source."""
    p = PreviewEvolveproSourceParams(**params)
    resolved = _validate_filepath(p.filepath, allowed_extensions=_ALLOWED_TABLE_EXTENSIONS)
    ext = Path(str(resolved)).suffix.lower()
    if ext == ".xlsx":
        return _preview_xlsx(str(resolved), p.sheet_name, p.max_rows)
    if ext == ".xls":
        return _preview_xls(str(resolved), p.sheet_name, p.max_rows)
    return _preview_csv(str(resolved), p.max_rows)


def _frame_checked_ca_coords(
    ca_coords: list | None,
    structure_accession: str | None,
    ref_seq: str,
) -> tuple[list | None, bool]:
    """Two-value form of ``_frame_checked_ca_projection`` for callers that ignore coverage."""
    projected, mismatch, _ = _frame_checked_ca_projection(ca_coords, structure_accession, ref_seq)
    return projected, mismatch


def _frame_checked_ca_projection(
    ca_coords: list | None,
    structure_accession: str | None,
    ref_seq: str,
) -> tuple[list | None, bool, dict | None]:
    """Project a unique exact reference interval or report an unavailable frame.

    Returns ``(coords, frame_mismatch, coverage)``. ``coverage`` is
    ``{"covered", "reference_length"}`` when the structure lacks terminal
    reference residues (those positions are None in ``coords``) and None when it
    covers the whole reference.

    3D coordinates are indexed by reference-sequence position, so a structure
    that does not contain the reference exactly once would place
    Cα coordinates on the wrong residues, silently corrupting any 3D-aware
    selection. When it does not match, return None so callers fall back to 1-D
    distance, plus a flag the UI can surface. Both load_evolvepro_csv and
    run_benchmark share this so their handling cannot diverge.

    The legacy callers retain their existing fallback policies when coordinates
    are unavailable. This conservative sequence contract does not estimate
    homolog geometry or imply that substitutions always change residue indices.

    A user-supplied structure caches its own sequence, so use that and skip the
    network. Only fall back to fetching when the coordinates came from an
    accession, which has no cached sequence.
    """
    if ca_coords is None or not structure_accession or not ref_seq.strip():
        return ca_coords, False, None
    from kuma_core.kuro.interface import reference_structure_overlap

    structure_seq = _get_cached_ca_seq(structure_accession)
    if structure_seq is None:
        from kuma_core.kuro.alphafold import fetch_ca_seq

        structure_seq = fetch_ca_seq(structure_accession)
    overlap = reference_structure_overlap(structure_seq or "", ref_seq)
    if overlap is None:
        return None, True, None
    offset = overlap["offset"]
    length = overlap["reference_length"]
    partial = overlap["covered"] < length
    coverage = {"covered": overlap["covered"], "reference_length": length} if partial else None
    if offset == 0 and not partial and len((structure_seq or "").strip().rstrip("*")) == length:
        return ca_coords, False, None
    # Coordinates are 1-indexed in the source frame. Preserve missing entries;
    # never shift a tagged construct's residue 1 onto reference residue 1.
    return [None] + [
        ca_coords[p + offset] if 1 <= p + offset < len(ca_coords) else None
        for p in range(1, length + 1)
    ], False, coverage


def handle_load_evolvepro_csv(params: dict) -> dict:
    """Load EVOLVEpro df_test.csv, sort by y_pred descending, return top-N variants."""
    p = LoadEvolveproParams(**params)
    if not p.filepath:
        raise ValueError("filepath is required")
    resolved = _validate_filepath(p.filepath, allowed_extensions=_ALLOWED_TABLE_EXTENSIONS)

    ca_coords = _get_cached_ca_coords(p.structure_accession)
    strict_context = None
    if p.strict_spatial:
        if not p.structural_diversity or not p.structure_accession or p.structure_accession.startswith("file:"):
            raise ValueError("Strict spatial selection requires an AlphaFold accession or an ESMFold prediction, and structural mode")
        from kuma_core.kuro.alphafold import fetch_pdb_text
        from kuma_core.kuro.esmfold import STRUCTURE_KEY_PREFIX
        from kuma_core.kuro.strict_spatial import (
            SOURCE_ALPHAFOLD_DB,
            SOURCE_ESMFOLD,
            StrictFrameMismatchError,
            exact_pdb_context,
        )

        strict_accession = p.structure_accession.strip().upper()
        # An ESMFold key names a prediction of the reference made in this app;
        # anything else is an AlphaFold DB accession. Neither is guessed from TITLE.
        if strict_accession.startswith(STRUCTURE_KEY_PREFIX):
            pdb_text = _esmfold_pdb_text(strict_accession)
            strict_source = SOURCE_ESMFOLD
        else:
            pdb_text = fetch_pdb_text(strict_accession)
            strict_source = SOURCE_ALPHAFOLD_DB
        if not pdb_text and strict_source == SOURCE_ESMFOLD:
            # The prediction is gone (cache cleared, project opened elsewhere).
            # Same expected refusal as a structure that does not hold the
            # reference, so the UI answers it instead of logging a crash.
            raise StrictFrameMismatchError("Strict spatial source structure is unavailable")
        if not pdb_text:
            raise ValueError("Strict spatial source PDB is unavailable")
        strict_context = exact_pdb_context(pdb_text, p.ref_seq, strict_accession, source=strict_source)
        strict_context["candidate_sha256"] = hashlib.sha256(resolved.read_bytes()).hexdigest()
        strict_context["score_order"] = p.score_order
        strict_context["budget_mode"] = p.strict_spatial_budget
        strict_context["site_cap"] = p.strict_spatial_site_cap

    # Legacy exact-sequence guard with explicit reference-offset projection.
    # Strict mode validates the actual source PDB independently and never falls
    # back to sequence distances.
    if strict_context is None:
        ca_coords, structure_frame_mismatch, structure_coverage = _frame_checked_ca_projection(
            ca_coords, p.structure_accession, p.ref_seq
        )
    else:
        structure_frame_mismatch, structure_coverage = False, None
    result = load_evolvepro_csv(
        filepath=str(resolved),
        top_n=p.top_n,
        max_per_position=p.max_per_position,
        domains=p.domains,
        excluded_ranges=[{"start": r.start, "end": r.end} for r in p.excluded_ranges],
        domain_diversity=p.domain_diversity,
        domain_strategy=p.domain_strategy,
        domain_overlap_policy=p.domain_overlap_policy,
        linker_handling=p.linker_handling,
        domain_quota_min=p.domain_quota_min,
        pareto_diversity=p.pareto_diversity,
        entropy_weight=p.entropy_weight,
        pool_multiplier=p.pool_multiplier,
        distance_mode=p.distance_mode,
        ca_coords=ca_coords,
        evolvepro_round=p.evolvepro_round,
        round_size=p.round_size,
        ref_seq=p.ref_seq,
        variant_column=p.variant_column,
        score_column=p.score_column,
        score_order=p.score_order,
        sheet_name=p.sheet_name,
        domain_pool_autoexpand=p.domain_pool_autoexpand,
        domain_pool_max_multiplier=p.domain_pool_max_multiplier,
        structural_diversity=p.structural_diversity,
        structural_kappa=p.structural_kappa,
        anchor_variants=p.anchor_variants,
        strict_spatial_context=strict_context,
    )
    result["structure_frame_mismatch"] = structure_frame_mismatch
    result["structure_coverage"] = structure_coverage
    # What the selection actually ran on, so the UI reports 3D only when it was used.
    result["structure_coordinates_used"] = strict_context is not None or ca_coords is not None
    if strict_context is not None:
        if hashlib.sha256(resolved.read_bytes()).hexdigest() != strict_context["candidate_sha256"]:
            raise ValueError("Candidate input changed during strict spatial selection; retry")
    return result


def handle_run_benchmark(params: dict) -> dict:
    """Run benchmark simulation on provided fitness landscape."""
    from kuma_core.kuro.benchmark import run_benchmark

    p = RunBenchmarkParams(**params)

    if not p.landscape:
        raise ValueError("landscape data is required")

    landscape = [(v.variant, v.fitness) for v in p.landscape]

    ca_coords = _get_cached_ca_coords(p.structure_accession)
    # Same frame guard load_evolvepro_csv uses: a structure that does not cover
    # the reference frame must not feed 3D coordinates into the benchmark.
    ca_coords, structure_frame_mismatch, structure_coverage = _frame_checked_ca_projection(
        ca_coords, p.structure_accession, p.ref_seq
    )

    bench_results = run_benchmark(
        landscape,
        p.ground_truth,
        p.n_select,
        n_random_trials=p.n_random_trials,
        top_percentile=p.top_percentile,
        strategies=p.strategies,
        domains=p.domains,
        domain_strategy=p.domain_strategy,
        max_per_position=p.max_per_position,
        entropy_weight=p.entropy_weight,
        pool_multiplier=p.pool_multiplier,
        distance_mode=p.distance_mode,
        random_seed=p.random_seed,
        ca_coords=ca_coords,
    )
    return {
        "results": bench_results,
        "structure_frame_mismatch": structure_frame_mismatch,
        "structure_coordinates_used": ca_coords is not None,
        "structure_coverage": structure_coverage,
    }
