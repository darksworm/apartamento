"""Scraper for Akutbolig.dk."""

import asyncio
import logging
import re

from bs4 import BeautifulSoup

from ..models import Listing
from .base import BaseScraper

logger = logging.getLogger(__name__)


class AkutboligScraper(BaseScraper):
    """Scraper for Akutbolig.dk - Danish rental portal for urgent housing."""

    name = "akutbolig"
    base_url = "https://www.akutbolig.dk"

    # Major Danish cities - the site has server-rendered pages for these
    CITY_PAGES = [
        "/koebenhavn",
        "/aarhus",
        "/odense",
        "/aalborg",
        "/frederiksberg",
        "/esbjerg",
        "/randers",
        "/kolding",
        "/horsens",
        "/vejle",
        "/roskilde",
        "/herning",
        "/hoersholm",
        "/silkeborg",
        "/naestved",
        "/fredericia",
        "/viborg",
        "/koege",
        "/holstebro",
        "/taastrup",
        "/slagelse",
        "/hilleroed",
        "/holbaek",
        "/sonderborg",
        "/svendborg",
        "/hjorring",
        "/ringsted",
    ]

    async def fetch_listings(self, max_pages: int = 20) -> list[Listing]:
        """
        Fetch rental listings from Akutbolig.dk.

        Scrapes city-specific pages which have server-rendered HTML content.
        """
        all_listings: list[Listing] = []
        seen_ids: set[str] = set()

        for city_path in self.CITY_PAGES:
            try:
                url = f"{self.base_url}{city_path}"
                response = await self.fetch_page(url)
                page_listings = self._parse_page(response.text, city_path)

                # Deduplicate
                new_listings = []
                for listing in page_listings:
                    if listing.id not in seen_ids:
                        seen_ids.add(listing.id)
                        new_listings.append(listing)

                if new_listings:
                    all_listings.extend(new_listings)
                    logger.info(
                        f"[{self.name}] {city_path}: {len(new_listings)} listings "
                        f"(total: {len(all_listings)})"
                    )

                await asyncio.sleep(0.2)

            except Exception as e:
                logger.warning(f"[{self.name}] Error fetching {city_path}: {e}")
                continue

        logger.info(f"[{self.name}] Total listings fetched: {len(all_listings)}")
        return all_listings

    def _parse_page(self, html: str, city_path: str = "") -> list[Listing]:
        """Parse listings from HTML page."""
        soup = BeautifulSoup(html, "lxml")
        listings: list[Listing] = []

        # Extract city name from path for fallback
        city_name = city_path.strip("/").replace("-", " ").title() if city_path else ""

        # Find all links that look like listing links
        # Akutbolig listing URLs typically contain /LID/ pattern
        listing_links = soup.find_all("a", href=re.compile(r"/[A-Z0-9]{6,}/"))

        # Group by listing ID to avoid duplicates
        seen_ids: set[str] = set()

        for link in listing_links:
            try:
                href = link.get("href", "")
                if not href:
                    continue

                # Extract listing ID from URL (e.g., /ABC123/ or /XYZ789/)
                match = re.search(r"/([A-Z0-9]{6,})/", href)
                if not match:
                    continue

                listing_id = match.group(1)
                if listing_id in seen_ids:
                    continue
                seen_ids.add(listing_id)

                # Build full URL
                url = href if href.startswith("http") else f"{self.base_url}{href}"

                # Try to find the parent card/container
                card = link.find_parent(["article", "div", "li"])
                if not card:
                    card = link

                listing = self._parse_card(card, listing_id, url, city_name)
                if listing:
                    listings.append(listing)

            except Exception as e:
                logger.debug(f"[{self.name}] Failed to parse link: {e}")

        return listings

    def _parse_card(
        self, card, listing_id: str, url: str, fallback_city: str
    ) -> Listing | None:
        """Parse a listing card element."""
        # Get all text content for parsing
        text_content = card.get_text(" ", strip=True)

        # Parse title - look for room/size description like "1 værelses lejlighed på 31 m²"
        title = ""
        title_match = re.search(
            r"(\d+\s*værelses?\s+\w+(?:\s+på\s+\d+\s*m²)?)", text_content, re.IGNORECASE
        )
        if title_match:
            title = title_match.group(1)

        # Parse rent - format like "8.300,-" or "8300 kr"
        rent = 0
        rent_match = re.search(r"([\d.]+)(?:,-|kr|\s*DKK)", text_content)
        if rent_match:
            rent_str = rent_match.group(1).replace(".", "")
            rent = int(rent_str) if rent_str.isdigit() else 0

        # Parse size in m²
        size = None
        size_match = re.search(r"(\d+)\s*m²", text_content)
        if size_match:
            size = int(size_match.group(1))

        # Parse rooms - "X vær" or "X værelses"
        rooms = None
        rooms_match = re.search(r"(\d+)\s*vær", text_content, re.IGNORECASE)
        if rooms_match:
            rooms = int(rooms_match.group(1))

        # Parse address - look for street patterns
        address = ""
        # Danish street patterns: "Streetname 123" or "Streetname 12, 3."
        addr_match = re.search(
            r"([A-ZÆØÅ][a-zæøåA-ZÆØÅ\s]+(?:vej|gade|allé|plads|torv|vænge|parken|have)\s*\d+[A-Za-z]?)",
            text_content,
        )
        if addr_match:
            address = addr_match.group(1).strip()

        # Try to find city from text or use fallback
        city = fallback_city
        # Look for postal code + city pattern
        city_match = re.search(r"\d{4}\s+([A-ZÆØÅ][a-zæøå]+(?:\s+[A-ZÆØÅ])?)", text_content)
        if city_match:
            city = city_match.group(1).strip()

        # Get image
        images = []
        img = card.select_one("img[src]")
        if img:
            src = img.get("src") or img.get("data-src")
            if src and not src.startswith("data:"):
                if not src.startswith("http"):
                    src = f"{self.base_url}{src}"
                images.append(src)

        # Also check for background-image style
        if not images:
            for el in card.select("[style*='background']"):
                style = el.get("style", "")
                bg_match = re.search(r"url\(['\"]?([^)'\")]+)", style)
                if bg_match:
                    img_url = bg_match.group(1)
                    if not img_url.startswith("http"):
                        img_url = f"https://img.akut-bolig.dk{img_url}"
                    images.append(img_url)
                    break

        # Only return if we have meaningful data
        if not rent and not size and not rooms:
            return None

        return Listing(
            id=self.make_id(listing_id),
            portal=self.name,
            url=url,
            title=title or f"Listing {listing_id}",
            address=address,
            city=city,
            rent=rent,
            size=size,
            rooms=rooms,
            images=images[:5],
        )
