"""Own harness guards only; never loads a model or downloads anything."""
import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("merizo_smoke", ROOT / "scripts/merizo_windows_smoke/run.py")
assert SPEC is not None and SPEC.loader is not None
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)


class SmokeContractTests(unittest.TestCase):
    def test_public_original_and_roundtrip(self):
        raw = (ROOT / "tests/data/domain_annotation/1ubq.pdb").read_bytes()
        self.assertEqual(smoke.sha(raw), smoke.INPUT_SHA)
        normalized, mapping, coordinates = smoke.prepare(raw.decode("ascii"))
        self.assertEqual(len(mapping), 76)
        self.assertEqual(len(coordinates), 76)
        self.assertEqual(sum(line.startswith("ATOM  ") for line in normalized.splitlines()), 602)
        self.assertEqual(smoke.sha(normalized.encode("ascii")), "b3dd4103f338f741fbfcee70f3b01c245ed79b385109e920be1fcc2599634768")

    def test_ca_only_rejected(self):
        raw = (ROOT / "tests/data/domain_annotation/1ubq.pdb").read_text()
        with self.assertRaises(ValueError):
            smoke.prepare("\n".join(line for line in raw.splitlines() if not line.startswith("ATOM  ") or line[12:16].strip() == "CA"))

    def test_prediction_guard(self):
        good = {"nres": 76, "residue_numbers": list(range(1, 77)), "labels": [1] * 76, "ndom": 1, "confidence": 0.8}
        smoke.validate_prediction(good)
        for patch in ({"nres": 75}, {"residue_numbers": list(range(76))}, {"labels": [1] * 75},
                      {"labels": [True] * 76}, {"labels": [-1] * 76}, {"ndom": 0},
                      {"confidence": float("nan")}, {"confidence": 1.1}, {"labels": [0] * 76}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                smoke.validate_prediction({**copy.deepcopy(good), **patch})

    def test_feature_coordinate_guards(self):
        good = [[1.0, 2.0, 3.0] for _ in range(76)]
        smoke.validate_coordinates(good, good)
        for value in (float("nan"), float("inf"), 9.0):
            bad = copy.deepcopy(good)
            bad[0][0] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                smoke.validate_coordinates(bad, good)
        with self.assertRaises(ValueError):
            smoke.validate_coordinates(good[:-1], good)
        with self.assertRaises(ValueError):
            smoke.validate_coordinates([[1.0, 2.0]] * 76, good)

    def test_author_insertion_roundtrip(self):
        raw = (ROOT / "tests/data/domain_annotation/1ubq.pdb").read_text()
        original, _, _ = smoke.prepare(raw)
        lines = []
        for line in raw.splitlines():
            if line.startswith("ATOM  ") and line[21] == "A":
                residue = int(line[22:26])
                number, insertion = (110, "A") if residue == 11 else (residue + 100, " ")
                line = line[:22] + f"{number:4d}" + insertion + line[27:]
            lines.append(line)
        normalized, mapping, _ = smoke.prepare("\n".join(lines))
        self.assertEqual(normalized, original)
        self.assertEqual(mapping[9]["author_number"], 110)
        self.assertEqual(mapping[10]["author_number"], 110)
        self.assertEqual(mapping[10]["insertion_code"], "A")


if __name__ == "__main__":
    unittest.main()
