# 📊 GEX · Dealer Gamma Dashboard

> **Live demo → [Benjadeville.github.io/gex-dealer](https://Benjadeville.github.io/gex-dealer)**

A real-time (or EOD) options market microstructure dashboard tracking **dealer gamma exposure (GEX)** — one of the most actionable signals in institutional equity trading.

Inspired by the Citadel Securities framework described by Scott Rubner: when dealers flip from short to long gamma after a large quarterly expiration, they mechanically dampen volatility and create conditions for a mean-reversion squeeze.

---

## The Problem

After the Iran conflict began (Feb 28, 2026), US equities sold off aggressively. But the *mechanism* mattered: most of the selling came from **systematic strategies and ETF short hedges** — not fundamental sellers. GEX models can identify when that mechanical pressure reverses.

Specifically:
- **Short gamma** → dealers amplify moves (buy when it goes up, sell when it goes down)
- **Long gamma** → dealers dampen moves (buy dips, sell rallies) → vol suppression, mean reversion

The gamma flip level is the single price where dealer behavior changes sign.

---

## Approach

1. **Compute GEX per strike** — for each option: `GEX = gamma × OI × contract_mult × spot²`
2. **Aggregate by expiry and sign** — call GEX (positive) vs. put GEX (negative)
3. **Find the flip level** — strike where net GEX crosses zero
4. **Track over time** — monitor regime changes around major expirations
5. **Layer in ETF short interest** and CTA positioning as corroborating signals

---

## Dashboard Features

| Panel | Description |
|---|---|
| **GEX by Strike** | Bar chart — net dealer gamma per strike, green = long, red = short |
| **Gamma Flip Zone** | Key level where dealer behavior inverts |
| **Regime Badge** | Current regime: LONG Γ (stabilizing) or SHORT Γ (amplifying) |
| **Historical GEX** | 60-day time series showing regime shifts around expirations |
| **Expiry Calendar** | Upcoming expirations by notional and GEX impact |
| **ETF Volume %** | ETF as % of total equity volume — tracks systematic hedge activity |
| **Signal Matrix** | Multi-signal confluence: GEX trend, VIX term structure, P/C ratio |
| **Systematic Positioning** | CTA / vol-targeting / retail flow breakdown |

---

## Tech Stack

```
Python    → options chain fetch, GEX computation, data export
yfinance  → spot price, options chain (calls + puts)
pandas    → chain processing, strike aggregation
scipy     → implied vol solver (optional)
HTML/JS   → dashboard UI (Chart.js, zero dependencies)
```

---

## Quickstart

```bash
git clone https://github.com/Benjadeville/gex-dealer.git
cd gex-dealer
pip install yfinance pandas numpy scipy
python compute_gex.py --ticker SPY --export data/gex.json
# Then open index.html in browser, or deploy to GitHub Pages
```

---

## Core Computation (Python)

```python
import yfinance as yf
import pandas as pd
import numpy as np

def compute_gex(ticker="SPY"):
    spot = yf.Ticker(ticker).fast_info["last_price"]
    expirations = yf.Ticker(ticker).options[:6]  # next 6 expiries

    all_gex = []
    for exp in expirations:
        chain = yf.Ticker(ticker).option_chain(exp)
        
        for opt_type, df in [("call", chain.calls), ("put", chain.puts)]:
            df = df[["strike", "openInterest", "gamma"]].dropna()
            df["sign"] = 1 if opt_type == "call" else -1
            # GEX = gamma × OI × 100 × spot²  (for 100-share contracts)
            df["gex"] = df["sign"] * df["gamma"] * df["openInterest"] * 100 * spot**2 / 1e9
            df["expiry"] = exp
            all_gex.append(df)

    gex_df = pd.concat(all_gex).groupby("strike")["gex"].sum().reset_index()
    flip_level = gex_df.iloc[(gex_df["gex"]).abs().argsort()[:1]]["strike"].values[0]
    
    return {
        "spot": spot,
        "gex_by_strike": gex_df.to_dict("records"),
        "flip_level": float(flip_level),
        "total_gex": float(gex_df["gex"].sum()),
        "regime": "LONG" if gex_df["gex"].sum() > 0 else "SHORT"
    }
```

---

## Deploy to GitHub Pages (5 minutes)

```bash
# 1. Create repo on GitHub named: gex-dealer
# 2. Enable GitHub Pages in Settings → Pages → Branch: main → /root
# 3. Push your files:
git add . && git commit -m "Initial deploy" && git push

# For auto-refresh via GitHub Actions, see .github/workflows/update_data.yml
```

For live data, add a GitHub Action that runs `compute_gex.py` on a schedule and commits `data/gex.json` — the HTML dashboard reads this file on load.

---

## Data Sources

| Source | Use | Cost |
|---|---|---|
| `yfinance` | Options chain (delayed 15min) | Free |
| CBOE DataShop | Real-time options feed | Paid |
| Unusual Whales API | GEX pre-computed | ~$30/mo |
| Tradier API | Real-time chain, free tier available | Free tier |

---

## Key Concepts

**GEX (Gamma Exposure)** — Aggregate measure of how much dealers must buy/sell to maintain delta neutrality as spot moves. Positive = long gamma (dampening), negative = short gamma (amplifying).

**Gamma Flip** — The strike where aggregate dealer gamma changes sign. Acts as a magnet for spot price in long-gamma regimes.

**Vol-of-Vol** — In long gamma regimes, realized volatility compresses as dealer hedging absorbs order flow. In short gamma: vol feeds on itself.

**Post-OPEX dynamics** — After large quarterly expirations, gamma resets. The direction of reset (long vs. short) determines the next regime.

---

## Related Projects in This Portfolio

- [`cta-positioning-model`](../cta-positioning-model) — CTA trend-following exposure simulator
- [`etf-short-monitor`](../etf-short-monitor) — ETF short interest as % of total volume tracker
- [`black-scholes-pricer`](../black-scholes-pricer) — Foundation: options pricing and Greeks

---

## References

- Rubner, S. (2026). *Citadel Securities equity flow note* — GEX regime analysis
- Bouchaud, J.P. et al. — *Trades, Quotes and Prices* (market microstructure)
- [SpotGamma](https://spotgamma.com) — Industry standard GEX methodology
- [CBOE White Paper](https://www.cboe.com) — Options market structure

---

*Simulated data for demo. Not financial advice.*
