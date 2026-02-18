"""
Project/shoot day management module for ingesta.

Manages projects, shoot days, and their associated media offloads.
Provides consolidated reporting for entire projects.

Storage: JSON-based project database in ~/.ingesta/projects/
"""

import json
import uuid
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime


# Default storage location
DEFAULT_PROJECTS_DIR = Path.home() / ".ingesta" / "projects"


@dataclass
class IngestSession:
    """Represents a single offload/ingest session."""
    session_id: str
    timestamp: str
    source_path: str
    destination_paths: List[str]
    files_count: int
    total_size_bytes: int
    notes: Optional[str] = None
    card_label: Optional[str] = None  # e.g., "A001", "Card 1"
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'IngestSession':
        return cls(**data)


@dataclass
class ShootDay:
    """Represents a shoot day within a project."""
    shoot_day_id: str
    date: str  # ISO format YYYY-MM-DD
    label: str  # e.g., "Day 1", "Shoot Day A"
    description: Optional[str] = None
    location: Optional[str] = None
    sessions: List[IngestSession] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    @property
    def total_files(self) -> int:
        return sum(s.files_count for s in self.sessions)
    
    @property
    def total_size_bytes(self) -> int:
        return sum(s.total_size_bytes for s in self.sessions)
    
    def to_dict(self) -> Dict:
        return {
            'shoot_day_id': self.shoot_day_id,
            'date': self.date,
            'label': self.label,
            'description': self.description,
            'location': self.location,
            'sessions': [s.to_dict() for s in self.sessions],
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'ShootDay':
        sessions = [IngestSession.from_dict(s) for s in data.get('sessions', [])]
        return cls(
            shoot_day_id=data['shoot_day_id'],
            date=data['date'],
            label=data['label'],
            description=data.get('description'),
            location=data.get('location'),
            sessions=sessions,
            created_at=data.get('created_at', datetime.now().isoformat()),
            updated_at=data.get('updated_at', datetime.now().isoformat()),
        )


@dataclass
class Project:
    """Represents a production project."""
    project_id: str
    name: str
    client: Optional[str] = None
    director: Optional[str] = None
    producer: Optional[str] = None
    dp: Optional[str] = None  # Director of Photography
    description: Optional[str] = None
    base_directory: Optional[str] = None
    shoot_days: List[ShootDay] = field(default_factory=list)
    status: str = "active"  # active, completed, archived
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    @property
    def total_shoot_days(self) -> int:
        return len(self.shoot_days)
    
    @property
    def total_sessions(self) -> int:
        return sum(len(sd.sessions) for sd in self.shoot_days)
    
    @property
    def total_files(self) -> int:
        return sum(sd.total_files for sd in self.shoot_days)
    
    @property
    def total_size_bytes(self) -> int:
        return sum(sd.total_size_bytes for sd in self.shoot_days)
    
    def get_shoot_day(self, shoot_day_id: str) -> Optional[ShootDay]:
        """Get a shoot day by ID."""
        for sd in self.shoot_days:
            if sd.shoot_day_id == shoot_day_id:
                return sd
        return None
    
    def get_all_media_paths(self) -> List[Path]:
        """Get all media paths from all sessions."""
        paths = []
        for shoot_day in self.shoot_days:
            for session in shoot_day.sessions:
                for dest_path in session.destination_paths:
                    paths.append(Path(dest_path))
        return paths
    
    def to_dict(self) -> Dict:
        return {
            'project_id': self.project_id,
            'name': self.name,
            'client': self.client,
            'director': self.director,
            'producer': self.producer,
            'dp': self.dp,
            'description': self.description,
            'base_directory': self.base_directory,
            'shoot_days': [sd.to_dict() for sd in self.shoot_days],
            'status': self.status,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Project':
        shoot_days = [ShootDay.from_dict(sd) for sd in data.get('shoot_days', [])]
        return cls(
            project_id=data['project_id'],
            name=data['name'],
            client=data.get('client'),
            director=data.get('director'),
            producer=data.get('producer'),
            dp=data.get('dp'),
            description=data.get('description'),
            base_directory=data.get('base_directory'),
            shoot_days=shoot_days,
            status=data.get('status', 'active'),
            created_at=data.get('created_at', datetime.now().isoformat()),
            updated_at=data.get('updated_at', datetime.now().isoformat()),
        )


class ProjectManager:
    """
    Manager for projects and shoot days.
    
    Handles project CRUD operations, shoot day management,
    and session tracking for consolidated reporting.
    """
    
    def __init__(self, projects_dir: Optional[Path] = None):
        self.projects_dir = projects_dir or DEFAULT_PROJECTS_DIR
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(__name__)
    
    def _get_project_path(self, project_id: str) -> Path:
        """Get the file path for a project."""
        return self.projects_dir / f"{project_id}.json"
    
    def create_project(self, name: str, **kwargs) -> Project:
        """
        Create a new project.
        
        Args:
            name: Project name
            **kwargs: Optional fields (client, director, producer, dp, description, base_directory)
            
        Returns:
            Created Project instance
        """
        project_id = str(uuid.uuid4())[:8]  # Short UUID
        
        project = Project(
            project_id=project_id,
            name=name,
            client=kwargs.get('client'),
            director=kwargs.get('director'),
            producer=kwargs.get('producer'),
            dp=kwargs.get('dp'),
            description=kwargs.get('description'),
            base_directory=kwargs.get('base_directory'),
        )
        
        self._save_project(project)
        self.logger.info(f"Created project: {name} (ID: {project_id})")
        
        return project
    
    def get_project(self, project_id: str) -> Optional[Project]:
        """Get a project by ID."""
        project_path = self._get_project_path(project_id)
        
        if not project_path.exists():
            return None
        
        try:
            with open(project_path, 'r') as f:
                data = json.load(f)
            return Project.from_dict(data)
        except Exception as e:
            self.logger.error(f"Failed to load project {project_id}: {e}")
            return None
    
    def get_project_by_name(self, name: str) -> Optional[Project]:
        """Find a project by name (exact match)."""
        for project in self.list_projects():
            if project.name == name:
                return project
        return None
    
    def list_projects(self, status: Optional[str] = None) -> List[Project]:
        """
        List all projects.
        
        Args:
            status: Filter by status (optional)
            
        Returns:
            List of Project instances
        """
        projects = []
        
        for project_file in self.projects_dir.glob("*.json"):
            try:
                with open(project_file, 'r') as f:
                    data = json.load(f)
                project = Project.from_dict(data)
                
                if status is None or project.status == status:
                    projects.append(project)
            except Exception as e:
                self.logger.warning(f"Failed to load project file {project_file}: {e}")
        
        # Sort by updated_at (most recent first)
        projects.sort(key=lambda p: p.updated_at, reverse=True)
        
        return projects
    
    def update_project(self, project: Project) -> bool:
        """Update an existing project."""
        project.updated_at = datetime.now().isoformat()
        return self._save_project(project)
    
    def delete_project(self, project_id: str) -> bool:
        """Delete a project."""
        project_path = self._get_project_path(project_id)
        
        if project_path.exists():
            project_path.unlink()
            self.logger.info(f"Deleted project: {project_id}")
            return True
        
        return False
    
    def _save_project(self, project: Project) -> bool:
        """Save project to disk."""
        try:
            project_path = self._get_project_path(project.project_id)
            with open(project_path, 'w') as f:
                json.dump(project.to_dict(), f, indent=2)
            return True
        except Exception as e:
            self.logger.error(f"Failed to save project: {e}")
            return False
    
    def add_shoot_day(self, project_id: str, label: str, date: Optional[str] = None,
                     description: Optional[str] = None, location: Optional[str] = None) -> Optional[ShootDay]:
        """
        Add a shoot day to a project.
        
        Args:
            project_id: Project ID
            label: Shoot day label (e.g., "Day 1", "Interview Day")
            date: Date in ISO format (YYYY-MM-DD), defaults to today
            description: Optional description
            location: Optional location
            
        Returns:
            Created ShootDay or None if project not found
        """
        project = self.get_project(project_id)
        if not project:
            return None
        
        shoot_day_id = str(uuid.uuid4())[:8]
        
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')
        
        shoot_day = ShootDay(
            shoot_day_id=shoot_day_id,
            date=date,
            label=label,
            description=description,
            location=location,
        )
        
        project.shoot_days.append(shoot_day)
        self.update_project(project)
        
        self.logger.info(f"Added shoot day '{label}' to project {project.name}")
        
        return shoot_day
    
    def add_ingest_session(self, project_id: str, shoot_day_id: str,
                          source_path: str, destination_paths: List[str],
                          files_count: int, total_size_bytes: int,
                          card_label: Optional[str] = None,
                          notes: Optional[str] = None) -> Optional[IngestSession]:
        """
        Add an ingest session to a shoot day.
        
        Args:
            project_id: Project ID
            shoot_day_id: Shoot day ID
            source_path: Source media path
            destination_paths: List of destination paths
            files_count: Number of files ingested
            total_size_bytes: Total size in bytes
            card_label: Optional card label (e.g., "A001")
            notes: Optional notes
            
        Returns:
            Created IngestSession or None if not found
        """
        project = self.get_project(project_id)
        if not project:
            return None
        
        shoot_day = project.get_shoot_day(shoot_day_id)
        if not shoot_day:
            return None
        
        session = IngestSession(
            session_id=str(uuid.uuid4())[:8],
            timestamp=datetime.now().isoformat(),
            source_path=source_path,
            destination_paths=destination_paths,
            files_count=files_count,
            total_size_bytes=total_size_bytes,
            card_label=card_label,
            notes=notes,
        )
        
        shoot_day.sessions.append(session)
        shoot_day.updated_at = datetime.now().isoformat()
        self.update_project(project)
        
        self.logger.info(f"Added ingest session to {project.name} / {shoot_day.label}")
        
        return session
    
    def get_project_summary(self, project_id: str) -> Optional[Dict]:
        """
        Get a summary of a project for reporting.
        
        Returns:
            Dictionary with project summary
        """
        project = self.get_project(project_id)
        if not project:
            return None
        
        return {
            'project_id': project.project_id,
            'name': project.name,
            'client': project.client,
            'director': project.director,
            'status': project.status,
            'created_at': project.created_at,
            'total_shoot_days': project.total_shoot_days,
            'total_sessions': project.total_sessions,
            'total_files': project.total_files,
            'total_size_gb': project.total_size_bytes / (1024**3),
            'shoot_days': [
                {
                    'date': sd.date,
                    'label': sd.label,
                    'location': sd.location,
                    'sessions_count': len(sd.sessions),
                    'files_count': sd.total_files,
                    'size_gb': sd.total_size_bytes / (1024**3),
                }
                for sd in project.shoot_days
            ]
        }
    
    def format_size(self, bytes_size: int) -> str:
        """Format bytes to human readable."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_size < 1024.0:
                return f"{bytes_size:.2f} {unit}"
            bytes_size /= 1024.0
        return f"{bytes_size:.2f} PB"


# Global instance for convenience
_project_manager: Optional[ProjectManager] = None


def get_project_manager() -> ProjectManager:
    """Get the global project manager instance."""
    global _project_manager
    if _project_manager is None:
        _project_manager = ProjectManager()
    return _project_manager
