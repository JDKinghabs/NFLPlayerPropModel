import pandas as pd
import pytest
from props import calibration as CAL
from props import config as C
from props import picks as P

CALIB = CAL.load()
KICK = pd.Timestamp("2026-10-11 13:00", tz="America/New_York")
KICK_UTC = "2026-10-11T17:00:00Z"


def test_price_math():
    assert P.implied(-110) == pytest.approx(0.5238, abs=1e-4) and P.implied(150) == pytest.approx(0.4)
    assert P.profit(-110) == pytest.approx(100 / 110) and P.profit(250) == 2.5
    assert P.ev(0.6, 100) == pytest.approx(0.2) and P.ev(P.implied(-110), -110) == pytest.approx(0, abs=1e-9)
    assert P.price_for(0.6) == -150 and P.price_for(0.25) == 300 and P.price_for(0.5) == -100


def test_grades_need_the_edge_and_positive_ev():
    a, b = C.PICK_EDGE["RB"]
    assert P.grade("RB", a, 0.1) == "A" and P.grade("RB", b, 0.05) == "B" and P.grade("RB", b - 0.001, 0.05) is None
    assert P.grade("RB", a + 0.1, -0.01) is None
    assert C.PICK_EDGE["QB"][1] > C.PICK_EDGE["WR"][1] > C.PICK_EDGE["TD"][1]       # stricter where calibration is worse


def player(pid, proj, ypg=None, team="AAA", game="g1", q_flag=False, p_out=0.0, kick=KICK, **kw):
    return dict(player_id=pid, name=pid.upper(), team=team, opp_txt="BBB", kick_txt="Sun 1p", kickoff=kick, week=5,
                game_id=game, proj=proj, ypg=ypg or proj, rank=3, opp_rank=15, vs_lg=0.0, beta=0.45, gs_ctx=0.0,
                q_flag=q_flag, q_txt="Starter QB Q (60%)" if q_flag else "", inj="", p_out=p_out, **kw)


def yline(point, over=-110, under=-110, teams=("AAA", "BBB")):
    return dict(kickoff=KICK_UTC, updated="2026-10-11T10:55:00Z", teams=list(teams), point=point, over=over, under=under)


def test_the_better_side_is_taken_and_priced_against_the_book():
    elite = {"WR": pd.DataFrame([player("low", 50, ypg=80)]), "QB": pd.DataFrame(), "RB": pd.DataFrame()}
    priced, unpriced = P.yard_candidates(elite, {("low", "WR"): [yline(70.5)]}, CALIB)
    c = priced[0]
    assert c["side"] == "Under" and c["line"] == 70.5 and c["price"] == -110 and not unpriced
    assert c["p"] == pytest.approx(1 - P._p_over(CALIB, "WR", 50, 70.5)) and c["edge"] == pytest.approx(c["p"] - P.implied(-110))
    assert c["grade"] == "A" and c["ev"] > 0 and c["label"] == "Rec yds" and c["book"] == "DraftKings"
    assert c["reasons"][0] == "proj 50 vs line 70.5" and "hot start, regresses" in c["reasons"][1]


def test_a_flagged_qb_blocks_the_over_and_likely_out_players_are_skipped():
    elite = {"WR": pd.DataFrame([player("hot", 95, q_flag=True), player("gone", 95, p_out=0.6)])}
    lines = {("hot", "WR"): [yline(60.5)], ("gone", "WR"): [yline(60.5)]}
    priced, _ = P.yard_candidates(elite, lines, CALIB)
    assert [c["pid"] for c in priced] == ["hot"] and priced[0]["side"] == "Under" and priced[0]["grade"] is None
    assert any(r.startswith("QB ") for r in priced[0]["reasons"])


def td_row(pid, p, team="AAA", game="g1", **kw):
    return dict(player_id=pid, name=pid.upper(), team=team, opp_txt="BBB", kick_txt="Sun 1p", kickoff=KICK, week=5, game_id=game,
                p_td=p, xtd=0.7, pg_touch=20.0, tt=25.5, inj="", p_out=0.0, role_up=False, **kw)


