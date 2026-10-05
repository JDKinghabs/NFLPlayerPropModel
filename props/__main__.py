"""CLI:  python -m props [--weeks 4 5] [--season 2026] [--out file.xlsx] [--refresh]"""
from __future__ import annotations

import argparse
from pathlib import Path

from . import config as C
from .pipeline import build
from .workbook import write_workbook


def main(argv=None):
    ap = argparse.ArgumentParser(prog="props", description=__doc__)
    ap.add_argument("--season", type=int, help="default: current NFL season")
    ap.add_argument("--weeks", type=int, nargs="+",
                    help="weeks to include (default: earliest week with games still to play)")
    ap.add_argument("--lookahead", type=int, default=1,
                    help="with no --weeks: include this many weeks starting at the earliest open one")
    ap.add_argument("--site", type=Path, help="also write a static website (index.html + xlsx) to this folder")
    ap.add_argument("--out", type=Path, help="output .xlsx (default: output/NFL_Props_<season>_Wk<weeks>.xlsx)")
    ap.add_argument("--refresh", action="store_true", help="re-download all data now")
    ap.add_argument("--include-started", action="store_true",
                    help="also include games that have already kicked off (not final)")
    ap.add_argument("--top", type=int, default=C.ELITE_TOP_N, help="'elite' = top N at the position")
    ap.add_argument("--weak", type=int, default=C.WEAK_DEF_N,
                    help="'weak defense' = N defenses allowing the most yards to the position")
    a = ap.parse_args(argv)

    res = build(season=a.season, weeks=a.weeks, refresh=a.refresh,
                include_started=a.include_started, lookahead=a.lookahead, top_n=a.top, weak_n=a.weak)
    wk = res.meta["weeks"]
    if not wk:
        raise SystemExit("No upcoming games found for that season/weeks.")
    out = a.out or Path("output") / f"NFL_Props_{res.season}_Wk{'-'.join(map(str, wk))}.xlsx"
    out.parent.mkdir(parents=True, exist_ok=True)
    write_workbook(res, out)

    print(f"Wrote {out}  (season {res.season}, weeks {wk}, {res.meta['games']} games, "
          f"stats through week {res.meta['data_through_week']})")
    for k in C.CATS:
        print(f"  {k}: {len(res.elite[k]):2d} elite-vs-weak-defense rows | {len(res.backups[k]):2d} backup rows")
    for w, (rep, stale) in res.meta["injury_reports"].items():
        if stale:
            print(f"  NOTE: no injury report for week {w} yet - using week {rep} (marked stale)")
        elif rep is None:
            print(f"  NOTE: no usable injury report for week {w} yet - no injury flags for those games")
    if a.site:
        from .site import write_site
        write_site(res, a.site, out)
        print(f"Wrote site to {a.site}/index.html")


if __name__ == "__main__":
    main()
