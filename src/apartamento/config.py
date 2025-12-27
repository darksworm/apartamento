"""Configuration management for Apartamento."""

from datetime import date
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class NtfyConfig(BaseModel):
    """ntfy.sh notification settings."""

    topic: str = "apartamento-alerts"
    server: str = "https://ntfy.sh"
    priority: str = "default"  # min, low, default, high, urgent


class FilterConfig(BaseModel):
    """Apartment filter criteria."""

    locations: list[str] = Field(default_factory=list)
    max_rent: int | None = None
    min_rent: int | None = None
    min_size: int | None = None
    max_size: int | None = None
    min_rooms: int | None = None
    max_rooms: int | None = None
    pets_allowed: bool | None = None
    has_balcony: bool | None = None
    furnished: bool | None = None
    available_from: date | None = None
    available_to: date | None = None


class ScheduleConfig(BaseModel):
    """Scheduling settings."""

    interval_minutes: int = 15


class PortalsConfig(BaseModel):
    """Which portals to scrape."""

    boligportal: bool = True
    lejebolig: bool = True
    bolighub: bool = True
    boligzonen: bool = True
    akutbolig: bool = True


class Config(BaseModel):
    """Main configuration."""

    ntfy: NtfyConfig = Field(default_factory=NtfyConfig)
    filters: FilterConfig = Field(default_factory=FilterConfig)
    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig)
    portals: PortalsConfig = Field(default_factory=PortalsConfig)
    data_dir: Path = Field(default=Path("data"))


def load_config(config_path: Path | str = "config.yaml") -> Config:
    """Load configuration from YAML file."""
    config_path = Path(config_path)

    if not config_path.exists():
        # Return default config if no file exists
        return Config()

    with open(config_path) as f:
        data: dict[str, Any] = yaml.safe_load(f) or {}

    return Config(**data)
