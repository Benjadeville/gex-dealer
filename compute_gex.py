"""
compute_gex.py — Dealer Gamma Exposure Calculator
GEX · Dealer Gamma Dashboard
======================================================
Fetches the SPY/SPX options chain via yfinance,
computes net dealer GEX per strike, identifies the
gamma flip level, and exports JSON for the dashboard.

Usage:
    python compute_gex.py --ticker SPY
    python compute_gex.py --ticker SPY --export data/gex.json
    python compute_gex.py --ticker SPX --n-expiries 4

Note: yfinance options data is ~15min delayed (free tier).
For real-time: use Tradier API (free tier) or CBOE DataShop.
"""

import argparse
import json
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import yfinance as yf


# ── CONFIG ────────────────────────────────────────────
CONTRACT_MULT = 100          # standard US equity options
GEX_SCALE = 1e9              # report in $B


# ── CORE COMPUTATION ─────────────────────────────────

def fetch_options_chain(ticker: str, n_expiries: int = 6) -> tuple[float, pd.DataFrame]:
    """
    Fetch options chain and spot price.
    Returns (spot_price, combined_chain_df).
    """
    t = yf.Ticker(ticker)
    spot = t.fast_info.get("last_price") or t.fast_info.get("previousClose")
    if spot is None:
        raise ValueError(f"Could not fetch spot price for {ticker}")

    expirations = t.options[:n_expiries]
    if not expirations:
        raise ValueError(f"No options data available for {ticker}")

    print(f"  Spot: ${spot:,.2f} | Fetching {len(expirations)} expirations...")

    frames = []
    for exp in expirations:
        chain = t.option_chain(exp)
        for opt_type, df in [("call", chain.calls), ("put", chain.puts)]:
            df = df.copy()
            df["option_type"] = opt_type
            df["expiry"] = exp
            frames.append(df)
        print(f"    ✓ {exp}")

    full_chain = pd.concat(frames, ignore_index=True)
    return float(spot), full_chain


def compute_gex_per_strike(chain: pd.DataFrame, spot: float) -> pd.DataFrame:
    """
    GEX formula (per contract):
        GEX = sign × gamma × open_interest × contract_mult × spot²

    sign: +1 for calls (dealers short = long gamma), -1 for puts (dealers short = short gamma)
    
    This is the standard dealer GEX convention assuming dealers are
    net short optionality to market makers.
    """
    df = chain[["strike", "option_type", "openInterest", "gamma", "expiry"]].copy()
    df = df.dropna(subset=["gamma", "openInterest"])
    df = df[df["gamma"] > 0]

    df["sign"] = df["option_type"].map({"call": 1, "put": -1})
    df["gex_raw"] = (
        df["sign"]
        * df["gamma"]
        * df["openInterest"]
        * CONTRACT_MULT
        * (spot ** 2)
    )

    # Aggregate per strike (sum across expiries and option types)
    by_strike = df.groupby("strike", as_index=False).agg(
        gex=("gex_raw", "sum"),
        total_oi=("openInterest", "sum"),
    )
    by_strike["gex_bn"] = by_strike["gex"] / GEX_SCALE   # in $B
    by_strike = by_strike.sort_values("strike").reset_index(drop=True)

    return by_strike


def compute_gex_by_expiry(chain: pd.DataFrame, spot: float) -> pd.DataFrame:
    """GEX aggregated by expiry date — for the expiry calendar panel."""
    df = chain[["expiry", "option_type", "openInterest", "gamma", "strike"]].copy()
    df = df.dropna(subset=["gamma", "openInterest"])
    df["sign"] = df["option_type"].map({"call": 1, "put": -1})
    df["gex_raw"] = df["sign"] * df["gamma"] * df["openInterest"] * CONTRACT_MULT * (spot ** 2)
    df["notional"] = df["openInterest"] * CONTRACT_MULT * df["strike"]

    by_expiry = df.groupby("expiry", as_index=False).agg(
        gex=("gex_raw", "sum"),
        notional=("notional", "sum"),
    )
    by_expiry["gex_bn"] = by_expiry["gex"] / GEX_SCALE
    by_expiry["notional_tn"] = by_expiry["notional"] / 1e12
    return by_expiry


