from unittest.mock import patch

from sidecar_kuro.handlers import misc


def test_unique_tag_reindexes_coordinates():
    coords = [None] + [(float(i), 0., 0.) for i in range(1, 8)]
    with patch.object(misc, '_get_cached_ca_seq', return_value='HHMACDE'):
        projected, mismatch = misc._frame_checked_ca_coords(coords, 'file:model', 'MACDE')
    assert not mismatch
    assert projected == [None] + coords[3:8]


def test_repeated_reference_has_no_unique_frame():
    with patch.object(misc, '_get_cached_ca_seq', return_value='MACDEMACDE'):
        projected, mismatch = misc._frame_checked_ca_coords([None] * 11, 'file:model', 'MACDE')
    assert projected is None and mismatch


def test_missing_sequence_does_not_authorize_frame():
    with patch.object(misc, '_get_cached_ca_seq', return_value=''):
        projected, mismatch = misc._frame_checked_ca_coords([None, (0., 0., 0.)], 'file:model', 'M')
    assert projected is None and mismatch


def test_c_terminal_extension_does_not_extend_reference_coordinates():
    coords = [None] + [(float(i), 0., 0.) for i in range(1, 8)]
    with patch.object(misc, '_get_cached_ca_seq', return_value='MACDEHH'):
        projected, mismatch = misc._frame_checked_ca_coords(coords, 'file:model', 'MACDE')
    assert not mismatch
    assert projected == coords[:6]
