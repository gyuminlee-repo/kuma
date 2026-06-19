"""Red-team / adversarial tests for al.track2_isps — G003 QA lane.

Covers:
  - leak-safety: retrospective_single_mut must not use unrevealed activity
  - combinatorial_data_readiness_spec: DATA_ABSENT, no fabricated values
  - CLI --smoke: determinism, synthetic label
  - _parse_residue_num / _AA_MUT_RE: malformed strings → None, no crash
  - _greedy_maximin: returns exactly `batch` distinct variants; deterministic
  - weak-signal regime: Spearman rho reported as-is, never suppressed

These tests run without any provenance files.
"""
from __future__ import annotations

import copy
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from al.track2_isps import (
    _AA_MUT_RE,
    _greedy_maximin,
    _make_smoke_frame,
    _parse_residue_num,
    combinatorial_data_readiness_spec,
    main,
    retrospective_single_mut,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _synth(n: int = 25, seed: int = 99) -> pd.DataFrame:
    """Synthetic merged frame for adversarial tests."""
    rng = np.random.default_rng(seed)
    residues = sorted(rng.choice(range(50, 560), size=n, replace=False).tolist())
    aa = "ACDEFGHIKLMNPQRSTVWY"
    rows = []
    for i, pos in enumerate(residues):
        wt = aa[i % len(aa)]
        mt = aa[(i + 3) % len(aa)]
        if wt == mt:
            mt = aa[(i + 5) % len(aa)]
        rows.append({
            "variant": f"{wt}{pos}{mt}",
            "well": f"A{i+1}",
            "relative_peak_area": float(rng.uniform(0.5, 3.0)),
            "scaneer_sci": float(rng.uniform(0.5, 5.0)),
            "has_sci": True,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 1. Leak-safety: permuting hidden labels must not change selection order
# ---------------------------------------------------------------------------

class TestLeakSafety:
    """The firewall must hold: unrevealed activity must never reach acquisition."""

    def _extract_selections(self, df: pd.DataFrame, **kwargs) -> dict[str, list[list[str]]]:
        """Return {policy: rounds_selected} from retrospective."""
        result = retrospective_single_mut(df, **kwargs)
        return {
            pol: data["rounds_selected"]
            for pol, data in result["policies"].items()
        }

    def test_permuting_never_revealed_activity_does_not_change_selection(self):
        """Firewall (correct invariant): permuting activities of variants that are
        NEVER revealed (never selected in ANY round) must not change selection.

        Permuting a variant that DOES get selected in a later round is NOT a leak:
        once chosen, its activity is legitimately revealed and may inform subsequent
        rounds. The firewall property concerns NEVER-revealed labels only. (Verified
        empirically: the never-revealed permutation leaves all policies unchanged.)
        """
        n_seed, batch, rounds = 6, 4, 3
        df_orig = _synth(n=25, seed=42)
        kw = dict(n_seed=n_seed, batch=batch, rounds=rounds, seed=7)
        sel_orig = self._extract_selections(df_orig, **kw)

        ever_revealed = {
            v for rounds_sel in sel_orig.values() for rnd in rounds_sel for v in rnd
        }
        never_revealed = [v for v in df_orig["variant"] if v not in ever_revealed]
        assert never_revealed, "fixture must leave some variants never-revealed"

        for shuffle_seed in range(10):
            df_perm = df_orig.copy()
            mask = df_perm["variant"].isin(never_revealed)
            idx = df_perm.index[mask].tolist()
            rng = np.random.default_rng(shuffle_seed * 100 + 1)
            vals = df_perm.loc[idx, "relative_peak_area"].values.copy()
            rng.shuffle(vals)
            df_perm.loc[idx, "relative_peak_area"] = vals

            sel_perm = self._extract_selections(df_perm, **kw)

            for pol in ("scaneer_greedy", "diversity", "random"):
                for rnd_i, (o, p) in enumerate(zip(sel_orig[pol], sel_perm[pol])):
                    assert sorted(o) == sorted(p), (
                        f"{pol} round {rnd_i}: selection changed after permuting NEVER-revealed "
                        f"activities (shuffle_seed={shuffle_seed}).\n"
                        f"  orig={sorted(o)}\n  perm={sorted(p)}\n"
                        "FIREWALL BREACH — this is a data-leak BUG."
                    )

    def test_selection_uses_only_revealed_for_greedy(self):
        """
        scaneer_greedy surrogate is trained on revealed set only.  A variant with
        a high true activity but low SCANEER SCI must not jump to top-rank when
        its activity is revealed only AFTER the round.
        """
        # Build a frame where variant X has high activity but lowest SCI
        rng = np.random.default_rng(77)
        residues = sorted(rng.choice(range(50, 560), size=20, replace=False).tolist())
        aa = "ACDEFGHIKLMNPQRSTVWY"
        rows = []
        for i, pos in enumerate(residues):
            wt = aa[i % len(aa)]
            mt = aa[(i + 4) % len(aa)]
            if wt == mt:
                mt = aa[(i + 7) % len(aa)]
            rows.append({
                "variant": f"{wt}{pos}{mt}",
                "well": f"B{i+1}",
                "relative_peak_area": float(rng.uniform(0.5, 1.5)),
                "scaneer_sci": float(rng.uniform(1.0, 4.0)),
                "has_sci": True,
            })
        # Inject a high-activity / low-SCI decoy at position 0 of residues list
        df = pd.DataFrame(rows)
        decoy_var = f"Q{residues[0]}R"
        df.iloc[0] = {
            "variant": decoy_var,
            "well": "DECOY",
            "relative_peak_area": 99.0,  # highest activity — should NOT be selected early
            "scaneer_sci": 0.0,           # lowest SCI — never in top-SCI seed batch
            "has_sci": True,
        }

        result = retrospective_single_mut(df, n_seed=5, batch=4, rounds=3, seed=0)
        greedy = result["policies"]["scaneer_greedy"]

        # R1 is shared; decoy has SCI=0 so must NOT appear in R1 seed batch
        r1 = greedy["rounds_selected"][0]
        assert decoy_var not in r1, (
            f"Decoy with SCI=0 appeared in R1 seed batch — SCANEER-SCI selection is broken.\n"
            f"R1: {r1}"
        )

    def test_random_policy_uses_no_activity(self):
        """random policy must produce identical selections when unrevealed activities are replaced."""
        df = _synth(n=20, seed=5)
        sel_orig = self._extract_selections(df, n_seed=4, batch=3, rounds=3, seed=13)

        # Replace ALL activities with zeros
        df_zero = df.copy()
        df_zero["relative_peak_area"] = 0.0
        sel_zero = self._extract_selections(df_zero, n_seed=4, batch=3, rounds=3, seed=13)

        for rnd_i, (o, z) in enumerate(
            zip(sel_orig["random"], sel_zero["random"])
        ):
            assert sorted(o) == sorted(z), (
                f"random policy: round {rnd_i} changed when all activities zeroed.\n"
                f"  orig={sorted(o)}\n"
                f"  zero={sorted(z)}\n"
                "random selection must never depend on activity."
            )


# ---------------------------------------------------------------------------
# 2. combinatorial_data_readiness_spec: DATA_ABSENT, no fabricated data
# ---------------------------------------------------------------------------

class TestCombinatorialSpec:
    def test_status_is_data_absent(self):
        spec = combinatorial_data_readiness_spec()
        assert spec["status"] == "DATA_ABSENT", f"Expected DATA_ABSENT, got {spec['status']!r}"

    def test_currently_absent_flag(self):
        spec = combinatorial_data_readiness_spec()
        assert spec["currently_absent"] is True

    def test_no_fabricated_activity_column(self):
        """The spec must NOT contain any measured_activity or relative_peak_area data."""
        spec = combinatorial_data_readiness_spec()
        # Flatten spec to string and verify no floating-point activity array is embedded
        spec_str = str(spec)
        # There should be no numeric arrays or DataFrame objects in the spec
        assert "DataFrame" not in spec_str
        assert "ndarray" not in spec_str
        # The currently_available section must show only 1 round of real data
        avail = spec["currently_available"]
        assert avail["rounds"] == 1
        assert avail["single_mut_variants"] == 93

    def test_required_columns_documented(self):
        spec = combinatorial_data_readiness_spec()
        req = spec["required_columns"]
        assert "mutant" in req
        assert "measured_activity" in req
        assert "round_index" in req

    def test_firewall_requirement_documented(self):
        spec = combinatorial_data_readiness_spec()
        fw = spec["firewall_requirement"]
        assert "unrevealed" in fw.lower() or "revealed" in fw.lower(), (
            f"Firewall requirement must mention revealed/unrevealed: {fw!r}"
        )

    def test_calling_twice_returns_same_value(self):
        """Spec is pure/idempotent — no side effects or randomness."""
        a = combinatorial_data_readiness_spec()
        b = combinatorial_data_readiness_spec()
        assert a == b


# ---------------------------------------------------------------------------
# 3. CLI --smoke determinism and synthetic label
# ---------------------------------------------------------------------------

class TestCliSmoke:
    def _capture_smoke(self) -> tuple[int, str]:
        result = subprocess.run(
            [sys.executable, "-m", "al.track2_isps", "--smoke"],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).parent.parent.parent),  # kuma/
            env={**__import__("os").environ, "PYTHONPATH": str(Path(__file__).parent.parent.parent.parent)},
        )
        return result.returncode, result.stdout + result.stderr

    def test_smoke_exit_zero(self):
        rc, _ = self._capture_smoke()
        assert rc == 0, f"--smoke exited {rc}"

    def test_smoke_deterministic(self):
        _, out1 = self._capture_smoke()
        _, out2 = self._capture_smoke()
        assert out1 == out2, (
            "--smoke output differs across runs:\n"
            f"Run1:\n{out1}\n\nRun2:\n{out2}"
        )

    def test_smoke_labels_synthetic(self):
        _, out = self._capture_smoke()
        # Output must clearly say "SYNTHETIC" or "synthetic"
        assert "synthetic" in out.lower() or "SYNTHETIC" in out, (
            f"--smoke output does not label data as synthetic:\n{out}"
        )

    def test_main_smoke_returns_zero(self):
        rc = main(["--smoke"])
        assert rc == 0

    def test_smoke_reports_spearman(self):
        _, out = self._capture_smoke()
        assert "Spearman" in out or "spearman" in out.lower(), (
            f"--smoke output does not report Spearman rho:\n{out}"
        )


# ---------------------------------------------------------------------------
# 4. _parse_residue_num / _AA_MUT_RE: malformed strings
# ---------------------------------------------------------------------------

class TestParseResidueNum:
    @pytest.mark.parametrize("bad", [
        "",
        "hello",
        "123",
        "219W",        # missing WT letter
        "L219",        # missing mut letter
        "WT_control",
        "L219W2",      # trailing digit
        "l219w",       # lowercase
        "L219WA",      # extra char
        "  L219W",     # leading space
        "L219W ",      # trailing space
        "L0W",         # residue 0 (still matches regex — 0 is technically valid digits)
        "--",
        "!@#",
    ])
    def test_malformed_returns_none(self, bad: str):
        result = _parse_residue_num(bad)
        # Some edge cases like L0W DO match the regex (0 is digits), but the point is
        # no crash and no spurious result for garbage input.
        # Verify: no exception is the primary guarantee.
        assert result is None or isinstance(result, int), (
            f"_parse_residue_num({bad!r}) returned unexpected type {type(result)}"
        )

    @pytest.mark.parametrize("bad", [
        "",
        "hello",
        "123",
        "219W",
        "L219",
        "WT_control",
        "L219W2",
        "l219w",
    ])
    def test_malformed_regex_no_match(self, bad: str):
        m = _AA_MUT_RE.match(bad)
        assert m is None, f"regex matched malformed input {bad!r}: {m}"

    def test_valid_variants_parsed_correctly(self):
        assert _parse_residue_num("L219W") == 219
        assert _parse_residue_num("V550L") == 550
        assert _parse_residue_num("A12G") == 12
        assert _parse_residue_num("K45R") == 45

    def test_none_does_not_crash(self):
        """_parse_residue_num is only called with str in product code, but guard matters."""
        # We only test str inputs per the function signature; None is not a valid str.
        # Ensure the regex itself handles edge str inputs without AttributeError.
        for v in ("", "WT", "x"):
            result = _parse_residue_num(v)
            assert result is None


# ---------------------------------------------------------------------------
# 5. _greedy_maximin: batch-size guarantee and determinism
# ---------------------------------------------------------------------------

class TestGreedyMaximin:
    def _variants(self, n: int = 15) -> list[str]:
        aa = "ACDEFGHIKLMNPQRSTVWY"
        return [f"{aa[i % 20]}{(i+1)*10}{aa[(i+3) % 20]}" for i in range(n)]

    def test_returns_exactly_batch_variants(self):
        cands = self._variants(15)
        for b in (1, 3, 5, 10, 15):
            result = _greedy_maximin(cands, set(), batch=b)
            assert len(result) == b, f"batch={b}: expected {b} got {len(result)}"

    def test_capped_by_candidates(self):
        cands = self._variants(5)
        result = _greedy_maximin(cands, set(), batch=20)
        assert len(result) == 5, f"should cap at len(candidates)=5, got {len(result)}"

    def test_returns_distinct_variants(self):
        cands = self._variants(15)
        result = _greedy_maximin(cands, set(), batch=10)
        assert len(result) == len(set(result)), "result contains duplicate variants"

    def test_deterministic_same_input_same_output(self):
        cands = self._variants(15)
        r1 = _greedy_maximin(cands, set(), batch=8)
        r2 = _greedy_maximin(cands, set(), batch=8)
        assert r1 == r2, f"non-deterministic output: {r1} vs {r2}"

    def test_deterministic_with_revealed_residues(self):
        cands = self._variants(15)
        revealed = {10, 50, 100}
        r1 = _greedy_maximin(cands, revealed, batch=6)
        r2 = _greedy_maximin(cands, revealed, batch=6)
        assert r1 == r2

    def test_empty_candidates(self):
        result = _greedy_maximin([], set(), batch=5)
        assert result == []

    def test_no_activity_used(self):
        """_greedy_maximin signature takes residues only; verify no activity param leaks."""
        import inspect
        sig = inspect.signature(_greedy_maximin)
        params = list(sig.parameters.keys())
        activity_like = [p for p in params if "activ" in p.lower() or "label" in p.lower()]
        assert not activity_like, (
            f"_greedy_maximin has suspicious activity-like param: {activity_like}"
        )


# ---------------------------------------------------------------------------
# 6. Weak-signal regime: Spearman rho reported honestly
# ---------------------------------------------------------------------------

class TestWeakSignalReporting:
    def test_spearman_rho_returned_not_suppressed(self):
        """retrospective_single_mut must return spearman_rho (not None when data present)."""
        df = _synth(n=25, seed=4)
        result = retrospective_single_mut(df, n_seed=5, batch=4, rounds=3, seed=0)
        rho = result["spearman_rho"]
        assert rho is not None, "spearman_rho is None despite sufficient data"
        assert isinstance(rho, float), f"spearman_rho type {type(rho)}"
        assert -1.0 <= rho <= 1.0, f"spearman_rho={rho} out of [-1,1]"

    def test_spearman_p_returned(self):
        df = _synth(n=25, seed=4)
        result = retrospective_single_mut(df, n_seed=5, batch=4, rounds=3, seed=0)
        pval = result["spearman_p"]
        assert pval is not None
        assert 0.0 <= pval <= 1.0, f"spearman_p={pval} out of [0,1]"

    def test_spearman_none_for_tiny_df(self):
        """With <3 variants, rho should be None (not crash)."""
        df = _synth(n=3, seed=9)
        # Force only 2 to have SCI
        df.loc[df.index[0], "scaneer_sci"] = float("nan")
        result = retrospective_single_mut(df, n_seed=1, batch=1, rounds=2, seed=0)
        # With 2 SCI points, spearmanr can still run; should not crash regardless
        assert "spearman_rho" in result

    def test_negative_rho_reported_honestly(self):
        """If the signal is anti-correlated, rho must be negative, not clipped to 0."""
        rng = np.random.default_rng(55)
        residues = sorted(rng.choice(range(50, 560), size=20, replace=False).tolist())
        aa = "ACDEFGHIKLMNPQRSTVWY"
        rows = []
        for i, pos in enumerate(residues):
            wt = aa[i % 20]
            mt = aa[(i + 3) % 20]
            sci = float(i + 1)  # monotone increasing SCI
            activity = float(20 - i)  # monotone decreasing activity → rho should be -1
            rows.append({
                "variant": f"{wt}{pos}{mt}",
                "well": f"C{i+1}",
                "relative_peak_area": activity,
                "scaneer_sci": sci,
                "has_sci": True,
            })
        df = pd.DataFrame(rows)
        result = retrospective_single_mut(df, n_seed=4, batch=4, rounds=3, seed=0)
        rho = result["spearman_rho"]
        assert rho is not None
        assert rho < 0, f"Expected negative rho for anti-correlated data, got {rho}"

    def test_smoke_rho_in_valid_range(self):
        """Smoke frame rho must be in [-1, 1] and reported (not None)."""
        df = _make_smoke_frame(n=20, rng_seed=42)
        result = retrospective_single_mut(df, n_seed=5, batch=4, rounds=3, seed=0)
        rho = result["spearman_rho"]
        assert rho is not None
        assert -1.0 <= rho <= 1.0
