#!/bin/bash
# Interactive setup script for Spotify credentials

echo "================================================"
echo "  Spotify Player Setup"
echo "================================================"
echo ""
echo "You need to get credentials from Spotify Developer Dashboard:"
echo "1. Go to: https://developer.spotify.com/dashboard"
echo "2. Log in with your Spotify account"
echo "3. Click 'Create app'"
echo "4. Fill in app name and description"
echo "5. Accept terms and create"
echo "6. Copy your Client ID and Client Secret"
echo ""
echo "================================================"
echo ""

read -p "Enter your Spotify Client ID: " CLIENT_ID
read -p "Enter your Spotify Client Secret: " CLIENT_SECRET

CONFIG_FILE="config.yaml"
PI_IP="192.168.50.225"

# Create config file
cat > "$CONFIG_FILE" << EOF
# Spotify API Configuration
spotify:
  client_id: "$CLIENT_ID"
  client_secret: "$CLIENT_SECRET"
  redirect_uri: "http://$PI_IP:5001/callback"
  
# Spotify playback options
playback:
  player: "spotifyd"
  device_name: "Raspberry Pi"
  
# Queue settings
queue:
  max_size: 100
  auto_play: true
EOF

echo ""
echo "✅ Config file created!"
echo ""
echo "⚠️  IMPORTANT: Add this redirect URI to your Spotify app:"
echo "   http://$PI_IP:5001/callback"
echo ""
echo "Steps:"
echo "1. Go back to https://developer.spotify.com/dashboard"
echo "2. Click on your app"
echo "3. Click 'Edit Settings'"
echo "4. Under 'Redirect URIs', click 'Add'"
echo "5. Paste: http://$PI_IP:5001/callback"
echo "6. Click 'Add' then 'Save'"
echo ""
echo "Then start the server: python3 server.py"
