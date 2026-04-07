import time
import random
import struct

def generate_nmea_gga(lat, lon, sats):
    """Generate a dummy GPGGA sentence."""
    # Simplified DDM conversion for dummy data
    lat_deg = int(lat)
    lat_min = (lat - lat_deg) * 60
    lon_deg = int(lon)
    lon_min = (lon - lon_deg) * 60
    
    sentence = f"GPGGA,123519,{lat_deg:02d}{lat_min:07.4f},N,{lon_deg:03d}{lon_min:07.4f},E,1,{sats:02d},0.9,545.4,M,46.9,M,,"
    
    # Calculate checksum
    checksum = 0
    for char in sentence:
        checksum ^= ord(char)
        
    return f"${sentence}*{checksum:02X}\r\n"

def generate_ubx_nav_pvt(lat, lon, sats):
    """Generate a dummy UBX-NAV-PVT packet."""
    # Header: B5 62 01 07 5C 00 (92 bytes payload)
    preamble = b"\xb5\x62"
    cls_id = b"\x01\x07"
    length = b"\x5c\x00"
    
    # Payload (92 bytes)
    # iTOW(4), Year(2), Month(1), Day(1), Hour(1), Min(1), Sec(1), Valid(1), tAcc(4), nano(4),
    # fixType(1), flags(1), flags2(1), numSV(1), lon(4), lat(4), height(4), hMSL(4), hAcc(4), vAcc(4)...
    
    payload = bytearray(92)
    payload[20] = 3 # 3D Fix
    payload[21] = 0x18 # RTK Fixed (for fun)
    payload[23] = sats
    
    # lat/lon in 1e-7 deg
    lat_raw = int(lat * 1e7)
    lon_raw = int(lon * 1e7)
    struct.pack_into("<i", payload, 24, lon_raw)
    struct.pack_into("<i", payload, 28, lat_raw)
    
    # Checksum
    ck_a, ck_b = 0, 0
    for b in cls_id + length + payload:
        ck_a = (ck_a + b) & 0xFF
        ck_b = (ck_b + ck_a) & 0xFF
        
    return preamble + cls_id + length + payload + bytes([ck_a, ck_b])

def run_dummy_generator(callback):
    """Loop and send mixed data."""
    lat, lon = 37.5665, 126.9780
    while True:
        sats = random.randint(12, 24)
        # Randomly choose protocol
        if random.random() > 0.5:
            data = generate_nmea_gga(lat, lon, sats).encode()
        else:
            data = generate_ubx_nav_pvt(lat, lon, sats)
            
        callback(data)
        
        # Drift coordinates slightly
        lat += 0.00001 * (random.random() - 0.5)
        lon += 0.00001 * (random.random() - 0.5)
        
        time.sleep(1.0) # 1Hz update

if __name__ == "__main__":
    from astrostream import AutoParser
    
    def on_pos(pos):
        print(f"Parsed: {pos}")
        
    parser = AutoParser(callback=on_pos)
    run_dummy_generator(parser.feed)
