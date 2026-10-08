def test_logger_writes_to_kuma_home_log(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    import importlib

    import kuma_core.shared.config_paths as cp
    import kuma_core.shared.logging as lg

    importlib.reload(cp)
    importlib.reload(lg)
    log = lg.get_logger("test_logger_unique")
    log.info("hello")
    for h in log.handlers:
        try:
            h.flush()
        except Exception:
            pass
    assert (tmp_path / ".kuma" / "logs" / "test_logger_unique.log").exists()
