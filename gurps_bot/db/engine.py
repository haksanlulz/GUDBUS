"""Async engine + session factory; module-level helpers delegate to a default DatabaseManager."""

from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


class DatabaseManager:
    """Owns the engine + session-factory lifecycle; instances are independent, so tests can run their own in-memory."""

    def __init__(self) -> None:
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    def init(self, url: str | None = None) -> async_sessionmaker[AsyncSession]:
        """Create the engine and session factory; idempotent."""
        if self._engine is not None:
            return self._session_factory  # type: ignore[return-value]

        if url is None:
            from gurps_bot.config import DATABASE_URL
            url = DATABASE_URL

        self._engine = create_async_engine(url, echo=False)
        self._session_factory = async_sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False,
        )

        if "sqlite" in url:

            @event.listens_for(self._engine.sync_engine, "connect")
            def _set_sqlite_pragma(dbapi_conn, connection_record):
                cursor = dbapi_conn.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA busy_timeout=5000")
                # sqlite defaults foreign_keys OFF per connection; without this
                # every declared ondelete is inert and character deletes strand
                # dangling character_id rows
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()
                # sqlite's built-in lower() folds ASCII only; use python's so
                # func.lower(col) agrees with .lower()ed bind values for
                # non-ascii names
                dbapi_conn.create_function(
                    "lower", 1,
                    lambda s: s.lower() if isinstance(s, str) else s,
                    deterministic=True,
                )

        return self._session_factory

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        if self._session_factory is None:
            raise RuntimeError(
                "Database not initialized. Call init() first "
                "(this happens automatically in bot.setup_hook)."
            )
        return self._session_factory

    async def create_tables(self) -> None:
        from gurps_bot.config import DATA_DIR
        from gurps_bot.db.models import Base

        if self._engine is None:
            raise RuntimeError("Call init() before create_tables().")

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def dispose(self) -> None:
        """Safe to call multiple times."""
        if self._engine is not None:
            await self._engine.dispose()
        self._engine = None
        self._session_factory = None


_default = DatabaseManager()


def init_engine(url: str | None = None) -> async_sessionmaker[AsyncSession]:
    return _default.init(url)


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return _default.session_factory


async def init_db() -> None:
    await _default.create_tables()


async def dispose_engine() -> None:
    """Resets the default instance so init_engine() can be called again (test teardown)."""
    global _default
    await _default.dispose()
    _default = DatabaseManager()
