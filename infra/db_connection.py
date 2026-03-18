"""Database connection management."""
import pyodbc
from typing import Optional
from contextlib import contextmanager
import structlog

from core.config import settings

logger = structlog.get_logger()


class DatabaseConnection:
    """Manages SQL Server database connections."""
    
    def __init__(self):
        self.connection_string = settings.connection_string
        self._conn: Optional[pyodbc.Connection] = None
    
    def connect(self) -> None:
        """Establish database connection."""
        if self._conn is None or self._conn.closed:
            self._conn = pyodbc.connect(self.connection_string, autocommit=False)
            logger.info("database_connected", server=settings.db_server)
    
    def close(self) -> None:
        """Close database connection."""
        if self._conn and not self._conn.closed:
            self._conn.close()
            logger.info("database_closed")
    
    @contextmanager
    def cursor(self):
        """Get database cursor with automatic connection."""
        self.connect()
        cursor = self._conn.cursor()
        try:
            yield cursor
        finally:
            cursor.close()
    
    def commit(self) -> None:
        """Commit current transaction."""
        if self._conn:
            self._conn.commit()
    
    def rollback(self) -> None:
        """Rollback current transaction."""
        if self._conn:
            self._conn.rollback()


# Global database instance
db = DatabaseConnection()
