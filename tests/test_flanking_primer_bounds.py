import random

import pytest

from kuma_core.mame.ingest.barcode_package import design_flanking_primers
from kuma_core.mame.ingest.polymerase import get_profile


@pytest.mark.parametrize("tm_range", [(-1000.0, 1000.0), (1000.0, 1001.0)])
@pytest.mark.parametrize("topology", ["linear", "circular"])
def test_entire_primer_binding_site_stays_in_flank(
    tm_range: tuple[float, float], topology: str,
) -> None:
    rng = random.Random(471)
    template = "".join(rng.choice("ACGT") for _ in range(400))

    forward, reverse, _ = design_flanking_primers(
        template, 100, 200, get_profile("Q5"), flank_min=20, flank_max=40,
        binding_min_len=18, binding_max_len=18, tm_min=tm_range[0],
        tm_max=tm_range[1], require_gc_clamp=False, topology=topology,
    )

    forward_site = forward.upper()
    reverse_site = reverse.upper().translate(str.maketrans("ACGT", "TGCA"))[::-1]
    assert template.count(forward_site) == template.count(reverse_site) == 1
    assert 60 <= template.index(forward_site) <= 80 - len(forward_site)
    assert 220 <= template.index(reverse_site) <= 240 - len(reverse_site)


def test_flank_too_narrow_for_binding_site_is_rejected() -> None:
    with pytest.raises(ValueError, match="binding_min_len"):
        design_flanking_primers(
            "ACGT" * 100, 100, 200, get_profile("Q5"), flank_min=5, flank_max=10,
            binding_min_len=18, binding_max_len=18, require_gc_clamp=False,
        )
