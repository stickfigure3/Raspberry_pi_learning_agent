#!/bin/bash
# Force audio to work on 3.5mm jack

echo "Fixing audio output..."

# Set audio output to 3.5mm jack
sudo raspi-config nonint do_audio 1

# Load audio module
sudo modprobe snd_bcm2835

# Set volume to maximum on all possible controls
amixer -c 2 sset PCM 100% unmute 2>/dev/null
amixer -c 2 sset 'Headphone' 100% unmute 2>/dev/null
amixer -c 2 sset 'Digital' 100% unmute 2>/dev/null
amixer -c 0 sset Master 100% unmute 2>/dev/null
amixer -c 1 sset Master 100% unmute 2>/dev/null

# Save settings
sudo alsactl store

echo "Audio configured! Testing..."
sleep 1

# Test with speaker-test
speaker-test -t sine -f 440 -l 1 -c 2 -s 1 2>/dev/null &
SPEAKER_PID=$!
sleep 2
kill $SPEAKER_PID 2>/dev/null

echo "Done! Audio should now work."
