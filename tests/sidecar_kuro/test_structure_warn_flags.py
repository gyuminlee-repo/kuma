"""The per-structure warning verdicts the result table now reads.

The UI used to re-derive "warning" from `hairpin_tm > 40` on every row, which
fired on most results because the threshold ignored the annealing
temperature. The verdict is now computed at serialize time by
``kuma_core.kuro.sdm_engine.secondary_structure_warn_flags`` -- hairpin on
the folded fraction at the pair's recommended Ta, homodimer on the absolute
design-scale Tm -- and shipped as four booleans on the wire model.

These tests pin the wire contract: the keys exist, they follow the profile's
Ta, and they are display-only (penalty and sequences are untouched).
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from kuma_core.kuro.annealing import compute_annealing
from kuma_core.kuro import neb_tm
from kuma_core.kuro.polymerase import PolymeraseRegistry
from kuma_core.kuro.sdm_engine import secondary_structure_warn_flags
from sidecar_kuro.core import _state, _state_lock
from sidecar_kuro.handlers.design import _serialize_result, handle_design_sdm_primers
from sidecar_kuro.models import SdmPrimerResultModel
from tests.conftest import TARGET_START

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures"
GENBANK = FIXTURES_DIR / "pSHCE-dmpR.gb"
EVOLVEPRO_CSV = FIXTURES_DIR / "dmpR_evolvepro.csv"

WARN_KEYS = {
    "hairpin_warn_fwd",
    "hairpin_warn_rev",
    "homodimer_warn_fwd",
    "homodimer_warn_rev",
}


@pytest.fixture
def restore_state():
    """A real design mutates module-level state; put it back afterwards."""
    with _state_lock:
        saved = (
            list(_state.results),
            dict(_state.candidates),
            list(_state.plate_mappings),
            dict(_state.dedup_info or {}),
            _state.design_provenance,
            list(_state.interventions),
        )
    yield
    with _state_lock:
        (
            _state.results,
            _state.candidates,
            _state.plate_mappings,
            _state.dedup_info,
            _state.design_provenance,
            _state.interventions,
        ) = saved


def _design(restore_state, polymerase: str):
    with EVOLVEPRO_CSV.open() as fh:
        mutations = [row["mutation"] for row in csv.DictReader(fh)][:6]
    return handle_design_sdm_primers({
        "fasta_path": str(GENBANK),
        "target_start": TARGET_START,
        "mutations_csv_or_text": "\n".join(mutations),
        "polymerase": polymerase,
        "overlap_len": 18,
        "rescue_pool": [],
        "auto_relax": False,
    })


def test_wire_rows_carry_the_four_verdicts(restore_state):
    response = _design(restore_state, "KOD")
    assert response["success_count"] > 0
    for row in response["results"]:
        for key in WARN_KEYS:
            assert key in row, f"{row['mutation']} is missing {key}"
            assert isinstance(row[key], bool)


def test_flags_track_the_profile_annealing_temperature(restore_state):
    """Serialize the same engine result under two profiles: the flags must
    follow each profile's recommended Ta while penalty and sequences are
    byte-identical."""
    response = _design(restore_state, "KOD")
    raw = response["results"][0]["mutation"]
    with _state_lock:
        r = next(res for res in _state.results if res.mutation.raw == raw)

    reg = PolymeraseRegistry()
    offsets = neb_tm.load_offsets()
    profiles = [reg.get("Taq"), reg.get("Q5")]
    serialized = [_serialize_result(r, profile=p) for p in profiles]
    tas = [
        compute_annealing(r.forward_seq, r.reverse_seq, p, offsets)["recommended_ta"]
        for p in profiles
    ]
    assert tas[0] != tas[1], "test needs two profiles with different Ta"

    assert serialized[0].forward_seq == serialized[1].forward_seq
    assert serialized[0].penalty == serialized[1].penalty
    for model, ta in zip(serialized, tas):
        expected = secondary_structure_warn_flags(r, ta)
        for key in WARN_KEYS:
            assert getattr(model, key) == expected[key]


def test_no_profile_falls_back_to_60c(restore_state):
    """Custom-evaluate and other profile-less serializations use the Ta
    fallback inside secondary_structure_warn_flags."""
    response = _design(restore_state, "KOD")
    raw = response["results"][0]["mutation"]
    with _state_lock:
        r = next(res for res in _state.results if res.mutation.raw == raw)

    model = _serialize_result(r)  # profile=None
    assert model.recommended_ta is None
    expected = secondary_structure_warn_flags(r, None)
    for key in WARN_KEYS:
        assert getattr(model, key) == expected[key]


def test_model_defaults_are_absent_not_false():
    """Rows serialized before the fields existed must not silently read as
    'no warning'; the flag is Optional[bool] defaulting to None."""
    model = SdmPrimerResultModel(
        mutation="A1V", aa_position=1, codon_pos=1,
        forward_seq="ATGC", reverse_seq="GCAT",
        fwd_len=20, rev_len=20, overlap_len=18,
        tm_no_fwd=60.0, tm_no_rev=60.0, tm_overlap=45.0,
        tm_condition_met=True, tolerance_used=0.5,
        has_offtarget=False, penalty=1.0,
        gc_fwd=50.0, gc_rev=50.0,
        wt_codon="GCT", mt_codon="GTT", overlap_seq="ATGC",
    )
    for key in WARN_KEYS:
        assert getattr(model, key) is None
