# ruff: noqa: S101
"""Tests for G001 backend: map_ref_to_accession, compute_round_dispersion,
fetch_pdb_text shared cache, fetch_active_site_features, and dispatcher
registration.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# 1. map_ref_to_accession
# ---------------------------------------------------------------------------


class TestMapRefToAccession:
    """Tests for kuma_core.kuro.interface.map_ref_to_accession."""

    def _fn(self):
        from kuma_core.kuro.interface import map_ref_to_accession
        return map_ref_to_accession

    def test_identity_case(self) -> None:
        """Same sequences => mapped == sorted unique positions, dropped == []."""
        fn = self._fn()
        seq = "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGDGTQDNLSGAEKAVQVKVKALPDAQFEVVHSLAKWKRQTLGQHDFSAGEGLYTHMKALRPDEDRLSPLHSVYVDQWDWERVMGDGERQFSTLKSTVEAIWAGIKATEAAVSEEFGLAPFLPDQIHFVHSQELLSRYPDLDAKGRERAIAKDLGAVFLVGIGGKLSDGHRHDVRAPDYDDWSTPSELGHAGLNGDILVWNPSVSMYFCFEYELHARFEELNADFLAQQ"
        positions = [5, 10, 20, 10]  # duplicate 10 should be de-duped
        result = fn(positions, seq, seq)
        assert result["mapped"] == [5, 10, 20]
        assert result["dropped"] == []

    def test_offset_case(self) -> None:
        """accession_seq is a C-terminal truncation of ref_seq (N-terminal extension).

        ref_seq:       MMMMMXXXXX...  (len N+10)
        accession_seq: XXXXX...       (len N, = ref_seq[10:])

        ref position 11 should map to accession position 1.
        ref position 5 (within extension) should be dropped.
        """
        fn = self._fn()
        # Construct a concrete example using real-ish amino-acid strings.
        # Extension = 10-aa prefix on ref_seq; accession_seq = ref_seq[10:]
        extension = "MKTAYIAKQR"           # 10 aa N-terminal extension
        shared = "QISFVKSHFSRQLEERLGLI"    # 20 aa shared core
        ref_seq = extension + shared
        accession_seq = shared

        # ref position 15 is in the shared region (15 - 10 = 5 in accession)
        result = fn([15, 5], accession_seq, ref_seq)
        # Position 15 in ref_seq aligns to shared[4] (0-based index 4 = position 5 in acc)
        assert 15 not in result["dropped"], "pos 15 should map into accession"
        assert 5 in result["dropped"], "pos 5 is in extension, no accession alignment"
        # The mapped accession position for ref pos 15 should be 5
        assert result["mapped"] == [5]
        assert result["dropped"] == [5]

    def test_mapping_does_not_require_blosum62_data_file(self, monkeypatch) -> None:
        """Packaged sidecars may omit Biopython's loose BLOSUM62 data file."""
        from Bio.Align import substitution_matrices

        def fail_if_loaded(name: str):
            raise FileNotFoundError(name)

        monkeypatch.setattr(substitution_matrices, "load", fail_if_loaded)
        fn = self._fn()

        ref_seq = "MKTAYIAKQR" + "QISFVKSHFSRQLEERLGLI"
        accession_seq = "QISFVKSHFSRQLEERLGLI"

        assert fn([15], accession_seq, ref_seq) == {"mapped": [5], "dropped": []}

    def test_empty_positions(self) -> None:
        fn = self._fn()
        result = fn([], "MKTAY", "MKTAY")
        assert result == {"mapped": [], "dropped": []}


# ---------------------------------------------------------------------------
# 2. compute_round_dispersion
# ---------------------------------------------------------------------------

def _make_linear_coords(n: int) -> list[tuple[float, float, float] | None]:
    """Build 1-based coords list: residue i at (i*10, 0, 0)."""
    coords: list[tuple[float, float, float] | None] = [None]  # index 0 unused
    for i in range(1, n + 1):
        coords.append((float(i * 10), 0.0, 0.0))
    return coords


def test_parse_pdb_seq_one_letter_1based() -> None:
    """_parse_pdb_seq maps CA residues to a 1-based one-letter sequence."""
    from kuma_core.kuro.alphafold import _parse_pdb_seq, fetch_ca_seq

    pdb = "\n".join(
        [
            "ATOM      1  CA  MET A   1       0.000   0.000   0.000  1.00 90.00           C",
            "ATOM      2  CA  ALA A   2       3.800   0.000   0.000  1.00 90.00           C",
            "ATOM      3  CA  LYS A   4       7.600   0.000   0.000  1.00 90.00           C",
            "END",
        ]
    )
    # Residue 3 missing -> 'X'; residue 1=M, 2=A, 4=K
    assert _parse_pdb_seq(pdb) == "MAXK"

    with patch("kuma_core.kuro.alphafold.fetch_pdb_text", return_value=pdb):
        assert fetch_ca_seq("TESTQ9") == "MAXK"
    with patch("kuma_core.kuro.alphafold.fetch_pdb_text", return_value=None):
        assert fetch_ca_seq("TESTQ9") == ""


