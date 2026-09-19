"""
Generates realistic thermal surveillance sample frames for Lion, Tiger, Leopard, and Bear.
Uses OpenCV and NumPy with realistic thermal colormaps (Ironbow/Inferno/Rainbow).
"""

import os
import numpy as np
import cv2

def create_thermal_background(width=640, height=400):
    # Base forest background with temperature gradient
    y = np.linspace(20, 24, height).reshape(-1, 1) # Cooler ground, slightly warmer foliage
    bg = np.repeat(y, width, axis=1) + np.random.normal(0, 1.5, (height, width))
    
    # Add tree trunk thermal signatures
    for _ in range(6):
        tx = np.random.randint(50, width - 50)
        t_width = np.random.randint(15, 35)
        bg[:, max(0, tx - t_width):min(width, tx + t_width)] += np.random.uniform(-2, 3)

    return bg.astype(np.float32)

def draw_animal_thermal_signature(bg, species="tiger", center=(320, 240)):
    h, w = bg.shape
    cx, cy = center
    
    # Body heat ellipse (36°C - 39°C core body temperature)
    animal_mask = np.zeros((h, w), dtype=np.float32)
    
    if species.lower() == "tiger":
        # Massive muscular torso
        cv2.ellipse(animal_mask, (cx, cy), (140, 65), 5, 0, 360, 38.5, -1)
        # Head & neck
        cv2.circle(animal_mask, (cx + 120, cy - 35), 45, 39.0, -1)
        # Limbs
        cv2.line(animal_mask, (cx - 70, cy + 30), (cx - 80, cy + 110), 37.5, 24)
        cv2.line(animal_mask, (cx - 40, cy + 30), (cx - 50, cy + 105), 37.5, 22)
        cv2.line(animal_mask, (cx + 60, cy + 30), (cx + 60, cy + 110), 37.5, 24)
        cv2.line(animal_mask, (cx + 90, cy + 30), (cx + 95, cy + 105), 37.5, 22)
        # Tail
        pts = np.array([[cx - 130, cy - 10], [cx - 170, cy + 10], [cx - 190, cy + 40]], np.int32)
        cv2.polylines(animal_mask, [pts], False, 36.5, 14)
        
        # Stripes (cooler fur variation)
        for sx in range(cx - 100, cx + 100, 22):
            cv2.line(animal_mask, (sx, cy - 50), (sx - 15, cy + 40), 33.0, 6)

    elif species.lower() == "leopard":
        # Sleek, agile feline frame
        cv2.ellipse(animal_mask, (cx, cy), (115, 48), -5, 0, 360, 38.0, -1)
        cv2.circle(animal_mask, (cx + 100, cy - 25), 36, 38.5, -1)
        # Long sleek legs
        cv2.line(animal_mask, (cx - 60, cy + 20), (cx - 70, cy + 105), 37.0, 18)
        cv2.line(animal_mask, (cx + 60, cy + 20), (cx + 65, cy + 105), 37.0, 18)
        # Characteristic long curved tail
        pts = np.array([[cx - 110, cy - 10], [cx - 150, cy - 30], [cx - 180, cy - 10]], np.int32)
        cv2.polylines(animal_mask, [pts], False, 36.0, 10)

    elif species.lower() == "bear":
        # Bulky, shaggy silhouette (Sloth bear)
        cv2.ellipse(animal_mask, (cx, cy), (125, 80), 0, 0, 360, 37.5, -1)
        cv2.circle(animal_mask, (cx + 100, cy - 20), 48, 38.0, -1)
        # Muzzle (cooler snout)
        cv2.ellipse(animal_mask, (cx + 135, cy - 15), (20, 14), 0, 0, 360, 34.0, -1)
        # Heavy thick legs
        cv2.line(animal_mask, (cx - 50, cy + 40), (cx - 60, cy + 115), 36.5, 32)
        cv2.line(animal_mask, (cx + 60, cy + 40), (cx + 60, cy + 115), 36.5, 32)

    elif species.lower() == "lion":
        # Stocky build with heavy mane
        cv2.ellipse(animal_mask, (cx, cy), (135, 62), 0, 0, 360, 38.2, -1)
        # Big Mane around neck/head
        cv2.circle(animal_mask, (cx + 115, cy - 30), 60, 36.5, -1)
        cv2.circle(animal_mask, (cx + 120, cy - 30), 38, 39.0, -1)
        cv2.line(animal_mask, (cx - 65, cy + 30), (cx - 70, cy + 110), 37.5, 24)
        cv2.line(animal_mask, (cx + 70, cy + 30), (cx + 70, cy + 110), 37.5, 24)

    # Blur mask for natural biological thermal heat dissipation
    animal_mask = cv2.GaussianBlur(animal_mask, (25, 25), 0)
    
    # Blend animal into background
    combined = np.where(animal_mask > 0, animal_mask, bg)
    return combined

def render_thermal_image(temp_matrix, output_path, label=""):
    # Normalize to 0-255 based on typical ambient to body range (15°C to 40°C)
    norm = np.clip((temp_matrix - 18.0) / (40.0 - 18.0) * 255.0, 0, 255).astype(np.uint8)
    
    # Apply Ironbow / Inferno Colormap
    colored = cv2.applyColorMap(norm, cv2.COLORMAP_INFERNO)
    
    # Add subtle thermal grain
    noise = np.random.normal(0, 3, colored.shape).astype(np.int16)
    colored = np.clip(colored.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    
    # Add HUD temperature scale tag
    cv2.putText(colored, f"TEMP: 38.4C [HEAT SIGNATURE DETECTED]", (20, 370), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1, cv2.LINE_AA)
    
    cv2.imwrite(output_path, colored)
    print(f"Generated thermal frame: {output_path}")

def generate_all_samples(output_dir="static/snapshots"):
    os.makedirs(output_dir, exist_ok=True)
    
    animals = [
        ("tiger", "tiger_sample.jpg"),
        ("leopard", "leopard_sample.jpg"),
        ("bear", "bear_sample.jpg"),
        ("lion", "lion_sample.jpg")
    ]
    
    for species, filename in animals:
        bg = create_thermal_background(640, 400)
        thermal_matrix = draw_animal_thermal_signature(bg, species, center=(310, 220))
        out_file = os.path.join(output_dir, filename)
        render_thermal_image(thermal_matrix, out_file, label=species.upper())

if __name__ == "__main__":
    generate_all_samples("d:/Ashutosh_01/Indhradhanu/static/snapshots")
