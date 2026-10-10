import json

import pandas as pd
import pytest
from props import config as C
from props import odds as O

NOW = pd.Timestamp("2026-10-11 07:00", tz="America/New_York")          # Sunday 7am ET = 11:00 UTC


def roster():
    rows = [("DAL", "Dak Prescott", "dak"), ("DAL", "CeeDee Lamb", "lamb"), ("TB", "Bucky Irving", "irving"),
            ("SEA", "Kenneth Walker III", "walker"), ("PHI", "A.J. Brown", "ajb"), ("PHI", "Josh Brown", "jbrown"),
            ("PHI", "Jalen Brown", "jbrown2")]
    return pd.DataFrame([dict(team=t, full_name=n, gsis_id=p, position="WR", status="ACT", week=5) for t, n, p in rows])


def test_names_match_through_suffixes_initials_and_punctuation_but_not_ambiguity():
    idx = O.roster_index(roster())
    assert O.match(idx, "Dak Prescott", ["DAL", "TB"]) == "dak"
    assert O.match(idx, "Kenneth Walker", ["SEA", "LA"]) == "walker"            # "III" dropped
    assert O.match(idx, "AJ Brown", ["PHI", "NYG"]) == "ajb"                     # punctuation
    assert O.match(idx, "J. Brown", ["PHI", "NYG"]) is None                      # two PHI "J Brown"s: refuse to guess
    assert O.match(idx, "CeeDee Lamb", ["SEA", "LA"]) is None                    # only the game's two teams count
    assert O.match(idx, "Dallas Cowboys D/ST", ["DAL", "TB"]) is None
    assert set(O.TEAM_ABBR.values()) >= {"LA", "LAC", "LV", "WAS", "JAX"} and len(O.TEAM_ABBR) == 32


class Resp:
    def __init__(self, data, remaining=400): self.data, self.headers = data, {"x-requests-remaining": str(remaining), "x-requests-used": "100"}
    def raise_for_status(self): pass
    def json(self): return self.data


def fake_get(events, remaining=400, calls=None):
    def get(url, params=None, timeout=None):
        if calls is not None:
            calls.append(url)
        if url.endswith("/events"):
            return Resp(events, remaining)
        ev = url.split("/events/")[1].split("/")[0]
        return Resp(dict(bookmakers=[
            dict(key="draftkings", markets=[
                dict(key="player_pass_yds", last_update="2026-10-11T10:55:00Z", outcomes=[
                    dict(name="Over", description="Dak Prescott", price=-115, point=265.5),
                    dict(name="Under", description="Dak Prescott", price=-105, point=265.5)]),
                dict(key="player_anytime_td", last_update="2026-10-11T10:55:00Z", outcomes=[
                    dict(name="Yes", description="CeeDee Lamb", price=-115),
                    dict(name="Yes", description="Dallas Cowboys D/ST", price=900)])]),
            dict(key="fanduel", markets=[dict(key="player_pass_yds", outcomes=[
                dict(name="Over", description="Dak Prescott", price=-110, point=262.5)])])]), remaining)
    return get


def events():
    return [dict(id="sun", commence_time="2026-10-11T17:00:00Z", home_team="Dallas Cowboys", away_team="Tampa Bay Buccaneers"),
            dict(id="mnf", commence_time="2026-10-13T00:15:00Z", home_team="Seattle Seahawks", away_team="Los Angeles Rams"),
            dict(id="old", commence_time="2026-10-09T00:15:00Z", home_team="Dallas Cowboys", away_team="Tampa Bay Buccaneers")]


