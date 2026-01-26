#!/bin/bash
# Raspberry Pi Initial Setup Script
# Run this on your Raspberry Pi to set up the auto-deploy system

set -e

REPO_URL="${1:-}"
INSTALL_DIR="/home/pi/raspberry_pi"
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

# Check if running as pi user
if [ "$USER" != "pi" ]; then
    print_warning "Running as user '$USER' instead of 'pi'"
    print_warning "You may need to adjust paths in the service file"
fi

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

# Install the systemd service
print_status "Installing systemd service..."
sudo cp auto_deploy/git-sync.service /etc/systemd/system/
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
echo ""
print_status "Your Raspberry Pi will now auto-pull updates every 60 seconds!"
