import pytest
from props import calibration as CAL

Q = {"p": [0.1, 0.5, 0.9], "r": [0.4, 1.0, 1.6]}


def test_cdf_interpolates_and_clamps():
    assert CAL.cdf(Q["p"], Q["r"], 1.0) == pytest.approx(0.5)
    assert CAL.cdf(Q["p"], Q["r"], 0.7) == pytest.approx(0.3)           # halfway between 0.1 and 0.5
    assert CAL.cdf(Q["p"], Q["r"], 0.2) == pytest.approx(0.05)          # below the lowest quantile: scaled toward 0
    assert CAL.cdf(Q["p"], Q["r"], 3.2) == pytest.approx(1.0)           # far above the top quantile


def test_p_over_is_decreasing_in_line_and_bounded():
    ps = [CAL.p_over(Q["p"], Q["r"], 100, line) for line in (10, 50, 90, 100, 130, 200, 900)]
    assert ps == sorted(ps, reverse=True)
    assert all(CAL.FLOOR <= p <= CAL.CEIL for p in ps)
    assert CAL.p_over(Q["p"], Q["r"], 100, 100) == pytest.approx(0.5)     # line at the median outcome


def test_shipped_calibration_is_sane_and_shows_the_mean_median_gap():
    cal = CAL.load()
    for sheet in ("elite", "backup"):
        for k in ("QB", "RB", "WR"):
            p, r = cal[sheet][k]["p"], cal[sheet][k]["r"]
            assert p == sorted(p) and r == sorted(r) and 0 < p[0] and p[-1] < 1
    # yardage is right-skewed for RB/WR: the median outcome sits below the projection (which is a mean)
    mid = lambda q: q["r"][len(q["r"]) // 2]                              # noqa: E731
    assert mid(cal["elite"]["RB"]) < 1.0 and mid(cal["elite"]["WR"]) < 1.0
