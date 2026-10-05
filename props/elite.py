"""Sheet 1: top-N performers at each position facing a defense that is weak against the category."""
from __future__ import annotations

import pandas as pd

from . import config as C
from .config import Category
from .defense import matchup_beta, shrink
from .gamescript import context_effect, multiplier
from .slate import fmt_kick, fmt_opp, fmt_spread_total
from .touches import add_outlook


def season_table(stats: pd.DataFrame, cat: Category) -> pd.DataFrame:
    """Per-player season-to-date line for the category (games = games with real volume)."""
    s = stats[stats.position.isin(cat.positions) & (stats[cat.volume].fillna(0) > 0)]
    s = s.sort_values(["player_id", "week"])
    g = s.groupby("player_id")
    t = pd.DataFrame({
        "name": g.player_display_name.last(),
        "team": g.team.last(),
        "games": g.size(),
        "total": g[cat.yards].sum(),
        "l3": g[cat.yards].apply(lambda x: x.tail(3).mean()),
    })
    t["ypg"] = t.total / t.games
    return t.reset_index()


def prior_ypg(prev_stats: pd.DataFrame, cat: Category) -> pd.Series:
    """Last season's per-game average for players with enough games to mean something."""
    if prev_stats is None or prev_stats.empty:
        return pd.Series(dtype=float)
    t = season_table(prev_stats, cat)
    t = t[t.games >= C.MIN_PRIOR_GAMES]
    return t.set_index("player_id").ypg


def elite_table(cat: Category, stats, prev_stats, ratings: pd.DataFrame, slate: pd.DataFrame,
                pout_by_week: dict, top_n: int | None = None, weak_n: int = C.WEAK_DEF_N,
                ) -> pd.DataFrame:
    """Top-N at the position (by season yards) whose upcoming opponent is a weak defense."""
    t = season_table(stats, cat)
    if t.empty:
        return pd.DataFrame()
    t["rank"] = t.total.rank(ascending=False, method="min").astype(int)
    elite = t[t["rank"] <= (top_n or cat.elite_n)].copy()

    prior = prior_ypg(prev_stats, cat)
    elite["base"] = [shrink(y, g, prior.get(pid, float("nan")), C.PLAYER_PRIOR_GAMES)
                     for pid, y, g in zip(elite.player_id, elite.ypg, elite.games)]
    # winner's-curse correction: players picked for a hot start regress toward the elite pack
    elite["base"] = (1 - C.ELITE_GROUP_PULL) * elite.base + C.ELITE_GROUP_PULL * elite.base.mean()

    m = elite.merge(slate, on="team", how="inner")
    m = m.merge(ratings[["defense", "rank", "blend", "vs_lg", "factor"]]
                .rename(columns={"rank": "opp_rank", "blend": "opp_alw"}),
                left_on="opp", right_on="defense", how="left")
    m["gs"] = [multiplier(cat.key, sp, o, h) for sp, o, h in zip(m.spread, m.ou, m.home)]
    m["gs_ctx"] = [context_effect(cat.key, sp, o, h) for sp, o, h in zip(m.spread, m.ou, m.home)]
    m["beta"] = [matchup_beta(cat.key, int(r)) for r in m["rank"]]
    m["proj"] = m.base * (1 + m.beta * (m.factor - 1)) * m.gs

    inj_label, p_out = [], []
    for pid, wk in zip(m.player_id, m.week):
        po = pout_by_week.get(wk)
        hit = po[po.gsis_id == pid] if po is not None and len(po) else None
        if hit is not None and len(hit):
            inj_label.append(hit.label.iloc[0]); p_out.append(hit.p_out.iloc[0])
        else:
            inj_label.append(""); p_out.append(0.0)
    m["inj"], m["p_out"] = inj_label, p_out

    m = m[(m.opp_rank <= weak_n) & (m.p_out < 0.99) & m.proj.notna()].copy()      # never list a card with no projection
    m = add_outlook(m, cat, stats, prev_stats, ratings, pout_by_week)
    m["opp_txt"] = m.apply(fmt_opp, axis=1)
    m["kick_txt"] = m.kickoff.map(fmt_kick)
    m["spr_tot"] = [fmt_spread_total(s, o) for s, o in zip(m.spread, m.ou)]
    return m.sort_values(["kickoff", "opp_rank", "rank"]).reset_index(drop=True)
