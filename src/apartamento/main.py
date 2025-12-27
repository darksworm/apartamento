"""Main entry point for Apartamento."""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .config import Config, load_config
from .database import SeenListingsDB
from .filters import apply_filters, score_listing
from .notifier import Notifier
from .scrapers import (
    AkutboligScraper,
    BoligPortalScraper,
    BoligZonenScraper,
    LejeboligScraper,
)
from .scrapers.base import BaseScraper

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def get_enabled_scrapers(config: Config) -> list[BaseScraper]:
    """Get list of scraper instances based on config."""
    scrapers: list[BaseScraper] = []

    if config.portals.boligportal:
        scrapers.append(BoligPortalScraper())

    if config.portals.lejebolig:
        scrapers.append(LejeboligScraper())

    if config.portals.boligzonen:
        scrapers.append(BoligZonenScraper())


    if config.portals.akutbolig:
        scrapers.append(AkutboligScraper())

    return scrapers


async def _run_scraper(scraper: BaseScraper) -> tuple[str, list]:
    """Run a single scraper and return its name and listings."""
    try:
        async with scraper:
            listings = await scraper.fetch_listings()
            logger.info(f"[{scraper.name}] Fetched {len(listings)} listings")
            return scraper.name, listings
    except Exception as e:
        logger.error(f"[{scraper.name}] Scraper failed: {e}")
        return scraper.name, []


async def run_scan(config: Config, db: SeenListingsDB, notifier: Notifier) -> int:
    """
    Run a single scan of all enabled portals.
    Returns the number of new listings found.
    """
    logger.info("Starting scan...")
    all_listings = []

    scrapers = get_enabled_scrapers(config)

    # Run all scrapers in parallel
    results = await asyncio.gather(*[_run_scraper(s) for s in scrapers])

    for name, listings in results:
        all_listings.extend(listings)

    if not all_listings:
        logger.info("No listings fetched")
        return 0

    # Apply filters
    filtered = apply_filters(all_listings, config.filters)
    logger.info(f"After filtering: {len(filtered)} listings match criteria")

    if not filtered:
        return 0

    # Find new listings (not seen before)
    listing_ids = [l.id for l in filtered]
    new_ids = await db.filter_new(listing_ids)
    new_listings = [l for l in filtered if l.id in new_ids]

    logger.info(f"New listings: {len(new_listings)}")

    if new_listings:
        # Sort by score (best matches first)
        new_listings.sort(key=lambda l: score_listing(l, config.filters), reverse=True)

        # Send notifications
        for listing in new_listings:
            score = score_listing(listing, config.filters)
            priority = "high" if score >= 15 else "default"
            await notifier.send(listing, priority=priority)

        # Mark all as seen
        await db.mark_many_seen([(l.id, l.portal) for l in new_listings])

    # Also mark filtered listings as seen to avoid re-checking
    await db.mark_many_seen([(l.id, l.portal) for l in filtered])

    return len(new_listings)


async def daemon_mode(config: Config) -> None:
    """Run in daemon mode with scheduled scans."""
    logger.info(f"Starting daemon mode (interval: {config.schedule.interval_minutes} min)")

    async with SeenListingsDB(config.data_dir / "seen.db") as db:
        notifier = Notifier(config.ntfy)

        # Run initial scan
        await run_scan(config, db, notifier)

        # Set up scheduler
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            run_scan,
            trigger=IntervalTrigger(minutes=config.schedule.interval_minutes),
            args=[config, db, notifier],
            id="scan_job",
            name="Apartment scan",
            replace_existing=True,
        )
        scheduler.start()

        logger.info("Scheduler started. Press Ctrl+C to stop.")

        # Keep running
        try:
            while True:
                await asyncio.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            logger.info("Shutting down...")
            scheduler.shutdown()


async def single_run(config: Config) -> int:
    """Run a single scan and exit."""
    async with SeenListingsDB(config.data_dir / "seen.db") as db:
        notifier = Notifier(config.ntfy)
        return await run_scan(config, db, notifier)


async def test_notify(config: Config) -> bool:
    """Send a test notification."""
    notifier = Notifier(config.ntfy)
    return await notifier.send_test()


async def async_main(args: argparse.Namespace) -> int:
    """Async main entry point."""
    config = load_config(args.config)

    # Ensure data directory exists
    config.data_dir.mkdir(parents=True, exist_ok=True)

    if args.test_notify:
        logger.info(f"Sending test notification to {config.ntfy.server}/{config.ntfy.topic}")
        success = await test_notify(config)
        return 0 if success else 1

    if args.daemon:
        await daemon_mode(config)
        return 0
    else:
        new_count = await single_run(config)
        logger.info(f"Scan complete. Found {new_count} new listings.")
        return 0


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Apartamento - Danish rental listing agent"
    )
    parser.add_argument(
        "-c", "--config",
        type=Path,
        default=Path("config.yaml"),
        help="Path to config file (default: config.yaml)",
    )
    parser.add_argument(
        "-d", "--daemon",
        action="store_true",
        help="Run in daemon mode with scheduled scans",
    )
    parser.add_argument(
        "--test-notify",
        action="store_true",
        help="Send a test notification and exit",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        sys.exit(asyncio.run(async_main(args)))
    except KeyboardInterrupt:
        logger.info("Interrupted")
        sys.exit(0)


if __name__ == "__main__":
    main()
