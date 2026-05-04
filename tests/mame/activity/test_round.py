from kuma_core.mame.activity.round import Round, RoundStatus, RoundErrorInfo
from datetime import datetime


def test_round_status_includes_combinatorial():
    assert RoundStatus.COMBINATORIAL == "combinatorial"
    assert RoundStatus.ERROR == "error"


def test_round_minimal():
    r = Round(
        id="round_1", n=1, created_at=datetime.now(),
        status=RoundStatus.DESIGN,
        plate_meta={"plates": []},
        design={}, genotype={},
        activity=None, merged_table=[]
    )
    assert r.id == "round_1"
    assert r.status == RoundStatus.DESIGN


def test_round_error_info():
    info = RoundErrorInfo(stage="merge", message="WT 없음", occurred_at=datetime.now())
    assert info.stage == "merge"
