#!/usr/bin/env python3
"""
Audio System Test Script
Tests audio playback on Raspberry Pi.
"""

import subprocess
import sys
import os
from pathlib import Path

def test_audio_devices():
    """Test if audio devices are available."""
    print("=" * 50)
    print("Test 1: Checking Audio Devices")
    print("=" * 50)
    
    # Check ALSA devices
    result = subprocess.run(["aplay", "-l"], capture_output=True, text=True)
    if result.returncode == 0:
        print("✓ ALSA devices found:")
        print(result.stdout)
    else:
        print("✗ No ALSA devices found")
        print(result.stderr)
    
    # Check for pulseaudio
    result = subprocess.run(["pactl", "list", "short", "sinks"], capture_output=True, text=True)
    if result.returncode == 0 and result.stdout.strip():
        print("\n✓ PulseAudio sinks found:")
        print(result.stdout)
    else:
        print("\n✗ No PulseAudio sinks found")
    
    return True


def test_mpv():
    """Test if mpv is installed and working."""
    print("\n" + "=" * 50)
    print("Test 2: Checking mpv Installation")
    print("=" * 50)
    
    result = subprocess.run(["which", "mpv"], capture_output=True, text=True)
    if result.returncode == 0:
        mpv_path = result.stdout.strip()
        print(f"✓ mpv found at: {mpv_path}")
        
        # Get version
        version_result = subprocess.run(["mpv", "--version"], capture_output=True, text=True)
        print(version_result.stdout.split('\n')[0])
        return True
    else:
        print("✗ mpv not found")
        print("Install with: sudo apt install mpv")
        return False


def generate_test_tone():
    """Generate a test audio file using sox or ffmpeg."""
    print("\n" + "=" * 50)
    print("Test 3: Generating Test Audio File")
    print("=" * 50)
    
    audio_dir = Path.home() / "raspberry_pi" / "audio_files"
    audio_dir.mkdir(parents=True, exist_ok=True)
    test_file = audio_dir / "test_tone.wav"
    
    # Try using sox first
    if subprocess.run(["which", "sox"], capture_output=True).returncode == 0:
        print("Using sox to generate test tone...")
        cmd = [
            "sox", "-n", "-r", "44100", str(test_file),
            "synth", "2", "sine", "440"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✓ Test tone generated: {test_file}")
            return str(test_file)
    
    # Try using ffmpeg
    if subprocess.run(["which", "ffmpeg"], capture_output=True).returncode == 0:
        print("Using ffmpeg to generate test tone...")
        cmd = [
            "ffmpeg", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-ar", "44100", "-y", str(test_file)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, stderr=subprocess.DEVNULL)
        if result.returncode == 0:
            print(f"✓ Test tone generated: {test_file}")
            return str(test_file)
    
    # Try using Python to generate a simple WAV
    print("Using Python to generate test tone...")
    try:
        import wave
        import numpy as np
        
        sample_rate = 44100
        duration = 2  # seconds
        frequency = 440  # A4 note
        
        t = np.linspace(0, duration, int(sample_rate * duration), False)
        wave_data = np.sin(2 * np.pi * frequency * t)
        wave_data = (wave_data * 32767).astype(np.int16)
        
        with wave.open(str(test_file), 'w') as wf:
            wf.setnchannels(1)  # Mono
            wf.setsampwidth(2)  # 2 bytes per sample
            wf.setframerate(sample_rate)
            wf.writeframes(wave_data.tobytes())
        
        print(f"✓ Test tone generated: {test_file}")
        return str(test_file)
    except ImportError:
        print("✗ numpy not available for generating test tone")
    
    print("✗ Could not generate test tone")
    return None


def test_playback(filepath):
    """Test playing an audio file."""
    print("\n" + "=" * 50)
    print("Test 4: Testing Audio Playback")
    print("=" * 50)
    
    if not filepath or not Path(filepath).exists():
        print("✗ Test file not found")
        return False
    
    print(f"Attempting to play: {filepath}")
    
    # Try mpv first
    if subprocess.run(["which", "mpv"], capture_output=True).returncode == 0:
        print("\nTrying mpv...")
        cmd = ["mpv", "--no-video", "--volume=100", filepath]
        print(f"Command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            print("✓ mpv playback successful")
            return True
        else:
            print(f"✗ mpv failed: {result.stderr}")
    
    # Try aplay for WAV files
    if filepath.endswith('.wav'):
        print("\nTrying aplay...")
        cmd = ["aplay", filepath]
        print(f"Command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            print("✓ aplay playback successful")
            return True
        else:
            print(f"✗ aplay failed: {result.stderr}")
    
    # Try speaker-test
    print("\nTrying speaker-test (system beep)...")
    cmd = ["speaker-test", "-t", "sine", "-f", "440", "-l", "1", "-c", "2"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
    if result.returncode == 0:
        print("✓ speaker-test successful")
        return True
    else:
        print(f"✗ speaker-test failed")
    
    return False


def test_api():
    """Test the audio player API."""
    print("\n" + "=" * 50)
    print("Test 5: Testing Audio Player API")
    print("=" * 50)
    
    import requests
    
    try:
        # Check if server is running
        response = requests.get("http://localhost:5000/status", timeout=2)
        if response.status_code == 200:
            print("✓ API server is running")
            print(f"  Status: {response.json()}")
            return True
        else:
            print(f"✗ API returned status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("✗ API server not running")
        print("  Start with: python3 ~/raspberry_pi/audio_player/server.py")
        return False
    except Exception as e:
        print(f"✗ API test failed: {e}")
        return False


def main():
    """Run all tests."""
    print("\n" + "=" * 50)
    print("Raspberry Pi Audio System Tests")
    print("=" * 50 + "\n")
    
    results = {
        "devices": test_audio_devices(),
        "mpv": test_mpv(),
        "api": test_api(),
    }
    
    test_file = generate_test_tone()
    if test_file:
        results["playback"] = test_playback(test_file)
    else:
        results["playback"] = False
    
    # Summary
    print("\n" + "=" * 50)
    print("Test Summary")
    print("=" * 50)
    for test, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{test:15} {status}")
    
    # Recommendations
    print("\n" + "=" * 50)
    print("Recommendations")
    print("=" * 50)
    
    if not results.get("devices"):
        print("• Check audio hardware connections")
        print("• Run: sudo raspi-config → Advanced → Audio")
        print("• Try: sudo modprobe snd_bcm2835")
    
    if not results.get("mpv"):
        print("• Install mpv: sudo apt install mpv")
    
    if not results.get("playback"):
        print("• Check volume: alsamixer")
        print("• Test with: speaker-test -t sine -f 440 -l 1")
        print("• Check if audio output is muted")
    
    if not results.get("api"):
        print("• Start API server: python3 ~/raspberry_pi/audio_player/server.py")
    
    return all(results.values())


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
