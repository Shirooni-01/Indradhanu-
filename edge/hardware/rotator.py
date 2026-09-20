"""
Pan-Tilt Rotator Driver with Hardware & Simulation Abstraction.
Controls camera heading to sweep the forest perimeter and aim at motion sectors.
"""

import time
import threading
from edge.config import PIN_SERVO_PAN, PIN_SERVO_TILT, SIMULATION_MODE

class PanTiltRotator:
    def __init__(self, initial_heading=145):
        self.current_heading = initial_heading
        self.tilt_angle = 15  # Slight downward angle to cover ground level
        self.is_scanning = False
        self._stop_scan = False
        self.scan_thread = None

        if not SIMULATION_MODE:
            try:
                import RPi.GPIO as GPIO
                self.GPIO = GPIO
                self.GPIO.setup(PIN_SERVO_PAN, GPIO.OUT)
                self.pan_pwm = self.GPIO.PWM(PIN_SERVO_PAN, 50)  # 50Hz PWM for servo
                self.pan_pwm.start(self._angle_to_duty(self.current_heading))
                print(f"[Rotator] Hardware PWM initialized on pin {PIN_SERVO_PAN}")
            except Exception as e:
                print(f"[Rotator Warning] Failed hardware PWM setup: {e}. Using software simulation.")
        else:
            print(f"[Rotator] Initialized in SIMULATION mode at heading {self.current_heading}°.")

    def _angle_to_duty(self, angle):
        """Converts angle (0-180) to servo duty cycle (2.5% to 12.5%)."""
        clamped = max(0, min(180, angle))
        return 2.5 + (clamped / 180.0) * 10.0

    def set_heading(self, angle):
        """Points the camera to a specific compass bearing (0-360 degrees)."""
        self.current_heading = angle % 360
        if not SIMULATION_MODE and hasattr(self, 'pan_pwm'):
            try:
                duty = self._angle_to_duty(self.current_heading % 180)
                self.pan_pwm.ChangeDutyCycle(duty)
            except Exception:
                pass
        return self.current_heading

    def get_heading(self):
        return self.current_heading

    def sweep_step(self, step_degrees=15):
        """Steps heading for perimeter patrol sweep."""
        new_angle = (self.current_heading + step_degrees) % 360
        self.set_heading(new_angle)
        return self.current_heading
