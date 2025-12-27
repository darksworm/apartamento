"""Filter logic for applying user criteria to listings."""

import logging
from typing import Callable

from .config import FilterConfig
from .models import Listing

logger = logging.getLogger(__name__)


def normalize_location(location: str) -> str:
    """Normalize location string for matching."""
    return location.lower().strip()


def matches_location(listing: Listing, locations: list[str]) -> bool:
    """Check if listing matches any of the target locations."""
    if not locations:
        return True  # No location filter = match all

    normalized_locations = [normalize_location(loc) for loc in locations]

    # Check city and address
    listing_city = normalize_location(listing.city)
    listing_address = normalize_location(listing.address)

    for loc in normalized_locations:
        if loc in listing_city or loc in listing_address:
            return True

    return False


def apply_filters(listings: list[Listing], config: FilterConfig) -> list[Listing]:
    """
    Apply all filter criteria to a list of listings.

    Returns only listings that match ALL criteria.
    A criteria of None means "don't filter on this".
    """
    filters: list[Callable[[Listing], bool]] = []

    # Location filter
    if config.locations:
        filters.append(lambda l: matches_location(l, config.locations))

    # Rent filters
    if config.max_rent is not None:
        filters.append(lambda l: l.rent <= config.max_rent)
    if config.min_rent is not None:
        filters.append(lambda l: l.rent >= config.min_rent)

    # Size filters
    if config.min_size is not None:
        filters.append(lambda l: l.size is not None and l.size >= config.min_size)
    if config.max_size is not None:
        filters.append(lambda l: l.size is not None and l.size <= config.max_size)

    # Room filters
    if config.min_rooms is not None:
        filters.append(lambda l: l.rooms is not None and l.rooms >= config.min_rooms)
    if config.max_rooms is not None:
        filters.append(lambda l: l.rooms is not None and l.rooms <= config.max_rooms)

    # Boolean feature filters (only filter if explicitly set to True)
    if config.pets_allowed is True:
        filters.append(lambda l: l.pets_allowed is True)
    if config.has_balcony is True:
        filters.append(lambda l: l.has_balcony is True)
    if config.furnished is True:
        filters.append(lambda l: l.furnished is True)

    # Date filters
    if config.available_from is not None:
        filters.append(
            lambda l: l.available_from is None or l.available_from >= config.available_from
        )
    if config.available_to is not None:
        filters.append(
            lambda l: l.available_from is None or l.available_from <= config.available_to
        )

    # Apply all filters
    filtered = listings
    for f in filters:
        filtered = [l for l in filtered if f(l)]

    logger.info(f"Filtered {len(listings)} listings down to {len(filtered)}")
    return filtered


def score_listing(listing: Listing, config: FilterConfig) -> int:
    """
    Score a listing based on how well it matches preferences.
    Higher score = better match. Used for prioritizing notifications.
    """
    score = 0

    # Lower rent is better (within budget)
    if config.max_rent and listing.rent:
        rent_savings = config.max_rent - listing.rent
        score += min(rent_savings // 500, 10)  # +1 per 500 DKK under budget, max 10

    # Larger size is better
    if listing.size:
        if config.min_size:
            extra_space = listing.size - config.min_size
            score += min(extra_space // 5, 10)  # +1 per 5m² extra, max 10

    # Bonus for desirable features
    if listing.pets_allowed:
        score += 5
    if listing.has_balcony:
        score += 5
    if listing.furnished:
        score += 3

    # Sooner availability is better
    if listing.available_from:
        from datetime import date
        days_until = (listing.available_from - date.today()).days
        if days_until <= 30:
            score += 5
        elif days_until <= 60:
            score += 3

    return score
