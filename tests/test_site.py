import re

import pandas as pd
from props.pipeline import Result
from props.site import render, write_site


def result():
    ko = pd.Timestamp("2026-10-04 13:00", tz="America/New_York")
    elite = pd.DataFrame([dict(player_id="00-1", kickoff=ko, name="A <b>Bold</b> Player", team="AAA", opp_txt="@BBB", kick_txt="Sun 10/4 1p",
                               spr_tot="-3 / 44", inj="Q (28%)", rank=1, games=3, total=900, ypg=300.0, l3=310.0,
                               opp_rank=2, opp_alw=250.0, vs_lg=0.1, proj=270.0, week=4, gs_ctx=0.05, beta=0.0,
                               t_label="Att", t_exp=34.5, t_base=33.0, t_cur=36.0, t_l3=35.0, t_fvol=1.08, t_vac=0.0, t_flag=False, t_if=None, t_out="")])
    backups = pd.DataFrame([dict(player_id="00-2", kickoff=ko, name="Back Up", team="AAA", opp_txt="BBB", kick_txt="Sun 10/4 1p", spr_tot="",
                                 inj="", role="RB2", starters_out="Starter OUT", p_out=1.0, streak=3, base_vol=5.0,
                                 last_vol=6.0, proj_vol=12.0, ypv=4.2, opp_rank=20, opp_vs_lg=-0.05,
                                 proj_if_out=50.0, proj_exp=50.0, week=4)])
    empty = pd.DataFrame()
    rb = pd.DataFrame([dict(player_id="00-3", kickoff=ko, name="Runner", team="AAA", opp_txt="BBB", kick_txt="Sun 10/4 1p",
                            spr_tot="", inj="", rank=3, games=3, total=300, ypg=100.0, l3=95.0, opp_rank=4, opp_alw=110.0,
                            vs_lg=0.1, proj=80.0, week=4, gs_ctx=0.0, beta=0.6, t_label="Tch", t_exp=20.0, t_base=20.0,
                            t_cur=21.0, t_l3=22.0, t_fvol=1.05, t_vac=0.69, t_flag=True, t_if=27.4,
                            t_out="Starter OUT (69% of RB touches)")])
    return Result(2026, pd.DataFrame(), {}, {"QB": elite, "RB": rb, "WR": empty},
                  {"QB": empty, "RB": backups, "WR": empty},
                  {"generated": pd.Timestamp("2026-10-04 12:00", tz="America/New_York"), "weeks": [4, 5], "games": 2,
                   "data_through_week": 3, "injury_reports": {4: (4, False), 5: (4, True)},
                   "top_n": {"QB": 10, "RB": 15, "WR": 25}, "weak_n": 10, "model": "v2"},
                  {"season": 2026, "final": ["2026|3|AAA"], "y": {"2026|3|00-1|QB": 250}, "t": {"2026|3|00-1|QB": 31}})


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
    assert len(snaps) == 3
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
    assert r["final"] == ["2026|3|AAA"] and r["y"]["2026|3|00-1|QB"] == 250 and r["t"]["2026|3|00-1|QB"] == 31
    assert "250" not in (tmp_path / "s" / "index.html").read_text().split('id="meta"')[0]    # results never baked into cards


def test_new_model_features_are_visible_and_stamped():
    import json
    from html import unescape
    from props import config as C
    html = render(result())
    assert "10 QBs, 15 RBs and 25 WRs" in html
    assert "Game script +5%" in html and "Matchup not predictive at this rank" in html      # chips from gs_ctx / beta
    snaps = [json.loads(unescape(m)) for m in re.findall(r'data-snap="([^"]+)"', html)]
    assert all(x["model"] == C.MODEL_VERSION for x in snaps)
    meta = json.loads(re.search(r'id="meta">(.*?)</script>', html, re.S).group(1))
    assert meta["model"] == "v2"
    assert "Model check" in html and "review_bets.py" in html                               # feedback loop is wired into the page


def td_frame(n=30):
    rows = []
    for i in range(n):
        rows.append(dict(player_id=f"p{i}", name="A <b>Bold</b> RB" if i == 0 else f"Runner {i}", team="AAA", week=4, rank=i + 1,
                         opp_txt="@BBB", kick_txt="Sun 10/4 1p", tt=27.5 if i else float("nan"), xtd=0.5, p_td=0.6 - i * 0.01,
                         fair="-150" if i == 0 else "-100", inj="Q (28%)" if i == 1 else "", role_up=(i == 2)))
    return pd.DataFrame(rows)


