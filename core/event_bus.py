"""Event bus for publishing tag update events."""
from typing import Callable, List
import structlog

from core.models import TagUpdatedEvent
from infra.redis_client import redis_client

logger = structlog.get_logger()


class EventBus:
    """In-process and Redis-based event bus."""
    
    def __init__(self):
        self._subscribers: List[Callable[[TagUpdatedEvent], None]] = []
        self._event_count = 0
    
    def subscribe(self, handler: Callable[[TagUpdatedEvent], None]) -> None:
        """Subscribe to tag update events."""
        self._subscribers.append(handler)
        logger.info("event_subscriber_added", handler=handler.__name__)
    
    def publish(self, event: TagUpdatedEvent) -> None:
        """Publish tag update event."""
        # In-process subscribers
        for subscriber in self._subscribers:
            try:
                subscriber(event)
            except Exception as e:
                logger.error("event_subscriber_error", 
                           handler=subscriber.__name__, 
                           error=str(e))
        
        # Redis pub/sub for external consumers
        try:
            redis_client.publish_event("tag_updates", event.model_dump(mode='json'))
            self._event_count += 1
        except Exception as e:
            logger.error("redis_publish_error", error=str(e))
    
    def get_event_count(self) -> int:
        """Get total events published."""
        return self._event_count


# Global event bus instance
event_bus = EventBus()
