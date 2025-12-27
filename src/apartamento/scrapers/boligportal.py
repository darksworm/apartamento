"""Scraper for BoligPortal.dk."""

import asyncio
import json
import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

from ..models import Listing
from .base import BaseScraper

logger = logging.getLogger(__name__)


class BoligPortalScraper(BaseScraper):
    """Scraper for BoligPortal.dk - Denmark's largest rental portal."""

    name = "boligportal"
    base_url = "https://www.boligportal.dk"

    async def fetch_listings(self, max_pages: int = 50) -> list[Listing]:
        """
        Fetch all rental listings from BoligPortal.

        Fetches from the main listings page and paginates through results.
        Filtering is done post-fetch.
        """
        all_listings: list[Listing] = []
        offset = 0
        limit = 18  # BoligPortal's default page size

        for page in range(max_pages):
            url = f"{self.base_url}/lejeboliger/"
            params = {"offset": offset} if offset > 0 else {}

            try:
                response = await self.fetch_page(url, params=params)
                page_listings, has_more = self._parse_page(response.text)

                if page_listings:
                    all_listings.extend(page_listings)
                    logger.info(
                        f"[{self.name}] Page {page + 1}: {len(page_listings)} listings "
                        f"(total: {len(all_listings)})"
                    )

                if not has_more or not page_listings:
                    break

                offset += limit

                # Small delay between pages to be polite
                await asyncio.sleep(0.3)

            except Exception as e:
                logger.error(f"[{self.name}] Error fetching page {page + 1}: {e}")
                break

        logger.info(f"[{self.name}] Total listings fetched: {len(all_listings)}")
        return all_listings

    def _parse_page(self, html: str) -> tuple[list[Listing], bool]:
        """
        Parse listings from HTML page containing embedded JSON.

        Returns:
            Tuple of (listings, has_more_pages)
        """
        soup = BeautifulSoup(html, "lxml")

        # Find the embedded JSON data
        script_tag = soup.find("script", id="store")
        if not script_tag or not script_tag.string:
            logger.warning(f"[{self.name}] No store script found")
            return [], False

        try:
            data = json.loads(script_tag.string)
        except json.JSONDecodeError as e:
            logger.error(f"[{self.name}] Failed to parse JSON: {e}")
            return [], False

        # Navigate to the results
        # Structure: data.props.page_props.results
        props = data.get("props", {})
        page_props = props.get("page_props", {})
        results = page_props.get("results", [])

        listings: list[Listing] = []
        for item in results:
            try:
                listing = self._parse_listing(item)
                if listing:
                    listings.append(listing)
            except Exception as e:
                logger.error(f"[{self.name}] Failed to parse listing: {e}")

        # Check if there are more pages
        has_more = page_props.get("next_page_url") is not None

        return listings, has_more

    def _parse_listing(self, item: dict) -> Listing | None:
        """Parse a single listing from JSON data."""
        listing_id = item.get("rentable_id") or item.get("id")
        if not listing_id:
            return None

        # Extract features
        features = item.get("features", {})

        # Parse available_from date
        available_from = None
        if item.get("available_from"):
            try:
                available_from = datetime.fromisoformat(
                    item["available_from"].replace("Z", "+00:00")
                ).date()
            except (ValueError, AttributeError):
                pass

        # Extract images
        images = []
        for img in item.get("images", []):
            if isinstance(img, dict) and img.get("url"):
                images.append(img["url"])
            elif isinstance(img, str):
                images.append(img)

        # Build URL
        url = item.get("url", "")
        if url and not url.startswith("http"):
            url = f"{self.base_url}{url}"

        # Get rent amount (can be int or float)
        rent = item.get("monthly_rent", 0)
        if isinstance(rent, (int, float)):
            rent = int(rent)
        elif isinstance(rent, str):
            rent = int(re.sub(r"[^\d]", "", rent) or 0)

        # Get size (can be int or float)
        size = item.get("size_m2")
        if isinstance(size, (int, float)):
            size = int(size)
        elif isinstance(size, str):
            size = int(re.sub(r"[^\d]", "", size) or 0)

        # Get rooms (can be int or float like 2.5)
        rooms = item.get("rooms")
        if isinstance(rooms, (int, float)):
            rooms = int(rooms)

        return Listing(
            id=self.make_id(str(listing_id)),
            portal=self.name,
            url=url,
            title=item.get("title", ""),
            address=f"{item.get('street_name', '')} {item.get('street_number', '')}".strip(),
            city=item.get("city", "") or item.get("city_area", ""),
            rent=rent,
            size=size,
            rooms=rooms,
            pets_allowed=features.get("pet_friendly"),
            has_balcony=features.get("balcony"),
            furnished=features.get("furnished"),
            available_from=available_from,
            deposit=item.get("deposit"),
            prepaid_rent=item.get("prepaid_rent"),
            images=images[:5],  # Limit to first 5 images
            description=item.get("description"),
        )
