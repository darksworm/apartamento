"""Data models for apartment listings."""

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass
class Listing:
    """Represents a rental listing from any portal."""

    id: str  # Unique ID: "{portal}:{listing_id}"
    portal: str  # Source portal name
    url: str  # Direct link to listing
    title: str
    address: str
    city: str
    rent: int  # DKK per month
    size: int | None  # m²
    rooms: int | None
    pets_allowed: bool | None = None
    has_balcony: bool | None = None
    furnished: bool | None = None
    available_from: date | None = None
    deposit: int | None = None  # DKK
    prepaid_rent: int | None = None  # DKK
    images: list[str] = field(default_factory=list)
    description: str | None = None
    scraped_at: datetime = field(default_factory=datetime.now)

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Listing):
            return False
        return self.id == other.id

    def format_notification(self) -> str:
        """Format listing for notification message."""
        lines = [
            f"{self.title}",
            f"{self.rent:,} DKK/month".replace(",", "."),
        ]

        if self.size:
            lines.append(f"{self.size} m²")

        if self.rooms:
            lines.append(f"{self.rooms} rooms")

        lines.append(f"{self.address}, {self.city}")

        features = []
        if self.pets_allowed:
            features.append("Pets OK")
        if self.has_balcony:
            features.append("Balcony")
        if self.furnished:
            features.append("Furnished")

        if features:
            lines.append(" | ".join(features))

        if self.available_from:
            lines.append(f"Available: {self.available_from.strftime('%d/%m/%Y')}")

        lines.append(f"\n{self.url}")

        return "\n".join(lines)
