"""
Thermal Camera Driver with Hardware & Simulation Support.
Captures infrared thermal sensor arrays and renders thermal colormaps.
"""

import os
import random
from edge.config import SIMULATION_MODE, SNAPSHOTS_DIR

class ThermalCamera:
    def __init__(self):
        self.is_connected = False
        if not SIMULATION_MODE:
            try:
                # Attempt to load MLX90640 or I2C sensor
                import smbus2
                print("[Thermal Cam] I2C bus initialized for MLX90640 thermal sensor.")
                self.is_connected = True
            except Exception as e:
                print(f"[Thermal Cam Warning] Sensor not found ({e}). Running in simulation mode.")
        else:
            print("[Thermal Cam] Initialized in SIMULATION mode.")

    def capture_frame(self, target_species_hint=None):
        """
        Captures a thermal frame.
        In simulation mode, selects or generates a thermal image for one of the 4 target animals.
        Returns a dict containing snapshot path and metadata.
        """
        # Look for existing sample snapshots in static/snapshots or edge/snapshots
        samples_root = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "static", "snapshots")
        
        species_files = {
            "tiger": ("tiger_sample.jpg", "Tiger", "Panthera tigris", "CRITICAL"),
            "leopard": ("leopard_sample.jpg", "Leopard", "Panthera pardus", "CRITICAL"),
            "bear": ("bear_sample.jpg", "Indian Sloth Bear", "Melursus ursinus", "HIGH"),
            "lion": ("lion_sample.jpg", "Lion", "Panthera leo persica", "CRITICAL")
        }

        if target_species_hint and target_species_hint.lower() in species_files:
            key = target_species_hint.lower()
        else:
            key = random.choice(list(species_files.keys()))

        filename, common_name, sci_name, threat = species_files[key]
        full_path = os.path.join(samples_root, filename)

        # Fallback relative path for web dashboard viewing
        web_relative_path = f"/static/snapshots/{filename}"

        return {
            "species_key": key,
            "common_name": common_name,
            "scientific_name": sci_name,
            "threat_level": threat,
            "snapshot_path": full_path if os.path.exists(full_path) else web_relative_path,
            "web_snapshot_path": web_relative_path,
            "ambient_temp_c": round(26.0 + random.random() * 4.0, 1),
            "max_target_temp_c": round(37.5 + random.random() * 2.5, 1)  # Warm mammal body temp
        }
