"""
Project Indradhanu (Project C) - Headless Edge Station Runner
Runs an autonomous camera post on Raspberry Pi 3 Model B+.
"""

import sys
import os

# Add root directory to python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from edge.edge_daemon import main

if __name__ == "__main__":
    main()
