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
    elite_n: int = 10            # Sheet 1 pool: top N at the position by season yards


CATS = {
    "QB": Category("QB", "QB - Passing Yards", ("QB",), "passing_yards", "attempts", "Att",
                   None, 0.50, 2, 0.0, 10, 60, "group", 1.00, 10),
    "RB": Category("RB", "RB - Rushing Yards", ("RB", "FB"), "rushing_yards", "carries", "Car",
                   ("RB", "FB"), 0.15, 2, 1.0, 3, 60, "group", 0.75, 15),
    "WR": Category("WR", "WR - Receiving Yards", ("WR",), "receiving_yards", "targets", "Tgt",
                   ("WR",), 0.10, 3, 0.7, 2, 40, "all", 1.00, 25),
}

# ---- Sheet 1: elite players vs weak defenses --------------------------------
ELITE_TOP_N = 10          # default pool size; per-position sizes live on each Category (QB 10, RB 15, WR 25)
WEAK_DEF_N = 10           # "weak" = the N defenses allowing the most yards to the position

# ---- Projection knobs -------------------------------------------------------
PLAYER_PRIOR_GAMES = 6    # [tuned] pseudo-games of last season's per-game average blended in
MIN_PRIOR_GAMES = 6       # games needed last season before we trust it as a prior
ELITE_GROUP_PULL = 0.3    # [tuned] pull toward the elite-group mean (winner's-curse correction)
MATCHUP_BETA = 0.75       # [tuned] share of the defense's yards-allowed edge passed through (QB; see tiers below)
# Matchup pass-through falls with player rank (2022-25 walk-forward, research/backtest_elite.py): WR slopes were
# 0.53 / 0.36 / 0.05 / 0.04 for ranks 1-5 / 6-10 / 11-18 / 19-25, RB 0.65 / 0.50 / 0.33.  Rounded, conservative values.
# (max rank in tier, beta): the first tier whose bound covers the player's rank applies.
MATCHUP_BETA_TIERS = {"QB": [(10, 0.75)], "RB": [(10, 0.60), (15, 0.30)], "WR": [(10, 0.45), (25, 0.0)]}
DEF_PRIOR_GAMES = 6       # [tuned] pseudo-games of last season's defensive numbers
DEF_PRIOR_REGRESS = 0.5   # [assumed] last season's defense is itself pulled halfway to league avg
TEAM_VOL_PRIOR_GAMES = 3  # [assumed] pseudo-games pulling team volume toward league average

# ---- Game script (QB only; see props/gamescript.py) -------------------------------------------
MODEL_VERSION = "v2"           # stamped on every saved bet so old and new model eras can be compared
LEAGUE_TEAM_TOTAL = 22.0       # average points per team per game, 2022-25
# [tuned] 2022-25 leave-one-season-out: QB RMSE 74.8 -> 73.2.  `level` fixes the elite-QB projection running ~4% high,
# `tt` is the effect per unit of implied-team-total gap, `home` the home-field effect, `tt_ref` the typical gap.
GAME_SCRIPT = {"QB": {"level": -0.0416, "tt": 0.2368, "home": 0.0466, "tt_ref": 0.1234}}

# ---- Touches outlook (props/touches.py; evidence in research/experiment_touches.py) ----------------------------
TOUCH_QB_VOLUME_BETA = 0.8     # [tuned] QB attempts per unit of the opposing defense's volume-allowed gap (slope 0.87, t=4.1)
TOUCH_FLAG_MIN = 0.05          # flag a workload bump when teammates likely to miss hold at least this share of the pool
# RB/WR workload effect when teammates are out, 2023-25: `slope` per unit of v/(1-v); `bump` = avg touches vs baseline
# in those games; `n` = games.  Shown as a flag only: it did not improve out-of-sample accuracy.
TOUCH_WORKLOAD = {"RB": {"slope": 0.55, "bump": 0.19, "n": 36}, "WR": {"slope": 0.45, "bump": 0.06, "n": 241}}

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
# Weight (in share points per 100% of offensive snaps) of a player's recent snap share when a starter's
# volume is redistributed.  0 = off.  See research/experiment_snaps.py.
SNAP_WEIGHT = {"QB": 0.0, "RB": 0.5, "WR": 0.25}   # [tuned] 2024-25: RB corr(proj, actual) 0.29 -> 0.32, WR 0.10 -> 0.13
WITHOUT_SAMPLE_PRIOR = 2   # [assumed] games of "with-starter" evidence blended against each "without" game
ESTABLISHED_AFTER = 3      # starter has missed this many straight team games -> role already priced in
