"""Public-coordinate synthetic-container proof; never model execution evidence."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import hashlib
from io import StringIO
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch
import zipfile

import pytest

from kuma_core.kuro.domain_jobs import prepare_source
from kuma_core.kuro.residue_mapping import ResidueId
from scripts.merizo_runtime_archive import public_fixture as fixture

PUBLIC = Path(__file__).parent / 'data/domain_annotation/1ubq.pdb'


def original_atoms() -> list[str]:
    return [line for line in PUBLIC.read_text(encoding='ascii').splitlines()
            if line.startswith('ATOM  ') and line[21] == 'A']


def cif_rows(raw: bytes) -> dict[str, list[str]]:
    # Independent parser rather than trusting the generator's private columns.
    from Bio.PDB.MMCIF2Dict import MMCIF2Dict
    return dict(MMCIF2Dict(StringIO(raw.decode('ascii'))))


def test_repeat_directories_produce_identical_bytes_and_prepared_binding(tmp_path: Path) -> None:
    results = []
    for name in ('first', 'second', 'third'):
        directory = tmp_path / name
        directory.mkdir()
        path = directory / f'{name}.zip'
        source, prepared, recipe = fixture.create_af3_fixture(PUBLIC, path)
        repeated, binding = prepare_source(source)
        assert repeated == prepared
        assert binding == {key: recipe[key] for key in (
            'bundle_sha256', 'source_sha256', 'reference_sha256', 'model_id', 'chain_id')}
        results.append((path.read_bytes(), prepared, recipe))
    assert results[0] == results[1] == results[2]
    raw, prepared, recipe = results[0]
    assert hashlib.sha256(raw).hexdigest() == recipe['bundle_sha256']
    assert recipe['bundle_sha256'] == '25b66532b5b97ffc9726a5734ed2f0c6d1edb3522920ff147a33cdcafe593cba'
    assert recipe['binding_sha256'] == prepared.binding_sha256
    assert recipe['generator_source_sha256'] == hashlib.sha256(Path(fixture.__file__).read_bytes()).hexdigest()
    assert recipe['public_source_sha256'] == hashlib.sha256(PUBLIC.read_bytes()).hexdigest() == fixture.PUBLIC_SHA
    assert recipe['schema'] == 'kuma-merizo-public-af3-fixture-v1'
    assert recipe['atom_count'] == 602 and recipe['residue_count'] == 76
    assert recipe['synthetic_confidence_disclaimer'] == fixture.SYNTHETIC_CONFIDENCE_DISCLAIMER
    assert 'not AF3 pLDDT' in recipe['synthetic_confidence_disclaimer']


def test_zip_metadata_ascii_cif_and_canonical_json_are_fixed(tmp_path: Path) -> None:
    destination = tmp_path / 'synthetic.zip'
    _, prepared, recipe = fixture.create_af3_fixture(PUBLIC, destination)
    with zipfile.ZipFile(destination) as archive:
        assert archive.namelist() == ['fold_synthetic_model_0.cif', 'fold_synthetic_full_data_0.json']
        assert archive.comment == b''
        for member in archive.infolist():
            assert member.compress_type == zipfile.ZIP_STORED
            assert member.date_time == (1980, 1, 1, 0, 0, 0)
            assert member.create_system == 3
            assert member.create_version == member.extract_version == 20
            assert member.external_attr == (stat.S_IFREG | 0o644) << 16
            assert member.internal_attr == member.flag_bits == 0
            assert member.comment == member.extra == b''
            assert member.compress_size == member.file_size
        cif = archive.read(fixture.MODEL_MEMBER)
        metadata = archive.read(fixture.CONFIDENCE_MEMBER)
    assert cif.isascii() and metadata.isascii()
    assert b'\r' not in cif and b'\r' not in metadata
    assert cif.endswith(b'\n') and metadata.endswith(b'\n')
    value = json.loads(metadata)
    assert metadata == (json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True,
                                   separators=(',', ':')) + '\n').encode('ascii')
    assert value['synthetic_confidence_disclaimer'] == fixture.SYNTHETIC_CONFIDENCE_DISCLAIMER
    assert recipe['source_sha256'] == hashlib.sha256(cif).hexdigest() == prepared.source_sha256
    assert recipe['confidence_member_sha256'] == hashlib.sha256(metadata).hexdigest()


def test_every_atom_value_order_and_identity_is_preserved(tmp_path: Path) -> None:
    destination = tmp_path / 'synthetic.zip'
    source, prepared, recipe = fixture.create_af3_fixture(PUBLIC, destination)
    public = fixture.public_prepared(PUBLIC)
    with zipfile.ZipFile(destination) as archive:
        rows = cif_rows(archive.read(fixture.MODEL_MEMBER))
        metadata = json.loads(archive.read(fixture.CONFIDENCE_MEMBER))
    original = original_atoms()
    normalized = prepared.normalized_pdb.splitlines()
    assert normalized[-2:] == ['TER', 'END']
    assert normalized[:-2] == original
    assert prepared.normalized_pdb == public.normalized_pdb
    assert prepared.binding_sha256 != public.binding_sha256
    assert prepared.sequence == public.sequence == fixture.SEQUENCE
    assert prepared.model_id == '7' and prepared.chain_id == 'B'
    assert source.prediction_chain_id == 'label-AA'
    assert len(rows['_atom_site.id']) == len(original) == 602
    ca_positions = []
    for i, line in enumerate(original):
        assert rows['_atom_site.group_PDB'][i] == 'ATOM'
        assert int(rows['_atom_site.id'][i]) == int(line[6:11])
        assert rows['_atom_site.label_atom_id'][i] == rows['_atom_site.auth_atom_id'][i] == line[12:16].strip()
        assert rows['_atom_site.label_comp_id'][i] == rows['_atom_site.auth_comp_id'][i] == line[17:20]
        assert rows['_atom_site.type_symbol'][i] == line[76:78].strip()
        assert rows['_atom_site.label_asym_id'][i] == 'label-AA'
        assert rows['_atom_site.auth_asym_id'][i] == 'B'
        assert rows['_atom_site.pdbx_PDB_model_num'][i] == '7'
        assert rows['_atom_site.label_alt_id'][i] == '.'
        assert rows['_atom_site.pdbx_formal_charge'][i] == '?'
        position = int(line[22:26])
        assert int(rows['_atom_site.label_seq_id'][i]) == position
        assert int(rows['_atom_site.auth_seq_id'][i]) == (110 if position == 11 else 100 + position)
        assert rows['_atom_site.pdbx_PDB_ins_code'][i] == ('A' if position == 11 else '?')
        for field, start, end in (('Cartn_x', 30, 38), ('Cartn_y', 38, 46), ('Cartn_z', 46, 54),
                                  ('occupancy', 54, 60), ('B_iso_or_equiv', 60, 66)):
            assert Decimal(rows['_atom_site.' + field][i]) == Decimal(line[start:end])
        assert Decimal(str(metadata['atom_plddts'][i])) == Decimal(line[60:66])
        if line[12:16].strip() == 'CA':
            ca_positions.append((position, line[30:54]))
    assert [position for position, _ in ca_positions] == list(range(1, 77))
    assert metadata['atom_chain_ids'] == ['label-AA'] * 602
    assert metadata['token_chain_ids'] == ['label-AA'] * 76
    assert metadata['token_res_ids'] == list(range(1, 77))
    assert rows['_entity_poly_seq.num'] == [str(i) for i in range(1, 77)]
    seqres = [monomer for line in PUBLIC.read_text(encoding='ascii').splitlines()
              if line.startswith('SEQRES') and line[11] == 'A' for monomer in line[19:70].split()]
    assert rows['_entity_poly_seq.mon_id'] == seqres
    assert rows['_entity_poly_seq.entity_id'] == ['1'] * 76
    assert prepared.residues == tuple(ResidueId('7', 'B', 110, 'A') if i == 11
                                      else ResidueId('7', 'B', 100 + i) for i in range(1, 77))
    assert prepared.residues[9:12] == (ResidueId('7', 'B', 110), ResidueId('7', 'B', 110, 'A'),
                                      ResidueId('7', 'B', 112))
    # Specifically guard the non-unit terminal occupancy and variable B factors.
    assert Decimal(normalized[-3][54:60]) == Decimal('0.25')
    assert len({line[60:66] for line in original}) > 100
    assert recipe['public_normalized_sha256'] == prepared.normalized_sha256
    assert recipe['public_binding_sha256'] == public.binding_sha256


@pytest.mark.parametrize('contents', [b'', b'not a PDB\n', PUBLIC.read_bytes() + b'\n',
                                      PUBLIC.read_bytes().replace(b'27.340', b'27.341', 1)])
def test_only_exact_pinned_public_bytes_are_accepted(tmp_path: Path, contents: bytes) -> None:
    changed = tmp_path / 'changed.pdb'
    changed.write_bytes(contents)
    destination = tmp_path / 'output.zip'
    for call in (lambda: fixture.public_prepared(changed), lambda: fixture.create_af3_fixture(changed, destination)):
        with pytest.raises(ValueError, match='pinned public'):
            call()
    assert not destination.exists()


@pytest.mark.parametrize('kind', ['file', 'directory', 'symlink', 'dangling', 'hardlink'])
def test_stale_outputs_are_not_replaced(tmp_path: Path, kind: str) -> None:
    destination, target = tmp_path / 'output.zip', tmp_path / 'target'
    target.write_bytes(b'untouched')
    if kind == 'file':
        destination.write_bytes(b'stale')
    elif kind == 'directory':
        destination.mkdir()
    elif kind == 'hardlink':
        os.link(target, destination)
    else:
        try:
            destination.symlink_to(target if kind == 'symlink' else tmp_path / 'missing')
        except OSError:
            pytest.skip('Symlinks unavailable on this host')
    with pytest.raises((FileExistsError, ValueError)):
        fixture.create_af3_fixture(PUBLIC, destination)
    assert target.read_bytes() == b'untouched'
    if kind == 'file':
        assert destination.read_bytes() == b'stale'
    elif kind in {'symlink', 'dangling'}:
        assert destination.is_symlink()


def test_input_links_and_parent_links_are_refused(tmp_path: Path) -> None:
    copied = tmp_path / 'public.pdb'
    copied.write_bytes(PUBLIC.read_bytes())
    hardlink = tmp_path / 'hardlink.pdb'
    os.link(copied, hardlink)
    with pytest.raises(ValueError, match='regular non-link'):
        fixture.public_prepared(hardlink)
    hardlink.unlink()
    linked = tmp_path / 'linked.pdb'
    linked_parent = tmp_path / 'linked-parent'
    try:
        linked.symlink_to(copied)
        linked_parent.symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        pytest.skip('Symlinks unavailable on this host')
    with pytest.raises(ValueError, match='regular non-link'):
        fixture.public_prepared(linked)
    with pytest.raises(ValueError, match='plain parent'):
        fixture.public_prepared(linked_parent / copied.name)
    with pytest.raises(ValueError, match='plain parent'):
        fixture.create_af3_fixture(PUBLIC, linked_parent / 'output.zip')
    assert not (tmp_path / 'output.zip').exists()


@pytest.mark.parametrize('change', ['coordinate', 'occupancy', 'bfactor', 'model', 'author',
                                    'polymer', 'ca_only', 'missing_oxt', 'atom_order'])
def test_malformed_generated_fixtures_fail_and_owned_output_is_removed(tmp_path: Path, change: str) -> None:
    original = fixture._cif_payload
    def malformed(*args):
        text = original(*args).decode('ascii')
        if change == 'coordinate':
            text = text.replace('27.340', '27.341', 1)
        elif change == 'occupancy':
            text = text.replace('1.00 9.67', '0.50 9.67', 1)
        elif change == 'bfactor':
            text = text.replace('1.00 9.67', '1.00 90.00', 1)
        elif change == 'model':
            text = text.replace(' 7 ', ' 8 ')
        elif change == 'author':
            text = text.replace(' B ', ' C ')
        elif change == 'polymer':
            text = text.replace('1 1 MET\n', '1 1 ALA\n')
        else:
            lines = text.splitlines()
            if change == 'ca_only':
                lines = [line for line in lines if not line.startswith('ATOM ') or line.split()[3] == 'CA']
            elif change == 'missing_oxt':
                lines = [line for line in lines if not line.startswith('ATOM ') or line.split()[3] != 'OXT']
            else:
                atoms = [i for i, line in enumerate(lines) if line.startswith('ATOM ')]
                lines[atoms[0]], lines[atoms[1]] = lines[atoms[1]], lines[atoms[0]]
            text = '\n'.join(lines) + '\n'
        return text.encode('ascii')
    destination = tmp_path / 'output.zip'
    with patch.object(fixture, '_cif_payload', side_effect=malformed), pytest.raises(ValueError):
        fixture.create_af3_fixture(PUBLIC, destination)
    assert not destination.exists()


def test_stale_bundle_hash_and_exact_source_selection_are_enforced(tmp_path: Path) -> None:
    source, _, _ = fixture.create_af3_fixture(PUBLIC, tmp_path / 'source.zip')
    for changed in (replace(source, prediction_bundle_sha256='0' * 64),
                    replace(source, prediction_model_id='fold_synthetic_model_1.cif'),
                    replace(source, prediction_chain_id='B'), replace(source, ref_seq=fixture.SEQUENCE[:-1])):
        with pytest.raises(ValueError):
            prepare_source(changed)


def test_failed_preparation_preserves_a_replacement_file(tmp_path: Path) -> None:
    destination = tmp_path / 'source.zip'
    def replaced(source):
        replacement = tmp_path / 'replacement.zip'
        replacement.write_bytes(b'not owned')
        os.replace(replacement, source.prediction_bundle_path)
        raise ValueError('injected parser failure')
    with patch('kuma_core.kuro.domain_jobs.prepare_source', side_effect=replaced):
        with pytest.raises(ValueError, match='injected parser failure'):
            fixture.create_af3_fixture(PUBLIC, destination)
    assert destination.read_bytes() == b'not owned'


def test_same_bytes_replacement_is_not_mistaken_for_owned_output(tmp_path: Path) -> None:
    destination = tmp_path / 'source.zip'
    real_prepare = prepare_source
    def replaced(source):
        result = real_prepare(source)
        replacement = tmp_path / 'replacement.zip'
        replacement.write_bytes(destination.read_bytes())
        os.replace(replacement, destination)
        return result
    with patch('kuma_core.kuro.domain_jobs.prepare_source', side_effect=replaced):
        with pytest.raises(ValueError, match='output identity'):
            fixture.create_af3_fixture(PUBLIC, destination)
    assert destination.is_file()  # Replacement is not ours to delete.


def test_deleted_output_does_not_mask_the_original_parser_error(tmp_path: Path) -> None:
    destination = tmp_path / 'source.zip'
    def removed(source):
        Path(source.prediction_bundle_path).unlink()
        raise ValueError('original parser failure')
    with patch('kuma_core.kuro.domain_jobs.prepare_source', side_effect=removed):
        with pytest.raises(ValueError, match='original parser failure'):
            fixture.create_af3_fixture(PUBLIC, destination)
    assert not destination.exists()


def test_windows_reparse_points_and_parent_traversal_are_rejected(tmp_path: Path) -> None:
    assert fixture._is_link(cast(os.stat_result, SimpleNamespace(st_mode=stat.S_IFREG, st_file_attributes=0x400)))
    assert fixture._is_link(cast(os.stat_result, SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)))
    assert not fixture._is_link(cast(os.stat_result, SimpleNamespace(st_mode=stat.S_IFREG, st_file_attributes=0)))
    with pytest.raises(ValueError, match='parent traversal'):
        fixture.create_af3_fixture(PUBLIC, tmp_path / '..' / 'output.zip')


def test_import_is_host_only_lazy_and_never_loads_model_packages() -> None:
    root = Path(__file__).parent.parent
    code = ('import sys; import scripts.merizo_runtime_archive.public_fixture; '
            'assert not any(name in sys.modules for name in '
            '("Bio", "torch", "numpy", "kuma_core.kuro.domain_jobs"))')
    completed = subprocess.run([sys.executable, '-c', code], cwd=root, capture_output=True, text=True,
                               check=False, timeout=30)
    assert completed.returncode == 0, completed.stderr
