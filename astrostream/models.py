from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional

@dataclass
class GNSSPosition:
    """Unified GNSS Position data."""
    timestamp: datetime = None
    lat: float = 0.0          # Decimal Degrees
    lon: float = 0.0          # Decimal Degrees
    alt: float = 0.0          # Meters
    fix_type: int = 0         # 0: No Fix, 1: 2D, 2: 3D, 4: RTK Fixed, 5: RTK Float
    num_sats: int = 0
    hdop: float = 99.9
    
    # Constellation counts: {'gps': 8, 'glonass': 4, ...}
    sat_counts: Dict[str, int] = field(default_factory=dict)
    
    def __repr__(self):
        return f"<GNSS {self.fix_type}D Fix: {self.lat:.6f}, {self.lon:.6f} Sats: {self.num_sats}>"

@dataclass
class SatelliteInfo:
    """Detailed information for a single satellite."""
    gnss_id: str              # 'gps', 'glonass', 'galileo', 'beidou', 'qzss'
    sv_id: int
    elevation: int = 0
    azimuth: int = 0
    snr: int = 0              # Signal to Noise Ratio (dB-Hz)
    is_used: bool = False
