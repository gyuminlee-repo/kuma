"""Fresh origin observations for this installed executable, never old probe proof."""
from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
import platform
import re
import stat
import sys
import tempfile
from typing import cast

from scripts.merizo_runtime_archive.common import canonical, digest, strict_json
from scripts.merizo_windows_smoke import runtime_origins as shared

SCHEMA = 'kuma-merizo-installed-origins-v1'
MAX_ORIGIN_BYTES = 512 * 1024
MAX_ORIGIN_ROWS = 2048
PHASES = ('before_weights', 'after_inference')
_CHECKS = {'empty_search_path', 'private_home_cache_temp', 'no_python_environment',
           'bundle_loader_paths', 'gpu_hidden', 'single_thread_environment'}
_MODULES = ('torch', 'model', 'predict')
_HASH = re.compile('[0-9a-f]{64}\\Z')

ORIGIN_FAILURE_SCHEMA = 'kuma-merizo-origin-failure-v1'
MAX_ORIGIN_FAILURE_FRAMES = 8
MAX_ORIGIN_FAILURE_BYTES = 2048
_ORIGIN_PHASES = frozenset({'bootstrap', *PHASES})
_ORIGIN_STAGES = frozenset({'initialization', 'phase_validation', 'module_collection', 'module_validation',
    'module_normalization', 'native_enumeration', 'native_policy', 'native_normalization', 'environment',
    'serialization', 'final_validation', 'executable_reverification', 'publication', 'unavailable'})
_NATIVE_CLASSES = frozenset({'bundled_python_role', 'bundled_torch_cpu_role', 'bundled_c10_role',
    'bundled_python_flat_path', 'bundled_python_framework_path', 'external_inference_runtime', 'external_other_image'})


def _unavailable_native_classes():
    return {'status': 'unavailable', **{key: None for key in _NATIVE_CLASSES}}


def native_classes(paths, root: Path, internal: Path, system: str) -> dict:
    """Diagnostic observations from the original snapshot, never acceptance evidence."""
    try:
        if not isinstance(paths, (list, tuple)) or not 0 < len(paths) <= MAX_ORIGIN_ROWS:
            return _unavailable_native_classes()
        result = {'status': 'observed', **{key: False for key in _NATIVE_CLASSES}}
        for raw in paths:
            if not isinstance(raw, str) or len(raw) > 4096 or any(c in raw for c in '\0\r\n'):
                return _unavailable_native_classes()
            original, path = Path(raw), Path(raw).resolve()
            if not original.is_absolute():
                return _unavailable_native_classes()
            if path.is_relative_to(root):
                role = ({'python311.dll': 'python', 'torch_cpu.dll': 'torch_cpu', 'c10.dll': 'c10'}.get(path.name.casefold())
                        if system == 'Windows' else shared.runtime_role(path, system))
                if role in {'python', 'torch_cpu', 'c10'}:
                    result['bundled_' + role + '_role'] = True
                if system == 'Darwin':
                    result['bundled_python_flat_path'] |= path == internal / 'Python'
                    result['bundled_python_framework_path'] |= path == internal / 'Python.framework/Versions/3.11/Python'
            elif shared.is_inference_runtime(original) or shared.is_inference_runtime(path):
                result['external_inference_runtime'] = True
            else:
                result['external_other_image'] = True
        return result
    except BaseException:
        return _unavailable_native_classes()  # Never replace an original policy failure.


