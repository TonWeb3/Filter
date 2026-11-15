from typing import Dict, Any

# ─────────────────────────────────────────────────────────────────────────────
#  POB-main Chainlink-only EV entry engine.
#
#  Matches POB-main/backtest.py (simulate_strategy_fast):
#  - Evaluates Chainlink-based fair_up vs Polymarket CLOB ask prices.
#  - Enforces timing window gates (min_entry_second, max_entry_second, min_seconds_left).
#  - Optional net fee EV hurdle (deducting fee_rate * p * (1 - p)).
#  - Optional RSI (>70 / <30) and Heiken-Ashi (>=6 streak) vetoes when use_vetoes is True.
#  - Optional moneyness / strike distance filter (min_strike_distance_bp).
# ─────────────────────────────────────────────────────────────────────────────

EXHAUSTION_BARS = 6


def _no_ev(reason: str) -> Dict[str, Any]:
    return {"action": "NO_TRADE", "side": None, "phase": "EV", "strength": "EV", "reason": reason}


def decide_ev(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """POB-main EV gate: Chainlink fair probability vs Polymarket ask price."""
    p_up = inputs.get("mcProbUp")
    price_up = inputs.get("priceUp")      # ask (buy) price for the UP share, 0..1
    price_down = inputs.get("priceDown")  # ask (buy) price for the DOWN share, 0..1

    if p_up is None:
        return _no_ev("missing_model_data")
    if price_up is None or price_down is None:
        return _no_ev("missing_prices")
    if price_up <= 0.001 or price_up >= 0.999 or price_down <= 0.001 or price_down >= 0.999:
        return _no_ev("invalid_quote_bounds")

    # Timing gates from POB-main
    t_s = inputs.get("t_s")
    tau_s = inputs.get("tau_s")
    min_ts = int(inputs.get("minEntrySecond", 0))
    max_ts = int(inputs.get("maxEntrySecond", 840))
    min_seconds_left = int(inputs.get("minSecondsLeft", 20))

    if t_s is not None and (t_s < min_ts or t_s > max_ts):
        return _no_ev(f"entry_time_{int(t_s)}s_outside_{min_ts}_{max_ts}s")
    if tau_s is not None and tau_s < min_seconds_left:
        return _no_ev(f"tau_{int(tau_s)}s_below_{min_seconds_left}s")

    p_down = 1.0 - p_up
    ev_up = p_up - price_up
    ev_down = p_down - price_down

    fees_enabled = bool(inputs.get("feesEnabled", True))
    net_ev_gate = bool(inputs.get("netEvGate", False))
    fee_rate = float(inputs.get("feeRate", 0.07))

    f_up = (fee_rate * price_up * (1.0 - price_up)) if (fees_enabled and net_ev_gate) else 0.0
    f_down = (fee_rate * price_down * (1.0 - price_down)) if (fees_enabled and net_ev_gate) else 0.0
    h_ev_up = ev_up - f_up
    h_ev_down = ev_down - f_down

    side_is_up = h_ev_up >= h_ev_down
    side = "UP" if side_is_up else "DOWN"
    p = p_up if side_is_up else p_down
    price = price_up if side_is_up else price_down
    raw_ev = ev_up if side_is_up else ev_down
    h_ev = h_ev_up if side_is_up else h_ev_down

    min_prob = float(inputs.get("minProb", 0.55))
    ev_threshold = float(inputs.get("evThreshold", 0.04))
    use_vetoes = bool(inputs.get("useVetoes", True))

    # Filter 1: Micro vetoes (RSI & Heiken-Ashi streaks on Chainlink ticks)
    if use_vetoes:
        rsi = inputs.get("rsi")
        if side_is_up and ((rsi is not None and rsi > 70.0) or inputs.get("haExhaustedGreen")):
            return _no_ev("rsi_overbought" if (rsi is not None and rsi > 70.0) else "ha_exhausted_up")
        if (not side_is_up) and ((rsi is not None and rsi < 30.0) or inputs.get("haExhaustedRed")):
            return _no_ev("rsi_oversold" if (rsi is not None and rsi < 30.0) else "ha_exhausted_down")

    # Filter 2: Moneyness / Strike Distance (basis points)
    min_bp = float(inputs.get("minStrikeDistanceBp", 0.0))
    if min_bp > 0:
        spot = inputs.get("spot")
        strike = inputs.get("strike")
        if not spot or not strike or strike <= 0:
            return _no_ev("missing_spot_or_strike")
        move_bp = (spot - strike) / strike * 10000.0
        if side_is_up and move_bp < min_bp:
            return _no_ev(f"move_bp_{move_bp:.1f}_below_{min_bp:.1f}")
        if (not side_is_up) and move_bp > -min_bp:
            return _no_ev(f"move_bp_{move_bp:.1f}_above_{-min_bp:.1f}")

    # Edge & Probability Gating
    if p < min_prob:
        return _no_ev(f"prob_{p:.2f}_below_{min_prob:.2f}")
    if h_ev < ev_threshold:
        return _no_ev(f"ev_{h_ev:.3f}_below_{ev_threshold:.3f}")

    strength = "HIGH_CONVICTION" if p >= 0.70 else "STRONG"
    return {
        "action": "ENTER", "side": side, "phase": "EV", "strength": strength,
        "prob": p, "price": price, "ev": raw_ev, "reason": "ev_enter"
    }