def test_auto_pull_takes_only_games_inside_the_window_and_saves_every_book(tmp_path):
    calls = []
    path, note = O.pull("k", 2026, NOW, "auto", tmp_path, roster(), get=fake_get(events(), calls=calls))
    assert sum(u.endswith("/odds") for u in calls) == 1 and "/events/sun/odds" in "".join(calls)   # MNF is 37h away; the old game started
    doc = json.loads(path.read_text())
    assert path.parent.name == "2026" and doc["pulled"] == "2026-10-11T11:00:00Z" and doc["remaining"] == 400
    assert {ln["book"] for ln in doc["lines"]} == {"draftkings", "fanduel"}
    dak = [ln for ln in doc["lines"] if ln["player"] == "Dak Prescott" and ln["book"] == "draftkings"]
    assert {ln["side"] for ln in dak} == {"Over", "Under"} and dak[0]["pid"] == "dak" and dak[0]["market"] == "QB"
    assert "1 game" in note and "400 credits left" in note
    again = []
    path2, note2 = O.pull("k", 2026, NOW + pd.Timedelta(hours=1), "auto", tmp_path, roster(), get=fake_get(events(), calls=again))
    assert path2 is None and not any(u.endswith("/odds") for u in again)       # pulled an hour ago: not paid for twice


def test_force_pulls_every_game_left_in_the_slate_week_and_off_or_no_key_pull_nothing(tmp_path):
    calls = []
    O.pull("k", 2026, NOW, "force", tmp_path, roster(), last_kickoff=pd.Timestamp("2026-10-13T00:15:00Z"),
           get=fake_get(events(), calls=calls))
    assert sum(u.endswith("/odds") for u in calls) == 2
    assert O.pull("k", 2026, NOW, "off", tmp_path, roster(), get=fake_get(events())) == (None, "")
    path, note = O.pull(None, 2026, NOW, "auto", tmp_path, roster(), get=fake_get(events()))
    assert path is None and "No ODDS_API_KEY" in note


def test_pulling_stops_when_credits_run_low(tmp_path):
    calls = []
    O.pull("k", 2026, NOW, "force", tmp_path, roster(), get=fake_get(events(), remaining=C.ODDS_MIN_REMAINING - 1, calls=calls))
    assert sum(u.endswith("/odds") for u in calls) == 1                      # the first answer said credits are low: stop


def test_load_keeps_the_latest_price_for_games_not_started_and_book_lines_pairs_sides(tmp_path):
    O.pull("k", 2026, NOW - pd.Timedelta(hours=8), "auto", tmp_path, roster(), get=fake_get(events()))
    df, meta = O.load(tmp_path, 2026, NOW)
    assert meta["book_lines"] == 4 and meta["unmatched"] == 1 and meta["pulled"] == "2026-10-11T03:00:00Z"   # 7am ET - 8h; one unmatched = the D/ST line
    lines = O.book_lines(df)
    dak = O.line_for(lines, "dak", "QB", pd.Timestamp("2026-10-11 13:00", tz="America/New_York"))
    assert dak == dict(kickoff="2026-10-11T17:00:00Z", updated="2026-10-11T10:55:00Z", teams=["DAL", "TB"], point=265.5,
                       over=-115, under=-105)                                  # the game's teams travel with the line
    assert O.line_for(lines, "lamb", "TD", pd.Timestamp("2026-10-11T17:00:00Z"))["yes"] == -115
    assert O.line_for(lines, "dak", "QB", pd.Timestamp("2026-10-18T17:00:00Z")) is None                    # a different game
    df2, _ = O.load(tmp_path, 2026, pd.Timestamp("2026-10-11T18:00:00Z"))
    assert df2.empty                                                                                       # kicked off: gone


def test_book_lines_takes_the_most_even_pair_when_a_player_has_two_points():
    df = pd.DataFrame([dict(event="e", kickoff="2026-10-11T17:00:00Z", book="draftkings", updated="t", market="WR", player="X",
                            pid="x", side=s, point=pt, price=pr, pulled="p")
                       for s, pt, pr in [("Over", 70.5, -150), ("Under", 70.5, +120), ("Over", 74.5, -112), ("Under", 74.5, -108)]])
    ln = O.book_lines(df)[("x", "WR")][0]
    assert ln["point"] == 74.5 and ln["over"] == -112 and ln["under"] == -108
