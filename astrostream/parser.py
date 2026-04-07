import struct
from typing import Optional, Callable
from .protocols.nmea import NMEAParser
from .protocols.ubx import UBXParser
from .models import GNSSPosition

class AutoParser:
    """Universal GNSS stream parser with auto-protocol detection."""
    
    def __init__(self, callback: Optional[Callable[[GNSSPosition], None]] = None):
        self.callback = callback
        self.nmea = NMEAParser()
        self.ubx = UBXParser()
        self._buffer = bytearray()
        
    def feed(self, data: bytes):
        """Append new bytes and process any complete packets."""
        self._buffer.extend(data)
        self._process_buffer()
        
    def _process_buffer(self):
        """Internal logic to extract and route packets."""
        while len(self._buffer) > 0:
            # Look for headers
            # NMEA starts with $ (0x24)
            # UBX starts with \xB5\x62
            
            # Find the first occurrences of headers
            nmea_idx = self._buffer.find(b"$")
            ubx_idx = self._buffer.find(b"\xB5\x62")
            
            # Case 1: No headers found
            if nmea_idx == -1 and ubx_idx == -1:
                # Discard noise if buffer is too large
                if len(self._buffer) > 1024:
                    self._buffer = self._buffer[-1024:]
                return
            
            # Determine which header came first
            if (nmea_idx != -1 and (ubx_idx == -1 or nmea_idx < ubx_idx)):
                # Handle NMEA
                # Remove noise before header
                self._buffer = self._buffer[nmea_idx:]
                # Read until \n
                nl_idx = self._buffer.find(b"\n")
                if nl_idx == -1:
                    return # Incomplete sentence
                
                # Extract sentence
                sentence_bytes = self._buffer[:nl_idx+1]
                self._buffer = self._buffer[nl_idx+1:]
                
                try:
                    sentence = sentence_bytes.decode("ascii", errors="ignore")
                    pos = self.nmea.parse(sentence)
                    if pos and self.callback:
                        self.callback(pos)
                except Exception:
                    pass
                    
            elif ubx_idx != -1:
                # Handle UBX
                # Remove noise before header
                self._buffer = self._buffer[ubx_idx:]
                
                # Need at least 6 bytes for the full header (Preamble(2), Class(1), ID(1), Length(2))
                if len(self._buffer) < 6:
                    return
                
                cls, msg_id, length = struct.unpack("<BBH", self._buffer[2:6])
                
                # Total packet length: Preamble(2) + Cls(1) + ID(1) + Length(2) + Payload(L) + Checksum(2)
                total_len = 6 + length + 2
                
                if len(self._buffer) < total_len:
                    return # Incomplete packet
                
                # Extract full packet and payload
                packet = self._buffer[:total_len]
                payload = self._buffer[6:6+length]
                self._buffer = self._buffer[total_len:]
                
                # Verify UBX checksum
                expected_ck_a, expected_ck_b = packet[-2], packet[-1]
                if not self.ubx.verify_checksum(cls, msg_id, length, payload, expected_ck_a, expected_ck_b):
                    continue
                
                pos = self.ubx.parse_payload(cls, msg_id, payload)
                if pos and self.callback:
                    self.callback(pos)
            else:
                # Should not happen
                self._buffer = self._buffer[1:]
