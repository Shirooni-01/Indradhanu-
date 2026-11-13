"""
System Configuration & Environment Loader - Project Indradhanu
Provides non-destructive environment variable loading and persistent system configuration
without hardcoded personal data, fixed IP addresses, or destructive .env overwrites.
"""

import os
import json
from pathlib import Path

CONFIG_FILE = Path(__file__).resolve().parent / "system_config.json"
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def load_dotenv_file(env_path=ENV_FILE):
    """Loads key=value pairs from .env into os.environ without overwriting existing process env vars."""
    if not env_path or not Path(env_path).exists():
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val
    except Exception as e:
        print(f"[Config Warning] Failed reading .env file: {e}")


# Load .env immediately on import
load_dotenv_file()

DEFAULT_SYSTEM_CONFIG = {
    "latitude": 21.1458,
    "longitude": 79.0882,
    "location_name": "Forest Perimeter Command",
    "location_source": "CONFIG",
    "location_accuracy_m": 0.0,
    "sms_mode": "SIMULATED_CONSOLE",
    "fast2sms_api_key": "",
    "twilio_account_sid": "",
    "twilio_auth_token": "",
    "twilio_from_number": "",
    "gsm_port": "COM3" if os.name == "nt" else "/dev/ttyUSB0",
    "gsm_baudrate": 115200,
    "test_mobile_number": "",
    "central_verify_conf_threshold": 0.55,
    "siren_alert_conf_threshold": 0.65,
    "siren_max_sync_delay_sec": 300,
    "siren_enabled": True,
    "siren_mode": "SAFE_TEST",
    "siren_controller_url": "http://127.0.0.1:5050",
    "siren_duration_sec": 15,
    "allowed_alert_species": ["tiger", "lion", "leopard", "bear"]
}


def load_system_config():
    """Loads system configuration, merging defaults, system_config.json, and environment variables."""
    load_dotenv_file()
    cfg = dict(DEFAULT_SYSTEM_CONFIG)
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                if isinstance(saved, dict):
                    cfg.update(saved)
        except Exception as e:
            print(f"[Config Error] Could not parse system_config.json: {e}")

    # Environment variables take precedence when explicitly provided
    env_float_map = {
        "EDGE_LATITUDE": "latitude",
        "EDGE_LONGITUDE": "longitude",
        "CENTRAL_VERIFY_CONF_THRESHOLD": "central_verify_conf_threshold",
        "SIREN_ALERT_CONF_THRESHOLD": "siren_alert_conf_threshold",
    }
    for env_key, cfg_key in env_float_map.items():
        if os.environ.get(env_key):
            try:
                cfg[cfg_key] = float(os.environ[env_key])
            except ValueError:
                pass

    env_int_map = {
        "SIREN_MAX_SYNC_DELAY_SEC": "siren_max_sync_delay_sec",
        "SIREN_DURATION_SEC": "siren_duration_sec",
        "GSM_BAUDRATE": "gsm_baudrate",
    }
    for env_key, cfg_key in env_int_map.items():
        if os.environ.get(env_key):
            try:
                cfg[cfg_key] = int(os.environ[env_key])
            except ValueError:
                pass

    env_str_map = {
        "SMS_MODE": "sms_mode",
        "FAST2SMS_API_KEY": "fast2sms_api_key",
        "TWILIO_ACCOUNT_SID": "twilio_account_sid",
        "TWILIO_AUTH_TOKEN": "twilio_auth_token",
        "TWILIO_FROM_NUMBER": "twilio_from_number",
        "GSM_PORT": "gsm_port",
        "TEST_MOBILE_NUMBER": "test_mobile_number",
        "SIREN_MODE": "siren_mode",
        "SIREN_CONTROLLER_URL": "siren_controller_url",
    }
    for env_key, cfg_key in env_str_map.items():
        if env_key in os.environ and os.environ[env_key] != "":
            cfg[cfg_key] = os.environ[env_key]

    return cfg


def save_system_config(new_values):
    """
    Saves updated configuration to system_config.json and non-destructively updates
    matching keys in .env without erasing DATABASE_URL or other secrets.
    """
    cfg = load_system_config()
    cfg.update(new_values)
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

    # Non-destructively update .env if it exists
    env_key_mapping = {
        "latitude": "EDGE_LATITUDE",
        "longitude": "EDGE_LONGITUDE",
        "sms_mode": "SMS_MODE",
        "fast2sms_api_key": "FAST2SMS_API_KEY",
        "twilio_account_sid": "TWILIO_ACCOUNT_SID",
        "twilio_auth_token": "TWILIO_AUTH_TOKEN",
        "twilio_from_number": "TWILIO_FROM_NUMBER",
        "gsm_port": "GSM_PORT",
        "gsm_baudrate": "GSM_BAUDRATE",
        "test_mobile_number": "TEST_MOBILE_NUMBER",
        "siren_mode": "SIREN_MODE",
        "siren_controller_url": "SIREN_CONTROLLER_URL",
    }

    updates_for_env = {}
    for k, v in new_values.items():
        if k in env_key_mapping and v is not None:
            env_name = env_key_mapping[k]
            updates_for_env[env_name] = str(v)
            os.environ[env_name] = str(v)

    if updates_for_env and ENV_FILE.exists():
        try:
            existing_lines = []
            with open(ENV_FILE, "r", encoding="utf-8") as f:
                existing_lines = f.readlines()

            seen_keys = set()
            new_lines = []
            for line in existing_lines:
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and "=" in stripped:
                    k = stripped.split("=", 1)[0].strip()
                    if k in updates_for_env:
                        new_lines.append(f"{k}={updates_for_env[k]}\n")
                        seen_keys.add(k)
                    else:
                        new_lines.append(line if line.endswith("\n") else line + "\n")
                else:
                    new_lines.append(line if line.endswith("\n") else line + "\n")

            for k, v in updates_for_env.items():
                if k not in seen_keys:
                    new_lines.append(f"{k}={v}\n")

            with open(ENV_FILE, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
        except Exception as e:
            print(f"[Config Warning] Could not update .env: {e}")

    return cfg
