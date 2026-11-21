"""Market-agnostic dataset loaders, observable feature normalization, and frozen snapshots."""
from __future__ import annotations

from quantseal.data.base import (
    AVAILABILITY_CONVENTION,
    AVAILABILITY_DISCLAIMER,
    CONTAMINATED_HISTORICAL_STATE,
    CORE_FEATURE_UNITS,
    CORE_OBSERVABLE_COLUMNS,
    LoadedDiscoveryDataset,
    LoaderConfig,
    build_dataset_from_raw_frames,
    compute_dataset_hash,
    load_frozen_dataset_snapshot,
    save_frozen_dataset_snapshot,
)
from quantseal.data.csv_source import load_csv_directory_dataset
from quantseal.data.market_sources import (
    load_binance_spot_dataset,
    load_dataset_by_source,
    load_yahoo_dataset,
)
from quantseal.data.synthetic import load_demo_dataset

__all__ = [
    "AVAILABILITY_CONVENTION",
    "AVAILABILITY_DISCLAIMER",
    "CONTAMINATED_HISTORICAL_STATE",
    "CORE_FEATURE_UNITS",
    "CORE_OBSERVABLE_COLUMNS",
    "LoadedDiscoveryDataset",
    "LoaderConfig",
    "build_dataset_from_raw_frames",
    "compute_dataset_hash",
    "load_binance_spot_dataset",
    "load_csv_directory_dataset",
    "load_dataset_by_source",
    "load_demo_dataset",
    "load_frozen_dataset_snapshot",
    "load_yahoo_dataset",
    "save_frozen_dataset_snapshot",
]