class TestComputeRoundDispersion:
    """Tests for kuma_core.kuro.dispersion.compute_round_dispersion."""

    def _run(self, positions, accession_seq, ref_seq, coords, **kwargs):
        from kuma_core.kuro.dispersion import compute_round_dispersion

        # Patch structure/coords fetches: structure-derived seq carries the
        # accession frame (UniProt FASTA is only a fallback, forced empty here).
        with (
            patch("kuma_core.kuro.dispersion.fetch_ca_coords", return_value=coords),
            patch("kuma_core.kuro.dispersion.fetch_ca_seq", return_value=accession_seq),
            patch("kuma_core.kuro.dispersion._fetch_accession_seq", return_value=""),
        ):
            return compute_round_dispersion(
                accession="TESTQ9",
                ref_seq=ref_seq,
                positions=positions,
                **kwargs,
            )

    def test_seed_determinism(self) -> None:
        """Same seed => identical percentile."""
        coords = _make_linear_coords(50)
        seq = "A" * 50
        r1 = self._run([10, 20, 30], seq, seq, coords, seed=42, n_trials=200)
        r2 = self._run([10, 20, 30], seq, seq, coords, seed=42, n_trials=200)
        assert r1["percentile"] == r2["percentile"]
        assert r1["klass"] == r2["klass"]
        # null_hist is present and has 24 bins summing to n_trials
        nh = r1["null_hist"]
        assert len(nh["counts"]) == 24
        assert sum(nh["counts"]) == 200
        assert nh["min"] <= nh["max"]

    def test_clustered_klass(self) -> None:
        """Very tightly grouped positions -> percentile <= 5 -> klass='clustered'."""
        # Build a 100-residue structure spread from x=10 to x=1000.
        # Use positions 1,2,3 (very close) vs random from 1..100.
        coords = _make_linear_coords(100)
        seq = "A" * 100
        # positions 1,2,3 are clustered at x=10,20,30 with mean pairwise ~13.33 Å
        # The null distribution samples from all 100 residues so most samples
        # will have higher mean pairwise distances.
        result = self._run([1, 2, 3], seq, seq, coords, seed=0, n_trials=2000)
        assert result["klass"] == "clustered", (
            f"Expected 'clustered', got '{result['klass']}' "
            f"(percentile={result['percentile']:.1f})"
        )

    def test_spread_klass(self) -> None:
        """Positions at the extremes -> percentile >= 95 -> klass='spread'."""
        coords = _make_linear_coords(100)
        seq = "A" * 100
        # positions 1 and 100 are maximally spread (distance = 990 Å)
        result = self._run([1, 100], seq, seq, coords, seed=0, n_trials=2000)
        assert result["klass"] == "spread", (
            f"Expected 'spread', got '{result['klass']}' "
            f"(percentile={result['percentile']:.1f})"
        )

    def test_mapped_and_dropped_returned(self) -> None:
        """mapped + dropped correctly reflect the alignment outcome."""
        # Use identity mapping (same seq) so no positions drop
        coords = _make_linear_coords(20)
        seq = "A" * 20
        result = self._run([5, 10, 15], seq, seq, coords, seed=1)
        assert result["mapped"] == [5, 10, 15]
        assert result["dropped"] == []

    def test_less_than_two_positions_returns_na(self) -> None:
        """Fewer than 2 mapped positions -> klass='na'."""
        coords = _make_linear_coords(10)
        seq = "A" * 10
        result = self._run([3], seq, seq, coords, seed=0)
        assert result["klass"] == "na"
        assert result["mean_pairwise"] == 0.0
        # degenerate na -> null_hist with empty counts
        nh = result["null_hist"]
        assert nh["counts"] == []
        assert nh["min"] == 0.0
        assert nh["max"] == 0.0

    def test_na_on_no_coords(self) -> None:
        """None coords (structure unavailable) -> klass='na', empty mapped."""
        from kuma_core.kuro.dispersion import compute_round_dispersion

        with patch("kuma_core.kuro.dispersion.fetch_ca_coords", return_value=None):
            result = compute_round_dispersion(
                accession="BADACC",
                ref_seq="MKTAY",
                positions=[1, 2, 3],
                seed=0,
            )
        assert result["klass"] == "na"
        assert result["mapped"] == []
        # no-coords na -> empty null_hist
        assert result["null_hist"]["counts"] == []

    def test_na_when_accession_seq_fetch_fails(self) -> None:
        """Accession FASTA fetch failure -> fail-loud na, all positions dropped.

        We must NOT silently identity-map (could place dispersion on wrong
        residues); instead surface the failure via klass='na' + dropped=all.
        """
        from kuma_core.kuro.dispersion import compute_round_dispersion

        coords = _make_linear_coords(50)
        with (
            patch("kuma_core.kuro.dispersion.fetch_ca_coords", return_value=coords),
            patch("kuma_core.kuro.dispersion.fetch_ca_seq", return_value=""),
            patch("kuma_core.kuro.dispersion._fetch_accession_seq", return_value=""),
        ):
            result = compute_round_dispersion(
                accession="TESTQ9",
                ref_seq="A" * 50,
                positions=[10, 20, 30],
                seed=0,
            )
        assert result["klass"] == "na"
        assert result["mapped"] == []
        assert result["dropped"] == [10, 20, 30]
        # fetch-fail na -> empty null_hist
        assert result["null_hist"]["counts"] == []

    def test_structure_seq_maps_when_uniprot_fasta_fails(self) -> None:
        """Regression: structure carries the accession frame even if UniProt FASTA fails.

        The user-reported case: the AlphaFold structure loads (coords + structure
        sequence available) but the UniProt FASTA fetch fails; mapping must still
        succeed from the structure-derived sequence instead of dropping all.
        """
        from kuma_core.kuro.dispersion import compute_round_dispersion

        coords = _make_linear_coords(50)
        seq = "A" * 50
        with (
            patch("kuma_core.kuro.dispersion.fetch_ca_coords", return_value=coords),
            patch("kuma_core.kuro.dispersion.fetch_ca_seq", return_value=seq),
            patch("kuma_core.kuro.dispersion._fetch_accession_seq", return_value=""),
        ):
            result = compute_round_dispersion(
                accession="TESTQ9",
                ref_seq=seq,
                positions=[10, 20, 30],
                seed=0,
            )
        assert result["klass"] != "na"
        assert result["mapped"] == [10, 20, 30]
        assert result["dropped"] == []

    def test_uniprot_fasta_fallback_when_structure_seq_empty(self) -> None:
        """Fallback: when the structure carries no sequence, UniProt FASTA is used."""
        from kuma_core.kuro.dispersion import compute_round_dispersion

        coords = _make_linear_coords(50)
        seq = "A" * 50
        with (
            patch("kuma_core.kuro.dispersion.fetch_ca_coords", return_value=coords),
            patch("kuma_core.kuro.dispersion.fetch_ca_seq", return_value=""),
            patch("kuma_core.kuro.dispersion._fetch_accession_seq", return_value=seq),
        ):
            result = compute_round_dispersion(
                accession="TESTQ9",
                ref_seq=seq,
                positions=[10, 20, 30],
                seed=0,
            )
        assert result["mapped"] == [10, 20, 30]
        assert result["dropped"] == []

    def test_null_hist_24_bins_sum_to_n_trials(self) -> None:
        """null_hist has exactly 24 bins summing to n_trials when null is computed."""
        coords = _make_linear_coords(50)
        seq = "A" * 50
        n_trials = 500
        result = self._run([5, 15, 25], seq, seq, coords, seed=7, n_trials=n_trials)
        nh = result["null_hist"]
        assert len(nh["counts"]) == 24, f"Expected 24 bins, got {len(nh['counts'])}"
        assert sum(nh["counts"]) == n_trials, (
            f"Expected counts sum={n_trials}, got {sum(nh['counts'])}"
        )
        assert nh["min"] <= nh["max"]

    def test_null_hist_min_le_max(self) -> None:
        """null_hist min<=max and all counts non-negative."""
        coords = _make_linear_coords(30)
        seq = "A" * 30
        result = self._run([3, 10, 20], seq, seq, coords, seed=0, n_trials=100)
        nh = result["null_hist"]
        assert nh["min"] <= nh["max"]
        assert all(c >= 0 for c in nh["counts"])


