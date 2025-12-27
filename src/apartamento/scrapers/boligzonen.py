"""Scraper for BoligZonen.dk."""

import asyncio
import logging
import re

from bs4 import BeautifulSoup

from ..models import Listing
from .base import BaseScraper

logger = logging.getLogger(__name__)


class BoligZonenScraper(BaseScraper):
    """Scraper for BoligZonen.dk - Danish rental portal."""

    name = "boligzonen"
    base_url = "https://www.boligzonen.dk"

    async def fetch_listings(self, max_pages: int = 30) -> list[Listing]:
        """
        Fetch rental listings from BoligZonen.dk.

        Uses their JSON API endpoint which returns HTML in result_html.
        Filtering is done post-fetch.
        """
        all_listings: list[Listing] = []

        for page in range(1, max_pages + 1):
            try:
                url = f"{self.base_url}/ledige-lejeboliger/find.json"
                params = {"page": page} if page > 1 else {}

                if not self.client:
                    raise RuntimeError("Scraper not initialized")

                # Request JSON
                response = await self.client.get(
                    url,
                    params=params,
                    headers={"Accept": "application/json"},
                )
                response.raise_for_status()
                data = response.json()

                # Parse HTML from JSON response
                result_html = data.get("result_html", "")
                if not result_html:
                    logger.info(f"[{self.name}] No more results at page {page}")
                    break

                page_listings = self._parse_html(result_html)

                if not page_listings:
                    break

                all_listings.extend(page_listings)
                logger.info(
                    f"[{self.name}] Page {page}: {len(page_listings)} listings "
                    f"(total: {len(all_listings)})"
                )

                # Check for more pages
                next_page = data.get("next_page", "")
                if not next_page:
                    break

                await asyncio.sleep(0.3)

            except Exception as e:
                logger.error(f"[{self.name}] Error fetching page {page}: {e}")
                break

        logger.info(f"[{self.name}] Total listings fetched: {len(all_listings)}")
        return all_listings

    def _parse_html(self, html: str) -> list[Listing]:
        """Parse listings from HTML content."""
        soup = BeautifulSoup(html, "lxml")

        # Find all property cards with data-id
        cards = soup.select("[data-id][href]")
        listings: list[Listing] = []

        for card in cards:
            try:
                listing = self._parse_card(card)
                if listing:
                    listings.append(listing)
            except Exception as e:
                logger.error(f"[{self.name}] Failed to parse card: {e}")

        return listings

    def _parse_card(self, card) -> Listing | None:
        """Parse a single listing card."""
        listing_id = card.get("data-id")
        if not listing_id:
            return None

        href = card.get("href", "")
        url = f"{self.base_url}{href}" if href and not href.startswith("http") else href

        # Extract text items from the card
        text_items = [
            t.strip()
            for t in card.stripped_strings
            if len(t.strip()) > 1 and len(t.strip()) < 100
        ]

        # Filter out common non-data strings
        skip_phrases = ["add to favorites", "tilføj", "favorit"]
        text_items = [
            t for t in text_items if not any(skip in t.lower() for skip in skip_phrases)
        ]

        # Parse the text items
        # Typical pattern: [Type, "X værelses på Y m", Street, City, Price, "DKK"]
        property_type = ""
        size = None
        rooms = None
        address = ""
        city = ""
        rent = 0

        for i, item in enumerate(text_items):
            # Property type (first item)
            if i == 0 and item in ["Lejlighed", "Værelse", "Hus / Rækkehus", "Hus", "Rækkehus"]:
                property_type = item
                continue

            # Size and rooms pattern: "2 værelses på 63 m" or "1 værelse på 12 m"
            match = re.search(r"(\d+)\s*v[æa]rels?e?s?\s+p[åa]\s+(\d+)\s*m", item, re.I)
            if match:
                rooms = int(match.group(1))
                size = int(match.group(2))
                continue

            # Just size: "63 m2" or "63 m²"
            match = re.search(r"^(\d+)\s*m[²2]?$", item)
            if match:
                size = int(match.group(1))
                continue

            # Price (number followed by DKK or standalone number > 1000)
            if item == "DKK":
                continue
            match = re.search(r"^([\d.]+)$", item.replace(".", ""))
            if match:
                num = int(match.group(1).replace(".", ""))
                if num > 1000:  # Likely a price
                    rent = num
                    continue

            # Address (contains comma or is a street name)
            if "," in item:
                parts = item.split(",")
                address = parts[0].strip()
                if len(parts) > 1:
                    city = parts[1].strip()
                continue

            # City (standalone, title case, not already found)
            if not city and item[0].isupper() and len(item) < 30:
                # Check if it looks like a city name
                if not any(c.isdigit() for c in item):
                    if address:  # If we already have an address, this is likely city
                        city = item
                    else:
                        address = item

        # Build title from available info
        title = f"{property_type} i {city}" if property_type and city else href.split("/")[-1].replace("-", " ").title()

        # Get first image
        images: list[str] = []
        img_el = card.select_one("img[src*='cloudfront'], source[srcset]")
        if img_el:
            src = img_el.get("src") or ""
            if not src:
                srcset = img_el.get("srcset", "")
                if srcset:
                    src = srcset.split()[0]
            if src:
                images.append(src)

        return Listing(
            id=self.make_id(listing_id),
            portal=self.name,
            url=url,
            title=title,
            address=address,
            city=city,
            rent=rent,
            size=size,
            rooms=rooms,
            pets_allowed=None,  # Not available in list view
            has_balcony=None,
            furnished=None,
            available_from=None,
            images=images,
        )
