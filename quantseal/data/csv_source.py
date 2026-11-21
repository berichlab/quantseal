"""Local CSV and Parquet dataset loader supporting arbitrary custom numeric columns."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from quantseal.data.base import LoadedDiscoveryDataset, LoaderConfig, build_dataset_from_raw_frames


def load_csv_directory_dataset(
    csv_dir: str | Path,
    config: LoaderConfig | None = None,
) -> LoadedDiscoveryDataset:
    """Load per-symbol CSV/Parquet files (or a multi-symbol file with a 'symbol' column)."""
    root = Path(csv_dir).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"Dataset directory not found: {root}")

    raw_frames: dict[str, pd.DataFrame] = {}
    sector_map: dict[str, str] = {}

    files = sorted(
        list(root.glob("*.csv")) + list(root.glob("*.parquet"))
    )
    if not files:
        raise ValueError(f"No .csv or .parquet files found in {root}")

    for fpath in files:
        if fpath.suffix.lower() == ".parquet":
            df = pd.read_parquet(fpath)
        else:
            df = pd.read_csv(fpath)
        if df.empty:
            continue

        lower_cols = {c.lower(): c for c in df.columns}
        if "symbol" in lower_cols:
            sym_col = lower_cols["symbol"]
            sec_col = lower_cols.get("sector") or lower_cols.get("industry")
            for sym_val, grp in df.groupby(sym_col):
                sym = str(sym_val).strip().upper()
                if not sym:
                    continue
                if sec_col and grp[sec_col].dropna().any():
                    sector_map[sym] = str(grp[sec_col].dropna().iloc[0]).strip()
                raw_frames[sym] = grp.drop(columns=[c for c in (sym_col, sec_col) if c and c in grp.columns])
        else:
            sym = fpath.stem.strip().upper()
            sec_col = lower_cols.get("sector") or lower_cols.get("industry")
            if sec_col and df[sec_col].dropna().any():
                sector_map[sym] = str(df[sec_col].dropna().iloc[0]).strip()
                df = df.drop(columns=[sec_col])
            raw_frames[sym] = df

    cfg = config or LoaderConfig(source="csv", csv_dir=str(root))
    if cfg.symbols:
        wanted = {s.upper() for s in cfg.symbols}
        raw_frames = {k: v for k, v in raw_frames.items() if k in wanted}

    return build_dataset_from_raw_frames(
        raw_frames,
        cfg,
        source_meta={"source": "csv", "directory": str(root)},
        sector_map=sector_map,
    )