def find_gamma_flip(by_strike: pd.DataFrame) -> float:
    """
    Find the gamma flip level: the strike where net GEX changes sign.
    Returns the strike closest to zero cumulative GEX.
    """
    # Sort by strike, find zero-crossing
    df = by_strike.sort_values("strike").copy()
    df["cumgex"] = df["gex_bn"].cumsum()

    # Find the strike where cumulative GEX is closest to zero
    flip_idx = (df["cumgex"].abs()).idxmin()
    return float(df.loc[flip_idx, "strike"])


def determine_regime(total_gex: float, spot: float, flip_level: float) -> dict:
    """
    Determine current gamma regime.
    """
    regime = "LONG" if total_gex > 0 else "SHORT"
    spot_vs_flip = spot - flip_level
    pct_from_flip = (spot_vs_flip / flip_level) * 100

    return {
        "regime": regime,
        "regime_label": "LONG GAMMA — Volatility suppression, mean reversion" if regime == "LONG"
                        else "SHORT GAMMA — Volatility amplification, trending",
        "spot_above_flip": spot_vs_flip > 0,
        "pts_from_flip": round(spot_vs_flip, 1),
        "pct_from_flip": round(pct_from_flip, 2),
        "dealer_action": (
            "Dealers BUY dips / SELL rallies (stabilizing)" if regime == "LONG"
            else "Dealers SELL dips / BUY rallies (destabilizing)"
        )
    }


# ── EXPORT ────────────────────────────────────────────

def build_dashboard_json(ticker: str, n_expiries: int = 6) -> dict:
    """Full pipeline → JSON payload for the dashboard."""
    print(f"\n[GEX] Computing for {ticker}...")

    spot, chain = fetch_options_chain(ticker, n_expiries)
    by_strike = compute_gex_per_strike(chain, spot)
    by_expiry = compute_gex_by_expiry(chain, spot)

    total_gex = float(by_strike["gex_bn"].sum())
    flip_level = find_gamma_flip(by_strike)
    regime = determine_regime(total_gex, spot, flip_level)

    print(f"\n  ▸ Total GEX : ${total_gex:+.2f}B")
    print(f"  ▸ Flip Level: {flip_level:,.0f}")
    print(f"  ▸ Regime    : {regime['regime']}")
    print(f"  ▸ Spot      : ${spot:,.2f} ({regime['pts_from_flip']:+.0f}pts from flip)")

    return {
        "meta": {
            "ticker": ticker,
            "spot": spot,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "source": "yfinance (15min delayed)",
        },
        "summary": {
            "total_gex_bn": round(total_gex, 3),
            "flip_level": flip_level,
            "regime": regime,
        },
        "gex_by_strike": by_strike[["strike", "gex_bn", "total_oi"]].round(4).to_dict("records"),
        "gex_by_expiry": by_expiry[["expiry", "gex_bn", "notional_tn"]].round(4).to_dict("records"),
    }


# ── CLI ───────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Compute Dealer GEX for the dashboard")
    parser.add_argument("--ticker", default="SPY", help="Ticker (SPY, QQQ, etc.)")
    parser.add_argument("--n-expiries", type=int, default=6, help="Number of expirations to include")
    parser.add_argument("--export", default="data/gex.json", help="Output JSON path")
    args = parser.parse_args()

    payload = build_dashboard_json(args.ticker, args.n_expiries)

    os.makedirs(os.path.dirname(args.export), exist_ok=True)
    with open(args.export, "w") as f:
        json.dump(payload, f, indent=2, default=str)

    print(f"\n  ✓ Exported → {args.export}")
    print(f"    {len(payload['gex_by_strike'])} strikes · {len(payload['gex_by_expiry'])} expirations\n")


if __name__ == "__main__":
    main()


# ── USAGE EXAMPLES ────────────────────────────────────
#
# Basic run:
#   python compute_gex.py
#
# SPX with 4 expiries:
#   python compute_gex.py --ticker SPX --n-expiries 4
#
# Custom output path:
#   python compute_gex.py --ticker SPY --export public/data/gex.json
#
# GitHub Actions (auto-refresh):
#   Schedule this script daily via .github/workflows/update_gex.yml
#   Commit gex.json → GitHub Pages dashboard reads it on load
#
# Extend with Tradier API for real-time (free tier):
#   Replace fetch_options_chain() with requests to:
#   https://sandbox.tradier.com/v1/markets/options/chains
