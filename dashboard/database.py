"""PostgreSQL connection pooling for the read-only dashboard."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool

from dashboard.config import DashboardConfig


class DatabasePool:
    def __init__(self, config: DashboardConfig):
        self._pool = ThreadedConnectionPool(
            minconn=config.pool_minconn,
            maxconn=config.pool_maxconn,
            dsn=config.database_url,
            connect_timeout=config.connect_timeout_seconds,
            options=f"-c statement_timeout={config.statement_timeout_ms}",
        )

    @contextmanager
    def cursor(self) -> Iterator[RealDictCursor]:
        connection = self._pool.getconn()
        connection.set_session(readonly=True, autocommit=True)
        try:
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                yield cursor
        except psycopg2.Error:
            connection.rollback()
            raise
        finally:
            self._pool.putconn(connection)

    def close(self) -> None:
        self._pool.closeall()


def create_pool(config: DashboardConfig) -> DatabasePool:
    return DatabasePool(config)
