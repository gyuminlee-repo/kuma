#!/usr/bin/env python3
"""Freeze the thermodynamic output of the current primer3 engine as a fixture.

kuma routes every Tm, hairpin, homodimer and heterodimer number through
``primer3-py``, which is GPL. If that dependency is ever swapped for a
permissive engine, the only honest way to judge the replacement is to ask
whether it reproduces the numbers kuma ships today. This script records those
numbers so the comparison has a baseline.

It does not exercise kuma behaviour and it does not change it. It calls the
four primer3 entry points kuma calls, with the parameter combinations kuma
actually passes, read out of the live code rather than retyped here:

  - kuma_core.kuro.sdm_engine        design Tm plus hairpin/homodimer/heterodimer
  - kuma_core.kuro.annealing         per polymerase profile Tm
  - kuma_core.kuro.neb_tm            NEB calibration reference Tm
  - kuma_core.mame.ingest.barcode_package  MAME barcode Tm

Both tm and dg are recorded for every structure call. kuma warns on hairpins and
homodimers at a Tm threshold of 40.0 C (sdm_engine._check_secondary_structure),
so a corpus holding only dg would not cover the value the product actually gates
on.

Run from anywhere:

    python3 python-core/scripts/gen_thermo_golden.py

No network access. Everything here is a local calculation.
"""

from __future__ import annotations

import inspect
import json
import platform
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import primer3  # noqa: E402

from kuma_core.kuro import sdm_engine  # noqa: E402
from kuma_core.mame.ingest.polymerase import POLYMERASE_PROFILES as MAME_PROFILES  # noqa: E402

OUT_PATH = REPO_ROOT / "tests" / "fixtures" / "thermo_golden.json"
GEN_COMMAND = "python3 python-core/scripts/gen_thermo_golden.py"

_COMPLEMENT = str.maketrans("ACGT", "TGCA")


def reverse_complement(seq: str) -> str:
    return seq.translate(_COMPLEMENT)[::-1]


# ---------------------------------------------------------------------------
# Parameter sets, read from the live code
# ---------------------------------------------------------------------------

def _design_concs() -> dict:
    """The four concentrations of the fixed design scale (sdm_engine)."""
    return dict(sdm_engine._DESIGN_CONCS)


def build_param_sets() -> dict[str, dict]:
    """Every calc_tm keyword combination kuma issues, keyed by a stable id.

    Values come from the modules and resource files themselves so that a later
    edit to a concentration shows up as a fixture mismatch instead of being
    masked by a hand-copied literal.
    """
    sets: dict[str, dict] = {}

    # 1. kuro/sdm_engine._calc_sdm_tm: enzyme independent design scale.
    sets["design"] = {
        **_design_concs(),
        "tm_method": sdm_engine._DESIGN_TM_METHOD,
        "salt_corrections_method": sdm_engine._DESIGN_SALT_CORRECTION,
    }

    # 2. kuro/annealing._primer3_profile_tm: the profile buffer, one per
    #    polymerase defined in the committed resource file.
    profiles_path = REPO_ROOT / "kuma_core" / "kuro" / "resources" / "polymerase_profiles.json"
    profiles = json.loads(profiles_path.read_text(encoding="utf-8"))
    for name in sorted(profiles):
        p = profiles[name]
        sets[f"kuro_profile:{name}"] = {
            "mv_conc": p["salt_monovalent"],
            "dv_conc": p["salt_divalent"],
            "dntp_conc": p["dntp_conc"],
            "dna_conc": p["dna_conc"],
            "tm_method": p["tm_method"],
            "salt_corrections_method": p["salt_correction"],
        }

    # 3. kuro/neb_tm.neb_estimated_tm: the reference config each NEB product
    #    was calibrated against. Values are passed through verbatim by that
    #    function, so they are copied verbatim here (ints stay ints).
    offsets_path = REPO_ROOT / "kuma_core" / "kuro" / "resources" / "neb_tm_offsets.json"
    offsets = json.loads(offsets_path.read_text(encoding="utf-8"))
    for product in sorted(offsets["products"]):
        sets[f"neb_ref:{product}"] = dict(offsets["products"][product]["ref_config"])

    # 4. mame/ingest/barcode_package._calc_tm: the MAME barcode profiles.
    for name in sorted(MAME_PROFILES):
        p = MAME_PROFILES[name]
        sets[f"mame_profile:{name}"] = {
            "mv_conc": p.mv_conc,
            "dv_conc": p.dv_conc,
            "dntp_conc": p.dntp_conc,
            "dna_conc": p.dna_conc,
            "tm_method": p.tm_method,
            "salt_corrections_method": p.salt_corrections_method,
        }

    return sets


