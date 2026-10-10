"""Anytime-TD probabilities for RB / WR / TE (the "Anytime TD" tab and sheet 3).

Evidence: research/experiment_td.py, walk-forward 2022-25, leave-one-season-out.  The probabilities are calibrated (predicted vs
actual TD rate within about 2.7 points in every quintile).  A player's field-position opportunity (expected TDs from where his
rushes and targets started), the game's implied team total and his carries + targets per game beat his own TD history for RB and
WR (log loss t = -5.3 / -4.4) and modestly for TE.  QBs are not modelled: the gain was not stable across seasons.

The same functions serve research and production, so the two cannot drift apart.  Coefficients, yard-line TD rates and
standardisation live in props/td_model.json (fit by research/fit_td_model.py), the same pattern as calibration.json.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C
from .slate import fmt_kick, fmt_opp, fmt_spread_total

MODEL_PATH = Path(__file__).with_name("td_model.json")
EDGES = np.array([1, 2, 3, 4, 6, 9, 13, 21, 36, 51])       # lower bounds of the yard-line buckets (yards from the end zone)
TD_GROUPS = ("RB", "WR", "TE")
FEATS = ["td", "rush_xtd", "tgt_xtd", "touch", "rush10", "tgt20"]
XCOLS = ["rush_xtd", "tgt_xtd", "rush10", "rush5", "tgt20", "tgt10"]
MODEL_FEATURES = ["lt", "lr", "lg", "ltt", "lv"]
# players with a real role, by shrunk usage per game: carries + targets (RB/WR/TE), rushes (QB)
MIN_TOUCH = {"RB": 6.0, "WR": 4.0, "TE": 3.0, "QB": 3.0}
PBP_COLS = ["season", "week", "season_type", "posteam", "play_type", "yardline_100", "rusher_player_id", "receiver_player_id",
            "rush_touchdown", "pass_touchdown", "sack", "two_point_attempt"]
AVAILABLE_ROSTER = ("ACT", "INA")       # INA is the game-day inactive list for the week just played, not a durable status


# ---- play-by-play -> expected TDs ---------------------------------------------------------------------------------------
def plays(d: pd.DataFrame):
    """(rushes, targets): runs with a rusher, and pass plays with a receiver that were not sacks."""
    rush = d[(d.play_type == "run") & d.rusher_player_id.notna()]
    tgt = d[(d.play_type == "pass") & d.receiver_player_id.notna() & (d.sack.fillna(0) == 0)]
    return rush, tgt


def clean_pbp(d: pd.DataFrame) -> pd.DataFrame:
    """Regular-season rushes and targets that were not two-point tries, with a known field position."""
    d = d[(d.season_type == "REG") & (d.two_point_attempt.fillna(0) == 0) & d.yardline_100.notna()]
    r, t = plays(d)
    return d[d.index.isin(r.index) | d.index.isin(t.index)]


def read_pbp(path) -> pd.DataFrame:
    """Load an nflverse play_by_play csv(.gz), keeping only the columns and plays the TD model uses."""
    if path is None:
        return pd.DataFrame(columns=PBP_COLS)
    return clean_pbp(pd.read_csv(path, usecols=lambda c: c in PBP_COLS, low_memory=False))


def bucket(y) -> np.ndarray:
    return np.clip(np.digitize(np.asarray(y, dtype=float), EDGES) - 1, 0, len(EDGES) - 1)


def td_rates(frames) -> tuple[np.ndarray, np.ndarray]:
    """(P(TD) per rush, P(TD) per target) in each yard-line bucket, pooled over cleaned play-by-play frames."""
    r = pd.concat([plays(f)[0] for f in frames])
    t = pd.concat([plays(f)[1] for f in frames])
    n = len(EDGES)
    rr = r.groupby(bucket(r.yardline_100.values)).rush_touchdown.mean().reindex(range(n)).fillna(0).values
    rt = t.groupby(bucket(t.yardline_100.values)).pass_touchdown.mean().reindex(range(n)).fillna(0).values
    return rr, rt


def player_weeks(d: pd.DataFrame, rr, rt) -> pd.DataFrame:
    """Per (season, week, player): rush_xtd / tgt_xtd (expected TDs from where the plays started), rush10, rush5, tgt20, tgt10."""
    key = ["season", "week", "player_id"]
    if d is None or d.empty:
        return pd.DataFrame({"season": pd.Series(dtype="int64"), "week": pd.Series(dtype="int64"), "player_id": pd.Series(dtype="object"),
                             **{c: pd.Series(dtype="float64") for c in XCOLS}})
    rush, tgt = plays(d)
    a = pd.DataFrame({"season": rush.season.values, "week": rush.week.values, "player_id": rush.rusher_player_id.values,
                      "rush_xtd": np.asarray(rr)[bucket(rush.yardline_100.values)],
                      "rush10": (rush.yardline_100.values <= 10).astype(int),
                      "rush5": (rush.yardline_100.values <= 5).astype(int)}).groupby(key).sum().reset_index()
    b = pd.DataFrame({"season": tgt.season.values, "week": tgt.week.values, "player_id": tgt.receiver_player_id.values,
                      "tgt_xtd": np.asarray(rt)[bucket(tgt.yardline_100.values)],
                      "tgt20": (tgt.yardline_100.values <= 20).astype(int),
                      "tgt10": (tgt.yardline_100.values <= 10).astype(int)}).groupby(key).sum().reset_index()
    return a.merge(b, on=key, how="outer").fillna(0)


def universe(stats: pd.DataFrame) -> pd.DataFrame:
    """Skill-position player-games from weekly stats; td = scored a rushing or receiving TD (the anytime-TD market)."""
    cols = ["season", "week", "player_id", "player_display_name", "grp", "team", "opponent_team", "touch", "td"]
    if stats is None or stats.empty:
        return pd.DataFrame(columns=cols)
    s = stats[stats.position.isin(["QB", "RB", "FB", "WR", "TE"])].copy()
    s["grp"] = s.position.replace({"FB": "RB"})
    car, tg = s.carries.fillna(0), s.targets.fillna(0)
    s["touch"] = np.where(s.grp == "QB", car, car + tg)
    played = np.where(s.grp == "QB", s.attempts.fillna(0) > 0, s.touch > 0)
    s = s[played].copy()
    s["td"] = ((s.rushing_tds.fillna(0) + s.receiving_tds.fillna(0)) >= 1).astype(int)
    return s[cols]


def with_opportunity(u: pd.DataFrame, pw: pd.DataFrame) -> pd.DataFrame:
    """Join each player-game with its field-position opportunity (zeros when he had no plays in the play-by-play)."""
    d = u.merge(pw, on=["season", "week", "player_id"], how="left")
    d[XCOLS] = d[XCOLS].fillna(0).astype(float)          # float even when there is no play-by-play (e.g. a failed download)
    return d


# ---- pre-game features ------------------------------------------------------------------------------------------------
def pregame(df: pd.DataFrame, k: float = C.PLAYER_PRIOR_GAMES) -> pd.DataFrame:
    """Add `pg_<feature>`: per-game mean of each feature over the player's EARLIER games this season, shrunk toward his
    per-game mean last season (if he played MIN_PRIOR_GAMES+ games), else toward last season's mean for his position.
    `n_prev` = earlier games this season.  df needs season, week, player_id, grp and the FEATS columns.
    """
    df = df.sort_values(["player_id", "season", "week"]).reset_index(drop=True)
    g = df.groupby(["player_id", "season"])
    df["n_prev"] = g.cumcount()
    # last season's per-player and per-position means, re-keyed to the season they will serve as a prior for
    me = df.groupby(["player_id", "season"]).agg(**{f: (f, "mean") for f in FEATS}, size=("td", "size")).reset_index()
    me["season"] += 1
    me = me.rename(columns={f: "pl_" + f for f in FEATS})
    me.loc[me["size"] < C.MIN_PRIOR_GAMES, ["pl_" + f for f in FEATS]] = np.nan
    po = df.groupby(["season", "grp"])[FEATS].mean().reset_index()
    po["season"] += 1
    po = po.rename(columns={f: "po_" + f for f in FEATS})
    df = df.merge(me.drop(columns="size"), on=["player_id", "season"], how="left").merge(po, on=["season", "grp"], how="left")
    for f in FEATS:
        cum = g[f].cumsum() - df[f]
        mean_prev = (cum / df.n_prev.replace(0, np.nan)).fillna(0)
        prior = df["pl_" + f].fillna(df["po_" + f]).fillna(df.groupby("grp")[f].transform("mean"))
        df["pg_" + f] = (df.n_prev * mean_prev + k * prior) / (df.n_prev + k)
    return df.drop(columns=[c for c in df.columns if c.startswith(("pl_", "po_"))])


def design(d: pd.DataFrame, tt_mean: float) -> pd.DataFrame:
    """Model inputs: log-odds of the TD history, log expected TDs from rushes / targets, log team total, log volume."""
    f = pd.DataFrame(index=d.index)
    r = np.clip(d.pg_td, 0.02, 0.98)
    f["lt"] = np.log(r / (1 - r))
    f["lr"] = np.log(d.pg_rush_xtd + 0.02)
    f["lg"] = np.log(d.pg_tgt_xtd + 0.02)
    f["ltt"] = np.log(d.tt.fillna(tt_mean) / tt_mean)
    f["lv"] = np.log(d.pg_touch + 1)
    return f


# ---- the stored model --------------------------------------------------------------------------------------------------
def load_model(path: Path = MODEL_PATH) -> dict | None:
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


def predict(group_model: dict, F: pd.DataFrame) -> np.ndarray:
    """P(anytime TD | plays) from the stored standardisation and logistic coefficients."""
    cols = group_model["features"]
    z = (F[cols].values - np.asarray(group_model["mean"])) / np.asarray(group_model["sd"])
    return 1 / (1 + np.exp(-(group_model["coef"][0] + z @ np.asarray(group_model["coef"][1:]))))


def fair_odds(p: float) -> str:
    """American price at which a bet on probability p breaks even."""
    if not 0 < p < 1:
        return ""
    o = -100 * p / (1 - p) if p >= 0.5 else 100 * (1 - p) / p
    return f"{o:+.0f}"


# ---- production: the slate's players --------------------------------------------------------------------------------------
def td_table(stats, prev_stats, pbp, prev_pbp, roster, slate, pout_by_week, model, backup_ids=frozenset()) -> dict:
    """{group: ranked DataFrame} of P(anytime TD) for role players on the slate's teams.

    Players come from the roster (so a player coming back from injury, or on a new team, is handled); his features come from
    his games this season and last, shrunk as in the research.  Players ruled out are dropped, Questionable ones stay with a
    flag.  P(TD) is conditional on the player playing (books void the bet if he is inactive).  Rank is within week and position.
    """
    empty = {k: pd.DataFrame() for k in TD_GROUPS}
    if model is None or slate is None or slate.empty or stats is None or stats.empty or roster is None or roster.empty:
        return empty
    rr, rt = np.asarray(model["rush_rate"]), np.asarray(model["tgt_rate"])
    season = int(stats.season.max())
    cur_u = with_opportunity(universe(stats), player_weeks(pbp, rr, rt))
    prev_u = with_opportunity(universe(prev_stats), player_weeks(prev_pbp, rr, rt))
    prior_games = prev_u.groupby("player_id").size() if len(prev_u) else pd.Series(dtype=int)

    r = roster.sort_values("week").drop_duplicates("gsis_id", keep="last") if "week" in roster else roster.drop_duplicates("gsis_id")
    r = r.assign(grp=r.position.replace({"FB": "RB"}))
    # fullbacks are left out: shrinkage toward the RB average inflates their usage early in the season, so the model gave one
    # a 15% chance against a 2.4% DraftKings price (Oct 2026); their role is too unlike a running back's to trust
    r = r[r.grp.isin(TD_GROUPS) & (r.position != "FB") & r.team.isin(set(slate.team)) & r.status.isin(AVAILABLE_ROSTER)
          & r.gsis_id.notna()]
    if r.empty:
        return empty
    # one stand-in "next game" per player (week 99), so his features use only games already played
    future = pd.DataFrame({"season": season, "week": 99, "player_id": r.gsis_id.values, "player_display_name": r.full_name.values,
                           "grp": r.grp.values, "team": r.team.values, "opponent_team": "", "touch": 0.0, "td": 0,
                           **{c: 0.0 for c in XCOLS}})
    allg = pd.concat([x for x in (prev_u, cur_u) if len(x)] + [future], ignore_index=True)
    f = pregame(allg)
    f = f[f.week == 99].copy()
    f["prior_games"] = f.player_id.map(prior_games).fillna(0)
    f = f[(f.pg_touch >= f.grp.map(MIN_TOUCH)) & ((f.n_prev >= 1) | (f.prior_games >= C.MIN_PRIOR_GAMES))]
    f = f.drop(columns=["week", "opponent_team", "team"]).merge(
        r[["gsis_id", "team"]].rename(columns={"gsis_id": "player_id"}), on="player_id")

    m = f.merge(slate, on="team", how="inner")
    if m.empty:
        return empty
    m["tt"] = m.ou / 2 - m.spread / 2                                   # book notation: negative spread = favoured
    F = design(m, model["tt_mean"])
    m["p_td"] = np.nan
    for g in TD_GROUPS:
        sel = (m.grp == g).values
        if sel.any() and g in model["groups"]:
            m.loc[sel, "p_td"] = predict(model["groups"][g], F[sel])
    m = m[m.p_td.notna()].copy()

    inj, p_out = [], []
    for pid, wk in zip(m.player_id, m.week):
        po = pout_by_week.get(wk)
        hit = po[po.gsis_id == pid] if po is not None and len(po) else None
        inj.append(hit.label.iloc[0] if hit is not None and len(hit) else "")
        p_out.append(float(hit.p_out.iloc[0]) if hit is not None and len(hit) else 0.0)
    m["inj"], m["p_out"] = inj, p_out
    m = m[m.p_out < 0.99].copy()

    m["name"] = m.player_display_name
    m["xtd"] = m.pg_rush_xtd + m.pg_tgt_xtd
    m["fair"] = m.p_td.map(fair_odds)
    m["role_up"] = m.player_id.isin(set(backup_ids))
    m["note"] = np.where(m.role_up, "Starter out: role may be bigger than his average", "")
    m["opp_txt"] = m.apply(fmt_opp, axis=1)
    m["kick_txt"] = m.kickoff.map(fmt_kick)
    m["spr_tot"] = [fmt_spread_total(s, o) for s, o in zip(m.spread, m.ou)]
    out = {}
    for g in TD_GROUPS:
        x = m[m.grp == g].sort_values(["week", "p_td"], ascending=[True, False]).reset_index(drop=True)
        x["rank"] = x.groupby("week").cumcount() + 1
        out[g] = x
    return out
