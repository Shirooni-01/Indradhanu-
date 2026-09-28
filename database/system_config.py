"""
System Configuration & Persistence - Project Indradhanu
Provides persistent, centralized management for:
1. Exact GPS / Station Location (Latitude, Longitude, Source)
2. SMS Gateway Settings (Fast2SMS, Twilio, GSM Modem, Simulation)
Used by both the Central Dashboard (app.py) and Edge Nodes (edge_daemon.py).
"""

import os
import json
from pathlib import Path

CONFIG_FILE = Path(__file__).resolve().parent / "system_config.json"
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

DEFAULT_SYSTEM_CONFIG = {
    "latitude": 21.1458,
    "longitude": 79.0882,
    "location_name": "System Exact Position",
    "location_source": "DEFAULT",  # 'GPS_BROWSER', 'MANUAL', 'DEFAULT'
    "location_accuracy_m": 0.0,
    "sms_mode": "FAST2SMS",  # 'FAST2SMS', 'TWILIO', 'SIMULATED_CONSOLE', 'GSM_MODEM'
    "fast2sms_api_key": "",
    "twilio_account_sid": "",
    "twilio_auth_token": "",
    "twilio_from_number": "",
    "gsm_port": "COM3" if os.name == "nt" else "/dev/ttyUSB0",
    "gsm_baudrate": 115200,
    "test_mobile_number": "+91 8010294703"
}

def load_system_config():
    """Loads system configuration, falling back to defaults and environment variables."""
    cfg = dict(DEFAULT_SYSTEM_CONFIG)
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                cfg.update(saved)
        except Exception as e:
            print(f"[Config Error] Could not parse system_config.json: {e}")

    # Environment variables override if explicitly set
    if "EDGE_LATITUDE" in os.environ:
        try: cfg["latitude"] = float(os.environ["EDGE_LATITUDE"])
        except ValueError: pass
    if "EDGE_LONGITUDE" in os.environ:
        try: cfg["longitude"] = float(os.environ["EDGE_LONGITUDE"])
        except ValueError: pass
    if "SMS_MODE" in os.environ:
        cfg["sms_mode"] = os.environ["SMS_MODE"]
    if "FAST2SMS_API_KEY" in os.environ and os.environ["FAST2SMS_API_KEY"]:
        cfg["fast2sms_api_key"] = os.environ["FAST2SMS_API_KEY"]
    if "TWILIO_ACCOUNT_SID" in os.environ and os.environ["TWILIO_ACCOUNT_SID"]:
        cfg["twilio_account_sid"] = os.environ["TWILIO_ACCOUNT_SID"]
    if "TWILIO_AUTH_TOKEN" in os.environ and os.environ["TWILIO_AUTH_TOKEN"]:
        cfg["twilio_auth_token"] = os.environ["TWILIO_AUTH_TOKEN"]
    if "TWILIO_FROM_NUMBER" in os.environ and os.environ["TWILIO_FROM_NUMBER"]:
        cfg["twilio_from_number"] = os.environ["TWILIO_FROM_NUMBER"]

    return cfg

def save_system_config(new_values):
    """Saves updated configuration to system_config.json and updates .env file."""
    cfg = load_system_config()
    cfg.update(new_values)
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

    # Also sync to .env file for external daemons
    try:
        lines = [
            f"# Project Indradhanu Auto-Generated Configuration",
            f"EDGE_LATITUDE={cfg.get('latitude', 21.1458)}",
            f"EDGE_LONGITUDE={cfg.get('longitude', 79.0882)}",
            f"SMS_MODE={cfg.get('sms_mode', 'FAST2SMS')}",
            f"FAST2SMS_API_KEY={cfg.get('fast2sms_api_key', '')}",
            f"TWILIO_ACCOUNT_SID={cfg.get('twilio_account_sid', '')}",
            f"TWILIO_AUTH_TOKEN={cfg.get('twilio_auth_token', '')}",
            f"TWILIO_FROM_NUMBER={cfg.get('twilio_from_number', '')}",
            f"GSM_PORT={cfg.get('gsm_port', 'COM3')}",
            f"GSM_BAUDRATE={cfg.get('gsm_baudrate', 115200)}",
            f"TEST_MOBILE_NUMBER={cfg.get('test_mobile_number', '')}\n"
        ]
        with open(ENV_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    except Exception as e:
        print(f"[Config Warning] Could not write .env: {e}")

    return cfg
