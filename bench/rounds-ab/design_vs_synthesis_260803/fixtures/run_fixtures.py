"""Put make_fidelity_panel.py through the two fixtures and judge its behaviour.

  (a) fixture A   all eight VerdictClass members present. The script counts
                  every one of them, the tally equals the 288 records read, and
                  it exits 0.
  (b) fixture B   the same input with one verdict reading BOGUS. Exit status is
                  NOT 0 and the message names BOGUS.
  (c) negative    the pre-fix script, taken out of git, is put through the same
      control     two fixtures. It has to behave differently, otherwise the fix
                  changed nothing observable.

(b) is the half with teeth. A script that walks a closed class list and skips
what it does not recognise passes exit-status-only versions of both conditions,
because the record it cannot classify simply leaves the numerator. Requiring the
failure to name BOGUS separates refusing the record from dropping it: an assert
that came out one short would also give a non-zero status without the script
ever having noticed the verdict.

The script runs as a subprocess, because what is being judged is exit status.
Each run gets its own temporary directory holding a copy of the script and the
fixture renamed well_verdicts.csv, because make_fidelity_panel.py resolves both
its input and its output next to itself. Running it in place would overwrite the
manuscript SVGs with fixture artwork.

LIMIT. The tally is read off the script's stdout line "replicate 판정: {...}",
not off the SVG, because the tally is not drawn. That is the point of the fix
being output-neutral and it is also the reason this runner cannot check the
artwork. Byte-identity of the two SVGs before and after the fix is checked
separately, by sha256 against the values recorded in ../README.md.
"""
from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PANEL = HERE.parent / "make_fidelity_panel.py"
REPO = HERE.parents[3]
# The verbatim pre-fix import. Its subject is
# "chore(bench): import the design-vs-synthesis fidelity panel script ...".
PREFIX_REV = "7cd1c1a7"
PANEL_REL = "bench/rounds-ab/design_vs_synthesis_260803/make_fidelity_panel.py"
BOGUS = "BOGUS"
TALLY_MARK = "replicate 판정:"


def run_panel(script_text, fixture):
    """Run a copy of the script on a fixture, in a directory of its own."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "make_fidelity_panel.py").write_text(script_text, encoding="utf-8")
        shutil.copy(fixture, d / "well_verdicts.csv")
        env = dict(os.environ, KUMA_REPO_ROOT=str(REPO))
        p = subprocess.run([sys.executable, str(d / "make_fidelity_panel.py")],
                           capture_output=True, text=True, cwd=str(d), env=env)
        return p.returncode, p.stdout + p.stderr


def tally(text):
    """Pull the per-class dict and its total off the stdout line."""
    for line in text.splitlines():
        if line.startswith(TALLY_MARK):
            body = line[len(TALLY_MARK):].strip()
            dict_text, _, rest = body.partition("} 합 ")
            return ast.literal_eval(dict_text + "}"), int(rest.strip())
    return None, None


CHECKS = []


def report(name, ok, detail):
    CHECKS.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {name:52s} {detail}")
    return ok


def main():
    spec = json.loads((HERE / "fixture_a_spec.json").read_text())
    fix_a = HERE / "fixture_a_well_verdicts.csv"
    fix_b = HERE / "fixture_b_well_verdicts.csv"
    current = PANEL.read_text(encoding="utf-8")
    prefix = subprocess.run(["/usr/bin/git", "-C", str(REPO), "show",
                             f"{PREFIX_REV}:{PANEL_REL}"],
                            capture_output=True, text=True, check=True).stdout

    print("fixture A: all eight VerdictClass members present")
    print("fixture B: fixture A with one verdict replaced by BOGUS")
    print(f"negative control: make_fidelity_panel.py at {PREFIX_REV}\n")

    print("current script:")
    rc, text = run_panel(current, fix_a)
    counted, total = tally(text)
    report("(a) exit 0 on fixture A", rc == 0, f"exit={rc}")
    report("(a) counts all eight classes", counted == spec["expected"],
           f"{counted}")
    report("(a) tally equals the records read",
           total == spec["n_records"], f"sum={total} n={spec['n_records']}")

    rc, text = run_panel(current, fix_b)
    report("(b) refuses BOGUS, non-zero exit and names it",
           rc != 0 and BOGUS in text,
           f"exit={rc} names_bogus={BOGUS in text}")

    print("\nnegative control, pre-fix script:")
    rc_a, text_a = run_panel(prefix, fix_a)
    counted_a, total_a = tally(text_a)
    report("(c) pre-fix drops the four planted classes on A",
           rc_a == 0 and total_a is not None and total_a < spec["n_records"],
           f"exit={rc_a} sum={total_a} n={spec['n_records']} tally={counted_a}")
    rc_b, text_b = run_panel(prefix, fix_b)
    report("(c) pre-fix swallows BOGUS on B, exit 0",
           rc_b == 0 and BOGUS not in text_b,
           f"exit={rc_b} names_bogus={BOGUS in text_b}")

    n_ok = sum(CHECKS)
    print(f"\nchecks run: {len(CHECKS)}, passed: {n_ok}")
    print("LIMIT: the fixtures are the real well_verdicts.csv with four "
          "replicate slots rewritten, because build() asserts 96 rows and an "
          "audit set derived from the data; the tally is read off stdout, not "
          "off the SVG, because it is not drawn. SVG byte-identity is checked "
          "separately by sha256.")
    print("FIXTURES_OK" if n_ok == len(CHECKS) else "FIXTURES_FAIL")
    return 0 if n_ok == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
