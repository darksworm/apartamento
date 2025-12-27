"""Scrapers for Danish rental portals."""

from .akutbolig import AkutboligScraper
from .base import BaseScraper
from .boligportal import BoligPortalScraper
from .boligzonen import BoligZonenScraper
from .lejebolig import LejeboligScraper

__all__ = [
    "AkutboligScraper",
    "BaseScraper",
    "BoligPortalScraper",
    "BoligZonenScraper",
    "LejeboligScraper",
]
