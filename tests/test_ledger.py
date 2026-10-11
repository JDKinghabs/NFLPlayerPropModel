import pytest

from props import ledger as L
from props.picks import profit


def pk(rank, name, market="WR", side="Under", line=56.5, price=-110, team="GB", week=5, grade="A"):
    kind = "td" if market == "TD" else "yards"
    return dict(rank=rank, grade=grade, kind=kind, market=market, label="Rec yds" if kind == "yards" else "Anytime TD",
                pid=name.lower(), name=name, team=team, opp_txt="vs CHI", kick_txt="Sun 1p", kickoff="2026-10-11T17:00:00Z",
                week=week, inj="", side=side, line=line if kind == "yards" else None, price=price, p=0.6, implied=0.52,
                edge=0.08, ev=0.15, fair="-150", proj=50.0, book="DraftKings", updated="2026-10-11T12:50:48Z", reasons=["r"])


SNAP = {"season": 2026, "built": "2026-10-11T13:25:30Z", "hash": "abc",
        "picks": [pk(3, "C"), pk(1, "A", market="TD", side="Yes", price=425, team="IND"), pk(2, "B", side="Over", line=40.5)]}


def test_card_takes_the_top_n_in_board_order_and_freezes_where_it_came_from():
    c = L.card(SNAP, 2, source="2026-10-11T13-25-30Z.json")
    assert [e["name"] for e in c] == ["A", "B"]
    assert c[0]["id"] == "2026|5|a|TD" and c[0]["source_built"] == "2026-10-11T13:25:30Z" and c[0]["source_hash"] == "abc"
    assert c[0]["outcome"] is None and c[0]["price"] == 425 and c[1]["line"] == 40.5


def test_log_appends_once_and_never_edits_a_logged_pick(tmp_path):
    path = tmp_path / "2026.json"
    assert len(L.log(path, L.card(SNAP, 2), "2026-10-11T13:40:00Z")) == 2
    changed = [{**e, "price": 999} for e in L.card(SNAP, 3)]
    added = L.log(path, changed, "2026-10-11T14:00:00Z")
    assert [e["name"] for e in added] == ["C"]                                # only the new one
    by = {e["name"]: e for e in L.load(path)}
    assert by["A"]["price"] == 425 and by["A"]["logged_at"] == "2026-10-11T13:40:00Z"


def results(final=("GB", "IND"), y=None, td=None):
    return {"final": [f"2026|5|{t}" for t in final],
            "y": {f"2026|5|{k}|WR": v for k, v in (y or {}).items()}, "td": {f"2026|5|{k}": v for k, v in (td or {}).items()}}


def test_grading_yards_and_tds_with_units():
    entries = L.card({**SNAP, "picks": [pk(1, "U"), pk(2, "O", side="Over", line=40.5), pk(3, "T", market="TD", side="Yes",
                                                                                          price=425, team="IND"),
                                        pk(4, "N", market="TD", side="Yes", price=200, team="IND"), pk(5, "D")]}, 5)
    g, changed = L.grade(entries, results(y={"u": 41, "o": 40}, td={"t": 1, "n": 0}))
    by = {e["name"]: e for e in g}
    assert changed
    assert by["U"]["outcome"] == "W" and by["U"]["units"] == pytest.approx(profit(-110), abs=1e-3) and by["U"]["actual"] == 41
    assert by["O"]["outcome"] == "L" and by["O"]["units"] == -1.0
    assert by["T"]["outcome"] == "W" and by["T"]["units"] == 4.25
    assert by["N"]["outcome"] == "L"
    assert by["D"]["outcome"] == "void" and by["D"]["units"] == 0.0                     # team final, no stat line


def test_pending_until_final_push_on_the_number_and_graded_entries_stay_put():
    e = L.card({**SNAP, "picks": [pk(1, "U", line=50)]}, 1)
    g, changed = L.grade(e, results(final=()))
    assert not changed and g[0]["outcome"] is None
    g, _ = L.grade(e, results(y={"u": 50}))
    assert g[0]["outcome"] == "P" and g[0]["units"] == 0.0
    again, changed = L.grade(g, results(y={"u": 10}))                              # a later stat correction does not regrade
    assert not changed and again[0]["outcome"] == "P"


def test_summary_record_units_and_roi():
    es = [{"outcome": "W", "units": 0.909}, {"outcome": "W", "units": 4.25}, {"outcome": "L", "units": -1.0},
          {"outcome": "void", "units": 0.0}, {"outcome": None, "units": None}]
    s = L.summary(es)
    assert (s["w"], s["l"], s["p"], s["void"], s["pending"], s["n"]) == (2, 1, 0, 1, 1, 5)
    assert s["units"] == pytest.approx(4.159) and s["roi"] == pytest.approx(4.159 / 3)
    assert L.summary([])["roi"] is None
