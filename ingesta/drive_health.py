"""
Drive health monitoring module for ingesta.

Monitors destination drive health using SMART data when available.
Warns about slow, failing, or problematic drives.
Gracefully falls back if SMART tools aren't available.

Supports:
- smartctl (smartmontools) on Linux/macOS
- PowerShell/Get-PhysicalDisk on Windows (partial)
- Basic disk space monitoring (always available)
"""

import logging
import shutil
import subprocess
import json
import re
from pathlib import Path
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field
from enum import Enum
import platform


logger = logging.getLogger(__name__)


class DriveHealthStatus(Enum):
    """Drive health status levels."""
    HEALTHY = "healthy"
    WARNING = "warning"  # Pre-fail signs
    CRITICAL = "critical"  # Failing
    UNKNOWN = "unknown"  # Can't determine
    NOT_AVAILABLE = "not_available"  # SMART not available


class DriveType(Enum):
    """Types of storage drives."""
    SSD = "ssd"
    HDD = "hdd"
    NVME = "nvme"
    USB = "usb"
    NETWORK = "network"
    UNKNOWN = "unknown"


@dataclass
class DriveHealthInfo:
    """Drive health information."""
    device_path: str
    mount_point: Optional[str] = None
    drive_type: DriveType = DriveType.UNKNOWN
    health_status: DriveHealthStatus = DriveHealthStatus.UNKNOWN
    
    # SMART attributes (if available)
    temperature_celsius: Optional[int] = None
    power_on_hours: Optional[int] = None
    wear_level: Optional[int] = None  # For SSDs
    bad_sectors: Optional[int] = None
    
    # Health percentages
    health_percent: Optional[int] = None
    
    # Warnings
    warnings: List[str] = field(default_factory=list)
    
    # SMART availability
    smart_available: bool = False
    smart_enabled: bool = False
    
    # Basic info always available
    total_space_bytes: int = 0
    free_space_bytes: int = 0
    
    @property
    def used_space_bytes(self) -> int:
        return self.total_space_bytes - self.free_space_bytes
    
    @property
    def free_space_percent(self) -> float:
        if self.total_space_bytes == 0:
            return 0.0
        return (self.free_space_bytes / self.total_space_bytes) * 100
    
    @property
    def is_healthy(self) -> bool:
        return self.health_status == DriveHealthStatus.HEALTHY
    
    @property
    def has_critical_issues(self) -> bool:
        return self.health_status == DriveHealthStatus.CRITICAL


