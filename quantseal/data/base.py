"""Market-agnostic dataset normalization, NaN preservation, and SHA-256 frozen snapshots.

Core invariants:
1. Missing values and non-finite numbers (+/-inf) are NEVER coerced to 0; they
   remain NaN so strategies cannot silently hallucinate zero volume or zero flow.
2. Conservative availability convention: daily bar features observed at close t
   are strictly executed at the next market session open (t + 1).
3. Universe selection relies strictly on the warmup window (trade_date <= warmup_end)
   prior to the evaluation calendar — zero forward survivorship peeking.
4. `data_hash` hashes exact normalized floats, date ordering, NaN masks, and
   temporal split boundaries; frozen snapshots verify SHA-256 integrity on reload.
"""
from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from quantseal.core.split import temporal_boundaries

CONTAMINATED_HISTORICAL_STATE = "contaminated_historical"
AVAILABILITY_CONVENTION = "next_session_open_conservative"
AVAILABILITY_DISCLAIMER = (
    "Historical OHLCV datasets without point-in-time revision timestamps are treated "
    "under the conservative convention 'signals formed at close t execute at next "
    "market session open t+1'. All historical backtest partitions are explicitly "
    "labeled contaminated_historical and never advertised as live forward proof."
)

CORE_OBSERVABLE_COLUMNS: tuple[str, ...] = (
    "open",
    "high",
    "low",
    "close",
    "volume",
    "turnover",
    "ret_1d",
    "overnight_ret",
    "intraday_ret",
    "range_pct",
    "close_pos_in_range",
)

CORE_FEATURE_UNITS: dict[str, str] = {
    "open": "price",
    "high": "price",
    "low": "price",
    "close": "price",
    "volume": "units",
    "turnover": "notional",
    "ret_1d": "pct",
    "overnight_ret": "pct",
    "intraday_ret": "pct",
    "range_pct": "pct",
    "close_pos_in_range": "ratio_0_1",
}


def coerce_iso_date(val: dt.date | dt.datetime | str | None) -> dt.date | None:
    if val is None or val == "":
        return None
    if isinstance(val, dt.datetime):
        return val.date()
    if isinstance(val, dt.date):
        return val
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return None
        return dt.date.fromisoformat(s[:10])
    raise ValueError(f"Unable to parse date value: {val!r}")


@dataclass(frozen=True)
class LoaderConfig:
    source: str = "demo"
    symbols: tuple[str, ...] = ()
    max_assets: int = 30
    max_days: int = 240
    warmup_days: int = 60
    end_date: dt.date | None = None
    min_warmup_bars: int = 20
    csv_dir: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "symbols": list(self.symbols),
            "max_assets": int(self.max_assets),
            "max_days": int(self.max_days),
            "warmup_days": int(self.warmup_days),
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "min_warmup_bars": int(self.min_warmup_bars),
            "csv_dir": self.csv_dir,
        }


@dataclass
class LoadedDiscoveryDataset:
    frames: dict[str, pd.DataFrame]
    calendar_dates: list[dt.date]
    warmup_end: dt.date
    discovery_start: dt.date
    discovery_end: dt.date
    validation_start: dt.date
    validation_end: dt.date
    sealed_start: dt.date | None
    sealed_end: dt.date | None
    observable_columns: tuple[str, ...]
    feature_units: dict[str, str]
    available_columns: set[str]
    coverage_report: dict[str, Any]
    data_hash: str
    source_meta: dict[str, Any] = field(default_factory=dict)
    sector_map: dict[str, str] = field(default_factory=dict)


def _clean_float_series(series: pd.Series) -> pd.Series:
    arr = pd.to_numeric(series, errors="coerce").astype("float64")
    arr = arr.where(np.isfinite(arr), np.nan)
    return arr


