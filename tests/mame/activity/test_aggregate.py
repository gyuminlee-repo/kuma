from kuma_core.mame.activity.aggregate import aggregate_replicates


def test_aggregate_three_replicates():
    values = [2.40, 2.50, 2.45]
    mean, sd, n = aggregate_replicates(values)
    assert mean is not None and sd is not None
    assert abs(mean - 2.45) < 1e-6
    assert abs(sd - 0.05) < 0.001
    assert n == 3


def test_aggregate_single_value_no_sd():
    mean, sd, n = aggregate_replicates([1.5])
    assert mean == 1.5
    assert sd is None
    assert n == 1


def test_aggregate_empty():
    mean, sd, n = aggregate_replicates([])
    assert mean is None
    assert sd is None
    assert n == 0
