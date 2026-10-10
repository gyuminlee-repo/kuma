"""Mock scientific interchange tests, not native Merizo or accuracy evidence.

Runnable with stdlib unittest while the optional runtime is absent. The public
1UBQ file tests atom preservation; short synthetic structures test variable
lengths and are explicitly not genuine ColabFold producer outputs.
"""
from __future__ import annotations

import copy
import hashlib
import json
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any
from unittest.mock import patch

from kuma_core.kuro.domain_annotation import (
    DomainAnnotationError, DomainSegment, prepare_domain_input,
)
from kuma_core.kuro.domain_merizo import (
    AF3_UNSUPPORTED_REASON, MERIZO_COMMIT, MERIZO_WEIGHTS_SHA256,
    decode_merizo_result, domain_input_manifest, expected_ca_coordinates,
    prepare_colabfold_domain_input, summarize_domain_selection,
)
from kuma_core.kuro.prediction_bundle import load_prediction_bundle
from kuma_core.kuro.residue_mapping import PolymerRecord, ResidueId

ROOT = Path(__file__).parents[1]
PDB = ROOT / "tests" / "data" / "domain_annotation" / "1ubq.pdb"
SEQUENCE = "MQIFVKTLTGKTITLEVEPSDTIENVKAKIQDKEGIPPDQQRLIFAGKQLEDGRTLSDYNIQKESTLHLVLRLRGG"
MODEL = "synthetic_unrelaxed_rank_001_alphafold2_ptm_model_1_seed_000.pdb"
SCORES = "synthetic_scores_rank_001_alphafold2_ptm_model_1_seed_000.json"
AA = dict(zip("ACDEFGHIKLMNPQRSTVWY", "ALA CYS ASP GLU PHE GLY HIS ILE LYS LEU MET ASN PRO GLN ARG SER THR VAL TRP TYR".split(), strict=True))


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def synthetic(sequence: str = "ACDEFG", *, chain: str = "B", offset: int = 100,
              insertion: bool = True) -> tuple[str, PolymerRecord]:
    """Synthetic complete backbones plus side-chain CB, not biological geometry."""
    lines: list[str] = []
    identities: list[ResidueId] = []
    for position, aa in enumerate(sequence, 1):
        number = offset + position - (1 if insertion and position == 3 else 0)
        code = "A" if insertion and position == 3 else ""
        identities.append(ResidueId("1", chain, number, code))
        for atom in ("N", "CA", "C", "O", "CB"):
            serial = len(lines) + 1
            lines.append(f"ATOM  {serial:5d} {atom:^4} {AA[aa]:3} {chain}{number:4d}{code or ' ' }   "
                         f"{position * 2.123:8.3f}{serial * 1.111:8.3f}{-position * 3.234:8.3f}"
                         f"{1.0:6.2f}{90.0:6.2f}          {atom[0]:>2}  ")
    source = "\n".join(lines) + "\nEND\n"
    polymer = PolymerRecord(sequence, "synthetic independent polymer", "synthetic-original-frame",
                            "1", chain, tuple(identities))
    return source, polymer


def prepared_synthetic(sequence: str = "ACDEFG"):
    source, polymer = synthetic(sequence)
    return prepare_domain_input(source, polymer, sequence, source_sha256=digest(source))


def envelope(prepared, labels: list[int] | None = None) -> dict[str, Any]:
    nres = len(prepared.sequence)
    labels = [1] * nres if labels is None else labels
    return {"schema": "kuma-merizo-result-v1", "tool_commit": MERIZO_COMMIT,
            "weights_sha256": dict(MERIZO_WEIGHTS_SHA256), "input": domain_input_manifest(prepared),
            "process": {"status": "ok", "exit_code": 0, "warnings": []},
            "features": {"nres": nres, "sequence": prepared.sequence,
                         "residue_numbers": list(range(1, nres + 1)),
                         "ca_coordinates": [list(xyz) for xyz in expected_ca_coordinates(prepared)]},
            "prediction": {"nres": nres, "ndom": len(set(labels) - {0}), "labels": labels,
                           "residue_numbers": list(range(1, nres + 1)), "confidence": 0.91, "time_sec": 0.2}}


def decode(prepared, result):
    return decode_merizo_result(json.dumps(result), prepared,
                                current_binding_sha256=prepared.binding_sha256)


