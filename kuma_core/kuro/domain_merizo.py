"""Optional Merizo scientific interchange; no runtime, installation or selection.

The original full-atom input gate and annotation types are shared with the
earlier interchange. Merizo output is decoded into a provider-neutral structural
partition. Provenance fields establish consistency, not authenticated execution
or biological accuracy. No torch (or any other ML package) is imported here.
"""
from __future__ import annotations

import json
import math
import re
import struct
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from kuma_core.kuro.domain_annotation import (
    MAX_RESULT_BYTES, DomainAnnotation, DomainAnnotationError, DomainInput,
    DomainSegment, StructuralDomain, prepare_domain_input,
)
from kuma_core.kuro.residue_mapping import PolymerRecord, ResidueId

if TYPE_CHECKING:
    from kuma_core.kuro.prediction_bundle import PredictionBundleContext

MERIZO_COMMIT = "41d12fb84e6e8fdb586c2c859d12161dc7bb5bfd"
MERIZO_WEIGHTS_SHA256 = {
    "weights_part_0.pt": "8b90ad1967c3e445aca7ed3d53135190ceaf8e100d68afd1543e5e8d28547151",
    "weights_part_1.pt": "644f711b9573b44fc25a0bc0631ee9ab43f7fbd796db0a382298755057a2fa38",
    "weights_part_2.pt": "ddafe5fa5dfa729eb8715757004d2d3e4e9798f96ea43c689e799ef91af8c2b8",
}
AF3_UNSUPPORTED_REASON = (
    "AF3/mmCIF domain annotation is unsupported: a lossless full-atom mmCIF-to-PDB "
    "conversion with validated label/auth/model/chain residue mapping is required; "
    "the reference-indexed viewer CA trace cannot replace the original atoms."
)


def domain_input_manifest(prepared: DomainInput) -> dict[str, Any]:
    """Provider-neutral view of the existing, unchanged full-atom input contract."""
    prepared.check_consistency()
    return {**prepared.manifest(), "schema": "kuma-domain-input-v1"}


def prepare_colabfold_domain_input(
    context: PredictionBundleContext, reference_sequence: str,
) -> DomainInput:
    """Prepare an explicitly selected model/chain from a validated local bundle.

    Reuse independent A3M polymer evidence and original structure bytes, never
    reconstruct backbone atoms from display coordinates. Full reference/polymer
    identity is required, even though the general bundle importer allows exact
    fragments. Producer identity is not authenticated by this read-only check.
    """
    if context.format == "af3_server" or context.structure_format != "pdb":
        raise DomainAnnotationError(AF3_UNSUPPORTED_REASON)
    if context.format != "colabfold":
        raise DomainAnnotationError("Require a validated ColabFold PDB bundle")
    polymer = context.mapping.polymer
    expected_frame = f"prediction:{context.bundle_sha256}:{context.structure_sha256}:{context.model_id}"
    if (context.mapping.reference_sequence != reference_sequence
            or context.mapping.method != "exact"
            or context.chain_id != polymer.chain_id
            or context.structure_member != context.model_id
            or polymer.frame_id != expected_frame
            or not context.sequence_member or not context.sequence_sha256
            or polymer.source != f"{context.sequence_member}; sha256={context.sequence_sha256}"):
        raise DomainAnnotationError("ColabFold context reference/model/chain/polymer evidence mismatch")
    prepared = prepare_domain_input(context.structure_text, polymer, reference_sequence,
                                    source_sha256=context.structure_sha256)
    coordinates = expected_ca_coordinates(prepared)
    if len(context.mapping.residues) != len(prepared.sequence):
        raise DomainAnnotationError("ColabFold reference mapping must span the complete polymer")
    for position, (entry, residue, coordinate) in enumerate(
        zip(context.mapping.residues, prepared.residues, coordinates, strict=True), 1
    ):
        if (type(entry.reference_position) is not int or type(entry.polymer_position) is not int
                or entry.reference_position != position or entry.polymer_position != position
                or entry.residue_id != residue or entry.reference_aa != prepared.sequence[position - 1]
                or entry.polymer_aa != entry.reference_aa or entry.missing_reason is not None
                or entry.coordinate is None or len(entry.coordinate) != 3
                or any(type(value) not in (int, float) for value in entry.coordinate)
                or entry.coordinate != coordinate):
            raise DomainAnnotationError("ColabFold reference mapping differs from original atom identity/coordinates")
    return prepared