# ---------------------------------------------------------------------------
# Corpus
# ---------------------------------------------------------------------------

# Offsets and lengths into the repository's own MAME reference sequence. The
# file holds a 60 nt unit repeated five times, so every window starts inside the
# first 60 nt; anything past that would only duplicate an earlier window.
_MAME_WINDOWS = [
    (0, 18), (3, 20), (7, 22), (11, 24), (15, 25), (19, 27),
    (23, 30), (27, 33), (31, 36), (35, 39), (41, 40), (47, 20),
]

# Structured sequences chosen by a separate probe run and pinned here, so the
# corpus does not depend on the engine it is meant to hold to account. The
# comment on each line records the design-scale hairpin Tm seen at selection
# time; the authoritative value is whatever this script writes out.
_STRUCTURED = {
    # Strong hairpins, far above the 40.0 C warning threshold.
    "hairpin_gc_stem8": "GCGCGCGCTTTTGCGCGCGC",        # ~89 C
    "hairpin_hindiii": "AAGCTTGCTTTTGCAAGCTT",          # ~73 C
    "hairpin_bamhi": "GGATCCGGTTTTCCGGATCC",            # ~71 C
    "hairpin_nsii": "ATGCATTTTTATGCAT",                 # ~52 C
    # Just below the 40.0 C threshold.
    "hairpin_below_34_0": "GCTATTTTTAGC",               # ~34 C
    "hairpin_below_34_9": "GACTTTTTTTAGTC",             # ~35 C
    "hairpin_below_37_9": "AAGACTTTTTAGTCAA",           # ~38 C
    "hairpin_below_38_3": "ATCGTTTTTTTTCGAT",           # ~38 C
    "hairpin_below_38_8": "AGCTTTTTAGCT",               # ~39 C
    "hairpin_below_39_4": "AGCTTTTTTTTTAGCT",           # ~39 C
    # Just above it.
    "hairpin_above_40_1": "ACGTTTTTACGT",               # ~40 C
    "hairpin_above_41_1": "ATGCTTTTTTTTGCAT",           # ~41 C
    "hairpin_above_41_3": "TGCATTTTTGCA",               # ~41 C
    "hairpin_above_41_4": "ATCGTTTTTTCGAT",             # ~41 C
    "hairpin_above_42_0": "GCATATTTTTATGC",             # ~42 C
    "hairpin_above_44_4": "AGCTATTTTTAGCT",             # ~44 C
    # Self complementary, so the homodimer rather than the hairpin is the
    # strong feature. Needed because the corpus must hold dimers above the
    # threshold as well as hairpins.
    "homodimer_gc20": "GCGCGCGCGCGCGCGCGCGC",
    "homodimer_atgc24": "ATGCATGCATGCATGCATGCATGC",
    "homodimer_ccgg16": "CCGGCCGGCCGGCCGG",
    "homodimer_gcrich22": "GCCGGCATGCCGGCATGCCGGC",
    # No hairpin at all: the negative end of the structure corpus. The
    # homodimer call still reports structure_found on these, with a Tm far
    # below the threshold, which is why the counts below are reported both by
    # structure_found and against 40.0 C.
    "flat_a_rich": "AAAGAAATAAAGAAATAAAGAAAT",
    "flat_at_18": "ATATATATATATATATAT",
    # Sequences already present in this repository's own test suite.
    "repo_m13_fwd": "CAGGAAACAGCTATGACCATG",
    "repo_t7_like": "ACGACTCACTATAGGGCGAATTGG",
    "repo_cloning_site": "GCTAGCTAGCGGATCCAAAGGTGCTGACC",
    "repo_m13_rev": "GACCATGATTACGCCAAGCTTG",
}


