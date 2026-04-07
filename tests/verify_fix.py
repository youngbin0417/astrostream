
import astrostream
from astrostream import AutoParser
from astrostream.models import GNSSPosition

def get_checksum(body):
    cs = 0
    for ch in body:
        cs ^= ord(ch)
    return f"{cs:02X}"

def test_ubx_blocking_vulnerability():
    print("Testing UBX blocking vulnerability...")
    results = []
    parser = AutoParser(callback=lambda p: results.append(p))
    bogus_ubx_header = bytes([0xB5, 0x62, 0x01, 0x07, 0xD0, 0x07]) # Length 2000
    parser.feed(bogus_ubx_header)
    
    body = "GPGGA,120000,3733.9900,N,12658.6800,E,1,12,1.0,50.0,M,0.0,M,,"
    valid_nmea = f"${body}*{get_checksum(body)}\r\n".encode()
    parser.feed(valid_nmea)
    if len(results) > 0:
        print("  PASS: UBX blocking fixed.")
        return True
    else:
        print("  FAIL: UBX blocking still exists.")
        return False

def test_nmea_no_fix_coords_vulnerability():
    print("Testing NMEA no-fix coords vulnerability...")
    results = []
    parser = AutoParser(callback=lambda p: results.append(p))
    
    body = "GPGGA,120000,3733.9900,N,12658.6800,E,0,00,99.9,50.0,M,0.0,M,,"
    no_fix_gga = f"${body}*{get_checksum(body)}\r\n".encode()
    parser.feed(no_fix_gga)
    
    if len(results) == 1:
        pos = results[0]
        print(f"  Fix type: {pos.fix_type}, Lat: {pos.lat}, Lon: {pos.lon}")
        if pos.lat is None and pos.lon is None:
            print("  PASS: NMEA no-fix coords are None.")
            return True
        else:
            print(f"  FAIL: NMEA no-fix coords are still present. Lat: {pos.lat}")
    else:
        print(f"  FAIL: Sentence was not parsed. Results count: {len(results)}")
    return False

if __name__ == "__main__":
    b1 = test_ubx_blocking_vulnerability()
    b2 = test_nmea_no_fix_coords_vulnerability()
    if b1 and b2:
        print("\nALL VULNERABILITIES FIXED!")
    else:
        print("\nSOME VULNERABILITIES STILL EXIST.")
        import sys
        sys.exit(1)
