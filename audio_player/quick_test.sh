#!/bin/bash
# Quick audio test script

echo "================================================"
echo "Quick Audio Test"
echo "================================================"

AUDIO_DIR="$HOME/raspberry_pi/audio_files"
TEST_FILE="$AUDIO_DIR/sample-12s.mp3"

echo ""
echo "1. Checking if test file exists..."
if [ -f "$TEST_FILE" ]; then
    echo "✓ Found: $TEST_FILE"
else
    echo "✗ File not found: $TEST_FILE"
    exit 1
fi

echo ""
echo "2. Testing direct mpv playback..."
mpv --no-video --volume=100 --audio-device=alsa/auto "$TEST_FILE" 2>&1 | head -5

echo ""
echo "3. Testing via API..."
curl -X POST http://localhost:5000/play \
  -H "Content-Type: application/json" \
  -d '{"file": "sample-12s.mp3", "volume": 100}' 2>/dev/null | python3 -m json.tool

echo ""
echo "4. Checking playback status..."
sleep 2
curl http://localhost:5000/status 2>/dev/null | python3 -m json.tool

echo ""
echo "================================================"
echo "Test Complete!"
echo "================================================"
echo ""
echo "If you can't hear audio:"
echo "1. Check volume: alsamixer"
echo "2. Check audio output: sudo raspi-config → Advanced → Audio"
echo "3. Try: speaker-test -t sine -f 440 -l 1"
echo "4. Check if headphones/speakers are connected"
