#!/bin/bash
# Post-pull hook script
# This runs automatically after the repo is updated

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

echo "================================================"
echo "Running post-update script at $(date)"
echo "================================================"

cd "$REPO_DIR"

# Install Python dependencies if requirements changed
if [ -f requirements.txt ]; then
    echo "Installing Python dependencies..."
    pip3 install -r requirements.txt --break-system-packages -q
fi

# Restart audio player service if it exists
if systemctl is-enabled audio-player.service &>/dev/null; then
    echo "Restarting audio player service..."
    sudo systemctl restart audio-player.service
fi


echo "Post-update script completed successfully"
