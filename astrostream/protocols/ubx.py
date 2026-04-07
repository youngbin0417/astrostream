import struct
from typing import Optional
from copy import deepcopy
from ..models import GNSSPosition

class UBXParser:
    """u-blox binary protocol (UBX) parser."""
    
    # Message Classes
    UBX_NAV = 0x01
    
    # Message IDs
    UBX_NAV_PVT = 0x07
    
    # Minimum payload size for NAV-PVT (need at least 36 bytes)
    NAV_PVT_MIN_LENGTH = 36
    
    def __init__(self):
        self._current_pos = GNSSPosition()
        
    def verify_checksum(self, cls: int, msg_id: int, length: int, payload: bytes, expected_ck_a: int, expected_ck_b: int) -> bool:
        """Verify Fletcher-8 checksum of UBX message."""
        # Checksum is calculated over Class, ID, Length, and Payload
        header = struct.pack("<BBH", cls, msg_id, length)
        combined = header + payload
        
        ck_a, ck_b = 0, 0
        for byte in combined:
            ck_a = (ck_a + byte) & 0xFF
            ck_b = (ck_b + ck_a) & 0xFF
            
        return ck_a == expected_ck_a and ck_b == expected_ck_b

    def parse_payload(self, cls: int, msg_id: int, payload: bytes) -> Optional[GNSSPosition]:
        """Parse the payload of a UBX message."""
        if cls == self.UBX_NAV and msg_id == self.UBX_NAV_PVT:
            # Validate payload length
            if len(payload) < self.NAV_PVT_MIN_LENGTH:
                return None
            
            # NAV-PVT Payload (92 bytes)
            # iTOW(4), Year(2), Month(1), Day(1), Hour(1), Min(1), Sec(1), Valid(1), tAcc(4), nano(4),
            # fixType(1), flags(1), flags2(1), numSV(1), lon(4), lat(4), height(4), hMSL(4), hAcc(4), vAcc(4)...
            
            # fixType mapping:
            # 0: no fix, 1: dead reckoning, 2: 2D-fix, 3: 3D-fix, 4: GNSS+dead reckoning, 5: Time only
            # RTK status is in flags
            
            # Unpack key fields
            # Offset 20: fixType (B)
            # Offset 21: flags (B) - 0x18: RTK fixed, 0x10: RTK float
            # Offset 23: numSV (B)
            # Offset 24: lon (i) - 1e-7 deg
            # Offset 28: lat (i) - 1e-7 deg
            # Offset 32: height (i) - mm
            
            fix_type_raw = payload[20]
            flags = payload[21]
            # Offset 32: height (i) - mm (ellipsoid)
            # Offset 36: hMSL (i) - mm (mean sea level)
            lon_raw = struct.unpack("<i", payload[24:28])[0]
            lat_raw = struct.unpack("<i", payload[28:32])[0]
            hmsl_raw = struct.unpack("<i", payload[36:40])[0]
            
            # Convert to unified models
            self._current_pos.lat = lat_raw / 1e7
            self._current_pos.lon = lon_raw / 1e7
            self._current_pos.alt = hmsl_raw / 1000.0 # mm to meters
            self._current_pos.num_sats = num_sats
            
            # Map fix type (carrSoln is bits 6-7 -> mask 0xC0)
            if flags & 0xC0 == 0x80: # RTK Fixed
                self._current_pos.fix_type = GNSSPosition.RTK_FIXED
            elif flags & 0xC0 == 0x40: # RTK Float
                self._current_pos.fix_type = GNSSPosition.RTK_FLOAT
            elif fix_type_raw == 2:
                self._current_pos.fix_type = GNSSPosition.FIX_2D
            elif fix_type_raw == 3:
                self._current_pos.fix_type = GNSSPosition.FIX_3D
            else:
                self._current_pos.fix_type = GNSSPosition.NO_FIX
                
            # Return a copy to avoid shared reference issues
            return deepcopy(self._current_pos)
            
        return None
