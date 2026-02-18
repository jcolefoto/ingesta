"""
Base step class for workflow orchestration.

Provides the foundation for all workflow steps with lifecycle hooks,
event emission, and context integration.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, TypeVar, Generic
from dataclasses import dataclass, field
from datetime import datetime
import time

from ..events import (
    EventBus,
    EventType,
    StepStartedEvent,
    StepCompletedEvent,
    StepFailedEvent,
    StepProgressEvent,
    get_default_event_bus,
)
from ..context import WorkflowContext


T = TypeVar("T")


@dataclass
class StepResult:
    """Result of step execution.
    
    Attributes:
        success: Whether the step completed successfully
        output: Output data produced by the step
        error_message: Error message if step failed
        error_details: Additional error information
        duration_seconds: Time taken to execute the step
    """
    success: bool
    output: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None
    duration_seconds: float = 0.0
    
    @classmethod
    def success_result(cls, output: Optional[Dict[str, Any]] = None, **kwargs) -> "StepResult":
        """Create a successful result.
        
        Args:
            output: Output data
            **kwargs: Additional fields
            
        Returns:
            StepResult with success=True
        """
        return cls(success=True, output=output or {}, **kwargs)
    
    @classmethod
    def failure_result(
        cls, 
        message: str, 
        details: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> "StepResult":
        """Create a failure result.
        
        Args:
            message: Error message
            details: Additional error details
            **kwargs: Additional fields
            
        Returns:
            StepResult with success=False
        """
        return cls(
            success=False, 
            error_message=message, 
            error_details=details,
            **kwargs
        )


class WorkflowStep(ABC):
    """Abstract base class for all workflow steps.
    
    Steps are the building blocks of workflows. Each step represents
    a discrete unit of work that can be executed independently.
    
    To create a custom step:
        1. Subclass WorkflowStep
        2. Implement the `execute` method
        3. Optionally override `validate_input` and `on_failure`
    
    Example:
        class MyStep(WorkflowStep):
            def execute(self, context: WorkflowContext) -> StepResult:
                # Do work
                return StepResult.success_result({"key": "value"})
    """
    
    def __init__(
        self,
        name: Optional[str] = None,
        event_bus: Optional[EventBus] = None,
    ):
        """Initialize the step.
        
        Args:
            name: Step name (defaults to class name)
            event_bus: Event bus for emitting events (defaults to global)
        """
        self.name = name or self.__class__.__name__
        self._event_bus = event_bus or get_default_event_bus()
        self._step_index = 0
        self._total_steps = 0
        self._workflow_id = ""
    
    @property
    def step_type(self) -> str:
        """Get the step type identifier."""
        return self.__class__.__name__
    
    def configure(
        self,
        workflow_id: str,
        step_index: int,
        total_steps: int,
    ) -> None:
        """Configure step with workflow context.
        
        Called by the workflow engine before execution.
        
        Args:
            workflow_id: Unique workflow identifier
            step_index: Index of this step in the workflow
            total_steps: Total number of steps in the workflow
        """
        self._workflow_id = workflow_id
        self._step_index = step_index
        self._total_steps = total_steps
    
    def validate_input(self, context: WorkflowContext) -> Optional[str]:
        """Validate that required inputs exist in context.
        
        Override this method to add custom validation logic.
        Return an error message string if validation fails, None otherwise.
        
        Args:
            context: The workflow context
            
        Returns:
            Error message if invalid, None if valid
        """
        return None
    
    @abstractmethod
    def execute(self, context: WorkflowContext) -> StepResult:
        """Execute the step's main logic.
        
        This method must be implemented by subclasses.
        
        Args:
            context: The workflow context containing shared state
            
        Returns:
            StepResult indicating success/failure and output data
        """
        pass
    
    def on_failure(
        self, 
        context: WorkflowContext, 
        error: Exception
    ) -> None:
        """Handle step failure.
        
        Override to add custom cleanup or recovery logic.
        Called after a step fails but before the failure event is emitted.
        
        Args:
            context: The workflow context
            error: The exception that caused the failure
        """
        pass
    
    def emit_progress(
        self,
        percent_complete: float,
        current_item: Optional[str] = None,
        items_processed: int = 0,
        items_total: int = 0,
        bytes_processed: int = 0,
        bytes_total: int = 0,
        current_speed_mbps: Optional[float] = None,
        eta_seconds: Optional[float] = None,
    ) -> None:
        """Emit a progress event during step execution.
        
        Call this method from within execute() to report progress
        for long-running operations.
        
        Args:
            percent_complete: Progress percentage (0-100)
            current_item: Description of current item
            items_processed: Number of items completed
            items_total: Total number of items
            bytes_processed: Bytes processed
            bytes_total: Total bytes
            current_speed_mbps: Current speed in MB/s
            eta_seconds: Estimated seconds remaining
        """
        event = StepProgressEvent(
            event_type=EventType.STEP_PROGRESS,
            workflow_id=self._workflow_id,
            step_name=self.name,
            step_index=self._step_index,
            total_steps=self._total_steps,
            percent_complete=percent_complete,
            current_item=current_item,
            items_processed=items_processed,
            items_total=items_total,
            bytes_processed=bytes_processed,
            bytes_total=bytes_total,
            current_speed_mbps=current_speed_mbps,
            eta_seconds=eta_seconds,
        )
        self._event_bus.emit(event)
    
    def run(self, context: WorkflowContext) -> StepResult:
        """Run the step with event emission and error handling.
        
        This method is called by the workflow engine. It handles:
        - Input validation
        - Event emission (started, completed, failed)
        - Timing
        - Error handling
        
        Args:
            context: The workflow context
            
        Returns:
            StepResult indicating success/failure
        """
        start_time = time.time()
        
        # Validate input
        validation_error = self.validate_input(context)
        if validation_error:
            result = StepResult.failure_result(
                message=f"Input validation failed: {validation_error}",
                details={"validation_error": validation_error}
            )
            self._emit_failed(result, start_time)
            return result
        
        # Emit started event
        self._emit_started(context)
        
        try:
            # Execute step logic
            result = self.execute(context)
            result.duration_seconds = time.time() - start_time
            
            # Emit completed event
            if result.success:
                self._emit_completed(result, start_time)
            else:
                self._emit_failed(result, start_time)
            
            return result
            
        except Exception as e:
            # Handle unexpected errors
            duration = time.time() - start_time
            self.on_failure(context, e)
            
            result = StepResult.failure_result(
                message=str(e),
                details={
                    "error_type": type(e).__name__,
                    "traceback": self._get_traceback(),
                },
                duration_seconds=duration
            )
            
            self._emit_failed(result, start_time, exception=e)
            return result
    
    def _emit_started(self, context: WorkflowContext) -> None:
        """Emit step started event."""
        event = StepStartedEvent(
            event_type=EventType.STEP_STARTED,
            workflow_id=self._workflow_id,
            step_name=self.name,
            step_index=self._step_index,
            total_steps=self._total_steps,
            step_type=self.step_type,
            input_data=self._get_input_summary(context),
        )
        self._event_bus.emit(event)
    
    def _emit_completed(self, result: StepResult, start_time: float) -> None:
        """Emit step completed event."""
        duration = time.time() - start_time
        event = StepCompletedEvent(
            event_type=EventType.STEP_COMPLETED,
            workflow_id=self._workflow_id,
            step_name=self.name,
            step_index=self._step_index,
            total_steps=self._total_steps,
            duration_seconds=duration,
            output_data=self._get_output_summary(result),
        )
        self._event_bus.emit(event)
    
    def _emit_failed(
        self, 
        result: StepResult, 
        start_time: float,
        exception: Optional[Exception] = None
    ) -> None:
        """Emit step failed event."""
        duration = time.time() - start_time
        event = StepFailedEvent(
            event_type=EventType.STEP_FAILED,
            workflow_id=self._workflow_id,
            step_name=self.name,
            step_index=self._step_index,
            total_steps=self._total_steps,
            error_message=result.error_message or "Unknown error",
            error_type=type(exception).__name__ if exception else "StepError",
            error_details=result.error_details or {},
        )
        self._event_bus.emit(event)
    
    def _get_input_summary(self, context: WorkflowContext) -> Dict[str, Any]:
        """Get a summary of input data for event emission.
        
        Override to customize what input data is included in events.
        Be careful not to include sensitive or large data.
        
        Args:
            context: The workflow context
            
        Returns:
            Dictionary summarizing inputs
        """
        return {"context_keys": list(context.data.keys())}
    
    def _get_output_summary(self, result: StepResult) -> Dict[str, Any]:
        """Get a summary of output data for event emission.
        
        Override to customize what output data is included in events.
        Be careful not to include sensitive or large data.
        
        Args:
            result: The step result
            
        Returns:
            Dictionary summarizing outputs
        """
        return {"output_keys": list(result.output.keys()) if result.output else []}
    
    def _get_traceback(self) -> Optional[str]:
        """Get current exception traceback as string."""
        import traceback
        import sys
        exc_type, exc_value, exc_tb = sys.exc_info()
        if exc_tb:
            return "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        return None
