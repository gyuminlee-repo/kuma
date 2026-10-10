"""Pinned public geometry in a deterministic, explicitly synthetic AF3 container.

Host-side proof helper only: no inference, model loading, downloads or biological
validation. Original crystallographic B factors remain unchanged. Duplicating
them into ``atom_plddts`` meets the parser's paired-field contract and does not
turn these public experimental coordinates into an AF3 prediction.
"""
from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal
import hashlib
import io
import json
import os
from pathlib import Path
import stat
from typing import TYPE_CHECKING
import zipfile

if TYPE_CHECKING:
    from kuma_core.kuro.domain_annotation import DomainInput
    from kuma_core.kuro.domain_jobs import DomainSource

PUBLIC_SHA = 'd4a6812d8951cf6594e6a0763f089e35f5a80b62acb3c117b2c5565228a7b161'
SEQUENCE = 'MQIFVKTLTGKTITLEVEPSDTIENVKAKIQDKEGIPPDQQRLIFAGKQLEDGRTLSDYNIQKESTLHLVLRLRGG'
MODEL_MEMBER = 'fold_synthetic_model_0.cif'
CONFIDENCE_MEMBER = 'fold_synthetic_full_data_0.json'
LABEL_CHAIN = 'label-AA'
AUTHOR_CHAIN = 'B'
COORDINATE_MODEL = '7'
RECIPE_SCHEMA = 'kuma-merizo-public-af3-fixture-v1'
SYNTHETIC_CONFIDENCE_DISCLAIMER = (
    'Synthetic parser metadata only: atom_plddts duplicates unchanged original '
    '1UBQ crystallographic B factors. These values are not AF3 pLDDT, producer '
    'confidence validation, an AF3 prediction, or biological accuracy evidence.'
)
_LIMIT = 1024 * 1024
_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
_ZIP_MODE = stat.S_IFREG | 0o644
_AA: dict[str, str] = dict(zip(
    'ALA ARG ASN ASP CYS GLN GLU GLY HIS ILE LEU LYS MET PHE PRO SER THR TRP TYR VAL'.split(),
    'ARNDCQEGHILKMFPSTWYV', strict=True))
_ATOM_COLUMNS = (
    'group_PDB', 'id', 'type_symbol', 'label_atom_id', 'label_alt_id', 'label_comp_id',
    'label_asym_id', 'label_seq_id', 'auth_asym_id', 'auth_seq_id', 'pdbx_PDB_ins_code',
    'Cartn_x', 'Cartn_y', 'Cartn_z', 'occupancy', 'B_iso_or_equiv', 'pdbx_PDB_model_num',
    'auth_atom_id', 'auth_comp_id', 'label_entity_id', 'pdbx_formal_charge',
)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'),
                      allow_nan=False).encode('ascii') + b'\n'


def _is_link(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 0x400)


def _plain_path(path: Path) -> tuple[Path, tuple[tuple[int, int], ...]]:
    """No resolving through links, including parent-directory reparse points."""
    path = Path(path)
    if '..' in path.parts:
        raise ValueError('Fixture paths must not contain parent traversal')
    path = Path(os.path.abspath(path))
    identities = []
    for parent in reversed(path.parents):
        info = parent.lstat()
        if _is_link(info) or not stat.S_ISDIR(info.st_mode):
            raise ValueError('Fixture paths require plain parent directories')
        identities.append((info.st_dev, info.st_ino))
    return path, tuple(identities)


