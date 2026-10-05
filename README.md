# NFL Player Prop Model

Builds a two-sheet Excel workbook for single-game prop research on **QB passing yards, RB rushing
yards and WR receiving yards**. QB, RB and WR each get their own block of columns on both sheets.

| Sheet | Question it answers |
|---|---|
| **1 Elite vs Weak D** | Which top-10 performers at each position face a defense that gives up that category? |
| **2 Backups** | Which backups inherit volume because a starter is out (or might be)? |

Every row has a yellow **Line** cell. Type the sportsbook number and **Edge** (`Proj - Line`) turns
green or red.

```bash
pip install -r requirements.txt
python -m props                    # earliest week with games still to play
python -m props --weeks 5          # a specific week (or several: --weeks 4 5)
python -m props --refresh          # force a re-download (data is cached for 3h in data/raw/)
pytest                             # 20 tests
```

Output goes to `output/NFL_Props_<season>_Wk<weeks>.xlsx`. Only games that have **not kicked off** are shown.
Run it again Wednesday, Friday and Sunday morning: injury news is the main thing that moves Sheet 2.

## Live website

A GitHub Action (`.github/workflows/refresh.yml`) rebuilds the workbook and a static site from fresh nflverse data
and publishes it to GitHub Pages: daily, plus right after the Wednesday/Friday injury reports and Sunday around noon.
It covers this week's remaining games plus next week. Pages needs to be switched on once: **Settings -> Pages ->
Source: "GitHub Actions"**. The site is then at `https://<owner>.github.io/NFLPlayerPropModel/` and is public.

Build it locally with `python -m props --lookahead 2 --site site` and open `site/index.html`.

## Data

Everything comes from [nflverse](https://github.com/nflverse/nflverse-data) (free, no key): weekly player
stats, schedules (with spreads/totals), injury reports, depth charts and roster status. Sportsbook prop
lines are **not** included, so you enter them by hand. An odds feed is the obvious next addition (see Roadmap).

## How it works

### Sheet 1: elite players vs weak defenses

1. **Elite** = top 10 at the position by season-to-date yards (QB passing, RB rushing, WR receiving).
2. **Weak defense** = one of the 10 defenses allowing the most yards to that position (`Opp Rk 1` = worst).
   Yards allowed are position-specific (rushing yards allowed *to RBs*, receiving yards allowed *to WRs*),
   shrunk toward last season's number because 3-4 games of defense is noisy.
3. **Proj** = the player's per-game average, shrunk toward last season and toward the elite pack, times
   `1 + 0.75 x (defense edge)`.
4. Players listed Out/Doubtful are dropped; Questionable ones stay, flagged.

### Sheet 2: backups

For each team and position, find unavailable **starters** (a player who accounted for at least 50% of the team's
attempts / 15% of carries / 10% of targets in the games he played). Then:

1. Split the team's games into those where the starter played and those where he didn't.
2. Redistribute the starter's share of team volume to healthy teammates in proportion to their share, plus a
   depth-chart "next man up" bonus. Blend with what actually happened in the games he missed, so a role that
   has existed for weeks is not double counted.
3. `yards = team volume/game x projected share x yards-per-volume (shrunk to league average) x defense edge`.

Availability is probabilistic. `P(out)` comes from the injury report and from roster status (IR etc.). When
next week's report isn't out yet, last week's is carried forward at the **historical** carry-over rate, and the
cell says so (`OUT (wk4 rpt)`). `Proj if Out` assumes the starter misses; `Proj Exp` weights by `P(out)`.
Grey italic rows mean the starter has already missed 3+ straight games (the market has had time to price it).

## Validation (what the evidence says)

All scripts are in `research/` and reproduce the numbers below. Constants in `props/config.py` are tagged
`[tuned]`, `[calibrated]` or `[assumed]`.

**Sheet 1 thesis, walk-forward 2023-25** (`research/backtest_elite.py`, top-10 players, week 4 onward, using only
data available before each game): actual / baseline yards

| | vs weak D | vs middle | vs strong D |
|---|---|---|---|
| QB | 1.03 | 0.96 | 0.88 |
| RB | 1.08 | 0.98 | 0.92 |
| WR | 1.01 | 0.89 | 0.89 |

The matchup effect is real, a 10-17% swing between weak and strong defenses. Elite players also regress about
5-10% from a hot start, which is why the baseline is shrunk rather than using the raw average.

**But point accuracy barely improves.** On the 2025 hold-out the projection's RMSE was QB 74.9 vs 76.7
(naive season-to-date average), RB 42.9 vs 43.7, WR 42.8 vs 42.6. It mainly removes bias (QB -5.5 vs -15.9
yards). Single-game yardage is very noisy, so treat Proj as a fair-value anchor, not a prediction.

**Sheet 2 mechanism, 2024-25 games where a starter was listed Out and the backup played**
(`research/backtest_backups.py`; depth rank proxied by volume rank because depth charts aren't archived weekly):

| | n | predicted extra volume | actual extra volume | volume RMSE (model / naive) | yards RMSE (model / naive) |
|---|---|---|---|---|---|
| QB (att) | 37 | +22.9 | +22.3 | 12.2 / 25.3 | 88 / 163 |
| RB (car) | 95 | +5.3 | +5.5 | 6.3 / 7.8 | 34.5 / 39.8 |
| WR (tgt) | 142 | +1.8 | +1.9 | 3.1 / 3.6 | 31.5 / 34.5 |

("Naive" = the backup keeps his season-average workload.) The model gets the *size* of the bump right at every
position. It is **much** better for QBs, modestly better for RBs, and for WRs it cannot reliably tell *which*
receiver gets the extra targets (correlation with actual about 0.2). The two backup knobs (`DEPTH_BONUS`,
`uplift_shrink`) were tuned on this same sample, so expect these numbers to be somewhat optimistic out of sample.

**Injury probabilities** (`research/calibrate_injuries.py`, 2023-25 rotation players): Out/Doubtful essentially
never play; Questionable misses 64% for starting QBs vs 29% for RB/WR/TE; a player listed Out is still out the
next game 67% of the time, and a Questionable player who sat is out again 52% (13% if he played).

## Known limits

- **No market data.** The model finds *candidate* spots; whether a spot is mispriced depends on the posted line,
  which you supply. Books already price the headline matchup effect.
- **Late news.** Mid-game injuries and inactives (announced ~90 minutes before kickoff) aren't visible until the
  next report. The `Last Gm` column helps: a backup who logged 4 attempts after averaging 24 may have been hurt.
- **Cross-position effects are not modelled**: a missing TE or RB also moves WR targets; an offensive-line injury
  moves everything.
- Game script, weather, pace and snap counts aren't used; spread/total are shown for context only.
- Early-season samples are small (3-4 games); everything is shrunk toward prior information accordingly.
- Depth charts come from ESPN via nflverse and can lag roster moves.

## Roadmap

1. Pull prop lines from an odds API, then track closing-line value, the only honest test of an edge.
2. Cross-position redistribution (TE/RB out -> WR targets) and a snap-count-based role signal.
3. Game-script adjustment from spread/total; weather for passing props.
4. Re-tune `DEPTH_BONUS` with true weekly depth charts and out-of-sample splits.

## Layout

```
props/        config.py (all constants) | data.py | slate.py | defense.py | availability.py
              elite.py (Sheet 1) | backups.py (Sheet 2) | workbook.py | site.py | pipeline.py | __main__.py
.github/      workflows/refresh.yml (scheduled rebuild + Pages deploy)
research/     backtest_elite.py | backtest_backups.py | calibrate_injuries.py
tests/        pytest suite
output/       generated workbooks
```
