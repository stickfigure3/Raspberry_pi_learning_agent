#!/bin/bash
# Audio Fix and Diagnostic Script

echo "================================================"
echo "Audio Diagnostic and Fix Script"
echo "================================================"

echo ""
echo "1. Checking audio devices..."
aplay -l

echo ""
echo "2. Testing system beep (you should hear a tone)..."
speaker-test -t sine -f 440 -l 1 -c 2 -s 1 2>/dev/null || echo "speaker-test failed"

echo ""
echo "3. Checking volume levels..."
# Try different volume controls
for control in "Headphone" "PCM" "Master" "Digital"; do
    echo "Checking $control..."
    amixer -c 0 sget "$control" 2>/dev/null | grep -E 'Playback|\[.*%\]' | head -2
    amixer -c 1 sget "$control" 2>/dev/null | grep -E 'Playback|\[.*%\]' | head -2
    amixer -c 2 sget "$control" 2>/dev/null | grep -E 'Playback|\[.*%\]' | head -2
done

echo ""
echo "4. Setting volume to 100% (if possible)..."
amixer -c 2 set Headphone 100% unmute 2>/dev/null || \
amixer -c 2 set PCM 100% unmute 2>/dev/null || \
amixer -c 0 set Master 100% unmute 2>/dev/null || \
echo "Could not set volume automatically"

echo ""
echo "5. Testing mpv with explicit audio device..."
AUDIO_FILE="$HOME/raspberry_pi/audio_files/sample-12s.mp3"
if [ -f "$AUDIO_FILE" ]; then
    echo "Playing: $AUDIO_FILE"
    echo "Trying different audio outputs..."
    
    # Try auto
    echo "  - Auto device..."
    timeout 3 mpv --no-video --volume=100 --audio-device=alsa/auto "$AUDIO_FILE" 2>&1 | grep -E "AO:|Playing" | head -2
    
    # Try headphone device
    echo "  - Headphone device (plughw:2,0)..."
    timeout 3 mpv --no-video --volume=100 --audio-device=alsa/plughw:2,0 "$AUDIO_FILE" 2>&1 | grep -E "AO:|Playing" | head -2
    
    # Try HDMI
    echo "  - HDMI device (plughw:0,0)..."
    timeout 3 mpv --no-video --volume=100 --audio-device=alsa/plughw:0,0 "$AUDIO_FILE" 2>&1 | grep -E "AO:|Playing" | head -2
else
    echo "Test file not found: $AUDIO_FILE"
fi

echo ""
echo "================================================"
echo "Diagnostics Complete"
echo "================================================"
echo ""
echo "If you still can't hear audio:"
echo ""
echo "1. Check physical connections:"
echo "   - Are headphones/speakers connected?"
echo "   - Try a different audio output (HDMI vs 3.5mm jack)"
echo ""
echo "2. Configure audio output:"
echo "   sudo raspi-config"
echo "   → Advanced Options → Audio"
echo "   → Select: Force 3.5mm jack (or Force HDMI)"
echo ""
echo "3. Manually set volume:"
echo "   alsamixer"
echo "   (Use arrow keys, M to unmute, Esc to exit)"
echo ""
echo "4. Test with:"
echo "   speaker-test -t sine -f 440 -l 1"
echo ""
