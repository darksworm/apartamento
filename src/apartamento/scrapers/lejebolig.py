"""Scraper for Lejebolig.dk."""

import asyncio
import json
import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

from ..models import Listing
from .base import BaseScraper

logger = logging.getLogger(__name__)


class LejeboligScraper(BaseScraper):
    """Scraper for Lejebolig.dk - major Danish rental site."""

    name = "lejebolig"
    base_url = "https://www.lejebolig.dk"

    async def fetch_listings(self, max_pages: int = 20) -> list[Listing]:
        """
        Fetch rental listings from Lejebolig.dk.

        Uses the "more results" endpoint for pagination.
        Filtering is done post-fetch.
        """
        all_listings: list[Listing] = []

        # First page
        try:
            response = await self.fetch_page(f"{self.base_url}/lejeboliger")
            page_listings = self._parse_page(response.text)
            if page_listings:
                all_listings.extend(page_listings)
                logger.info(f"[{self.name}] Page 1: {len(page_listings)} listings")
        except Exception as e:
            logger.error(f"[{self.name}] Failed to fetch first page: {e}")
            return all_listings

        # Subsequent pages using AJAX endpoint
        for page in range(2, max_pages + 1):
            try:
                url = f"{self.base_url}/Hunter/MoreResults"
                params = {"isCitySearch": "False", "page": page}

                response = await self.fetch_page(url, params=params)

                # This endpoint returns HTML fragments
                page_listings = self._parse_page(response.text)

                if not page_listings:
                    logger.info(f"[{self.name}] No more listings at page {page}")
                    break

                all_listings.extend(page_listings)
                logger.info(
                    f"[{self.name}] Page {page}: {len(page_listings)} listings "
                    f"(total: {len(all_listings)})"
                )

                await asyncio.sleep(0.3)

            except Exception as e:
                logger.error(f"[{self.name}] Error fetching page {page}: {e}")
                break

        logger.info(f"[{self.name}] Total listings fetched: {len(all_listings)}")
        return all_listings

    def _parse_page(self, html: str) -> list[Listing]:
        """Parse listings from HTML."""
        soup = BeautifulSoup(html, "lxml")

        # Find all lease items (excluding dummy/placeholder items)
        items = soup.select(".lease-item:not(.dummy)")
        listings: list[Listing] = []

        for item in items:
            try:
                listing = self._parse_item(item)
                if listing:
                    listings.append(listing)
            except Exception as e:
                logger.error(f"[{self.name}] Failed to parse item: {e}")

        return listings

    def _parse_item(self, item) -> Listing | None:
        """Parse a single listing item."""
        # Get link and ID
        link = item.select_one('a[href*="/lejebolig/"]')
        if not link:
            return None

        href = link.get("href", "")
        match = re.search(r"/lejebolig/(\d+)/", href)
        if not match:
            return None

        listing_id = match.group(1)
        url = f"{self.base_url}{href}" if not href.startswith("http") else href

        # Title
        title_el = item.select_one("h2")
        title = title_el.get_text(strip=True) if title_el else ""

        # Sub-header contains type and city (e.g., "Lejlighed i København")
        sub_el = item.select_one(".lease-sub-header")
        sub_text = sub_el.get_text(strip=True) if sub_el else ""

        # Parse city from sub-header
        city = ""
        if " i " in sub_text:
            city = sub_text.split(" i ", 1)[1].strip()

        # Price (e.g., "5.850,-")
        rent = 0
        rent_el = item.select_one(".rent")
        if rent_el:
            rent_text = rent_el.get_text(strip=True)
            # Parse Danish number format: "5.850,-" -> 5850
            rent_match = re.search(r"([\d.]+)", rent_text)
            if rent_match:
                rent = int(rent_match.group(1).replace(".", ""))

        # Specs: m², rooms, lease duration
        specs = item.select(".lease-spec")
        size = None
        rooms = None

        if len(specs) >= 1:
            # First spec is usually m²
            size_text = specs[0].get_text(strip=True)
            if size_text.isdigit():
                size = int(size_text)

        if len(specs) >= 2:
            # Second spec is usually rooms
            rooms_text = specs[1].get_text(strip=True)
            if rooms_text.isdigit():
                rooms = int(rooms_text)

        # Images from embedded JSON
        images: list[str] = []
        img_script = item.select_one('script[type="application/json"]')
        if img_script and img_script.string:
            try:
                images = json.loads(img_script.string)[:5]
            except json.JSONDecodeError:
                pass

        # Fallback to data-lazy-bg attribute
        if not images:
            img_div = item.select_one("[data-lazy-bg]")
            if img_div:
                images = [img_div.get("data-lazy-bg")]

        return Listing(
            id=self.make_id(listing_id),
            portal=self.name,
            url=url,
            title=title,
            address="",  # Not available in list view
            city=city,
            rent=rent,
            size=size,
            rooms=rooms,
            pets_allowed=None,  # Not available in list view
            has_balcony=None,  # Not available in list view
            furnished=None,
            available_from=None,
            images=images,
        )