def normalize_symbol_frame(
    raw_df: pd.DataFrame,
    *,
    extra_columns: tuple[str, ...] = (),
) -> pd.DataFrame:
    """Normalize raw OHLCV (+ optional custom features) while strictly preserving NaNs."""
    if raw_df is None or raw_df.empty:
        return pd.DataFrame(columns=["trade_date", *CORE_OBSERVABLE_COLUMNS, *extra_columns])

    df = raw_df.copy()
    rename_map = {}
    for col in df.columns:
        low = str(col).strip().lower()
        if low in ("date", "timestamp", "datetime", "trade_date"):
            rename_map[col] = "trade_date"
        elif low in ("open", "high", "low", "close", "volume", "turnover"):
            rename_map[col] = low
    df = df.rename(columns=rename_map)

    if "trade_date" not in df.columns:
        raise ValueError("Input DataFrame must contain a 'trade_date' (or 'date') column")

    df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce").dt.date
    df = df[df["trade_date"].notna()].copy()
    df = df.sort_values("trade_date").drop_duplicates(subset=["trade_date"], keep="last").reset_index(drop=True)

    for col in ("open", "high", "low", "close", "volume"):
        if col in df.columns:
            df[col] = _clean_float_series(df[col])
        else:
            df[col] = np.nan

    # Exclude non-positive prices (never fabricate 0)
    for col in ("open", "high", "low", "close"):
        df[col] = df[col].where(df[col] > 0.0, np.nan)
    df["volume"] = df["volume"].where(df["volume"] >= 0.0, np.nan)

    if "turnover" in df.columns:
        df["turnover"] = _clean_float_series(df["turnover"]).where(lambda s: s >= 0.0, np.nan)
    else:
        df["turnover"] = df["close"] * df["volume"]

    prev_close = df["close"].shift(1)
    df["ret_1d"] = ((df["close"] / prev_close) - 1.0) * 100.0
    df["overnight_ret"] = ((df["open"] / prev_close) - 1.0) * 100.0
    df["intraday_ret"] = ((df["close"] / df["open"]) - 1.0) * 100.0
    df["range_pct"] = ((df["high"] - df["low"]) / df["open"]) * 100.0
    span = df["high"] - df["low"]
    df["close_pos_in_range"] = np.where(
        span > 0.0,
        (df["close"] - df["low"]) / span,
        np.nan,
    )

    keep_cols = ["trade_date", *CORE_OBSERVABLE_COLUMNS]
    for col in extra_columns:
        if col not in keep_cols:
            if col in df.columns:
                df[col] = _clean_float_series(df[col])
            else:
                df[col] = np.nan
            keep_cols.append(col)

    for col in keep_cols[1:]:
        df[col] = df[col].where(np.isfinite(df[col]), np.nan)

    return df[keep_cols].reset_index(drop=True)


def compute_dataset_hash(
    frames: dict[str, pd.DataFrame],
    *,
    observable_columns: tuple[str, ...],
    warmup_end: dt.date,
    discovery_start: dt.date,
    discovery_end: dt.date,
    validation_start: dt.date,
    validation_end: dt.date,
    sealed_start: dt.date | None,
) -> str:
    """Deterministic SHA-256 fingerprint across normalized values, date order, and NaN masks."""
    hasher = hashlib.sha256()
    meta = {
        "observable_columns": list(observable_columns),
        "warmup_end": warmup_end.isoformat(),
        "discovery_start": discovery_start.isoformat(),
        "discovery_end": discovery_end.isoformat(),
        "validation_start": validation_start.isoformat(),
        "validation_end": validation_end.isoformat(),
        "sealed_start": sealed_start.isoformat() if sealed_start else None,
    }
    hasher.update(json.dumps(meta, sort_keys=True).encode("utf-8"))
    for symbol in sorted(frames.keys()):
        df = frames[symbol]
        hasher.update(f"|SYM:{symbol}|N:{len(df)}|".encode())
        if df.empty:
            continue
        date_str = ",".join(d.isoformat() for d in df["trade_date"])
        hasher.update(date_str.encode("utf-8"))
        for col in observable_columns:
            if col not in df.columns:
                hasher.update(f"|{col}:ABSENT".encode())
                continue
            arr = pd.to_numeric(df[col], errors="coerce").to_numpy(dtype=np.float64)
            nan_mask = np.isnan(arr)
            rounded = np.where(nan_mask, 0.0, np.round(arr, 6))
            hasher.update(f"|{col}:".encode())
            hasher.update(nan_mask.tobytes())
            hasher.update(rounded.tobytes())
    return hasher.hexdigest()[:16]


