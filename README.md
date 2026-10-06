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
pytest                             # 57 tests
```

Output goes to `output/NFL_Props_<season>_Wk<weeks>.xlsx`. Only games that have **not kicked off** are shown.
Run it again Wednesday, Friday and Sunday morning: injury news is the main thing that moves Sheet 2.

## Live website

A GitHub Action (`.github/workflows/refresh.yml`) rebuilds the workbook and a static site from fresh nflverse data
and publishes it to GitHub Pages: daily, plus right after the Wednesday/Friday injury reports and Sunday around noon.
It covers this week's remaining games plus next week. Pages needs to be switched on once: **Settings -> Pages ->
Source: "GitHub Actions"**. The site is then at `https://<owner>.github.io/NFLPlayerPropModel/` and is public.

Build it locally with `python -m props --lookahead 2 --site site` and open `site/index.html`.

### Bet log ("My bets" tab)

Enter the book line on a card and the page shows the model's chance of going Over, with a lean (Over at 55%+, Under at 45%
or less, otherwise Pass). Open **Log a bet**, pick a side, odds and units, and save. Learning from the log is only honest
if hindsight can't leak in, so:

- **The snapshot is frozen at save time**: projection, matchup rank, injury status, the starters ruled out, the line, the
  lean and the time the page's data was built. Nothing is ever recomputed.
- **Results are a separate file** (`results.json`, rebuilt daily from nflverse). It only grades bets and never touches a snapshot.
- **Bets lock at kickoff**: no adding or deleting after the game starts. Only games not yet kicked off are on the page.
- A bet with a team-final but no stat line for the player is **void** (check your book if he was active). A line equal to the result is a push.
- The log lives in the browser (localStorage), so it is private to that device. **Export / Import** moves it between devices.
- The summary shows record, units, ROI, the model's average miss and bias, and how you did when following vs going against its lean.
- Every bet records the **model version** (`MODEL_VERSION` in `config.py`), so bets made before and after a model change stay comparable.
- **Model check** (appears at 5+ settled bets): actual vs projection by position, and, at 10+, predicted vs realised Over rates.

**Retuning from your own bets:** export the log and run `python research/review_bets.py nfl-prop-bets.json`. It grades every bet
against the real results and reports record, bias with 95% intervals, calibration with Wilson intervals, and whether following the
lean beat going against it. It only recommends a change at 30+ settled bets per position *and* a bias whose interval excludes zero
by 3%+; below that it says "no change warranted". Nothing is changed automatically.

Elite-sheet probabilities come from `research/calibrate_distribution.py`: the distribution of actual / projection in the
walk-forward backtests, fit on 2023-24 and checked on 2025 (predicted P(over) within about 2-5 points for RB and WR, up to 10 for
QB). Backups get **no lean**: fit on 2024 and tested on 2025, their P(over) was off by 10-20 points (only 21-71 cases per
position), so the page shows the projection and a wide past-cases range instead.

## Data

