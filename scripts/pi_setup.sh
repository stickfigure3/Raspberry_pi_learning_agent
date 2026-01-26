#!/bin/bash
# Raspberry Pi Initial Setup Script
# Run this on your Raspberry Pi to set up the auto-deploy system

set -e

REPO_URL="${1:-}"
CURRENT_USER="$(whoami)"
INSTALL_DIR="/home/$CURRENT_USER/raspberry_pi"
SERVICE_NAME="git-sync"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

echo "================================================"
echo "  Raspberry Pi Auto-Deploy Setup"
echo "================================================"
echo ""
echo "Running as user: $CURRENT_USER"
echo "Install directory: $INSTALL_DIR"
echo ""

# Check for repo URL argument
if [ -z "$REPO_URL" ]; then
    print_error "Please provide your Git repository URL"
    echo ""
    echo "Usage: ./pi_setup.sh <git-repo-url>"
    echo "Example: ./pi_setup.sh https://github.com/yourusername/raspberry_pi.git"
    echo "Example: ./pi_setup.sh git@github.com:yourusername/raspberry_pi.git"
    exit 1
fi

# Update system
print_status "Updating system packages..."
sudo apt-get update -qq

# Install dependencies
print_status "Installing dependencies..."
sudo apt-get install -y -qq git python3 python3-pip

# Set up Git credentials cache (for HTTPS)
print_status "Configuring Git..."
git config --global credential.helper store
git config --global pull.rebase false

# Clone the repository
if [ -d "$INSTALL_DIR" ]; then
    print_warning "Directory $INSTALL_DIR already exists"
    read -p "Remove and re-clone? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$INSTALL_DIR"
    else
        print_status "Keeping existing directory"
    fi
fi

if [ ! -d "$INSTALL_DIR" ]; then
    print_status "Cloning repository..."
    git clone "$REPO_URL" "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"

# Create logs directory
mkdir -p logs

# Make scripts executable
print_status "Setting up scripts..."
chmod +x auto_deploy/git_sync.py
chmod +x scripts/*.sh 2>/dev/null || true

# Create systemd service with correct user paths
print_status "Creating systemd service for user $CURRENT_USER..."
cat << EOF | sudo tee /etc/systemd/system/git-sync.service > /dev/null
[Unit]
Description=Git Auto-Sync Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$INSTALL_DIR
Environment="GIT_SYNC_REPO_PATH=$INSTALL_DIR"
Environment="GIT_SYNC_BRANCH=main"
Environment="GIT_SYNC_INTERVAL=60"
Environment="GIT_SYNC_POST_PULL=scripts/on_update.sh"
ExecStart=/usr/bin/python3 $INSTALL_DIR/auto_deploy/git_sync.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable git-sync.service
sudo systemctl start git-sync.service

# Check service status
sleep 2
if sudo systemctl is-active --quiet git-sync.service; then
    print_status "Git sync service is running!"
else
    print_error "Service failed to start. Check logs with: journalctl -u git-sync -f"
    exit 1
fi

echo ""
echo "================================================"
echo "  Setup Complete!"
echo "================================================"
echo ""
echo "The auto-sync service is now running."
echo ""
echo "Useful commands:"
echo "  View logs:      journalctl -u git-sync -f"
echo "  Service status: sudo systemctl status git-sync"
echo "  Restart:        sudo systemctl restart git-sync"
echo "  Stop:           sudo systemctl stop git-sync"
echo ""
echo "Repository location: $INSTALL_DIR"
echo "User: $CURRENT_USER"
echo ""
print_status "Your Raspberry Pi will now auto-pull updates every 60 seconds!"
