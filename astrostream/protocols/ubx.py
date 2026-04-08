import struct
from typing import Optional
from copy import deepcopy
from datetime import datetime, timezone
from ..models import GNSSPosition

class UBXParser:
    """u-blox binary protocol (UBX) parser."""
    
    # Message Classes
    UBX_NAV = 0x01
    
    # Message IDs
    UBX_NAV_PVT = 0x07
    
    # Minimum payload size for NAV-PVT (need at least 40 bytes for hMSL)
    NAV_PVT_MIN_LENGTH = 40
        
    def verify_checksum(self, cls: int, msg_id: int, length: int, payload: bytes, expected_ck_a: int, expected_ck_b: int) -> bool:
        """Verify Fletcher-8 checksum of UBX message."""
        # Checksum is calculated over Class, ID, Length, and Payload
        header = struct.pack("<BBH", cls, msg_id, length)
        
        ck_a, ck_b = 0, 0
        for byte in header:
            ck_a = (ck_a + byte) & 0xFF
            ck_b = (ck_b + ck_a) & 0xFF
        for byte in payload:
            ck_a = (ck_a + byte) & 0xFF
            ck_b = (ck_b + ck_a) & 0xFF
            
        return ck_a == expected_ck_a and ck_b == expected_ck_b

    def _create_utc_datetime(self, year, month, day, hour, minute, sec) -> Optional[datetime]:
        """Safely create datetime, handling leap seconds."""
        try:
            # Python datetime.datetime does not support second=60
            return datetime(year, month, day, hour, minute, min(sec, 59), tzinfo=timezone.utc)
        except ValueError:
            return None

    def parse_payload(self, cls: int, msg_id: int, payload: bytes) -> Optional[GNSSPosition]:
        """Parse the payload of a UBX message."""
        if cls == self.UBX_NAV and msg_id == self.UBX_NAV_PVT:
            # Validate payload length
            if len(payload) < self.NAV_PVT_MIN_LENGTH:
                return None
            
            pos = GNSSPosition()
            
            # NAV-PVT Payload (92 bytes)
            # iTOW(4), Year(2), Month(1), Day(1), Hour(1), Min(1), Sec(1), Valid(1), tAcc(4), nano(4),
            # fixType(1), flags(1), flags2(1), numSV(1), lon(4), lat(4), height(4), hMSL(4), hAcc(4), vAcc(4)...
            
            # fixType mapping:
            # 0: no fix, 1: dead reckoning, 2: 2D-fix, 3: 3D-fix, 4: GNSS+dead reckoning, 5: Time only
            
            # Unpack time (UTC)
            year = struct.unpack("<H", payload[4:6])[0]
            month, day, hour, minute, sec = payload[6:11]
            valid_flags = payload[11]
            
            # Check validDate (bit 0) and validTime (bit 1)
            if valid_flags & 0x03 == 0x03:
                pos.timestamp = self._create_utc_datetime(year, month, day, hour, minute, sec)
            else:
                pos.timestamp = None
            
            # Unpack key fields
            fix_type_raw = payload[20]
            flags = payload[21]
            num_sats = payload[23]
            lon_raw = struct.unpack("<i", payload[24:28])[0]
            lat_raw = struct.unpack("<i", payload[28:32])[0]
            hmsl_raw = struct.unpack("<i", payload[36:40])[0]
            
            # Convert to unified models
            # Only set coordinates if we have some kind of fix (2D, 3D, or RTK)
            # carrSoln: bits 6-7 of flags OR bits 3-4 (some versions)
            is_rtk_fixed = (flags & 0xC0 == 0x80) or (flags & 0x18 == 0x18)
            is_rtk_float = (flags & 0xC0 == 0x40) or (flags & 0x18 == 0x10)
            
            has_fix = (fix_type_raw in (2, 3, 4)) or is_rtk_fixed or is_rtk_float
            
            if has_fix:
                pos.lat = lat_raw / 1e7
                pos.lon = lon_raw / 1e7
                pos.alt = hmsl_raw / 1000.0 # mm to meters
            
            pos.num_sats = num_sats
            
            # Map fix type
            if is_rtk_fixed:
                pos.fix_type = GNSSPosition.RTK_FIXED
            elif is_rtk_float:
                pos.fix_type = GNSSPosition.RTK_FLOAT
            elif fix_type_raw == 2:
                pos.fix_type = GNSSPosition.FIX_2D
            elif fix_type_raw in (3, 4): # 3D or GNSS+DR
                pos.fix_type = GNSSPosition.FIX_3D
            else:
                pos.fix_type = GNSSPosition.NO_FIX
                
            return pos
            
        return None