def _file_identity(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _read_regular(path: Path) -> bytes:
    path, parents = _plain_path(path)
    before = path.lstat()
    if (_is_link(before) or not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
            or before.st_size > _LIMIT):
        raise ValueError('Fixture requires a bounded regular non-link file')
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
    flags |= getattr(os, 'O_BINARY', 0)
    with os.fdopen(os.open(path, flags), 'rb') as stream:
        opened = os.fstat(stream.fileno())
        if _file_identity(opened) != _file_identity(before):
            raise ValueError('Fixture file changed while opening')
        raw = stream.read(_LIMIT + 1)
        after = os.fstat(stream.fileno())
    named = path.lstat()
    if (_file_identity(after) != _file_identity(before)
            or _file_identity(named) != _file_identity(before) or _is_link(named)
            or named.st_nlink != 1 or len(raw) != before.st_size
            or _plain_path(path)[1] != parents):
        raise ValueError('Fixture file or parent identity changed while reading')
    return raw


def _public_source(fixture: Path) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    raw = _read_regular(fixture)
    if _sha(raw) != PUBLIC_SHA:
        raise ValueError('Internal fixture requires the pinned public 1UBQ bytes')
    text = raw.decode('ascii')
    # Full polymer evidence is independently taken from SEQRES, never inferred
    # from observed atoms or the viewer trace.
    seqres = [line for line in text.splitlines() if line.startswith('SEQRES') and line[11] == 'A']
    monomers = tuple(name for line in seqres for name in line[19:70].split())
    if (not seqres or any(int(line[13:17]) != len(SEQUENCE) for line in seqres)
            or ''.join(_AA.get(name, '?') for name in monomers) != SEQUENCE):
        raise ValueError('Public fixture complete SEQRES does not match the pinned sequence')
    atoms = tuple(line for line in text.splitlines() if line.startswith('ATOM  ') and line[21] == 'A')
    if not atoms:
        raise ValueError('Public fixture has no selected all-atom chain')
    return text, atoms, monomers


def _prepare_public(text: str) -> DomainInput:
    from kuma_core.kuro.domain_annotation import prepare_domain_input
    from kuma_core.kuro.residue_mapping import PolymerRecord, ResidueId

    polymer = PolymerRecord(SEQUENCE, 'RCSB 1UBQ SEQRES', 'public-1ubq', '1', 'A',
                            tuple(ResidueId('1', 'A', i) for i in range(1, len(SEQUENCE) + 1)))
    return prepare_domain_input(text, polymer, SEQUENCE, source_sha256=PUBLIC_SHA)


def public_prepared(fixture: Path) -> DomainInput:
    """Prepare only the exact pinned public source, without executing a model."""
    text, _, _ = _public_source(fixture)
    return _prepare_public(text)


def _author_identity(position: int) -> tuple[int, str]:
    return (110, 'A') if position == 11 else (100 + position, '')


def _cif_payload(atoms: tuple[str, ...], monomers: tuple[str, ...]) -> bytes:
    lines = ['data_synthetic_public_1ubq', '#', 'loop_', '_struct_asym.id',
             '_struct_asym.entity_id', f'{LABEL_CHAIN} 1', '#', 'loop_',
             '_entity_poly_seq.entity_id', '_entity_poly_seq.num', '_entity_poly_seq.mon_id']
    lines.extend(f'1 {position} {name}' for position, name in enumerate(monomers, 1))
    lines.extend(['#', 'loop_', *(f'_atom_site.{name}' for name in _ATOM_COLUMNS)])
    for line in atoms:
        position = int(line[22:26])
        number, insertion = _author_identity(position)
        atom, name = line[12:16].strip(), line[17:20]
        charge = line[78:80].strip()
        if charge:
            raise ValueError('Pinned public fixture unexpectedly carries formal charges')
        fields = ('ATOM', line[6:11].strip(), line[76:78].strip(), atom, '.', name,
                  LABEL_CHAIN, str(position), AUTHOR_CHAIN, str(number), insertion or '?',
                  line[30:38].strip(), line[38:46].strip(), line[46:54].strip(),
                  line[54:60].strip(), line[60:66].strip(), COORDINATE_MODEL,
                  atom, name, '1', '?')
        lines.append(' '.join(fields))
    return ('\n'.join([*lines, '#']) + '\n').encode('ascii')


def _bundle_bytes(structure: bytes, metadata: bytes) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_STORED, allowZip64=False) as archive:
        archive.comment = b''
        for name, raw in ((MODEL_MEMBER, structure), (CONFIDENCE_MEMBER, metadata)):
            info = zipfile.ZipInfo(name, date_time=_ZIP_TIME)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.create_version = info.extract_version = 20
            info.external_attr = _ZIP_MODE << 16
            info.internal_attr = 0
            info.flag_bits = 0
            info.extra = info.comment = b''
            archive.writestr(info, raw)
    return output.getvalue()


def _assert_fidelity(atoms: tuple[str, ...], public: DomainInput, prepared: DomainInput,
                     bundle_sha: str, source_sha: str) -> None:
    """Independently inspect fixed columns and identities after the real adapter."""
    from kuma_core.kuro.residue_mapping import ResidueId

    prepared.check_consistency()
    normalized = prepared.normalized_pdb.splitlines()
    if normalized[-2:] != ['TER', 'END'] or len(normalized) != len(atoms) + 2:
        raise ValueError('Synthetic AF3 normalization changed all-atom coverage')
    ca_positions = []
    for original, actual in zip(atoms, normalized[:-2], strict=True):
        # These public fields are already in normalized chain/residue order.
        # Require every byte, not just the atom count or rounded CA coordinates.
        if len(actual) != 80 or actual != original:
            raise ValueError('Synthetic AF3 normalization changed public atom fields or order')
        for start, end in ((30, 38), (38, 46), (46, 54), (54, 60), (60, 66)):
            if Decimal(actual[start:end]) != Decimal(original[start:end]):
                raise ValueError('Synthetic AF3 normalization changed exact atom values')
        if original[12:16].strip() == 'CA':
            ca_positions.append((int(actual[22:26]), actual[17:20]))
    expected_ca = [(position, name) for position, name in enumerate(
        [next(key for key, value in _AA.items() if value == aa) for aa in SEQUENCE], 1)]
    identities = tuple(ResidueId(COORDINATE_MODEL, AUTHOR_CHAIN, *_author_identity(position))
                       for position in range(1, len(SEQUENCE) + 1))
    if (ca_positions != expected_ca or prepared.sequence != SEQUENCE
            or prepared.residues != identities or prepared.model_id != COORDINATE_MODEL
            or prepared.chain_id != AUTHOR_CHAIN or prepared.source_sha256 != source_sha
            or prepared.frame_id != f'prediction:{bundle_sha}:{source_sha}:{MODEL_MEMBER}'
            or f'label_asym_id="{LABEL_CHAIN}"' not in prepared.polymer_source
            or prepared.normalized_pdb != public.normalized_pdb
            or prepared.binding_sha256 == public.binding_sha256):
        raise ValueError('Synthetic AF3 public geometry or source identity binding differs')