class MerizoScientificContractTests(unittest.TestCase):
    def test_preserves_every_public_atom_without_runtime_imports(self):
        source = PDB.read_text()
        self.assertEqual(digest(source), "d4a6812d8951cf6594e6a0763f089e35f5a80b62acb3c117b2c5565228a7b161")
        polymer = PolymerRecord(SEQUENCE, "RCSB 1UBQ SEQRES", "1ubq-public-pdb", "1", "A",
                                tuple(ResidueId("1", "A", p) for p in range(1, 77)))
        prepared = prepare_domain_input(source, polymer, SEQUENCE, source_sha256=digest(source))
        before = [line for line in source.splitlines() if line.startswith("ATOM  ")]
        after = [line for line in prepared.normalized_pdb.splitlines() if line.startswith("ATOM  ")]
        self.assertEqual(len(before), 602)
        self.assertEqual(before, after)
        self.assertEqual(len(expected_ca_coordinates(prepared)), 76)
        self.assertEqual(decode(prepared, envelope(prepared)).coverage, 1)
        run = subprocess.run([sys.executable, "-c", (
            "import sys; import kuma_core.kuro.domain_merizo; "
            "assert not any(k.split('.')[0] in {'torch','numpy','Bio'} for k in sys.modules)"
        )], cwd=ROOT, text=True, capture_output=True, check=False)
        self.assertEqual(run.returncode, 0, run.stderr)

    def test_general_lengths_discontinuities_unassigned_and_inverse_mapping(self):
        prepared = prepared_synthetic()
        result = decode(prepared, envelope(prepared, [42, 0, 7, 42, 7, 0]))
        self.assertEqual(len(result.domains), 2)
        self.assertEqual(result.domains[0].segments, (DomainSegment(1, 1), DomainSegment(4, 4)))
        self.assertEqual(result.domains[1].reference_positions, (3, 5))
        self.assertEqual(result.domains[1].source_residues[0], ResidueId("1", "B", 102, "A"))
        self.assertEqual(result.unassigned_positions, (2, 6))
        self.assertEqual(result.total_residues, 6)
        self.assertEqual(result.assigned_residues, 4)
        self.assertEqual(result.coverage, 4 / 6)
        self.assertIn("structural_partition_only", result.interpretation)
        for sequence in ("A", "ACDE", "ACDEFGHIKLMNPQRSTVWY" * 5):
            with self.subTest(length=len(sequence)):
                sample = prepared_synthetic(sequence)
                self.assertEqual(decode(sample, envelope(sample)).assigned_residues, len(sequence))

    def test_neutral_manifest_does_not_change_legacy_contract(self):
        prepared = prepared_synthetic()
        self.assertEqual(prepared.manifest()["schema"], "kuma-chainsaw-input-v1")
        neutral = domain_input_manifest(prepared)
        self.assertEqual(neutral["schema"], "kuma-domain-input-v1")
        self.assertEqual(neutral["binding_sha256"], prepared.binding_sha256)
        self.assertEqual(neutral["residues"][2]["insertion_code"], "A")
        neutral["residues"][0]["author_number"] = 999
        self.assertEqual(prepared.residues[0].author_number, 101)

    def test_refuses_all_stale_binding_components(self):
        prepared = prepared_synthetic()
        cases = [(key, "wrong") for key in (
            "source_sha256", "reference_sha256", "normalized_sha256", "binding_sha256",
            "polymer_source", "frame_id", "model_id", "chain_id", "sequence", "normalized_chain", "normalized_model",
        )]
        for key, value in cases:
            with self.subTest(field=key):
                result = envelope(prepared)
                result["input"][key] = value
                with self.assertRaises(DomainAnnotationError):
                    decode(prepared, result)
        for key in ("reference_position", "polymer_position", "normalized_position", "author_number"):
            with self.subTest(mapping=key):
                result = envelope(prepared)
                result["input"]["residues"][0][key] = True
                with self.assertRaises(DomainAnnotationError):
                    decode(prepared, result)
        with self.assertRaisesRegex(DomainAnnotationError, "Stale"):
            decode_merizo_result(json.dumps(envelope(prepared)), prepared, current_binding_sha256="new-input")

    def test_malformed_process_features_predictions_fail_closed(self):
        prepared = prepared_synthetic()
        cases = [
            ("process", "status", "failed"), ("process", "exit_code", 1),
            ("process", "exit_code", False), ("process", "warnings", ["warning"]),
            ("features", "sequence", "CDEFGH"), ("features", "nres", 5),
            ("features", "nres", True), ("features", "residue_numbers", [1, 2, 3, 4, 5, 5]),
            ("features", "residue_numbers", [True, 2, 3, 4, 5, 6]),
            ("features", "residue_numbers", [1., 2, 3, 4, 5, 6]),
            ("features", "ca_coordinates", [[0, 0, 0]] * 6),
            ("features", "ca_coordinates", []), ("features", "ca_coordinates", [None] * 6),
            ("prediction", "nres", 5), ("prediction", "nres", True),
            ("prediction", "ndom", 0), ("prediction", "ndom", True),
            ("prediction", "residue_numbers", [6, 5, 4, 3, 2, 1]),
            ("prediction", "residue_numbers", [True, 2, 3, 4, 5, 6]),
            ("prediction", "labels", [1] * 5), ("prediction", "labels", [0] * 6),
            ("prediction", "labels", [-1] * 6), ("prediction", "labels", [True] * 6),
            ("prediction", "labels", [1.] * 6), ("prediction", "labels", [2**31] * 6),
            ("prediction", "labels", ["1"] * 6), ("prediction", "labels", None),
            ("prediction", "confidence", -0.01), ("prediction", "confidence", 1.01),
            ("prediction", "confidence", True), ("prediction", "confidence", float("nan")),
            ("prediction", "confidence", float("inf")), ("prediction", "time_sec", -0.1),
            ("prediction", "time_sec", True), ("prediction", "time_sec", "0.2"),
        ]
        for section, key, value in cases:
            with self.subTest(section=section, key=key, value=value):
                result = envelope(prepared)
                result[section][key] = value
                with self.assertRaises(DomainAnnotationError):
                    decode(prepared, result)

    def test_required_records_and_pins(self):
        prepared = prepared_synthetic()
        for key in envelope(prepared):
            with self.subTest(missing=key):
                result = envelope(prepared)
                del result[key]
                with self.assertRaises(DomainAnnotationError):
                    decode(prepared, result)
        for key, value in (("schema", "kuma-chainsaw-result-v1"), ("tool_commit", "latest"),
                           ("weights_sha256", {"weights_part_0.pt": "0" * 64}),
                           ("process", []), ("features", None), ("prediction", "success")):
            with self.subTest(field=key):
                result = envelope(prepared)
                result[key] = value
                with self.assertRaises(DomainAnnotationError):
                    decode(prepared, result)

    def test_strict_json_duplicates_nonfinite_types_depth_and_size(self):
        prepared = prepared_synthetic()
        for text in ("[]", "null", "{", '{"a":1,"a":2}', '{"a": {"x":1,"x":2}}',
                     '{"unused": 1e999}', '{"unused": NaN}', "[" * 2000, "\ud800"):
            with self.subTest(text=text[:30]):
                with self.assertRaises(DomainAnnotationError):
                    decode_merizo_result(text, prepared, current_binding_sha256=prepared.binding_sha256)
        with patch("kuma_core.kuro.domain_merizo.MAX_RESULT_BYTES", 30):
            with self.assertRaisesRegex(DomainAnnotationError, "size"):
                decode(prepared, envelope(prepared))

    def test_coordinate_roundoff_only_and_finite_three_component_contract(self):
        prepared = prepared_synthetic()
        result = envelope(prepared)
        result["features"]["ca_coordinates"] = [
            [struct.unpack("f", struct.pack("f", v))[0] for v in xyz]
            for xyz in result["features"]["ca_coordinates"]]
        self.assertEqual(decode(prepared, result).total_residues, 6)
        for value in (True, "2.123", float("inf"), float("nan"), 2.12301):
            with self.subTest(value=value):
                result = envelope(prepared)
                result["features"]["ca_coordinates"][0][0] = value
                with self.assertRaises(DomainAnnotationError):
                    decode(prepared, result)
        for vector in ([1, 2], [1, 2, 3, 4], None):
            result = envelope(prepared)
            result["features"]["ca_coordinates"][0] = vector
            with self.assertRaises(DomainAnnotationError):
                decode(prepared, result)

    def test_large_valid_pdb_coordinates_allow_exact_float32_rounding(self):
        source, polymer = synthetic("AC")
        source = "\n".join(line[:30] + "9999.999" + line[38:] if line.startswith("ATOM  ") else line
                           for line in source.splitlines()) + "\n"
        prepared = prepare_domain_input(source, polymer, polymer.sequence, source_sha256=digest(source))
        result = envelope(prepared)
        result["features"]["ca_coordinates"] = [
            [struct.unpack("f", struct.pack("f", v))[0] for v in xyz]
            for xyz in result["features"]["ca_coordinates"]]
        self.assertGreater(abs(result["features"]["ca_coordinates"][0][0] - 9999.999), 0.00001)
        self.assertEqual(decode(prepared, result).assigned_residues, 2)

    def test_finite_source_outside_float32_feature_range_is_refused_cleanly(self):
        source, polymer = synthetic("AC")
        source = "\n".join(line[:30] + "   1e+39" + line[38:] if line.startswith("ATOM  ") else line
                           for line in source.splitlines()) + "\n"
        prepared = prepare_domain_input(source, polymer, polymer.sequence, source_sha256=digest(source))
        with self.assertRaisesRegex(DomainAnnotationError, "float32"):
            expected_ca_coordinates(prepared)

    def test_self_consistent_hashes_alone_cannot_allow_ca_only_input(self):
        prepared = prepared_synthetic()
        normalized = "\n".join(line for line in prepared.normalized_pdb.splitlines()
                               if line[12:16].strip() == "CA") + "\nTER\nEND\n"
        normalized_hash = digest(normalized)
        binding = digest(json.dumps({"source": prepared.source_sha256, "reference": prepared.reference_sha256,
                                     "normalized": normalized_hash, "polymer_source": prepared.polymer_source,
                                     "frame": prepared.frame_id, "model": prepared.model_id,
                                     "chain": prepared.chain_id, "residues": [asdict(r) for r in prepared.residues]},
                                    sort_keys=True, separators=(",", ":")))
        changed = replace(prepared, normalized_pdb=normalized, normalized_sha256=normalized_hash,
                          binding_sha256=binding)
        changed.check_consistency()
        with self.assertRaisesRegex(DomainAnnotationError, "N/CA/C/O"):
            expected_ca_coordinates(changed)

    def test_prepared_hash_changes_and_ca_only_are_refused(self):
        prepared = prepared_synthetic()
        with self.assertRaises(DomainAnnotationError):
            expected_ca_coordinates(replace(prepared, normalized_pdb=prepared.normalized_pdb + "\n"))
        source, polymer = synthetic()
        for change in ("ca_only", "missing_o", "alternate", "duplicate_atom", "missing_residue", "wrong_residue"):
            with self.subTest(change=change):
                lines = source.splitlines()
                if change == "ca_only":
                    lines = [line for line in lines if line[12:16].strip() == "CA"]
                elif change == "missing_o":
                    lines = [line for line in lines if line[12:16].strip() != "O"]
                elif change == "alternate":
                    lines[0] = lines[0][:16] + "A" + lines[0][17:]
                elif change == "duplicate_atom":
                    lines.insert(0, lines[0])
                elif change == "missing_residue":
                    lines = [line for line in lines if line[22:26].strip() != "101"]
                else:
                    lines[0] = lines[0][:17] + "TYR" + lines[0][20:]
                changed = "\n".join(lines) + "\n"
                with self.assertRaises(DomainAnnotationError):
                    prepare_domain_input(changed, polymer, polymer.sequence, source_sha256=digest(changed))

    def test_original_model_chain_reference_and_mapping_are_bound(self):
        source, polymer = synthetic()
        atoms = "\n".join(line for line in source.splitlines() if line.startswith("ATOM  "))
        source = "MODEL        1\n" + atoms + "\nENDMDL\nMODEL        2\n" + atoms + "\nENDMDL\n"
        first = prepare_domain_input(source, polymer, polymer.sequence, source_sha256=digest(source))
        second_polymer = replace(polymer, model_id="2", residues_by_position=tuple(
            replace(r, model_id="2") for r in polymer.residues_by_position if r is not None))
        second = prepare_domain_input(source, second_polymer, polymer.sequence, source_sha256=digest(source))
        self.assertEqual(first.normalized_pdb, second.normalized_pdb)
        self.assertNotEqual(first.binding_sha256, second.binding_sha256)
        with self.assertRaises(DomainAnnotationError):
            decode(second, envelope(first))

    def test_colabfold_helper_reuses_full_atom_context_and_refuses_af3(self):
        source, polymer = synthetic(insertion=False)
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "synthetic-colabfold.zip"
            with zipfile.ZipFile(bundle, "w") as archive:
                archive.writestr(MODEL, source)
                archive.writestr(SCORES, json.dumps({"plddt": [90] * len(polymer.sequence)}))
                archive.writestr("synthetic.a3m", ">query\n" + polymer.sequence + "\n")
            context = load_prediction_bundle(bundle, MODEL, "B", polymer.sequence)
            prepared = prepare_colabfold_domain_input(context, polymer.sequence)
            atoms = [line for line in source.splitlines() if line.startswith("ATOM  ")]
            normalized = [line for line in prepared.normalized_pdb.splitlines() if line.startswith("ATOM  ")]
            self.assertEqual(len(normalized), 30)
            self.assertTrue(all(a[:21] == b[:21] and a[27:] == b[27:]
                                for a, b in zip(atoms, normalized, strict=True)))
            self.assertEqual(decode(prepared, envelope(prepared)).total_residues, 6)
            bad_position = replace(context.mapping.residues[0], reference_position=True)
            bad_coordinate = replace(context.mapping.residues[0], coordinate=(0., 0., 0.))
            for changed in (replace(context, chain_id="A"), replace(context, model_id="other.pdb"),
                            replace(context, bundle_sha256="0" * 64), replace(context, sequence_sha256=None),
                            replace(context, sequence_member="other.a3m"),
                            replace(context, mapping=replace(context.mapping, residues=context.mapping.residues[:-1])),
                            replace(context, mapping=replace(context.mapping, residues=(bad_position, *context.mapping.residues[1:]))),
                            replace(context, mapping=replace(context.mapping, residues=(bad_coordinate, *context.mapping.residues[1:])))):
                with self.subTest(context=changed.model_id):
                    with self.assertRaises(DomainAnnotationError):
                        prepare_colabfold_domain_input(changed, polymer.sequence)
            with self.assertRaises(DomainAnnotationError):
                prepare_colabfold_domain_input(context, "C" + polymer.sequence[1:])
            with self.assertRaises(DomainAnnotationError) as error:
                prepare_colabfold_domain_input(replace(context, format="af3_server", structure_format="mmcif"), polymer.sequence)
            self.assertEqual(str(error.exception), AF3_UNSUPPORTED_REASON)


