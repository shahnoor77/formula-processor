import pyodbc
from typing import Optional
from contextlib import contextmanager
from queue import Queue, Empty
from threading import Lock
import structlog

from core.config import settings

logger = structlog.get_logger()


class ConnectionPool:
    def __init__(self, connection_string: str, pool_size: int = 5, max_overflow: int = 10):
        self.connection_string = connection_string
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self._pool: Queue = Queue(maxsize=pool_size + max_overflow)
        self._current_size = 0
        self._lock = Lock()

        for _ in range(pool_size):
            conn = self._create_connection()
            self._pool.put(conn)
            self._current_size += 1

        logger.info("connection_pool_initialized", pool_size=pool_size, max_overflow=max_overflow)

    def _create_connection(self) -> pyodbc.Connection:
        return pyodbc.connect(self.connection_string, autocommit=False)

    def get_connection(self, timeout: float = 5.0) -> pyodbc.Connection:
        try:
            conn = self._pool.get(timeout=timeout)
            if conn.closed:
                conn = self._create_connection()
            return conn
        except Empty:
            with self._lock:
                if self._current_size < (self.pool_size + self.max_overflow):
                    conn = self._create_connection()
                    self._current_size += 1
                    return conn
                else:
                    raise Exception(f"Connection pool exhausted (max {self.pool_size + self.max_overflow})")

    def return_connection(self, conn: pyodbc.Connection) -> None:
        if not conn.closed:
            try:
                conn.rollback()
                self._pool.put_nowait(conn)
            except Exception as e:
                logger.error("connection_return_failed", error=str(e))
                conn.close()
                with self._lock:
                    self._current_size -= 1
        else:
            with self._lock:
                self._current_size -= 1

    def close_all(self) -> None:
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                if not conn.closed:
                    conn.close()
            except Empty:
                break


class DatabaseConnection:
    def __init__(self):
        self.connection_string = settings.connection_string
        self._pool = ConnectionPool(
            connection_string=self.connection_string,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow
        )
        self._conn: Optional[pyodbc.Connection] = None

    def connect(self) -> None:
        if self._conn is None or self._conn.closed:
            self._conn = self._pool.get_connection()

    def close(self) -> None:
        if self._conn and not self._conn.closed:
            self._pool.return_connection(self._conn)
            self._conn = None

    @contextmanager
    def cursor(self):
        # Each call gets its own connection from the pool to avoid thread conflicts
        conn = self._pool.get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            self._pool.return_connection(conn)

    def commit(self) -> None:
        if self._conn:
            self._conn.commit()

    def rollback(self) -> None:
        if self._conn:
            self._conn.rollback()

    def close_pool(self) -> None:
        self._pool.close_all()


db = DatabaseConnection()
