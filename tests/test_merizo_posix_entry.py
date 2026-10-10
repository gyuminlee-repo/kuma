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


class FakeDyld:
    """Real ctypes buffers, with only public dyld calls replaced (no model)."""

    def __init__(self, paths, *, flags=entry.MH_DYLIB_IN_CACHE, member=True):
        self.names = [ctypes.create_string_buffer(path.encode() if isinstance(path, str) else path)
                      for path in paths]
        self.headers = [entry.MachHeader64(entry.MH_MAGIC_64, entry.CPU_TYPE_ARM64, 0,
                                          entry.MH_DYLIB, 0, 0, flags, 0) for _ in paths]
        self.library = mock.Mock(spec=["_dyld_image_count", "_dyld_get_image_name",
                                      "_dyld_get_image_header", "_dyld_shared_cache_contains_path"])
        self.library._dyld_image_count.return_value = len(paths)
        self.library._dyld_get_image_name.side_effect = lambda index: ctypes.cast(
            self.names[index], ctypes.POINTER(ctypes.c_char))
        self.library._dyld_get_image_header.side_effect = lambda index: ctypes.addressof(self.headers[index])
        self.library._dyld_shared_cache_contains_path.return_value = member

    def snapshot(self):
        with mock.patch.object(entry.ctypes, "CDLL", return_value=self.library):
            return entry.darwin_native_images()


