"""
Project Indradhanu - Edge LoRa Radio Transmitter (PRD v2.0 Section 6)
Transmits compact 20-character detection alerts from Raspberry Pi edge nodes.
Supports:
1. Physical Hardware Serial UART (e.g. /dev/serial0, /dev/ttyS0, COM ports for LoRa UART modules)
2. Direct HTTP bridge transmission to Dashboard receptor (for network-connected tests)
3. Simulated local radio logging fallback
"""

import os
import sys
import time
import requests

try:
    import serial
except ImportError:
    serial = None

from services.lora_codec import encode_lora_message, decode_lora_message


class LoRaRadioSender:
    def __init__(self, port=None, baudrate=9600, dashboard_url=None):
        self.port = port or os.environ.get("LORA_SERIAL_PORT", "/dev/serial0" if sys.platform.startswith("linux") else "COM4")
        self.baudrate = int(baudrate or os.environ.get("LORA_BAUDRATE", 9600))
        self.dashboard_url = dashboard_url or os.environ.get("HQ_SERVER_URL", "http://127.0.0.1:5000")
        self.serial_conn = None
        self._init_serial()

    def _init_serial(self):
        if serial:
            try:
                self.serial_conn = serial.Serial(
                    port=self.port,
                    baudrate=self.baudrate,
                    timeout=1.0,
                    write_timeout=1.0,
                )
                print(f"[LoRa Radio] Initialized physical UART serial port on {self.port} @ {self.baudrate} baud.")
            except Exception as e:
                # Normal when testing without physical LoRa module connected
                self.serial_conn = None
                print(f"[LoRa Radio Info] Physical serial {self.port} not open ({e}). Using radio logging/bridge mode.")

    def transmit(self, node_code, species, confidence_pct, dt=None, seq_num=1):
        """
        Encodes detection and transmits compact 20-character LoRa message.
        Format: N01T2611121445087001
        Returns: (success: bool, raw_message: str, detail: str)
        """
        try:
            raw_msg = encode_lora_message(
                node_id=node_code,
                species_name_or_code=species,
                confidence_pct=confidence_pct,
                dt=dt,
                seq_num=seq_num,
            )
        except Exception as err:
            return False, "", f"Encoding error: {err}"

        # 1. Physical Serial UART transmission
        serial_sent = False
        if self.serial_conn and self.serial_conn.is_open:
            try:
                self.serial_conn.write((raw_msg + "\r\n").encode("ascii"))
                self.serial_conn.flush()
                serial_sent = True
                print(f"[LoRa Radio] TX >> Sent {len(raw_msg)} bytes over {self.port}: '{raw_msg}'")
            except Exception as e:
                print(f"[LoRa Radio Warning] Serial write error on {self.port}: {e}")

        # 2. Local RFO Dashboard receiver bridge (if reachable for automated tests)
        bridge_sent = False
        if self.dashboard_url:
            try:
                url = f"{self.dashboard_url.rstrip('/')}/api/lora/incoming"
                resp = requests.post(url, json={"message": raw_msg}, timeout=3)
                if resp.status_code in (200, 201):
                    bridge_sent = True
            except Exception:
                bridge_sent = False

        status_detail = "Transmitted via LoRa radio" if serial_sent else (
            "Delivered to RFO receiver bridge" if bridge_sent else "Logged radio transmission (Simulated)"
        )
        print(f"[LoRa Radio TX] Node [{node_code}] >> '{raw_msg}' ({status_detail})")
        return True, raw_msg, status_detail
