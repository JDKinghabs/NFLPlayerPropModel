import json
import pandas as pd

from props import linelog as L


class Resp:
    def __init__(self, data): self.data = data
    def raise_for_status(self): pass
    def json(self): return self.data


class FakeSession:
    def __init__(self): self.calls = []
    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        if url.endswith("/events"):
            return Resp([dict(id="e1", commence_time="2026-10-11T17:00:00Z", home_team="A", away_team="B"),
                         dict(id="e2", commence_time="2026-10-20T17:00:00Z", home_team="C", away_team="D")])
        return Resp(dict(bookmakers=[dict(key="dk", markets=[dict(key="player_pass_yds", last_update="t", outcomes=[
            dict(name="Over", description="Patrick Mahomes", price=-115, point=265.5),
            dict(name="Under", description="Patrick Mahomes", price=-105, point=265.5)])])]))


def test_fetch_skips_late_events_and_flattens():
    s = FakeSession()
    rows = L.fetch_lines("k", kickoffs_before="2026-10-12T00:00:00Z", session=s)
    assert len(rows) == 2 and {r["side"] for r in rows} == {"Over", "Under"}
    assert rows[0]["market"] == "QB" and rows[0]["point"] == 265.5 and rows[0]["book"] == "dk"
    assert sum(u.endswith("/odds") for u, _ in s.calls) == 1


def test_attach_projection_by_normalised_name():
    lines = [dict(market="QB", player="Patrick Mahomes II"), dict(market="QB", player="Nobody")]
    proj = [dict(market="QB", name="Patrick Mahomes", pid="p1", proj=270.0)]
    out = L.attach_projections(lines, proj)
    assert out[0]["pid"] == "p1" and out[0]["proj"] == 270.0 and out[1]["pid"] is None


def test_log_skipped_without_key(monkeypatch, tmp_path):
    monkeypatch.delenv("ODDS_API_KEY", raising=False)
    assert L.log_lines(None, tmp_path) is None
    assert not list(tmp_path.iterdir())


def test_write_log_roundtrip(tmp_path):
    cols = ["player_id", "name", "team", "week", "proj"]
    elite = pd.DataFrame([["p1", "Patrick Mahomes", "KC", 5, 270.0]], columns=cols)
    td = pd.DataFrame([["p2", "Kyren Williams", "LA", 5, 0.5]], columns=["player_id", "name", "team", "week", "p_td"])
    bk = pd.DataFrame([["p3", "Tank Bigsby", "JAX", 5, 41.0, 60.0]],
                      columns=["player_id", "name", "team", "week", "proj_exp", "proj_if_out"])
    res = type("R", (), dict(season=2026, elite={"QB": elite}, backups={"RB": bk}, td={"RB": td},
                             meta=dict(generated=pd.Timestamp("2026-10-07 18:00", tz="UTC"), weeks=[5])))
    path = L.write_log(res, tmp_path, [dict(market="TD", player="Kyren Williams", side="Yes", price=-130, point=None)])
    d = json.loads(path.read_text())
    assert path.parent.name == "2026" and len(d["projections"]) == 3 and d["projections"][1]["proj"] == 41.0
    assert d["lines"][0]["pid"] == "p2" and d["lines"][0]["proj"] == 0.5
