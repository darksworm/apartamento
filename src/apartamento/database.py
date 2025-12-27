"""SQLite database for tracking seen listings."""

import asyncio
from datetime import datetime, timedelta
from pathlib import Path

import aiosqlite


class SeenListingsDB:
    """Track which listings we've already seen to avoid duplicate notifications."""

    def __init__(self, db_path: Path | str = "data/seen.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        """Initialize database connection and create tables."""
        self._connection = await aiosqlite.connect(self.db_path)
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS seen_listings (
                id TEXT PRIMARY KEY,
                portal TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            )
        """)
        await self._connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_portal ON seen_listings(portal)
        """)
        await self._connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_first_seen ON seen_listings(first_seen_at)
        """)
        await self._connection.commit()

    async def close(self) -> None:
        """Close database connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None

    async def __aenter__(self) -> "SeenListingsDB":
        await self.connect()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    async def is_seen(self, listing_id: str) -> bool:
        """Check if we've seen this listing before."""
        if not self._connection:
            raise RuntimeError("Database not connected")

        cursor = await self._connection.execute(
            "SELECT 1 FROM seen_listings WHERE id = ?", (listing_id,)
        )
        row = await cursor.fetchone()
        return row is not None

    async def mark_seen(self, listing_id: str, portal: str) -> None:
        """Mark a listing as seen."""
        if not self._connection:
            raise RuntimeError("Database not connected")

        now = datetime.now().isoformat()
        await self._connection.execute(
            """
            INSERT INTO seen_listings (id, portal, first_seen_at, last_seen_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET last_seen_at = ?
            """,
            (listing_id, portal, now, now, now),
        )
        await self._connection.commit()

    async def mark_many_seen(self, listings: list[tuple[str, str]]) -> None:
        """Mark multiple listings as seen. Each tuple is (id, portal)."""
        if not self._connection:
            raise RuntimeError("Database not connected")

        now = datetime.now().isoformat()
        await self._connection.executemany(
            """
            INSERT INTO seen_listings (id, portal, first_seen_at, last_seen_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET last_seen_at = ?
            """,
            [(lid, portal, now, now, now) for lid, portal in listings],
        )
        await self._connection.commit()

    async def filter_new(self, listing_ids: list[str]) -> list[str]:
        """Return only listing IDs that we haven't seen before."""
        if not self._connection:
            raise RuntimeError("Database not connected")

        if not listing_ids:
            return []

        placeholders = ",".join("?" * len(listing_ids))
        cursor = await self._connection.execute(
            f"SELECT id FROM seen_listings WHERE id IN ({placeholders})", listing_ids
        )
        seen = {row[0] for row in await cursor.fetchall()}
        return [lid for lid in listing_ids if lid not in seen]

    async def prune_old(self, days: int = 30) -> int:
        """Remove listings older than specified days. Returns count deleted."""
        if not self._connection:
            raise RuntimeError("Database not connected")

        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        cursor = await self._connection.execute(
            "DELETE FROM seen_listings WHERE last_seen_at < ?", (cutoff,)
        )
        await self._connection.commit()
        return cursor.rowcount

    async def count(self) -> int:
        """Return total number of seen listings."""
        if not self._connection:
            raise RuntimeError("Database not connected")

        cursor = await self._connection.execute("SELECT COUNT(*) FROM seen_listings")
        row = await cursor.fetchone()
        return row[0] if row else 0
