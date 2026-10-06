import pandas as pd
from openpyxl import load_workbook
from props.pipeline import Result
from props.workbook import write_workbook


def td_rows():
    return pd.DataFrame([dict(name="R", rank=1, team="AAA", week=5, opp_txt="BBB", kick_txt="Sun 10/11 1p", spr_tot="-3 / 44", inj="",
                              n_prev=4, pg_touch=20.0, xtd=0.8, tt=27.0, note="", p_td=0.55, fair="-122")])


def test_workbook_has_three_sheets_with_line_edge_formulas(tmp_path):
    elite = pd.DataFrame([dict(name="P", team="AAA", opp_txt="@BBB", kick_txt="Sun 10/4 1p", spr_tot="-3 / 44", inj="",
                               rank=1, games=3, total=900, ypg=300.0, l3=310.0, opp_rank=2, opp_alw=250.0,
                               vs_lg=0.1, proj=270.0, t_exp=34.5, t_cur=33.0)])
    empty = pd.DataFrame()
    res = Result(2026, pd.DataFrame(), {}, {"QB": elite, "RB": empty, "WR": empty}, {"QB": empty, "RB": empty, "WR": empty},
                 {"generated": pd.Timestamp("2026-10-04 12:00", tz="America/New_York"), "weeks": [4], "games": 1,
                  "data_through_week": 3, "injury_reports": {4: (4, False)}, "top_n": 10, "weak_n": 10},
                 td={"RB": td_rows(), "WR": empty, "TE": empty})
    out = tmp_path / "x.xlsx"
    write_workbook(res, out)
    wb = load_workbook(out)
    assert wb.sheetnames == ["1 Elite vs Weak D", "2 Backups", "3 Anytime TD"]
    ws = wb[wb.sheetnames[0]]
    formulas = [c.value for row in ws.iter_rows() for c in row if isinstance(c.value, str) and c.value.startswith("=IF(")]
    assert len(formulas) == 1 and "ISNUMBER" in formulas[0]
    assert ws["A7"].value == "P"
    ws3 = wb["3 Anytime TD"]
    f3 = [c for row in ws3.iter_rows() for c in row if isinstance(c.value, str) and c.value.startswith("=IF(")]
    assert len(f3) == 1 and "ISNUMBER" in f3[0].value and "100/(" in f3[0].value        # odds -> implied probability, edge = P(TD) - implied
    assert "%" in f3[0].number_format
    assert ws3["A7"].value == "R" and ws3["A6"].value == "Player"
    heads = [c.value for c in ws3[6] if c.value]
    assert "P(TD)" in heads and "Book odds" in heads and "Fair" in heads
    assert ws3["A5"].value == "RB - Anytime TD"
