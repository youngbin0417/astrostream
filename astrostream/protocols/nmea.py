from typing import Optional
from copy import deepcopy
from datetime import datetime, timezone
from ..models import GNSSPosition

class NMEAParser:
    """NMEA 0183 protocol parser."""

    def __init__(self):
        # Persistence state for coordinates (required for void status handling)
        self._last_lat: Optional[float] = None
        self._last_lon: Optional[float] = None
        self._last_alt: Optional[float] = None
        
    def _verify_checksum(self, sentence: str) -> bool:
        """Verify XOR checksum of NMEA sentence."""
        if "*" not in sentence:
            return False
        
        body, checksum = sentence.split("*", 1)
        if body.startswith("$"):
            body = body[1:]
        
        calculated = 0
        for char in body:
            calculated ^= ord(char)
        
        try:
            return calculated == int(checksum, 16)
        except ValueError:
            return False

    def _dm_to_deg(self, value: str, direction: str) -> Optional[float]:
        """Convert Degree-Minutes (DDMM.MMMM) to Decimal Degrees (DD.DDDDD)."""
        if not value or not value.strip():
            return None
        
        # Split into degrees and minutes
        # Lat: DDMM.MMMM, Lon: DDDMM.MMMM
        dot_idx = value.find(".")
        if dot_idx < 0:
            # Maybe it's just degrees? (Non-standard but let's be safe)
            try:
                deg = float(value)
                return -deg if direction in ["S", "W"] else deg
            except ValueError:
                return None
            
        if dot_idx < 2:
            return None # Invalid format
        
        try:
            min_str = value[dot_idx - 2:]
            deg_str = value[:dot_idx - 2]
            
            # deg_str could be empty for very small latitudes if not zero-padded
            deg_val = float(deg_str) if deg_str else 0.0
            deg = deg_val + (float(min_str) / 60.0)
            
            if direction in ["S", "W"]:
                deg = -deg
                
            return deg
        except ValueError:
            return None

    def _create_utc_datetime(self, year, month, day, hour, minute, sec) -> Optional[datetime]:
        """Safely create datetime, handling leap seconds."""
        try:
            # Python datetime.datetime does not support second=60
            return datetime(year, month, day, hour, minute, min(sec, 59), tzinfo=timezone.utc)
        except ValueError:
            return None

    def parse(self, sentence: str) -> Optional[GNSSPosition]:
        """Parse a single NMEA sentence ($GPGGA, $GPRMC, etc.)."""
        if not self._verify_checksum(sentence):
            return None
        
        # Remove $ and *CS
        raw = sentence.strip()[1:].split("*")[0]
        fields = raw.split(",")
        if not fields:
            return None
            
        talker_id = fields[0][:2]
        msg_type = fields[0][2:]
        
        pos = GNSSPosition()
        # Initialize with last known values
        pos.lat = self._last_lat
        pos.lon = self._last_lon
        pos.alt = self._last_alt
        
        if msg_type == "GGA":
            # $GPGGA,time,lat,N,lon,E,fix,sats,hdop,alt,M,geoid,M,age,id
            if len(fields) >= 10:
                # Standardize fix type
                quality = 0
                if fields[6] and fields[6].isdigit():
                    quality = int(fields[6])
                
                if quality > 0:
                    lat = self._dm_to_deg(fields[2], fields[3])
                    lon = self._dm_to_deg(fields[4], fields[5])
                    if lat is not None and lon is not None:
                        pos.lat = self._last_lat = lat
                        pos.lon = self._last_lon = lon
                    
                    if quality in [1, 2, 3]: # GPS, DGPS, PPS fix
                        pos.fix_type = GNSSPosition.FIX_3D
                    elif quality == 4: # RTK Fixed
                        pos.fix_type = GNSSPosition.RTK_FIXED
                    elif quality == 5: # RTK Float
                        pos.fix_type = GNSSPosition.RTK_FLOAT
                else:
                    # In case of loss of fix, we keep the last coordinates in pos 
                    # but set fix_type to NO_FIX
                    pos.fix_type = GNSSPosition.NO_FIX
                
                if fields[7] and fields[7].isdigit():
                    pos.num_sats = int(fields[7])
                
                try:
                    if fields[8]: pos.hdop = float(fields[8])
                    if fields[9]: 
                        pos.alt = self._last_alt = float(fields[9])
                except ValueError:
                    pass
                    
                return pos
                
        elif msg_type == "RMC":
            # $GPRMC,time,status,lat,N,lon,E,spd,cog,date,mv,mvE,mode
            if len(fields) >= 10:
                # Update status
                status = fields[2]
                if status == "A": # Active
                    lat = self._dm_to_deg(fields[3], fields[4])
                    lon = self._dm_to_deg(fields[5], fields[6])
                    if lat is not None and lon is not None:
                        pos.lat = self._last_lat = lat
                        pos.lon = self._last_lon = lon
                    pos.fix_type = GNSSPosition.FIX_3D if pos.lat else GNSSPosition.NO_FIX
                else:
                    pos.fix_type = GNSSPosition.NO_FIX
                
                # Parse Date and Time if available
                if fields[1] and fields[9]:
                    try:
                        t_str = fields[1].split(".")[0]
                        d_str = fields[9]
                        if len(t_str) >= 6 and len(d_str) == 6:
                            hour = int(t_str[0:2])
                            minute = int(t_str[2:4])
                            sec = int(t_str[4:6])
                            day = int(d_str[0:2])
                            month = int(d_str[2:4])
                            year = 2000 + int(d_str[4:6])
                            
                            pos.timestamp = self._create_utc_datetime(year, month, day, hour, minute, sec)
                    except (ValueError, IndexError):
                        pos.timestamp = None
                return pos
                        
        return None
