"""
Workflow engine for orchestrating step execution.

Provides sequential step execution with event emission and context management.
"""

from typing import Any, Dict, List, Optional, Type, Callable
from dataclasses import dataclass, field
from datetime import datetime
import time
import uuid

from .events import (
    EventBus,
    EventType,
    WorkflowEvent,
    WorkflowStartedEvent,
    WorkflowCompletedEvent,
    WorkflowFailedEvent,
    get_default_event_bus,
)
from .context import WorkflowContext
from .steps.base import WorkflowStep, StepResult


@dataclass
class WorkflowResult:
    """Result of workflow execution.
    
    Attributes:
        success: Whether the workflow completed successfully
        workflow_id: Unique identifier for the workflow
        step_results: List of results from each step
        context: Final workflow context state
        duration_seconds: Total execution time
        error_message: Error message if workflow failed
        failed_step_index: Index of the step that failed (-1 if success)
    """
    success: bool
    workflow_id: str
    step_results: List[StepResult] = field(default_factory=list)
    context: Optional[WorkflowContext] = None
    duration_seconds: float = 0.0
    error_message: Optional[str] = None
    failed_step_index: int = -1
    
    @property
    def successful_steps(self) -> int:
        """Count of successful step executions."""
        return sum(1 for r in self.step_results if r.success)
    
    @property
    def failed_steps(self) -> int:
        """Count of failed step executions."""
        return sum(1 for r in self.step_results if not r.success)


class WorkflowEngine:
    """Engine for executing workflows.
    
    The workflow engine orchestrates the execution of a sequence of steps,
    managing context, emitting events, and handling errors.
    
    Features:
    - Sequential step execution
    - Event emission at workflow and step levels
    - Shared context across all steps
    - Error handling with optional continue-on-error
    
    Example:
        # Create steps
        steps = [IngestStep(), AnalysisStep(), ExportStep()]
        
        # Create engine and run
        engine = WorkflowEngine(steps=steps)
        context = WorkflowContext()
        context.set("source", "/path/to/media")
        
        result = engine.run(context)
        
        if result.success:
            print(f"Workflow completed in {result.duration_seconds}s")
    """
    
    def __init__(
        self,
        steps: List[WorkflowStep],
        workflow_id: Optional[str] = None,
        workflow_type: str = "Workflow",
        event_bus: Optional[EventBus] = None,
        continue_on_error: bool = False,
    ):
        """Initialize the workflow engine.
        
        Args:
            steps: List of steps to execute in order
            workflow_id: Unique identifier (generated if not provided)
            workflow_type: Type/name of the workflow
            event_bus: Event bus for emitting events
            continue_on_error: Whether to continue after step failures
        """
        self.steps = steps
        self.workflow_id = workflow_id or str(uuid.uuid4())
        self.workflow_type = workflow_type
        self.event_bus = event_bus or get_default_event_bus()
        self.continue_on_error = continue_on_error
    
    def run(self, context: Optional[WorkflowContext] = None) -> WorkflowResult:
        """Execute the workflow.
        
        Runs all steps sequentially, emitting events and managing context.
        
        Args:
            context: Optional pre-configured context. Creates new one if None.
            
        Returns:
            WorkflowResult with execution details
        """
        start_time = time.time()
        
        # Initialize or update context
        if context is None:
            context = WorkflowContext()
        
        context.workflow_id = self.workflow_id
        context.workflow_type = self.workflow_type
        
        # Initialize result tracking
        step_results: List[StepResult] = []
        failed_index = -1
        error_message = None
        
        # Emit workflow started event
        self._emit_started(context)
        
        # Execute steps
        for i, step in enumerate(self.steps):
            # Configure step with workflow info
            step.configure(
                workflow_id=self.workflow_id,
                step_index=i,
                total_steps=len(self.steps),
            )
            
            # Run the step
            result = step.run(context)
            step_results.append(result)
            
            # Store result in context for downstream steps
            context.set(f"step_{i}_result", result.output)
            context.set(f"step_{step.name}_result", result.output)
            
            # Handle failure
            if not result.success:
                failed_index = i
                error_message = result.error_message
                context.add_error(step.name, result.error_message or "Step failed")
                
                if not self.continue_on_error:
                    # Stop workflow
                    break
        
        # Mark completion
        context.mark_completed()
        duration = time.time() - start_time
        
        # Determine success
        success = failed_index == -1 or (self.continue_on_error and self.successful_steps(step_results) > 0)
        
        # Emit completion/failure event
        if success:
            self._emit_completed(context, step_results, duration)
        else:
            self._emit_failed(context, step_results, duration, error_message or "Workflow failed")
        
        return WorkflowResult(
            success=success,
            workflow_id=self.workflow_id,
            step_results=step_results,
            context=context,
            duration_seconds=duration,
            error_message=error_message,
            failed_step_index=failed_index,
        )
    
    def _emit_started(self, context: WorkflowContext) -> None:
        """Emit workflow started event."""
        event = WorkflowStartedEvent(
            event_type=EventType.WORKFLOW_STARTED,
            workflow_id=self.workflow_id,
            workflow_type=self.workflow_type,
            total_steps=len(self.steps),
            input_summary=self._get_input_summary(context),
        )
        self.event_bus.emit(event)
    
    def _emit_completed(
        self, 
        context: WorkflowContext, 
        step_results: List[StepResult],
        duration: float
    ) -> None:
        """Emit workflow completed event."""
        successful = sum(1 for r in step_results if r.success)
        failed = len(step_results) - successful
        
        event = WorkflowCompletedEvent(
            event_type=EventType.WORKFLOW_COMPLETED,
            workflow_id=self.workflow_id,
            workflow_type=self.workflow_type,
            total_steps=len(self.steps),
            successful_steps=successful,
            failed_steps=failed,
            duration_seconds=duration,
            result_summary=self._get_result_summary(context, step_results),
        )
        self.event_bus.emit(event)

    def _emit_failed(
        self,
        context: WorkflowContext,
        step_results: List[StepResult],
        duration: float,
        error_message: str
    ) -> None:
        """Emit workflow failed event."""
        completed = len(step_results)
        
        event = WorkflowFailedEvent(
            event_type=EventType.WORKFLOW_FAILED,
            workflow_id=self.workflow_id,
            workflow_type=self.workflow_type,
            total_steps=len(self.steps),
            completed_steps=completed,
            error_message=error_message,
            error_type="WorkflowError",
        )
        self.event_bus.emit(event)
    
    def _get_input_summary(self, context: WorkflowContext) -> Dict[str, Any]:
        """Get summary of workflow inputs."""
        return {
            "context_keys": list(context.data.keys())[:10],  # Limit to first 10
            "step_count": len(self.steps),
        }
    
    def _get_result_summary(
        self, 
        context: WorkflowContext, 
        step_results: List[StepResult]
    ) -> Dict[str, Any]:
        """Get summary of workflow results."""
        return {
            "successful_steps": sum(1 for r in step_results if r.success),
            "failed_steps": sum(1 for r in step_results if not r.success),
            "final_context_keys": list(context.data.keys())[:10],
            "has_errors": context.has_errors(),
        }
    
    @staticmethod
    def successful_steps(step_results: List[StepResult]) -> int:
        """Count successful step results."""
        return sum(1 for r in step_results if r.success)


