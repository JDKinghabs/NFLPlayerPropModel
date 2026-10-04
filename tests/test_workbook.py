import pandas as pd
from openpyxl import load_workbook
from props.pipeline import Result
from props.workbook import write_workbook


def test_workbook_has_exactly_two_sheets_with_line_edge_formulas(tmp_path):
    elite = pd.DataFrame([dict(name="P", team="AAA", opp_txt="@BBB", kick_txt="Sun 10/4 1p", spr_tot="-3 / 44", inj="",
                               rank=1, games=3, total=900, ypg=300.0, l3=310.0, opp_rank=2, opp_alw=250.0,
                               vs_lg=0.1, proj=270.0)])
    res = Result(2026, pd.DataFrame(), {}, {"QB": elite, "RB": pd.DataFrame(), "WR": pd.DataFrame()},
                 {"QB": pd.DataFrame(), "RB": pd.DataFrame(), "WR": pd.DataFrame()},
                 {"generated": pd.Timestamp("2026-10-04 12:00", tz="America/New_York"), "weeks": [4], "games": 1,
                  "data_through_week": 3, "injury_reports": {4: (4, False)}, "top_n": 10, "weak_n": 10})
    out = tmp_path / "x.xlsx"
    write_workbook(res, out)
    wb = load_workbook(out)
    assert len(wb.sheetnames) == 2
    ws = wb[wb.sheetnames[0]]
    formulas = [c.value for row in ws.iter_rows() for c in row if isinstance(c.value, str) and c.value.startswith("=IF(")]
    assert len(formulas) == 1 and "ISNUMBER" in formulas[0]
    assert ws["A7"].value == "P"
