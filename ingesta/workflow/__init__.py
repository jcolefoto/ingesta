"""
ingesta.workflow - Workflow Orchestrator for media processing pipelines.

This package provides event-driven workflow orchestration for ingesta,
enabling structured, observable media processing pipelines.

Example:
    from ingesta.workflow import WorkflowEngine, WorkflowContext, IngestStep
    from ingesta.workflow.events import EventBus, EventType
    
    # Create event bus and subscribe to events
    bus = EventBus()
    bus.subscribe(EventType.STEP_PROGRESS, lambda e: print(f"{e.percent_complete:.1f}%"))
    
    # Build and run workflow
    engine = (WorkflowBuilder()
        .with_step(IngestStep())
        .with_event_bus(bus)
        .build())
    
    context = WorkflowContext()
    context.set("source", "/path/to/media")
    context.set("destinations", ["/backup"])
    
    result = engine.run(context)
"""

__version__ = "0.1.0"

# Core workflow components
from .engine import WorkflowEngine, WorkflowResult, WorkflowBuilder
from .context import WorkflowContext

# Event system
from .events import (
    EventBus,
    EventType,
    WorkflowEvent,
    StepStartedEvent,
    StepCompletedEvent,
    StepFailedEvent,
    StepProgressEvent,
    WorkflowStartedEvent,
    WorkflowCompletedEvent,
    WorkflowFailedEvent,
    get_default_event_bus,
)

# Step base class
from .steps.base import WorkflowStep, StepResult

# Available step implementations
from .steps.ingest import IngestStep, IngestStepConfig

__all__ = [
    # Engine
    "WorkflowEngine",
    "WorkflowResult",
    "WorkflowBuilder",
    # Context
    "WorkflowContext",
    # Events
    "EventBus",
    "EventType",
    "WorkflowEvent",
    "StepStartedEvent",
    "StepCompletedEvent",
    "StepFailedEvent",
    "StepProgressEvent",
    "WorkflowStartedEvent",
    "WorkflowCompletedEvent",
    "WorkflowFailedEvent",
    "get_default_event_bus",
    # Steps
    "WorkflowStep",
    "StepResult",
    "IngestStep",
    "IngestStepConfig",
]
