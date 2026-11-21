"""Deterministic multi-sector synthetic demo market dataset (zero network required).

Used for:
- Instant first-boot Hostinger 1-Click experience when no API key is configured.
- Reproducible CI tests covering anti-leakage, 4-arm falsification, and E-values.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from quantseal.data.base import LoadedDiscoveryDataset, LoaderConfig, build_dataset_from_raw_frames

DEMO_UNIVERSE: tuple[tuple[str, str, float, float], ...] = (
    ("SPY", "Broad Market", 480.0, 0.009),
    ("QQQ", "Technology", 410.0, 0.013),
    ("IWM", "Small Cap", 195.0, 0.014),
    ("XLK", "Technology", 190.0, 0.013),
    ("XLF", "Financials", 40.0, 0.011),
    ("XLE", "Energy", 88.0, 0.016),
    ("XLV", "Healthcare", 140.0, 0.009),
    ("XLI", "Industrials", 120.0, 0.011),
    ("XLP", "Staples", 75.0, 0.007),
    ("XLY", "Discretionary", 178.0, 0.013),
    ("XLB", "Materials", 86.0, 0.012),
    ("XLU", "Utilities", 68.0, 0.010),
    ("SMH", "Semiconductors", 215.0, 0.019),
    ("GLD", "Commodities", 210.0, 0.008),
    ("TLT", "Rates", 94.0, 0.011),
    ("EEM", "Emerging", 42.0, 0.012),
)


def generate_demo_raw_frames(
    *,
    n_days: int = 360,
    seed: int = 20260101,
    end_date: dt.date | None = None,
) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    """Generate realistic multi-sector OHLCV bars with regime volatility and subtle dynamics."""
    rng = np.random.default_rng(seed)
    ref_end = end_date or dt.date(2026, 10, 30)
    bdays = pd.bdate_range(end=ref_end, periods=n_days)
    dates = [d.date() for d in bdays]

    # Common market factor + regime volatility multiplier
    market_shock = rng.normal(0.00035, 0.0085, size=n_days)
    vol_regime = np.ones(n_days, dtype=np.float64)
    for t in range(1, n_days):
        vol_regime[t] = 0.85 * vol_regime[t - 1] + 0.15 * (1.0 + 3.0 * abs(market_shock[t - 1]) / 0.01)

    raw_frames: dict[str, pd.DataFrame] = {}
    sector_map: dict[str, str] = {}

    for idx, (symbol, sector, start_price, base_vol) in enumerate(DEMO_UNIVERSE):
        sector_map[symbol] = sector
        beta = 0.75 + 0.35 * ((idx % 4) / 3.0)
        price = float(start_price)
        closes = np.empty(n_days, dtype=np.float64)
        opens = np.empty(n_days, dtype=np.float64)
        highs = np.empty(n_days, dtype=np.float64)
        lows = np.empty(n_days, dtype=np.float64)
        volumes = np.empty(n_days, dtype=np.float64)

        recent_rets = np.zeros(n_days, dtype=np.float64)
        ma20_buf: list[float] = []

        for t in range(n_days):
            idio = rng.normal(0.0, base_vol * vol_regime[t])
            # Mild compression-breakout continuation embedded so seed hypotheses have realistic signal structure
            carry = 0.0
            if t >= 20:
                ma20 = float(np.mean(ma20_buf[-20:]))
                recent_vol_5 = float(np.mean(np.abs(recent_rets[t - 5 : t])))
                if price > ma20 and recent_vol_5 < base_vol * 0.85 and recent_rets[t - 1] > 0.004:
                    carry = 0.0028

            gap = rng.normal(0.0, base_vol * 0.35)
            open_p = max(1.0, price * (1.0 + gap))
            intraday_r = beta * market_shock[t] + idio + carry
            close_p = max(1.0, open_p * (1.0 + intraday_r))

            wick_up = abs(rng.normal(0.0, base_vol * 0.45))
            wick_dn = abs(rng.normal(0.0, base_vol * 0.45))
            high_p = max(open_p, close_p) * (1.0 + wick_up)
            low_p = max(0.5, min(open_p, close_p) * (1.0 - wick_dn))

            vol_spike = 1.0 + 4.0 * abs(intraday_r) / max(base_vol, 1e-4)
            base_shares = (18_000_000.0 / max(start_price, 10.0)) * (1.0 + 0.25 * (idx % 3))
            volume = max(10_000.0, base_shares * vol_spike * rng.lognormal(0.0, 0.25))

            opens[t] = round(open_p, 4)
            highs[t] = round(high_p, 4)
            lows[t] = round(low_p, 4)
            closes[t] = round(close_p, 4)
            volumes[t] = round(volume, 2)
            recent_rets[t] = (close_p / price) - 1.0
            price = close_p
            ma20_buf.append(price)

        raw_frames[symbol] = pd.DataFrame(
            {
                "trade_date": dates,
                "open": opens,
                "high": highs,
                "low": lows,
                "close": closes,
                "volume": volumes,
            }
        )

    return raw_frames, sector_map


def load_demo_dataset(config: LoaderConfig | None = None) -> LoadedDiscoveryDataset:
    cfg = config or LoaderConfig(source="demo", max_assets=16, max_days=240, warmup_days=60)
    raw_frames, sector_map = generate_demo_raw_frames(
        n_days=cfg.warmup_days + cfg.max_days + 20,
        end_date=cfg.end_date,
    )
    if cfg.symbols:
        wanted = {s.upper() for s in cfg.symbols}
        filtered = {k: v for k, v in raw_frames.items() if k in wanted}
        if filtered:
            raw_frames = filtered
    return build_dataset_from_raw_frames(
        raw_frames,
        cfg,
        source_meta={
            "source": "demo",
            "description": "Deterministic multi-sector synthetic OHLCV dataset (offline-ready)",
        },
        sector_map=sector_map,
    )
