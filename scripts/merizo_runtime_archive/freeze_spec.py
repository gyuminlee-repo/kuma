"""Helpers called from the generated PyInstaller 6.16.0 spec, without TOC eval."""
from __future__ import annotations

from pathlib import Path
from scripts.merizo_runtime_archive.common import digest, write_json

MAX_TOC_ROWS = 100000


def capture(rows):
    if len(rows) > MAX_TOC_ROWS:
        raise ValueError('PyInstaller input inventory exceeds declared bound')
    result = []
    for destination, source, typecode in rows:
        path = Path(source) if source else None
        row = {'destination': destination, 'source': source, 'typecode': typecode}
        if path is not None and path.is_file():
            row.update(sha256=digest(path), size=path.stat().st_size)
        result.append(row)
    return result


def snapshot(path, stages):
    write_json(Path(path), {stage: capture(rows) for stage, rows in stages.items()})


def write_spec(path: Path, *, source: Path, project: Path, generated: Path,
               evidence: Path, package_name: str) -> None:
    entry = project / 'scripts/merizo_runtime_archive/runtime_entry.py'
    data = []
    for file in sorted(source.rglob('*.py')):
        relative = file.relative_to(source)
        data.append((str(file), str(Path('merizo_source') / relative.parent)))
    from kuma_core.kuro.domain_merizo import MERIZO_WEIGHTS_SHA256
    data.extend((str(source / 'weights' / name), 'merizo_weights') for name in MERIZO_WEIGHTS_SHA256)
    data.append((str(generated / 'merizo-source-identity.json'), '.'))
    hidden = ['predict', 'model.network', 'model.utils.features', 'model.utils.utils',
              'torch', 'numpy', 'scipy', 'networkx', 'einops', 'rotary_embedding_torch', 'natsort',
              'backports', 'backports.tarfile', '_merizo_build_identity']
    # Analyze upstream imports for the full dependency closure, then omit its
    # compiled copies: runtime imports the separately hashed official .py bytes.
    text = f'''# Generated internal evidence spec. No runtime/model distribution authority.
from scripts.merizo_runtime_archive.freeze_spec import snapshot
from PyInstaller.utils.hooks import copy_metadata

a = Analysis([{str(entry)!r}], pathex={[str(source), str(project), str(generated)]!r},
             binaries=[], datas={data!r} + copy_metadata('torch'),
             hiddenimports={hidden!r}, hookspath=[], hooksconfig={{}},
             runtime_hooks=[], excludes=[], noarchive=False)
analysis_pure = list(a.pure)
a.pure = [row for row in a.pure if not (row[0] == 'predict' or row[0] == 'model' or row[0].startswith('model.'))]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name={package_name!r},
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=True, disable_windowed_traceback=False, argv_emulation=False,
          target_arch={'arm64' if __import__('sys').platform == 'darwin' else None!r},
          codesign_identity=None, entitlements_file=None)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name={package_name!r})
snapshot({str(evidence)!r}, {{'Analysis.scripts': a.scripts, 'Analysis.pure': analysis_pure,
    'Analysis.binaries': a.binaries, 'Analysis.datas': a.datas,
    'PYZ.input': a.pure, 'PKG.input': exe.pkg.toc, 'EXE.input': exe.toc, 'COLLECT.input': coll.toc}})
'''
    path.write_text(text, encoding='utf-8')
