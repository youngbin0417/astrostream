"""Edge case tests for astrostream GNSS parser.

Tests cover:
- Shared reference independence (NMEA/UBX)
- NMEA checksum validation & multiple asterisks
- Coordinate conversion edge cases (hemispheres, empty fields, null island)
- RMC active/void status
- UBX payload length validation, checksum rejection, RTK flags
- AutoParser stream handling (noise, partial packets, byte-by-byte, interleaving)
- GNSSPosition model defaults & repr
"""
import struct
import pytest
from astrostream import AutoParser
from astrostream.models import GNSSPosition


# ── Helpers ──────────────────────────────────────────────────────────────────

def _nmea_checksum(body: str) -> str:
    cs = 0
    for ch in body:
        cs ^= ord(ch)
    return f"{cs:02X}"


def make_gga(lat_dm="3733.9900", lat_dir="N", lon_dm="12658.6800", lon_dir="E",
             fix=1, sats=12, hdop=1.0, alt=50.0, talker="GP"):
    """Build a valid $xxGGA sentence as bytes."""
    body = (f"{talker}GGA,120000,{lat_dm},{lat_dir},{lon_dm},{lon_dir},"
            f"{fix},{sats:02d},{hdop},{alt},M,0.0,M,,")
    return f"${body}*{_nmea_checksum(body)}\r\n".encode()


def make_rmc(lat_dm="3733.9900", lat_dir="N", lon_dm="12658.6800", lon_dir="E",
             status="A", talker="GP"):
    """Build a valid $xxRMC sentence as bytes."""
    body = (f"{talker}RMC,120000,{status},{lat_dm},{lat_dir},{lon_dm},{lon_dir},"
            f"0.0,0.0,070426,,,")
    return f"${body}*{_nmea_checksum(body)}\r\n".encode()


def make_ubx_nav_pvt(lat=37.5665, lon=126.978, alt=50.0,
                     fix_type=3, flags=0x00, num_sats=12):
    """Build a valid UBX NAV-PVT packet."""
    preamble = b"\xb5\x62"
    cls_id = b"\x01\x07"
    length = b"\x5c\x00"
    payload = bytearray(92)
    payload[20] = fix_type
    payload[21] = flags
    payload[23] = num_sats
    struct.pack_into("<i", payload, 24, int(lon * 1e7))
    struct.pack_into("<i", payload, 28, int(lat * 1e7))
    struct.pack_into("<i", payload, 32, int(alt * 1000))

    ck_a = ck_b = 0
    for b in cls_id + length + payload:
        ck_a = (ck_a + b) & 0xFF
        ck_b = (ck_b + ck_a) & 0xFF
    return preamble + cls_id + length + payload + bytes([ck_a, ck_b])


def _collect(data: bytes) -> list:
    """Feed data into a fresh parser and return collected positions."""
    results = []
    parser = AutoParser(callback=lambda p: results.append(p))
    parser.feed(data)
    return results


# ── 1. Shared Reference Independence ────────────────────────────────────────

class TestSharedReference:

    def test_nmea_results_are_independent_objects(self):
        """Two GGA sentences with different coords → two distinct objects."""
        gga_seoul = make_gga("3733.9900", "N", "12658.6800", "E", alt=50.0)
        gga_tokyo = make_gga("3540.5720", "N", "13939.0180", "E", alt=40.0)
        r = _collect(gga_seoul + gga_tokyo)

        assert len(r) == 2
        assert r[0] is not r[1], "Results must be independent objects"
        assert abs(r[0].lat - 37.5665) < 0.001
        assert abs(r[1].lat - 35.6762) < 0.001

    def test_ubx_results_are_independent_objects(self):
        """Two UBX packets with different coords → two distinct objects."""
        u1 = make_ubx_nav_pvt(37.5665, 126.978)
        u2 = make_ubx_nav_pvt(35.6762, 139.6503)
        r = _collect(u1 + u2)

        assert len(r) == 2
        assert r[0] is not r[1], "Results must be independent objects"
        assert abs(r[0].lat - 37.5665) < 0.001
        assert abs(r[1].lat - 35.6762) < 0.001


# ── 2. NMEA Checksum Validation ─────────────────────────────────────────────

