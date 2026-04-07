from typing import Optional
from copy import deepcopy
from datetime import datetime, timezone
from ..models import GNSSPosition

class NMEAParser:
    """NMEA 0183 protocol parser."""
    
    def __init__(self):
        self._current_pos = GNSSPosition()
        
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

    def _dm_to_deg(self, value: str, direction: str) -> float:
        """Convert Degree-Minutes (DDMM.MMMM) to Decimal Degrees (DD.DDDDD)."""
        if not value:
            return 0.0
        
        # Split into degrees and minutes
        # Lat: DDMM.MMMM, Lon: DDDMM.MMMM
        dot_idx = value.find(".")
        if dot_idx < 0:
            return 0.0
            
        if dot_idx < 2:
            raise ValueError(f"Invalid coordinate format: {value}")
        
        min_str = value[dot_idx - 2:]
        deg_str = value[:dot_idx - 2]
        
        deg = float(deg_str) + (float(min_str) / 60.0)
        
        if direction in ["S", "W"]:
            deg = -deg
            
        return deg

    def parse(self, sentence: str) -> Optional[GNSSPosition]:
        """Parse a single NMEA sentence ($GPGGA, $GPRMC, etc.)."""
        if not self._verify_checksum(sentence):
            return None
        
        # Remove $ and *CS
        raw = sentence.strip()[1:].split("*")[0]
        fields = raw.split(",")
        if not fields:
            return None
            
        talker_id = fields[0][:2]  # Left for potential future use or context
        msg_type = fields[0][2:]
        
        # const_map could map talker ID to constellation if needed in future
        # const_map = {
        #     "GP": "gps", "GL": "glonass", "GA": "galileo", "GB": "beidou", "GQ": "qzss", "GN": "mixed"
        # }
        
        if msg_type == "GGA":
            # $GPGGA,time,lat,N,lon,E,fix,sats,hdop,alt,M,geoid,M,age,id
            if len(fields) >= 10:
                try:
                    self._current_pos.lat = self._dm_to_deg(fields[2], fields[3])
                    self._current_pos.lon = self._dm_to_deg(fields[4], fields[5])
                    
                    # Standardize fix type
                    quality = int(fields[6]) if fields[6] else 0
                    if quality in [1, 2, 3]: # GPS, DGPS, PPS fix
                        self._current_pos.fix_type = GNSSPosition.FIX_3D
                    elif quality == 4: # RTK Fixed
                        self._current_pos.fix_type = GNSSPosition.RTK_FIXED
                    elif quality == 5: # RTK Float
                        self._current_pos.fix_type = GNSSPosition.RTK_FLOAT
                    else:
                        self._current_pos.fix_type = GNSSPosition.NO_FIX

                    self._current_pos.num_sats = int(fields[7]) if fields[7] else 0
                    self._current_pos.hdop = float(fields[8]) if fields[8] else 99.9
                    self._current_pos.alt = float(fields[9]) if fields[9] else 0.0
                except ValueError:
                    return None
                
        elif msg_type == "RMC":
            # $GPRMC,time,status,lat,N,lon,E,spd,cog,date,mv,mvE,mode
            if len(fields) >= 10:
                # Update time if possible
                status = fields[2]
                if status == "A": # Active
                    try:
                        self._current_pos.lat = self._dm_to_deg(fields[3], fields[4])
                        self._current_pos.lon = self._dm_to_deg(fields[5], fields[6])
                    except ValueError:
                        return None
                
                # Parse Date and Time if available (fields[1] is time HHMMSS, fields[9] is date DDMMYY)
                if len(fields) >= 10 and fields[1] and fields[9]:
                    try:
                        t_str = fields[1].split(".")[0] # remove milliseconds
                        d_str = fields[9]
                        if len(t_str) == 6 and len(d_str) == 6:
                            hour, minute, sec = int(t_str[0:2]), int(t_str[2:4]), int(t_str[4:6])
                            day, month, year = int(d_str[0:2]), int(d_str[2:4]), 2000 + int(d_str[4:6])
                            self._current_pos.timestamp = datetime(year, month, day, hour, minute, sec, tzinfo=timezone.utc)
                    except ValueError:
                        self._current_pos.timestamp = None
                        
        return deepcopy(self._current_pos)
