"""Write the two-sheet Excel workbook."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from . import config as C

FONT = "Calibri"
BLOCK_FILL = {"QB": "1F4E78", "RB": "375623", "WR": "7F3F00"}      # dark header bands
SUB_FILL = {"QB": "DDEBF7", "RB": "E2EFDA", "WR": "FCE4D6"}        # column-header tint
INPUT_FILL = PatternFill("solid", fgColor="FFF2CC")
THIN = Side(style="thin", color="D9D9D9")
HEADER_ROW, FIRST_ROW = 6, 7


def _elite_cols(cat):
    return [
        ("Player", "name", 20, None), ("Tm", "team", 5, None), ("Opp", "opp_txt", 6, None),
        ("Kickoff", "kick_txt", 15, None), ("Spr / Tot", "spr_tot", 12, None),
        ("Inj", "inj", 13, None), ("Rk", "rank", 4, "0"), ("G", "games", 4, "0"),
        ("Szn Yds", "total", 8, "#,##0"), ("YPG", "ypg", 7, "0.0"), ("L3 Avg", "l3", 7, "0.0"),
        ("Opp Rk", "opp_rank", 7, "0"), ("Opp Alw/G", "opp_alw", 9, "0.0"),
        ("vs Lg", "vs_lg", 7, '+0%;-0%;0%'), ("Proj", "proj", 7, "0"),
    ]


def _backup_cols(cat):
    v = cat.vol_short
    return [
        ("Player", "name", 20, None), ("Tm", "team", 5, None), ("Opp", "opp_txt", 6, None),
        ("Kickoff", "kick_txt", 15, None), ("Spr / Tot", "spr_tot", 12, None),
        ("Role", "role", 6, None), ("Inj", "inj", 12, None),
        ("Starter(s) out", "starters_out", 36, None), ("P(out)", "p_out", 7, "0%"),
        ("Starter missed (straight)", "streak", 9, "0"),
        (f"Base {v}/G", "base_vol", 8, "0.0"), (f"Last Gm {v}", "last_vol", 7, "0"),
        (f"Proj {v}/G", "proj_vol", 8, "0.0"),
        (f"Yds/{v}", "ypv", 7, "0.00"), ("Opp Rk", "opp_rank", 7, "0"),
        ("vs Lg", "opp_vs_lg", 7, '+0%;-0%;0%'), ("Proj if Out", "proj_if_out", 9, "0"),
        ("Proj Exp", "proj_exp", 8, "0"),
    ]


def _write_block(ws, c0, cat, df, cols, proj_key, established_flag=False):
    """Write one position block starting at column c0. Returns number of columns used."""
    n = len(cols)
    line_c, edge_c = c0 + n, c0 + n + 1
    width = n + 2
    # block header band
    ws.merge_cells(start_row=HEADER_ROW - 1, start_column=c0, end_row=HEADER_ROW - 1,
                   end_column=c0 + width - 1)
    h = ws.cell(HEADER_ROW - 1, c0, cat.title)
    h.font = Font(name=FONT, bold=True, color="FFFFFF", size=12)
    h.fill = PatternFill("solid", fgColor=BLOCK_FILL[cat.key])
    h.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    # column headers
    heads = [c[0] for c in cols] + ["Line", "Edge"]
    for i, t in enumerate(heads):
        cell = ws.cell(HEADER_ROW, c0 + i, t)
        cell.font = Font(name=FONT, bold=True, size=9)
        cell.fill = PatternFill("solid", fgColor=SUB_FILL[cat.key])
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = Border(bottom=Side(style="medium", color=BLOCK_FILL[cat.key]))
    for i, (_, _, w, _) in enumerate(cols):
        ws.column_dimensions[get_column_letter(c0 + i)].width = w
    ws.column_dimensions[get_column_letter(line_c)].width = 7
    ws.column_dimensions[get_column_letter(edge_c)].width = 7
    ws.column_dimensions[get_column_letter(c0 + width)].width = 2     # spacer

    if df is None or df.empty:
        ws.merge_cells(start_row=FIRST_ROW, start_column=c0, end_row=FIRST_ROW, end_column=c0 + width - 1)
        c = ws.cell(FIRST_ROW, c0, "No qualifying players for this slate")
        c.font = Font(name=FONT, italic=True, color="7F7F7F", size=10)
        return width

    proj_col = next(i for i, c in enumerate(cols) if c[1] == proj_key)
    proj_letter = get_column_letter(c0 + proj_col)
    line_letter, edge_letter = get_column_letter(line_c), get_column_letter(edge_c)
    for r, row in enumerate(df.itertuples(index=False), start=FIRST_ROW):
        rowd = row._asdict()
        grey = established_flag and bool(rowd.get("streak", 0) >= C.ESTABLISHED_AFTER)
        for i, (_, key, _, fmt) in enumerate(cols):
            val = rowd[key]
            if isinstance(val, float) and pd.isna(val):
                val = None
            cell = ws.cell(r, c0 + i, val)
            cell.font = Font(name=FONT, size=10, italic=grey, color="7F7F7F" if grey else "000000")
            cell.border = Border(bottom=THIN)
            if fmt:
                cell.number_format = fmt
            cell.alignment = Alignment(horizontal="left" if i == 0 or key in ("starters_out", "inj", "spr_tot")
                                       else "center", vertical="center")
            if key == "opp_rank" and val is not None:
                if val <= 3:
                    cell.fill = PatternFill("solid", fgColor="F4B183")      # very weak D
                elif val <= C.WEAK_DEF_N:
                    cell.fill = PatternFill("solid", fgColor="FCE4D6")      # weak D
                elif val >= 33 - C.WEAK_DEF_N:
                    cell.fill = PatternFill("solid", fgColor="DDEBF7")      # strong D
            if key in (proj_key, "proj_exp"):
                cell.font = Font(name=FONT, size=10, bold=True, italic=grey,
                                 color="7F7F7F" if grey else "000000")
        lc = ws.cell(r, line_c)
        lc.fill, lc.number_format, lc.border = INPUT_FILL, "0.0", Border(bottom=THIN)
        lc.alignment = Alignment(horizontal="center")
        ec = ws.cell(r, edge_c, f'=IF(ISNUMBER({line_letter}{r}),{proj_letter}{r}-{line_letter}{r},"")')
        ec.number_format, ec.border = '+0.0;-0.0;0.0', Border(bottom=THIN)
        ec.alignment, ec.font = Alignment(horizontal="center"), Font(name=FONT, size=10, bold=True)
    last = FIRST_ROW + len(df) - 1
    rng = f"{edge_letter}{FIRST_ROW}:{edge_letter}{last}"
    ws.conditional_formatting.add(rng, FormulaRule(
        formula=[f"AND(ISNUMBER({edge_letter}{FIRST_ROW}),{edge_letter}{FIRST_ROW}>0)"],
        fill=PatternFill("solid", bgColor="C6EFCE"), font=Font(color="006100")))
    ws.conditional_formatting.add(rng, FormulaRule(
        formula=[f"AND(ISNUMBER({edge_letter}{FIRST_ROW}),{edge_letter}{FIRST_ROW}<0)"],
        fill=PatternFill("solid", bgColor="FFC7CE"), font=Font(color="9C0006")))
    return width


def _header(ws, title, sub, legend):
    ws["A1"] = title
    ws["A1"].font = Font(name=FONT, bold=True, size=15)
    ws["A2"] = sub
    ws["A2"].font = Font(name=FONT, size=10, color="404040")
    for i, line in enumerate(legend):
        ws.cell(3 + i, 1, line).font = Font(name=FONT, size=9, italic=True, color="595959")
    ws.row_dimensions[HEADER_ROW].height = 40
    ws.row_dimensions[HEADER_ROW - 1].height = 20
    ws.freeze_panes = ws.cell(FIRST_ROW, 1)
    ws.sheet_view.zoomScale = 90
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True


def _sub(res) -> str:
    m = res.meta
    wk = ", ".join(map(str, m["weeks"]))
    parts = [f"{res.season} season - week{'s' if len(m['weeks']) > 1 else ''} {wk} - {m['games']} games not yet kicked off",
             f"stats through week {m['data_through_week']}",
             f"built {m['generated'].strftime('%a %b %d %I:%M%p ET').replace(' 0', ' ')}"]
    for w, (rep, stale) in m["injury_reports"].items():
        if stale:
            parts.append(f"week {w} injury report not out yet - using week {rep}'s, carried forward at historical odds")
    return "  |  ".join(parts)


def write_workbook(res, path: Path) -> None:
    wb = Workbook()

    # ---------------- Sheet 1 ----------------
    ws = wb.active
    ws.title = "1 Elite vs Weak D"
    _header(
        ws, "Elite performers vs defenses that give up the category", _sub(res),
        [f"Elite = top {res.meta['top_n']} at the position by {res.season} yards (QB passing, RB rushing, WR receiving). "
         f"Weak defense = one of the {res.meta['weak_n']} allowing the most yards to that position (Opp Rk 1 = worst).",
         "Proj = per-game baseline (shrunk toward last year and the elite pack) x defense edge. L3 = last 3 games. "
         "Type the book number in the yellow Line column: Edge goes green when the model is above the line, red below."])
    c0 = 1
    for k, cat in C.CATS.items():
        c0 += _write_block(ws, c0, cat, res.elite.get(k), _elite_cols(cat), "proj") + 1

    # ---------------- Sheet 2 ----------------
    ws2 = wb.create_sheet("2 Backups")
    _header(
        ws2, "Backups who inherit volume because a starter is out", _sub(res),
        ["Backup = QB2 / RB2+ / WR3+ on a team missing a starter with real volume (QB 50%+ of attempts, RB 15%+ of carries, WR 10%+ of targets). "
         "Grey italic = starter already missed 3+ straight games (role likely priced in).",
         "P(out) = chance the listed starter(s) miss the game. Proj if Out assumes they do; Proj Exp is probability-weighted (Edge uses Proj Exp). "
         "Last Gm = volume in the team's most recent game (a sudden drop can mean an in-game injury that is not on the report yet)."])
    c0 = 1
    for k, cat in C.CATS.items():
        c0 += _write_block(ws2, c0, cat, res.backups.get(k), _backup_cols(cat), "proj_exp",
                           established_flag=True) + 1

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
