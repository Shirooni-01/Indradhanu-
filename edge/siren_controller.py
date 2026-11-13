"""
Project Indradhanu - Village Siren Hardware Controller & Safe Electrical Interface
Target Hardware: Raspberry Pi GPIO -> Optocoupler Isolation Stage (PC817) -> MOSFET/Relay Driver -> 12V 115dB Industrial Siren.

Features:
- Authenticated command verification via X-Siren-Key header / token
- Hardware Watchdog Auto-Cutoff Timer (prevents stuck relay if network or server drops)
- Strict separation between SAFE_TEST mode and real HARDWARE_GPIO activation
- Never reports physical_siren_active=True unless real Raspberry Pi GPIO hardware is present and energized
"""

import os
import time
import threading
from datetime import datetime
from flask import Flask, request, jsonify

try:
    import RPi.GPIO as GPIO
    HAS_RPI_GPIO = True
except ImportError:
    GPIO = None
    HAS_RPI_GPIO = False


class SirenHardwareController:
    """
    Controls the optocoupler-isolated GPIO relay for the 115 dB village siren.
    Includes a hardware watchdog timer and strict state reporting.
    """

    def __init__(self, gpio_pin=None, api_key=None, mode=None, active_high=True):
        self.gpio_pin = int(gpio_pin or os.environ.get("SIREN_GPIO_PIN", "23"))
        self.api_key = api_key or os.environ.get("SIREN_API_KEY", "indradhanu-siren-secret-key-2026")
        self.mode = (mode or os.environ.get("SIREN_MODE", "SAFE_TEST")).upper()
        self.active_high = active_high
        self.max_duration_sec = 60

        self._lock = threading.Lock()
        self._is_energized = False
        self._active_event_id = None
        self._activated_at = None
        self._cutoff_timer = None
        self._gpio_initialized = False
        self._history = []

        if self.mode == "HARDWARE_GPIO" and HAS_RPI_GPIO:
            try:
                GPIO.setwarnings(False)
                GPIO.setmode(GPIO.BCM)
                initial_level = GPIO.LOW if self.active_high else GPIO.HIGH
                GPIO.setup(self.gpio_pin, GPIO.OUT, initial=initial_level)
                self._gpio_initialized = True
            except Exception as e:
                print(f"[Siren Controller Error] Failed initializing BCM GPIO pin {self.gpio_pin}: {e}")
                self._gpio_initialized = False

    def verify_key(self, provided_key):
        return bool(provided_key and str(provided_key).strip() == str(self.api_key).strip())

    def activate(self, event_id, species, verified_confidence, duration_sec=15, provided_key=None, requested_mode=None):
        """
        Executes an authenticated siren activation command.
        Distinguishes strictly between SAFE_TEST and physical HARDWARE_GPIO relay activation.
        """
        if not self.verify_key(provided_key):
            return {
                "acknowledged": False,
                "command_status": "REJECTED_UNAUTHORIZED",
                "physical_siren_active": False,
                "error": "Invalid or missing X-Siren-Key authentication token.",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }, 401

        effective_mode = (requested_mode or self.mode).upper()
        duration = max(1, min(int(duration_sec or 15), self.max_duration_sec))
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with self._lock:
            # Case 1: SAFE_TEST Mode (Default safe verification mode)
            if effective_mode == "SAFE_TEST":
                record = {
                    "acknowledged": True,
                    "command_status": "TEST_MODE_VERIFIED",
                    "physical_siren_active": False,
                    "siren_mode": "SAFE_TEST",
                    "event_id": event_id,
                    "species": species,
                    "verified_confidence": verified_confidence,
                    "gpio_pin": self.gpio_pin,
                    "duration_sec": duration,
                    "hardware_attached": HAS_RPI_GPIO and self._gpio_initialized,
                    "message": (
                        f"SAFE_TEST: Siren command authenticated and verified for {species} "
                        f"({verified_confidence}%). Physical relay on BCM Pin {self.gpio_pin} NOT energized."
                    ),
                    "timestamp": now_str,
                }
                self._history.insert(0, record)
                self._history = self._history[:50]
                return record, 200

            # Case 2: Physical Hardware Mode requested, verify RPi.GPIO hardware is actually initialized
            if not (HAS_RPI_GPIO and self._gpio_initialized):
                record = {
                    "acknowledged": False,
                    "command_status": "FAILED_NO_HARDWARE",
                    "physical_siren_active": False,
                    "siren_mode": effective_mode,
                    "event_id": event_id,
                    "species": species,
                    "gpio_pin": self.gpio_pin,
                    "hardware_attached": False,
                    "error": (
                        f"Hardware siren activation requested on BCM Pin {self.gpio_pin}, "
                        "but RPi.GPIO hardware interface is not present on this host."
                    ),
                    "timestamp": now_str,
                }
                self._history.insert(0, record)
                self._history = self._history[:50]
                return record, 503

            # Energize physical optocoupler relay pin on Raspberry Pi
            try:
                on_level = GPIO.HIGH if self.active_high else GPIO.LOW
                GPIO.output(self.gpio_pin, on_level)
                readback = GPIO.input(self.gpio_pin)
                physically_active = (readback == on_level)

                self._is_energized = physically_active
                self._active_event_id = event_id
                self._activated_at = now_str

                if self._cutoff_timer is not None:
                    self._cutoff_timer.cancel()
                self._cutoff_timer = threading.Timer(duration, self._watchdog_cutoff)
                self._cutoff_timer.daemon = True
                self._cutoff_timer.start()

                record = {
                    "acknowledged": physically_active,
                    "command_status": "ACKNOWLEDGED_ACTIVE" if physically_active else "FAILED_PIN_READBACK",
                    "physical_siren_active": physically_active,
                    "siren_mode": "HARDWARE_GPIO",
                    "event_id": event_id,
                    "species": species,
                    "verified_confidence": verified_confidence,
                    "gpio_pin": self.gpio_pin,
                    "duration_sec": duration,
                    "hardware_attached": True,
                    "message": (
                        f"Physical 115dB siren relay ENERGIZED on BCM Pin {self.gpio_pin} for {duration}s (Watchdog active)."
                        if physically_active
                        else f"GPIO pin {self.gpio_pin} readback failed after output command."
                    ),
                    "timestamp": now_str,
                }
                self._history.insert(0, record)
                self._history = self._history[:50]
                return record, (200 if physically_active else 500)
            except Exception as e:
                return {
                    "acknowledged": False,
                    "command_status": "FAILED_GPIO_EXCEPTION",
                    "physical_siren_active": False,
                    "siren_mode": "HARDWARE_GPIO",
                    "event_id": event_id,
                    "error": str(e),
                    "timestamp": now_str,
                }, 500

    def _watchdog_cutoff(self):
        """Hardware safety cutoff callback to de-energize relay after duration expires."""
        with self._lock:
            if HAS_RPI_GPIO and self._gpio_initialized:
                try:
                    off_level = GPIO.LOW if self.active_high else GPIO.HIGH
                    GPIO.output(self.gpio_pin, off_level)
                except Exception:
                    pass
            self._is_energized = False
            self._active_event_id = None

    def stop(self, provided_key=None):
        """Immediately de-energizes the physical siren relay."""
        if not self.verify_key(provided_key):
            return {"acknowledged": False, "error": "Unauthorized X-Siren-Key"}, 401

        with self._lock:
            if self._cutoff_timer is not None:
                self._cutoff_timer.cancel()
                self._cutoff_timer = None
            if HAS_RPI_GPIO and self._gpio_initialized:
                try:
                    off_level = GPIO.LOW if self.active_high else GPIO.HIGH
                    GPIO.output(self.gpio_pin, off_level)
                except Exception:
                    pass
            self._is_energized = False
            self._active_event_id = None
            return {
                "acknowledged": True,
                "command_status": "STOPPED",
                "physical_siren_active": False,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }, 200

    def get_status(self):
        with self._lock:
            return {
                "controller_online": True,
                "configured_mode": self.mode,
                "gpio_pin_bcm": self.gpio_pin,
                "hardware_gpio_available": HAS_RPI_GPIO and self._gpio_initialized,
                "physical_siren_active": self._is_energized,
                "active_event_id": self._active_event_id,
                "last_activated_at": self._activated_at,
                "recent_commands": self._history[:10],
            }