def _synthetic_gc_ladder() -> dict[str, str]:
    """Random sequences spanning length and GC, from a pinned seed.

    The seed is fixed so a regeneration reproduces the same corpus. GC bands are
    low, mid, high and very high, two sequences each.
    """
    rng = random.Random(20260920)
    out: dict[str, str] = {}
    bands = [(20, 34), (20, 34), (35, 49), (35, 49), (50, 64), (50, 64), (65, 80), (65, 80)]
    for i, (lo, hi) in enumerate(bands):
        length = rng.choice([18, 21, 24, 27, 30, 36])
        n_gc = round(length * rng.uniform(lo, hi) / 100)
        chars = ["G" if rng.random() < 0.5 else "C" for _ in range(n_gc)]
        chars += ["A" if rng.random() < 0.5 else "T" for _ in range(length - n_gc)]
        rng.shuffle(chars)
        out[f"synth_gc{lo}_{i}"] = "".join(chars)
    return out


def build_sequences() -> dict[str, dict]:
    """The sequence pool, each entry carrying where it came from."""
    seqs: dict[str, dict] = {}

    ref_path = REPO_ROOT / "tests" / "fixtures" / "mame" / "reference.fasta"
    lines = ref_path.read_text(encoding="utf-8").splitlines()
    ref = "".join(line.strip() for line in lines if not line.startswith(">"))
    for offset, length in _MAME_WINDOWS:
        seqs[f"mame_ref_{offset}_{length}"] = {
            "seq": ref[offset:offset + length],
            "origin": f"tests/fixtures/mame/reference.fasta[{offset}:{offset + length}]",
        }

    for key, seq in _synthetic_gc_ladder().items():
        seqs[key] = {"seq": seq, "origin": "synthetic GC/length ladder, seed 20260920"}

    for key, seq in _STRUCTURED.items():
        origin = "in-repo test sequence" if key.startswith("repo_") else "pinned structure probe"
        seqs[key] = {"seq": seq, "origin": origin}

    return seqs


# Heterodimer pairs. sdm_engine calls calc_heterodimer(primer, rc(site)), so
# every pair here is built the same way: a primer against the reverse complement
# of some window. Pairing a window with its own reverse complement gives a
# perfect duplex; pairing across distant windows gives a weak or absent one.
_HETERO_PAIRS = [
    ("mame_ref_0_18", "mame_ref_0_18"),
    ("mame_ref_19_27", "mame_ref_19_27"),
    ("mame_ref_41_40", "mame_ref_41_40"),
    ("mame_ref_0_18", "mame_ref_35_39"),
    ("mame_ref_3_20", "mame_ref_27_33"),
    ("mame_ref_7_22", "flat_a_rich"),
    ("synth_gc65_6", "synth_gc20_0"),
    ("synth_gc50_4", "synth_gc50_4"),
    ("repo_m13_fwd", "repo_m13_rev"),
    ("flat_at_18", "flat_a_rich"),
    ("hairpin_gc_stem8", "hairpin_gc_stem8"),
    ("homodimer_ccgg16", "flat_at_18"),
]


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

def _implicit_defaults(fn, passed_keys: set[str]) -> dict:
    """Defaults of the arguments kuma never passes, read off the live signature.

    A replacement engine has to match these too, and retyping them from memory
    is how a baseline starts lying. Values that do not survive JSON are recorded
    as their repr.
    """
    out: dict = {}
    for name, param in inspect.signature(fn).parameters.items():
        if param.default is inspect.Parameter.empty or name in passed_keys:
            continue
        value = param.default
        if not isinstance(value, (str, int, float, bool, type(None))):
            value = repr(value)
        out[name] = value
    return out


