"""Notification system using ntfy.sh."""

import logging

import httpx
from unidecode import unidecode

from .config import NtfyConfig
from .models import Listing

logger = logging.getLogger(__name__)


class Notifier:
    """Send notifications via ntfy.sh."""

    def __init__(self, config: NtfyConfig):
        self.config = config
        self.url = f"{config.server.rstrip('/')}/{config.topic}"

    async def send(
        self,
        listing: Listing,
        priority: str | None = None,
    ) -> bool:
        """Send notification for a listing. Returns True if successful."""
        message = listing.format_notification()
        title = unidecode(f"New: {listing.rent:,} DKK - {listing.city}".replace(",", "."))

        headers = {
            "Title": title,
            "Priority": priority or self.config.priority,
            "Tags": f"house,{listing.portal}",
            "Click": listing.url,
        }

        # Add first image as attachment if available
        if listing.images:
            headers["Attach"] = listing.images[0]

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.url,
                    content=message.encode("utf-8"),
                    headers=headers,
                    timeout=30.0,
                )
                response.raise_for_status()
                logger.info(f"Notification sent for {listing.id}")
                return True
        except httpx.HTTPError as e:
            logger.error(f"Failed to send notification for {listing.id}: {e}")
            return False

    async def send_batch(
        self,
        listings: list[Listing],
        priority: str | None = None,
    ) -> int:
        """Send notifications for multiple listings. Returns count of successful sends."""
        successful = 0
        for listing in listings:
            if await self.send(listing, priority):
                successful += 1
        return successful

    async def send_test(self) -> bool:
        """Send a test notification to verify setup."""
        headers = {
            "Title": "Apartamento Test",
            "Priority": "default",
            "Tags": "white_check_mark",
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.url,
                    content="Test notification from Apartamento. Your setup is working!",
                    headers=headers,
                    timeout=30.0,
                )
                response.raise_for_status()
                logger.info("Test notification sent successfully")
                return True
        except httpx.HTTPError as e:
            logger.error(f"Failed to send test notification: {e}")
            return False

    async def send_summary(self, new_count: int, portals_checked: list[str]) -> bool:
        """Send a summary notification after a scan."""
        if new_count == 0:
            return True  # Don't notify if nothing new

        message = f"Found {new_count} new listing(s) matching your criteria.\n"
        message += f"Portals checked: {', '.join(portals_checked)}"

        headers = {
            "Title": f"Apartamento: {new_count} new listing(s)",
            "Priority": "high" if new_count > 0 else "default",
            "Tags": "bell",
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.url,
                    content=message,
                    headers=headers,
                    timeout=30.0,
                )
                response.raise_for_status()
                return True
        except httpx.HTTPError as e:
            logger.error(f"Failed to send summary notification: {e}")
            return False
