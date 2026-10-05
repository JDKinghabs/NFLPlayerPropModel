"""What counts as a 'touch' for each prop category."""
from __future__ import annotations

import pandas as pd

TOUCH_LABEL = {"QB": "Att", "RB": "Tch", "WR": "Tgt"}          # short column labels
TOUCH_WORD = {"QB": "attempts", "RB": "touches", "WR": "targets"}               # plain word for sentences
TOUCH_NAME = {"QB": "pass attempts", "RB": "touches (carries + catches)", "WR": "targets"}


def touch_col(df: pd.DataFrame, key: str) -> pd.Series:
    """QB: pass attempts.  RB: carries + receptions.  WR: targets."""
    if key == "QB":
        return df["attempts"].fillna(0)
    if key == "RB":
        rec = df["receptions"].fillna(0) if "receptions" in df else 0
        return df["carries"].fillna(0) + rec
    return df["targets"].fillna(0)