def validate_paths(paths, root, system, **kwargs):
    if system == "Darwin" and "darwin_images" not in kwargs:
        kwargs["darwin_images"] = FakeDyld(paths).snapshot()
    return entry.validate_native_paths(paths, root, system, **kwargs)


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
        fake = FakeDyld(["/bundle/Python", "/usr/lib/libSystem.B.dylib"])
        library = fake.library
        # arm64e CPU subtype capability bits are not a different architecture.
        fake.headers[1].cpusubtype = ctypes.c_int32(0x80000002).value
        with mock.patch.object(entry.ctypes, "CDLL", return_value=library) as loader:
            images = entry.darwin_native_images()
        self.assertEqual([image.path for image in images], ["/bundle/Python", "/usr/lib/libSystem.B.dylib"])
        self.assertEqual([image.image_index for image in images], [0, 1])
        self.assertEqual(images[1].header_address, ctypes.addressof(fake.headers[1]))
        self.assertEqual(images[1].flags, entry.MH_DYLIB_IN_CACHE)
        self.assertTrue(images[1].shared_cache_member)
        loader.assert_called_once_with(None)
        self.assertEqual(library._dyld_image_count.argtypes, [])
        self.assertIs(library._dyld_image_count.restype, ctypes.c_uint32)
        for name, result in (("_dyld_get_image_name", ctypes.POINTER(ctypes.c_char)),
                             ("_dyld_get_image_header", ctypes.c_void_p)):
            function = getattr(library, name)
            self.assertEqual(function.argtypes, [ctypes.c_uint32])
            self.assertIs(function.restype, result)
            self.assertEqual(function.call_count, 4)
        self.assertEqual(library._dyld_shared_cache_contains_path.argtypes, [ctypes.c_char_p])
        self.assertIs(library._dyld_shared_cache_contains_path.restype, ctypes.c_bool)
        self.assertEqual(library._dyld_shared_cache_contains_path.call_count, 4)
        self.assertEqual(ctypes.sizeof(entry.MachHeader64), 32)
        self.assertEqual(entry.MachHeader64.flags.offset, 24)

    def test_dyld_rejects_changed_index_path_address_flags_or_membership(self):
        for fault in ("index", "path", "address", "flags", "membership", "count_changed"):
            with self.subTest(fault=fault):
                fake = FakeDyld(["/a", "/b"])
                library = fake.library
                if fault == "index":
                    # Same path set and stable count, but different index associations.
                    library._dyld_get_image_name.side_effect = [ctypes.cast(fake.names[i], ctypes.POINTER(ctypes.c_char))
                                                               for i in (0, 1, 1, 0) * 2]
                elif fault == "path":
                    library._dyld_get_image_name.side_effect = [ctypes.cast(fake.names[i], ctypes.POINTER(ctypes.c_char))
                                                               for i in (0, 1, 1, 1) * 2]
                elif fault == "address":
                    library._dyld_get_image_header.side_effect = [ctypes.addressof(fake.headers[i])
                                                                 for i in (0, 1, 1, 0) * 2]
                elif fault == "flags":
                    def changed_header(index):
                        fake.headers[index].flags ^= 1
                        return ctypes.addressof(fake.headers[index])
                    library._dyld_get_image_header.side_effect = changed_header
                elif fault == "membership":
                    library._dyld_shared_cache_contains_path.side_effect = [True, True, False, True] * 2
                else:
                    library._dyld_image_count.side_effect = [2, 3] * 4
                with self.assertRaisesRegex(ValueError, "stabilize"):
                    fake.snapshot()
                self.assertLessEqual(library._dyld_get_image_name.call_count, 8)

    def test_dyld_rejects_overflow_null_relative_long_and_invalid_utf8_paths(self):
        for fault in ("zero", "overflow", "null", "relative", "long", "utf8", "newline", "carriage_return",
                      "windows_drive", "windows_slashes", "windows_unc"):
            with self.subTest(fault=fault):
                names = {"relative": b"@rpath/lib.so", "long": b"/" + b"x" * entry.MAX_PATH_BYTES,
                         "utf8": b"/\xff", "newline": b"/bad\npath", "carriage_return": b"/bad\rpath",
                         "windows_drive": br"C:\bundle\native.dylib", "windows_slashes": b"C:/bundle/native.dylib",
                         "windows_unc": br"\\server\bundle\native.dylib"}
                fake = FakeDyld([names.get(fault, b"/a")])
                if fault in {"zero", "overflow"}:
                    fake.library._dyld_image_count.return_value = 0 if fault == "zero" else entry.MAX_NATIVE_IMAGES + 1
                if fault == "null":
                    fake.library._dyld_get_image_name.side_effect = None
                    fake.library._dyld_get_image_name.return_value = ctypes.POINTER(ctypes.c_char)()
                with self.assertRaises(ValueError):
                    fake.snapshot()

    def test_dyld_path_copy_is_bounded_before_allocation(self):
        fake = FakeDyld(["/a"])
        pointer = mock.Mock()
        pointer.__getitem__ = mock.Mock(return_value=b"x")
        fake.library._dyld_get_image_name.side_effect = None
        fake.library._dyld_get_image_name.return_value = pointer
        with self.assertRaisesRegex(ValueError, "byte limit"):
            fake.snapshot()
        self.assertEqual(pointer.__getitem__.call_count, entry.MAX_PATH_BYTES + 1)
        fake.library._dyld_get_image_header.assert_not_called()

    def test_dyld_rejects_missing_api_null_header_and_invalid_native_abi(self):
        for name in ("_dyld_image_count", "_dyld_get_image_name", "_dyld_get_image_header",
                     "_dyld_shared_cache_contains_path"):
            fake = FakeDyld(["/a"])
            delattr(fake.library, name)
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "unavailable"):
                fake.snapshot()
        with mock.patch.object(entry.ctypes, "CDLL", side_effect=OSError("missing")), \
             self.assertRaisesRegex(ValueError, "unavailable"):
            entry.darwin_native_images()
        for field, value in (("magic", 0xCFFAEDFE), ("magic", 0xFEEDFACE), ("cputype", 0x01000007),
                             ("cputype", 12), ("cpusubtype", 99), ("filetype", 1), ("filetype", 9)):
            fake = FakeDyld(["/a"])
            setattr(fake.headers[0], field, value)
            with self.subTest(field=field, value=value), self.assertRaisesRegex(ValueError, "header"):
                fake.snapshot()
        for address in (None, 0, 1):
            fake = FakeDyld(["/a"])
            fake.library._dyld_get_image_header.side_effect = None
            fake.library._dyld_get_image_header.return_value = address
            with self.subTest(address=address), \
                 mock.patch.object(entry.ctypes, "string_at") as read, self.assertRaisesRegex(ValueError, "header"):
                fake.snapshot()
            read.assert_not_called()
        with mock.patch.object(entry.sys, "byteorder", "big"), self.assertRaisesRegex(ValueError, "ABI"):
            FakeDyld(["/a"]).snapshot()
        with mock.patch.object(entry.ctypes, "sizeof", return_value=4), self.assertRaisesRegex(ValueError, "ABI"):
            FakeDyld(["/a"]).snapshot()

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
                root = Path(folder).resolve()
                host_files = {}
                for name in names:
                    path = root / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.touch()
                    host_files["/bundle/" + name] = path
                # dyld speaks POSIX even on a Windows test host. Map only the
                # filesystem boundary; existence checks still use real files.
                paths = list(host_files)
                with mock.patch.object(entry, "Path", side_effect=lambda raw: host_files[raw]):
                    result = validate_paths(paths, root, system)
                    self.assertEqual(set(result["required_bundled"]), {"python", "torch_cpu", "c10"})
                    for missing in range(3):
                        with self.subTest(missing=missing), self.assertRaisesRegex(ValueError, "missing"):
                            validate_paths(paths[:missing] + paths[missing + 1:], root, system)
                    host_files[paths[0]].unlink()
                    with self.assertRaisesRegex(ValueError, "missing"):
                        validate_paths(paths, root, system)

    @unittest.skipUnless(os.name == "posix", "POSIX absolute-path semantics")
    def test_os_roots_membership_and_loaded_cache_flag_are_all_required(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            bundled = []
            for name in ("libpython3.11.dylib", "libtorch_cpu.dylib", "libc10.dylib"):
                path = root / name
                path.touch()
                bundled.append(str(path))
            for official in ("/usr/lib/libSystem.B.dylib", "/usr/lib/system/libunlisted.dylib",
                             "/System/Library/PrivateFrameworks/NewOS.framework/NewOS",
                             "/System/Library/Frameworks/Accelerate.framework/Versions/A/Frameworks/vecLib.framework/Versions/A/libQuadrature.dylib"):
                paths = [*bundled, official]
                result = validate_paths(paths, root, "Darwin")
                self.assertEqual(result["posix_system"], [official])
                # A familiar name or OS path alone provides no exception.
                self.assertFalse(entry.system_library(Path(official), "Darwin"))
                for member, flags, filetype in ((False, entry.MH_DYLIB_IN_CACHE, entry.MH_DYLIB),
                                               (True, 0, entry.MH_DYLIB),
                                               (True, entry.MH_DYLIB_IN_CACHE, entry.MH_BUNDLE)):
                    fake = FakeDyld(paths)
                    images = list(fake.snapshot())
                    images[-1] = images[-1]._replace(shared_cache_member=member, flags=flags, filetype=filetype)
                    with self.subTest(path=official, member=member, flags=flags, filetype=filetype), \
                         self.assertRaisesRegex(ValueError, "allowlist"):
                        validate_paths(paths, root, "Darwin", darwin_images=tuple(images))
            for raw in ("/opt/homebrew/lib/libSystem.B.dylib", "/usr/local/lib/libSystem.B.dylib",
                        "/usr/library/libSystem.B.dylib", "/System/LibraryOther/libSystem.B.dylib",
                        "/System/Library/../Library/libSystem.B.dylib", "/usr/lib", "/System/Library"):
                with self.subTest(raw=raw), self.assertRaisesRegex(ValueError, "allowlist"):
                    validate_paths([*bundled, raw], root, "Darwin")

    @unittest.skipUnless(os.name == "posix", "POSIX absolute-path semantics")
    def test_cached_external_runtimes_never_get_os_exception(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for raw in ("/usr/lib/libpython3.11.dylib", "/usr/lib/libtorch_cpu.dylib", "/usr/lib/libc10.dylib",
                        "/System/Library/Frameworks/Python.framework/Versions/3.11/Python",
                        "/Library/Frameworks/Python.framework/Versions/3.11/Python",
                        "/opt/homebrew/lib/libomp.dylib", "/usr/lib/libomp.dylib", "/usr/lib/libgomp.dylib",
                        "/usr/lib/libiomp5.dylib", "/usr/lib/libopenblas.dylib", "/usr/lib/libmkl_core.dylib",
                        "/System/Library/torch/custom.dylib", "/usr/lib/site-packages/arbitrary.dylib"):
                # Even both true cache indicators cannot promote a runtime.
                with self.subTest(raw=raw), self.assertRaisesRegex(ValueError, "runtime escaped"):
                    validate_paths([raw], root, "Darwin")
            for raw in ("/usr/lib/libpython3.11.so.1.0", "/usr/lib/libtorch_cpu.so", "/usr/lib/libc10.so",
                        "/usr/local/lib/libc.so.6"):
                with self.subTest(raw=raw), self.assertRaisesRegex(ValueError, "escaped|allowlist"):
                    validate_paths([raw], root, "Linux")
            self.assertFalse(entry.system_library(Path("/usr/local/lib/libc.so.6"), "Linux"))

    def test_validation_rejects_missing_mismatched_or_json_dyld_evidence_without_dereference(self):
        paths = ["/usr/lib/libSystem.B.dylib"]
        images = FakeDyld(paths).snapshot()
        cases = (None, (), (images[0]._replace(image_index=1),), (images[0]._replace(path="/different"),),
                 (dict(images[0]._asdict(), header_address=1),))
        with tempfile.TemporaryDirectory() as folder:
            for evidence in cases:
                with self.subTest(evidence=evidence), mock.patch.object(entry.ctypes, "string_at") as read, \
                     self.assertRaisesRegex(ValueError, "snapshot"):
                    entry.validate_native_paths(paths, Path(folder), "Darwin", darwin_images=evidence)
                read.assert_not_called()

    @unittest.skipUnless(os.name == "posix", "POSIX symlink semantics")
    def test_cache_flags_cannot_approve_bundle_symlink_escape_or_os_root_escape(self):
        official = Path("/usr/lib/libSystem.B.dylib")
        image = FakeDyld([str(official)]).snapshot()[0]
        self.assertFalse(entry.darwin_cached_os_image(official, Path("/outside/libSystem.B.dylib"), image))
        self.assertFalse(entry.darwin_cached_os_image(Path("/outside/libSystem.B.dylib"), official, image))
        with tempfile.TemporaryDirectory() as folder:
            real_root = Path(folder) / "real"
            real_root.mkdir()
            alias = Path(folder) / "alias"
            alias.symlink_to(real_root, target_is_directory=True)
            # Exercise macOS-style temporary-path aliases on every POSIX host.
            root = alias.resolve()
            link = root / "libSystem.B.dylib"
            link.symlink_to(official)
            with self.assertRaisesRegex(ValueError, "symlink escaped"):
                validate_paths([str(link)], root, "Darwin")

    def test_rejected_origin_carries_same_inventory_without_reenumeration(self):
        paths = ["/bundle/libpython3.11.dylib", "/System/Library/unapproved.dylib"]
        images = FakeDyld(paths).snapshot()
        with tempfile.TemporaryDirectory() as folder, \
             mock.patch.object(entry, "bundle_root", return_value=(Path(folder), Path(folder) / "_internal")), \
             mock.patch.object(entry, "module_origins", return_value={}), \
             mock.patch.object(entry.platform, "system", return_value="Darwin"), \
             mock.patch.object(entry, "darwin_native_images", return_value=images) as inventory, \
             mock.patch.object(entry, "validate_native_paths", side_effect=ValueError("unapproved native image")) as validate:
            with self.assertRaises(entry.NativeOriginError) as caught:
                entry.runtime_provenance()
        inventory.assert_called_once_with()
        self.assertEqual(validate.call_count, 1)
        self.assertEqual(validate.call_args.args[0], paths)
        self.assertIs(validate.call_args.kwargs["darwin_images"], images)
        self.assertEqual(caught.exception.paths, tuple(paths))
        self.assertIsInstance(caught.exception.__cause__, ValueError)

    def test_native_diagnostic_limits_preserve_paths_or_mark_truncation(self):
        cases = (("/unchanged path/lib.dylib",), tuple(f"/image/{index}" for index in range(2050)),
                 tuple("/" + "x" * 4000 + str(index) for index in range(300)),
                 tuple("/" + "\U0001f9ec" * 1000 + str(index) for index in range(300)),
                 ("/" + "x" * 4096, "/valid", "relative", "/bad\nname"))
        for paths in cases:
            with self.subTest(total=len(paths)):
                report = entry.native_diagnostic(paths)
                kept = report["native_diagnostic_paths"]
                self.assertEqual(report["native_diagnostic_total"], len(paths))
                self.assertEqual(report["native_diagnostic_truncated"], len(kept) != len(paths))
                self.assertEqual(report["native_diagnostic_snapshot"], "rejected_validation_snapshot")
                self.assertLessEqual(len(kept), 2048)
                self.assertTrue(all(path in paths and len(path.encode("utf-8")) <= 4096 for path in kept))
                self.assertLessEqual(len(json.dumps(report, indent=2).encode("utf-8")), 256 * 1024)

    def test_main_retains_native_failure_and_optional_bounded_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "failure.json"
            error = entry.NativeOriginError("original rejection", ("/rejected/path",))
            argv = ["--fixture", str(Path(folder) / "fixture"), "--output", str(output)]
            with mock.patch.object(entry, "bundle_root", side_effect=error):
                self.assertEqual(entry.main(argv), 2)
            report = json.loads(output.read_text())
            self.assertEqual(report["status"], "failed")
            self.assertIn("original rejection", report["error"])
            self.assertEqual(report["native_diagnostic_paths"], ["/rejected/path"])
            with mock.patch.object(entry, "bundle_root", side_effect=error), \
                 mock.patch.object(entry, "native_diagnostic", side_effect=RuntimeError("diagnostic failure")):
                self.assertEqual(entry.main(argv), 2)
            report = json.loads(output.read_text())
            self.assertEqual(report["status"], "failed")
            self.assertIn("original rejection", report["error"])
            self.assertNotIn("native_diagnostic_paths", report)

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
            self.assertEqual(len(validate_paths(paths, root, "Linux")["bundled"]), 3)
            outside = base / "libc10.so"
            outside.touch()
            link = root / "libc10.so"
            link.unlink()
            link.symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "escaped"):
                validate_paths(paths, root, "Linux")
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
                validate_paths([str(system_link)], root, "Linux")

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
            for system, function in (("Linux", "linux_native_paths"), ("Darwin", "darwin_native_images")):
                # This test mocks validation and checks dispatch, not host paths.
                paths = ["/bundle/native"]
                darwin_inventory = FakeDyld(paths).snapshot()
                inventory = darwin_inventory if system == "Darwin" else paths
                with self.subTest(system=system), \
                     mock.patch.object(entry, "bundle_root", return_value=(root, root / "_internal")), \
                     mock.patch.object(entry, "module_origins", return_value={"predict": "inside"}), \
                     mock.patch.object(entry.platform, "system", return_value=system), \
                     mock.patch.object(entry, function, return_value=inventory), \
                     mock.patch.object(entry, "validate_native_paths", return_value={"bundled": []}) as validate:
                    report = entry.runtime_provenance()
                    self.assertTrue(report["frozen"])
                    self.assertEqual(report["bundle_root"], str(root))
                    if system == "Darwin":
                        validate.assert_called_once_with(paths, root, system, darwin_images=inventory)
                        self.assertEqual(report["native_origin_contract"], "darwin_dyld_shared_cache_v2")
                        self.assertEqual(report["loaded_native_images"], [image._asdict() for image in darwin_inventory])
                    else:
                        validate.assert_called_once_with(paths, root, system)
                        self.assertNotIn("native_origin_contract", report)
                        self.assertEqual(report["inventory_mechanism"], "proc_self_maps_executable_files")
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
