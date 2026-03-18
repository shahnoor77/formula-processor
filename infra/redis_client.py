"""Redis client for tag state management."""
import json
from typing import Optional, Dict, List
from datetime import datetime
import redis
import structlog

from core.config import settings
from core.models import TagState

logger = structlog.get_logger()


class RedisClient:
    """Redis client for tag state storage."""
    
    def __init__(self):
        self.client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            password=settings.redis_password if settings.redis_password else None,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_keepalive=True
        )
        self._test_connection()
    
    def _test_connection(self) -> None:
        """Test Redis connection."""
        try:
            self.client.ping()
            logger.info("redis_connected", host=settings.redis_host, port=settings.redis_port)
        except redis.ConnectionError as e:
            logger.error("redis_connection_failed", error=str(e))
            raise
    
    def set_tag_state(self, tag_id: int, tag_name: str, value: float, 
                      timestamp: datetime, quality: str = "GOOD") -> None:
        """Update tag state in Redis."""
        key = f"tag:{tag_id}"
        data = {
            "tag_id": tag_id,
            "tag_name": tag_name,
            "value": value,
            "timestamp": timestamp.isoformat(),
            "quality": quality
        }
        self.client.hset(key, mapping=data)
    
    def get_tag_state(self, tag_id: int) -> Optional[TagState]:
        """Get tag state from Redis."""
        key = f"tag:{tag_id}"
        data = self.client.hgetall(key)
        if not data:
            return None
        
        return TagState(
            tag_id=int(data["tag_id"]),
            tag_name=data["tag_name"],
            value=float(data["value"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            quality=data["quality"]
        )
    
    def get_all_tag_states(self) -> List[TagState]:
        """Get all tag states from Redis."""
        states = []
        for key in self.client.scan_iter("tag:*"):
            data = self.client.hgetall(key)
            if data:
                states.append(TagState(
                    tag_id=int(data["tag_id"]),
                    tag_name=data["tag_name"],
                    value=float(data["value"]),
                    timestamp=datetime.fromisoformat(data["timestamp"]),
                    quality=data["quality"]
                ))
        return states
    
    def get_tag_count(self) -> int:
        """Get total number of tags in Redis."""
        return len(list(self.client.scan_iter("tag:*")))
    
    def publish_event(self, channel: str, event: Dict) -> None:
        """Publish event to Redis pub/sub."""
        self.client.publish(channel, json.dumps(event))
    
    def close(self) -> None:
        """Close Redis connection."""
        self.client.close()
        logger.info("redis_closed")


# Global Redis instance
redis_client = RedisClient()