# ---------------------------------------------------------------------------
# 3. fetch_pdb_text shared cache: download-once guarantee
# ---------------------------------------------------------------------------


class TestFetchPdbTextSharedCache:
    """fetch_pdb_text then fetch_ca_coords should only download once."""

    def test_single_download_shared_cache(self, tmp_path: Path) -> None:
        """Calling fetch_pdb_text then fetch_ca_coords uses the shared PDB cache."""
        from kuma_core.kuro import alphafold as af_mod

        accession = "TESTQ9X1"
        # Minimal valid PDB text with one CA atom at residue 1
        fake_pdb = (
            "ATOM      1  CA  ALA A   1      10.000  20.000  30.000  1.00 50.00           C\n"
            "END\n"
        )
        fake_af_response = [{"pdbUrl": "http://fake.example/fake.pdb"}]
        download_count = {"n": 0}

        def fake_urlopen(req, context=None, timeout=None):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            mock_resp = MagicMock()
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            if "alphafold.ebi.ac.uk" in url:
                mock_resp.read.return_value = json.dumps(fake_af_response).encode()
            elif "fake.example" in url:
                download_count["n"] += 1
                mock_resp.read.return_value = fake_pdb.encode()
            else:
                raise RuntimeError(f"Unexpected URL: {url}")
            return mock_resp

        orig_cache_dir = af_mod._CACHE_DIR
        try:
            af_mod._CACHE_DIR = tmp_path / "embeddings"
            af_mod._CACHE_DIR.mkdir(parents=True, exist_ok=True)

            import urllib.request as _req
            with patch.object(_req, "urlopen", side_effect=fake_urlopen):
                # First call: fetch_pdb_text — should trigger download
                pdb_text = af_mod.fetch_pdb_text(accession)
                assert pdb_text is not None
                assert download_count["n"] == 1

                # Second call: fetch_ca_coords — should read from .pdb cache, NO second download
                coords = af_mod.fetch_ca_coords(accession)
                assert coords is not None
                assert download_count["n"] == 1, (
                    "fetch_ca_coords should reuse the shared .pdb cache; "
                    f"actual download count = {download_count['n']}"
                )
        finally:
            af_mod._CACHE_DIR = orig_cache_dir


