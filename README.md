# 🌌 AstroStream GNSS

**AstroStream** is a lightweight, high-performance "Plug-and-Play" GNSS parser library. It is designed to automatically detect and parse various satellite data protocols from a byte stream, providing a unified and clean data interface.

---

## 🛰️ Supported Data Formats

AstroStream currently focuses on the two most widely used protocols in the industry: **NMEA 0183** and **u-blox UBX**.

### 1. NMEA 0183 (ASCII)
NMEA uses **Talker IDs** as the first two characters after the `$` to identify the constellation.

| Constellation | Talker ID | Sample Sentence (GGA) |
| :--- | :--- | :--- |
| **GPS** | `GP` | `$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47` |
| **GLONASS** | `GL` | `$GLGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*53` |
| **Galileo** | `GA` | `$GAGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*41` |
| **BeiDou** | `GB` or `BD` | `$GBGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*42` |
| **Mixed** | `GN` | `$GNGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*52` |

---

### 2. u-blox UBX (Binary)
UBX uses a `gnssId` byte in messages like `NAV-SAT` to identify constellations.

| ID | Constellation | Protocol Mapping (gnssId) |
| :--- | :--- | :--- |
| **0** | **GPS** | `0` |
| **1** | **SBAS** | `1` |
| **2** | **Galileo** | `2` |
| **3** | **BeiDou** | `3` |
| **4** | **IMES** | `4` |
| **5** | **QZSS** | `5` |
| **6** | **GLONASS** | `6` |

---

## 💎 Unified Output Example (JSON)
AstroStream summarizes all protocols into a single, easy-to-read structure.

```json
{
  "timestamp": "2026-04-07T12:00:00Z",
  "position": {
    "lat": 37.5665,
    "lon": 126.9780,
    "alt": 45.2
  },
  "satellites": {
    "gps": 8,
    "glonass": 4,
    "galileo": 2,
    "beidou": 6,
    "total": 20
  },
  "fix": "3D",
  "quality": "RTK Fixed"
}
```

---

## 🛠️ Core Engine Logic: Auto-Detection
### 3. Coordinate Data Formats
Different protocols represent geographical coordinates differently. AstroStream handles the conversion automatically to **Decimal Degrees (DD)**.

| Format | Example | Protocol |
| :--- | :--- | :--- |
| **DMS** | 37° 33' 52.1" N | Human-readable (Display only) |
| **DDM** | `3733.868, N` | **NMEA 0183** (Degrees + Decimal Minutes) |
| **DD** | `37.56447` | **Standardized Output** (Internal/API) |
| **ECEF** | `X, Y, Z` (meters) | **UBX (NAV-POSLLH)** (Earth-Centered, Earth-Fixed) |

---

## 🛠️ Core Engine Logic: Auto-Detection

AstroStream uses a state-machine based "Header Sniffer" to identify the protocol without manual configuration:

1.  **Buffer Scan**: Reads incoming bytes searching for `0x24` ($) or `0xB5` (µ).
2.  **Protocol Branching**:
    -   If `$` is found: Reads until `\n` and sends to NMEA Parser.
    -   If `0xB5 0x62` is found: Reads the next 4 bytes (Class, ID, Length), then fetches the specified payload length for UBX Parser.
3.  **Validation**: Performs Checksum (XOR for NMEA, Fletcher for UBX) before emitting data.

---

## 🚀 Quick Start (Concept)

```python
from astrostream import AutoParser

def on_data(pos):
    print(f"Lat: {pos.lat}, Lon: {pos.lon}, Satellites: {pos.num_sats}")

# Initialize parser
parser = AutoParser(callback=on_data)

# Feed raw bytes from serial port
raw_data = b"$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47"
parser.feed(raw_data)
```

---

## 🎨 Visual Dashboard
AstroStream includes a premium React-based dashboard to visualize:
- **Satellite Constellation Map** (BDS, GPS, GLONASS, Galileo).
- **Signal Strength (SNR) Graphs**.
- **Real-time Trajectory Mapping**.
