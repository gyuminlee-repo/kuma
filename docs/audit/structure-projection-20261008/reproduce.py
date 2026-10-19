"""Synthetic observations of the audited source, not a projection implementation.

No network/model calls or biological candidate inputs. Prints JSON to stdout.
Use a checkout containing the audited commit and the project's Python deps.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

AUDITED_SHA = "9b9fd8682ba97a225a839d00f21b6ec7cc5b50f4"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[3])
    root = parser.parse_args().source_root.resolve()
    paths = [
        "kuma_core/kuro/interface.py", "kuma_core/kuro/alphafold.py",
        "kuma_core/kuro/evolvepro.py", "kuma_core/kuro/dispersion.py",
        "python-core/sidecar_kuro/handlers/misc.py",
    ]
    hashes = {}
    for path in paths:
        old = subprocess.check_output(["git", "-C", str(root), "show", f"{AUDITED_SHA}:{path}"])
        current = (root / path).read_bytes()
        if old != current:
            raise RuntimeError(f"Audited source differs: {path}")
        hashes[path] = hashlib.sha256(current).hexdigest()
    sys.path[:0] = [str(root), str(root / "python-core")]
    import Bio
    from kuma_core.kuro import interface, alphafold, evolvepro, dispersion
    # Isolate the exact guard function without importing unrelated primer sidecar deps.
    guard_path = root / "python-core/sidecar_kuro/handlers/misc.py"
    parsed = ast.parse(guard_path.read_text())
    node = next(n for n in parsed.body if isinstance(n, ast.FunctionDef) and n.name == "_frame_checked_ca_coords")
    guard_namespace = {}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(guard_path), "exec"), guard_namespace)
    for module in [interface, alphafold, evolvepro, dispersion]:
        if not Path(module.__file__).resolve().is_relative_to(root):
            raise RuntimeError(f"Unexpected module origin: {module.__name__}")

    results = []

    def check(name, expected, observed):
        if expected != observed:
            raise AssertionError((name, expected, observed))
        results.append({"case": name, "expected": expected, "observed": observed})

    ref = "ACDEFGHIKLMNPQRSTVWY"
    coords = [None] + [(float(i * i), 0., 0.) for i in range(1, len(ref) + 1)]

    def guard(sequence, ca=coords):
        with patch.dict(guard_namespace, {"_get_cached_ca_seq": lambda _accession: sequence}):
            return guard_namespace["_frame_checked_ca_coords"](ca, "file:synthetic.pdb", ref)

    check("exact gate", True, interface.structure_matches_reference(ref, ref))
    for name, seq in [("one substitution", ref[:8] + "A" + ref[9:]), ("structure N-terminal deletion", ref[1:])]:
        c, flag = guard(seq)
        check(name, [False, True, True], [interface.structure_matches_reference(seq, ref), c is None, flag])
    mapping = interface._build_position_map(ref, ref[:8] + "A" + ref[9:])
    check("substitution preserves position correspondence", {i: i for i in range(1, 21)}, mapping)
    deleted = interface._build_position_map(ref, ref[1:])
    check("terminal gap is absent, subsequent positions shifted", [False, 1], [1 in deleted, deleted[2]])
    tagged = [None, (999., 0., 0.), (998., 0., 0.)] + coords[1:]
    c, flag = guard("HH" + ref, tagged)
    check("accepted tag does not reindex", [True, False, 999., 1.], [c is tagged, flag, c[1][0], tagged[3][0]])
    check("empty structure sequence guard is open", [True, False], [guard("")[0] is coords, guard("")[1]])
    check("missing pair CA returns maximum distance", 1., alphafold.pairwise_ca_distance([None, (0.,0.,0.), None], 1, 2, 10.))
    with patch.object(dispersion, "fetch_ca_coords", return_value=coords), patch.object(dispersion, "fetch_ca_seq", return_value=ref[:8] + "A" + ref[9:]):
        d = dispersion.compute_round_dispersion("SYNTHETIC", ref, [1, 9, 19], n_trials=10, seed=7)
    check("dispersion remaps despite selector gate", [3, [1, 9, 19]], [d["n_positions"], d["mapped"]])
    rows = [("A1G", 3.), ("C2G", 2.), ("D3G", 1.)]
    before = [None, (0.,0.,0.), (10.,0.,0.), None]
    after = [None, (1000.,1000.,1000.), (1010.,1000.,1000.), None]
    chosen = [evolvepro.structural_diversity_select(rows, 2, ca_coords=c)[0][1][0] for c in [before, after]]
    check("mixed fallback loses translation invariance", ["C2G", "D3G"], chosen)
    before[3], after[3] = (3.,3.,3.), (1003.,1003.,1003.)
    chosen = [evolvepro.structural_diversity_select(rows, 2, ca_coords=c)[0][1][0] for c in [before, after]]
    check("complete coverage translation control", ["C2G", "C2G"], chosen)

    def atom(n, chain="A", x=1., insertion=" "):
        line = f"ATOM      1  CA  ALA {chain}{n:4d}{insertion}   {x:8.3f}{0.:8.3f}{0.:8.3f}  1.00 20.00           C"
        if line[21] != chain or line[26] != insertion:
            raise AssertionError("fixture columns")
        return line

    check("PDB combines chains by residue integer", [None, (1.,0.,0.), (200.,0.,0.)], alphafold._parse_pdb_ca(atom(1) + "\n" + atom(2, "B", 200.)))
    check("PDB insertion code collapses", [None, (1.,0.,0.)], alphafold._parse_pdb_ca(atom(1) + "\n" + atom(1, x=99., insertion="A")))
    multi = "\n".join(["MODEL        1", atom(1), "ENDMDL", "MODEL        2", atom(2, x=99.), "ENDMDL"])
    check("PDB later model fills absent first-model residue", [None, (1.,0.,0.), (99.,0.,0.)], alphafold._parse_pdb_ca(multi))
    print(json.dumps({"audited_sha": AUDITED_SHA, "python": sys.version.split()[0], "biopython": Bio.__version__, "source_sha256": hashes, "guard_execution": "unchanged AST-extracted function; cache lookup stubbed; not sidecar integration", "assertions_passed": len(results), "results": results}, indent=2))


if __name__ == "__main__":
    main()
