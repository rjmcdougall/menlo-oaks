"""
Telegram Bot API client for stolen plate alerts.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional

import requests

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


class TelegramClient:
    """Sends messages via the Telegram Bot API."""

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id

    def _api_url(self, method: str) -> str:
        return TELEGRAM_API.format(token=self.bot_token, method=method)

    def send_message(self, text: str) -> bool:
        """Send a plain or HTML-formatted message. Returns True on success."""
        try:
            resp = requests.post(
                self._api_url("sendMessage"),
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

    def send_photo(self, photo_url: str, caption: str = "") -> bool:
        """Send a photo by URL with an optional HTML caption."""
        try:
            resp = requests.post(
                self._api_url("sendPhoto"),
                json={
                    "chat_id": self.chat_id,
                    "photo": photo_url,
                    "caption": caption,
                    "parse_mode": "HTML",
                },
                timeout=15,
            )
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Telegram sendPhoto failed: {e}")
            return False

    @staticmethod
    def build_static_map_url(
        locations: List[dict], mapbox_token: str
    ) -> Optional[str]:
        """
        Build a Mapbox Static Images API URL showing pins for each location.
        Returns None if no valid coordinates are available.
        """
        valid = [
            loc for loc in locations
            if loc.get("lat") is not None and loc.get("lng") is not None
        ]
        if not valid:
            return None

        markers = ",".join(
            f"pin-s+ff4444({loc['lng']:.6f},{loc['lat']:.6f})"
            for loc in valid
        )

        # Single point: use fixed zoom; multiple points: auto-fit bounding box
        if len(valid) == 1:
            loc = valid[0]
            viewport = f"{loc['lng']:.6f},{loc['lat']:.6f},15"
            padding = ""
        else:
            viewport = "auto"
            padding = "&padding=60"

        return (
            f"https://api.mapbox.com/styles/v1/mapbox/streets-v11/static/"
            f"{markers}/{viewport}/600x400"
            f"?access_token={mapbox_token}{padding}"
        )

    def send_stolen_plate_alert(
        self,
        plate_number: str,
        camera_name: Optional[str] = None,
        camera_location: Optional[str] = None,
        detection_timestamp: Optional[str] = None,
        confidence: Optional[float] = None,
        thumbnail_url: Optional[str] = None,
        recent_count: Optional[int] = None,
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

        if recent_count is not None:
            lines.append(f"Seen: {recent_count}x in last 10 min")

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
        recent_count: Optional[int] = None,
        locations: Optional[List[dict]] = None,
        mapbox_token: Optional[str] = None,
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

        if recent_count is not None:
            lines.append(f"Seen: {recent_count}x in last 10 min")

        if thumbnail_url:
            lines.append(f'<a href="{thumbnail_url}">View thumbnail</a>')

        ok = self.send_message("\n".join(lines))

        # Follow up with a map image showing all camera locations hit in the window
        if locations and mapbox_token:
            map_url = self.build_static_map_url(locations, mapbox_token)
            if map_url:
                location_list = ", ".join(
                    loc["camera_name"] for loc in locations if loc.get("camera_name")
                ) or f"{len(locations)} location(s)"
                self.send_photo(
                    map_url,
                    caption=f"📍 <b>{plate_number}</b> — cameras hit: {location_list}",
                )

        return ok
