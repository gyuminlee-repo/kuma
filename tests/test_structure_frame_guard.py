# ruff: noqa: S101
"""Structure-accuracy guard: 3D Cα coordinates are only used for selection when
the loaded structure exactly covers the reference frame. Near-but-not-exact
structures fall back to 1-D distance instead of silently mis-placing residues.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

_PROJECT_ROOT = Path(__file__).parent.parent
_SIDECAR_DIR = _PROJECT_ROOT / "python-core"
if str(_SIDECAR_DIR) not in sys.path:
    sys.path.insert(0, str(_SIDECAR_DIR))

_REF = "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGDGTQDNLSGAEKAVQVKVK"


class TestStructureMatchesReference:
    def test_identical(self) -> None:
        from kuma_core.kuro.interface import structure_matches_reference

        assert structure_matches_reference(_REF, _REF) is True

    def test_trailing_stop_tolerated(self) -> None:
        from kuma_core.kuro.interface import structure_matches_reference

        assert structure_matches_reference(_REF + "*", _REF) is True

    def test_reference_is_clean_substring(self) -> None:
        """N-terminal tag on the structure; every ref residue is identical."""
        from kuma_core.kuro.interface import structure_matches_reference

        tagged = "MHHHHHH" + _REF
        assert structure_matches_reference(tagged, _REF) is True

    def test_interior_substitution_rejected(self) -> None:
        from kuma_core.kuro.interface import structure_matches_reference

        mutated = _REF[:10] + ("A" if _REF[10] != "A" else "G") + _REF[11:]
        assert structure_matches_reference(mutated, _REF) is False

    def test_empty_rejected(self) -> None:
        from kuma_core.kuro.interface import structure_matches_reference

        assert structure_matches_reference("", _REF) is False
        assert structure_matches_reference(_REF, "") is False


class TestHandlerGuard:
    def _base_params(self, **extra) -> dict:
        params = {
            "filepath": "unused.csv",
            "structure_accession": "P12345",
            "ref_seq": _REF,
            "structural_diversity": True,
        }
        params.update(extra)
        return params

    def test_ca_coords_dropped_on_mismatch(self, tmp_path) -> None:
        from sidecar_kuro.handlers import misc as _misc

        csv = tmp_path / "df.csv"
        csv.write_text("variant,y_pred\nA2G,0.9\nK5R,0.5\n")

        fake_coords = [None] + [(float(i), 0.0, 0.0) for i in range(1, 60)]
        captured: dict = {}

        def fake_load(**kwargs):
            captured["ca_coords"] = kwargs.get("ca_coords")
            return {"variants": [], "y_preds": []}

        with patch.object(_misc, "_get_cached_ca_coords", return_value=fake_coords), \
             patch.object(_misc, "_validate_filepath", return_value=csv), \
             patch("kuma_core.kuro.alphafold.fetch_ca_seq", return_value="MABCDEF" * 10), \
             patch.object(_misc, "load_evolvepro_csv", side_effect=fake_load):
            result = _misc.handle_load_evolvepro_csv(self._base_params())

        assert captured["ca_coords"] is None
        assert result["structure_frame_mismatch"] is True

    def test_ca_coords_kept_on_exact_match(self, tmp_path) -> None:
        from sidecar_kuro.handlers import misc as _misc

        csv = tmp_path / "df.csv"
        csv.write_text("variant,y_pred\nA2G,0.9\nK5R,0.5\n")

        fake_coords = [None] + [(float(i), 0.0, 0.0) for i in range(1, 60)]
        captured: dict = {}

        def fake_load(**kwargs):
            captured["ca_coords"] = kwargs.get("ca_coords")
            return {"variants": [], "y_preds": []}

        with patch.object(_misc, "_get_cached_ca_coords", return_value=fake_coords), \
             patch.object(_misc, "_validate_filepath", return_value=csv), \
             patch("kuma_core.kuro.alphafold.fetch_ca_seq", return_value=_REF), \
             patch.object(_misc, "load_evolvepro_csv", side_effect=fake_load):
            result = _misc.handle_load_evolvepro_csv(self._base_params())

        assert captured["ca_coords"] is fake_coords
        assert result["structure_frame_mismatch"] is False
