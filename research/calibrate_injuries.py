"""Calibrate the P(out) constants in props/config.py from 2023-25 injury reports.

"Rotation player" = averaged >= 6 attempts+carries+targets per game before the week in question.
A player "played" if he recorded any attempt/carry/target.

    python research/calibrate_injuries.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from props.data import cached  # noqa: E402

warnings.filterwarnings("ignore")
SKILL = ["QB", "RB", "WR", "TE", "FB"]
COLS = ["player_id", "position", "team", "season", "week", "season_type", "attempts", "carries", "targets"]


def main():
    fr = []
    for y in (2022, 2023, 2024, 2025):
        d = pd.read_csv(cached(f"stats_player/stats_player_week_{y}.csv", False), usecols=COLS)
        fr.append(d[d.season_type == "REG"])
    all_rows = pd.concat(fr)
    st = all_rows.copy()
    st["vol"] = st.attempts.fillna(0) + st.carries.fillna(0) + st.targets.fillna(0)
    st = st[st.position.isin(SKILL) & (st.vol > 0)].sort_values(["player_id", "season", "week"])

    cur = {k: list(zip(g.week, g.vol)) for k, g in st.groupby(["player_id", "season"])}
    prior = st.groupby(["player_id", "season"]).vol.mean()
    prior.index = pd.MultiIndex.from_tuples([(a, b + 1) for a, b in prior.index])
    prior = prior.to_dict()
    played = set(zip(st.player_id, st.season, st.week))
    team_weeks = set(zip(all_rows.team, all_rows.season, all_rows.week))

    inj = pd.concat([pd.read_csv(cached(f"injuries/injuries_{y}.csv", False)) for y in (2023, 2024, 2025)])
    inj = inj[(inj.game_type == "REG") & inj.position.isin(SKILL)].copy()

    def role(pid, s, w):
        g = [v for (wk, v) in cur.get((pid, s), []) if wk < w]
        return np.mean(g) if g else prior.get((pid, s), np.nan)

    inj["role"] = [role(a, b, c) for a, b, c in zip(inj.gsis_id, inj.season, inj.week)]
    inj["played_w"] = [(a, b, c) in played for a, b, c in zip(inj.gsis_id, inj.season, inj.week)]
    inj["played_n"] = [(a, b, c + 1) in played for a, b, c in zip(inj.gsis_id, inj.season, inj.week)]
    inj["next_game"] = [(t, s, w + 1) in team_weeks for t, s, w in zip(inj.team, inj.season, inj.week)]
    inj["status"] = inj.report_status.fillna("(none)")
    rot = inj[inj.role >= 6]

    def line(label, df, col):
        print(f"  {label:58s} n={len(df):4d}  P(miss)={1 - df[col].mean():.3f}")

    print("== Same week: P(player does not play | final injury report status) ==")
    for s in ("Out", "Doubtful", "Questionable"):
        line(f"{s} (all skill positions)", rot[rot.status == s], "played_w")
    q = rot[(rot.status == "Questionable")]
    line("Questionable QB (starters, role >= 20)", q[(q.position == "QB") & (q.role >= 20)], "played_w")
    line("Questionable RB/WR/TE", q[q.position != "QB"], "played_w")
    x = rot[rot.status == "(none)"]
    line("No game designation, practice DNP", x[x.practice_status.fillna("").str.startswith("Did Not")], "played_w")

    print("\n== Carry-over: P(miss the NEXT game | status this week), byes excluded ==")
    nx = rot[rot.next_game]
    line("Out", nx[nx.status == "Out"], "played_n")
    line("Doubtful", nx[nx.status == "Doubtful"], "played_n")
    nq = nx[nx.status == "Questionable"]
    line("Questionable and did NOT play that week", nq[~nq.played_w], "played_n")
    line("Questionable and played that week", nq[nq.played_w], "played_n")

    outs = set(zip(*[inj[inj.report_status == "Out"][c] for c in ("gsis_id", "season", "week")]))
    o = nx[nx.status == "Out"].copy()
    o["prev"] = [(a, b, c - 1) in outs for a, b, c in zip(o.gsis_id, o.season, o.week)]
    line("Out, first week out", o[~o.prev], "played_n")
    line("Out, 2+ straight weeks", o[o.prev], "played_n")


if __name__ == "__main__":
    main()