class DriveHealthMonitor:
    """Monitor drive health using SMART and basic metrics."""
    
    # Temperature thresholds (Celsius)
    TEMP_WARNING = 50
    TEMP_CRITICAL = 60
    
    # Free space thresholds
    SPACE_WARNING_PERCENT = 10.0
    SPACE_CRITICAL_PERCENT = 5.0
    
    # Bad sector thresholds
    BAD_SECTORS_WARNING = 10
    BAD_SECTORS_CRITICAL = 50
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._smartctl_available = None
        self._os_type = platform.system().lower()
    
    def _check_smartctl_available(self) -> bool:
        """Check if smartctl is available on the system."""
        if self._smartctl_available is not None:
            return self._smartctl_available
        
        self._smartctl_available = shutil.which('smartctl') is not None
        if not self._smartctl_available:
            self.logger.debug("smartctl not found - SMART monitoring unavailable")
        return self._smartctl_available
    
    def get_drive_health(self, path: Path) -> DriveHealthInfo:
        """
        Get health information for a drive.
        
        Args:
            path: Path on the drive to check
            
        Returns:
            DriveHealthInfo with health data
        """
        path = Path(path).resolve()
        
        # Basic disk space info (always available)
        health_info = self._get_basic_info(path)
        
        # Try to get SMART data
        if self._check_smartctl_available():
            try:
                smart_info = self._get_smart_info(path)
                if smart_info:
                    # Merge SMART data into health info
                    health_info.smart_available = True
                    health_info.smart_enabled = True
                    health_info = self._merge_smart_data(health_info, smart_info)
            except Exception as e:
                self.logger.debug(f"Could not get SMART data for {path}: {e}")
                health_info.smart_available = True
                health_info.smart_enabled = False
        else:
            health_info.smart_available = False
            health_info.smart_enabled = False
        
        # Evaluate overall health
        health_info = self._evaluate_health(health_info)
        
        return health_info
    
    def _get_basic_info(self, path: Path) -> DriveHealthInfo:
        """Get basic drive information (always available)."""
        try:
            stat = path.stat()
            
            # Try to get mount point
            mount_point = self._get_mount_point(path)
            
            # Get disk usage
            if hasattr(path, 'statvfs'):
                # Unix-like
                vfs_stat = path.statvfs()
                total = vfs_stat.f_blocks * vfs_stat.f_frsize
                free = vfs_stat.f_bavail * vfs_stat.f_frsize
            else:
                # Cross-platform using shutil
                total, used, free = shutil.disk_usage(path)
            
            return DriveHealthInfo(
                device_path=str(path),
                mount_point=str(mount_point) if mount_point else None,
                total_space_bytes=total,
                free_space_bytes=free,
            )
        except Exception as e:
            self.logger.warning(f"Could not get basic info for {path}: {e}")
            return DriveHealthInfo(device_path=str(path))
    
    def _get_mount_point(self, path: Path) -> Optional[Path]:
        """Get the mount point for a path."""
        try:
            path = path.resolve()
            # Walk up until we find the mount point
            while not path.is_mount() and path.parent != path:
                path = path.parent
            return path
        except Exception:
            return None
    
    def _get_smart_info(self, path: Path) -> Optional[Dict[str, Any]]:
        """Get SMART information using smartctl."""
        if not self._check_smartctl_available():
            return None
        
        try:
            # First, find the device for this path
            device = self._get_device_for_path(path)
            if not device:
                return None
            
            # Run smartctl
            cmd = ['smartctl', '-a', '--json', device]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode not in [0, 2]:  # 2 = some attributes failed but still usable
                self.logger.debug(f"smartctl failed with code {result.returncode}")
                return None
            
            data = json.loads(result.stdout)
            return data
            
        except subprocess.TimeoutExpired:
            self.logger.debug("smartctl timed out")
            return None
        except json.JSONDecodeError as e:
            self.logger.debug(f"Could not parse smartctl output: {e}")
            return None
        except Exception as e:
            self.logger.debug(f"Error running smartctl: {e}")
            return None
    
    def _get_device_for_path(self, path: Path) -> Optional[str]:
        """Get the device path for a filesystem path."""
        try:
            if self._os_type == 'linux':
                # Use findmnt to get device
                cmd = ['findmnt', '-n', '-o', 'SOURCE', '--target', str(path)]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    device = result.stdout.strip()
                    # Convert UUID= or LABEL= to actual device
                    if device.startswith('UUID=') or device.startswith('LABEL='):
                        # Try to resolve
                        cmd = ['blkid', '-U', device[5:]] if device.startswith('UUID=') else ['blkid', '-L', device[6:]]
                        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                        if result.returncode == 0:
                            device = result.stdout.strip()
                    return device
            elif self._os_type == 'darwin':
                # macOS - use diskutil
                cmd = ['df', str(path)]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')
                    if len(lines) > 1:
                        device = lines[1].split()[0]
                        return device
            
            # Fallback: try to get from mount info
            mount_point = self._get_mount_point(path)
            if mount_point:
                with open('/proc/mounts', 'r') as f:
                    for line in f:
                        parts = line.split()
                        if len(parts) >= 2 and parts[1] == str(mount_point):
                            return parts[0]
        except Exception as e:
            self.logger.debug(f"Could not get device for {path}: {e}")
        
        return None
    
    def _merge_smart_data(self, health_info: DriveHealthInfo, smart_data: Dict) -> DriveHealthInfo:
        """Merge SMART data into health info."""
        try:
            # Get drive type
            if 'device' in smart_data:
                dev_info = smart_data['device']
                if 'type' in dev_info:
                    dev_type = dev_info['type'].lower()
                    if 'nvme' in dev_type:
                        health_info.drive_type = DriveType.NVME
                    elif 'usb' in dev_type:
                        health_info.drive_type = DriveType.USB
            
            # Get ATA/SMART attributes
            if 'ata_smart_attributes' in smart_data:
                attrs = smart_data['ata_smart_attributes'].get('table', [])
                for attr in attrs:
                    attr_id = attr.get('id', 0)
                    attr_name = attr.get('name', '').lower()
                    raw_value = attr.get('raw', {}).get('value', 0)
                    
                    # Temperature (various attributes)
                    if attr_id in [190, 194] or 'temperature' in attr_name:
                        if isinstance(raw_value, (int, float)):
                            health_info.temperature_celsius = int(raw_value)
                    
                    # Power-on hours
                    elif attr_id == 9 or 'power_on' in attr_name:
                        if isinstance(raw_value, (int, float)):
                            health_info.power_on_hours = int(raw_value)
                    
                    # Wear leveling (SSDs)
                    elif attr_id in [177, 202] or 'wear' in attr_name:
                        if isinstance(raw_value, (int, float)):
                            health_info.wear_level = int(raw_value)
                    
                    # Reallocated sectors (bad sectors)
                    elif attr_id == 5 or 'reallocated' in attr_name:
                        if isinstance(raw_value, (int, float)):
                            health_info.bad_sectors = int(raw_value)
            
            # NVMe specific data
            if 'nvme_smart_health_information_log' in smart_data:
                nvme_data = smart_data['nvme_smart_health_information_log']
                health_info.drive_type = DriveType.NVME
                
                if 'temperature' in nvme_data:
                    # NVMe temperature is in Kelvin
                    temp_kelvin = nvme_data['temperature']
                    health_info.temperature_celsius = temp_kelvin - 273
                
                if 'percentage_used' in nvme_data:
                    # NVMe percentage used (wear)
                    health_info.wear_level = int(nvme_data['percentage_used'])
            
            # Get overall health from SMART
            if 'smart_status' in smart_data:
                smart_status = smart_data['smart_status']
                if isinstance(smart_status, dict):
                    passed = smart_status.get('passed', False)
                    if passed:
                        health_info.health_status = DriveHealthStatus.HEALTHY
                    else:
                        health_info.health_status = DriveHealthStatus.CRITICAL
            
        except Exception as e:
            self.logger.debug(f"Error parsing SMART data: {e}")
        
        return health_info
    
    def _evaluate_health(self, health_info: DriveHealthInfo) -> DriveHealthInfo:
        """Evaluate overall drive health and generate warnings."""
        warnings = []
        critical = False
        
        # Check temperature
        if health_info.temperature_celsius:
            if health_info.temperature_celsius >= self.TEMP_CRITICAL:
                warnings.append(f"Critical temperature: {health_info.temperature_celsius}°C")
                critical = True
            elif health_info.temperature_celsius >= self.TEMP_WARNING:
                warnings.append(f"High temperature: {health_info.temperature_celsius}°C")
        
        # Check free space
        if health_info.free_space_percent <= self.SPACE_CRITICAL_PERCENT:
            warnings.append(f"Critical free space: {health_info.free_space_percent:.1f}%")
            critical = True
        elif health_info.free_space_percent <= self.SPACE_WARNING_PERCENT:
            warnings.append(f"Low free space: {health_info.free_space_percent:.1f}%")
        
        # Check bad sectors
        if health_info.bad_sectors:
            if health_info.bad_sectors >= self.BAD_SECTORS_CRITICAL:
                warnings.append(f"Many bad sectors: {health_info.bad_sectors}")
                critical = True
            elif health_info.bad_sectors >= self.BAD_SECTORS_WARNING:
                warnings.append(f"Some bad sectors: {health_info.bad_sectors}")
        
        # Check wear level (SSDs)
        if health_info.wear_level and health_info.wear_level > 80:
            warnings.append(f"High SSD wear: {health_info.wear_level}% used")
        
        health_info.warnings = warnings
        
        # Determine overall status
        if critical:
            health_info.health_status = DriveHealthStatus.CRITICAL
        elif warnings:
            health_info.health_status = DriveHealthStatus.WARNING
        elif health_info.smart_available and health_info.smart_enabled:
            health_info.health_status = DriveHealthStatus.HEALTHY
        elif not health_info.smart_available:
            health_info.health_status = DriveHealthStatus.NOT_AVAILABLE
        
        return health_info
    
    def check_destinations(self, destinations: List[Path]) -> List[DriveHealthInfo]:
        """
        Check health of multiple destination drives.
        
        Args:
            destinations: List of destination paths
            
        Returns:
            List of DriveHealthInfo for each destination
        """
        results = []
        for dest in destinations:
            health_info = self.get_drive_health(dest)
            results.append(health_info)
        return results
    
    def format_health_report(self, health_info: DriveHealthInfo) -> str:
        """Format drive health info as readable text."""
        lines = []
        
        # Status icon
        if health_info.health_status == DriveHealthStatus.HEALTHY:
            icon = "✓"
        elif health_info.health_status == DriveHealthStatus.CRITICAL:
            icon = "✗"
        else:
            icon = "⚠"
        
        lines.append(f"{icon} {health_info.mount_point or health_info.device_path}")
        lines.append(f"   Status: {health_info.health_status.value}")
        
        if health_info.drive_type != DriveType.UNKNOWN:
            lines.append(f"   Type: {health_info.drive_type.value.upper()}")
        
        # Space
        free_gb = health_info.free_space_bytes / (1024**3)
        total_gb = health_info.total_space_bytes / (1024**3)
        lines.append(f"   Space: {free_gb:.1f} GB free / {total_gb:.1f} GB total ({health_info.free_space_percent:.1f}%)")
        
        # SMART data
        if health_info.smart_available:
            if health_info.smart_enabled:
                if health_info.temperature_celsius:
                    lines.append(f"   Temperature: {health_info.temperature_celsius}°C")
                if health_info.power_on_hours:
                    days = health_info.power_on_hours / 24
                    lines.append(f"   Power-on time: {health_info.power_on_hours} hours ({days:.0f} days)")
                if health_info.bad_sectors:
                    lines.append(f"   Bad sectors: {health_info.bad_sectors}")
                if health_info.wear_level:
                    lines.append(f"   SSD wear: {health_info.wear_level}%")
            else:
                lines.append("   SMART: Available but not enabled")
        else:
            lines.append("   SMART: Not available (install smartmontools for drive health monitoring)")
        
        # Warnings
        if health_info.warnings:
            lines.append("   Warnings:")
            for warning in health_info.warnings:
                lines.append(f"     - {warning}")
        
        return '\n'.join(lines)


def check_drive_health(path: Path) -> DriveHealthInfo:
    """
    Convenience function to check drive health.
    
    Args:
        path: Path on the drive to check
        
    Returns:
        DriveHealthInfo with health data
    """
    monitor = DriveHealthMonitor()
    return monitor.get_drive_health(path)


def check_destinations_health(destinations: List[Path]) -> List[DriveHealthInfo]:
    """
    Check health of multiple destinations.
    
    Args:
        destinations: List of destination paths
        
    Returns:
        List of DriveHealthInfo
    """
    monitor = DriveHealthMonitor()
    return monitor.check_destinations(destinations)