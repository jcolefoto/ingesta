"""
Workflow event system for structured event-driven orchestration.

Provides EventBus for publish/subscribe and strongly-typed event classes
for workflow lifecycle and progress tracking.
"""

from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Type, TypeVar
from datetime import datetime
from pathlib import Path


T = TypeVar("T", bound="WorkflowEvent")


class EventType(Enum):
    """Enumeration of all workflow event types."""
    STEP_STARTED = auto()
    STEP_COMPLETED = auto()
    STEP_FAILED = auto()
    STEP_PROGRESS = auto()
    WORKFLOW_STARTED = auto()
    WORKFLOW_COMPLETED = auto()
    WORKFLOW_FAILED = auto()


@dataclass
class WorkflowEvent:
    """Base class for all workflow events.
    
    Attributes:
        event_type: The type of event
        workflow_id: Unique identifier for the workflow
        timestamp: When the event occurred
        metadata: Additional event-specific data
    """
    event_type: EventType
    workflow_id: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary for serialization."""
        return {
            "event_type": self.event_type.name,
            "workflow_id": self.workflow_id,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class StepStartedEvent(WorkflowEvent):
    """Emitted when a workflow step begins execution.
    
    Attributes:
        step_name: Name of the step
        step_index: Index of the step in the workflow sequence
        total_steps: Total number of steps in the workflow
        step_type: Type/class of the step being executed
        input_data: Summary of input data (excluding large payloads)
    """
    step_name: str = ""
    step_index: int = 0
    total_steps: int = 0
    step_type: str = ""
    input_data: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.event_type:
            self.event_type = EventType.STEP_STARTED


@dataclass
class StepCompletedEvent(WorkflowEvent):
    """Emitted when a workflow step completes successfully.
    
    Attributes:
        step_name: Name of the step
        step_index: Index of the step in the workflow sequence
        total_steps: Total number of steps in the workflow
        duration_seconds: Time taken to execute the step
        output_data: Summary of output data (excluding large payloads)
    """
    step_name: str = ""
    step_index: int = 0
    total_steps: int = 0
    duration_seconds: float = 0.0
    output_data: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.event_type:
            self.event_type = EventType.STEP_COMPLETED


@dataclass
class StepFailedEvent(WorkflowEvent):
    """Emitted when a workflow step fails.
    
    Attributes:
        step_name: Name of the step
        step_index: Index of the step in the workflow sequence
        total_steps: Total number of steps in the workflow
        error_message: Human-readable error description
        error_type: Type of exception that occurred
        error_details: Additional error context
    """
    step_name: str = ""
    step_index: int = 0
    total_steps: int = 0
    error_message: str = ""
    error_type: str = ""
    error_details: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.event_type:
            self.event_type = EventType.STEP_FAILED


@dataclass
class StepProgressEvent(WorkflowEvent):
    """Emitted periodically during long-running step execution.
    
    Attributes:
        step_name: Name of the step
        step_index: Index of the step in the workflow sequence
        total_steps: Total number of steps in the workflow
        percent_complete: Progress percentage (0-100)
        current_item: Description of current item being processed
        items_processed: Number of items completed
        items_total: Total number of items to process
        bytes_processed: Bytes processed (for file operations)
        bytes_total: Total bytes to process
        current_speed_mbps: Current processing speed in MB/s
        eta_seconds: Estimated seconds remaining
    """
    step_name: str = ""
    step_index: int = 0
    total_steps: int = 0
    percent_complete: float = 0.0
    current_item: Optional[str] = None
    items_processed: int = 0
    items_total: int = 0
    bytes_processed: int = 0
    bytes_total: int = 0
    current_speed_mbps: Optional[float] = None
    eta_seconds: Optional[float] = None
    
    def __post_init__(self):
        if not self.event_type:
            self.event_type = EventType.STEP_PROGRESS


@dataclass
class WorkflowStartedEvent(WorkflowEvent):
    """Emitted when a workflow begins execution.
    
    Attributes:
        workflow_type: Type/class of the workflow
        total_steps: Total number of steps in the workflow
        input_summary: Summary of input parameters
    """
    workflow_type: str = ""
    total_steps: int = 0
    input_summary: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.event_type:
            self.event_type = EventType.WORKFLOW_STARTED


@dataclass
class WorkflowCompletedEvent(WorkflowEvent):
    """Emitted when a workflow completes successfully.
    
    Attributes:
        workflow_type: Type/class of the workflow
        total_steps: Total number of steps executed
        successful_steps: Number of steps that succeeded
        failed_steps: Number of steps that failed
        duration_seconds: Total workflow execution time
        result_summary: Summary of workflow results
    """
    workflow_type: str = ""
    total_steps: int = 0
    successful_steps: int = 0
    failed_steps: int = 0
    duration_seconds: float = 0.0
    result_summary: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.event_type:
            self.event_type = EventType.WORKFLOW_COMPLETED


@dataclass
class WorkflowFailedEvent(WorkflowEvent):
    """Emitted when a workflow fails.
    
    Attributes:
        workflow_type: Type/class of the workflow
        total_steps: Total number of steps in the workflow
        completed_steps: Number of steps completed before failure
        error_message: Human-readable error description
        error_type: Type of exception that occurred
    """
    workflow_type: str = ""
    total_steps: int = 0
    completed_steps: int = 0
    error_message: str = ""
    error_type: str = ""
    
    def __post_init__(self):
        if not self.event_type:
            self.event_type = EventType.WORKFLOW_FAILED


# Type alias for event handlers
EventHandler = Callable[[WorkflowEvent], None]


class EventBus:
    """Event bus for publish/subscribe pattern.
    
    Allows components to subscribe to specific event types and
    emit events that are dispatched to all matching subscribers.
    
    Example:
        bus = EventBus()
        
        def on_step_started(event: StepStartedEvent) -> None:
            print(f"Step started: {event.step_name}")
        
        bus.subscribe(EventType.STEP_STARTED, on_step_started)
        bus.emit(StepStartedEvent(...))
    """
    
    def __init__(self):
        self._subscribers: Dict[EventType, List[EventHandler]] = {
            event_type: [] for event_type in EventType
        }
        self._global_subscribers: List[EventHandler] = []
    
    def subscribe(
        self, 
        event_type: EventType, 
        handler: EventHandler
    ) -> None:
        """Subscribe a handler to a specific event type.
        
        Args:
            event_type: The event type to subscribe to
            handler: Callback function that receives the event
        """
        self._subscribers[event_type].append(handler)
    
    def subscribe_all(self, handler: EventHandler) -> None:
        """Subscribe a handler to all event types.
        
        Args:
            handler: Callback function that receives all events
        """
        self._global_subscribers.append(handler)
    
    def unsubscribe(
        self, 
        event_type: EventType, 
        handler: EventHandler
    ) -> bool:
        """Unsubscribe a handler from a specific event type.
        
        Args:
            event_type: The event type to unsubscribe from
            handler: The handler to remove
            
        Returns:
            True if handler was found and removed, False otherwise
        """
        if handler in self._subscribers[event_type]:
            self._subscribers[event_type].remove(handler)
            return True
        return False
    
    def unsubscribe_all(self, handler: EventHandler) -> bool:
        """Unsubscribe a handler from all event types.
        
        Args:
            handler: The handler to remove
            
        Returns:
            True if handler was found and removed, False otherwise
        """
        removed = False
        if handler in self._global_subscribers:
            self._global_subscribers.remove(handler)
            removed = True
        
        for handlers in self._subscribers.values():
            if handler in handlers:
                handlers.remove(handler)
                removed = True
        
        return removed
    
    def emit(self, event: WorkflowEvent) -> None:
        """Emit an event to all subscribers.
        
        Args:
            event: The event to emit. Must have event_type set.
        """
        event_type = event.event_type
        
        # Call type-specific subscribers
        for handler in self._subscribers.get(event_type, []):
            try:
                handler(event)
            except Exception as e:
                # Don't let subscriber errors break the chain
                # In production, this should use proper logging
                import logging
                logging.getLogger(__name__).warning(
                    f"Event handler failed for {event_type.name}: {e}"
                )
        
        # Call global subscribers
        for handler in self._global_subscribers:
            try:
                handler(event)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(
                    f"Global event handler failed for {event_type.name}: {e}"
                )
    
    def clear(self) -> None:
        """Remove all subscribers."""
        self._subscribers = {
            event_type: [] for event_type in EventType
        }
        self._global_subscribers.clear()


# Global event bus instance for convenience
default_event_bus = EventBus()


def get_default_event_bus() -> EventBus:
    """Get the default global event bus instance."""
    return default_event_bus
