"""Tests for ExportMacrogenParams and ExportAllParams Pydantic models."""

import pytest
from pydantic import ValidationError

from sidecar_kuro.models import ExportAllParams, ExportMacrogenParams


def test_macrogen_params_defaults():
    p = ExportMacrogenParams(
        output_path="/tmp/x.xls",
        fwd_plate_name="P1_fwd",
        rev_plate_name="P1_rev",
    )
    assert p.amount == "0.05"
    assert p.purification == "MOPC"


def test_macrogen_params_rejects_korean_plate_name():
    with pytest.raises(ValidationError):
        ExportMacrogenParams(
            output_path="/tmp/x.xls",
            fwd_plate_name="한글",
            rev_plate_name="P1",
        )


def test_macrogen_params_accepts_empty_plate_name():
    p = ExportMacrogenParams(output_path="/tmp/x.xls")
    assert p.fwd_plate_name == ""
    assert p.rev_plate_name == ""


def test_export_all_defaults():
    p = ExportAllParams(output_dir="/tmp/out")
    assert p.echo_transfer_vol == 100
    assert 25 <= p.echo_transfer_vol <= 500
    assert p.janus_transfer_vol == 2.0
    assert p.bom is False


def test_export_all_echo_clamp_rejects():
    with pytest.raises(ValidationError):
        ExportAllParams(output_dir="/tmp/out", echo_transfer_vol=1000)


def test_export_all_janus_clamp_rejects():
    with pytest.raises(ValidationError):
        ExportAllParams(output_dir="/tmp/out", janus_transfer_vol=20.0)