def test_anytime_td_tab_is_ranked_escaped_capped_and_has_an_odds_box():
    res = result()
    res.td = {"RB": td_frame(), "WR": pd.DataFrame(), "TE": pd.DataFrame()}
    html = render(res)
    assert 'data-p="p4"' in html and 'id="p4"' in html and ">Anytime TD<" in html
    assert "A &lt;b&gt;Bold&lt;/b&gt; RB" in html and "<b>Bold</b>" not in html
    assert 'data-p="0.6000"' in html and "fair -150" in html and "60%" in html
    assert html.count('class="tdrow"') == 30 and "Show all 30" in html          # 25 up front, the rest folded away
    assert "no line yet" in html and "team total 27.5" in html
    assert 'class="tdodds"' in html and "Q (28%)" in html and "Starter out: role may be bigger" in html
    assert "No players for this slate yet." in html                              # the empty WR / TE columns
    assert not re.search(r"\bnan\b", html, re.I)
    assert "/^p[0-4]$/" in html                                                   # every tab is reachable by link


def test_anytime_td_tab_shows_why_it_is_empty():
    res = result()
    res.meta["td_note"] = "The anytime-TD tab could not be built this time (ValueError)."
    assert "could not be built this time (ValueError)" in render(res)


def test_qb_flag_chip_note_and_frozen_fields_on_wr_cards():
    import json
    from html import unescape
    res = result()
    wr = res.elite["RB"].assign(player_id="00-4", name="Receiver", t_label="Tgt", q_flag=True, q_txt="Starter QB Q (60%)",
                                q_p=0.6, q_if=62.4)
    res.elite["WR"] = wr
    html = render(res)
    assert 'chip q">QB: Starter QB Q (60%)' in html
    assert "QB flag: Starter QB Q (60%)" in html and "about -22% in receiving yards" in html
    assert "About 62 yds if he sits" in html and "it is not in the projection" in html
    snaps = [json.loads(unescape(m)) for m in re.findall(r'data-snap="([^"]+)"', html)]
    w = next(x for x in snaps if x["pid"] == "00-4")
    assert w["q_flag"] is True and w["q_p"] == 0.6 and w["q_if"] == 62.4
    q = next(x for x in snaps if x["pid"] == "00-1")
    assert q["q_flag"] is False and "QB flag" not in html.split('data-snap="')[1]       # unflagged cards stay clean


def test_touches_outlook_block_and_frozen_fields():
    import json
    from html import unescape
    html = render(result())
    assert "Touches outlook (pass attempts)" in html and "Touches outlook (touches (carries + catches))" in html
    assert "The opposing defense faces 8% more pass attempts than average" in html          # QB driver note
    assert "Workload flag: Starter OUT (69% of RB touches)" in html and "not in the expected number" in html
    assert "About 27.4 touches if it holds" in html                                              # RB "if the bump holds" figure
    snaps = [json.loads(unescape(m)) for m in re.findall(r'data-snap="([^"]+)"', html)]
    rb = next(x for x in snaps if x["cat"] == "RB" and x["sheet"] == "elite")
    assert rb["t_exp"] == 20.0 and rb["t_flag"] is True and rb["t_if"] == 27.4 and rb["t_label"] == "Tch"
    qb = next(x for x in snaps if x["cat"] == "QB" and x["sheet"] == "elite")
    assert qb["t_exp"] == 34.5 and qb["t_fvol"] == 1.08 and qb["t_flag"] is False


def pick(**kw):
    base = dict(kind="yards", market="QB", label="Pass yds", pid="00-1", name="A <b>Bold</b> Player", team="AAA", opp_txt="@BBB",
                kick_txt="Sun 10/4 1p", kickoff="2026-10-04T17:00:00Z", week=4, game="g1", inj="", side="Under", line=244.5,
                price=-112, p=0.71, implied=0.5283, edge=0.1817, ev=0.34, fair="-245", proj=210.0, grade="A",
                reasons=["proj 210 vs line 244.5", "season 260/g (hot start, regresses)"], book="DraftKings",
                updated="2026-10-04T15:55:00Z", rank=1)
    return {**base, **kw}


def board_result(picks=None, watch=None, book_lines=262):
    res = result()
    res.picks = [pick(), pick(kind="td", market="TD", label="Anytime TD", pid="00-3", name="Runner", side="Yes", line=None,
                          price=135, p=0.48, implied=0.4255, edge=0.0545, ev=0.13, fair="+108", grade="B", rank=2,
                          reasons=["0.68 exp TD/g", "11 touches/g"])] if picks is None else picks
    res.watch = [dict(kind="yards", market="WR", label="Rec yds", pid="w9", name="Watch Wr", team="CCC", opp_txt="DDD",
                      kick_txt="Mon 10/5 8:15p", week=4, fair_line=58.5, over_at=54.5, under_at=61.5, proj=67.0,
                      reasons=["proj 67"]),
                 dict(kind="td", market="TD", label="Anytime TD", pid="t9", name="Watch Td", team="CCC", opp_txt="DDD",
                      kick_txt="Mon 10/5 8:15p", week=4, p=0.55, fair="-122", yes_at=150, reasons=["0.80 exp TD/g"])] if watch is None else watch
    res.meta["odds"] = {"pulled": "2026-10-04T15:55:00Z", "book_lines": book_lines, "remaining": 300, "unmatched": 0, "note": ""}
    return res


