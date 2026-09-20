"""
Edge Node Configuration - Project Indradhanu (Project C)
Defines station identity, sensor pins, hardware abstraction, and HQ sync settings.
"""

import os

# Base directory for the edge system
EDGE_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Station Identity
# ---------------------------------------------------------------------------
NODE_CODE = os.environ.get("EDGE_NODE_CODE", "NODE-01")
NODE_NAME = os.environ.get("EDGE_NODE_NAME", "Tadoba North Perimeter Tower")
SECTOR = os.environ.get("EDGE_SECTOR", "Sector 1 (Rampur Buffer)")
LATITUDE = float(os.environ.get("EDGE_LATITUDE", 21.1458))
LONGITUDE = float(os.environ.get("EDGE_LONGITUDE", 79.0882))

# ---------------------------------------------------------------------------
# Central HQ Server (Where data is synced when network is available)
# ---------------------------------------------------------------------------
HQ_SERVER_URL = os.environ.get("HQ_SERVER_URL", "http://127.0.0.1:5000")
HEARTBEAT_INTERVAL_SEC = 10     # How often to send telemetry ping to HQ
SYNC_RETRY_INTERVAL_SEC = 5     # Retry interval for flushing offline queue

# ---------------------------------------------------------------------------
# Hardware & Simulation Settings
# ---------------------------------------------------------------------------
# Automatically detects if running on real Raspberry Pi hardware
try:
    with open("/proc/cpuinfo", "r") as f:
        IS_RASPBERRY_PI = "Raspberry Pi" in f.read()
except Exception:
    IS_RASPBERRY_PI = False

# Force simulation mode if not on physical Pi
SIMULATION_MODE = os.environ.get("EDGE_SIMULATE", "true").lower() in ("true", "1") or not IS_RASPBERRY_PI

# GPIO Pin Configuration (RPi BCM numbering)
PIN_PIR = 18                    # Hardware interrupt pin for motion sensor
PIN_SERVO_PAN = 12              # PWM pin for pan axis
PIN_SERVO_TILT = 13             # PWM pin for tilt axis

# Thermal Camera Settings
THERMAL_SENSOR_TYPE = "MLX90640"  # 'MLX90640', 'SEEK_COMPACT', or 'SIMULATED'
THERMAL_FPS = 16

# ---------------------------------------------------------------------------
# AI Model Scope (Strictly 4 species only)
# ---------------------------------------------------------------------------
TARGET_SPECIES = {
    "tiger": {
        "common_name": "Tiger",
        "scientific_name": "Panthera tigris",
        "threat_level": "CRITICAL"
    },
    "leopard": {
        "common_name": "Leopard",
        "scientific_name": "Panthera pardus",
        "threat_level": "CRITICAL"
    },
    "bear": {
        "common_name": "Indian Sloth Bear",
        "scientific_name": "Melursus ursinus",
        "threat_level": "HIGH"
    },
    "lion": {
        "common_name": "Lion",
        "scientific_name": "Panthera leo persica",
        "threat_level": "CRITICAL"
    }
}

CONFIDENCE_THRESHOLD = 0.70     # 70% minimum confidence to trigger emergency alert

# ---------------------------------------------------------------------------
# SMS Alert Gateway Settings
# ---------------------------------------------------------------------------
# Options: 'SIMULATED_CONSOLE', 'FAST2SMS', 'TWILIO', or 'GSM_MODEM' (SIM800/SIM7600)
SMS_GATEWAY_MODE = os.environ.get("SMS_MODE", "SIMULATED_CONSOLE")
GSM_SERIAL_PORT = os.environ.get("GSM_PORT", "/dev/ttyUSB0")
GSM_BAUDRATE = 115200

# 1. Fast2SMS Provider (India quick SMS API)
FAST2SMS_API_KEY = os.environ.get("FAST2SMS_API_KEY", "")

# 2. Twilio Provider (Global SMS)
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.environ.get("TWILIO_FROM_NUMBER", "")

# Destination Test Mobile Number (If set, alerts will also be sent to this number)
TEST_MOBILE_NUMBER = os.environ.get("TEST_MOBILE_NUMBER", "")

# Local Storage Database Path
DB_PATH = os.path.join(EDGE_DIR, "database", "edge.db")
SNAPSHOTS_DIR = os.path.join(EDGE_DIR, "snapshots")
os.makedirs(SNAPSHOTS_DIR, exist_ok=True)