def create_siren_controller_app(controller=None):
    """Creates standalone Flask HTTP app for the Siren Hardware Controller daemon."""
    app = Flask(__name__)
    ctrl = controller or SirenHardwareController()

    @app.route("/api/siren/status", methods=["GET"])
    def status_endpoint():
        return jsonify(ctrl.get_status()), 200

    @app.route("/api/siren/activate", methods=["POST"])
    def activate_endpoint():
        key = request.headers.get("X-Siren-Key") or (request.json or {}).get("siren_key")
        data = request.get_json(silent=True) or {}
        res, code = ctrl.activate(
            event_id=data.get("event_id", f"manual-{int(time.time())}"),
            species=data.get("species", "Unknown"),
            verified_confidence=data.get("verified_confidence", 0.0),
            duration_sec=data.get("duration_sec", 15),
            provided_key=key,
            requested_mode=data.get("mode"),
        )
        return jsonify(res), code

    @app.route("/api/siren/stop", methods=["POST"])
    def stop_endpoint():
        key = request.headers.get("X-Siren-Key") or (request.json or {}).get("siren_key")
        res, code = ctrl.stop(provided_key=key)
        return jsonify(res), code

    return app


if __name__ == "__main__":
    port = int(os.environ.get("SIREN_CONTROLLER_PORT", "5055"))
    app = create_siren_controller_app()
    print(f"[Siren Controller] Starting Village Siren Controller on port {port}...")
    app.run(host="0.0.0.0", port=port, debug=False)
