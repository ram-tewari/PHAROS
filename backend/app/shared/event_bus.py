"""
Shared event bus for inter-module communication.

Implements publish-subscribe pattern with synchronous delivery.
Provides error isolation, metrics tracking, and logging.
"""

from typing import Callable, Dict, List, Any, Optional
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
import logging
import time
import uuid

logger = logging.getLogger(__name__)


class EventPriority(Enum):
    """Event priority levels for logging and metrics."""

    CRITICAL = 100
    HIGH = 75
    NORMAL = 50
    LOW = 25


@dataclass
class Event:
    """Represents a system event with metadata (for API compatibility)."""

    name: str
    data: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    priority: EventPriority = EventPriority.NORMAL
    correlation_id: Optional[str] = field(default_factory=lambda: str(uuid.uuid4()))


class EventBus:
    """
    Synchronous event bus for module communication.

    Features:
    - Type-safe event names
    - Priority-based delivery
    - Error isolation (handler failures don't affect other handlers)
    - Logging and metrics tracking
    - Handler execution time tracking
    - Singleton pattern for global event bus
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        """Ensure singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize event bus with empty handlers and metrics (only once due to singleton)."""
        if not EventBus._initialized:
            from collections import deque

            self._handlers: Dict[str, List[Callable]] = {}
            self._metrics = {
                "events_emitted": 0,
                "events_delivered": 0,
                "handler_errors": 0,
                "total_handler_time_ms": 0.0,
                "total_emission_time_ms": 0.0,
            }
            self._event_types: Dict[str, int] = {}
            self._handler_latencies: List[float] = []
            self._emission_latencies: List[float] = []
            self._event_history: deque = deque(maxlen=1000)
            EventBus._initialized = True
            logger.info("EventBus initialized")

    def subscribe(
        self, event_type: str, handler: Callable[[Dict[str, Any]], None]
    ) -> None:
        """
        Subscribe to an event type.

        Args:
            event_type: Event type to subscribe to (e.g., "resource.deleted")
            handler: Callable that receives event payload as dict
        """
        if event_type not in self._handlers:
            self._handlers[event_type] = []

        # Avoid duplicate registrations
        if handler not in self._handlers[event_type]:
            self._handlers[event_type].append(handler)
            logger.info(
                f"Subscribed handler '{handler.__name__}' to event '{event_type}'"
            )

    def on(
        self, event_name: str, handler: Callable, async_handler: bool = False
    ) -> None:
        """
        Register an event listener (alias for subscribe for API compatibility).

        Args:
            event_name: Name of the event to listen for
            handler: Callback function to execute when event is emitted
            async_handler: Whether the handler is async (ignored in EventBus, for compatibility)
        """
        self.subscribe(event_name, handler)

    def unsubscribe(
        self, event_type: str, handler: Callable[[Dict[str, Any]], None]
    ) -> None:
        """
        Unsubscribe from an event type.

        Args:
            event_type: Event type to unsubscribe from
            handler: Handler function to remove
        """
        if event_type in self._handlers:
            self._handlers[event_type] = [
                h for h in self._handlers[event_type] if h != handler
            ]
            logger.info(
                f"Unsubscribed handler '{handler.__name__}' from event '{event_type}'"
            )

    def off(self, event_name: str, handler: Callable) -> None:
        """
        Unregister an event listener (alias for unsubscribe for API compatibility).

        Args:
            event_name: Name of the event
            handler: Handler function to remove
        """
        self.unsubscribe(event_name, handler)

    def emit(
        self,
        event_type: str,
        payload: Dict[str, Any],
        priority: EventPriority = EventPriority.NORMAL,
    ) -> Event:
        """
        Emit an event to all subscribers.

        Implements error isolation - handler failures don't affect other handlers.
        Tracks metrics for monitoring and performance analysis.

        Args:
            event_type: Event type to emit (e.g., "resource.deleted")
            payload: Event data as dictionary
            priority: Event priority (for logging/metrics)

        Returns:
            The emitted Event object
        """
        # Track emission start time for performance monitoring
        emission_start_time = time.time()

        # Create Event object for API compatibility
        event = Event(name=event_type, data=payload, priority=priority)

        self._metrics["events_emitted"] += 1

        # Track event types
        if event_type not in self._event_types:
            self._event_types[event_type] = 0
        self._event_types[event_type] += 1

        logger.debug(
            f"Emitting event '{event_type}' with priority {priority.name}",
            extra={
                "component": "event_bus",
                "operation": "event_emission",
                "event_type": event_type,
                "priority": priority.name,
                "payload": payload,
                "correlation_id": event.correlation_id,
            },
        )

        # Store in history (deque automatically maintains maxlen of 1000)
        from datetime import timezone

        self._event_history.append(
            {
                "name": event_type,
                "data": payload,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "priority": priority.name,
                "correlation_id": event.correlation_id,
            }
        )

        handlers = self._handlers.get(event_type, [])

        if not handlers:
            logger.debug(f"No handlers registered for event '{event_type}'")
            return event

        for handler in handlers:
            start_time = time.time()
            try:
                # Try to call handler with Event object first (new API)
                # Fall back to dict payload for backward compatibility
                import inspect

                sig = inspect.signature(handler)
                pass_event_object = False

                if len(sig.parameters) > 0:
                    first_param = list(sig.parameters.values())[0]
                    annotation = first_param.annotation

                    # Check if handler explicitly requests Event object via type hint
                    if annotation is not inspect.Parameter.empty and (
                        annotation is Event
                        or str(annotation) == "Event"
                        or str(annotation).endswith(".Event")
                    ):
                        pass_event_object = True

                if pass_event_object:
                    handler(event)
                else:
                    # Fallback to dict payload for backward compatibility
                    handler(payload)

                # Track successful delivery
                self._metrics["events_delivered"] += 1

                # Track handler execution time
                execution_time_ms = (time.time() - start_time) * 1000
                self._metrics["total_handler_time_ms"] += execution_time_ms
                self._handler_latencies.append(execution_time_ms)

                # Keep only last 1000 latencies for percentile calculation
                if len(self._handler_latencies) > 1000:
                    self._handler_latencies = self._handler_latencies[-1000:]

                # Structured logging for successful handler execution
                logger.debug(
                    f"Event handler executed: '{handler.__name__}' for '{event_type}'",
                    extra={
                        "component": "event_bus",
                        "operation": "handler_execution",
                        "event_type": event_type,
                        "handler": handler.__name__,
                        "duration_ms": round(execution_time_ms, 2),
                        "status": "success",
                    },
                )

                # Log warning for slow handlers
                if execution_time_ms > 100:
                    logger.warning(
                        f"Slow event handler detected: '{handler.__name__}' for '{event_type}' "
                        f"took {execution_time_ms:.2f}ms",
                        extra={
                            "component": "event_bus",
                            "operation": "slow_handler",
                            "event_type": event_type,
                            "handler": handler.__name__,
                            "duration_ms": round(execution_time_ms, 2),
                            "threshold_ms": 100,
                        },
                    )

            except Exception as e:
                # Log error but continue to next handler (error isolation)
                self._metrics["handler_errors"] += 1
                logger.error(
                    f"Handler error: '{handler.__name__}' for event '{event_type}': {e}",
                    exc_info=True,
                    extra={
                        "component": "event_bus",
                        "operation": "handler_error",
                        "event_type": event_type,
                        "handler": handler.__name__,
                        "error": str(e),
                        "status": "error",
                    },
                )

        # Track total emission time (including all handler executions)
        total_emission_time_ms = (time.time() - emission_start_time) * 1000
        self._metrics["total_emission_time_ms"] += total_emission_time_ms
        self._emission_latencies.append(total_emission_time_ms)

        # Keep only last 1000 emission latencies for percentile calculation
        if len(self._emission_latencies) > 1000:
            self._emission_latencies = self._emission_latencies[-1000:]

        # Log structured info about emission completion
        logger.debug(
            f"Event emission completed: '{event_type}' delivered to {len(handlers)} handlers",
            extra={
                "component": "event_bus",
                "operation": "emission_complete",
                "event_type": event_type,
                "handlers_count": len(handlers),
                "total_duration_ms": round(total_emission_time_ms, 2),
            },
        )

        return event

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get event bus metrics for monitoring.

        Returns:
            dict: Metrics including:
                - events_emitted: Total events emitted
                - events_delivered: Total successful handler executions
                - handler_errors: Total handler failures
                - total_handler_time_ms: Cumulative handler execution time
                - total_emission_time_ms: Cumulative emission time (including handlers)
                - event_types: Breakdown of events by type
                - handler_latency_p50: 50th percentile handler latency (ms)
                - handler_latency_p95: 95th percentile handler latency (ms)
                - handler_latency_p99: 99th percentile handler latency (ms)
                - emission_latency_p50: 50th percentile emission latency (ms)
                - emission_latency_p95: 95th percentile emission latency (ms)
                - emission_latency_p99: 99th percentile emission latency (ms)
        """
        metrics = self._metrics.copy()
        metrics["event_types"] = self._event_types.copy()

        # Calculate handler latency percentiles
        if self._handler_latencies:
            sorted_latencies = sorted(self._handler_latencies)
            n = len(sorted_latencies)

            metrics["handler_latency_p50"] = round(sorted_latencies[int(n * 0.50)], 2)
            metrics["handler_latency_p95"] = round(sorted_latencies[int(n * 0.95)], 2)
            metrics["handler_latency_p99"] = round(sorted_latencies[int(n * 0.99)], 2)
        else:
            metrics["handler_latency_p50"] = 0.0
            metrics["handler_latency_p95"] = 0.0
            metrics["handler_latency_p99"] = 0.0

        # Calculate emission latency percentiles
        if self._emission_latencies:
            sorted_emission = sorted(self._emission_latencies)
            n = len(sorted_emission)

            metrics["emission_latency_p50"] = round(sorted_emission[int(n * 0.50)], 2)
            metrics["emission_latency_p95"] = round(sorted_emission[int(n * 0.95)], 2)
            metrics["emission_latency_p99"] = round(sorted_emission[int(n * 0.99)], 2)
        else:
            metrics["emission_latency_p50"] = 0.0
            metrics["emission_latency_p95"] = 0.0
            metrics["emission_latency_p99"] = 0.0

        return metrics

    def get_handlers(self, event_type: str) -> List[Callable]:
        """
        Get all registered handlers for an event type.

        Args:
            event_type: Event type to query

        Returns:
            List of handler functions
        """
        return self._handlers.get(event_type, []).copy()

    def get_listeners(self, event_name: str) -> List[Callable]:
        """
        Get all registered listeners for an event (alias for get_handlers).

        Args:
            event_name: Name of the event

        Returns:
            List of handler functions
        """
        return self.get_handlers(event_name)

    def clear_handlers(self, event_type: str | None = None) -> None:
        """
        Clear handlers for testing purposes.

        Args:
            event_type: Specific event to clear, or None to clear all
        """
        if event_type:
            self._handlers[event_type] = []
            logger.debug(f"Cleared handlers for event '{event_type}'")
        else:
            self._handlers.clear()
            logger.debug("Cleared all event handlers")

    def clear_listeners(self, event_name: str | None = None) -> None:
        """
        Clear listeners (alias for clear_handlers for API compatibility).

        Args:
            event_name: Specific event to clear, or None to clear all
        """
        self.clear_handlers(event_name)

    def get_subscribers(self, event_type: str | None = None) -> dict:
        """
        Get subscribers for testing/debugging.

        Args:
            event_type: Specific event to get subscribers for, or None for all

        Returns:
            Dictionary mapping event names to lists of handler functions
        """
        if event_type:
            return {event_type: self._handlers.get(event_type, []).copy()}

        # Return all subscribers
        return {event: handlers.copy() for event, handlers in self._handlers.items()}

    def clear_subscribers(self, event_type: str | None = None) -> None:
        """
        Clear subscribers (alias for clear_handlers for API consistency).

        Args:
            event_type: Specific event to clear, or None to clear all
        """
        self.clear_handlers(event_type)

    def reset_metrics(self) -> None:
        """Reset metrics for testing purposes."""
        self._metrics = {
            "events_emitted": 0,
            "events_delivered": 0,
            "handler_errors": 0,
            "total_handler_time_ms": 0.0,
            "total_emission_time_ms": 0.0,
        }
        self._event_types.clear()
        self._handler_latencies.clear()
        self._emission_latencies.clear()
        logger.debug("Reset event bus metrics")

    def get_event_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get recent event history.

        Args:
            limit: Maximum number of events to return

        Returns:
            List of event dictionaries with name, data, timestamp, priority
        """
        if not self._event_history:
            return []
        # Convert deque to list and slice
        history_list = list(self._event_history)
        return history_list[-limit:] if len(history_list) > limit else history_list

    def clear_history(self) -> None:
        """Clear event history for testing purposes."""
        self._event_history.clear()
        logger.debug("Cleared event history")


# Global event bus instance
event_bus = EventBus()
