#!/bin/bash
# =============================================================================
# PROJECT INDRADHANU - RASPBERRY PI 3 MODEL B+ AUTOMATED SETUP SCRIPT
# Target OS: Raspberry Pi OS Lite (Bookworm / Bullseye)
# =============================================================================

set -e

echo "====================================================================="
echo "   PROJECT INDRADHANU - EDGE NODE INSTALLER (RASPBERRY PI 3 B+)"
echo "====================================================================="

HQ_URL="${1:-${HQ_SERVER_URL:-http://central-server.local:5000}}"
NODE_ID="${2:-${EDGE_NODE_CODE:-NODE-01}}"
API_KEY="${3:-${EDGE_API_KEY:-indradhanu-edge-secret-key-2026}}"

echo "Configured Central Server URL : $HQ_URL"
echo "Configured Edge Device ID     : $NODE_ID"

# 1. System Package Updates & Hardware Dependencies
echo "[1/6] Installing Linux System Libraries for Raspberry Pi OS Lite..."
sudo apt-get update || true
sudo apt-get install -y python3-pip python3-venv python3-dev v4l-utils git sqlite3 || true
sudo apt-get install -y libgl1 || sudo apt-get install -y libgl1-mesa-glx || true
sudo apt-get install -y python3-opencv libglib2.0-0 libopenblas-dev libopenblas0 || true

# 2. Configure Permissions for Video & GPIO
echo "[2/6] Configuring hardware group permissions for $(whoami)..."
sudo usermod -aG video $(whoami) 2>/dev/null || true
sudo usermod -aG dialout $(whoami) 2>/dev/null || true
sudo usermod -aG gpio $(whoami) 2>/dev/null || true

# 3. Create Isolated Python Virtual Environment
echo "[3/6] Setting up Python virtual environment..."
VENV_DIR="/home/$(whoami)/indradhanu_env"
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv --system-site-packages "$VENV_DIR" || python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

# 4. Install Python Dependencies from requirements-pi.txt
echo "[4/6] Installing Python ML & Edge dependencies..."
pip install --upgrade pip setuptools wheel || true
pip install rpi-lgpio || pip install RPi.GPIO || true
pip install --upgrade numpy opencv-python-headless || true
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu || pip install torch torchvision || true
pip install -r requirements-pi.txt || true

# 5. Verify Camera Detection
echo "[5/6] Checking for connected USB / CSI cameras..."
if v4l2-ctl --list-devices 2>/dev/null | grep -q "/dev/video"; then
    echo "Camera detected on /dev/video*:"
    v4l2-ctl --list-devices
else
    echo "Warning: No camera detected yet. Connect USB/CSI camera before starting service."
fi

# 6. Generate Systemd Service File (Environment-configurable, no hardcoded IP)
echo "[6/6] Creating systemd service for 24/7 autonomous edge monitoring..."
SERVICE_FILE="/etc/systemd/system/indradhanu-edge.service"
CURRENT_DIR=$(pwd)

sudo bash -c "cat > $SERVICE_FILE" <<EOL
[Unit]
Description=Project Indradhanu Autonomous Edge Station Daemon ($NODE_ID)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$CURRENT_DIR
Environment="PATH=$VENV_DIR/bin:/usr/local/bin:/usr/bin:/bin"
Environment="HQ_SERVER_URL=$HQ_URL"
Environment="EDGE_NODE_CODE=$NODE_ID"
Environment="EDGE_API_KEY=$API_KEY"
Environment="EDGE_TORCH_THREADS=2"
Environment="EDGE_IMGSZ=320"
Environment="CAMERA_SOURCE=0"
ExecStart=$VENV_DIR/bin/python3 $CURRENT_DIR/edge/edge_daemon.py --node $NODE_ID --hq $HQ_URL
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOL

sudo systemctl daemon-reload

echo "====================================================================="
echo "SETUP COMPLETE!"
echo "Usage:"
echo "  ./setup_pi.sh http://<CENTRAL_SERVER_HOST>:5000 NODE-01 <EDGE_API_KEY>"
echo "To enable 24/7 service:"
echo "  sudo systemctl enable --now indradhanu-edge.service"
echo "====================================================================="
