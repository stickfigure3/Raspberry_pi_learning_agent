#!/bin/bash
# Post-pull hook script
# This runs automatically after the repo is updated
# Add your deployment commands here

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

echo "================================================"
echo "Running post-update script at $(date)"
echo "================================================"

cd "$REPO_DIR"

# Example: Restart your application service
# sudo systemctl restart your-app.service

# Example: Install new Python dependencies
# if [ -f requirements.txt ]; then
#     pip3 install -r requirements.txt
# fi

# Example: Run database migrations
# python3 manage.py migrate

echo "Post-update script completed successfully"
