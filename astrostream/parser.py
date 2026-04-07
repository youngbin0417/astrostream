import struct
import threading
from typing import Optional, Callable
from .protocols.nmea import NMEAParser
from .protocols.ubx import UBXParser
from .models import GNSSPosition

class AutoParser:
    """Universal GNSS stream parser with auto-protocol detection."""
    
    MAX_NMEA_LENGTH = 150
    MAX_UBX_PAYLOAD = 2048

    def __init__(self, callback: Optional[Callable[[GNSSPosition], None]] = None):
        self.callback = callback
        self.nmea = NMEAParser()
        self.ubx = UBXParser()
        self._buffer = bytearray()
        self._lock = threading.Lock()
        
    def feed(self, data: bytes):
        """Append new bytes and process any complete packets."""
        positions = []
        with self._lock:
            self._buffer.extend(data)
            positions = self._process_buffer()
        
        # Execute callbacks outside the lock to prevent deadlocks and performance issues
        if self.callback and positions:
            for pos in positions:
                try:
                    self.callback(pos)
                except Exception:
                    # Prevent callback exceptions from crashing the parser thread
                    pass
        
    def _process_buffer(self) -> list[GNSSPosition]:
        """Internal logic to extract and route packets with efficient noise handling."""
        extracted_positions = []
        
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
                return extracted_positions
            
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
                    if len(self._buffer) > self.MAX_NMEA_LENGTH:
                        # Too long without newline or header -> safely drop the garbage
                        del self._buffer[:self.MAX_NMEA_LENGTH]
                        continue
                    return extracted_positions # Incomplete sentence
                
                # Extract sentence
                sentence_bytes = self._buffer[:nl_idx+1]
                del self._buffer[:nl_idx+1]
                
                # Prevent decoding garbage by filtering out obvious null bytes safely
                if b'\x00' in sentence_bytes:
                    continue
                
                try:
                    # errors="replace" avoids crashing safely
                    sentence = sentence_bytes.decode("ascii", errors="replace")
                    pos = self.nmea.parse(sentence)
                    if pos:
                        extracted_positions.append(pos)
                except ValueError:
                    pass
                    
            elif ubx_idx == 0:
                # Handle UBX
                # Need at least 6 bytes for the full header
                if len(self._buffer) < 6:
                    return extracted_positions
                
                cls, msg_id, length = struct.unpack("<BBH", self._buffer[2:6])
                
                # Security: Prevent memory exhaustion if length is huge
                if length > self.MAX_UBX_PAYLOAD:
                    del self._buffer[:2] # Skip preamble and search again
                    continue

                # Total packet length: Preamble(2) + Cls(1) + ID(1) + Length(2) + Payload(L) + Checksum(2)
                total_len = 6 + length + 2
                
                if len(self._buffer) < total_len:
                    return extracted_positions # Incomplete packet
                
                # Extract full packet and payload
                packet = self._buffer[:total_len]
                payload = self._buffer[6:6+length]
                
                # Verify UBX checksum
                expected_ck_a, expected_ck_b = packet[-2], packet[-1]
                if not self.ubx.verify_checksum(cls, msg_id, length, payload, expected_ck_a, expected_ck_b):
                    # Efficient re-sync: Find the next potential header instead of skipping just 2 bytes
                    next_nmea = self._buffer.find(b"$", 1)
                    next_ubx = self._buffer.find(b"\xB5\x62", 1)
                    
                    found_indices = [idx for idx in (next_nmea, next_ubx) if idx != -1]
                    if found_indices:
                        del self._buffer[:min(found_indices)]
                    else:
                        # No more headers in the current buffer, but keep the last byte 
                        # just in case it's the start of a new header (\xB5)
                        if self._buffer[-1] == 0xB5:
                            del self._buffer[:-1]
                        else:
                            self._buffer.clear()
                    continue
                
                del self._buffer[:total_len]
                
                pos = self.ubx.parse_payload(cls, msg_id, payload)
                if pos:
                    extracted_positions.append(pos)
            else:
                # Should not happen
                del self._buffer[:1]
        
        return extracted_positions