def expected_ca_coordinates(prepared: DomainInput) -> tuple[tuple[float, float, float], ...]:
    """Revalidate normalized full-atom structure and return CA coordinates in order.

    Checking hashes alone cannot establish that a hand-constructed DomainInput
    meets the full-atom input contract. Reapply the existing gate to the normalized
    structure with explicit 1..N identities before accepting its feature frame.
    """
    prepared.check_consistency()
    polymer = PolymerRecord(prepared.sequence, prepared.polymer_source, prepared.frame_id,
                            "1", "A", tuple(ResidueId("1", "A", i)
                                             for i in range(1, len(prepared.sequence) + 1)))
    validated = prepare_domain_input(prepared.normalized_pdb, polymer, prepared.sequence,
                                     source_sha256=prepared.normalized_sha256)
    if validated.normalized_pdb != prepared.normalized_pdb:
        raise DomainAnnotationError("Normalized domain input is not the exact full-atom export")
    coordinates = tuple((float(line[30:38]), float(line[38:46]), float(line[46:54]))
                        for line in prepared.normalized_pdb.splitlines()
                        if line.startswith("ATOM  ") and line[12:16].strip() == "CA")
    if len(coordinates) != len(prepared.sequence):
        raise DomainAnnotationError("Normalized input must have one canonical CA record per residue")
    try:
        if any(not math.isfinite(struct.unpack("f", struct.pack("f", value))[0])
               for xyz in coordinates for value in xyz):
            raise OverflowError
    except OverflowError as exc:
        raise DomainAnnotationError("CA coordinates exceed the supported finite float32 feature range") from exc
    return coordinates


def _number(value: Any, label: str) -> float:
    if type(value) not in (int, float):
        raise DomainAnnotationError(f"{label} must be finite numeric data")
    try:
        result = float(value)
    except OverflowError as exc:
        raise DomainAnnotationError(f"{label} must be finite numeric data") from exc
    if not math.isfinite(result):
        raise DomainAnnotationError(f"{label} must be finite numeric data")
    return result


def _integer(value: Any, expected: int, label: str) -> None:
    if type(value) is not int or value != expected:
        raise DomainAnnotationError(f"{label} mismatch")


def _positions(value: Any, nres: int, label: str) -> None:
    if (not isinstance(value, list) or len(value) != nres
            or any(type(p) is not int or p != i for i, p in enumerate(value, 1))):
        raise DomainAnnotationError(f"{label} must preserve every normalized residue in order")


