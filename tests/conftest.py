import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def gerar_candles(n=300, seed=0, drift=0.0, vol=0.02):
    """Série OHLCV sintética (random walk geométrico)."""
    rng   = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(drift, vol, n)))
    open_ = np.r_[close[0], close[:-1]]
    high  = np.maximum(open_, close) * (1 + rng.uniform(0, 0.01, n))
    low   = np.minimum(open_, close) * (1 - rng.uniform(0, 0.01, n))
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=n, freq="h"),
        "open": open_, "high": high, "low": low, "close": close,
        "volume": rng.uniform(1e3, 5e3, n),
    })


@pytest.fixture
def candles():
    return gerar_candles
