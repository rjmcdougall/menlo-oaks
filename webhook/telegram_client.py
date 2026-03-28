"""
Telegram Bot API client for stolen plate alerts.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import requests

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramClient:
    """Sends messages via the Telegram Bot API."""

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id

    def send_message(self, text: str) -> bool:
        """Send a plain or HTML-formatted message. Returns True on success."""
        try:
            resp = requests.post(
                TELEGRAM_API.format(token=self.bot_token),
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": False,
                },
                timeout=10,
            )
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False

    def send_stolen_plate_alert(
        self,
        plate_number: str,
        camera_name: Optional[str] = None,
        camera_location: Optional[str] = None,
        detection_timestamp: Optional[str] = None,
        confidence: Optional[float] = None,
        thumbnail_url: Optional[str] = None,
    ) -> bool:
        """Send a formatted stolen plate alert."""
        ts = detection_timestamp or datetime.now(tz=timezone.utc).isoformat()

        lines = [
            "🚨 <b>STOLEN PLATE DETECTED</b>",
            "",
            f"Plate: <b>{plate_number}</b>",
        ]

        if camera_name:
            lines.append(f"Camera: {camera_name}")
        if camera_location:
            lines.append(f"Location: {camera_location}")

        lines.append(f"Time: {ts}")

        if confidence is not None:
            lines.append(f"Confidence: {int(confidence * 100)}%")

        if thumbnail_url:
            lines.append(f'<a href="{thumbnail_url}">View thumbnail</a>')

        return self.send_message("\n".join(lines))

    def send_unknown_plate_alert(
        self,
        plate_number: str,
        camera_name: Optional[str] = None,
        camera_location: Optional[str] = None,
        detection_timestamp: Optional[str] = None,
        confidence: Optional[float] = None,
        thumbnail_url: Optional[str] = None,
    ) -> bool:
        """Send a formatted alert for an unknown (unrecognised) plate."""
        ts = detection_timestamp or datetime.now(tz=timezone.utc).isoformat()

        lines = [
            "🔍 <b>UNKNOWN PLATE DETECTED</b>",
            "",
            f"Plate: <b>{plate_number}</b>",
        ]

        if camera_name:
            lines.append(f"Camera: {camera_name}")
        if camera_location:
            lines.append(f"Location: {camera_location}")

        lines.append(f"Time: {ts}")

        if confidence is not None:
            lines.append(f"Confidence: {int(confidence * 100)}%")

        if thumbnail_url:
            lines.append(f'<a href="{thumbnail_url}">View thumbnail</a>')

        return self.send_message("\n".join(lines))
