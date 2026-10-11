"""
Edge Node Configuration - Project Indradhanu
Defines edge device identity, authentication, hardware settings, and central server sync parameters.
Target Hardware: Raspberry Pi 3 Model B+ running Raspberry Pi OS Lite.
"""

import os

EDGE_DIR = os.path.dirname(os.path.abspath(__file__))

try:
    from database.system_config import load_system_config
    _SYS_CFG = load_system_config()
except Exception:
    _SYS_CFG = {}

# ---------------------------------------------------------------------------
# Edge Device Identity & Coordinates (Configurable per device)
# ---------------------------------------------------------------------------
NODE_CODE = os.environ.get("EDGE_NODE_CODE") or os.environ.get("INDRADHANU_NODE_CODE") or "NODE-01"
NODE_NAME = os.environ.get("EDGE_NODE_NAME", f"Perimeter Edge Unit ({NODE_CODE})")
SECTOR = os.environ.get("EDGE_SECTOR", "Sector 1 (Perimeter Buffer)")
LATITUDE = float(os.environ.get("EDGE_LATITUDE", _SYS_CFG.get("latitude", 21.1458)))
LONGITUDE = float(os.environ.get("EDGE_LONGITUDE", _SYS_CFG.get("longitude", 79.0882)))
FIXED_HEADING_DEG = int(os.environ.get("FIXED_HEADING_DEG", "145"))
FIRMWARE_VERSION = os.environ.get("EDGE_FIRMWARE_VERSION", "2.0.0-pi3bplus")

# ---------------------------------------------------------------------------
# Central Server Connection & Authentication
# ---------------------------------------------------------------------------
HQ_SERVER_URL = (
    os.environ.get("HQ_SERVER_URL")
    or os.environ.get("INDRADHANU_HQ_URL")
    or "http://127.0.0.1:5000"
).rstrip("/")
EDGE_API_KEY = (
    os.environ.get("EDGE_API_KEY")
    or os.environ.get("EDGE_SHARED_API_KEY")
    or _SYS_CFG.get("edge_api_key", "indradhanu-edge-secret-key-2026")
).strip()
HEARTBEAT_INTERVAL_SEC = int(os.environ.get("HEARTBEAT_INTERVAL_SEC", "10"))
SYNC_RETRY_INTERVAL_SEC = int(os.environ.get("SYNC_RETRY_INTERVAL_SEC", "5"))

# ---------------------------------------------------------------------------
# Hardware Settings (Raspberry Pi 3 Model B+ / USB or CSI Camera)
# ---------------------------------------------------------------------------
try:
    with open("/proc/cpuinfo", "r", encoding="utf-8") as f:
        IS_RASPBERRY_PI = "Raspberry Pi" in f.read()
except Exception:
    IS_RASPBERRY_PI = False

PIR_ENABLED = os.environ.get("ENABLE_PIR", "false").lower() in ("true", "1")
PIN_PIR = int(os.environ.get("PIN_PIR", "18"))
CAMERA_SOURCE = os.environ.get("CAMERA_SOURCE", "0")

# ---------------------------------------------------------------------------
# 4-Species Target Scope (Bengal Tiger, Asiatic Lion, Indian Leopard, Indian Sloth Bear)
# ---------------------------------------------------------------------------
TARGET_SPECIES = {
    "tiger": {
        "common_name": "Bengal Tiger",
        "scientific_name": "Panthera tigris tigris",
        "threat_level": "CRITICAL",
    },
    "lion": {
        "common_name": "Asiatic Lion",
        "scientific_name": "Panthera leo persica",
        "threat_level": "CRITICAL",
    },
    "leopard": {
        "common_name": "Indian Leopard",
        "scientific_name": "Panthera pardus fusca",
        "threat_level": "CRITICAL",
    },
    "bear": {
        "common_name": "Indian Sloth Bear",
        "scientific_name": "Melursus ursinus",
        "threat_level": "CRITICAL",
    },
}

CONFIDENCE_THRESHOLD = float(os.environ.get("CONFIDENCE_THRESHOLD", "0.55"))

# ---------------------------------------------------------------------------
# SMS Alert Gateway Settings (Environment-driven, no hardcoded personal data)
# ---------------------------------------------------------------------------
SMS_GATEWAY_MODE = os.environ.get("SMS_MODE", _SYS_CFG.get("sms_mode", "FAST2SMS"))
GSM_SERIAL_PORT = os.environ.get("GSM_PORT", _SYS_CFG.get("gsm_port", "COM3" if os.name == "nt" else "/dev/ttyUSB0"))
GSM_BAUDRATE = int(os.environ.get("GSM_BAUDRATE", _SYS_CFG.get("gsm_baudrate", 115200)))
FAST2SMS_API_KEY = os.environ.get("FAST2SMS_API_KEY", _SYS_CFG.get("fast2sms_api_key", ""))
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", _SYS_CFG.get("twilio_account_sid", ""))
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", _SYS_CFG.get("twilio_auth_token", ""))
TWILIO_FROM_NUMBER = os.environ.get("TWILIO_FROM_NUMBER", _SYS_CFG.get("twilio_from_number", ""))
TEST_MOBILE_NUMBER = os.environ.get("TEST_MOBILE_NUMBER", _SYS_CFG.get("test_mobile_number", ""))

# Local SQLite Buffer & Snapshot Storage Paths
DB_PATH = os.environ.get("EDGE_DB_PATH", os.path.join(EDGE_DIR, "database", "edge.db"))
SNAPSHOT_DIR = os.environ.get("EDGE_SNAPSHOT_DIR", os.path.join(EDGE_DIR, "snapshots"))
SNAPSHOTS_DIR = SNAPSHOT_DIR
os.makedirs(SNAPSHOT_DIR, exist_ok=True)
