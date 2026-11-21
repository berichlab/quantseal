"""Public market data adapters: Yahoo Finance (Equities/ETFs) and Binance Spot (Crypto).

Both adapters use standard HTTP REST endpoints via `httpx` (zero API key needed)
so self-hosted Docker containers stay lightweight and fast.
"""
from __future__ import annotations

import datetime as dt
import logging
from typing import Any

import httpx
import pandas as pd

from quantseal.data.base import LoadedDiscoveryDataset, LoaderConfig, build_dataset_from_raw_frames
from quantseal.data.csv_source import load_csv_directory_dataset
from quantseal.data.synthetic import load_demo_dataset

logger = logging.getLogger(__name__)

DEFAULT_US_ETFS: tuple[str, ...] = (
    "SPY", "QQQ", "IWM", "XLK", "XLF", "XLE", "XLV", "XLI", "XLP", "XLY", "GLD", "TLT",
)

DEFAULT_CRYPTO_SYMBOLS: tuple[str, ...] = (
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOGEUSDT", "DOTUSDT",
)

_ETF_SECTORS: dict[str, str] = {
    "SPY": "Broad Market", "QQQ": "Technology", "IWM": "Small Cap",
    "XLK": "Technology", "XLF": "Financials", "XLE": "Energy",
    "XLV": "Healthcare", "XLI": "Industrials", "XLP": "Staples",
    "XLY": "Discretionary", "XLB": "Materials", "XLU": "Utilities",
    "GLD": "Commodities", "TLT": "Rates", "SMH": "Semiconductors",
}


def _fetch_yahoo_symbol_daily(
    client: httpx.Client,
    symbol: str,
    *,
    range_str: str = "2y",
) -> pd.DataFrame | None:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    resp = client.get(url, params={"interval": "1d", "range": range_str})
    resp.raise_for_status()
    payload = resp.json()
    results = (payload.get("chart") or {}).get("result") or []
    if not results:
        return None
    item = results[0]
    timestamps = item.get("timestamp") or []
    quote = ((item.get("indicators") or {}).get("quote") or [{}])[0]
    if not timestamps or not quote:
        return None

    dates = [dt.datetime.fromtimestamp(int(ts), tz=dt.UTC).date() for ts in timestamps]
    df = pd.DataFrame(
        {
            "trade_date": dates,
            "open": quote.get("open"),
            "high": quote.get("high"),
            "low": quote.get("low"),
            "close": quote.get("close"),
            "volume": quote.get("volume"),
        }
    )
    return df


def load_yahoo_dataset(config: LoaderConfig | None = None) -> LoadedDiscoveryDataset:
    """Fetch public daily OHLCV bars from Yahoo Finance chart API."""
    cfg = config or LoaderConfig(source="yahoo", symbols=DEFAULT_US_ETFS)
    symbols = cfg.symbols or DEFAULT_US_ETFS
    range_str = "5y" if (cfg.warmup_days + cfg.max_days) > 450 else "2y"

    raw_frames: dict[str, pd.DataFrame] = {}
    errors: dict[str, str] = {}
    headers = {"User-Agent": "QuantSeal/0.1 (+https://github.com/quantseal)"}
    with httpx.Client(timeout=15.0, headers=headers, follow_redirects=True) as client:
        for sym in symbols:
            try:
                df = _fetch_yahoo_symbol_daily(client, sym, range_str=range_str)
                if df is not None and not df.empty:
                    raw_frames[sym.upper()] = df
            except Exception as exc:
                errors[sym] = str(exc)
                logger.warning("Yahoo fetch failed for %s: %s", sym, exc)

    if not raw_frames:
        raise RuntimeError(f"Failed to fetch any symbols from Yahoo Finance: {errors}")

    return build_dataset_from_raw_frames(
        raw_frames,
        cfg,
        source_meta={"source": "yahoo", "fetch_errors": errors},
        sector_map={s: _ETF_SECTORS.get(s, "Equities") for s in raw_frames},
    )


def _fetch_binance_symbol_daily(
    client: httpx.Client,
    symbol: str,
    *,
    limit: int = 400,
) -> pd.DataFrame | None:
    url = "https://api.binance.com/api/v3/klines"
    resp = client.get(url, params={"symbol": symbol.upper(), "interval": "1d", "limit": min(1000, limit)})
    resp.raise_for_status()
    rows = resp.json()
    if not isinstance(rows, list) or not rows:
        return None
    records: list[dict[str, Any]] = []
    for k in rows:
        open_ms = int(k[0])
        records.append(
            {
                "trade_date": dt.datetime.fromtimestamp(open_ms / 1000.0, tz=dt.UTC).date(),
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
                "turnover": float(k[7]),
            }
        )
    return pd.DataFrame(records)


def load_binance_spot_dataset(config: LoaderConfig | None = None) -> LoadedDiscoveryDataset:
    """Fetch public daily spot OHLCV bars from Binance public REST API."""
    cfg = config or LoaderConfig(source="crypto", symbols=DEFAULT_CRYPTO_SYMBOLS)
    symbols = cfg.symbols or DEFAULT_CRYPTO_SYMBOLS
    limit = min(1000, cfg.warmup_days + cfg.max_days + 30)

    raw_frames: dict[str, pd.DataFrame] = {}
    errors: dict[str, str] = {}
    with httpx.Client(timeout=15.0) as client:
        for sym in symbols:
            try:
                df = _fetch_binance_symbol_daily(client, sym, limit=limit)
                if df is not None and not df.empty:
                    raw_frames[sym.upper()] = df
            except Exception as exc:
                errors[sym] = str(exc)
                logger.warning("Binance fetch failed for %s: %s", sym, exc)

    if not raw_frames:
        raise RuntimeError(f"Failed to fetch any symbols from Binance public API: {errors}")

    return build_dataset_from_raw_frames(
        raw_frames,
        cfg,
        source_meta={"source": "crypto", "provider": "binance_public_spot", "fetch_errors": errors},
        sector_map={s: "Crypto" for s in raw_frames},
    )


def load_dataset_by_source(config: LoaderConfig) -> LoadedDiscoveryDataset:
    """Dispatch loader by `config.source` (`demo`, `yahoo`, `crypto`, `csv`)."""
    src = str(config.source or "demo").strip().lower()
    if src == "demo":
        return load_demo_dataset(config)
    if src in ("yahoo", "us_equities", "equities"):
        return load_yahoo_dataset(config)
    if src in ("crypto", "binance", "crypto_spot"):
        return load_binance_spot_dataset(config)
    if src == "csv":
        if not config.csv_dir:
            raise ValueError("LoaderConfig.csv_dir is required when source='csv'")
        return load_csv_directory_dataset(config.csv_dir, config)
    raise ValueError(f"Unsupported dataset source '{src}'. Choose from: demo, yahoo, crypto, csv")
