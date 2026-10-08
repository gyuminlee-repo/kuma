import random

import pytest

from kuma_core.mame.ingest.barcode_package import design_flanking_primers
from kuma_core.mame.ingest.polymerase import get_profile


@pytest.mark.parametrize("tm_range", [(-1000.0, 1000.0), (1000.0, 1001.0)])
@pytest.mark.parametrize("topology", ["linear", "circular"])
def test_entire_primer_binding_site_stays_outside_the_gene(
    tm_range: tuple[float, float], topology: str,
) -> None:
    rng = random.Random(471)
    template = "".join(rng.choice("ACGT") for _ in range(400))

    forward, reverse, _ = design_flanking_primers(
        template, 100, 200, get_profile("Q5"), overhang_min=20, overhang_max=40,
        binding_min_len=18, binding_max_len=18, tm_min=tm_range[0],
        tm_max=tm_range[1], require_gc_clamp=False, topology=topology,
    )

    forward_site = forward.upper()
    reverse_site = reverse.upper().translate(str.maketrans("ACGT", "TGCA"))[::-1]
    assert template.count(forward_site) == template.count(reverse_site) == 1
    fwd_start = template.index(forward_site)
    rev_start = template.index(reverse_site)
    # Overhang bounds, plus the gap invariant that no site enters [100, 200).
    assert 20 <= 100 - fwd_start <= 40
    assert fwd_start + len(forward_site) <= 100
    assert 20 <= rev_start + len(reverse_site) - 200 <= 40
    assert rev_start >= 200


def test_overhang_too_small_for_binding_site_is_rejected() -> None:
    with pytest.raises(ValueError, match="binding_min_len"):
        design_flanking_primers(
            "ACGT" * 100, 100, 200, get_profile("Q5"), overhang_min=5, overhang_max=10,
            binding_min_len=18, binding_max_len=18, require_gc_clamp=False,
        )