def build_dataset_from_raw_frames(
    raw_frames: dict[str, pd.DataFrame],
    config: LoaderConfig,
    *,
    source_meta: dict[str, Any] | None = None,
    sector_map: dict[str, str] | None = None,
    extra_feature_units: dict[str, str] | None = None,
) -> LoadedDiscoveryDataset:
    """Build a temporally isolated, warmup-screened LoadedDiscoveryDataset."""
    if not raw_frames:
        raise ValueError("No symbol frames provided to build_dataset_from_raw_frames")

    # Discover optional extra numeric columns present across inputs
    reserved = {"trade_date", "date", "timestamp", "datetime", "symbol", *CORE_OBSERVABLE_COLUMNS}
    extra_cols_set: set[str] = set()
    for df in raw_frames.values():
        if df is None or df.empty:
            continue
        for c in df.columns:
            cl = str(c).strip()
            if cl.lower() not in reserved and pd.api.types.is_numeric_dtype(df[c]):
                extra_cols_set.add(cl)
    extra_cols = tuple(sorted(extra_cols_set))
    observable_columns = CORE_OBSERVABLE_COLUMNS + extra_cols
    feature_units = dict(CORE_FEATURE_UNITS)
    for c in extra_cols:
        feature_units[c] = (extra_feature_units or {}).get(c, "custom_numeric")

    normalized: dict[str, pd.DataFrame] = {}
    all_dates_set: set[dt.date] = set()
    end_limit = config.end_date

    for sym, raw in sorted(raw_frames.items()):
        norm = normalize_symbol_frame(raw, extra_columns=extra_cols)
        if end_limit is not None:
            norm = norm[norm["trade_date"] <= end_limit].reset_index(drop=True)
        if not norm.empty:
            normalized[sym.upper()] = norm
            all_dates_set.update(norm["trade_date"].tolist())

    all_dates = sorted(all_dates_set)
    min_needed = config.warmup_days + 15
    if len(all_dates) < min_needed:
        raise ValueError(
            f"Insufficient market calendar: {len(all_dates)} trading days available, "
            f"need at least {min_needed} (warmup_days={config.warmup_days} + eval >= 15)."
        )

    total_window = config.warmup_days + config.max_days
    if len(all_dates) > total_window:
        selected_dates = all_dates[-total_window:]
    else:
        selected_dates = all_dates

    window_start = selected_dates[0]
    warmup_end = selected_dates[config.warmup_days - 1]
    eval_dates = selected_dates[config.warmup_days:]
    if len(eval_dates) < 10:
        raise ValueError(f"Evaluation calendar too short ({len(eval_dates)} days)")

    bounds = temporal_boundaries(eval_dates)
    val_start = bounds["validation_start"]
    sealed_start = bounds["sealed_start"]
    if val_start is None:
        raise ValueError("Unable to compute validation_start from evaluation calendar")

    disc_dates = [d for d in eval_dates if d < val_start]
    if sealed_start is not None:
        val_dates = [d for d in eval_dates if val_start <= d < sealed_start]
        sealed_dates = [d for d in eval_dates if d >= sealed_start]
    else:
        val_dates = [d for d in eval_dates if d >= val_start]
        sealed_dates = []

    if not disc_dates or not val_dates:
        raise ValueError("Discovery or validation partition is empty")

    # Universe eligibility strictly uses warmup window (trade_date <= warmup_end) — zero lookahead.
    scored_assets: list[tuple[float, str, pd.DataFrame]] = []
    for sym, df in sorted(normalized.items()):
        sliced = df[
            (df["trade_date"] >= window_start) & (df["trade_date"] <= eval_dates[-1])
        ].reset_index(drop=True)
        warmup_slice = sliced[sliced["trade_date"] <= warmup_end]
        valid_close = warmup_slice["close"].notna().sum()
        if valid_close < min(config.min_warmup_bars, config.warmup_days):
            continue
        med_turnover = float(np.nanmedian(warmup_slice["turnover"].to_numpy(dtype=np.float64)))
        if not np.isfinite(med_turnover):
            med_turnover = 0.0
        scored_assets.append((med_turnover, sym, sliced))

    if not scored_assets:
        raise ValueError("No assets satisfied warmup eligibility criteria")

    scored_assets.sort(key=lambda item: (-item[0], item[1]))
    chosen = scored_assets[: config.max_assets]
    frames = {sym: df for _, sym, df in chosen}

    # Compute column coverage on discovery + validation
    available_columns: set[str] = set()
    coverage: dict[str, dict[str, float]] = {}
    for col in observable_columns:
        disc_tot = disc_ok = val_tot = val_ok = 0
        for df in frames.values():
            dmask = (df["trade_date"] >= disc_dates[0]) & (df["trade_date"] <= disc_dates[-1])
            vmask = (df["trade_date"] >= val_dates[0]) & (df["trade_date"] <= val_dates[-1])
            disc_tot += int(dmask.sum())
            disc_ok += int(df.loc[dmask, col].notna().sum()) if col in df.columns else 0
            val_tot += int(vmask.sum())
            val_ok += int(df.loc[vmask, col].notna().sum()) if col in df.columns else 0
        d_cov = round(disc_ok / disc_tot, 4) if disc_tot > 0 else 0.0
        v_cov = round(val_ok / val_tot, 4) if val_tot > 0 else 0.0
        coverage[col] = {"discovery": d_cov, "validation": v_cov}
        if d_cov > 0.0:
            available_columns.add(col)

    data_hash = compute_dataset_hash(
        frames,
        observable_columns=observable_columns,
        warmup_end=warmup_end,
        discovery_start=disc_dates[0],
        discovery_end=disc_dates[-1],
        validation_start=val_dates[0],
        validation_end=val_dates[-1],
        sealed_start=sealed_dates[0] if sealed_dates else None,
    )

    return LoadedDiscoveryDataset(
        frames=frames,
        calendar_dates=eval_dates,
        warmup_end=warmup_end,
        discovery_start=disc_dates[0],
        discovery_end=disc_dates[-1],
        validation_start=val_dates[0],
        validation_end=val_dates[-1],
        sealed_start=sealed_dates[0] if sealed_dates else None,
        sealed_end=sealed_dates[-1] if sealed_dates else None,
        observable_columns=observable_columns,
        feature_units=feature_units,
        available_columns=available_columns,
        coverage_report={
            "asset_count": len(frames),
            "symbols": sorted(frames.keys()),
            "warmup_days": config.warmup_days,
            "discovery_days": len(disc_dates),
            "validation_days": len(val_dates),
            "sealed_days": len(sealed_dates),
            "column_coverage": coverage,
            "blind_status": CONTAMINATED_HISTORICAL_STATE,
            "availability_convention": AVAILABILITY_CONVENTION,
            "availability_disclaimer": AVAILABILITY_DISCLAIMER,
        },
        data_hash=data_hash,
        source_meta=dict(source_meta or {"source": config.source}),
        sector_map={k.upper(): v for k, v in (sector_map or {}).items()},
    )


