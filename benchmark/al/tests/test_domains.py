"""Tests for al.domains (real-domain resolution + stratification)."""

from __future__ import annotations

import json

import pytest

from al.domains import (
    DomainsUnavailable,
    classify_stratum,
    domain_count,
    fetch_domains,
)


def test_cache_hit_needs_no_network(tmp_path):
    acc = "P12345"
    (tmp_path / f"domains_{acc}.json").write_text(
        json.dumps({"accession": acc, "domains": [
            {"name": "A", "start": 1, "end": 50},
            {"name": "B", "start": 60, "end": 120},
        ]})
    )
    doms = fetch_domains(acc, tmp_path, allow_network=False)
    assert domain_count(doms) == 2
    assert doms[0]["start"] == 1


def test_missing_cache_offline_raises(tmp_path):
    with pytest.raises(DomainsUnavailable):
        fetch_domains("Q99999", tmp_path, allow_network=False)


def test_classify_stratum():
    doms = [{"name": "A", "start": 1, "end": 50}, {"name": "B", "start": 60, "end": 120}]
    # single-domain protein
    assert classify_stratum([{"name": "X", "start": 1, "end": 100}], [10, 20, 30]) == "single"
    # mutations span both domains -> multi
    assert classify_stratum(doms, [10, 70, 80]) == "multi"
    # mutations all within one domain -> degenerate
    assert classify_stratum(doms, [10, 20, 45]) == "degenerate"
