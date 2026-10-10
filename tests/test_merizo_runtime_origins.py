"""Shared/legacy origin equivalence with harmless files and native API mocks.

No test runs Merizo, loads weights, freezes a binary or establishes native host
portability. The wrappers still own each historical probe's output contract.
"""
from __future__ import annotations

import ast
import ctypes
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import ModuleType
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "scripts/merizo_windows_smoke"


def load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location("origin_equivalence_" + name, HARNESS / (name + ".py"))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


windows = load("frozen_entry")
posix = load("frozen_posix_entry")
shared = posix.origins


def outcome(function, *args, **kwargs):
    """Compare both successful records and exact rejection type/message."""
    try:
        return ("ok", function(*args, **kwargs))
    except ValueError as exc:
        return (type(exc).__name__, str(exc))


def module_records(internal: Path):
    records = []
    for name in sorted(shared.REQUIRED_MODULES):
        module = ModuleType(name)
        module.__file__ = str(internal / (name + ".pyc"))
        records.append((name, module))
    return records


class SharedOriginContracts(unittest.TestCase):
    def test_shared_helper_static_imports_are_stdlib_only(self):
        tree = ast.parse((HARNESS / "runtime_origins.py").read_text())
        roots = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                self.assertEqual(node.level, 0)
                roots.add((node.module or "").split(".")[0])
        self.assertLessEqual(roots, sys.stdlib_module_names)
        self.assertFalse(roots & {"run", "frozen_entry", "frozen_posix_entry", "torch", "predict", "model"})

    def test_isolated_import_loads_no_old_entry_or_scientific_package(self):
        code = """import json, sys
sys.path.insert(0, sys.argv[1])
import runtime_origins
print(json.dumps(sorted(name for name in sys.modules if
    name in {'run', 'frozen_entry', 'frozen_posix_entry', 'torch', 'predict', 'model'}
    or name.startswith(('torch.', 'model.')))))
"""
        result = subprocess.run([sys.executable, "-I", "-B", "-c", code, str(HARNESS)],
                                check=True, capture_output=True, text=True, timeout=15)
        self.assertEqual(json.loads(result.stdout), [])

    def test_module_origins_match_each_legacy_namespace_policy(self):
        with tempfile.TemporaryDirectory() as folder:
            internal = Path(folder) / "bundle/_internal"
            for legacy, check_namespace in ((windows, False), (posix, True)):
                for fault in (None, "missing", "no_origin", "outside", "namespace"):
                    records = module_records(internal)
                    if fault == "missing":
                        records.pop()
                    elif fault == "no_origin":
                        del records[0][1].__file__
                    elif fault == "outside":
                        records[0][1].__file__ = str(internal.parent.parent / "external.py")
                    elif fault == "namespace":
                        namespace = ModuleType("model.extra")
                        namespace.__path__ = [str(internal.parent)]
                        records.append((namespace.__name__, namespace))
                    with self.subTest(legacy=legacy.__name__, fault=fault):
                        result = outcome(legacy.module_origins, records, internal)
                        self.assertEqual(result, outcome(shared.module_origins, records, internal,
                                                        check_namespace_paths=check_namespace))
                        expected_ok = fault is None or (fault == "namespace" and not check_namespace)
                        self.assertEqual(result[0] == "ok", expected_ok)

    def test_windows_validation_keeps_required_dlls_and_system_rejections(self):
        with tempfile.TemporaryDirectory() as folder:
            alias = Path(folder) / "alias-segment" / ".."
            root, system = alias / "bundle", alias / "Windows"
            required = [str(root / "_internal" / name) for name in
                        ("python311.dll", "torch_cpu.dll", "c10.dll")]
            valid = required + [str(system / "System32/kernel32.dll")]
            cases = [valid, valid[1:]]
            for external in ("python311.dll", "Python3.dll", "python_d.dll", "torch_cpu.dll", "c10.dll"):
                cases.append(valid + [str(system / "System32" / external)])
            cases.append(valid + [str(Path(folder) / "elsewhere/extra.dll")])
            for index, paths in enumerate(cases):
                with self.subTest(paths=paths):
                    result = outcome(windows.validate_native_paths, paths, root, system)
                    self.assertEqual(result, outcome(shared.validate_windows_native_paths, paths, root, system))
                    self.assertEqual(result[0] == "ok", index == 0)
            self.assertEqual(windows.validate_native_paths(valid, root, system),
                             {"bundled": [str(Path(path).resolve()) for path in required],
                              "windows_system": [str((system / "System32/kernel32.dll").resolve())]})

    def test_windows_enumeration_is_bounded_and_uses_explicit_abi(self):
        with tempfile.TemporaryDirectory() as folder:
            alias = Path(folder) / "alias-segment" / ".."
            paths = [str(alias / name) for name in ("z.dll", "a.dll", "a.dll")]
            kernel, psapi = mock.Mock(), mock.Mock()
            kernel.GetCurrentProcess.return_value = 17

            def enumerate_modules(process, modules, size, needed, flags):
                self.assertEqual((process, flags), (17, 3))
                self.assertEqual(size, ctypes.sizeof(shared.wintypes.HMODULE) * 2048)
                ctypes.cast(needed, ctypes.POINTER(shared.wintypes.DWORD)).contents.value = (
                    ctypes.sizeof(shared.wintypes.HMODULE) * len(paths))
                for index in range(len(paths)):
                    modules[index] = index + 1
                return True

            def filename(process, handle, buffer, capacity):
                self.assertEqual((process, capacity), (17, 32768))
                buffer.value = paths[handle - 1]
                return len(buffer.value)

            psapi.EnumProcessModulesEx.side_effect = enumerate_modules
            psapi.GetModuleFileNameExW.side_effect = filename
            with mock.patch.object(shared.sys, "platform", "win32"), \
                 mock.patch.object(shared.ctypes, "WinDLL", side_effect=[kernel, psapi], create=True) as loader:
                expected = sorted({str(Path(path).resolve()) for path in paths}, key=str.casefold)
                self.assertNotEqual(expected, sorted(set(paths), key=str.casefold))
                self.assertEqual(shared.windows_loaded_native_paths(), expected)
            self.assertEqual(loader.call_args_list,
                             [mock.call("kernel32", use_last_error=True), mock.call("psapi", use_last_error=True)])
            self.assertIs(psapi.EnumProcessModulesEx.restype, shared.wintypes.BOOL)
            self.assertIs(psapi.GetModuleFileNameExW.restype, shared.wintypes.DWORD)
            for fault in ("capacity", "unresolved", "truncated"):
                def overflow(process, modules, size, needed, flags):
                    ctypes.cast(needed, ctypes.POINTER(shared.wintypes.DWORD)).contents.value = size + 1
                    return True
                psapi.EnumProcessModulesEx.side_effect = overflow if fault == "capacity" else enumerate_modules
                psapi.GetModuleFileNameExW.side_effect = None
                psapi.GetModuleFileNameExW.return_value = 0 if fault == "unresolved" else 32767
                with self.subTest(fault=fault), mock.patch.object(shared.sys, "platform", "win32"), \
                     mock.patch.object(shared.ctypes, "WinDLL", side_effect=[kernel, psapi], create=True), \
                     self.assertRaises(ValueError):
                    shared.windows_loaded_native_paths()
            with mock.patch.object(shared.sys, "platform", "linux"), self.assertRaisesRegex(ValueError, "Windows"):
                shared.windows_loaded_native_paths()

    def test_linux_map_parser_matches_old_api_for_escaped_or_missing_paths(self):
        prefix = "1000-2000 r-xp 00000000 08:01 12 "
        for name in ("/bundle with spaces/lib.so", "/bundle\ttab/lib.so", r"/bundle\040/lib.so",
                     r"/bundle\012/lib.so", "/bundle/lib.so (deleted)", "relative", ""):
            with self.subTest(name=name):
                self.assertEqual(outcome(posix.parse_linux_maps, prefix + name),
                                 outcome(shared.parse_linux_maps, prefix + name))
        self.assertEqual(shared.parse_linux_maps(prefix + "/bundle with spaces/lib.so"),
                         ["/bundle with spaces/lib.so"])

    @unittest.skipUnless(os.name == "posix", "POSIX absolute paths and symbolic links")
    def test_posix_native_equivalence_rejects_os_prefix_runtime_and_bundle_escape(self):
        for system, suffix, python in (("Linux", ".so", "libpython3.11.so.1.0"),
                                       ("Darwin", ".dylib", "libpython3.11.dylib")):
            with self.subTest(system=system), tempfile.TemporaryDirectory() as folder:
                root = Path(folder) / "bundle"
                root.mkdir()
                required = []
                for name in (python, "libtorch_cpu" + suffix, "libc10" + suffix):
                    file = root / name
                    file.touch()
                    required.append(str(file))
                cases = [required, required[1:]]
                cases += [required + ["/usr/lib/" + name] for name in
                          (python, "libtorch_cpu" + suffix, "libc10" + suffix, "libomp" + suffix)]
                outside = Path(folder) / "external"; outside.touch()
                escape = root / "other"; escape.symlink_to(outside)
                cases.append(required + [str(escape)])
                for index, paths in enumerate(cases):
                    # Typed snapshot records here exercise pure validation only;
                    # actual dyld pointers/ABI/stability have separate mock tests.
                    images = tuple(shared.DarwinImage(i, path, 8, shared.MH_MAGIC_64, shared.CPU_TYPE_ARM64,
                        0, shared.MH_DYLIB, shared.MH_DYLIB_IN_CACHE, True) for i, path in enumerate(paths))
                    kwargs = {"darwin_images": images} if system == "Darwin" else {}
                    with self.subTest(paths=paths):
                        result = outcome(posix.validate_native_paths, paths, root, system, **kwargs)
                        self.assertEqual(result, outcome(shared.validate_posix_native_paths, paths, root, system, **kwargs))
                        self.assertEqual(result[0] == "ok", index == 0)
                (root / python).unlink()
                required_images = tuple(shared.DarwinImage(i, path, 8, shared.MH_MAGIC_64,
                    shared.CPU_TYPE_ARM64, 0, shared.MH_DYLIB, shared.MH_DYLIB_IN_CACHE, True)
                    for i, path in enumerate(required))
                with self.assertRaisesRegex(ValueError, "missing"):
                    shared.validate_posix_native_paths(required, root, system,
                        darwin_images=required_images if system == "Darwin" else None)

    def test_darwin_typed_snapshot_and_contract_identity_are_shared(self):
        self.assertIs(posix.DarwinImage, shared.DarwinImage)
        self.assertIs(posix.MachHeader64, shared.MachHeader64)
        self.assertIs(posix.NativeOriginError, shared.NativeOriginError)
        self.assertEqual(shared.DARWIN_ORIGIN_CONTRACT, "darwin_dyld_shared_cache_v2")
        self.assertEqual(shared.LINUX_INVENTORY_MECHANISM, "proc_self_maps_executable_files")
        self.assertEqual(shared.DARWIN_INVENTORY_MECHANISM, "dyld_stable_indexed_cache_snapshots")
        with tempfile.TemporaryDirectory() as folder:
            for images in (None, (), ({"image_index": 0, "path": "/usr/lib/example.dylib"},)):
                with self.subTest(images=images), mock.patch.object(shared.ctypes, "string_at") as dereference:
                    result = outcome(shared.validate_posix_native_paths, ["/usr/lib/example.dylib"],
                                     Path(folder), "Darwin", darwin_images=images)
                    self.assertIn("same indexed dyld evidence snapshot", result[1])
                    dereference.assert_not_called()

    def test_rejected_snapshot_diagnostics_are_identical_and_bounded(self):
        paths = tuple(f"/native/{index}" for index in range(2050))
        self.assertEqual(posix.native_diagnostic(paths), shared.native_diagnostic(paths))
        result = shared.native_diagnostic(paths)
        self.assertEqual(result["native_diagnostic_total"], 2050)
        self.assertTrue(result["native_diagnostic_truncated"])
        self.assertEqual(len(result["native_diagnostic_paths"]), 2048)

    def test_both_old_builders_record_the_extracted_helper_hash(self):
        # Check the declared inventories without importing/executing a builder.
        for name in ("build_frozen.py", "build_frozen_posix.py"):
            tree = ast.parse((HARNESS / name).read_text())
            inventories = [ast.literal_eval(node) for node in ast.walk(tree)
                           if isinstance(node, ast.Tuple) and all(isinstance(item, ast.Constant)
                               and isinstance(item.value, str) for item in node.elts)
                           and any(isinstance(item, ast.Constant) and item.value == "run.py" for item in node.elts)]
            with self.subTest(builder=name):
                self.assertEqual(len(inventories), 1)
                self.assertIn("runtime_origins.py", inventories[0])


if __name__ == "__main__":
    unittest.main()
