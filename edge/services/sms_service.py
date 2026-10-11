"""
SMS Alert Dispatch Service - Project Indradhanu (Project C)
Dual-mode SMS Gateway:
1. Cloud SMS API (Fast2SMS for India / Twilio for International)
2. Hardware GSM/LTE HAT (SIM800 / SIM7600 via serial AT commands)
3. Simulated Console Output for development and testing
"""

import os
import re
import time
import requests
from pathlib import Path

try:
    from database.system_config import load_system_config
except Exception:
    def load_system_config():
        return {}


class SMSService:
    def __init__(self, mode=None):
        self.reload_config(mode)

    def reload_config(self, mode_override=None):
        """Reloads active credentials and settings from system_config.json / env."""
        cfg = load_system_config()
        self.mode = mode_override or cfg.get("sms_mode", os.environ.get("SMS_MODE", "FAST2SMS"))
        self.fast2sms_api_key = cfg.get("fast2sms_api_key", os.environ.get("FAST2SMS_API_KEY", "")).strip()
        self.twilio_account_sid = cfg.get("twilio_account_sid", os.environ.get("TWILIO_ACCOUNT_SID", "")).strip()
        self.twilio_auth_token = cfg.get("twilio_auth_token", os.environ.get("TWILIO_AUTH_TOKEN", "")).strip()
        self.twilio_from_number = cfg.get("twilio_from_number", os.environ.get("TWILIO_FROM_NUMBER", "")).strip()
        self.gsm_port = cfg.get("gsm_port", os.environ.get("GSM_PORT", "COM3" if os.name == "nt" else "/dev/ttyUSB0"))
        self.gsm_baudrate = int(cfg.get("gsm_baudrate", os.environ.get("GSM_BAUDRATE", 115200)))
        self.serial_conn = None

        if self.mode == "GSM_MODEM":
            try:
                import serial
                self.serial_conn = serial.Serial(self.gsm_port, self.gsm_baudrate, timeout=3)
                time.sleep(1)
                self._send_at("AT")
                self._send_at("AT+CMGF=1")
                print(f"[SMS Gateway] Hardware GSM modem initialized on {self.gsm_port}")
            except Exception as e:
                print(f"[SMS Warning] GSM Modem failed on {self.gsm_port}: {e}. Mode set to SIMULATED_CONSOLE.")
                self.mode = "SIMULATED_CONSOLE"
        elif self.mode == "FAST2SMS":
            if not self.fast2sms_api_key:
                print("[SMS Gateway] FAST2SMS mode active (API key not configured yet -> fallback simulation).")
            else:
                print("[SMS Gateway] FAST2SMS Live Cloud API active with configured API key.")
        elif self.mode == "TWILIO":
            if not (self.twilio_account_sid and self.twilio_auth_token and self.twilio_from_number):
                print("[SMS Gateway] Twilio credentials incomplete -> fallback simulation.")
            else:
                print("[SMS Gateway] Twilio Live Cloud API active.")
        else:
            print(f"[SMS Gateway] Running in mode: {self.mode}")

    def _send_at(self, cmd):
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.write((cmd + "\r\n").encode())
            time.sleep(0.3)
            return self.serial_conn.read_all().decode(errors="ignore")
        return ""

    def format_alert_message(self, species, scientific_name, threat_level, node_code, sector, distance_m):
        """Formats the official Forest Department Emergency SMS alert."""
        return (
            f"[FOREST EMERGENCY ALERT - {node_code}]\n"
            f"WILD ANIMAL DETECTED: {species.upper()} ({scientific_name})\n"
            f"Threat Level: {threat_level}\n"
            f"Sector: {sector} (~{distance_m}m from village boundary)\n"
            f"Time: {time.strftime('%H:%M:%S IST')}\n"
            f"ADVISORY: Villagers stay indoors. Secure livestock. Forest patrol dispatched."
        )

    def _send_via_fast2sms(self, recipient_phone, message):
        """Sends real SMS in India using Fast2SMS API."""
        if not self.fast2sms_api_key:
            return False, "FAST2SMS_API_KEY not configured. Enter API Key in Settings to receive real SMS."

        # Clean phone number (keep last 10 digits for Indian standard)
        digits = re.sub(r"\D", "", recipient_phone)
        if len(digits) > 10:
            digits = digits[-10:]

        if len(digits) != 10:
            return False, f"Invalid Indian mobile number: '{recipient_phone}' (Must be 10 digits)"

        url = "https://www.fast2sms.com/dev/bulkV2"
        headers = {
            "authorization": self.fast2sms_api_key,
            "Content-Type": "application/json"
        }
        payload = {
            "route": "q",
            "message": message,
            "language": "english",
            "flash": 0,
            "numbers": digits
        }
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=8)
            data = resp.json()
            if data.get("return"):
                req_id = data.get("request_id", "N/A")
                return True, f"Delivered via Fast2SMS (Req ID: {req_id})"
            return False, data.get("message", "Fast2SMS gateway rejected request")
        except Exception as e:
            return False, f"Fast2SMS connection error: {str(e)}"

    def _send_via_twilio(self, recipient_phone, message):
        """Sends real SMS globally using Twilio Messages API."""
        if not (self.twilio_account_sid and self.twilio_auth_token and self.twilio_from_number):
            return False, "Twilio credentials incomplete."

        # Format number with international prefix
        digits = re.sub(r"[^\d+]", "", recipient_phone)
        if not digits.startswith("+"):
            digits = "+91" + digits[-10:]

        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.twilio_account_sid}/Messages.json"
        auth = (self.twilio_account_sid, self.twilio_auth_token)
        data = {
            "To": digits,
            "From": self.twilio_from_number,
            "Body": message
        }
        try:
            resp = requests.post(url, data=data, auth=auth, timeout=8)
            if resp.status_code in (200, 201):
                return True, "Delivered via Twilio"
            return False, f"Twilio HTTP {resp.status_code}: {resp.text}"
        except Exception as e:
            return False, f"Twilio connection error: {str(e)}"

    def send_sms(self, recipient_phone, message):
        """
        Sends an SMS to the specified recipient.
        Returns tuple: (success: bool, status_detail: str, provider: str)
        """
        if not recipient_phone:
            return False, "No recipient phone number provided", "NONE"

        if self.mode == "GSM_MODEM" and self.serial_conn:
            try:
                self._send_at(f'AT+CMGS="{recipient_phone}"')
                time.sleep(0.2)
                self.serial_conn.write(message.encode() + bytes([26]))
                time.sleep(3)
                resp = self.serial_conn.read_all().decode(errors="ignore")
                if "+CMGS:" in resp or "OK" in resp:
                    return True, "Delivered via hardware GSM modem", "GSM_MODEM"
                return False, f"GSM modem error: {resp}", "GSM_MODEM"
            except Exception as e:
                return False, f"GSM modem communication failed: {e}", "GSM_MODEM"

        elif self.mode == "FAST2SMS":
            success, info = self._send_via_fast2sms(recipient_phone, message)
            if success:
                print(f"[SMS Fast2SMS SUCCESS] Real SMS sent to {recipient_phone}: {info}")
                return True, info, "FAST2SMS"
            else:
                print(f"[SMS Fast2SMS WARNING] {info}. Displaying simulation:")
                self._print_simulated_sms(recipient_phone, message)
                # If key was missing, inform user it was simulated
                return False, info, "FAST2SMS_SIMULATED"

        elif self.mode == "TWILIO":
            success, info = self._send_via_twilio(recipient_phone, message)
            if success:
                print(f"[SMS Twilio SUCCESS] Real SMS sent to {recipient_phone}: {info}")
                return True, info, "TWILIO"
            else:
                print(f"[SMS Twilio WARNING] {info}. Displaying simulation:")
                self._print_simulated_sms(recipient_phone, message)
                return False, info, "TWILIO_SIMULATED"

        # Default fallback: SIMULATED_CONSOLE
        self._print_simulated_sms(recipient_phone, message)
        return True, "Simulated alert printed to server console (SIMULATED mode).", "SIMULATED_CONSOLE"

    def _print_simulated_sms(self, recipient_phone, message):
        print("\n" + "=" * 65)
        print(f"[GSM SMS DISPATCH SIMULATION] -> To: {recipient_phone}")
        for line in message.split("\n"):
            print(f"   | {line}")
        print(f"   Status: [LOGGED] DISPATCHED VIA LOCAL TELEMETRY")
        print("=" * 65 + "\n")

    def broadcast_alert(self, contacts, species, scientific_name, threat_level, node_code, sector, distance_m):
        """
        Broadcasts emergency alert to all active village contacts.
        Returns: (successful_count, failed_recipients_list, alert_message, reports_list)
        """
        message = self.format_alert_message(species, scientific_name, threat_level, node_code, sector, distance_m)
        success_count = 0
        failed_list = []
        reports = []

        for c in contacts:
            phone = c.get("phone_number")
            name = c.get("full_name", "Villager")
            if not phone:
                continue

            success, detail, provider = self.send_sms(phone, message)
            report_item = {
                "name": name,
                "phone": phone,
                "success": success,
                "status": "DELIVERED" if success else "SIMULATED_OR_FAILED",
                "detail": detail,
                "provider": provider
            }
            reports.append(report_item)

            if success:
                success_count += 1
            else:
                failed_list.append({"phone": phone, "name": name, "message": message, "error": detail})

        return success_count, failed_list, message, reports

    def send_test_sms(self, recipient_phone, custom_msg=None):
        """Sends a single test SMS verification message."""
        msg = custom_msg or (
            f"[PROJECT INDRADHANU TEST ALERT]\n"
            f"Tactical Early Warning Gateway verification message.\n"
            f"Recipient: {recipient_phone}\n"
            f"Mode: {self.mode}\n"
            f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S IST')}\n"
            f"Status: SMS Gateway link operational."
        )
        success, detail, provider = self.send_sms(recipient_phone, msg)
        return {
            "success": success,
            "phone": recipient_phone,
            "provider": provider,
            "mode": self.mode,
            "detail": detail,
            "message": msg
        }
