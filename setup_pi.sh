#!/bin/bash
# =============================================================================
# PROJECT INDRADHANU (PROJECT C) - RASPBERRY PI AUTOMATED SETUP SCRIPT
# Target: Raspberry Pi 3 B+ / 4 / 5 running Raspberry Pi OS (Bookworm / Bullseye)
# =============================================================================

set -e

echo "====================================================================="
echo "   🐅 PROJECT INDRADHANU - EDGE NODE INSTALLER FOR RASPBERRY PI"
echo "====================================================================="

# 1. System Package Updates & Hardware Dependencies
echo "[1/6] Installing Linux System Libraries..."
sudo apt-get update
sudo apt-get install -y \
    python3-pip \
    python3-venv \
    python3-dev \
    python3-opencv \
    v4l-utils \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libatlas-base-dev \
    git

# 2. Configure Permissions for Video & GPIO
echo "[2/6] Configuring hardware group permissions for $(whoami)..."
sudo usermod -aG video,gpio,dialout $(whoami)

# 3. Create Isolated Python Virtual Environment with system-site packages
echo "[3/6] Setting up Python virtual environment..."
VENV_DIR="/home/$(whoami)/indradhanu_env"
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv --system-site-packages "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"

# 4. Install Python Dependencies
echo "[4/6] Installing Python ML & Edge dependencies..."
pip install --upgrade pip setuptools wheel

# Install GPIO library depending on OS version (Bookworm uses rpi-lgpio)
if grep -q "bookworm" /etc/os-release; then
    echo "Detected Debian Bookworm (Pi OS 12) - Installing rpi-lgpio..."
    pip install rpi-lgpio
else
    echo "Detected Debian Bullseye/Legacy - Installing RPi.GPIO..."
    pip install RPi.GPIO || pip install rpi-lgpio
fi

# Install PyTorch CPU and Ultralytics
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install ultralytics requests pillow

# 5. Verify Camera Detection
echo "[5/6] Checking for connected USB / CSI cameras..."
if v4l2-ctl --list-devices 2>/dev/null | grep -q "/dev/video"; then
    echo "✅ Camera detected on /dev/video*:"
    v4l2-ctl --list-devices
else
    echo "⚠️ Warning: No USB camera detected yet. Please plug in your USB webcam."
fi

# 6. Generate Systemd Service File
echo "[6/6] Creating systemd service for 24/7 autonomous monitoring..."
SERVICE_FILE="/etc/systemd/system/indradhanu-edge.service"
CURRENT_DIR=$(pwd)
CENTRAL_IP="${1:-http://127.0.0.1:5000}"

sudo bash -c "cat > $SERVICE_FILE" <<EOL
[Unit]
Description=Project Indradhanu Autonomous Edge Station Daemon
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$CURRENT_DIR
Environment="PATH=$VENV_DIR/bin:/usr/local/bin:/usr/bin:/bin"
Environment="HQ_SERVER_URL=$CENTRAL_IP"
Environment="EDGE_NODE_CODE=NODE-01"
Environment="PIN_PIR=18"
Environment="CAMERA_SOURCE=0"
ExecStart=$VENV_DIR/bin/python3 $CURRENT_DIR/edge/edge_daemon.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOL

sudo systemctl daemon-reload

echo "====================================================================="
echo "✅ SETUP COMPLETE!"
echo ""
echo "Quick Test Run:"
echo "   source $VENV_DIR/bin/activate"
echo "   python3 edge/edge_daemon.py --trigger-once"
echo ""
echo "To run continuously in foreground:"
echo "   python3 edge/edge_daemon.py"
echo ""
echo "To enable 24/7 background service (auto-start on boot):"
echo "   sudo systemctl enable --now indradhanu-edge.service"
echo "   sudo systemctl status indradhanu-edge.service"
echo "====================================================================="
