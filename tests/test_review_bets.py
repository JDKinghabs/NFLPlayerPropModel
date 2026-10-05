import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "research"))
from review_bets import analyze, grade, wilson                    # noqa: E402

RES = {"season": 2026, "final": ["2026|4|AAA"], "y": {"2026|4|p1|QB": 250, "2026|4|p2|QB": 300}}


def bet(pid="p1", side="Over", line=240.5, odds=-110, stake=1, proj=250, pover=0.6, lean="Over", sheet="elite", team="AAA"):
    return dict(id=pid + side, season=2026, week=4, team=team, pid=pid, cat="QB", sheet=sheet, side=side, line=line,
                odds=odds, stake=stake, pOver=pover, lean=lean, model="v2", snap={"proj": proj})


def test_grading():
    assert grade(bet(), RES)["s"] == "win" and grade(bet(side="Under"), RES)["s"] == "loss"
    assert grade(bet(line=250), RES)["s"] == "push"
    assert grade(bet(pid="nobody"), RES)["s"] == "void"
    assert grade(bet(team="BBB"), RES)["s"] == "pending"
    assert grade(bet(odds=+150), RES)["profit"] == pytest.approx(1.5)
    assert grade(bet(odds=-200), RES)["profit"] == pytest.approx(0.5)


def test_wilson_interval_brackets_the_rate():
    lo, hi = wilson(6, 10)
    assert lo < 0.6 < hi and 0 <= lo and hi <= 1


def test_advice_waits_for_enough_bets_then_flags_real_bias():
    few = analyze([bet(), bet(pid="p2")], RES)
    assert few["settled"] == 2 and "need 30+" in few["advice"][0]
    # 40 settled bets, model consistently 20% too high (actual 250 vs projection 312)
    results = {"season": 2026, "final": ["2026|4|AAA"], "y": {f"2026|4|q{i}|QB": 250 + (i % 5) for i in range(40)}}
    many = [bet(pid=f"q{i}", proj=312, line=240.5) for i in range(40)]
    a = analyze(many, results)
    assert a["groups"][("elite", "QB")]["n"] == 40
    assert "Consider a level adjustment" in a["advice"][0]
    # same count but unbiased -> no change warranted
    ok = analyze([bet(pid=f"q{i}", proj=250 + (i % 5)) for i in range(40)], results)
    assert "no change warranted" in ok["advice"][0]


def test_lean_followed_vs_against_and_calibration_buckets():
    bets = [bet(pid="p1", side="Over", lean="Over", pover=0.60), bet(pid="p2", side="Under", lean="Over", pover=0.60, line=280.5)]
    a = analyze(bets, RES)
    assert a["lean"]["followed"]["n"] == 1 and a["lean"]["against"]["n"] == 1
    assert a["calibration"][0]["bucket"] == "55-65%" and a["calibration"][0]["n"] == 2
