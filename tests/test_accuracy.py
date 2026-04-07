import struct
from astrostream import AutoParser

def calculate_checksum(sentence):
    checksum = 0
    for char in sentence:
        checksum ^= ord(char)
    return f"{checksum:02X}"

def test_astrostrem_accuracy():
    # Target exact position
    # Lat: 37.566500, Lon: 126.978000, Alt: 50.0m
    target_lat = 37.566500
    target_lon = 126.978000
    target_alt = 50.0

    # 1. Generate GPS NMEA (GPGGA)
    # 37.5665 = 37 deg + 0.5665 * 60 min = 37 deg 33.9900 min
    gga_body = "GPGGA,120000,3733.9900,N,12658.6800,E,1,12,1.0,50.0,M,0.0,M,,"
    gga_sentence = f"${gga_body}*{calculate_checksum(gga_body)}\r\n".encode()

    # 2. Generate GLONASS NMEA (GLGGA)
    # Same coords, GLONASS constellation
    glgga_body = "GLGGA,120000,3733.9900,N,12658.6800,E,1,12,1.0,50.0,M,0.0,M,,"
    glgga_sentence = f"${glgga_body}*{calculate_checksum(glgga_body)}\r\n".encode()

    # 3. Generate UBX-NAV-PVT
    preamble = b"\xb5\x62"
    cls_id = b"\x01\x07"
    length = b"\x5c\x00"
    payload = bytearray(92)
    payload[20] = 3 # 3D Fix
    payload[23] = 12 # 12 Sats
    
    # lat/lon in 1e-7 deg, alt in mm
    struct.pack_into("<i", payload, 24, int(target_lon * 1e7))
    struct.pack_into("<i", payload, 28, int(target_lat * 1e7))
    struct.pack_into("<i", payload, 32, int(target_alt * 1000))
    
    ck_a, ck_b = 0, 0
    for b in cls_id + length + payload:
        ck_a = (ck_a + b) & 0xFF
        ck_b = (ck_b + ck_a) & 0xFF
    ubx_packet = preamble + cls_id + length + payload + bytes([ck_a, ck_b])

    # Let's collect results
    results = []
    
    def on_pos(pos):
        results.append(pos)

    parser = AutoParser(callback=on_pos)

    # Feed all of them at once with some noise bytes in between
    stream = gga_sentence + b"garbage_noise123" + glgga_sentence + b"\x00\xff" + ubx_packet
    
    print("Feeding composite stream to parser...")
    parser.feed(stream)

    assert len(results) == 3, f"Expected 3 parsed positions, got {len(results)}"

    print("\n--- 파싱 결과 비교 ---")
    formats = ["GPS NMEA (GPGGA)", "GLONASS NMEA (GLGGA)", "UBX 바이너리 (NAV-PVT)"]
    for i, r in enumerate(results):
        print(f"[{formats[i]}]")
        print(f" 위도: {r.lat:.6f} (오차: {abs(r.lat - target_lat):.8f})")
        print(f" 경도: {r.lon:.6f} (오차: {abs(r.lon - target_lon):.8f})")
        print(f" 고도: {r.alt:.2f} (오차: {abs(r.alt - target_alt):.6f}m)\n")
        
        # Check accuracy (NMEA float conversion has slight rounding to ~1e-6deg)
        assert abs(r.lat - target_lat) < 0.000001, f"Lat mismatch in {formats[i]}"
        assert abs(r.lon - target_lon) < 0.000001, f"Lon mismatch in {formats[i]}"

    print("✅ 모든 프로토콜에서 동일한 좌표로 정확하게 파싱되었습니다!")

if __name__ == "__main__":
    test_astrostrem_accuracy()
