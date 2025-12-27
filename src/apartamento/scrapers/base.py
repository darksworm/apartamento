"""Base scraper interface for rental portals."""

import logging
from abc import ABC, abstractmethod

import httpx

from ..models import Listing

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """Abstract base class for portal scrapers."""

    name: str = "base"
    base_url: str = ""

    # Common headers to avoid bot detection
    DEFAULT_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "da-DK,da;q=0.9,en-US;q=0.8,en;q=0.7",
        # Note: Don't request brotli (br) as httpx may not have brotli support
        "Accept-Encoding": "gzip, deflate",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

    def __init__(self):
        self.client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "BaseScraper":
        self.client = httpx.AsyncClient(
            headers=self.DEFAULT_HEADERS,
            follow_redirects=True,
            timeout=30.0,
        )
        return self

    async def __aexit__(self, *args: object) -> None:
        if self.client:
            await self.client.aclose()
            self.client = None

    def make_id(self, listing_id: str) -> str:
        """Create a unique ID combining portal name and listing ID."""
        return f"{self.name}:{listing_id}"

    @abstractmethod
    async def fetch_listings(self) -> list[Listing]:
        """
        Fetch all available listings from the portal.

        Returns:
            List of Listing objects from this portal.
        """
        raise NotImplementedError

    async def fetch_page(self, url: str, **kwargs) -> httpx.Response:
        """Fetch a page with error handling."""
        if not self.client:
            raise RuntimeError("Scraper not initialized. Use async with.")

        try:
            response = await self.client.get(url, **kwargs)
            response.raise_for_status()
            return response
        except httpx.HTTPError as e:
            logger.error(f"[{self.name}] Failed to fetch {url}: {e}")
            raise

    async def fetch_json(self, url: str, **kwargs) -> dict:
        """Fetch JSON data with error handling."""
        if not self.client:
            raise RuntimeError("Scraper not initialized. Use async with.")

        try:
            response = await self.client.get(url, **kwargs)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"[{self.name}] Failed to fetch JSON from {url}: {e}")
            raise

    async def post_json(self, url: str, data: dict, **kwargs) -> dict:
        """POST JSON data and get JSON response."""
        if not self.client:
            raise RuntimeError("Scraper not initialized. Use async with.")

        try:
            response = await self.client.post(url, json=data, **kwargs)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"[{self.name}] Failed to POST to {url}: {e}")
            raise