# ---------------------------------------------------------------------------
# 4. fetch_active_site_features: monkeypatched UniProt response
# ---------------------------------------------------------------------------


class TestFetchActiveSiteFeatures:
    """Tests for kuma_core.kuro.uniprot_features.fetch_active_site_features."""

    def _fake_uniprot_response(self) -> dict:
        return {
            "features": [
                {"type": "Active site", "location": {"start": {"value": 42}}},
                {"type": "Active site", "location": {"start": {"value": 99}}},
                {"type": "Binding site", "location": {"start": {"value": 77}}},
                {"type": "Transmembrane", "location": {"start": {"value": 5}}},
            ]
        }

    def test_active_site_positions_parsed(self) -> None:
        from kuma_core.kuro.uniprot_features import fetch_active_site_features

        fake_resp = self._fake_uniprot_response()
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = json.dumps(fake_resp).encode()

        import urllib.request as _req
        with patch.object(_req, "urlopen", return_value=mock_resp):
            result = fetch_active_site_features("P12345")

        assert result["active_site_positions"] == [42, 99]
        assert result["binding_positions"] == [77]
        assert result["has_annotation"] is True
        assert result["source"] == "uniprot"
        assert result["accession"] == "P12345"

    def test_no_annotation(self) -> None:
        from kuma_core.kuro.uniprot_features import fetch_active_site_features

        fake_resp = {"features": [
            {"type": "Transmembrane", "location": {"start": {"value": 5}}},
        ]}
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = json.dumps(fake_resp).encode()

        import urllib.request as _req
        with patch.object(_req, "urlopen", return_value=mock_resp):
            result = fetch_active_site_features("Q99999")

        assert result["has_annotation"] is False
        assert result["source"] == "none"

    def test_network_failure_returns_error(self) -> None:
        from kuma_core.kuro.uniprot_features import fetch_active_site_features

        import urllib.request as _req
        with patch.object(_req, "urlopen", side_effect=OSError("network failure")):
            result = fetch_active_site_features("P12345")

        assert result["has_annotation"] is False
        assert result["source"] == "error"


# ---------------------------------------------------------------------------
# 5. Dispatcher registration tests
# ---------------------------------------------------------------------------


class TestDispatcherRegistration:
    """Verify the three new RPC names in _METHODS and _ASYNC_METHODS."""

    _EXPECTED = {
        "fetch_pdb_text",
        "fetch_active_site_residues",
        "compute_dispersion",
    }

    def test_methods_registered(self) -> None:
        from sidecar_kuro.dispatcher import _METHODS

        for name in self._EXPECTED:
            assert name in _METHODS, f"'{name}' not in _METHODS"

    def test_methods_callable(self) -> None:
        from sidecar_kuro.dispatcher import _METHODS

        for name in self._EXPECTED:
            assert callable(_METHODS[name]), f"_METHODS['{name}'] is not callable"

    def test_async_methods_registered(self) -> None:
        from sidecar_kuro.dispatcher import _ASYNC_METHODS

        for name in self._EXPECTED:
            assert name in _ASYNC_METHODS, f"'{name}' not in _ASYNC_METHODS"
