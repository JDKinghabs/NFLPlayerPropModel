# Prediction archive

Written by the "Refresh site" workflow (`python -m props --history history`, see `props/history.py`). Do not edit these files by hand.

Each `history/<season>/<UTC build time>.json` is what the model said, frozen, at that moment: every anytime-TD probability, every
yardage projection (Sheet 1 and Sheet 2) and every QB flag. It only contains games that had not kicked off when it was built, so it
can never contain hindsight. The **latest** snapshot a game appears in is the last thing the model said before kickoff; that is
the one to grade against what happened. A snapshot identical to the previous one is not written again.

The commit history is the audit trail: a prediction cannot be changed after the game without that showing up in git.
