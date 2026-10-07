import json

import numpy as np
import pandas as pd
import pytest
from props import config as C
from props.history import snapshot, write_snapshot
from props.pipeline import Result

ET = "America/New_York"
BUILT = pd.Timestamp("2026-10-07 18:00", tz=ET)
FUTURE = pd.Timestamp("2026-10-08 20:15", tz=ET)
PAST = pd.Timestamp("2026-10-07 13:00", tz=ET)          # already kicked off when the page was built


def td_rows(kick=FUTURE, p=0.6684879):
    return pd.DataFrame([dict(player_id="p1", name="A Runner", team="AAA", opp="BBB", grp="RB", kickoff=kick, week=5, p_td=p, tt=27.0,
                              xtd=1.0271, pg_touch=22.694, n_prev=4, inj="", p_out=0.0, role_up=False, rank=1),
                         dict(player_id="p2", name="No Line", team="AAA", opp="BBB", grp="RB", kickoff=kick, week=5, p_td=0.3,
                              tt=np.nan, xtd=0.4, pg_touch=8.0, n_prev=np.int64(3), inj="Q (28%)", p_out=0.28, role_up=True, rank=2)])


def elite_rows(kick=FUTURE):
    return pd.DataFrame([dict(player_id="w1", name="A Receiver", team="AAA", opp="BBB", kickoff=kick, week=5, proj=71.3456, opp_rank=3,
                              rank=4, t_exp=8.5, inj="", p_out=0.0, q_flag=True, q_p=0.6, q_if=55.64)])


def backup_rows(kick=FUTURE):
    return pd.DataFrame([dict(player_id="b1", name="Back Up", team="AAA", opp="BBB", kickoff=kick, week=5, proj_exp=50.123,
                              proj_if_out=61.0, p_out=1.0, starters_out="Starter OUT", role="RB2", inj="")])


def result(built=BUILT, td=None, elite=None, backups=None, td_model="2026-10-06"):
    empty = pd.DataFrame()
    return Result(2026, pd.DataFrame(), {}, {"QB": empty, "RB": empty, "WR": elite_rows() if elite is None else elite},
                  {"QB": empty, "RB": backup_rows() if backups is None else backups, "WR": empty},
                  {"generated": built, "weeks": [5], "games": 1, "data_through_week": 4, "injury_reports": {5: (5, False)},
                   "model": "v2", "td_model": td_model},
                  td={"RB": td_rows() if td is None else td, "WR": empty, "TE": empty})


def test_a_snapshot_holds_only_games_that_had_not_kicked_off():
    both = pd.concat([td_rows(FUTURE), td_rows(PAST).assign(player_id=["p3", "p4"])], ignore_index=True)
    s = snapshot(result(td=both, elite=elite_rows(PAST), backups=backup_rows(PAST)))
    assert {r["pid"] for r in s["td"]} == {"p1", "p2"}                          # the two already-started rows are dropped
    assert s["elite"] == [] and s["backup"] == []
    assert all(r["kickoff"] > s["built"] for r in s["td"])
    exactly_now = td_rows(BUILT)
    assert snapshot(result(td=exactly_now))["td"] == []                          # kickoff == build time is not "before kickoff"
    undated = td_rows().assign(kickoff=pd.NaT)
    assert snapshot(result(td=undated))["td"] == []                              # a row we cannot date is a row we cannot trust


def test_snapshot_is_plain_rounded_json():
    s = snapshot(result())
    json.dumps(s)                                                                # numpy scalars and NaN would raise or leak
    assert s["built"] == "2026-10-07T22:00:00Z" and s["season"] == 2026 and s["weeks"] == [5]
    assert s["model"] == {"yardage": "v2", "td": "2026-10-06"}
    a, b = s["td"]
    assert a["p_td"] == 0.6685 and a["xtd"] == 1.027 and a["touch"] == 22.69 and a["kickoff"] == "2026-10-09T00:15:00Z"
    assert b["tt"] is None and b["games"] == 3 and b["role_up"] is True and b["inj"] == "Q (28%)"
    assert s["elite"][0]["cat"] == "WR" and s["elite"][0]["proj"] == 71.35 and s["elite"][0]["qb_flag"] is True
    assert s["elite"][0]["qb_if"] == 55.6
    assert s["backup"][0]["cat"] == "RB" and s["backup"][0]["proj_if_out"] == 61.0 and s["backup"][0]["starters_out"] == "Starter OUT"


def test_write_snapshot_names_the_file_by_build_time_and_skips_repeats(tmp_path):
    p = write_snapshot(result(), tmp_path)
    assert p == tmp_path / "2026" / "2026-10-07T22-00-00Z.json"
    saved = json.loads(p.read_text())
    assert saved["hash"] and saved["td"][0]["pid"] == "p1"
    later_same = result(built=BUILT + pd.Timedelta(hours=13))                    # next morning, nothing changed
    assert write_snapshot(later_same, tmp_path) is None                           # identical predictions: not written again
    assert len(list((tmp_path / "2026").glob("*.json"))) == 1
    changed = result(built=BUILT + pd.Timedelta(hours=13), td=td_rows(p=0.5))     # an injury report moved a number
    p2 = write_snapshot(changed, tmp_path)
    assert p2 is not None and p2.name > p.name                                    # sorts after the first, so "latest" is well defined
    assert write_snapshot(changed, tmp_path) is None
    newer_model = result(built=BUILT + pd.Timedelta(hours=20), td=td_rows(p=0.5), td_model="2027-01-01")
    assert write_snapshot(newer_model, tmp_path) is not None                      # a refit counts as a change


def test_nothing_left_before_kickoff_writes_nothing(tmp_path):
    r = result(td=td_rows(PAST), elite=elite_rows(PAST), backups=backup_rows(PAST))
    assert write_snapshot(r, tmp_path) is None
    assert not (tmp_path / "2026").exists()


def test_code_version_is_recorded_but_does_not_make_two_snapshots_differ(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_SHA", "abc123")
    p = write_snapshot(result(), tmp_path)
    assert json.loads(p.read_text())["code_sha"] == "abc123"
    monkeypatch.setenv("GITHUB_SHA", "def456")
    assert write_snapshot(result(built=BUILT + pd.Timedelta(hours=1)), tmp_path) is None


def test_a_result_without_td_still_snapshots_the_yardage_predictions():
    r = result()
    r.td = {}
    s = snapshot(r)
    assert s["td"] == [] and len(s["elite"]) == 1 and len(s["backup"]) == 1


def test_cli_flag_writes_a_snapshot_and_reports_when_unchanged(tmp_path, monkeypatch, capsys):
    import props.__main__ as cli
    monkeypatch.setattr(cli, "build", lambda **kw: result())
    monkeypatch.setattr(cli, "write_workbook", lambda res, path: None)
    hist = tmp_path / "history"
    cli.main(["--out", str(tmp_path / "x.xlsx"), "--history", str(hist)])
    assert "Archived this build's predictions to" in capsys.readouterr().out
    assert len(list(hist.glob("2026/*.json"))) == 1
    cli.main(["--out", str(tmp_path / "x.xlsx"), "--history", str(hist)])
    assert "No new snapshot" in capsys.readouterr().out and len(list(hist.glob("2026/*.json"))) == 1
    cli.main(["--out", str(tmp_path / "x.xlsx")])                                  # without the flag nothing is archived
    assert len(list(hist.glob("2026/*.json"))) == 1
