from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional

@dataclass
class GNSSPosition:
    """Unified GNSS Position data."""
    # Fix types constants
    NO_FIX = 0
    FIX_2D = 2
    FIX_3D = 3
    RTK_FIXED = 4
    RTK_FLOAT = 5

    timestamp: Optional[datetime] = None
    lat: Optional[float] = None          # Decimal Degrees
    lon: Optional[float] = None          # Decimal Degrees
    alt: Optional[float] = None          # Meters
    fix_type: int = 0                    # Standardized using constants above
    num_sats: int = 0
    hdop: float = 99.9
    
    # Constellation counts: {'gps': 8, 'glonass': 4, ...}
    sat_counts: Dict[str, int] = field(default_factory=dict)
    
    def __repr__(self):
        fix_str = {
            self.NO_FIX: "No Fix",
            self.FIX_2D: "2D Fix",
            self.FIX_3D: "3D Fix",
            self.RTK_FIXED: "RTK Fixed",
            self.RTK_FLOAT: "RTK Float"
        }.get(self.fix_type, f"Unknown({self.fix_type})")
        
        lat_str = f"{self.lat:.6f}" if self.lat is not None else "None"
        lon_str = f"{self.lon:.6f}" if self.lon is not None else "None"
        return f"<GNSS {fix_str}: {lat_str}, {lon_str} Sats: {self.num_sats}>"

@dataclass
class SatelliteInfo:
    """Detailed information for a single satellite."""
    gnss_id: str              # 'gps', 'glonass', 'galileo', 'beidou', 'qzss'
    sv_id: int
    elevation: int = 0
    azimuth: int = 0
    snr: int = 0              # Signal to Noise Ratio (dB-Hz)
    is_used: bool = False