def _structure_record(res) -> dict:
    """dg and tm exactly as primer3 returns them, plus the found flag.

    dg is kept in primer3's native cal/mol. sdm_engine divides by 1000 for
    display; dividing here would bake a presentation choice into the baseline.
    """
    return {
        "structure_found": bool(res.structure_found),
        "tm": float(res.tm),
        "dg": float(res.dg),
    }


def build_entries(param_sets: dict[str, dict], sequences: dict[str, dict]) -> list[dict]:
    entries: list[dict] = []
    concs = _design_concs()

    # design_concs_only drives the structure calls, which take no method
    # arguments. It is not a calc_tm combination any kuma call site issues, so
    # it is excluded here rather than sweeping 46 imaginary Tm entries.
    tm_param_sets = [k for k in sorted(param_sets) if k != "design_concs_only"]

    for seq_id in sorted(sequences):
        seq = sequences[seq_id]["seq"]
        for ps_id in tm_param_sets:
            entries.append({
                "id": f"calc_tm|{seq_id}|{ps_id}",
                "call": "calc_tm",
                "seq_id": seq_id,
                "seq": seq,
                "param_set": ps_id,
                "expected": {"tm": float(primer3.calc_tm(seq, **param_sets[ps_id]))},
            })

    for seq_id in sorted(sequences):
        seq = sequences[seq_id]["seq"]
        entries.append({
            "id": f"calc_hairpin|{seq_id}",
            "call": "calc_hairpin",
            "seq_id": seq_id,
            "seq": seq,
            "param_set": "design_concs_only",
            "expected": _structure_record(primer3.calc_hairpin(seq, **concs)),
        })
        entries.append({
            "id": f"calc_homodimer|{seq_id}",
            "call": "calc_homodimer",
            "seq_id": seq_id,
            "seq": seq,
            "param_set": "design_concs_only",
            "expected": _structure_record(primer3.calc_homodimer(seq, **concs)),
        })

    for left_id, right_id in _HETERO_PAIRS:
        left = sequences[left_id]["seq"]
        right = reverse_complement(sequences[right_id]["seq"])
        entries.append({
            "id": f"calc_heterodimer|{left_id}|rc({right_id})",
            "call": "calc_heterodimer",
            "seq_id": left_id,
            "seq": left,
            "seq2": right,
            "seq2_source": f"reverse_complement({right_id})",
            "param_set": "design_concs_only",
            "expected": _structure_record(primer3.calc_heterodimer(left, right, **concs)),
        })

    return entries


def main() -> int:
    param_sets = build_param_sets()
    param_sets["design_concs_only"] = _design_concs()
    concs_keys = set(_design_concs())
    sequences = build_sequences()
    entries = build_entries(param_sets, sequences)

    payload = {
        "_meta": {
            "purpose": (
                "Golden corpus of primer3 thermodynamic output, frozen so a future "
                "permissive replacement for primer3-py can be judged on whether it "
                "reproduces the numbers kuma ships."
            ),
            "generated_by": GEN_COMMAND,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "primer3_version": primer3.__version__,
            "python_version": sys.version,
            "platform": platform.platform(),
            "warn_tm_threshold_degC": 40.0,
            "dg_units": "cal/mol, as primer3 returns it",
            "implicit_defaults": {
                "note": (
                    "kuma does not pass these, so a replacement must match "
                    "primer3-py's defaults for them at the recorded version. "
                    "Read off the installed signatures, not transcribed."
                ),
                "calc_tm": _implicit_defaults(primer3.calc_tm, set(param_sets["design"])),
                "calc_hairpin": _implicit_defaults(primer3.calc_hairpin, set(concs_keys)),
                "calc_homodimer": _implicit_defaults(primer3.calc_homodimer, set(concs_keys)),
                "calc_heterodimer": _implicit_defaults(primer3.calc_heterodimer, set(concs_keys)),
            },
        },
        "param_sets": param_sets,
        "sequences": sequences,
        "entries": entries,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT_PATH.relative_to(REPO_ROOT)}: {len(entries)} entries, "
          f"{len(sequences)} sequences, {len(param_sets)} parameter sets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