def create_af3_fixture(fixture: Path, destination: Path) -> tuple[DomainSource, DomainInput, dict]:
    """Create one fresh owned ZIP and re-open it through the real service adapter.

    A different filename or directory never changes bundle bytes or binding.
    Refuse stale destinations and links rather than overwriting/reusing them.
    Remove only our own file if writing or validation fails.
    """
    from kuma_core.kuro.domain_jobs import DomainSource, prepare_source

    text, atoms, monomers = _public_source(fixture)
    public = _prepare_public(text)
    structure = _cif_payload(atoms, monomers)
    metadata = _canonical({
        'atom_chain_ids': [LABEL_CHAIN] * len(atoms),
        'atom_plddts': [float(line[60:66]) for line in atoms],
        'token_chain_ids': [LABEL_CHAIN] * len(SEQUENCE),
        'token_res_ids': list(range(1, len(SEQUENCE) + 1)),
        'synthetic_confidence_disclaimer': SYNTHETIC_CONFIDENCE_DISCLAIMER,
    })
    raw = _bundle_bytes(structure, metadata)
    bundle_sha, source_sha = _sha(raw), _sha(structure)
    generator_sha = _sha(_read_regular(Path(__file__)))
    destination, parents = _plain_path(destination)
    # O_EXCL rejects regular files, dangling links, directories and hard links.
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)
    flags |= getattr(os, 'O_BINARY', 0)
    descriptor = os.open(destination, flags, 0o600)
    owned = os.fstat(descriptor)
    def check_owned() -> None:
        named = destination.lstat()
        if (_plain_path(destination)[1] != parents or _is_link(named)
                or (named.st_dev, named.st_ino) != (owned.st_dev, owned.st_ino)
                or _read_regular(destination) != raw):
            raise ValueError('Synthetic fixture output identity or bytes changed')
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            if not stat.S_ISREG(owned.st_mode) or owned.st_nlink != 1:
                raise ValueError('Synthetic fixture output is not a fresh owned regular file')
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        check_owned()
        source = DomainSource(str(destination), bundle_sha, MODEL_MEMBER, LABEL_CHAIN, SEQUENCE)
        prepared, binding = prepare_source(source)
        _assert_fidelity(atoms, public, prepared, bundle_sha, source_sha)
        expected_binding = {
            'bundle_sha256': bundle_sha, 'source_sha256': source_sha,
            'reference_sha256': _sha(SEQUENCE.encode('ascii')),
            'model_id': MODEL_MEMBER, 'chain_id': LABEL_CHAIN,
        }
        if binding != expected_binding:
            raise ValueError('Synthetic fixture service binding or source changed')
        check_owned()
        recipe = {
            'schema': RECIPE_SCHEMA,
            'public_source_sha256': PUBLIC_SHA,
            'generator_source_sha256': generator_sha,
            **expected_binding,
            'confidence_member_sha256': _sha(metadata),
            'normalized_sha256': prepared.normalized_sha256,
            'binding_sha256': prepared.binding_sha256,
            'public_binding_sha256': public.binding_sha256,
            'public_normalized_sha256': public.normalized_sha256,
            'sequence': SEQUENCE,
            'atom_count': len(atoms),
            'residue_count': len(SEQUENCE),
            'coordinate_model_id': COORDINATE_MODEL,
            'author_chain_id': AUTHOR_CHAIN,
            'source_residues': [asdict(residue) for residue in prepared.residues],
            'member_order': [MODEL_MEMBER, CONFIDENCE_MEMBER],
            'zip': {'compression': 'ZIP_STORED', 'timestamp': list(_ZIP_TIME),
                    'create_system': 3, 'create_version': 20, 'extract_version': 20,
                    'mode': _ZIP_MODE, 'comment': '', 'member_comments': '', 'extra': ''},
            'serialization': 'ASCII LF CIF; ASCII sorted compact JSON with final LF',
            'synthetic_confidence_disclaimer': SYNTHETIC_CONFIDENCE_DISCLAIMER,
            'validation_scope': 'Synthetic container and identity proof using unchanged public coordinates; no inference.',
        }
        return source, prepared, recipe
    except BaseException:
        # Do not unlink an adversarial replacement or traverse replaced parents.
        try:
            if _plain_path(destination)[1] == parents:
                current = destination.lstat()
                if not _is_link(current) and (current.st_dev, current.st_ino) == (owned.st_dev, owned.st_ino):
                    destination.unlink()
        except (OSError, ValueError):
            pass  # A cleanup failure must not replace the original validation error.
        raise