def validate_origin_failure(value):
    if value is None:
        return
    keys = {'schema', 'status', 'phase', 'substage', 'frames', 'truncated', 'native_classes'}
    if (not isinstance(value, dict) or set(value) != keys or value['schema'] != ORIGIN_FAILURE_SCHEMA
            or value['status'] not in {'collected', 'unavailable'} or value['phase'] not in _ORIGIN_PHASES
            or value['substage'] not in _ORIGIN_STAGES or type(value['truncated']) is not bool
            or not isinstance(value['frames'], list) or len(value['frames']) > MAX_ORIGIN_FAILURE_FRAMES):
        raise ValueError('Invalid origin failure diagnostic')
    for row in value['frames']:
        if (not isinstance(row, dict) or set(row) != {'call', 'line'} or row['call'] not in _ORIGIN_CALL_IDS
                or type(row['line']) is not int or not 1 <= row['line'] <= 1000000):
            raise ValueError('Invalid owned origin failure frame')
    classes = value['native_classes']
    if (not isinstance(classes, dict) or set(classes) != {'status'} | _NATIVE_CLASSES
            or classes['status'] not in {'observed', 'unavailable'}
            or any((type(classes[key]) is not bool if classes['status'] == 'observed' else classes[key] is not None)
                   for key in _NATIVE_CLASSES)):
        raise ValueError('Invalid native path classification diagnostic')
    if value['status'] == 'unavailable' and (value['frames'] or classes['status'] != 'unavailable'):
        raise ValueError('Unavailable origin diagnostic carries observations')
    if len(canonical(value)) > MAX_ORIGIN_FAILURE_BYTES:
        raise ValueError('Origin failure diagnostic exceeds bound')


def origin_failure(exc: BaseException, audit=None):
    """No messages, paths, locals, second enumeration, or filename-based trust."""
    try:
        frames, scanned, truncated = [], 0, False
        trace = exc.__traceback__
        while trace is not None and scanned < 64:
            code = trace.tb_frame.f_code
            trusted = _ORIGIN_CODES.get(id(code))
            if trusted is not None and code is trusted[0] and 1 <= trace.tb_lineno <= 1000000:
                frames.append({'call': trusted[1], 'line': trace.tb_lineno})
                if len(frames) > MAX_ORIGIN_FAILURE_FRAMES:
                    frames.pop(0)
                    truncated = True
            trace, scanned = trace.tb_next, scanned + 1
        if not frames:
            return None
        value = {'schema': ORIGIN_FAILURE_SCHEMA, 'status': 'collected',
            'phase': 'bootstrap' if audit is None else audit.failure_phase,
            'substage': 'initialization' if audit is None else audit.failure_substage,
            'frames': frames, 'truncated': truncated or trace is not None,
            'native_classes': _unavailable_native_classes() if audit is None else dict(audit.native_observations)}
        validate_origin_failure(value)
        return value
    except BaseException:
        return {'schema': ORIGIN_FAILURE_SCHEMA, 'status': 'unavailable', 'phase': 'bootstrap',
            'substage': 'unavailable', 'frames': [], 'truncated': False,
            'native_classes': _unavailable_native_classes()}


def read_stable(path: Path, limit: int) -> bytes:
    before = path.lstat()
    if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
            or getattr(before, 'st_file_attributes', 0) & 0x400 or before.st_size > limit):
        raise ValueError('Expected bounded single-link audit file')
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
    with os.fdopen(os.open(path, flags), 'rb') as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise ValueError('Audit file identity changed')
        raw = stream.read(limit + 1)
        after, named = os.fstat(stream.fileno()), path.lstat()
    if (len(raw) > limit or len(raw) != opened.st_size
            or (after.st_size, after.st_mtime_ns, after.st_ctime_ns)
            != (opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns)
            or (named.st_dev, named.st_ino) != (opened.st_dev, opened.st_ino)):
        raise ValueError('Audit file changed or exceeds bound')
    return raw


