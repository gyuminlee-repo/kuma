from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_build_sidecar_module():
    path = Path(__file__).resolve().parents[1] / "python-core" / "build_sidecar.py"
    spec = importlib.util.spec_from_file_location("build_sidecar_for_test", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_evolvepro_sidecar_packages_adapter_runtime_helpers():
    build_sidecar = _load_build_sidecar_module()

    add_data = set(build_sidecar.TARGETS["evolvepro"]["add_data"])

    assert ("kuma_core/evolvepro/adapter.py", "kuma_core/evolvepro") in add_data
    assert ("kuma_core/evolvepro/embedding_cache.py", "kuma_core/evolvepro") in add_data
