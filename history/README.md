# Prediction archive

Written by the "Refresh site" workflow (`python -m props --history history`, see `props/history.py`). Do not edit these files by hand.

Each `history/<season>/<UTC build time>.json` is what the model said, frozen, at that moment: every anytime-TD probability, every
yardage projection (Sheet 1 and Sheet 2) and every QB flag. It only contains games that had not kicked off when it was built, so it
can never contain hindsight. Snapshots also carry that build's Top plays (`picks`). The **latest** snapshot a game appears in is the last thing the model said before kickoff; that is
the one to grade against what happened. A snapshot identical to the previous one is not written again.

The commit history is the audit trail: a prediction cannot be changed after the game without that showing up in git.

## Sportsbook lines (`history/odds/`)

`history/odds/<season>/<UTC pull time>.json` is one pull from The Odds API (`props/odds.py`): the events, then every US book's
prop lines for QB pass yards, RB rush yards, WR receiving yards and anytime TD (`lines`: event, book, market, player, matched
`pid`, side, point, American price, the book's last update). Builds read the latest pull per game; together they are the line
history for closing-line work.

## Grading

`python -m props.scorecard --history history --season 2026` grades the latest snapshot of every finished game (see `props/scorecard.py`).
