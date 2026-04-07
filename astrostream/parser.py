import struct
import threading
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
        self._lock = threading.Lock()
        
    def feed(self, data: bytes):
        """Append new bytes and process any complete packets."""
        with self._lock:
            self._buffer.extend(data)
            self._process_buffer()
        
    def _process_buffer(self):
        """Internal logic to extract and route packets with efficient noise handling."""
        while len(self._buffer) > 0:
            # Look for headers
            nmea_idx = self._buffer.find(b"$")
            ubx_idx = self._buffer.find(b"\xB5\x62")
            
            # Case 1: No headers found at all
            if nmea_idx == -1 and ubx_idx == -1:
                # Keep last byte ONLY if it could be start of a header
                if len(self._buffer) > 0:
                    last_byte = self._buffer[-1]
                    if last_byte in (0x24, 0xB5): # '$' or '\xB5'
                        del self._buffer[:-1]
                    else:
                        self._buffer.clear()
                return
            
            # Case 2: Header found. Skip any noise before the first header.
            first_idx = min(idx for idx in (nmea_idx, ubx_idx) if idx != -1)
            if first_idx > 0:
                del self._buffer[:first_idx]
                # Re-check indices after shifting
                if nmea_idx != -1: nmea_idx -= first_idx
                if ubx_idx != -1: ubx_idx -= first_idx

            if nmea_idx == 0:
                # Handle NMEA
                # Read until \n
                nl_idx = self._buffer.find(b"\n")
                
                # Check if another header interrupts this sentence
                next_nmea = self._buffer.find(b"$", 1)
                next_ubx = self._buffer.find(b"\xB5\x62", 1)
                
                interrupt_idx = -1
                if next_nmea != -1: interrupt_idx = next_nmea
                if next_ubx != -1:
                    if interrupt_idx == -1 or next_ubx < interrupt_idx:
                        interrupt_idx = next_ubx
                        
                if interrupt_idx != -1 and (nl_idx == -1 or interrupt_idx < nl_idx):
                    # Interrupted by a new header! The current NMEA is garbage.
                    del self._buffer[:interrupt_idx]
                    continue
                    
                if nl_idx == -1:
                    # Protect against memory leak
                    if len(self._buffer) > 150:
                        # 150 bytes without newline or header -> safely drop all
                        del self._buffer[:150]
                        continue
                    return # Incomplete sentence
                
                # Extract sentence
                sentence_bytes = self._buffer[:nl_idx+1]
                del self._buffer[:nl_idx+1]
                
                # 1.2: Prevent decoding garbage by filtering out obvious null bytes safely
                if b'\x00' in sentence_bytes:
                    continue
                
                try:
                    # errors="replace" avoids crashing (keeps the library running) safely
                    sentence = sentence_bytes.decode("ascii", errors="replace")
                    pos = self.nmea.parse(sentence)
                    if pos and self.callback:
                        self.callback(pos)
                except ValueError:
                    pass
                    
            elif ubx_idx == 0:
                # Handle UBX
                # Need at least 6 bytes for the full header
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
                
                # Verify UBX checksum
                expected_ck_a, expected_ck_b = packet[-2], packet[-1]
                if not self.ubx.verify_checksum(cls, msg_id, length, payload, expected_ck_a, expected_ck_b):
                    del self._buffer[:2] # Skip preamble and try again
                    continue
                
                del self._buffer[:total_len]
                
                pos = self.ubx.parse_payload(cls, msg_id, payload)
                if pos and self.callback:
                    self.callback(pos)
            else:
                # Should not happen
                del self._buffer[:1]
