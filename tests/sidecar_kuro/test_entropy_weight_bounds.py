"""entropy_weight bound parity between the two RPC param models.

`LoadEvolveproParams.entropy_weight` and `RunBenchmarkParams.entropy_weight`
feed the same weighted-sum term in `kuma_core.kuro.evolvepro`:

    score = (1.0 - entropy_weight) * min_dist + entropy_weight * ent

so both are on the same [0, 1] scale. Before the fix only the benchmark model
carried `le=1.0`; the loader model had `ge=0.0` alone, which accepts `inf`
(`inf >= 0.0` is True) and let an infinite weight into the selection scoring.

The differing defaults (0.0 vs 0.3) are a deliberate per-endpoint choice and
are asserted here so a future bound change does not quietly unify them too.
"""
from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from sidecar_kuro.models import LoadEvolveproParams, RunBenchmarkParams

PARAM_MODELS = [LoadEvolveproParams, RunBenchmarkParams]


@pytest.mark.parametrize("model", PARAM_MODELS)
def test_entropy_weight_rejects_inf(model):
    with pytest.raises(ValidationError):
        model(entropy_weight=math.inf)


@pytest.mark.parametrize("model", PARAM_MODELS)
def test_entropy_weight_rejects_nan(model):
    with pytest.raises(ValidationError):
        model(entropy_weight=math.nan)


@pytest.mark.parametrize("model", PARAM_MODELS)
def test_entropy_weight_rejects_negative(model):
    with pytest.raises(ValidationError):
        model(entropy_weight=-0.1)


@pytest.mark.parametrize("model", PARAM_MODELS)
def test_entropy_weight_rejects_above_one(model):
    with pytest.raises(ValidationError):
        model(entropy_weight=1.5)


@pytest.mark.parametrize("model", PARAM_MODELS)
@pytest.mark.parametrize("value", [0.0, 0.3, 0.5, 1.0])
def test_entropy_weight_accepts_in_range(model, value):
    assert model(entropy_weight=value).entropy_weight == value


def test_entropy_weight_defaults_stay_distinct():
    # A differing default is a legitimate per-endpoint choice; only the bound
    # was unified.
    assert LoadEvolveproParams().entropy_weight == 0.0
    assert RunBenchmarkParams().entropy_weight == 0.3


def _numeric_constraints(model, field):
    """Extract ge/gt/le/lt from a pydantic v2 field regardless of how declared."""
    out = {}
    for meta in model.model_fields[field].metadata:
        for key in ("ge", "gt", "le", "lt"):
            if hasattr(meta, key):
                out[key] = getattr(meta, key)
    return out


def test_entropy_weight_constraints_identical_across_rpc_models():
    """Guards the family-B pattern: same parameter, two entry points, one bound.

    Asserted on constraint metadata rather than behaviour so that a future
    edit loosening one declaration fails here even if no value happens to
    exercise the gap.
    """
    load = _numeric_constraints(LoadEvolveproParams, "entropy_weight")
    bench = _numeric_constraints(RunBenchmarkParams, "entropy_weight")
    assert load == bench == {"ge": 0.0, "le": 1.0}
