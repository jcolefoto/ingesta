"""
Ingest step wrapper for workflow orchestration.

Wraps the existing ingest_media function as a workflow step,
emitting structured events during ingestion operations.
"""

from typing import Any, Dict, List, Optional, Union
from pathlib import Path
from dataclasses import dataclass

from .base import WorkflowStep, StepResult
from ..context import WorkflowContext
from ...ingestion import (
    ingest_media,
    IngestionJob,
    ProgressEvent as IngestionProgressEvent,
    IngestionStage,
)


@dataclass
class IngestStepConfig:
    """Configuration for the ingest step.
    
    Attributes:
        source_key: Context key for source path (default: "source")
        destinations_key: Context key for destinations (default: "destinations")
        checksum_algorithm: Algorithm for verification
        verify: Whether to verify copies
        include_patterns: File patterns to include
        exclude_patterns: File patterns to exclude
        output_key: Context key to store IngestionJob result
    """
    source_key: str = "source"
    destinations_key: str = "destinations"
    checksum_algorithm: str = "xxhash64"
    verify: bool = True
    include_patterns: Optional[List[str]] = None
    exclude_patterns: Optional[List[str]] = None
    output_key: str = "ingestion_job"


class IngestStep(WorkflowStep):
    """Workflow step wrapper for media ingestion.
    
    This step wraps the existing ingest_media function and integrates
    it with the workflow event system. It reads source/destinations from
    the workflow context and stores the IngestionJob result back to context.
    
    Example:
        # Configure workflow context
        context.set("source", "/path/to/source")
        context.set("destinations", ["/dest1", "/dest2"])
        
        # Create and run ingest step
        step = IngestStep(config=IngestStepConfig())
        result = step.run(context)
        
        # Access results
        job = context.get("ingestion_job")
        print(f"Copied {job.success_count} files")
    """
    
    def __init__(
        self,
        name: str = "IngestStep",
        config: Optional[IngestStepConfig] = None,
        event_bus=None,
    ):
        """Initialize the ingest step.
        
        Args:
            name: Step name
            config: Ingest step configuration
            event_bus: Event bus for workflow events
        """
        super().__init__(name=name, event_bus=event_bus)
        self.config = config or IngestStepConfig()
        self._current_job: Optional[IngestionJob] = None
        self._total_bytes: int = 0
        self._bytes_copied: int = 0
    
    def validate_input(self, context: WorkflowContext) -> Optional[str]:
        """Validate that source and destinations are provided."""
        source = context.get(self.config.source_key)
        destinations = context.get(self.config.destinations_key)
        
        if not source:
            return f"Missing required input: '{self.config.source_key}' not found in context"
        
        if not destinations:
            return f"Missing required input: '{self.config.destinations_key}' not found in context"
        
        # Normalize to list
        if isinstance(destinations, (str, Path)):
            destinations = [destinations]
        
        if len(destinations) == 0:
            return "At least one destination must be provided"
        
        # Validate source exists
        source_path = Path(source)
        if not source_path.exists():
            return f"Source does not exist: {source}"
        
        # Validate destinations are valid paths
        for i, dest in enumerate(destinations):
            try:
                Path(dest)
            except Exception as e:
                return f"Invalid destination path at index {i}: {e}"
        
        return None
    
    def execute(self, context: WorkflowContext) -> StepResult:
        """Execute the ingestion operation.
        
        Args:
            context: Workflow context containing source and destinations
            
        Returns:
            StepResult with ingestion results
        """
        # Get inputs from context
        source = context.get(self.config.source_key)
        destinations_raw = context.get(self.config.destinations_key)
        
        # Normalize and validate inputs
        if source is None:
            return StepResult.failure_result("Source is None")
        
        # Normalize destinations to list of strings
        if isinstance(destinations_raw, (str, Path)):
            destinations: List[Union[str, Path]] = [destinations_raw]
        elif isinstance(destinations_raw, list):
            destinations = destinations_raw
        else:
            return StepResult.failure_result(f"Invalid destinations type: {type(destinations_raw)}")
        
        if len(destinations) == 0:
            return StepResult.failure_result("No destinations provided")
        
        # Reset tracking
        self._total_bytes = 0
        self._bytes_copied = 0
        
        # Run ingestion with progress callback
        try:
            job = ingest_media(
                source=str(source),
                destinations=[str(d) for d in destinations],
                checksum_algorithm=self.config.checksum_algorithm,
                verify=self.config.verify,
                include_patterns=self.config.include_patterns,
                exclude_patterns=self.config.exclude_patterns,
                progress_event_callback=self._on_ingestion_progress,
            )
            
            # Store job in context
            context.set(self.config.output_key, job)
            
            # Build result
            result_data = {
                "source_file_count": len(set(f.source_path for f in job.files_processed)),
                "destination_count": len(destinations),
                "total_operations": len(job.files_processed),
                "successful_operations": job.success_count,
                "failed_operations": job.failure_count,
                "total_bytes": job.total_bytes,
                "safe_to_format": job.is_safe_to_format,
                "duration_seconds": job.get_completion().duration_seconds if job.start_time and job.end_time else 0,
            }
            
            # Add completion info
            completion = job.get_completion()
            result_data["completion"] = {
                "checksum_algorithm": completion.checksum_algorithm,
                "files": len(completion.files),
            }
            
            if job.failure_count > 0:
                return StepResult.failure_result(
                    message=f"Ingestion completed with {job.failure_count} failures",
                    details=result_data,
                    output=result_data
                )
            
            return StepResult.success_result(output=result_data)
            
        except Exception as e:
            return StepResult.failure_result(
                message=f"Ingestion failed: {str(e)}",
                details={"error_type": type(e).__name__}
            )
    
    def _on_ingestion_progress(self, event: IngestionProgressEvent) -> None:
        """Convert ingestion progress events to workflow progress events.
        
        Args:
            event: Progress event from the ingestion module
        """
        # Map ingestion stage to progress percentage ranges
        stage_progress = {
            IngestionStage.SCANNING: 5,
            IngestionStage.COPYING: 50,
            IngestionStage.VERIFYING: 90,
            IngestionStage.COMPLETE: 100,
        }
        
        # Calculate overall progress
        base_progress = stage_progress.get(event.stage, 0)
        
        if event.stage == IngestionStage.COPYING and event.total_bytes > 0:
            # Calculate detailed progress during copying
            file_progress = (event.bytes_copied / event.total_bytes) * 45  # Up to 45% for copying
            
            # Factor in which file we're on
            if event.total_source_files > 0:
                file_weight = 45 / event.total_source_files
                overall_file_progress = (event.current_file_index / event.total_source_files) * 45
                base_progress = 5 + overall_file_progress + file_progress
            else:
                base_progress = 5 + file_progress
        
        elif event.stage == IngestionStage.VERIFYING and event.total_source_files > 0:
            # Progress through verification
            verification_progress = (event.current_file_index / event.total_source_files) * 10
            base_progress = 50 + 40 + verification_progress  # 50 (copy) + 40 (base verify) + progress
        
        # Get current item description
        current_item = None
        if event.source_file:
            current_item = event.source_file.name
        
        # Emit workflow progress event
        self.emit_progress(
            percent_complete=min(base_progress, 99.9),  # Reserve 100% for completion
            current_item=current_item,
            items_processed=event.current_file_index,
            items_total=event.total_source_files,
            bytes_processed=event.bytes_copied,
            bytes_total=event.total_bytes,
            current_speed_mbps=event.current_speed_mb_s,
            eta_seconds=event.eta_seconds,
        )
    
    def _get_input_summary(self, context: WorkflowContext) -> Dict[str, Any]:
        """Get summary of ingestion inputs."""
        source = context.get(self.config.source_key)
        destinations = context.get(self.config.destinations_key)
        
        if isinstance(destinations, (str, Path)):
            destinations = [destinations]
        
        return {
            "source": str(source) if source else None,
            "destination_count": len(destinations) if destinations else 0,
            "checksum_algorithm": self.config.checksum_algorithm,
            "verify": self.config.verify,
        }
    
    def _get_output_summary(self, result: StepResult) -> Dict[str, Any]:
        """Get summary of ingestion outputs."""
        if result.output:
            return {
                "source_file_count": result.output.get("source_file_count"),
                "successful_operations": result.output.get("successful_operations"),
                "failed_operations": result.output.get("failed_operations"),
                "safe_to_format": result.output.get("safe_to_format"),
                "total_bytes": result.output.get("total_bytes"),
            }
        return {}