Everything comes from [nflverse](https://github.com/nflverse/nflverse-data) (free, no key): weekly player
stats, schedules (with spreads/totals), injury reports, depth charts and roster status. Sportsbook prop
lines are **not** included, so you enter them by hand. An odds feed is the obvious next addition (see Roadmap).

## How it works

### Sheet 1: elite players vs weak defenses

1. **Elite** = the top 10 QBs, top 15 RBs and top 25 WRs by season-to-date yards (QB passing, RB rushing, WR receiving).
2. **Weak defense** = one of the 10 defenses allowing the most yards to that position (`Opp Rk 1` = worst).
   Yards allowed are position-specific (rushing yards allowed *to RBs*, receiving yards allowed *to WRs*) and per game,
   shrunk toward last season's number because 3-4 games of defense is noisy.
3. **Proj** = the player's per-game average, shrunk toward last season and toward the pool average, times the matchup edge,
   times (for QBs only) a game-script factor from the market's spread and total plus home field.
   The **matchup weight falls with rank**: 0.75 for QBs, 0.60 / 0.30 for RB 1-10 / 11-15, 0.45 / 0 for WR 1-10 / 11-25,
   because in past seasons the defense barely predicted how depth receivers did. Cards say so.
4. Players listed Out/Doubtful are dropped; Questionable ones stay, flagged.
5. **Touches outlook** on each card (QB pass attempts, RB carries + catches, WR targets): expected touches next to the season
   average and last 3. Touches are steadier than yards (the plain average misses them by 26% / 33% / 41% vs ~30% / 52% / 57% for yards).
   - *QB*: expected attempts are adjusted for how many attempts the opposing defense faces (validated: t = 4.1, out-of-sample error -2.9%).
   - *RB / WR*: when teammates are likely out, a **workload flag** shows who and how much of the pool they held, plus the historical
     size of the bump (RB touches +19% over 36 games, WR targets +6% over 241). It is **information only**: it did not improve
     out-of-sample accuracy, so it is not folded into the expected number or the yards projection.
   - The forecast is frozen into each saved bet and graded against actual touches (`results.json` carries them) in the Model check.
6. **QB flag** (WR cards): when the team's starting QB (most attempts this season) may miss the game *and played the previous one*
   (injury report Out / Doubtful / Questionable, or on IR), the card shows a chip, the historical size of the effect and an
   "about N yds if he sits" figure. In a QB's first missed game, 2022-25, top WRs ran about -22% in receiving yards and -12% in
   targets vs baseline (t=-2.6 over 60 team-games, negative in all four seasons). A longer absence is not flagged because the season
   averages already contain it. It is **information only** (the error gain is small because only about 25 team-games a season
   qualify), so it is not in Proj. About 15-18 first missed games a season have no report designation (benchings, mid-game exits)
   and cannot be flagged in advance.

### Sheet 2: backups

For each team and position, find unavailable **starters** (a player who accounted for at least 50% of the team's
attempts / 15% of carries / 10% of targets in the games he played). Then:

1. Split the team's games into those where the starter played and those where he didn't.
2. Redistribute the starter's share of team volume to healthy teammates in proportion to their share, plus a
   depth-chart "next man up" bonus. Blend with what actually happened in the games he missed, so a role that
   has existed for weeks is not double counted.
3. `yards = team volume/game x projected share x yards-per-volume (shrunk to league average) x defense edge` (QBs also get the game-script factor).
   The redistribution weight is `share + depth-chart bonus + snap weight x recent offensive snap share` (RB 0.5, WR 0.25), so a
   receiver who is on the field a lot but barely targeted is first in line when a starter is out.

Availability is probabilistic. `P(out)` comes from the injury report and from roster status (IR etc.). When
next week's report isn't out yet, last week's is carried forward at the **historical** carry-over rate, and the
cell says so (`OUT (wk4 rpt)`). `Proj if Out` assumes the starter misses; `Proj Exp` weights by `P(out)`.
Grey italic rows mean the starter has already missed 3+ straight games (the market has had time to price it).

## Validation (what the evidence says)

All scripts are in `research/` and reproduce the numbers below. Constants in `props/config.py` are tagged
`[tuned]`, `[calibrated]` or `[assumed]`.

**Sheet 1 thesis, walk-forward 2023-25** (`research/backtest_elite.py`, QB top 10 / RB top 15 / WR top 25, week 4 onward, using only
data available before each game): actual / baseline yards

| | vs weak D | vs middle | vs strong D | matchup pass-through |
|---|---|---|---|---|
| QB | 1.03 | 0.96 | 0.88 | 0.78 |
| RB | 1.10 | 1.00 | 0.91 | 0.51 |
| WR | 0.97 | 0.93 | 0.95 | 0.13 |

The matchup effect is real for QBs and RBs (a 10-19% swing between weak and strong defenses) and **weak for receivers**,
fading to roughly nothing below the top 10 WRs (slopes 0.53 / 0.36 / 0.05 / 0.04 for WR ranks 1-5 / 6-10 / 11-18 / 19-25).
That is why the matchup weight is tiered by rank. Elite players also regress from a hot start, which is why the baseline is
shrunk rather than using the raw average, and yardage is right-skewed: the median outcome sits about 1% above the projection for
QBs, 6% below for RBs and 13% below for WRs, so the site uses a probability rather than "projection minus line".

**But point accuracy barely improves.** 2025 hold-out RMSE of the production projection vs the naive season-to-date average:
QB 73.8 vs 76.7, RB 39.6 vs 40.5, WR 38.5 vs 39.1 (bias: QB +2.5 vs -15.9 yards, RB -0.7 vs -3.1, WR -4.9 vs -7.7).
Single-game yardage is very noisy, so treat Proj as a fair-value anchor, not a prediction.

**Ideas tested and what happened** (`research/experiment_*.py`, leave-one-season-out over 2022-25):

| Idea | Result | Shipped |
|---|---|---|
| Game script (team total from spread/total) + home field | QB error -2.1% (implied team total t=3.2, home t=2.6); RB/WR no reliable gain | QB only |
| Weather, rest days, recent form | noise (all \|t\| < 2) | no |
| Per-play defense rating (yards per attempt/carry/target) | worse than per-game; ~zero pass-through for WRs | no |
| Wider pools (RB 15, WR 25) | tuning unchanged; model beats naive by more | yes |
| A second method (volume x regressed efficiency) as a cross-check | a near-clone: corr 0.97-0.99 with the production projection, same accuracy, no added information (t 0.9-1.6) | no |
| Teammates ruled Out as a forward signal for elite players | right direction, not significant (QB t=1.4, RB 1.7 on 38 games, WR 1.0) | no |
| Forecasting *touches* (attempts / carries+catches / targets): touches are steadier than yards (baseline misses 26% / 33% / 41% of the mean vs ~30% / 52% / 57% for yards) | QB attempts respond to a defense's volume-allowed rating (t=4.1, error -2.9%); teammates out raise RB touches +19% (t=3.6, 36 games) and WR targets +6% (t=2.8) but do not improve out-of-sample accuracy; none of it helps yards | QB: yes (expected attempts). RB/WR: shown as a flag only |
| Opposing defenders ruled Out as a forward signal | nothing (t <= 0.6) | no |
| Snap share for who absorbs a starter's volume | RB corr 0.29 -> 0.32, volume error about -3%; WR 0.10 -> 0.13, small | yes (RB 0.5, WR 0.25) |
| Starting QB out as a signal for his pass-catchers (`research/experiment_qb_out.py`, 2022-25, t-stats clustered by team-game) | **First missed game only** (injury report Out/Doubtful/Questionable, 60 team-games): WR receiving yards -22% (t=-2.6; negative in all 4 seasons), targets -12% and receptions -12%, so about half the drop is efficiency; RB receptions -20% (t=-2.0, directional); TE up but not significant (t 1.0-1.4); RB rushing nothing. A longer absence shows nothing because the season averages already contain it. Error gain is tiny (-0.4% RMSE) because only ~25 team-games a season qualify; the effect is large when it fires | not yet: candidate for a WR/RB receiving flag or multiplier |
| Teammates out, first missed game vs a longer absence (`research/experiment_fresh_absence.py`, same walk-forward pools, key teammates as in `backups.py`) | "Freshness" generalizes only partly. RB carries respond to a lead back's *first* missed game (+0.91 per 100% of RB carries vacated, t=3.7; flagged games +24% over 52 games) and not afterwards. Receivers' targets respond to a key teammate being out at *any* absence length (WR targets +0.35, t=2.2 forward / 4.0 ex-post; TE similar). None of it improves out-of-sample accuracy, even scored only on the flagged games (RMSE 0.4-10% worse): the effects are small next to single-game noise | no; the existing workload flag stays as information |
| Role columns nflverse already ships (target share, air-yards share, WOPR, depth of target, yards per target; `research/experiment_role_features.py`) | Nothing reliable out of sample (leave-one-season-out error within +/-0.5% for WR and TE). RB target share looked significant in-sample (t=2.8) but made out-of-sample error worse (+1%). WR depth of target predicts fewer receptions than the baseline (t=-3.9) for only a 0.4% gain | no |

**Sheet 2 mechanism, 2024-25 games where a starter was listed Out and the backup played**
(`research/backtest_backups.py`; depth rank proxied by volume rank because depth charts aren't archived weekly):

| | n | predicted extra volume | actual extra volume | volume RMSE (model / naive) | yards RMSE (model / naive) |
|---|---|---|---|---|---|
| QB (att) | 37 | +22.9 | +22.3 | 12.2 / 25.3 | 86 / 163 |
| RB (car) | 94 | +5.0 | +5.4 | 6.1 / 7.7 | 34 / 39 |
| WR (tgt) | 114 | +1.4 | +2.2 | 3.3 / 3.8 | 34 / 37 |

("Naive" = the backup keeps his season-average workload.) The model gets the *size* of the bump right at every position. It is
**much** better for QBs, clearly better for RBs, and for WRs it still cannot reliably tell *which* receiver gets the extra targets
(correlation with actual about 0.14). The backup knobs (`DEPTH_BONUS`, `SNAP_WEIGHT`, `uplift_shrink`) were tuned on this same
sample, so expect these numbers to be somewhat optimistic out of sample.

**Over/Under probabilities** (`research/calibrate_distribution.py`): fit on 2023-24 and checked on 2025, predicted P(over)
landed within about 2-7 points of the realised rate for every elite position. For backups the same check was off by 10-20 points
(21-58 cases per position), so they get no lean.

**Injury probabilities** (`research/calibrate_injuries.py`, 2023-25 rotation players): Out/Doubtful essentially
never play; Questionable misses 64% for starting QBs vs 29% for RB/WR/TE; a player listed Out is still out the
next game 67% of the time, and a Questionable player who sat is out again 52% (13% if he played).

## Known limits

- **No market data.** The model finds *candidate* spots; whether a spot is mispriced depends on the posted line,
  which you supply. Books already price the headline matchup effect.
- **Late news.** Mid-game injuries and inactives (announced ~90 minutes before kickoff) aren't visible until the
  next report. The `Last Gm` column helps: a backup who logged 4 attempts after averaging 24 may have been hurt.
- **Cross-position effects are mostly not modelled**: a missing TE or RB also moves WR targets (the workload flag only shows it); a QB's first missed game is flagged on WR cards but not in the projection; an offensive-line injury
  moves everything.
- Game script, weather, pace and snap counts aren't used; spread/total are shown for context only.
- Early-season samples are small (3-4 games); everything is shrunk toward prior information accordingly.
- The RB/WR workload flag rests on few games (36 RB games with a teammate out) and has not shown out-of-sample gains; treat it as context.
- Game script only helps QBs in the data. RB and WR lines are not adjusted for it.
- WR 11-25 are listed because they were asked for, but the defense matchup has shown no predictive value for them.
- Depth charts come from ESPN via nflverse and can lag roster moves.

## Roadmap

1. Pull prop lines from an odds API, then track closing-line value, the only honest test of an edge.
2. Cross-position redistribution (TE/RB out -> WR targets) and route-participation data for receivers.
3. A better WR model: targets per route run, and air yards share.
4. Re-tune `DEPTH_BONUS` with true weekly depth charts and out-of-sample splits.

## Layout

```
props/        config.py (all constants) | data.py | slate.py | defense.py | gamescript.py | snaps.py | volume.py | touches.py | qbout.py | availability.py
              elite.py (Sheet 1) | backups.py (Sheet 2) | workbook.py | site.py | results.py | calibration.py (+ calibration.json) | pipeline.py | __main__.py
.github/      workflows/refresh.yml (scheduled rebuild + Pages deploy)
research/     backtest_elite.py | backtest_backups.py | calibrate_injuries.py | calibrate_distribution.py | review_bets.py
              experiment_game_context.py | experiment_defense_rating.py | experiment_snaps.py
              experiment_opportunity_model.py | experiment_forward_signals.py | experiment_touches.py
              experiment_qb_out.py | experiment_fresh_absence.py | experiment_role_features.py | walkforward_pool.py (shared walk-forward helper)
tests/        pytest suite
output/       generated workbooks
```