def test_top_plays_board_is_the_first_tab_and_states_side_number_price_and_why():
    html = render(board_result())
    assert 'data-p="p0" aria-selected="true">Top plays' in html and '<div class="panel" id="p1" hidden>' in html
    assert "DraftKings lines &middot; Sun 11:55a" in html                         # header pill, Eastern time
    assert "2 plays &middot; 1 A &middot; 1 B" in html
    assert 'class="grade A"' in html and 'class="grade B"' in html
    assert 'class="pside under">UNDER 244.5<' in html and 'class="pside yes">YES<' in html
    assert ">-112<" in html and ">+135<" in html and "edge +18.2 pts" in html and "+0.34u" in html
    assert "proj 210 vs line 244.5 &middot; season 260/g (hot start, regresses)" in html
    assert 'data-goto="c-QB-00-1-4" data-tab="p1"' in html and 'data-goto="t-TD-00-3-4" data-tab="p4"' in html
    assert "A &lt;b&gt;Bold&lt;/b&gt; Player" in html and "<b>Bold</b>" not in html
    assert "Over &le; 54.5" in html and "Under &ge; 61.5" in html and "Yes at +150 or better" in html
    assert "How picks are graded" in html and "5 points for RB/WR yards" in html
    assert len(re.findall(r'data-snap="', html)) == 3                             # picks never add bet-log snapshots
    assert not re.search(r"\bnan\b", html, re.I)


def test_board_explains_itself_when_empty():
    assert "No play clears the bar" in render(board_result(picks=[], watch=[]))
    html = render(board_result(picks=[], watch=[], book_lines=0))
    assert "No DraftKings lines yet" in html and 'class="pill warn">No DraftKings lines yet' in html


def test_cards_prefill_the_book_line_and_carry_the_pick_badge():
    import json
    from html import unescape
    res = board_result()
    res.lines = {("00-1", "QB"): [dict(kickoff="2026-10-04T17:00:00Z", teams=["AAA", "BBB"], point=244.5, over=-112, under=-108)],
                 ("00-3", "TD"): [dict(kickoff="2026-10-04T17:00:00Z", teams=["AAA", "BBB"], yes=135)]}
    res.td = {"RB": td_frame(3).assign(player_id=["00-3", "p1", "p2"], kickoff=pd.Timestamp("2026-10-04 13:00", tz="America/New_York")),
              "WR": pd.DataFrame(), "TE": pd.DataFrame()}
    html = render(res)
    snaps = [json.loads(unescape(m)) for m in re.findall(r'data-snap="([^"]+)"', html)]
    qb = next(x for x in snaps if x["pid"] == "00-1")
    assert qb["dk_line"] == 244.5 and qb["dk_over"] == -112 and qb["dk_under"] == -108
    assert "DraftKings 244.5 &middot; O -112 / U -108" in html and "Top play A &middot; Under 244.5" in html
    assert 'data-dk="+135"' in html and "edge +" in html and "Top play B &middot; Yes" in html
    assert "snap.dk_line" in html and "getAttribute('data-dk')" in html             # the page fills the boxes in


def test_dark_only_with_no_white_flash_on_load():
    html = render(result())
    assert '<meta name="color-scheme" content="dark">' in html and "prefers-color-scheme" not in html
    assert "--bg:#0f1115" in html and "html{background:var(--bg)" in html
    assert "--pos:#22c55e" in html and "--neg:#f43f5e" in html


def test_yardage_tab_lists_every_opponent_with_a_weak_defense_filter():
    res = result()
    weak = res.elite["QB"].iloc[0]
    res.elite_all = {"QB": pd.DataFrame([weak, weak.copy().rename(None)]).assign(player_id=["00-1", "00-9"], opp_rank=[2, 20]),
                     "RB": res.elite["RB"], "WR": pd.DataFrame()}
    html = render(res)
    assert 'id="c-QB-00-1-4" data-weak="1"' in html and 'id="c-QB-00-9-4" data-weak="0"' in html
    assert 'id="weakonly"' in html and ".weakonly #p1 .card[data-weak=\"0\"]{display:none}" in html
