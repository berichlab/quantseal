"""Runtime services: shadow ladder tracking, scheduling, and notifications."""
from __future__ import annotations

from quantseal.runtime.notifier import NotificationConfig, dispatch_notification
from quantseal.runtime.scheduler import QuantSealScheduler, get_scheduler
from quantseal.runtime.shadow_service import (
    campaigns_root,
    enroll_strategy_to_shadow,
    ensure_demo_seeded,
    index_campaign_state,
    load_campaign_state_file,
    recompute_shadow_strategy,
    record_shadow_observation,
)

__all__ = [
    "NotificationConfig",
    "QuantSealScheduler",
    "campaigns_root",
    "dispatch_notification",
    "ensure_demo_seeded",
    "enroll_strategy_to_shadow",
    "get_scheduler",
    "index_campaign_state",
    "load_campaign_state_file",
    "record_shadow_observation",
    "recompute_shadow_strategy",
]