def publish_exclusive(path: Path, raw: bytes, limit: int) -> None:
    if len(raw) > limit or path.exists() or path.is_symlink() or not path.parent.is_dir():
        raise ValueError('Audit destination is not fresh or exceeds bound')
    descriptor, temporary = tempfile.mkstemp(prefix='.kuma-audit-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)  # Exclusive and atomic; never replace stale evidence.
    finally:
        Path(temporary).unlink(missing_ok=True)


def _relative(value: str) -> str:
    if (not isinstance(value, str) or not value or len(value) > 4096 or '\\' in value
            or ':' in value or any(ord(c) < 32 for c in value)
            or PurePosixPath(value).is_absolute() or any(x in {'', '.', '..'} for x in value.split('/'))):
        raise ValueError('Invalid bundle-relative origin')
    return value


def _system_path(value, system):
    if not isinstance(value, str) or len(value) > 4096 or any(c in value for c in '\0\r\n'):
        raise ValueError('Invalid system origin')
    if system == 'Windows':
        _relative(value)
        name = PurePosixPath(value).name.casefold()
        if re.fullmatch(r'python\d*(?:_d)?\.dll', name) or name.startswith(('torch', 'c10')):
            raise ValueError('Inference DLL cannot be a Windows OS exception')
        return
    path = PurePosixPath(value)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('Invalid absolute system origin')
    # These two shared predicates inspect names/parts only, never the filesystem.
    if shared.is_inference_runtime(cast(Path, path)):
        raise ValueError('Inference runtime cannot be an OS exception')
    roots = ('/lib', '/lib64', '/usr/lib', '/usr/lib64') if system == 'Linux' else ('/usr/lib', '/System/Library')
    if not any(path != PurePosixPath(root) and path.is_relative_to(root) for root in roots):
        raise ValueError('Saved system origin escaped OS roots')
    if system == 'Linux' and not shared.LINUX_SYSTEM_NAMES.fullmatch(path.name):
        raise ValueError('Saved Linux origin is not an allowed OS library')


def validate_origins(value, *, executable_sha256=None, binding_sha256=None, source_identity_sha256=None):
    keys = {'schema', 'platform', 'executable_sha256', 'input_binding_sha256', 'source_identity_sha256', 'module_families', 'snapshots'}
    if (not isinstance(value, dict) or set(value) != keys or value['schema'] != SCHEMA
            or not isinstance(value['platform'], str) or value['platform'] not in {'Linux', 'Darwin', 'Windows'}
            or value['module_families'] != list(_MODULES)):
        raise ValueError('Invalid installed-origin schema')
    for name, expected in (('executable_sha256', executable_sha256), ('input_binding_sha256', binding_sha256),
                           ('source_identity_sha256', source_identity_sha256)):
        if not isinstance(value[name], str) or not _HASH.fullmatch(value[name]) or (expected is not None and value[name] != expected):
            raise ValueError('Installed-origin identity mismatch')
    snapshots = value['snapshots']
    if not isinstance(snapshots, list) or len(snapshots) != 2:
        raise ValueError('Both origin phases are required')
    for phase, row in zip(PHASES, snapshots, strict=True):
        if (not isinstance(row, dict) or set(row) != {'phase', 'mechanism', 'contract', 'modules', 'native', 'images', 'environment'}
                or row['phase'] != phase or not isinstance(row['modules'], dict)
                or not 1 <= len(row['modules']) <= MAX_ORIGIN_ROWS
                or not isinstance(row['environment'], dict) or set(row['environment']) != _CHECKS
                or any(item is not True for item in row['environment'].values())):
            raise ValueError('Invalid origin snapshot')
        system = value['platform']
        expected = {'Linux': ('proc_self_maps_executable_files', 'linux_loaded_origins_v1'),
                    'Windows': ('enum_process_modules_ex', 'windows_loaded_origins_v1'),
                    'Darwin': ('dyld_stable_indexed_cache_snapshots', 'darwin_dyld_shared_cache_v2')}[system]
        if (row['mechanism'], row['contract']) != expected:
            raise ValueError('Unexpected native origin mechanism')
        for name, member in row['modules'].items():
            if not isinstance(name, str) or len(name) > 240 or not re.fullmatch('[A-Za-z0-9_.]+', name):
                raise ValueError('Invalid module name')
            if not any(name == prefix or name.startswith(prefix + '.') for prefix in _MODULES):
                raise ValueError('Module outside declared observation scope')
            _relative(member)
        if not {'torch', 'predict', 'model.network', 'model.utils.features'} <= row['modules'].keys():
            raise ValueError('Required module origins missing')
        native = row['native']
        if (not isinstance(native, dict) or set(native) != {'bundled', 'system', 'required', 'system_path_basis'}
                or native['system_path_basis'] != ('windows_directory_relative' if system == 'Windows' else 'absolute_posix_os_roots')):
            raise ValueError('Invalid native inventory')
        for kind in ('bundled', 'system'):
            if not isinstance(native[kind], list) or len(native[kind]) > MAX_ORIGIN_ROWS:
                raise ValueError('Native inventory exceeds bound')
            for member in native[kind]:
                _relative(member) if kind == 'bundled' else _system_path(member, system)
        if not isinstance(native['required'], dict) or set(native['required']) != {'python', 'torch_cpu', 'c10'}:
            raise ValueError('Required native roles missing')
        for role, member in native['required'].items():
            _relative(member)
            if member not in native['bundled']:
                raise ValueError('Required runtime is not bundled')
            actual_role = ({'python311.dll': 'python', 'torch_cpu.dll': 'torch_cpu', 'c10.dll': 'c10'}.get(
                PurePosixPath(member).name.casefold()) if system == 'Windows' else shared.runtime_role(cast(Path, PurePosixPath(member)), system))
            if actual_role != role:
                raise ValueError('Bundled required runtime role differs')
        images = row['images']
        if not isinstance(images, list) or len(images) > MAX_ORIGIN_ROWS or (system != 'Darwin' and images):
            raise ValueError('Invalid indexed image inventory')
        if system == 'Darwin' and not images:
            raise ValueError('Missing dyld evidence')
        for index, image in enumerate(images):
            numeric = {'image_index', 'header_address', 'magic', 'cputype', 'cpusubtype', 'filetype', 'flags'}
            if (not isinstance(image, dict) or set(image) != numeric | {'kind', 'path', 'resolved_path', 'shared_cache_member'}
                    or any(type(image[k]) is not int or not
                           (-2**31 <= image[k] < 2**31 if k in {'cputype', 'cpusubtype'} else
                            0 <= image[k] < 2**(64 if k == 'header_address' else 32))
                           for k in numeric)
                    or image['image_index'] != index or type(image['shared_cache_member']) is not bool
                    or image['kind'] not in {'bundled', 'system'}):
                raise ValueError('Invalid indexed dyld row')
            _relative(image['path']) if image['kind'] == 'bundled' else _system_path(image['path'], system)
            _relative(image['resolved_path']) if image['kind'] == 'bundled' else _system_path(image['resolved_path'], system)
            if (image['header_address'] == 0 or image['header_address'] % 8
                    or image['magic'] != shared.MH_MAGIC_64 or image['cputype'] != shared.CPU_TYPE_ARM64
                    or image['cpusubtype'] & (0xFFFFFFFF ^ shared.CPU_SUBTYPE_MASK) not in {0, 1, 2}
                    or image['filetype'] not in {shared.MH_EXECUTE, shared.MH_DYLIB, shared.MH_BUNDLE}):
                raise ValueError('Saved Mach-O header metadata differs')
            if image['kind'] == 'system':
                # Both paths passed lexical POSIX OS-root checks above. Replay
                # cache/header metadata without host-OS paths or pointer access.
                if (image['shared_cache_member'] is not True or image['filetype'] != shared.MH_DYLIB
                        or not image['flags'] & shared.MH_DYLIB_IN_CACHE):
                    raise ValueError('Saved dyld OS exception lacks cache/header evidence')
        if system == 'Darwin':
            for kind in ('bundled', 'system'):
                if {image['resolved_path'] for image in images if image['kind'] == kind} != set(native[kind]):
                    raise ValueError('Indexed dyld rows differ from native inventory')
    if len(canonical(value)) + 1 > MAX_ORIGIN_BYTES:
        raise ValueError('Origin evidence exceeds bound')
    return value


def environment_checks(root: Path, internal: Path, executable: Path) -> dict:
    env, cwd = os.environ, Path.cwd().resolve()
    search = Path(env.get('PATH', ''))
    private = search.parent
    if (not search.is_absolute() or search.name != 'empty-path' or private.parent != cwd
            or not private.name.startswith('domain-private-') or search.resolve() != search
            or not search.is_dir() or any(search.iterdir())):
        raise ValueError('Runtime search path is not private and empty')
    for name, leaf in {'HOME': 'home', 'USERPROFILE': 'home', 'TMPDIR': 'tmp', 'TMP': 'tmp', 'TEMP': 'tmp',
                       'APPDATA': 'config', 'LOCALAPPDATA': 'cache', 'XDG_CACHE_HOME': 'cache',
                       'XDG_CONFIG_HOME': 'config', 'TORCH_HOME': 'torch'}.items():
        path = Path(env.get(name, ''))
        if path != private / leaf or path.resolve() != path or not path.is_dir():
            raise ValueError('Runtime cache/home/temp is not private')
    mpl = Path(env.get('MPLCONFIGDIR', ''))
    if not mpl.is_absolute() or not mpl.resolve().is_relative_to(private) or not mpl.is_dir():
        raise ValueError('Matplotlib cache escaped private storage')
    if any(name.startswith(('PYTHON', 'CONDA', 'VIRTUAL_ENV', 'DYLD_')) for name in env):
        raise ValueError('Inherited interpreter/loader environment is forbidden')
    if env.get('LD_LIBRARY_PATH', str(internal)) != str(internal) or env.get('LD_LIBRARY_PATH_ORIG', ''):
        raise ValueError('Native search path escaped installed bundle')
    for key, expected in (('_PYI_APPLICATION_HOME_DIR', internal), ('_PYI_ARCHIVE_FILE', executable)):
        if key in env and Path(env[key]).resolve() != expected:
            raise ValueError('PyInstaller bootstrap identity differs')
    if any(env.get(name) != '' for name in ('CUDA_VISIBLE_DEVICES', 'HIP_VISIBLE_DEVICES', 'ROCR_VISIBLE_DEVICES')):
        raise ValueError('GPU visibility differs from managed CPU launch')
    if any(env.get(name) != '1' for name in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'NUMEXPR_NUM_THREADS')):
        raise ValueError('Managed thread environment differs')
    return {key: True for key in _CHECKS}


