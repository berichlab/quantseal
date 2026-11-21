"""Fixed temporal isolation: discovery (60%), validation (20%), sealed_test (20%).

Calendar boundaries are computed deterministically from market trading dates
before any strategy screening occurs. Historical data is always explicitly
labeled as `contaminated_historical` rather than misrepresented as pristine
prospective evidence.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from typing import Any

import pandas as pd

PROTOCOL = "discovery_validation_sealed_v2"


def temporal_boundaries(dates: Any) -> dict[str, dt.date | None]:
    """Return deterministic validation and sealed_test start dates (60/20/20 split)."""
    ordered = sorted({pd.Timestamp(d).date() for d in dates})
    if len(ordered) < 2:
        return {"validation_start": None, "sealed_start": None}
    discovery_count = max(1, int(len(ordered) * 0.6))
    discovery_count = min(discovery_count, len(ordered) - 1)
    validation_start = ordered[discovery_count]
    if len(ordered) < 3:
        return {"validation_start": validation_start, "sealed_start": None}
    sealed_index = max(discovery_count + 1, int(len(ordered) * 0.8))
    sealed_index = min(sealed_index, len(ordered) - 1)
    return {"validation_start": validation_start, "sealed_start": ordered[sealed_index]}


def calendar_manifest(frames: dict[str, pd.DataFrame]) -> dict[str, Any]:
    """Build immutable calendar boundaries before running any candidate evaluation."""
    dates = sorted(
        {
            pd.Timestamp(day).date()
            for frame in frames.values()
            if frame is not None and not frame.empty and "trade_date" in frame
            for day in frame["trade_date"].unique()
        }
    )
    boundaries = temporal_boundaries(dates)
    result: dict[str, Any] = {
        key: value.isoformat() if value else None for key, value in boundaries.items()
    }
    result.update(
        calendar_start=dates[0].isoformat() if dates else None,
        calendar_end=dates[-1].isoformat() if dates else None,
        protocol=PROTOCOL,
        blind_status="contaminated_historical",
    )
    result["cohort_id"] = hashlib.sha256(
        json.dumps(result, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return result


def manifest_boundaries(manifest: dict[str, Any]) -> dict[str, dt.date | None]:
    return {
        key: pd.Timestamp(manifest[key]).date() if manifest.get(key) else None
        for key in ("validation_start", "sealed_start")
    }


def select_frames(
    frames: dict[str, pd.DataFrame],
    manifest: dict[str, Any],
    *,
    discovery_only: bool = False,
    include_sealed: bool = False,
    keep_history: bool = False,
) -> dict[str, pd.DataFrame]:
    """Physically exclude withheld rows before probes, feature generation, or simulation."""
    cutoff = manifest.get("validation_start" if discovery_only else "sealed_start")
    out: dict[str, pd.DataFrame] = {}
    for sid, frame in frames.items():
        if frame is None or frame.empty:
            continue
        dates = pd.to_datetime(frame["trade_date"]).dt.date
        mask = dates.notna()
        if manifest.get("calendar_start") and not keep_history:
            mask &= dates >= pd.Timestamp(manifest["calendar_start"]).date()
        if manifest.get("calendar_end"):
            mask &= dates <= pd.Timestamp(manifest["calendar_end"]).date()
        if not include_sealed and cutoff:
            mask &= dates < pd.Timestamp(cutoff).date()
        elif not include_sealed and not cutoff:
            mask &= False  # Fail closed: insufficient calendar never exposes holdout.
        out[sid] = frame.loc[mask].copy()
    return out


def partition(day: dt.date, boundaries: dict[str, dt.date | None]) -> str:
    sealed = boundaries.get("sealed_start")
    validation = boundaries.get("validation_start")
    if sealed is not None and day >= sealed:
        return "sealed_test"
    if validation is not None and day >= validation:
        return "validation"
    return "discovery"


def window_fits(start: dt.date, end: dt.date, boundaries: dict[str, dt.date | None]) -> bool:
    return partition(start, boundaries) == partition(end, boundaries)