class DomainSelectionDistributionTests(unittest.TestCase):
    def setUp(self):
        self.prepared = prepared_synthetic()
        self.annotation = decode(self.prepared, envelope(self.prepared, [42, 0, 7, 42, 7, 0]))

    def summarize(self, variants, annotation=None):
        return summarize_domain_selection(annotation or self.annotation, self.prepared, variants,
                                           current_binding_sha256=self.prepared.binding_sha256)

    def test_preserves_n_order_same_site_variants_and_unassigned_bucket(self):
        variants = ["G6A", "A1V", "A1G", "D3A", "E4A"]
        before = copy.deepcopy(variants)
        result = self.summarize(variants)
        self.assertEqual(variants, before)
        self.assertEqual(result["selected_variants"], variants)
        self.assertEqual(result["selected_variant_count"], 5)
        self.assertEqual(result["selected_site_count"], 4)
        self.assertEqual([row["domain_index"] for row in result["memberships"]], [None, 1, 1, 2, 1])
        buckets = result["buckets"]
        self.assertEqual([b["selected_variant_count"] for b in buckets], [3, 1, 1])
        self.assertEqual([b["selected_site_count"] for b in buckets], [2, 1, 1])
        self.assertEqual(buckets[0]["selected_variant_fraction"], 3 / 5)
        self.assertEqual(buckets[0]["reference_fraction"], 2 / 6)
        self.assertEqual(sum(b["selected_variant_count"] for b in buckets), len(variants))
        self.assertNotIn("fitness", result)
        self.assertNotIn("candidate", result)

    def test_empty_set_has_zero_count_and_undefined_fraction(self):
        result = self.summarize([])
        self.assertEqual(result["selected_variant_count"], 0)
        self.assertTrue(all(b["selected_variant_fraction"] is None for b in result["buckets"]))
        json.dumps(result, allow_nan=False)

    def test_duplicate_unsupported_or_wrong_reference_variants_fail_whole_summary(self):
        for variants in (["A1V", "A1V"], ["A1A"], ["C1A"], ["G7A"], ["A0V"],
                         ["A1V/D3A"], ["WT"], ["A1*"], "A1V", [True], [" A1V"]):
            with self.subTest(variants=variants):
                with self.assertRaises(DomainAnnotationError):
                    self.summarize(variants)

    def test_stale_or_inconsistent_annotations_are_refused(self):
        bad_domains = (replace(self.annotation.domains[0], source_residues=()), *self.annotation.domains[1:])
        for changed in (replace(self.annotation, binding_sha256="stale"),
                        replace(self.annotation, total_residues=5),
                        replace(self.annotation, assigned_residues=True),
                        replace(self.annotation, coverage=1),
                        replace(self.annotation, confidence=float("nan")),
                        replace(self.annotation, unassigned_positions=()),
                        replace(self.annotation, domains=bad_domains),
                        replace(self.annotation, domains=(self.annotation.domains[0],) * 2)):
            with self.subTest(annotation=changed):
                with self.assertRaises(DomainAnnotationError):
                    self.summarize(["A1V"], changed)
        with self.assertRaisesRegex(DomainAnnotationError, "Stale"):
            summarize_domain_selection(self.annotation, self.prepared, ["A1V"], current_binding_sha256="new")


if __name__ == "__main__":
    unittest.main()