def save_frozen_dataset_snapshot(dataset: LoadedDiscoveryDataset, target_path: Path) -> Path:
    """Atomically persist a gzipped frozen dataset snapshot for immutable campaign resumes."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    serialized_frames: dict[str, list[dict[str, Any]]] = {}
    for sym, df in sorted(dataset.frames.items()):
        rows: list[dict[str, Any]] = []
        for rec in df.to_dict(orient="records"):
            clean_rec: dict[str, Any] = {}
            for k, v in rec.items():
                if k == "trade_date":
                    clean_rec[k] = v.isoformat() if isinstance(v, dt.date) else str(v)
                elif v is None or (isinstance(v, float) and not np.isfinite(v)):
                    clean_rec[k] = None
                else:
                    clean_rec[k] = float(v)
            rows.append(clean_rec)
        serialized_frames[sym] = rows

    payload = {
        "data_hash": dataset.data_hash,
        "calendar_dates": [d.isoformat() for d in dataset.calendar_dates],
        "warmup_end": dataset.warmup_end.isoformat(),
        "discovery_start": dataset.discovery_start.isoformat(),
        "discovery_end": dataset.discovery_end.isoformat(),
        "validation_start": dataset.validation_start.isoformat(),
        "validation_end": dataset.validation_end.isoformat(),
        "sealed_start": dataset.sealed_start.isoformat() if dataset.sealed_start else None,
        "sealed_end": dataset.sealed_end.isoformat() if dataset.sealed_end else None,
        "observable_columns": list(dataset.observable_columns),
        "feature_units": dataset.feature_units,
        "available_columns": sorted(dataset.available_columns),
        "coverage_report": dataset.coverage_report,
        "source_meta": dataset.source_meta,
        "sector_map": dataset.sector_map,
        "frames": serialized_frames,
    }

    raw_bytes = gzip.compress(json.dumps(payload, sort_keys=True).encode("utf-8"))
    fd, tmp_name = tempfile.mkstemp(prefix=".snap_", suffix=".json.gz", dir=str(target_path.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(raw_bytes)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, target_path)
    except Exception:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise
    return target_path


def load_frozen_dataset_snapshot(snapshot_path: Path) -> LoadedDiscoveryDataset:
    """Restore a frozen snapshot and verify its recomputed SHA-256 data_hash."""
    raw = gzip.decompress(snapshot_path.read_bytes())
    payload = json.loads(raw.decode("utf-8"))

    observable_columns = tuple(payload["observable_columns"])
    frames: dict[str, pd.DataFrame] = {}
    for sym, rows in payload["frames"].items():
        df = pd.DataFrame(rows)
        if not df.empty:
            df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
            for col in observable_columns:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")
        frames[sym] = df

    warmup_end = dt.date.fromisoformat(payload["warmup_end"])
    disc_start = dt.date.fromisoformat(payload["discovery_start"])
    disc_end = dt.date.fromisoformat(payload["discovery_end"])
    val_start = dt.date.fromisoformat(payload["validation_start"])
    val_end = dt.date.fromisoformat(payload["validation_end"])
    sealed_start = dt.date.fromisoformat(payload["sealed_start"]) if payload.get("sealed_start") else None
    sealed_end = dt.date.fromisoformat(payload["sealed_end"]) if payload.get("sealed_end") else None

    recomputed_hash = compute_dataset_hash(
        frames,
        observable_columns=observable_columns,
        warmup_end=warmup_end,
        discovery_start=disc_start,
        discovery_end=disc_end,
        validation_start=val_start,
        validation_end=val_end,
        sealed_start=sealed_start,
    )
    if recomputed_hash != payload["data_hash"]:
        raise ValueError(
            f"Frozen snapshot integrity mismatch: expected {payload['data_hash']}, got {recomputed_hash}"
        )

    return LoadedDiscoveryDataset(
        frames=frames,
        calendar_dates=[dt.date.fromisoformat(d) for d in payload["calendar_dates"]],
        warmup_end=warmup_end,
        discovery_start=disc_start,
        discovery_end=disc_end,
        validation_start=val_start,
        validation_end=val_end,
        sealed_start=sealed_start,
        sealed_end=sealed_end,
        observable_columns=observable_columns,
        feature_units=dict(payload["feature_units"]),
        available_columns=set(payload["available_columns"]),
        coverage_report=dict(payload["coverage_report"]),
        data_hash=recomputed_hash,
        source_meta=dict(payload.get("source_meta") or {}),
        sector_map=dict(payload.get("sector_map") or {}),
    )
