"""
PIR Motion Sensor Driver with Hardware & Simulation Abstraction.
Handles wake-on-interrupt to keep the edge device in ultra-low power standby.
"""

import time
import threading
from edge.config import PIN_PIR, SIMULATION_MODE

class PIRSensor:
    def __init__(self, on_motion_callback=None):
        self.on_motion_callback = on_motion_callback
        self.is_armed = False
        self.sim_thread = None
        self._stop_sim = False

        if not SIMULATION_MODE:
            try:
                import RPi.GPIO as GPIO
                self.GPIO = GPIO
                self.GPIO.setmode(GPIO.BCM)
                self.GPIO.setup(PIN_PIR, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
                self.GPIO.add_event_detect(
                    PIN_PIR, 
                    GPIO.RISING, 
                    callback=self._hardware_irq_callback, 
                    bouncetime=500
                )
                print(f"[PIR] Hardware interrupt armed on GPIO pin {PIN_PIR}")
                self.is_armed = True
            except Exception as e:
                print(f"[PIR Warning] Failed to initialize RPi.GPIO: {e}. Falling back to simulation mode.")
                self.is_armed = True
        else:
            print("[PIR] Running in SIMULATION mode (no physical GPIO required).")
            self.is_armed = True

    def _hardware_irq_callback(self, channel):
        """Called automatically on rising edge interrupt from physical PIR sensor."""
        if self.on_motion_callback:
            self.on_motion_callback()

    def trigger_simulated_motion(self):
        """Allows programmatic simulation of motion trigger from testing scripts or keyboard."""
        print("[PIR] Simulated motion event triggered!")
        if self.on_motion_callback:
            self.on_motion_callback()

    def start_periodic_simulation(self, interval_sec=15):
        """Runs a background timer that triggers motion periodically for testing."""
        self._stop_sim = False
        def loop():
            while not self._stop_sim:
                time.sleep(interval_sec)
                if not self._stop_sim:
                    self.trigger_simulated_motion()
        self.sim_thread = threading.Thread(target=loop, daemon=True)
        self.sim_thread.start()

    def stop(self):
        self._stop_sim = True
        if not SIMULATION_MODE and hasattr(self, 'GPIO'):
            try:
                self.GPIO.cleanup(PIN_PIR)
            except Exception:
                pass
