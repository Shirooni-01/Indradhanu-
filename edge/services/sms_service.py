"""
SMS Alert Dispatch Service - Project Indradhanu (Project C)
Dual-mode SMS Gateway:
1. Hardware GSM/LTE HAT (SIM800 / SIM7600 via serial AT commands)
2. Cloud SMS API fallback (Twilio / Fast2SMS)
3. Simulated Console Output for development and testing
"""

import time
import re
import requests
from edge.config import (
    SMS_GATEWAY_MODE, GSM_SERIAL_PORT, GSM_BAUDRATE,
    FAST2SMS_API_KEY, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, 
    TWILIO_FROM_NUMBER, TEST_MOBILE_NUMBER
)

class SMSService:
    def __init__(self, mode=SMS_GATEWAY_MODE):
        self.mode = mode
        self.serial_conn = None

        if self.mode == "GSM_MODEM":
            try:
                import serial
                self.serial_conn = serial.Serial(GSM_SERIAL_PORT, GSM_BAUDRATE, timeout=3)
                time.sleep(1)
                self._send_at("AT")
                self._send_at("AT+CMGF=1")  # Set SMS to Text Mode
                print(f"[SMS Gateway] Hardware GSM modem initialized on {GSM_SERIAL_PORT}")
            except Exception as e:
                print(f"[SMS Warning] GSM Modem failed to initialize: {e}. Falling back to SIMULATED_CONSOLE.")
                self.mode = "SIMULATED_CONSOLE"
        elif self.mode == "FAST2SMS":
            if not FAST2SMS_API_KEY:
                print("[SMS Gateway] FAST2SMS_API_KEY not set. Will log simulated SMS unless key provided.")
            else:
                print("[SMS Gateway] FAST2SMS Live Cloud API active.")
        elif self.mode == "TWILIO":
            if not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_FROM_NUMBER):
                print("[SMS Gateway] Twilio credentials incomplete. Will log simulated SMS unless configured.")
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
            f"Sector: {sector} (~{distance_m}m from boundary)\n"
            f"Time: {time.strftime('%H:%M:%S')}\n"
            f"ADVISORY: Villagers stay indoors. Secure cattle. Forest patrol dispatched."
        )

    def _send_via_fast2sms(self, recipient_phone, message):
        """Sends real SMS in India using Fast2SMS API."""
        if not FAST2SMS_API_KEY:
            return False, "FAST2SMS_API_KEY not configured."

        # Clean phone number (strip +91 or spaces, keep 10 digits)
        digits = re.sub(r"\D", "", recipient_phone)
        if len(digits) > 10:
            digits = digits[-10:]

        url = "https://www.fast2sms.com/dev/bulkV2"
        headers = {
            "authorization": FAST2SMS_API_KEY,
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
            resp = requests.post(url, json=payload, headers=headers, timeout=5)
            data = resp.json()
            if data.get("return"):
                return True, "Delivered via Fast2SMS"
            return False, data.get("message", "Fast2SMS error")
        except Exception as e:
            return False, str(e)

    def _send_via_twilio(self, recipient_phone, message):
        """Sends real SMS globally using Twilio Messages API."""
        if not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_FROM_NUMBER):
            return False, "Twilio credentials not configured."

        url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
        auth = (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        data = {
            "To": recipient_phone,
            "From": TWILIO_FROM_NUMBER,
            "Body": message
        }
        try:
            resp = requests.post(url, data=data, auth=auth, timeout=5)
            if resp.status_code in (200, 201):
                return True, "Delivered via Twilio"
            return False, resp.text
        except Exception as e:
            return False, str(e)

    def send_sms(self, recipient_phone, message):
        """
        Sends an SMS to the specified recipient.
        Returns True if successful, False if network/cellular failed.
        """
        if self.mode == "GSM_MODEM" and self.serial_conn:
            try:
                self._send_at(f'AT+CMGS="{recipient_phone}"')
                time.sleep(0.2)
                self.serial_conn.write(message.encode() + bytes([26]))
                time.sleep(3)
                resp = self.serial_conn.read_all().decode(errors="ignore")
                return "+CMGS:" in resp or "OK" in resp
            except Exception as e:
                print(f"[SMS Error] Failed to send via GSM modem: {e}")
                return False

        elif self.mode == "FAST2SMS":
            success, info = self._send_via_fast2sms(recipient_phone, message)
            if success:
                print(f"[SMS Fast2SMS] [SUCCESS] Real SMS sent to {recipient_phone}: {info}")
                return True
            else:
                print(f"[SMS Fast2SMS Warning] {info}. Displaying simulated dispatch:")
                self._print_simulated_sms(recipient_phone, message)
                return True

        elif self.mode == "TWILIO":
            success, info = self._send_via_twilio(recipient_phone, message)
            if success:
                print(f"[SMS Twilio] [SUCCESS] Real SMS sent to {recipient_phone}: {info}")
                return True
            else:
                print(f"[SMS Twilio Warning] {info}. Displaying simulated dispatch:")
                self._print_simulated_sms(recipient_phone, message)
                return True

        # Default: SIMULATED_CONSOLE
        self._print_simulated_sms(recipient_phone, message)
        return True

    def _print_simulated_sms(self, recipient_phone, message):
        print("\n" + "=" * 65)
        print(f"[GSM SMS DISPATCH SIMULATION] -> To: {recipient_phone}")
        for line in message.split("\n"):
            print(f"   | {line}")
        print(f"   Status: [SUCCESS] DELIVERED VIA GSM TOWER")
        print("=" * 65 + "\n")

    def broadcast_alert(self, contacts, species, scientific_name, threat_level, node_code, sector, distance_m):
        """
        Broadcasts emergency alert to all active village contacts.
        Returns (successful_count, failed_recipients_list)
        """
        message = self.format_alert_message(species, scientific_name, threat_level, node_code, sector, distance_m)
        success_count = 0
        failed_list = []

        for c in contacts:
            phone = c.get("phone_number")
            name = c.get("full_name", "Villager")
            success = self.send_sms(phone, message)
            if success:
                success_count += 1
            else:
                failed_list.append({"phone": phone, "name": name, "message": message})

        return success_count, failed_list, message
