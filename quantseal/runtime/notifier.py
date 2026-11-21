"""Notification dispatcher for Telegram Bot, Discord Webhook, and Generic JSON Webhook."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NotificationConfig:
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    discord_webhook_url: str = ""
    generic_webhook_url: str = ""

    def any_configured(self) -> bool:
        return bool(
            (self.telegram_bot_token.strip() and self.telegram_chat_id.strip())
            or self.discord_webhook_url.strip()
            or self.generic_webhook_url.strip()
        )


def dispatch_notification(
    title: str,
    message: str,
    config: NotificationConfig,
    *,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Send a concise alert to every configured notification channel."""
    results: dict[str, Any] = {"sent": [], "errors": {}}
    if not config.any_configured():
        results["status"] = "no_channels_configured"
        return results

    full_text = f"[QuantSeal] {title}\n{message}"

    with httpx.Client(timeout=10.0) as client:
        if config.telegram_bot_token.strip() and config.telegram_chat_id.strip():
            try:
                url = f"https://api.telegram.org/bot{config.telegram_bot_token.strip()}/sendMessage"
                resp = client.post(
                    url,
                    json={
                        "chat_id": config.telegram_chat_id.strip(),
                        "text": full_text,
                        "disable_web_page_preview": True,
                    },
                )
                resp.raise_for_status()
                results["sent"].append("telegram")
            except Exception as exc:
                logger.warning("Telegram dispatch failed: %s", exc)
                results["errors"]["telegram"] = str(exc)

        if config.discord_webhook_url.strip():
            try:
                resp = client.post(
                    config.discord_webhook_url.strip(),
                    json={"content": full_text},
                )
                resp.raise_for_status()
                results["sent"].append("discord")
            except Exception as exc:
                logger.warning("Discord dispatch failed: %s", exc)
                results["errors"]["discord"] = str(exc)

        if config.generic_webhook_url.strip():
            try:
                resp = client.post(
                    config.generic_webhook_url.strip(),
                    json={"source": "quantseal", "title": title, "message": message, "metadata": metadata or {}},
                )
                resp.raise_for_status()
                results["sent"].append("webhook")
            except Exception as exc:
                logger.warning("Generic webhook dispatch failed: %s", exc)
                results["errors"]["webhook"] = str(exc)

    results["status"] = "ok" if results["sent"] else "failed"
    return results
