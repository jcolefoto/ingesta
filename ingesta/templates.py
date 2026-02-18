"""
Project templates module for ingesta.

Provides preset templates for common production types:
- Documentary: Interviews, B-roll, archival, verité
- Commercial: Product, talent, lifestyle, backgrounds  
- Wedding: Ceremony, prep, reception, details

Each template includes:
- Predefined bin structures
- Recommended tags/keywords
- Default settings for reports and exports
- Project metadata defaults

All processing is done locally.
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum


logger = logging.getLogger(__name__)


class TemplateType(Enum):
    """Available project template types."""
    DOCUMENTARY = "documentary"
    COMMERCIAL = "commercial"
    WEDDING = "wedding"
    CORPORATE = "corporate"
    MUSIC_VIDEO = "music_video"
    CUSTOM = "custom"


@dataclass
class BinDefinition:
    """Definition of a bin/folder structure."""
    name: str
    description: str = ""
    sub_bins: List['BinDefinition'] = field(default_factory=list)
    color: Optional[str] = None  # For Premiere/Resolve
    auto_tag: List[str] = field(default_factory=list)  # Auto-apply tags


@dataclass
class TagDefinition:
    """Definition of a tag/keyword."""
    name: str
    description: str = ""
    category: str = "general"  # e.g., "content", "technical", "workflow"
    color: Optional[str] = None


@dataclass
class TemplateSettings:
    """Settings for the template."""
    # Report settings
    generate_thumbnails: bool = True
    thumbnail_count: int = 5
    transcribe_audio: bool = True
    analyze_frames: bool = False
    analyze_audio_tech: bool = True
    extract_metadata: bool = True
    generate_proxies: bool = True
    proxy_resolution: str = "960x540"
    
    # Premiere settings
    fps: float = 24.0
    resolution: str = "1920x1080"
    create_markers: bool = True
    organize_by_camera: bool = True
    
    # Export settings
    export_edl: bool = False
    export_xml: bool = True
    export_csv: bool = True
    export_pdf: bool = True
    
    # Deliverable settings
    include_proxies: bool = True
    include_transcripts: bool = True
    include_thumbnails: bool = True
    package_zip: bool = False


@dataclass
class ProjectTemplate:
    """Complete project template definition."""
    name: str
    template_type: TemplateType
    description: str
    bins: List[BinDefinition] = field(default_factory=list)
    tags: List[TagDefinition] = field(default_factory=list)
    settings: TemplateSettings = field(default_factory=TemplateSettings)
    metadata_defaults: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        """Convert template to dictionary."""
        return {
            'name': self.name,
            'template_type': self.template_type.value,
            'description': self.description,
            'bins': [self._bin_to_dict(b) for b in self.bins],
            'tags': [asdict(t) for t in self.tags],
            'settings': asdict(self.settings),
            'metadata_defaults': self.metadata_defaults,
        }
    
    def _bin_to_dict(self, bin_def: BinDefinition) -> Dict:
        """Convert bin definition to dictionary."""
        return {
            'name': bin_def.name,
            'description': bin_def.description,
            'color': bin_def.color,
            'auto_tag': bin_def.auto_tag,
            'sub_bins': [self._bin_to_dict(sb) for sb in bin_def.sub_bins],
        }


class TemplateManager:
    """
    Manager for project templates.
    
    Provides predefined templates and custom template creation.
    """
    
    def __init__(self):
        self._templates: Dict[TemplateType, ProjectTemplate] = {}
        self._init_default_templates()
    
    def _init_default_templates(self):
        """Initialize all default templates."""
        self._templates[TemplateType.DOCUMENTARY] = self._create_documentary_template()
        self._templates[TemplateType.COMMERCIAL] = self._create_commercial_template()
        self._templates[TemplateType.WEDDING] = self._create_wedding_template()
        self._templates[TemplateType.CORPORATE] = self._create_corporate_template()
        self._templates[TemplateType.MUSIC_VIDEO] = self._create_music_video_template()
    
    def _create_documentary_template(self) -> ProjectTemplate:
        """Create documentary production template."""
        bins = [
            BinDefinition(
                name="01_INTERVIEWS",
                description="Interview footage - A-roll",
                sub_bins=[
                    BinDefinition(name="Primary", description="Main interview subjects"),
                    BinDefinition(name="Secondary", description="B-roll interviews"),
                    BinDefinition(name="Pickups", description="Additional interview segments"),
                ],
                color="#4A90E2",
                auto_tag=["interview", "a-roll", "dialogue"]
            ),
            BinDefinition(
                name="02_B_ROLL",
                description="B-roll and cutaway footage",
                sub_bins=[
                    BinDefinition(name="Subjects", description="People and activities"),
                    BinDefinition(name="Locations", description="Places and environments"),
                    BinDefinition(name="Details", description="Close-ups and inserts"),
                    BinDefinition(name="Action", description="Movement and activity"),
                ],
                color="#7ED321",
                auto_tag=["b-roll", "cutaway", "environment"]
            ),
            BinDefinition(
                name="03_ESTABLISHING",
                description="Establishing shots and wide views",
                sub_bins=[
                    BinDefinition(name="Wide Shots", description="Wide establishing shots"),
                    BinDefinition(name="Aerials", description="Drone or elevated shots"),
                    BinDefinition(name="Transitions", description="Transition shots"),
                ],
                color="#F5A623",
                auto_tag=["establishing", "wide", "location"]
            ),
            BinDefinition(
                name="04_VERITE",
                description="Observational/cinema verité footage",
                color="#BD10E0",
                auto_tag=["verite", "observational", "natural"]
            ),
            BinDefinition(
                name="05_ARCHIVAL",
                description="Archival footage and materials",
                sub_bins=[
                    BinDefinition(name="Photos", description="Still images"),
                    BinDefinition(name="Video", description="Archival video"),
                    BinDefinition(name="Documents", description="Scanned documents"),
                ],
                color="#9013FE",
                auto_tag=["archival", "historical", "stock"]
            ),
            BinDefinition(
                name="06_AUDIO",
                description="Audio-only files",
                sub_bins=[
                    BinDefinition(name="Interviews", description="Audio interviews"),
                    BinDefinition(name="Ambient", description="Room tone and ambient"),
                    BinDefinition(name="Wild Sound", description="Wild sound effects"),
                ],
                color="#50E3C2",
                auto_tag=["audio", "sound", "dialogue"]
            ),
            BinDefinition(
                name="07_SYNCABLE",
                description="Clips needing audio sync",
                color="#D0021B",
                auto_tag=["sync", "dual-system", "external-audio"]
            ),
            BinDefinition(
                name="08_UNCATEGORIZED",
                description="Uncategorized footage",
                color="#9B9B9B",
                auto_tag=["uncategorized"]
            ),
        ]
        
        tags = [
            TagDefinition("interview", "Interview footage", "content", "#4A90E2"),
            TagDefinition("b-roll", "B-roll footage", "content", "#7ED321"),
            TagDefinition("establishing", "Establishing shot", "content", "#F5A623"),
            TagDefinition("verite", "Cinema verité", "content", "#BD10E0"),
            TagDefinition("archival", "Archival material", "content", "#9013FE"),
            TagDefinition("syncable", "Needs audio sync", "workflow", "#D0021B"),
            TagDefinition("primary", "Primary content", "workflow", "#4A90E2"),
            TagDefinition("secondary", "Secondary content", "workflow", "#50E3C2"),
            TagDefinition("good-take", "Good take", "workflow", "#7ED321"),
            TagDefinition("pickup", "Pickup shot", "workflow", "#F5A623"),
            TagDefinition("needs-review", "Needs review", "workflow", "#D0021B"),
        ]
        
        settings = TemplateSettings(
            generate_thumbnails=True,
            thumbnail_count=5,
            transcribe_audio=True,  # Important for interviews
            analyze_frames=False,
            analyze_audio_tech=True,
            extract_metadata=True,
            generate_proxies=True,
            proxy_resolution="960x540",
            fps=24.0,
            resolution="1920x1080",
            create_markers=True,
            organize_by_camera=True,
            export_edl=False,
            export_xml=True,
            export_csv=True,
            export_pdf=True,
            include_proxies=True,
            include_transcripts=True,
            include_thumbnails=True,
            package_zip=False,
        )
        
        return ProjectTemplate(
            name="Documentary",
            template_type=TemplateType.DOCUMENTARY,
            description="Template for documentary productions with interview-heavy workflows",
            bins=bins,
            tags=tags,
            settings=settings,
            metadata_defaults={
                'recommended_fps': 24,
                'recommended_codec': 'ProRes',
                'audio_priority': 'high',
            }
        )
    
    def _create_commercial_template(self) -> ProjectTemplate:
        """Create commercial production template."""
        bins = [
            BinDefinition(
                name="01_HERO_PRODUCT",
                description="Hero product shots - main focus",
                sub_bins=[
                    BinDefinition(name="Beauty", description="Beauty/product shots"),
                    BinDefinition(name="Detail", description="Detail/close-up shots"),
                    BinDefinition(name="Lifestyle", description="Product in use"),
                ],
                color="#D0021B",
                auto_tag=["product", "hero", "beauty"]
            ),
            BinDefinition(
                name="02_TALENT",
                description="Talent/on-camera subjects",
                sub_bins=[
                    BinDefinition(name="Hero", description="Main talent"),
                    BinDefinition(name="Supporting", description="Supporting talent"),
                    BinDefinition(name="Extras", description="Background talent"),
                ],
                color="#4A90E2",
                auto_tag=["talent", "subject", "person"]
            ),
            BinDefinition(
                name="03_LIFESTYLE",
                description="Lifestyle and environment shots",
                sub_bins=[
                    BinDefinition(name="Home", description="Home/living environments"),
                    BinDefinition(name="Work", description="Work/office environments"),
                    BinDefinition(name="Outdoors", description="Outdoor environments"),
                ],
                color="#7ED321",
                auto_tag=["lifestyle", "environment", "scene"]
            ),
            BinDefinition(
                name="04_GRAPHICS_ELEMENTS",
                description="Elements for graphics/VFX",
                sub_bins=[
                    BinDefinition(name="Green Screen", description="Green screen footage"),
                    BinDefinition(name="Plates", description="Background plates"),
                    BinDefinition(name="Elements", description="VFX elements"),
                ],
                color="#9013FE",
                auto_tag=["vfx", "greenscreen", "element"]
            ),
            BinDefinition(
                name="05_B_ROLL",
                description="Supporting B-roll",
                color="#F5A623",
                auto_tag=["b-roll", "supporting"]
            ),
            BinDefinition(
                name="06_AUDIO",
                description="Audio recordings",
                sub_bins=[
                    BinDefinition(name="Voiceover", description="Voiceover recordings"),
                    BinDefinition(name="Sound Design", description="Sound design elements"),
                    BinDefinition(name="Music", description="Reference music"),
                ],
                color="#50E3C2",
                auto_tag=["audio", "voiceover", "sound"]
            ),
            BinDefinition(
                name="07_REFERENCES",
                description="Reference materials",
                color="#9B9B9B",
                auto_tag=["reference", "stock"]
            ),
        ]
        
        tags = [
            TagDefinition("product", "Product shot", "content", "#D0021B"),
            TagDefinition("talent", "Talent/on-camera", "content", "#4A90E2"),
            TagDefinition("lifestyle", "Lifestyle shot", "content", "#7ED321"),
            TagDefinition("vfx", "VFX element", "content", "#9013FE"),
            TagDefinition("hero", "Hero shot", "workflow", "#D0021B"),
            TagDefinition("beauty", "Beauty shot", "workflow", "#D0021B"),
            TagDefinition("approved", "Client approved", "workflow", "#7ED321"),
            TagDefinition("alt-take", "Alternative take", "workflow", "#F5A623"),
        ]
        
        settings = TemplateSettings(
            generate_thumbnails=True,
            thumbnail_count=3,
            transcribe_audio=False,
            analyze_frames=True,  # For product shot analysis
            analyze_audio_tech=True,
            extract_metadata=True,
            generate_proxies=True,
            proxy_resolution="1280x720",  # Higher res for client review
            fps=24.0,
            resolution="1920x1080",
            create_markers=True,
            organize_by_camera=True,
            export_edl=False,
            export_xml=True,
            export_csv=True,
            export_pdf=True,
            include_proxies=True,
            include_transcripts=False,
            include_thumbnails=True,
            package_zip=True,  # Often need to deliver to clients
        )
        
        return ProjectTemplate(
            name="Commercial",
            template_type=TemplateType.COMMERCIAL,
            description="Template for commercial productions with product and talent focus",
            bins=bins,
            tags=tags,
            settings=settings,
            metadata_defaults={
                'recommended_fps': 24,
                'recommended_codec': 'ProRes HQ',
                'color_space': 'Rec.709',
            }
        )
    
    def _create_wedding_template(self) -> ProjectTemplate:
        """Create wedding production template."""
        bins = [
            BinDefinition(
                name="01_PREPARATION",
                description="Pre-ceremony preparation",
                sub_bins=[
                    BinDefinition(name="Bride", description="Bride preparation"),
                    BinDefinition(name="Groom", description="Groom preparation"),
                    BinDefinition(name="Venue", description="Venue prep and details"),
                ],
                color="#F5A623",
                auto_tag=["prep", "getting-ready", "details"]
            ),
            BinDefinition(
                name="02_CEREMONY",
                description="Wedding ceremony",
                sub_bins=[
                    BinDefinition(name="Wide", description="Wide ceremony shots"),
                    BinDefinition(name="Close", description="Close-ups and reactions"),
                    BinDefinition(name="Processional", description="Walking down aisle"),
                    BinDefinition(name="Vows", description="Vows and ring exchange"),
                    BinDefinition(name="Recessional", description="Walking back"),
                ],
                color="#D0021B",
                auto_tag=["ceremony", "vows", "processional"]
            ),
            BinDefinition(
                name="03_PORTRAITS",
                description="Formal portraits and couples",
                sub_bins=[
                    BinDefinition(name="Couple", description="Couple portraits"),
                    BinDefinition(name="Family", description="Family portraits"),
                    BinDefinition(name="Wedding Party", description="Bridal party"),
                    BinDefinition(name="Formals", description="Formal group shots"),
                ],
                color="#4A90E2",
                auto_tag=["portrait", "couple", "formal"]
            ),
            BinDefinition(
                name="04_RECEPTION",
                description="Reception and celebration",
                sub_bins=[
                    BinDefinition(name="Venue", description="Reception venue"),
                    BinDefinition(name="Grand Entrance", description="Introductions"),
                    BinDefinition(name="First Dance", description="First dance"),
                    BinDefinition(name="Speeches", description="Toasts and speeches"),
                    BinDefinition(name="Dancing", description="Open dancing"),
                    BinDefinition(name="Cake", description="Cake cutting"),
                    BinDefinition(name="Send-off", description="Exit/send-off"),
                ],
                color="#9013FE",
                auto_tag=["reception", "dance", "celebration"]
            ),
            BinDefinition(
                name="05_DETAILS",
                description="Detail shots",
                sub_bins=[
                    BinDefinition(name="Rings", description="Ring shots"),
                    BinDefinition(name="Flowers", description="Floral arrangements"),
                    BinDefinition(name="Decor", description="Venue decor"),
                    BinDefinition(name="Food", description="Food and cake"),
                    BinDefinition(name="Stationery", description="Invitations, programs"),
                ],
                color="#7ED321",
                auto_tag=["detail", "decor", "product"]
            ),
            BinDefinition(
                name="06_AUDIO",
                description="Audio recordings",
                sub_bins=[
                    BinDefinition(name="Vows", description="Ceremony vows audio"),
                    BinDefinition(name="Speeches", description="Reception speeches"),
                    BinDefinition(name="Ambient", description="Room tone"),
                ],
                color="#50E3C2",
                auto_tag=["audio", "vows", "speeches"]
            ),
            BinDefinition(
                name="07_B_ROLL",
                description="Additional B-roll",
                color="#BD10E0",
                auto_tag=["b-roll", "atmosphere"]
            ),
        ]
        
        tags = [
            TagDefinition("prep", "Getting ready", "content", "#F5A623"),
            TagDefinition("ceremony", "Ceremony", "content", "#D0021B"),
            TagDefinition("portrait", "Portrait", "content", "#4A90E2"),
            TagDefinition("reception", "Reception", "content", "#9013FE"),
            TagDefinition("detail", "Detail shot", "content", "#7ED321"),
            TagDefinition("key-moment", "Key moment", "workflow", "#D0021B"),
            TagDefinition("emotional", "Emotional moment", "workflow", "#4A90E2"),
            TagDefinition("must-have", "Must-have shot", "workflow", "#D0021B"),
            TagDefinition("backup", "Backup/alt angle", "workflow", "#9B9B9B"),
        ]
        
        settings = TemplateSettings(
            generate_thumbnails=True,
            thumbnail_count=5,
            transcribe_audio=True,  # For vows and speeches
            analyze_frames=False,
            analyze_audio_tech=True,
            extract_metadata=True,
            generate_proxies=True,
            proxy_resolution="960x540",
            fps=24.0,
            resolution="1920x1080",
            create_markers=True,
            organize_by_camera=True,
            export_edl=False,
            export_xml=True,
            export_csv=True,
            export_pdf=True,
            include_proxies=True,
            include_transcripts=True,
            include_thumbnails=True,
            package_zip=True,
        )
        
        return ProjectTemplate(
            name="Wedding",
            template_type=TemplateType.WEDDING,
            description="Template for wedding productions with timeline-based organization",
            bins=bins,
            tags=tags,
            settings=settings,
            metadata_defaults={
                'recommended_fps': 24,
                'recommended_codec': 'ProRes',
                'audio_channels': 2,
            }
        )
    
    def _create_corporate_template(self) -> ProjectTemplate:
        """Create corporate video template."""
        bins = [
            BinDefinition(
                name="01_INTERVIEWS",
                description="Executive and employee interviews",
                sub_bins=[
                    BinDefinition(name="Executives", description="Leadership interviews"),
                    BinDefinition(name="Employees", description="Staff interviews"),
                    BinDefinition(name="Customers", description="Client testimonials"),
                ],
                color="#4A90E2",
                auto_tag=["interview", "testimonial", "executive"]
            ),
            BinDefinition(
                name="02_B_ROLL",
                description="Office and workplace footage",
                sub_bins=[
                    BinDefinition(name="Office", description="Office environment"),
                    BinDefinition(name="Work", description="People working"),
                    BinDefinition(name="Meetings", description="Meeting footage"),
                    BinDefinition(name="Events", description="Company events"),
                ],
                color="#7ED321",
                auto_tag=["b-roll", "workplace", "office"]
            ),
            BinDefinition(
                name="03_PRODUCT_SERVICE",
                description="Product or service demonstrations",
                color="#F5A623",
                auto_tag=["product", "demo", "service"]
            ),
            BinDefinition(
                name="04_GRAPHICS",
                description="Graphics and animation elements",
                color="#9013FE",
                auto_tag=["graphics", "animation", "title"]
            ),
            BinDefinition(
                name="05_AUDIO",
                description="Audio recordings",
                sub_bins=[
                    BinDefinition(name="Interviews", description="Interview audio"),
                    BinDefinition(name="Narration", description="Voiceover/narration"),
                    BinDefinition(name="Sound", description="Sound design"),
                ],
                color="#50E3C2",
                auto_tag=["audio", "narration", "interview"]
            ),
        ]
        
        tags = [
            TagDefinition("interview", "Interview", "content", "#4A90E2"),
            TagDefinition("testimonial", "Testimonial", "content", "#4A90E2"),
            TagDefinition("b-roll", "B-roll", "content", "#7ED321"),
            TagDefinition("product", "Product", "content", "#F5A623"),
            TagDefinition("executive", "Executive", "content", "#4A90E2"),
            TagDefinition("approved", "Approved", "workflow", "#7ED321"),
            TagDefinition("legal-review", "Needs legal review", "workflow", "#F5A623"),
        ]
        
        settings = TemplateSettings(
            transcribe_audio=True,
            generate_proxies=True,
            proxy_resolution="1280x720",
            export_pdf=True,
            package_zip=True,
        )
        
        return ProjectTemplate(
            name="Corporate",
            template_type=TemplateType.CORPORATE,
            description="Template for corporate videos, testimonials, and promotional content",
            bins=bins,
            tags=tags,
            settings=settings
        )
    
    def _create_music_video_template(self) -> ProjectTemplate:
        """Create music video template."""
        bins = [
            BinDefinition(
                name="01_PERFORMANCE",
                description="Performance footage",
                sub_bins=[
                    BinDefinition(name="Wide", description="Wide shots"),
                    BinDefinition(name="Medium", description="Medium shots"),
                    BinDefinition(name="Close", description="Close-ups"),
                    BinDefinition(name="Extreme", description="Extreme angles"),
                ],
                color="#D0021B",
                auto_tag=["performance", "artist", "band"]
            ),
            BinDefinition(
                name="02_NARRATIVE",
                description="Story/narrative scenes",
                sub_bins=[
                    BinDefinition(name="Scene 1", description="Scene 1 footage"),
                    BinDefinition(name="Scene 2", description="Scene 2 footage"),
                    BinDefinition(name="Scene 3", description="Scene 3 footage"),
                ],
                color="#4A90E2",
                auto_tag=["narrative", "story", "scene"]
            ),
            BinDefinition(
                name="03_B_ROLL",
                description="Atmospheric B-roll",
                color="#7ED321",
                auto_tag=["b-roll", "atmosphere", "mood"]
            ),
            BinDefinition(
                name="04_VFX_PLATES",
                description="VFX and green screen",
                color="#9013FE",
                auto_tag=["vfx", "greenscreen", "effect"]
            ),
            BinDefinition(
                name="05_AUDIO",
                description="Audio tracks",
                color="#50E3C2",
                auto_tag=["audio", "music", "track"]
            ),
        ]
        
        tags = [
            TagDefinition("performance", "Performance", "content", "#D0021B"),
            TagDefinition("narrative", "Narrative", "content", "#4A90E2"),
            TagDefinition("choreo", "Choreography", "content", "#F5A623"),
            TagDefinition("vfx", "VFX", "content", "#9013FE"),
            TagDefinition("hero-shot", "Hero shot", "workflow", "#D0021B"),
            TagDefinition("sync-point", "Sync point", "workflow", "#F5A623"),
        ]
        
        settings = TemplateSettings(
            transcribe_audio=False,
            generate_proxies=True,
            proxy_resolution="1280x720",
            fps=24.0,
            export_xml=True,
        )
        
        return ProjectTemplate(
            name="Music Video",
            template_type=TemplateType.MUSIC_VIDEO,
            description="Template for music videos with performance and narrative organization",
            bins=bins,
            tags=tags,
            settings=settings
        )
    
    def get_template(self, template_type: TemplateType) -> Optional[ProjectTemplate]:
        """Get a template by type."""
        return self._templates.get(template_type)
    
    def get_template_by_name(self, name: str) -> Optional[ProjectTemplate]:
        """Get a template by name (case-insensitive)."""
        name_lower = name.lower()
        for template in self._templates.values():
            if template.name.lower() == name_lower:
                return template
            if template.template_type.value.lower() == name_lower:
                return template
        return None
    
    def list_templates(self) -> List[ProjectTemplate]:
        """List all available templates."""
        return list(self._templates.values())
    
    def export_template(self, template_type: TemplateType, output_path: Path) -> bool:
        """Export a template to JSON file."""
        template = self.get_template(template_type)
        if not template:
            return False
        
        try:
            with open(output_path, 'w') as f:
                json.dump(template.to_dict(), f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Failed to export template: {e}")
            return False


# Global instance
_template_manager: Optional[TemplateManager] = None


def get_template_manager() -> TemplateManager:
    """Get the global template manager instance."""
    global _template_manager
    if _template_manager is None:
        _template_manager = TemplateManager()
    return _template_manager
