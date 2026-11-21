"""Transaction cost models with price-tiered low-liquidity slippage multipliers.

Pure functions with zero database dependencies. Every trade return is decomposed
explicitly into:
    net_return_pct = gross_return_pct - fee_pct - tax_pct - slippage_pct

Includes presets for US equities/ETFs, crypto spot markets, Taiwan equities,
and custom basis-point configurations so backtests never assume zero friction.
"""
from __future__ import annotations

from dataclasses import dataclass

DEFAULT_PRICE_TIERS: tuple[tuple[float, float], ...] = (
    (5.0, 2.0),   # Low-priced / thin-book assets (< 5 currency units): 2x slippage
    (20.0, 1.5),  # Mid-low priced assets (< 20): 1.5x slippage
)
DEFAULT_TIER_MULTIPLIER = 1.0


@dataclass(frozen=True)
class CostModel:
    """Market-agnostic round-trip execution cost specification."""

    name: str
    fee_bps_per_side: float          # Commission per side in bps (1 bp = 0.01%)
    sell_tax_bps: float              # Transaction tax on exit in bps
    slippage_bps_per_side: float     # Base slippage per side in bps
    price_tiers: tuple[tuple[float, float], ...] = DEFAULT_PRICE_TIERS
    default_tier_multiplier: float = DEFAULT_TIER_MULTIPLIER
    currency: str = "USD"

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "fee_bps_per_side": float(self.fee_bps_per_side),
            "sell_tax_bps": float(self.sell_tax_bps),
            "slippage_bps_per_side": float(self.slippage_bps_per_side),
            "price_tiers": [[float(t), float(m)] for t, m in self.price_tiers],
            "default_tier_multiplier": float(self.default_tier_multiplier),
            "currency": self.currency,
        }


MARKET_COST_PRESETS: dict[str, CostModel] = {
    "us_equities": CostModel(
        name="us_equities",
        fee_bps_per_side=1.0,        # ~1 bp effective commission / regulatory fees
        sell_tax_bps=0.28,           # SEC / FINRA activity fee approximation
        slippage_bps_per_side=8.0,   # 8 bps/side base spread + market impact
        price_tiers=((5.0, 2.0), (20.0, 1.5)),
        currency="USD",
    ),
    "crypto_spot": CostModel(
        name="crypto_spot",
        fee_bps_per_side=10.0,       # 10 bps/side taker fee (0.10%)
        sell_tax_bps=0.0,
        slippage_bps_per_side=10.0,  # 10 bps/side slippage
        price_tiers=((0.10, 2.0), (1.0, 1.5)),
        currency="USDT",
    ),
    "tw_equities": CostModel(
        name="tw_equities",
        fee_bps_per_side=3.99,       # 0.1425% * 0.28 typical retail discount
        sell_tax_bps=30.0,           # 0.30% securities transaction tax on sell
        slippage_bps_per_side=15.0,  # 15 bps/side base slippage
        price_tiers=((10.0, 2.0), (50.0, 1.5)),
        currency="TWD",
    ),
    "custom": CostModel(
        name="custom",
        fee_bps_per_side=5.0,
        sell_tax_bps=0.0,
        slippage_bps_per_side=10.0,
        price_tiers=(),
        currency="USD",
    ),
}


def get_cost_model(preset_or_model: str | CostModel | None = None) -> CostModel:
    if isinstance(preset_or_model, CostModel):
        return preset_or_model
    key = str(preset_or_model or "us_equities").strip().lower()
    if key not in MARKET_COST_PRESETS:
        raise ValueError(
            f"Unknown market cost preset '{key}'. Valid presets: {sorted(MARKET_COST_PRESETS)}"
        )
    return MARKET_COST_PRESETS[key]


def slippage_multiplier(
    price: float | None,
    price_tiers: tuple[tuple[float, float], ...] = DEFAULT_PRICE_TIERS,
    default: float = DEFAULT_TIER_MULTIPLIER,
) -> float:
    """Return low-liquidity slippage multiplier based on asset price tier."""
    if price is None or price <= 0:
        return default
    for threshold, multiplier in price_tiers:
        if price < threshold:
            return multiplier
    return default


@dataclass(frozen=True)
class CostBreakdown:
    """Round-trip transaction cost decomposition expressed in percentage points."""

    fee_pct: float
    tax_pct: float
    slippage_pct: float
    slippage_multiplier: float
    total_pct: float


def cost_breakdown(
    *,
    model: str | CostModel = "us_equities",
    price: float | None = None,
    slippage_multiplier_override: float | None = None,
    cost_stress_multiplier: float = 1.0,
) -> CostBreakdown:
    """Compute explicit fee, tax, and price-tiered slippage in percentage points."""
    cm = get_cost_model(model)
    mult = (
        float(slippage_multiplier_override)
        if slippage_multiplier_override is not None
        else slippage_multiplier(price, cm.price_tiers, cm.default_tier_multiplier)
    )
    fee = (cm.fee_bps_per_side / 10000.0) * 2.0
    tax = cm.sell_tax_bps / 10000.0
    slippage = (cm.slippage_bps_per_side / 10000.0) * 2.0 * mult * float(cost_stress_multiplier)
    total = fee + tax + slippage
    return CostBreakdown(
        fee_pct=round(fee * 100.0, 4),
        tax_pct=round(tax * 100.0, 4),
        slippage_pct=round(slippage * 100.0, 4),
        slippage_multiplier=round(mult, 4),
        total_pct=round(total * 100.0, 4),
    )


def round_trip_cost_pct(
    *,
    model: str | CostModel = "us_equities",
    price: float | None = None,
    cost_stress_multiplier: float = 1.0,
) -> float:
    """Total round-trip cost in percentage points (e.g. 0.1828 = 0.1828%)."""
    return cost_breakdown(
        model=model,
        price=price,
        cost_stress_multiplier=cost_stress_multiplier,
    ).total_pct


def apply_cost(
    gross_pct: float,
    *,
    model: str | CostModel = "us_equities",
    price: float | None = None,
    cost_stress_multiplier: float = 1.0,
) -> float:
    """Return net return percentage points after deducting round-trip friction."""
    return round(
        float(gross_pct)
        - round_trip_cost_pct(
            model=model,
            price=price,
            cost_stress_multiplier=cost_stress_multiplier,
        ),
        4,
    )