class TestNMEAChecksum:

    def test_invalid_checksum_rejected(self):
        s = b"$GPGGA,120000,3733.9900,N,12658.6800,E,1,12,1.0,50.0,M,0.0,M,,*FF\r\n"
        assert _collect(s) == []

    def test_missing_asterisk_rejected(self):
        s = b"$GPGGA,120000,3733.9900,N,12658.6800,E,1,12,1.0,50.0,M,0.0,M,,\r\n"
        assert _collect(s) == []

    def test_multiple_asterisks_no_crash(self):
        """Corrupted sentence with extra '*' must not raise ValueError."""
        s = b"$GPGGA,12*00,3733.9900,N,12658.6800,E,1,12,1.0,50.0,M,0.0,M,,*FF\r\n"
        _collect(s)  # must not raise


# ── 3. NMEA Coordinate Edge Cases ───────────────────────────────────────────

class TestNMEACoordinates:

    def test_southern_hemisphere(self):
        r = _collect(make_gga("3352.1280", "S", "15112.5580", "E"))
        assert len(r) == 1
        assert r[0].lat < 0

    def test_western_hemisphere(self):
        r = _collect(make_gga("4042.7680", "N", "07400.3600", "W"))
        assert len(r) == 1
        assert r[0].lon < 0

    def test_south_west_both_negative(self):
        r = _collect(make_gga("3352.1280", "S", "04300.0000", "W"))
        assert len(r) == 1
        assert r[0].lat < 0
        assert r[0].lon < 0

    def test_empty_coordinate_fields(self):
        body = "GPGGA,120000,,,,,0,00,99.9,,M,,M,,"
        s = f"${body}*{_nmea_checksum(body)}\r\n".encode()
        r = _collect(s)
        assert len(r) == 1
        assert r[0].lat is None
        assert r[0].lon is None

    def test_no_fix_gga(self):
        """fix_type=0 should still parse without error."""
        r = _collect(make_gga(fix=0, sats=0))
        assert len(r) == 1
        assert r[0].fix_type == 0


# ── 4. NMEA RMC Tests ───────────────────────────────────────────────────────

class TestNMEARMC:

    def test_rmc_active_updates_position(self):
        r = _collect(make_rmc(status="A"))
        assert len(r) == 1
        assert abs(r[0].lat - 37.5665) < 0.001

    def test_rmc_void_is_handled(self):
        """V (void) status should result in None coordinates."""
        rmc_void = make_rmc("3733.9900", "N", "12658.6800", "E", status="V")
        r = _collect(rmc_void)
        assert len(r) == 1
        assert r[0].lat is None
        assert r[0].lon is None


# ── 5. UBX Edge Cases ───────────────────────────────────────────────────────

class TestUBXEdgeCases:

    def test_short_payload_no_crash(self):
        """NAV-PVT with payload < 36 bytes must not IndexError."""
        preamble = b"\xb5\x62"
        cls_id = b"\x01\x07"
        short_len = 10
        length = struct.pack("<H", short_len)
        payload = bytearray(short_len)
        ck_a = ck_b = 0
        for b in cls_id + length + payload:
            ck_a = (ck_a + b) & 0xFF
            ck_b = (ck_b + ck_a) & 0xFF
        packet = preamble + cls_id + length + payload + bytes([ck_a, ck_b])
        assert _collect(packet) == []

    def test_invalid_checksum_rejected(self):
        pkt = make_ubx_nav_pvt(37.5665, 126.978)
        corrupted = pkt[:-2] + b"\xFF\xFF"
        assert _collect(corrupted) == []

    def test_rtk_fixed_flag(self):
        # bit 6-7 = 2 (0x80)
        r = _collect(make_ubx_nav_pvt(37.5665, 126.978, flags=0x80))
        assert r[0].fix_type == 4

    def test_rtk_float_flag(self):
        # bit 6-7 = 1 (0x40)
        r = _collect(make_ubx_nav_pvt(37.5665, 126.978, flags=0x40))
        assert r[0].fix_type == 5

    def test_negative_coordinates(self):
        """Southern/Western hemisphere in UBX (signed int)."""
        r = _collect(make_ubx_nav_pvt(-22.9068, -43.1729))
        assert len(r) == 1
        assert r[0].lat < 0
        assert r[0].lon < 0
        assert abs(r[0].lat - (-22.9068)) < 0.001

    def test_unknown_message_class_ignored(self):
        preamble = b"\xb5\x62"
        cls_id = b"\x0A\x04"  # MON-VER
        pl_len = 10
        length = struct.pack("<H", pl_len)
        payload = bytearray(pl_len)
        ck_a = ck_b = 0
        for b in cls_id + length + payload:
            ck_a = (ck_a + b) & 0xFF
            ck_b = (ck_b + ck_a) & 0xFF
        pkt = preamble + cls_id + length + payload + bytes([ck_a, ck_b])
        assert _collect(pkt) == []

    def test_null_island_ubx(self):
        r = _collect(make_ubx_nav_pvt(0.0, 0.0, alt=0.0))
        assert len(r) == 1
        assert r[0].lat == 0.0 and r[0].lon == 0.0