class OriginAudit:
    def __init__(self, internal: Path, source_identity_sha256: str):
        self.failure_phase, self.failure_substage = 'bootstrap', 'initialization'
        self.native_observations = _unavailable_native_classes()
        self.executable = Path(sys.executable).resolve()
        self.root, self.internal = self.executable.parent, internal.resolve()
        if (not getattr(sys, 'frozen', False) or self.executable.name not in {'kuma-merizo', 'kuma-merizo.exe'}
                or self.internal == self.root or not self.internal.is_relative_to(self.root)):
            raise ValueError('Origin audit requires this installed frozen runtime')
        self.report = {'schema': SCHEMA, 'platform': platform.system(), 'executable_sha256': digest(self.executable),
                       'source_identity_sha256': source_identity_sha256, 'input_binding_sha256': None,
                       'module_families': list(_MODULES), 'snapshots': []}

    def capture(self, phase: str, prepared):
        self.failure_phase = phase if phase in PHASES else 'bootstrap'
        self.failure_substage = 'phase_validation'
        self.native_observations = _unavailable_native_classes()
        if len(self.report['snapshots']) >= len(PHASES) or phase != PHASES[len(self.report['snapshots'])]:
            raise ValueError('Origin phases out of order')
        if self.report['input_binding_sha256'] not in {None, prepared.binding_sha256}:
            raise ValueError('Input binding changed between origin phases')
        self.report['input_binding_sha256'] = prepared.binding_sha256
        self.failure_substage = 'module_collection'
        modules = [(name, module) for name, module in list(sys.modules.items()) if module is not None
                   and any(name == prefix or name.startswith(prefix + '.') for prefix in _MODULES)]
        self.failure_substage = 'module_validation'
        origins = shared.module_origins(modules, self.internal, check_namespace_paths=True)
        self.failure_substage = 'module_normalization'
        normalized = {name: Path(path).relative_to(self.internal).as_posix() for name, path in origins.items()}
        system, images = self.report['platform'], None
        self.failure_substage = 'native_enumeration'
        if system == 'Windows':
            paths = shared.windows_loaded_native_paths()
            self.native_observations = native_classes(paths, self.root, self.internal, system)
            self.failure_substage = 'native_policy'
            native = shared.validate_windows_native_paths(paths, self.root, Path(os.environ['SystemRoot']).resolve())
            self.failure_substage = 'native_normalization'
            required = {role: next(x for x in native['bundled'] if Path(x).name.casefold() == name)
                        for role, name in {'python': 'python311.dll', 'torch_cpu': 'torch_cpu.dll', 'c10': 'c10.dll'}.items()}
            system_paths = [Path(path).relative_to(Path(os.environ['SystemRoot']).resolve()).as_posix()
                            for path in native['windows_system']]
            mechanism, contract = 'enum_process_modules_ex', 'windows_loaded_origins_v1'
        else:
            images = shared.darwin_native_images() if system == 'Darwin' else None
            paths = [image.path for image in images] if images is not None else shared.linux_native_paths()
            self.native_observations = native_classes(paths, self.root, self.internal, system)
            self.failure_substage = 'native_policy'
            native = shared.validate_posix_native_paths(paths, self.root, system, darwin_images=images)
            self.failure_substage = 'native_normalization'
            required, system_paths = native['required_bundled'], native['posix_system']
            mechanism = 'dyld_stable_indexed_cache_snapshots' if images is not None else 'proc_self_maps_executable_files'
            contract = shared.DARWIN_ORIGIN_CONTRACT if images is not None else 'linux_loaded_origins_v1'
        relative = lambda value: Path(value).resolve().relative_to(self.root).as_posix()
        image_rows = []
        for image in images or ():
            row = image._asdict()
            bundled = Path(image.path).resolve().is_relative_to(self.root)
            row.update(kind='bundled' if bundled else 'system', path=relative(image.path) if bundled else image.path,
                       resolved_path=relative(image.path) if bundled else str(Path(image.path).resolve()))
            image_rows.append(row)
        native_record = {'bundled': [relative(x) for x in native['bundled']],
                         'system': system_paths, 'required': {role: relative(x) for role, x in required.items()}}
        self.failure_substage = 'environment'
        environment = environment_checks(self.root, self.internal, self.executable)
        self.failure_substage = 'serialization'
        self.report['snapshots'].append({'phase': phase, 'mechanism': mechanism, 'contract': contract,
            'modules': normalized, 'native': native_record,
            'images': image_rows, 'environment': environment})
        self.report['snapshots'][-1]['native']['system_path_basis'] = (
            'windows_directory_relative' if system == 'Windows' else 'absolute_posix_os_roots')
        if len(normalized) > MAX_ORIGIN_ROWS or len(canonical(self.report)) + 1 > MAX_ORIGIN_BYTES:
            raise ValueError('Origin snapshot exceeds declared bound')

    def finish(self, path: Path | None = None):
        self.failure_substage = 'final_validation'
        validate_origins(self.report)
        self.failure_substage = 'executable_reverification'
        if digest(self.executable) != self.report['executable_sha256']:
            raise ValueError('Installed executable changed during inference')
        if path is not None:
            self.failure_substage = 'publication'
            publish_exclusive(path, canonical(self.report) + b'\n', MAX_ORIGIN_BYTES)


def read_origins(path: Path, **expected):
    return validate_origins(strict_json(read_stable(path, MAX_ORIGIN_BYTES)), **expected)


def _owned_origin_codes():
    rows = {}
    for owner, prefix, names in (
        (OriginAudit, 'audit', ('__init__', 'capture', 'finish')),
        (sys.modules[__name__], 'origin', ('environment_checks', 'validate_origins', '_relative', '_system_path',
                                          'read_stable', 'publish_exclusive')),
        (shared, 'shared', ('module_origins', 'within', 'parse_linux_maps', 'linux_native_paths',
                           'darwin_native_images', 'runtime_role', 'is_inference_runtime', 'system_library',
                           'darwin_cached_os_image', 'validate_posix_native_paths',
                           'windows_loaded_native_paths', 'validate_windows_native_paths')),
    ):
        for name in names:
            code = getattr(owner, name).__code__
            rows[id(code)] = (code, prefix + '.' + name)
    return rows


_ORIGIN_CODES = _owned_origin_codes()
_ORIGIN_CALL_IDS = frozenset(value[1] for value in _ORIGIN_CODES.values())