def test_td_picks_need_a_real_chance_not_just_a_big_longshot_edge():
    td = {"RB": pd.DataFrame([td_row("cook", 0.59), td_row("fb", 0.15)]), "WR": pd.DataFrame(), "TE": pd.DataFrame()}
    lines = {("cook", "TD"): [dict(kickoff=KICK_UTC, teams=["AAA", "BBB"], yes=-110)],
             ("fb", "TD"): [dict(kickoff=KICK_UTC, teams=["AAA", "BBB"], yes=4000)]}
    priced, _ = P.td_candidates(td, lines)
    by = {c["pid"]: c for c in priced}
    assert by["cook"]["grade"] == "A" and by["cook"]["side"] == "Yes" and by["cook"]["fair"] == "-144"
    assert by["fb"]["edge"] > 0.1 and by["fb"]["grade"] is None                       # 15% vs a +4000 price: not trusted


def cand(pid, grade, ev, game="g1"):
    return dict(pid=pid, grade=grade, ev=ev, game=game)


def test_select_orders_caps_and_spreads_the_picks():
    out = P.select([cand("b1", "B", 0.30), cand("a1", "A", 0.10), cand("a2", "A", 0.20), cand("x", None, 0.9),
                    cand("a1", "B", 0.5)])                                              # a1's second market loses to its first
    assert [c["pid"] for c in out] == ["a2", "a1", "b1"] and [c["rank"] for c in out] == [1, 2, 3]
    crowd = P.select([cand(f"p{i}", "A", 1 - i / 10) for i in range(6)])               # all in one game
    assert len(crowd) == C.PICK_PER_GAME
    many = P.select([cand(f"p{i}", "B", 0.1, game=f"g{i}") for i in range(40)])
    assert len(many) == C.PICK_MAX


def test_watchlist_lists_unpriced_markets_with_target_numbers():
    elite = {"WR": pd.DataFrame([player("w1", 80, ypg=110), player("w2", 70, team="CCC", game="g2"),
                                 player("w3", 70, q_flag=True)])}
    td = {"RB": pd.DataFrame([td_row("r1", 0.55), td_row("r9", 0.12)]), "WR": pd.DataFrame(), "TE": pd.DataFrame()}
    # the AAA game has a WR line for someone else (so w1 / w3 are simply not offered) and nothing for TDs; CCC has nothing
    lines = {("other", "WR"): [yline(55.5, teams=("AAA", "BBB"))]}
    picks, watch = P.make(elite, td, lines, CALIB)
    names = [w["pid"] for w in watch]
    assert picks == [] and "w2" in names and "w1" not in names and "w3" not in names and "r1" in names and "r9" not in names
    w = next(x for x in watch if x["pid"] == "w2")
    assert w["over_at"] < w["fair_line"] < w["under_at"]
    assert P._p_over(CALIB, "WR", 70, w["over_at"]) >= C.BREAK_EVEN + C.PICK_EDGE["WR"][1]
    assert 1 - P._p_over(CALIB, "WR", 70, w["under_at"]) >= C.BREAK_EVEN + C.PICK_EDGE["WR"][1]
    r1 = next(x for x in watch if x["pid"] == "r1")
    assert r1["yes_at"] == P.price_for(0.55 - C.PICK_EDGE["TD"][1])


def test_watchlist_never_offers_an_over_on_a_flagged_wr():
    elite = {"WR": pd.DataFrame([player("w3", 70, q_flag=True, team="CCC", game="g2")])}
    _, watch = P.make(elite, {}, {}, CALIB)
    assert watch[0]["over_at"] is None and watch[0]["under_at"] is not None


def test_make_leaves_inputs_alone_and_needs_a_calibration():
    elite = {"WR": pd.DataFrame([player("w1", 80)])}
    cols = list(elite["WR"].columns)
    P.make(elite, {}, {}, CALIB)
    assert list(elite["WR"].columns) == cols
    assert P.make(elite, {}, {}, None) == ([], [])
