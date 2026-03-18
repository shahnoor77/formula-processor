"""Tag registry for managing tag metadata."""
from typing import Dict, Optional
from datetime import datetime
import structlog

from infra.db_connection import db
from core.models import TagInfo

logger = structlog.get_logger()


class TagRegistry:
    """Manages tag registration and caching."""
    
    def __init__(self):
        self._cache: Dict[str, int] = {}  # tag_name -> tag_id
        self._reverse_cache: Dict[int, str] = {}  # tag_id -> tag_name
        self._ensure_table_exists()
        self._load_cache()
    
    def _ensure_table_exists(self) -> None:
        """Create TagRegistry table if it doesn't exist."""
        create_table_sql = """
        IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'TagRegistry')
        BEGIN
            CREATE TABLE TagRegistry (
                id BIGINT IDENTITY(1,1) PRIMARY KEY,
                tag_name NVARCHAR(255) NOT NULL UNIQUE,
                created_at DATETIME2 DEFAULT GETUTCDATE()
            );
            CREATE UNIQUE INDEX idx_tag_name ON TagRegistry(tag_name);
        END
        """
        with db.cursor() as cursor:
            cursor.execute(create_table_sql)
            db.commit()
        logger.info("tag_registry_table_ready")
    
    def _load_cache(self) -> None:
        """Load existing tags into memory cache."""
        query = "SELECT id, tag_name FROM TagRegistry"
        with db.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()
            for row in rows:
                self._cache[row.tag_name] = row.id
                self._reverse_cache[row.id] = row.tag_name
        logger.info("tag_registry_cache_loaded", count=len(self._cache))
    
    def get_or_create_tag_id(self, tag_name: str) -> int:
        """Get tag_id for tag_name, creating if necessary."""
        # Check cache first
        if tag_name in self._cache:
            return self._cache[tag_name]
        
        # Try to insert, handle race condition
        try:
            insert_sql = """
            INSERT INTO TagRegistry (tag_name)
            OUTPUT INSERTED.id
            VALUES (?)
            """
            with db.cursor() as cursor:
                cursor.execute(insert_sql, (tag_name,))
                row = cursor.fetchone()
                tag_id = row.id
                db.commit()
                
                # Update cache
                self._cache[tag_name] = tag_id
                self._reverse_cache[tag_id] = tag_name
                
                logger.info("tag_registered", tag_name=tag_name, tag_id=tag_id)
                return tag_id
        
        except pyodbc.IntegrityError:
            # Tag already exists, fetch it
            select_sql = "SELECT id FROM TagRegistry WHERE tag_name = ?"
            with db.cursor() as cursor:
                cursor.execute(select_sql, (tag_name,))
                row = cursor.fetchone()
                tag_id = row.id
                
                # Update cache
                self._cache[tag_name] = tag_id
                self._reverse_cache[tag_id] = tag_name
                
                return tag_id
    
    def get_tag_name(self, tag_id: int) -> Optional[str]:
        """Get tag name by tag_id."""
        return self._reverse_cache.get(tag_id)
    
    def get_all_tags(self) -> list[TagInfo]:
        """Get all registered tags."""
        query = "SELECT id, tag_name, created_at FROM TagRegistry ORDER BY id"
        with db.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()
            return [
                TagInfo(tag_id=row.id, tag_name=row.tag_name, created_at=row.created_at)
                for row in rows
            ]
    
    def get_tag_count(self) -> int:
        """Get total number of registered tags."""
        return len(self._cache)


# Global tag registry instance
tag_registry = TagRegistry()