def _json(text: str) -> dict[str, Any]:
    if not isinstance(text, str):
        raise DomainAnnotationError("Result must be JSON text")
    try:
        if len(text.encode("utf-8")) > MAX_RESULT_BYTES:
            raise DomainAnnotationError("Result exceeds size limit")
    except UnicodeError as exc:
        raise DomainAnnotationError("Result must be valid UTF-8 text") from exc

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise DomainAnnotationError("Duplicate result JSON key")
            result[key] = value
        return result

    def invalid(value: str) -> Any:
        raise DomainAnnotationError(f"Nonfinite JSON constant {value}")

    try:
        data = json.loads(text, object_pairs_hook=pairs, parse_constant=invalid,
                          parse_float=lambda value: _number(float(value), "JSON number"))
    except (ValueError, RecursionError) as exc:
        raise DomainAnnotationError(f"Invalid result JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise DomainAnnotationError("Result must be an object")
    return data


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _segments(positions: Sequence[int]) -> tuple[DomainSegment, ...]:
    segments: list[DomainSegment] = []
    for position in positions:
        if segments and position == segments[-1].end + 1:
            segments[-1] = DomainSegment(segments[-1].start, position)
        else:
            segments.append(DomainSegment(position, position))
    return tuple(segments)


def decode_merizo_result(text: str, prepared: DomainInput, *,
                         current_binding_sha256: str) -> DomainAnnotation:
    """Decode a bounded run envelope against the exact current scientific input.

    Required envelope: schema/tool_commit/weights_sha256/input, process
    {status, exit_code, warnings}, features {nres, sequence, residue_numbers,
    ca_coordinates}, prediction {nres, ndom, labels, residue_numbers, confidence,
    time_sec}. Labels are nonnegative integers; zero is unassigned. Positive
    labels need not be consecutive or sorted. Domain order is first occurrence.
    Empty/all-zero predictions are inconclusive and refused conservatively.

    The process owner must enforce its CPU-only, bounded/cancellable execution
    contract separately and compare binding again before committing async state.
    """
    prepared.check_consistency()
    if prepared.binding_sha256 != current_binding_sha256:
        raise DomainAnnotationError("Stale domain result for a superseded input")
    coordinates = expected_ca_coordinates(prepared)
    data = _json(text)
    for key, expected in {
        "schema": "kuma-merizo-result-v1", "tool_commit": MERIZO_COMMIT,
        "weights_sha256": MERIZO_WEIGHTS_SHA256, "input": domain_input_manifest(prepared),
    }.items():
        # Canonical JSON comparison rejects bool/int equivalence inside mapping.
        if _canonical(data.get(key)) != _canonical(expected):
            raise DomainAnnotationError(f"Result {key} mismatch")
    process, features, prediction = (data.get(k) for k in ("process", "features", "prediction"))
    if not all(isinstance(record, dict) for record in (process, features, prediction)):
        raise DomainAnnotationError("Explicit process, features and prediction records required")
    assert isinstance(process, dict) and isinstance(features, dict) and isinstance(prediction, dict)
    _integer(process.get("exit_code"), 0, "Process exit")
    if process.get("status") != "ok" or process.get("warnings") != []:
        raise DomainAnnotationError("External failure, warnings or missing status evidence")
    nres = len(prepared.residues)
    for record, name in ((features, "Feature"), (prediction, "Prediction")):
        _integer(record.get("nres"), nres, f"{name} residue count")
        _positions(record.get("residue_numbers"), nres, f"{name} residue identities")
    if features.get("sequence") != prepared.sequence:
        raise DomainAnnotationError("Feature sequence differs from the complete reference")
    actual = features.get("ca_coordinates")
    if not isinstance(actual, list) or len(actual) != nres:
        raise DomainAnnotationError("Feature CA coordinate count mismatch")
    for position, (xyz, expected_xyz) in enumerate(zip(actual, coordinates, strict=True), 1):
        if not isinstance(xyz, list) or len(xyz) != 3:
            raise DomainAnnotationError("Feature CA coordinates must have three components")
        # Permit only the original parsed value or its exact float32 rounding.
        # A fixed tolerance either admits changed small coordinates or rejects
        # valid float32 coordinates near the limits of the PDB field width.
        if any(_number(value, f"CA coordinate {position}") not in
               (expected_value, struct.unpack("f", struct.pack("f", expected_value))[0])
               for value, expected_value in zip(xyz, expected_xyz, strict=True)):
            raise DomainAnnotationError("Feature CA coordinates differ from the full-atom input")
    confidence = _number(prediction.get("confidence"), "Prediction confidence")
    if not 0 <= confidence <= 1 or _number(prediction.get("time_sec"), "Prediction time") < 0:
        raise DomainAnnotationError("Prediction numeric values outside supported range")
    labels = prediction.get("labels")
    if (not isinstance(labels, list) or len(labels) != nres
            or any(type(label) is not int or not 0 <= label <= 2**31 - 1 for label in labels)):
        raise DomainAnnotationError("Prediction labels must be one nonnegative int32 per input residue")
    grouped: dict[int, list[int]] = {}
    for position, label in enumerate(labels, 1):
        if label:
            grouped.setdefault(label, []).append(position)
    if not grouped:
        raise DomainAnnotationError("Empty prediction is inconclusive, not domain absence")
    _integer(prediction.get("ndom"), len(grouped), "Domain count")
    domains = tuple(StructuralDomain(_segments(positions), tuple(positions),
                                    tuple(prepared.residues[p - 1] for p in positions))
                    for positions in grouped.values())
    unassigned = tuple(i for i, label in enumerate(labels, 1) if label == 0)
    assigned = nres - len(unassigned)
    return DomainAnnotation(prepared.binding_sha256, domains, unassigned, assigned,
                            nres, assigned / nres, confidence)


def summarize_domain_selection(
    annotation: DomainAnnotation, prepared: DomainInput, selected_variants: Sequence[str], *,
    current_binding_sha256: str,
) -> dict[str, Any]:
    """Describe an already-selected single-site set without changing it or its N.

    Per-domain selected-variant fractions use the selected set as denominator;
    residue fractions use the complete reference. Unique sites are reported
    separately so several substitutions at one site do not imply extra coverage.
    Duplicate variant IDs are refused, never deduplicated or counted twice;
    different substitutions at the same site each count as one selected variant.
    No candidates, scores, weights or selector inputs are accepted or produced.
    Domain indices are 1-based presentation ordinals; unassigned uses null.
    """
    prepared.check_consistency()
    if prepared.binding_sha256 != current_binding_sha256 or annotation.binding_sha256 != prepared.binding_sha256:
        raise DomainAnnotationError("Stale annotation or selected set for a superseded input")
    nres = len(prepared.sequence)
    _integer(annotation.total_residues, nres, "Annotation residue count")
    membership: dict[int, int | None] = {}
    for index, domain in enumerate(annotation.domains, 1):
        positions = domain.reference_positions
        if (not positions or any(type(p) is not int or not 1 <= p <= nres for p in positions)
                or tuple(sorted(set(positions))) != positions
                or any(type(segment.start) is not int or type(segment.end) is not int
                       for segment in domain.segments)
                or domain.segments != _segments(positions)
                or domain.source_residues != tuple(prepared.residues[p - 1] for p in positions)
                or any(p in membership for p in positions)):
            raise DomainAnnotationError("Annotation domain partition or source identity mismatch")
        membership.update((p, index) for p in positions)
    unassigned = tuple(p for p in range(1, nres + 1) if p not in membership)
    assigned = len(membership)
    if (annotation.unassigned_positions != unassigned
            or any(type(p) is not int for p in annotation.unassigned_positions)
            or not annotation.domains):
        raise DomainAnnotationError("Annotation unassigned partition mismatch")
    _integer(annotation.assigned_residues, assigned, "Annotation assigned residue count")
    if (_number(annotation.coverage, "Annotation coverage") != assigned / nres
            or not 0 <= _number(annotation.confidence, "Annotation confidence") <= 1):
        raise DomainAnnotationError("Annotation coverage/confidence mismatch")
    membership.update((p, None) for p in unassigned)
    if isinstance(selected_variants, (str, bytes)) or not isinstance(selected_variants, Sequence):
        raise DomainAnnotationError("Selected variants must be an ordered sequence")
    seen: set[str] = set()
    selected: list[dict[str, Any]] = []
    for variant in selected_variants:
        match = re.fullmatch(r"([ACDEFGHIKLMNPQRSTVWY])([1-9]\d{0,3})([ACDEFGHIKLMNPQRSTVWY])", variant) if isinstance(variant, str) else None
        if match is None:
            raise DomainAnnotationError("Domain distribution supports single-site substitutions only")
        position = int(match[2])
        if (variant in seen or position > nres or prepared.sequence[position - 1] != match[1]
                or match[1] == match[3]):
            raise DomainAnnotationError("Selected variant duplicate/reference/substitution mismatch")
        seen.add(variant)
        selected.append({"variant": variant, "reference_position": position,
                         "domain_index": membership[position]})
    buckets: list[dict[str, Any]] = []
    for index in (*range(1, len(annotation.domains) + 1), None):
        entries = [row for row in selected if row["domain_index"] == index]
        positions = unassigned if index is None else annotation.domains[index - 1].reference_positions
        buckets.append({"domain_index": index, "residue_count": len(positions),
                        "reference_fraction": len(positions) / nres,
                        "selected_variants": [row["variant"] for row in entries],
                        "selected_variant_count": len(entries),
                        "selected_site_count": len({row["reference_position"] for row in entries}),
                        "selected_variant_fraction": len(entries) / len(selected) if selected else None})
    return {"binding_sha256": prepared.binding_sha256, "total_residues": nres,
            "domain_coverage": annotation.coverage,
            "selected_variant_count": len(selected),
            "selected_site_count": len({row["reference_position"] for row in selected}),
            "selected_variants": list(selected_variants), "memberships": selected, "buckets": buckets,
            "interpretation": "descriptive_structural_partition_only_no_selection_or_function_inference"}
