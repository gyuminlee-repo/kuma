"""Opt-in internal Windows 10+ OS-library omission, never a license clearance.

The reviewed names are literal. New API contracts require a new review; this is
not PyInstaller's broad family exclusion and never filters DATA or aliases.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
from pathlib import Path, PureWindowsPath
import re
import struct
import sys
import sysconfig
import zipfile

from scripts.merizo_runtime_archive.common import canonical, read_regular

POLICY = 'windows10-os-ucrt-exact44-v1'
LEDGER_SCHEMA = 'kuma-merizo-omitted-windows-os-inputs-v1'
MAX_ROWS = 100000
MAX_DLL_BYTES = 64 * 1024 * 1024
EXCLUDED = frozenset({
    'api-ms-win-core-console-l1-1-0.dll',
    'api-ms-win-core-datetime-l1-1-0.dll',
    'api-ms-win-core-debug-l1-1-0.dll',
    'api-ms-win-core-errorhandling-l1-1-0.dll',
    'api-ms-win-core-fibers-l1-1-0.dll',
    'api-ms-win-core-fibers-l1-1-1.dll',
    'api-ms-win-core-file-l1-1-0.dll',
    'api-ms-win-core-file-l1-2-0.dll',
    'api-ms-win-core-file-l2-1-0.dll',
    'api-ms-win-core-handle-l1-1-0.dll',
    'api-ms-win-core-heap-l1-1-0.dll',
    'api-ms-win-core-interlocked-l1-1-0.dll',
    'api-ms-win-core-kernel32-legacy-l1-1-1.dll',
    'api-ms-win-core-libraryloader-l1-1-0.dll',
    'api-ms-win-core-localization-l1-2-0.dll',
    'api-ms-win-core-memory-l1-1-0.dll',
    'api-ms-win-core-namedpipe-l1-1-0.dll',
    'api-ms-win-core-processenvironment-l1-1-0.dll',
    'api-ms-win-core-processthreads-l1-1-0.dll',
    'api-ms-win-core-processthreads-l1-1-1.dll',
    'api-ms-win-core-profile-l1-1-0.dll',
    'api-ms-win-core-rtlsupport-l1-1-0.dll',
    'api-ms-win-core-string-l1-1-0.dll',
    'api-ms-win-core-synch-l1-1-0.dll',
    'api-ms-win-core-synch-l1-2-0.dll',
    'api-ms-win-core-sysinfo-l1-1-0.dll',
    'api-ms-win-core-sysinfo-l1-2-0.dll',
    'api-ms-win-core-timezone-l1-1-0.dll',
    'api-ms-win-core-util-l1-1-0.dll',
    'api-ms-win-crt-conio-l1-1-0.dll',
    'api-ms-win-crt-convert-l1-1-0.dll',
    'api-ms-win-crt-environment-l1-1-0.dll',
    'api-ms-win-crt-filesystem-l1-1-0.dll',
    'api-ms-win-crt-heap-l1-1-0.dll',
    'api-ms-win-crt-locale-l1-1-0.dll',
    'api-ms-win-crt-math-l1-1-0.dll',
    'api-ms-win-crt-private-l1-1-0.dll',
    'api-ms-win-crt-process-l1-1-0.dll',
    'api-ms-win-crt-runtime-l1-1-0.dll',
    'api-ms-win-crt-stdio-l1-1-0.dll',
    'api-ms-win-crt-string-l1-1-0.dll',
    'api-ms-win-crt-time-l1-1-0.dll',
    'api-ms-win-crt-utility-l1-1-0.dll',
    'ucrtbase.dll',
})
REQUIRED_RETAINED = frozenset({'msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll'})


def basename(value):
    if not isinstance(value, str) or not value or len(value) > 4096 or any(ord(c) < 32 for c in value):
        raise ValueError('Invalid Windows library path')
    return value.replace('\\', '/').rsplit('/', 1)[-1].casefold()


def relative(value):
    basename(value)
    normalized = value.replace('\\', '/')
    if ':' in normalized or any(part in {'', '.', '..'} or part.endswith(('.', ' '))
                                for part in normalized.split('/')):
        raise ValueError('Invalid relative Windows library destination')
    return normalized


def validate_host(value):
    if (not isinstance(value, dict) or set(value) != {'system', 'kernel_version', 'architecture', 'pointer_bits'}
            or value['system'] != 'Windows' or value['architecture'] != 'win-amd64'
            or type(value['pointer_bits']) is not int or value['pointer_bits'] != 64):
        raise ValueError('OS-DLL policy requires Windows x64')
    version = value['kernel_version']
    if (not isinstance(version, list) or len(version) != 3
            or any(type(item) is not int or not 0 <= item <= 2**31 - 1 for item in version)
            or version[0] < 10 or version[2] == 0):
        raise ValueError('OS-DLL policy requires Windows kernel 10 or later')
    return value


def host_identity(*, freezer=False):
    if sys.platform != 'win32':
        raise ValueError('OS-DLL policy is Windows-only')
    if freezer and importlib.metadata.version('pyinstaller') != '6.16.0':
        raise ValueError('OS-DLL policy requires PyInstaller 6.16.0')
    value = {'system': 'Windows', 'kernel_version': list(sys.getwindowsversion().platform_version),
             'architecture': sysconfig.get_platform(), 'pointer_bits': struct.calcsize('P') * 8}
    return validate_host(value)


def retained_name(value):
    name = basename(value)
    return name.endswith('.dll') and name.startswith(('msvcp', 'vcruntime'))


def partition(rows):
    """Validate shapes before any read; only exact top-level BINARYs qualify."""
    if not isinstance(rows, (list, tuple)) or len(rows) > MAX_ROWS:
        raise ValueError('Windows Analysis inventory exceeds bound')
    survivors, omitted, retained, names = [], [], [], set()
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) != 3:
            raise ValueError('Invalid Analysis row')
        destination, source, kind = row
        normalized = relative(destination)
        key = normalized.casefold()
        if key in names:
            raise ValueError('Case-fold Analysis destination collision')
        names.add(key)
        if source and not (Path(source).is_absolute() or PureWindowsPath(source).is_absolute()):
            raise ValueError('Analysis native source must be absolute')
        selected = basename(destination) in EXCLUDED or (source and basename(source) in EXCLUDED)
        if selected:
            if ('/' in normalized or destination != normalized or kind != 'BINARY'
                    or basename(source) != key or key not in EXCLUDED):
                raise ValueError('Excluded OS DLL is not an exact top-level BINARY input')
            omitted.append(row)
        else:
            survivors.append(row)
            if retained_name(destination):
                if kind != 'BINARY' or basename(source) != basename(destination):
                    raise ValueError('Retained MSVC input identity differs')
                retained.append(row)
    if {basename(row[0]) for row in omitted} != EXCLUDED:
        raise ValueError('Reviewed OS-DLL input set changed; expected exactly 44')
    if not REQUIRED_RETAINED <= {row[0].casefold() for row in retained}:
        raise ValueError('Required retained MSVC inputs missing')
    return survivors, omitted, retained


def input_record(row):
    destination, source, kind = row
    raw = read_regular(Path(source), MAX_DLL_BYTES)
    return {'destination': destination, 'source': source, 'typecode': kind,
            'sha256': hashlib.sha256(raw).hexdigest(), 'size': len(raw)}


def filter_analysis(rows):
    host = host_identity(freezer=True)
    survivors, omitted, retained = partition(rows)
    ledger = {'schema': LEDGER_SCHEMA, 'policy': POLICY, 'host': host,
              'scope': 'omitted_inputs_only_not_packaged_provenance_or_rights_clearance',
              'omitted': [input_record(row) for row in omitted],
              'retained_msvc_inputs': [input_record(row) for row in retained]}
    return survivors, ledger


def reject_toc(stages):
    """Reject destination AND source reentry, irrespective of type or nesting."""
    for stage, rows in stages.items():
        if not isinstance(rows, (list, tuple)) or len(rows) > MAX_ROWS:
            raise ValueError('Windows TOC exceeds bound')
        for row in rows:
            if not isinstance(row, (list, tuple)) or len(row) != 3:
                raise ValueError('Invalid Windows TOC row')
            if any(value and basename(value) in EXCLUDED for value in row[:2]):
                raise ValueError('Excluded Windows OS DLL reintroduced at ' + stage)


def reject_packaged(*, toc=None, embedded=None, records=None, archive=None):
    if toc is not None:
        reject_toc({stage: [(row['destination'], row['source'], row['typecode']) for row in rows]
                    for stage, rows in toc.items()})
    if embedded is not None:
        for row in embedded['carchive_members']:
            # CArchive dependency names encode `other-executable:member`.
            name = row['name'].rsplit(':', 1)[-1] if row.get('typecode') == 'd' else row['name']
            if basename(name) in EXCLUDED or (row.get('link_target') and basename(row['link_target']) in EXCLUDED):
                raise ValueError('Excluded Windows OS DLL in embedded CArchive')
    for row in records or ():
        for key in ('path', 'original_path', 'source_path'):
            if key in row and basename(row[key]) in EXCLUDED:
                raise ValueError('Excluded Windows OS DLL in packaged member')
        for alias in row.get('aliases', ()):
            if any(basename(part) in EXCLUDED for part in alias.split(' -> ')):
                raise ValueError('Excluded Windows OS DLL in packaged alias')
    if archive is not None:
        with zipfile.ZipFile(archive) as value:
            if len(value.infolist()) > MAX_ROWS or any(basename(name.rstrip('/')) in EXCLUDED
                                                     for name in value.namelist()):
                raise ValueError('Excluded Windows OS DLL in final ZIP')


def verify_retained(ledger, toc, records=None):
    if (not isinstance(ledger, dict) or set(ledger) != {'schema', 'policy', 'host', 'scope', 'omitted', 'retained_msvc_inputs'}
            or ledger.get('schema') != LEDGER_SCHEMA or ledger.get('policy') != POLICY
            or ledger.get('scope') != 'omitted_inputs_only_not_packaged_provenance_or_rights_clearance'
            or not isinstance(ledger.get('omitted'), list) or len(ledger['omitted']) != 44
            or not isinstance(ledger.get('retained_msvc_inputs'), list) or not 3 <= len(ledger['retained_msvc_inputs']) <= 32):
        raise ValueError('Invalid omitted OS input ledger')
    validate_host(ledger['host'])
    # The ledger lives separately: normal TOCs describe packaged inputs only.
    omitted = ledger['omitted']
    retained = ledger['retained_msvc_inputs']
    for row in omitted + retained:
        if (not isinstance(row, dict) or set(row) != {'destination', 'source', 'typecode', 'sha256', 'size'}
                or not isinstance(row['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', row['sha256'])
                or type(row['size']) is not int or not 0 < row['size'] <= MAX_DLL_BYTES):
            raise ValueError('Invalid hashed Windows input ledger row')
    partition([(row['destination'], row['source'], row['typecode']) for row in omitted + retained])
    actual = [row for row in toc['Analysis.binaries'] if retained_name(row['destination'])]
    if canonical(actual) != canonical(retained):
        raise ValueError('Retained MSVC survivor inputs changed')
    if records is not None:
        for source in retained:
            name = '_internal/' + relative(source['destination'])
            matches = [row for row in records if row['path'].casefold() == name.casefold()]
            if (len(matches) != 1 or matches[0]['sha256'] != source['sha256']
                    or matches[0]['size'] != source['size'] or matches[0]['aliases']):
                raise ValueError('Retained MSVC output differs from selected input')
    return {'policy': POLICY, 'omitted_count': len(omitted),
            'retained_msvc_count': len(retained), 'retained_output_bytes_matched': records is not None}


def validate_native(native):
    """Called only after the existing live/root or saved/path origin checks."""
    if native['system_path_basis'] != 'windows_directory_relative':
        raise ValueError('Windows OS origins require the existing relative path basis')
    if 'system32/ucrtbase.dll' not in {value.casefold() for value in native['system']}:
        raise ValueError('Windows OS UCRT was not observed at System32/ucrtbase.dll')
    if any(basename(value) in EXCLUDED for value in native['bundled']):
        raise ValueError('Excluded Windows OS DLL observed in installed bundle')
    if '_internal/msvcp140.dll' not in {value.casefold() for value in native['bundled']}:
        raise ValueError('Retained plain bundled MSVCP140 was not observed')
