from pathlib import Path


def test_kuma_home_defaults_to_dot_kuma(monkeypatch):
    monkeypatch.setenv("HOME", "/tmp/testhome")
    from kuma_core.shared.config_paths import kuma_home

    assert kuma_home() == Path("/tmp/testhome/.kuma")


def test_kuma_logs_and_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    from kuma_core.shared.config_paths import kuma_cache_dir, kuma_logs_dir

    assert kuma_logs_dir() == tmp_path / ".kuma" / "logs"
    assert kuma_cache_dir() == tmp_path / ".kuma" / "cache"
