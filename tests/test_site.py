import re

import pandas as pd
from props.pipeline import Result
from props.site import render, write_site


def result():
    ko = pd.Timestamp("2026-10-04 13:00", tz="America/New_York")
    elite = pd.DataFrame([dict(player_id="00-1", kickoff=ko, name="A <b>Bold</b> Player", team="AAA", opp_txt="@BBB", kick_txt="Sun 10/4 1p",
                               spr_tot="-3 / 44", inj="Q (28%)", rank=1, games=3, total=900, ypg=300.0, l3=310.0,
                               opp_rank=2, opp_alw=250.0, vs_lg=0.1, proj=270.0, week=4)])
    backups = pd.DataFrame([dict(player_id="00-2", kickoff=ko, name="Back Up", team="AAA", opp_txt="BBB", kick_txt="Sun 10/4 1p", spr_tot="",
                                 inj="", role="RB2", starters_out="Starter OUT", p_out=1.0, streak=3, base_vol=5.0,
                                 last_vol=6.0, proj_vol=12.0, ypv=4.2, opp_rank=20, opp_vs_lg=-0.05,
                                 proj_if_out=50.0, proj_exp=50.0, week=4)])
    empty = pd.DataFrame()
    return Result(2026, pd.DataFrame(), {}, {"QB": elite, "RB": empty, "WR": empty},
                  {"QB": empty, "RB": backups, "WR": empty},
                  {"generated": pd.Timestamp("2026-10-04 12:00", tz="America/New_York"), "weeks": [4, 5], "games": 2,
                   "data_through_week": 3, "injury_reports": {4: (4, False), 5: (4, True)}, "top_n": 10, "weak_n": 10},
                  {"season": 2026, "final": ["2026|3|AAA"], "y": {"2026|3|00-1|QB": 250}})


def test_render_escapes_html_and_shows_notes():
    html = render(result())
    assert "A &lt;b&gt;Bold&lt;/b&gt; Player" in html and "<b>Bold</b>" not in html
    assert "Week 5 injury reports aren&#x27;t out yet" in html or "Week 5 injury reports aren't out yet" in html
    assert "No qualifying players for this slate" in html          # empty RB/WR on the elite tab
    assert "likely priced in" in html                              # streak 3 -> faded card
    assert "data-proj" not in html                                 # replaced by the frozen data-snap
    assert not re.search(r"\bnan\b", html, re.I)                  # no leaked NaNs in visible content


def test_write_site(tmp_path):
    x = tmp_path / "in.xlsx"; x.write_bytes(b"x")
    idx = write_site(result(), tmp_path / "site", x)
    assert idx.exists() and (tmp_path / "site" / "NFL_Props_latest.xlsx").exists()
    assert (tmp_path / "site" / ".nojekyll").exists()
    assert "Download Excel" in idx.read_text()


def test_write_site_when_workbook_already_lives_in_the_site_folder(tmp_path):
    site = tmp_path / "site"; site.mkdir()
    x = site / "NFL_Props_latest.xlsx"; x.write_bytes(b"x")          # what the CI workflow does
    idx = write_site(result(), site, x)
    assert idx.exists() and x.read_bytes() == b"x"


def test_cards_carry_a_frozen_snapshot_with_kickoff_for_the_lock():
    import json
    from html import unescape
    html = render(result())
    snaps = [json.loads(unescape(m)) for m in re.findall(r'data-snap="([^"]+)"', html)]
    assert len(snaps) == 2
    e = next(x for x in snaps if x["sheet"] == "elite")
    assert e["pid"] == "00-1" and e["kickoff"] == "2026-10-04T17:00:00Z" and e["proj"] == 270.0 and e["season"] == 2026
    assert e["opp_rank"] == 2 and e["inj"] == "Q (28%)"
    b = next(x for x in snaps if x["sheet"] == "backup")
    assert b["p_out"] == 1.0 and b["proj_if_out"] == 50.0 and b["starters_out"] == "Starter OUT"


def test_page_has_bets_tab_and_embedded_calibration_and_meta():
    import json
    html = render(result())
    assert 'data-p="p3"' in html and 'id="p3"' in html and "Bets lock at kickoff" in html
    cal = json.loads(re.search(r'id="calib">(.*?)</script>', html, re.S).group(1))
    assert set(cal["elite"]) == {"QB", "RB", "WR"} and set(cal["backup"]) == {"QB", "RB", "WR"}
    meta = json.loads(re.search(r'id="meta">(.*?)</script>', html, re.S).group(1))
    assert meta["season"] == 2026 and meta["built"] == "2026-10-04T16:00:00Z"


def test_write_site_publishes_results_separately(tmp_path):
    import json
    write_site(result(), tmp_path / "s")
    r = json.loads((tmp_path / "s" / "results.json").read_text())
    assert r["final"] == ["2026|3|AAA"] and r["y"]["2026|3|00-1|QB"] == 250
    assert "250" not in (tmp_path / "s" / "index.html").read_text().split('id="meta"')[0]    # results never baked into cards
