import math
import numpy as np
from typing import List, Optional, Dict, Tuple, Sequence

SQRT2 = math.sqrt(2.0)


def compute_rsi(prices: Sequence[float], period: int = 14) -> Optional[float]:
    """Calculates Wilder's RSI over a 1D Chainlink price array (matching POB-main/backtest.py)."""
    arr = np.asarray(prices, dtype=float)
    if len(arr) < period + 1:
        return None
    deltas = np.diff(arr)
    seed = deltas[:period]
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period
    rs = up / down if down != 0 else 0.0
    rsi_val = 100.0 - 100.0 / (1.0 + rs) if down != 0 else 100.0

    upval = up
    downval = down
    for i in range(period + 1, len(arr)):
        delta = deltas[i - 1]
        if delta > 0:
            upval = (upval * (period - 1) + delta) / period
            downval = (downval * (period - 1)) / period
        else:
            upval = (upval * (period - 1)) / period
            downval = (downval * (period - 1) + (-delta)) / period
        rs = upval / downval if downval != 0 else 0.0
        rsi_val = 100.0 - 100.0 / (1.0 + rs) if downval != 0 else 100.0
    return float(rsi_val) if np.isfinite(rsi_val) else None


def compute_ha_streaks(prices: Sequence[float]) -> Tuple[int, int, Dict[str, Optional[object]]]:
    """Computes Heiken-Ashi consecutive streaks (green_streak, red_streak) over a 1D
    Chainlink price array, matching POB-main/backtest.py."""
    arr = np.asarray(prices, dtype=float)
    n = len(arr)
    if n < 2:
        return 0, 0, {"color": None, "count": None}

    ha_open = float(arr[0])
    curr_color: Optional[str] = None
    streak = 0

    for i in range(1, n):
        ha_close = float(arr[i])
        ha_open = (ha_open + float(arr[i - 1])) / 2.0
        is_green = ha_close >= ha_open
        color = "green" if is_green else "red"

        if color == curr_color:
            streak += 1
        else:
            curr_color = color
            streak = 1

    green_streak = streak if curr_color == "green" else 0
    red_streak = streak if curr_color == "red" else 0
    return green_streak, red_streak, {"color": curr_color, "count": streak}


def realized_sigma(prices: Sequence[float], default_sigma: float = 0.000045) -> float:
    """Computes per-tick log-return standard deviation over Chainlink prices (matching POB-main)."""
    arr = np.asarray(prices, dtype=float)
    arr = arr[np.isfinite(arr) & (arr > 0)]
    if arr.size > 100:
        r = np.diff(np.log(arr))
        r = r[np.isfinite(r)]
        if r.size > 10:
            sig = float(np.std(r))
            if sig > 0:
                return sig
    return default_sigma


def fair_prob_up(spot: float, strike: float, tau_s: float,
                 sigma: Optional[float] = 0.000045) -> float:
    """POB-main continuous-seconds zero-drift normal CDF model:
        z = ln(spot / strike) / (sigma * sqrt(tau_s))
        fair_up = Phi(z)
    """
    if not spot or not strike or spot <= 0 or strike <= 0:
        return 0.5
    if tau_s <= 0:
        return 1.0 if spot > strike else 0.0
    sig = sigma if (sigma is not None and sigma > 0) else 0.000045
    z = math.log(spot / strike) / (sig * math.sqrt(tau_s))
    prob = 0.5 * (1.0 + math.erf(z / SQRT2))
    return float(min(1.0, max(0.0, prob)))