# ── 6. AutoParser Stream Handling ────────────────────────────────────────────

class TestAutoParserStream:

    def test_empty_input(self):
        assert _collect(b"") == []

    def test_pure_noise(self):
        assert _collect(b"random noise with no protocol headers at all!") == []

    def test_byte_by_byte_nmea(self):
        """Feeding one byte at a time should still produce a result."""
        results = []
        parser = AutoParser(callback=lambda p: results.append(p))
        for b in make_gga():
            parser.feed(bytes([b]))
        assert len(results) == 1
        assert abs(results[0].lat - 37.5665) < 0.001

    def test_byte_by_byte_ubx(self):
        results = []
        parser = AutoParser(callback=lambda p: results.append(p))
        for b in make_ubx_nav_pvt():
            parser.feed(bytes([b]))
        assert len(results) == 1

    def test_partial_then_complete_nmea(self):
        gga = make_gga()
        mid = len(gga) // 2
        results = []
        parser = AutoParser(callback=lambda p: results.append(p))
        parser.feed(gga[:mid])
        assert len(results) == 0
        parser.feed(gga[mid:])
        assert len(results) == 1

    def test_partial_then_complete_ubx(self):
        ubx = make_ubx_nav_pvt()
        mid = len(ubx) // 2
        results = []
        parser = AutoParser(callback=lambda p: results.append(p))
        parser.feed(ubx[:mid])
        assert len(results) == 0
        parser.feed(ubx[mid:])
        assert len(results) == 1

    def test_noise_before_valid_packet(self):
        noise = b"\x00\xFF\xAB\xCD" * 10
        r = _collect(noise + make_gga())
        assert len(r) == 1

    def test_interleaved_nmea_ubx(self):
        data = make_gga() + make_ubx_nav_pvt(35.6762, 139.6503) + make_gga()
        r = _collect(data)
        assert len(r) == 3

    def test_no_callback_does_not_crash(self):
        parser = AutoParser(callback=None)
        parser.feed(make_gga())  # must not raise

    def test_large_noise_buffer_trimmed(self):
        parser = AutoParser(callback=lambda _: None)
        parser.feed(b"\x01\x02\x03\x04" * 300)  # 1200 bytes, no headers
        assert len(parser._buffer) <= 1024

    def test_multiple_constellations_parsed(self):
        """GP, GL, GA, GB talker IDs should all be accepted."""
        data = b""
        for t in ["GP", "GL", "GA", "GB"]:
            data += make_gga(talker=t)
        r = _collect(data)
        assert len(r) == 4


# ── 7. GNSSPosition Model ───────────────────────────────────────────────────

class TestGNSSPositionModel:

    def test_default_values(self):
        p = GNSSPosition()
        assert p.lat is None and p.lon is None and p.alt is None
        assert p.fix_type == 0
        assert p.num_sats == 0
        assert p.hdop == 99.9
        assert p.sat_counts == {}

    def test_repr_contains_key_info(self):
        p = GNSSPosition(lat=37.5665, lon=126.978, fix_type=3, num_sats=12)
        s = repr(p)
        assert "37.566500" in s
        assert "126.978000" in s
        assert "12" in s

    def test_sat_counts_isolation(self):
        """Each instance should have its own sat_counts dict."""
        a = GNSSPosition()
        b = GNSSPosition()
        a.sat_counts["gps"] = 8
        assert "gps" not in b.sat_counts


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
