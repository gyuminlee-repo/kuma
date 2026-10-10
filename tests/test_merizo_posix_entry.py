"""Mock/stdlib-only POSIX entry contracts; no model or freezing execution."""
from __future__ import annotations

import ast
import ctypes
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from types import ModuleType
import unittest
from unittest import mock

HARNESS = Path(__file__).resolve().parents[1] / "scripts/merizo_windows_smoke"
spec = importlib.util.spec_from_file_location("merizo_frozen_posix_entry_test", HARNESS / "frozen_posix_entry.py")
assert spec is not None and spec.loader is not None
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)


def mapping(path: str = "", *, permissions: str = "r-xp", inode: str = "123") -> str:
    return f"1000-2000 {permissions} 00000000 08:01 {inode}" + (" " + path if path else "")


class PosixEntryContracts(unittest.TestCase):
    def test_maps_preserves_spaces_and_deduplicates(self):
        raw = "\n".join([mapping("/bundle with spaces/libtorch_cpu.so"),
                         mapping("/bundle with spaces/libtorch_cpu.so"),
                         mapping("/bundle/libc10.so", permissions="r--p"),
                         mapping(inode="0"), mapping("[vdso]", inode="0")])
        self.assertEqual(entry.parse_linux_maps(raw), ["/bundle with spaces/libtorch_cpu.so"])
        self.assertEqual(entry.parse_linux_maps(mapping("/bundle\ttab/lib.so")), ["/bundle\ttab/lib.so"])

    def test_maps_rejects_deleted_ambiguous_malformed_and_oversize(self):
        for raw in (mapping("/bundle/lib.so (deleted)"), mapping(r"/bundle\012name/lib.so"),
                    mapping(r"/bundle\040name/lib.so"), mapping(r"/bundle\011name/lib.so"),
                    mapping(r"/bundle\999name/lib.so"), mapping("relative.so"), mapping(inode="9"),
                    mapping("/bundle/lib.so", inode="invalid"),
                    mapping("[unknown]", inode="5"), "bad line", mapping("/lib.so", permissions="rwxz"),
                    mapping("/bundle/" + "x" * entry.MAX_PATH_BYTES), ""):
            with self.subTest(raw=raw[:80]), self.assertRaises(ValueError):
                entry.parse_linux_maps(raw)
        with mock.patch.object(entry, "MAX_MAP_BYTES", 2), self.assertRaisesRegex(ValueError, "byte limit"):
            entry.parse_linux_maps(mapping("/x"))
        with mock.patch.object(entry, "MAX_NATIVE_IMAGES", 1), self.assertRaisesRegex(ValueError, "inventory"):
            entry.parse_linux_maps(mapping("/a") + "\n" + mapping("/b"))

    def test_maps_file_read_is_bounded(self):
        reader = mock.mock_open(read_data=b"x" * (entry.MAX_MAP_BYTES + 1))
        with mock.patch.object(entry.Path, "open", reader), self.assertRaisesRegex(ValueError, "byte limit"):
            entry.linux_native_paths()
        reader.return_value.read.assert_called_once_with(entry.MAX_MAP_BYTES + 1)

    def test_dyld_uses_explicit_abi_and_two_matching_snapshots(self):
        library = mock.Mock()
        library._dyld_image_count.return_value = 2
        library._dyld_get_image_name.side_effect = lambda index: [b"/bundle/Python", b"/usr/lib/libSystem.B.dylib"][index]
        with mock.patch.object(entry.ctypes, "CDLL", return_value=library) as loader:
            self.assertEqual(entry.darwin_native_paths(), ["/bundle/Python", "/usr/lib/libSystem.B.dylib"])
        loader.assert_called_once_with(None)
        self.assertEqual(library._dyld_image_count.argtypes, [])
        self.assertIs(library._dyld_image_count.restype, ctypes.c_uint32)
        self.assertEqual(library._dyld_get_image_name.argtypes, [ctypes.c_uint32])
        self.assertIs(library._dyld_get_image_name.restype, ctypes.c_char_p)
        self.assertEqual(library._dyld_get_image_name.call_count, 4)

    def test_dyld_rejects_unstable_overflow_null_relative_and_long_paths(self):
        for fault in ("unstable", "count_changed", "zero", "overflow", "null", "relative", "long", "utf8"):
            with self.subTest(fault=fault):
                library = mock.Mock()
                library._dyld_image_count.return_value = entry.MAX_NATIVE_IMAGES + 1 if fault == "overflow" else 1
                if fault == "zero":
                    library._dyld_image_count.return_value = 0
                if fault == "count_changed":
                    library._dyld_image_count.side_effect = [1, 2] * 4
                names = {"null": None, "relative": b"@rpath/lib.so", "long": b"/" + b"x" * entry.MAX_PATH_BYTES,
                         "utf8": b"/\xff"}
                if fault == "unstable":
                    library._dyld_get_image_name.side_effect = [b"/a", b"/b", b"/a", b"/b"]
                else:
                    library._dyld_get_image_name.return_value = names.get(fault, b"/a")
                with mock.patch.object(entry.ctypes, "CDLL", return_value=library), self.assertRaises(ValueError):
                    entry.darwin_native_paths()

    def test_bundle_requires_frozen_supported_arch_python_and_internal_root(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            executable = root / "merizo-frozen-smoke"
            executable.touch()
            internal = root / "_internal"
            internal.mkdir()
            with mock.patch.object(entry.sys, "executable", str(executable)), \
                 mock.patch.object(entry.sys, "frozen", True, create=True), \
                 mock.patch.object(entry.sys, "_MEIPASS", str(internal), create=True), \
                 mock.patch.object(entry.sys, "version_info", (3, 11, 9)), \
                 mock.patch.object(entry.platform, "system", return_value="Linux"), \
                 mock.patch.object(entry.platform, "machine", return_value="x86_64"):
                self.assertEqual(entry.bundle_root(), (root.resolve(), internal.resolve()))
                for attribute, value in (("frozen", False), ("_MEIPASS", str(root)),
                                         ("_MEIPASS", str(root.parent)), ("version_info", (3, 12, 0))):
                    with self.subTest(attribute=attribute, value=value), \
                         mock.patch.object(entry.sys, attribute, value), self.assertRaises(ValueError):
                        entry.bundle_root()
                with mock.patch.object(entry.platform, "machine", return_value="arm64"), self.assertRaises(ValueError):
                    entry.bundle_root()
                with mock.patch.object(entry.platform, "system", return_value="Darwin"), \
                     mock.patch.object(entry.platform, "machine", return_value="arm64"):
                    self.assertEqual(entry.bundle_root(), (root.resolve(), internal.resolve()))

    def test_module_origins_require_concrete_modules_and_namespace_containment(self):
        with tempfile.TemporaryDirectory() as folder:
            internal = Path(folder)
            modules = []
            for name in entry.REQUIRED_MODULES:
                module = ModuleType(name)
                module.__file__ = str(internal / (name + ".pyc"))
                modules.append((name, module))
            self.assertEqual(set(entry.module_origins(modules, internal)), entry.REQUIRED_MODULES)
            with self.assertRaisesRegex(ValueError, "Required"):
                entry.module_origins(modules[:-1], internal)
            modules[0][1].__file__ = str(internal.parent / "outside.py")
            with self.assertRaisesRegex(ValueError, "outside"):
                entry.module_origins(modules, internal)
            namespace = ModuleType("model.extra")
            namespace.__path__ = [str(internal.parent)]
            with self.assertRaisesRegex(ValueError, "Namespace"):
                entry.module_origins([("model.extra", namespace)], internal)

    def test_native_requires_actual_bundled_python_torch_and_c10(self):
        for system, names in (("Linux", ("libpython3.11.so.1.0", "libtorch_cpu.so", "libc10.so")),
                              ("Darwin", ("Python.framework/Versions/3.11/Python", "libtorch_cpu.dylib", "libc10.dylib"))):
            with self.subTest(system=system), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                paths = []
                for name in names:
                    path = root / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.touch()
                    paths.append(str(path))
                result = entry.validate_native_paths(paths, root, system)
                self.assertEqual(set(result["required_bundled"]), {"python", "torch_cpu", "c10"})
                for missing in range(3):
                    with self.subTest(missing=missing), self.assertRaisesRegex(ValueError, "missing"):
                        entry.validate_native_paths(paths[:missing] + paths[missing + 1:], root, system)
                Path(paths[0]).unlink()
                with self.assertRaisesRegex(ValueError, "missing"):
                    entry.validate_native_paths(paths, root, system)

    @unittest.skipUnless(os.name == "posix", "POSIX absolute-path and symlink semantics")
    def test_native_system_allowlist_never_allows_external_python_torch_or_homebrew(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for raw in ("/usr/lib/libpython3.11.so.1.0", "/usr/lib/libtorch_cpu.so", "/usr/lib/libc10.so",
                        "/System/Library/Frameworks/Python.framework/Versions/3.11/Python",
                        "/Library/Frameworks/Python.framework/Versions/3.11/Python",
                        "/opt/homebrew/lib/libomp.dylib", "/usr/local/lib/libc.so.6",
                        "/usr/lib/libunapproved.dylib", "/System/Library/Frameworks/Unapproved.framework/Unapproved"):
                system = "Linux" if ".so" in raw else "Darwin"
                with self.subTest(raw=raw), self.assertRaisesRegex(ValueError, "escaped|allowlist"):
                    entry.validate_native_paths([raw], root, system)
            self.assertTrue(entry.system_library(Path("/usr/lib/libSystem.B.dylib"), "Darwin"))
            self.assertTrue(entry.system_library(Path("/usr/lib/system/libsystem_kernel.dylib"), "Darwin"))
            self.assertFalse(entry.system_library(Path("/usr/lib/system/libsystem_unapproved.dylib"), "Darwin"))
            self.assertTrue(entry.system_library(Path("/System/Library/Frameworks/Accelerate.framework/Versions/A/Accelerate"), "Darwin"))
            self.assertFalse(entry.system_library(Path("/usr/local/lib/libc.so.6"), "Linux"))
            self.assertFalse(entry.system_library(Path("/System/Library/Frameworks/Foundation.framework/Versions/C/Resources/thirdparty.dylib"), "Darwin"))
            self.assertTrue(entry.system_library(Path("/System/Library/Frameworks/Accelerate.framework/Versions/A/Frameworks/vecLib.framework/Versions/A/libBLAS.dylib"), "Darwin"))

    @unittest.skipUnless(os.name == "posix", "POSIX symlink semantics")
    def test_internal_native_and_module_symlinks_allowed_but_escape_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            real_base = Path(folder) / "real"
            real_base.mkdir()
            alias = Path(folder) / "alias"
            alias.symlink_to(real_base, target_is_directory=True)
            base = alias.resolve()
            root = base / "bundle"
            root.mkdir()
            paths = []
            for name in ("libpython3.11.so.1.0", "libtorch_cpu.so", "libc10.so"):
                target = root / "lib" / name
                target.parent.mkdir(exist_ok=True)
                target.touch()
                link = root / name
                link.symlink_to(target.relative_to(root))
                paths.append(str(link))
            self.assertEqual(len(entry.validate_native_paths(paths, root, "Linux")["bundled"]), 3)
            outside = base / "libc10.so"
            outside.touch()
            link = root / "libc10.so"
            link.unlink()
            link.symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "escaped"):
                entry.validate_native_paths(paths, root, "Linux")
            module_link = root / "predict.py"
            module_link.symlink_to(outside)
            module = ModuleType("predict")
            module.__file__ = str(module_link)
            with self.assertRaisesRegex(ValueError, "outside"):
                entry.module_origins([("predict", module)], root)
            system_link = root / "libc.so.6"
            # Portable stand-in: no Linux library or /var spelling assumptions.
            external_system_image = base / "libc.so.6"
            external_system_image.touch()
            system_link.symlink_to(external_system_image)
            with self.assertRaisesRegex(ValueError, "symlink escaped"):
                entry.validate_native_paths([str(system_link)], root, "Linux")

    def test_gate_requires_own_session_location_and_bounded_wait(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            gate = root / "start gate"
            with mock.patch.object(entry.os, "getsid", return_value=42, create=True), \
                 mock.patch.object(entry.os, "getpgrp", return_value=42, create=True), \
                 mock.patch.object(entry.os, "getpid", return_value=42), \
                 mock.patch.object(entry.Path, "cwd", return_value=root), \
                 mock.patch.dict(entry.os.environ, {"KUMA_MERIZO_START_GATE": str(gate)}):
                with mock.patch.object(entry.time, "monotonic", side_effect=[0, 31]), \
                     self.assertRaises(TimeoutError):
                    entry.wait_for_job_gate()
                gate.touch()
                entry.wait_for_job_gate()
                with mock.patch.object(entry.os, "getsid", return_value=8), self.assertRaisesRegex(ValueError, "session"):
                    entry.wait_for_job_gate()
                with mock.patch.dict(entry.os.environ, {"KUMA_MERIZO_START_GATE": str(root.parent / "outside")}), \
                     self.assertRaisesRegex(ValueError, "isolated"):
                    entry.wait_for_job_gate()
                with mock.patch.dict(entry.os.environ, {}, clear=True), self.assertRaisesRegex(ValueError, "required"):
                    entry.wait_for_job_gate()

    def test_entry_calls_direct_inference_only_after_gate_and_verified_weights(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "result.json"
            adapter = ModuleType("run")
            setattr(adapter, "COMMIT", "pinned mock commit")
            order = []
            weights = mock.Mock(side_effect=lambda path: order.append("weights") or {"weight": "hash"})
            inference = mock.Mock(side_effect=lambda *args: order.append("inference") or {"status": "passed"})
            setattr(adapter, "verify_weights", weights)
            setattr(adapter, "inference", inference)
            with mock.patch.dict(sys.modules, {"run": adapter}), \
                 mock.patch.object(entry, "bundle_root", return_value=(root, root / "_internal")), \
                 mock.patch.object(entry, "wait_for_job_gate", side_effect=lambda: order.append("gate")):
                self.assertEqual(entry.main(["--fixture", str(root / "fixture"), "--output", str(output)]), 0)
            self.assertEqual(order, ["gate", "weights", "inference"])
            inference.assert_called_once_with((root / "fixture").resolve(), root / "_internal/merizo_weights", entry.runtime_provenance)
            result = json.loads(output.read_text())
            self.assertTrue(result["frozen"])
            self.assertEqual(result["source_commit"], "pinned mock commit")
            with mock.patch.object(entry, "bundle_root", side_effect=ValueError("injected origin failure")):
                self.assertEqual(entry.main(["--fixture", str(root / "fixture"), "--output", str(output)]), 2)
            self.assertIn("injected origin failure", json.loads(output.read_text())["error"])

    def test_json_is_bounded_and_rejects_nonfinite_values(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "report.json"
            with self.assertRaisesRegex(ValueError, "size limit"):
                entry.write_report(path, {"text": "x" * entry.MAX_REPORT_BYTES})
            with self.assertRaises(ValueError):
                entry.write_report(path, {"number": float("nan")})
            self.assertFalse(path.exists())

    def test_provenance_dispatch_and_shared_guard_surround_weight_load(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            for system, function in (("Linux", "linux_native_paths"), ("Darwin", "darwin_native_paths")):
                with self.subTest(system=system), \
                     mock.patch.object(entry, "bundle_root", return_value=(root, root / "_internal")), \
                     mock.patch.object(entry, "module_origins", return_value={"predict": "inside"}), \
                     mock.patch.object(entry.platform, "system", return_value=system), \
                     mock.patch.object(entry, function, return_value=[str(root / "native")]), \
                     mock.patch.object(entry, "validate_native_paths", return_value={"bundled": []}) as validate:
                    report = entry.runtime_provenance()
                    self.assertTrue(report["frozen"])
                    self.assertEqual(report["bundle_root"], str(root))
                    validate.assert_called_once_with([str(root / "native")], root, system)
        # The actual shared function remains the inference implementation. Its
        # two guards bracket weight deserialization and the segmentation call.
        tree = ast.parse((HARNESS / "run.py").read_text())
        inference = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "inference")
        calls = [node for node in ast.walk(inference) if isinstance(node, ast.Call)]
        guards = sorted(node.lineno for node in calls if isinstance(node.func, ast.Name) and node.func.id == "runtime_guard")
        load = next(node.lineno for node in calls if isinstance(node.func, ast.Attribute) and node.func.attr == "read_split_weight_files")
        segment = next(node.lineno for node in calls if isinstance(node.func, ast.Attribute) and node.func.attr == "segment")
        self.assertEqual(len(guards), 2)
        self.assertLess(guards[0], load)
        self.assertLess(segment, guards[1])


if __name__ == "__main__":
    unittest.main()
