"""
Project Indradhanu (Project C) - Central HQ Dashboard Runner
Starts the central tactical Flask web server & multi-camera ingestion APIs.
"""

import sys
import os

# Add root directory to python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, init_db

if __name__ == "__main__":
    init_db()
    print("=" * 65)
    print(" 🐅 PROJECT INDRADHANU - CENTRAL TACTICAL HQ DASHBOARD")
    print(" 📡 Ready to receive telemetry & detections from Edge Stations")
    print(" 🌐 Access Tactical Dashboard: http://127.0.0.1:5000")
    print("=" * 65)
    app.run(host="0.0.0.0", port=5000, debug=True)
