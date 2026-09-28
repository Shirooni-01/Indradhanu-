"""
Edge Node Configuration - Project Indradhanu (Project C)
Defines station identity, sensor pins, hardware abstraction, and HQ sync settings.
Target Hardware: Raspberry Pi 3 Model B+ with standard USB Camera.
"""

import os
import sys

# Base directory for the edge system
EDGE_DIR = os.path.dirname(os.path.abspath(__file__))

try:
    from database.system_config import load_system_config
    _SYS_CFG = load_system_config()
except Exception:
    _SYS_CFG = {}

# ---------------------------------------------------------------------------
# Station Identity & Coordinates
# ---------------------------------------------------------------------------
NODE_CODE = os.environ.get("EDGE_NODE_CODE", "NODE-01")
NODE_NAME = os.environ.get("EDGE_NODE_NAME", "Perimeter Surveillance Tower")
SECTOR = os.environ.get("EDGE_SECTOR", "Sector 1 (Perimeter Buffer)")
LATITUDE = float(os.environ.get("EDGE_LATITUDE", _SYS_CFG.get("latitude", 21.1458)))
LONGITUDE = float(os.environ.get("EDGE_LONGITUDE", _SYS_CFG.get("longitude", 79.0882)))
FIXED_HEADING_DEG = int(os.environ.get("FIXED_HEADING_DEG", "145"))

# ---------------------------------------------------------------------------
# Central HQ Server (Where data is synced when network is available)
# ---------------------------------------------------------------------------
HQ_SERVER_URL = os.environ.get("HQ_SERVER_URL", "http://127.0.0.1:5000")
HEARTBEAT_INTERVAL_SEC = 10     # How often to send telemetry ping to HQ
SYNC_RETRY_INTERVAL_SEC = 5     # Retry interval for flushing offline queue

# ---------------------------------------------------------------------------
# Hardware Settings (Raspberry Pi 3 B+)
# ---------------------------------------------------------------------------
try:
    with open("/proc/cpuinfo", "r") as f:
        IS_RASPBERRY_PI = "Raspberry Pi" in f.read()
except Exception:
    IS_RASPBERRY_PI = False

SIMULATION_MODE = os.environ.get("EDGE_SIMULATE", "false").lower() in ("true", "1") and not IS_RASPBERRY_PI

# Hardware interrupt pin for PIR motion sensor (RPi BCM numbering)
PIN_PIR = int(os.environ.get("PIN_PIR", "18"))

# Camera Settings (Default: USB webcam index 0)
CAMERA_SOURCE = os.environ.get("CAMERA_SOURCE", "0")

# ---------------------------------------------------------------------------
# AI Model Scope (Bengal Tiger & Indian Leopard)
# ---------------------------------------------------------------------------
TARGET_SPECIES = {
    "tiger": {
        "common_name": "Bengal Tiger",
        "scientific_name": "Panthera tigris",
        "threat_level": "CRITICAL"
    },
    "leopard": {
        "common_name": "Indian Leopard",
        "scientific_name": "Panthera pardus",
        "threat_level": "CRITICAL"
    }
}

CONFIDENCE_THRESHOLD = float(os.environ.get("CONFIDENCE_THRESHOLD", "0.70"))

# ---------------------------------------------------------------------------
# SMS Alert Gateway Settings
# ---------------------------------------------------------------------------
SMS_GATEWAY_MODE = os.environ.get("SMS_MODE", _SYS_CFG.get("sms_mode", "FAST2SMS"))
GSM_SERIAL_PORT = os.environ.get("GSM_PORT", _SYS_CFG.get("gsm_port", "COM3" if os.name == "nt" else "/dev/ttyUSB0"))
GSM_BAUDRATE = int(os.environ.get("GSM_BAUDRATE", _SYS_CFG.get("gsm_baudrate", 115200)))

# 1. Fast2SMS Provider (India quick SMS API)
FAST2SMS_API_KEY = os.environ.get("FAST2SMS_API_KEY", _SYS_CFG.get("fast2sms_api_key", ""))

# 2. Twilio Provider (Global SMS)
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", _SYS_CFG.get("twilio_account_sid", ""))
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", _SYS_CFG.get("twilio_auth_token", ""))
TWILIO_FROM_NUMBER = os.environ.get("TWILIO_FROM_NUMBER", _SYS_CFG.get("twilio_from_number", ""))

TEST_MOBILE_NUMBER = os.environ.get("TEST_MOBILE_NUMBER", _SYS_CFG.get("test_mobile_number", "+91 8010294703"))

# Local Storage Database Path
DB_PATH = os.path.join(EDGE_DIR, "database", "edge.db")
SNAPSHOTS_DIR = os.path.join(EDGE_DIR, "snapshots")
os.makedirs(SNAPSHOTS_DIR, exist_ok=True)