class WorkflowBuilder:
    """Builder for constructing workflows.
    
    Provides a fluent interface for building workflows step by step.
    
    Example:
        workflow = (WorkflowBuilder()
            .with_step(IngestStep())
            .with_step(AnalysisStep())
            .with_step(ExportStep())
            .with_event_bus(custom_bus)
            .build())
        
        result = workflow.run(context)
    """
    
    def __init__(self):
        self._steps: List[WorkflowStep] = []
        self._workflow_id: Optional[str] = None
        self._workflow_type: str = "Workflow"
        self._event_bus: Optional[EventBus] = None
        self._continue_on_error: bool = False
    
    def with_step(self, step: WorkflowStep) -> "WorkflowBuilder":
        """Add a step to the workflow."""
        self._steps.append(step)
        return self
    
    def with_steps(self, steps: List[WorkflowStep]) -> "WorkflowBuilder":
        """Add multiple steps to the workflow."""
        self._steps.extend(steps)
        return self
    
    def with_workflow_id(self, workflow_id: str) -> "WorkflowBuilder":
        """Set the workflow ID."""
        self._workflow_id = workflow_id
        return self
    
    def with_workflow_type(self, workflow_type: str) -> "WorkflowBuilder":
        """Set the workflow type."""
        self._workflow_type = workflow_type
        return self
    
    def with_event_bus(self, event_bus: EventBus) -> "WorkflowBuilder":
        """Set the event bus."""
        self._event_bus = event_bus
        return self
    
    def with_continue_on_error(self, continue_on_error: bool = True) -> "WorkflowBuilder":
        """Set whether to continue after step failures."""
        self._continue_on_error = continue_on_error
        return self
    
    def build(self) -> WorkflowEngine:
        """Build and return the workflow engine."""
        return WorkflowEngine(
            steps=self._steps,
            workflow_id=self._workflow_id,
            workflow_type=self._workflow_type,
            event_bus=self._event_bus,
            continue_on_error=self._continue_on_error,
        )
