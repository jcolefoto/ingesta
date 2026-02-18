"""
Workflow context for maintaining state across step executions.

Provides a shared context object that steps can read from and write to,
enabling data flow between steps in a workflow.
"""

from typing import Any, Dict, List, Optional, TypeVar, Union
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
import uuid


T = TypeVar("T")


@dataclass
class WorkflowContext:
    """Shared context for workflow execution.
    
    Maintains state across step executions, allowing steps to:
    - Store results for downstream steps
    - Access configuration and input parameters
    - Track execution metadata
    
    The context is passed to each step during execution, and steps
    can read/write arbitrary key-value data.
    
    Attributes:
        workflow_id: Unique identifier for this workflow execution
        workflow_type: Type/class name of the workflow
        started_at: When the workflow started
        completed_at: When the workflow completed (None if running)
        data: Shared data store (use get/set methods)
        errors: List of errors encountered during execution
        metadata: Workflow-level metadata
    """
    workflow_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    workflow_type: str = ""
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    data: Dict[str, Any] = field(default_factory=dict)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def get(self, key: str, default: Optional[T] = None) -> Optional[T]:
        """Get a value from the context data store.
        
        Args:
            key: The key to look up
            default: Default value if key not found
            
        Returns:
            The stored value or default
        """
        return self.data.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """Set a value in the context data store.
        
        Args:
            key: The key to store under
            value: The value to store
        """
        self.data[key] = value
    
    def has(self, key: str) -> bool:
        """Check if a key exists in the context data store.
        
        Args:
            key: The key to check
            
        Returns:
            True if the key exists
        """
        return key in self.data
    
    def delete(self, key: str) -> bool:
        """Delete a key from the context data store.
        
        Args:
            key: The key to delete
            
        Returns:
            True if key was found and deleted, False otherwise
        """
        if key in self.data:
            del self.data[key]
            return True
        return False
    
    def update(self, updates: Dict[str, Any]) -> None:
        """Update multiple values at once.
        
        Args:
            updates: Dictionary of key-value pairs to update
        """
        self.data.update(updates)
    
    def get_path(self, key: str, default: Optional[Path] = None) -> Optional[Path]:
        """Get a value as a Path object.
        
        Args:
            key: The key to look up
            default: Default value if key not found
            
        Returns:
            The stored value as Path, or default
        """
        value = self.data.get(key, default)
        if value is None:
            return default
        return Path(value) if not isinstance(value, Path) else value
    
    def get_list(self, key: str, default: Optional[List[T]] = None) -> List[T]:
        """Get a value as a list.
        
        Args:
            key: The key to look up
            default: Default value if key not found
            
        Returns:
            The stored value as list, or default
        """
        value = self.data.get(key, default or [])
        if value is None:
            return []
        return list(value) if not isinstance(value, list) else value
    
    def append(self, key: str, value: Any) -> None:
        """Append a value to a list in the context.
        
        Creates the list if it doesn't exist.
        
        Args:
            key: The key for the list
            value: Value to append
        """
        if key not in self.data:
            self.data[key] = []
        if not isinstance(self.data[key], list):
            self.data[key] = [self.data[key]]
        self.data[key].append(value)
    
    def extend(self, key: str, values: List[Any]) -> None:
        """Extend a list in the context with multiple values.
        
        Creates the list if it doesn't exist.
        
        Args:
            key: The key for the list
            values: Values to extend with
        """
        if key not in self.data:
            self.data[key] = []
        if not isinstance(self.data[key], list):
            self.data[key] = [self.data[key]]
        self.data[key].extend(values)
    
    def add_error(
        self, 
        step_name: str, 
        error: Union[str, Exception],
        **kwargs
    ) -> None:
        """Record an error that occurred during execution.
        
        Args:
            step_name: Name of the step where the error occurred
            error: The error message or exception
            **kwargs: Additional error context
        """
        error_info = {
            "step_name": step_name,
            "timestamp": datetime.now().isoformat(),
            "error": str(error),
            "error_type": type(error).__name__ if isinstance(error, Exception) else "Unknown",
        }
        error_info.update(kwargs)
        self.errors.append(error_info)
    
    def has_errors(self) -> bool:
        """Check if any errors have been recorded.
        
        Returns:
            True if errors exist
        """
        return len(self.errors) > 0
    
    def get_errors(self, step_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get recorded errors, optionally filtered by step.
        
        Args:
            step_name: If provided, only return errors from this step
            
        Returns:
            List of error dictionaries
        """
        if step_name:
            return [e for e in self.errors if e.get("step_name") == step_name]
        return self.errors.copy()
    
    def mark_completed(self) -> None:
        """Mark the workflow as completed."""
        self.completed_at = datetime.now()
    
    @property
    def duration_seconds(self) -> Optional[float]:
        """Get the workflow duration in seconds.
        
        Returns:
            Duration if workflow has completed, None otherwise
        """
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert context to dictionary for serialization.
        
        Note: Complex objects in data may not serialize cleanly.
        
        Returns:
            Dictionary representation of the context
        """
        return {
            "workflow_id": self.workflow_id,
            "workflow_type": self.workflow_type,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "has_errors": self.has_errors(),
            "error_count": len(self.errors),
            "data_keys": list(self.data.keys()),
            "metadata": self.metadata,
        }
