"""Model constants.

Everything tunable lives here. Values marked [tuned] come from the walk-forward
backtest in research/backtest_elite.py (fit on 2023-24, checked on 2025);
values marked [calibrated] come from research/calibrate_injuries.py;
values marked [assumed] are judgement calls not yet backtested.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Category:
    key: str                 # QB / RB / WR
    title: str               # block heading
    positions: tuple         # player positions that count as this group
    yards: str               # stat column the prop is on
    volume: str              # opportunity column (attempts / carries / targets)
    vol_short: str
    def_positions: tuple | None  # positions whose yards count against a defense (None = all)
    starter_min_share: float     # vacated share needed for an absent player to count as a "starter"
    backup_min_depth: int        # depth-chart rank at/after which a player is a "backup"
    min_uplift: float            # min projected volume gain per game to list a backup
    min_proj_vol: float          # min projected volume per game to list a backup
    ypv_prior_n: float           # pseudo-volume used to shrink a backup's yards/volume to league avg
    redistribute: str            # "group": vacated volume goes to same-position players; "all": to every teammate
    uplift_shrink: float         # fraction of the modelled volume gain to keep (backtest-calibrated)


CATS = {
    "QB": Category("QB", "QB - Passing Yards", ("QB",), "passing_yards", "attempts", "Att",
                   None, 0.50, 2, 0.0, 10, 60, "group", 1.00),
    "RB": Category("RB", "RB - Rushing Yards", ("RB", "FB"), "rushing_yards", "carries", "Car",
                   ("RB", "FB"), 0.15, 2, 1.0, 3, 60, "group", 0.75),
    "WR": Category("WR", "WR - Receiving Yards", ("WR",), "receiving_yards", "targets", "Tgt",
                   ("WR",), 0.10, 3, 0.7, 2, 40, "all", 1.00),
}

# ---- Sheet 1: elite players vs weak defenses --------------------------------
ELITE_TOP_N = 10          # "elite" = top N at the position by season yards
WEAK_DEF_N = 10           # "weak" = the N defenses allowing the most yards to the position

# ---- Projection knobs -------------------------------------------------------
PLAYER_PRIOR_GAMES = 6    # [tuned] pseudo-games of last season's per-game average blended in
MIN_PRIOR_GAMES = 6       # games needed last season before we trust it as a prior
ELITE_GROUP_PULL = 0.3    # [tuned] pull toward the elite-group mean (winner's-curse correction)
MATCHUP_BETA = 0.75       # [tuned] share of the defense's yards-allowed edge passed through
DEF_PRIOR_GAMES = 6       # [tuned] pseudo-games of last season's defensive numbers
DEF_PRIOR_REGRESS = 0.5   # [assumed] last season's defense is itself pulled halfway to league avg
TEAM_VOL_PRIOR_GAMES = 3  # [assumed] pseudo-games pulling team volume toward league average

# ---- Availability -----------------------------------------------------------
# Same-week designations (final injury report for the game).  [calibrated] on 2023-25 rotation
# players (avg >= 6 touches/targets/attempts per game): Out and Doubtful essentially never play.
P_OUT_QUESTIONABLE_QB = 0.60   # starting QBs listed Q missed 64% (n=86)
P_OUT_QUESTIONABLE = 0.28      # RB/WR/TE listed Q missed 23-34%
P_OUT_PRACTICE_DNP = 0.27      # no game designation yet but Did Not Participate in practice
# Stale designations: the NEXT week's report is not out yet, so carry last week's forward.
# [calibrated] P(miss the following game | status last week), byes excluded.
P_OUT_STALE_OUT = 0.67         # listed Out (no extra stickiness for repeat-Out: 69% -> 64% -> 59%)
P_OUT_STALE_DOUBTFUL = 0.62
P_OUT_STALE_Q_DNP = 0.52       # listed Q AND did not play (listed Q and played: only 13%)
# Roster statuses that mean "not available"; INA is deliberately absent - in nflverse it is the
# game-day inactive list for the week just played, not a durable status.
ROSTER_UNAVAILABLE = {"RES", "EXE", "SUS", "PUP", "NON", "RET", "CUT"}

# ---- Backup redistribution --------------------------------------------------
# Extra weight (in share points) given to the depth-chart "next man up" when a starter's volume
# is redistributed, so players with no 2026 volume can still inherit it.
# [tuned] 3x the first guess on 2024-25 starter-Out situations (research/backtest_backups.py):
# RB volume RMSE 7.7 (naive) -> 6.3, and the predicted mean uplift matches the realised one.
DEPTH_BONUS = {
    "QB": {2: 0.50, 3: 0.05},
    "RB": {2: 0.30, 3: 0.12, 4: 0.03},
    "WR": {3: 0.18, 4: 0.09, 5: 0.045},
}
WITHOUT_SAMPLE_PRIOR = 2   # [assumed] games of "with-starter" evidence blended against each "without" game
ESTABLISHED_AFTER = 3      # starter has missed this many straight team games -> role already priced in
