"""
PIR Motion Sensor Driver for Raspberry Pi 3 Model B+ Edge Unit.
Handles optional GPIO wake-on-interrupt when PIR_ENABLED is true.
"""

import time
import threading
from edge.config import PIN_PIR, PIR_ENABLED


class PIRSensor:
    def __init__(self, on_motion_callback=None):
        self.on_motion_callback = on_motion_callback
        self.is_armed = False
        self.sim_thread = None
        self._stop_sim = False

        if PIR_ENABLED:
            try:
                import RPi.GPIO as GPIO
                self.GPIO = GPIO
                self.GPIO.setmode(GPIO.BCM)
                self.GPIO.setup(PIN_PIR, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
                self.GPIO.add_event_detect(
                    PIN_PIR,
                    GPIO.RISING,
                    callback=self._hardware_irq_callback,
                    bouncetime=500,
                )
                print(f"[PIR] Hardware interrupt armed on GPIO pin {PIN_PIR}")
                self.is_armed = True
            except Exception as e:
                print(f"[PIR Warning] RPi.GPIO not available ({e}). Continuing without hardware PIR interrupt.")
                self.is_armed = False
        else:
            self.is_armed = False

    def _hardware_irq_callback(self, channel):
        """Called automatically on rising edge interrupt from physical PIR sensor."""
        if self.on_motion_callback:
            self.on_motion_callback()

    def trigger_simulated_motion(self):
        """Triggers motion callback programmatically for testing."""
        if self.on_motion_callback:
            self.on_motion_callback()

    def stop(self):
        self._stop_sim = True
        if hasattr(self, "GPIO"):
            try:
                self.GPIO.cleanup(PIN_PIR)
            except Exception:
                pass
