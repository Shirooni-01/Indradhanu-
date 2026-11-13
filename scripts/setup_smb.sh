#!/usr/bin/env bash
# ==============================================================================
# PROJECT INDRADHANU - SAMBA (SMB) WORKER RETRIEVAL SETUP SCRIPT
# Target: Raspberry Pi 3 Model B+ / Raspberry Pi 4 (Raspberry Pi OS Lite)
# PRD v2.0 Section 7: Local Image Storage and Ethernet Worker Retrieval
# ==============================================================================

set -e

echo "=================================================================="
echo " Project Indradhanu - Samba (SMB) Worker Evidence Share Setup"
echo "=================================================================="

# 1. Directory for worker image retrieval
PUBLIC_DIR="/home/pi/Indhradhanu/edge/storage/PUBLIC"
mkdir -p "$PUBLIC_DIR"
chmod 777 "$PUBLIC_DIR"
echo "[+] Public image retrieval directory ensured at: $PUBLIC_DIR"

# 2. Install Samba packages if not installed
if ! command -v smbd &> /dev/null; then
    echo "[+] Installing Samba daemon packages..."
    sudo apt-get update -y
    sudo apt-get install -y samba samba-common-bin
fi

# 3. Configure smb.conf share definition
SAMBA_CONF="/etc/samba/smb.conf"
SHARE_BLOCK="[PUBLIC]
   comment = Indradhanu Wildlife Evidence Retrieval Folder
   path = $PUBLIC_DIR
   browseable = yes
   read only = no
   guest ok = yes
   create mask = 0777
   directory mask = 0777
   force user = pi"

if grep -q "\[PUBLIC\]" "$SAMBA_CONF" 2>/dev/null; then
    echo "[!] [PUBLIC] share already present in $SAMBA_CONF. Skipping configuration append."
else
    echo "[+] Appending [PUBLIC] share definition to $SAMBA_CONF..."
    echo -e "\n$SHARE_BLOCK\n" | sudo tee -a "$SAMBA_CONF" > /dev/null
fi

# 4. Restart and enable Samba service
echo "[+] Restarting Samba service..."
sudo systemctl restart smbd nmbd || true
sudo systemctl enable smbd nmbd || true

echo "=================================================================="
echo " Samba Setup Completed Successfully!"
echo " Worker Workflow (PRD Section 7.3):"
echo " 1. Connect phone to Raspberry Pi via Ethernet adapter."
echo " 2. Open SMB-compatible Android file manager (e.g., Cx File Explorer)."
echo " 3. Connect to smb://<node-ip>/PUBLIC or smb://indradhanu.local/PUBLIC"
echo " 4. Copy images to phone, verify files, and delete retrieved copies."
echo "=================================================================="
