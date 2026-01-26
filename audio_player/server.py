#!/usr/bin/env python3
"""
Audio Player Server for Raspberry Pi
Simple REST API to play audio files on demand.
"""

import os
import subprocess
import signal
from pathlib import Path
from flask import Flask, jsonify, request

app = Flask(__name__)

# Configuration
AUDIO_DIR = Path(os.environ.get("AUDIO_DIR", "/home/akash/raspberry_pi/audio_files"))
CURRENT_PROCESS = None


def get_audio_files():
    """List all audio files in the audio directory."""
    if not AUDIO_DIR.exists():
        return []
    
    extensions = {'.mp3', '.wav', '.ogg', '.flac', '.m4a', '.aac'}
    files = []
    for f in AUDIO_DIR.iterdir():
        if f.suffix.lower() in extensions:
            files.append(f.name)
    return sorted(files)


def stop_current():
    """Stop any currently playing audio."""
    global CURRENT_PROCESS
    if CURRENT_PROCESS and CURRENT_PROCESS.poll() is None:
        CURRENT_PROCESS.terminate()
        try:
            CURRENT_PROCESS.wait(timeout=2)
        except subprocess.TimeoutExpired:
            CURRENT_PROCESS.kill()
        CURRENT_PROCESS = None
        return True
    return False


def play_audio(filename, volume=100):
    """Play an audio file using mpv (lightweight, works headless)."""
    global CURRENT_PROCESS
    
    filepath = AUDIO_DIR / filename
    if not filepath.exists():
        return False, f"File not found: {filename}"
    
    # Stop any current playback
    stop_current()
    
    # Play with mpv (works great on Pi, no GUI needed)
    try:
        CURRENT_PROCESS = subprocess.Popen(
            ["mpv", "--no-video", f"--volume={volume}", str(filepath)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return True, f"Playing: {filename}"
    except FileNotFoundError:
        # Fallback to aplay for wav files
        if filepath.suffix.lower() == '.wav':
            CURRENT_PROCESS = subprocess.Popen(
                ["aplay", str(filepath)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            return True, f"Playing: {filename}"
        return False, "mpv not installed. Run: sudo apt install mpv"


# =============================================================================
# API Routes
# =============================================================================

@app.route('/')
def index():
    """API documentation."""
    return jsonify({
        "name": "Raspberry Pi Audio Player",
        "endpoints": {
            "GET /": "This documentation",
            "GET /files": "List available audio files",
            "POST /play": "Play a file. Body: {\"file\": \"name.mp3\", \"volume\": 100}",
            "POST /stop": "Stop current playback",
            "GET /status": "Current playback status"
        }
    })


@app.route('/files')
def list_files():
    """List all available audio files."""
    files = get_audio_files()
    return jsonify({
        "audio_directory": str(AUDIO_DIR),
        "files": files,
        "count": len(files)
    })


@app.route('/play', methods=['POST'])
def play():
    """Play an audio file."""
    data = request.get_json() or {}
    filename = data.get('file') or request.args.get('file')
    volume = data.get('volume', 100)
    
    if not filename:
        return jsonify({"error": "Missing 'file' parameter"}), 400
    
    success, message = play_audio(filename, volume)
    
    if success:
        return jsonify({"status": "playing", "message": message})
    else:
        return jsonify({"status": "error", "message": message}), 400


@app.route('/play/<filename>', methods=['GET', 'POST'])
def play_direct(filename):
    """Play a file directly via URL."""
    volume = request.args.get('volume', 100, type=int)
    success, message = play_audio(filename, volume)
    
    if success:
        return jsonify({"status": "playing", "message": message})
    else:
        return jsonify({"status": "error", "message": message}), 400


@app.route('/stop', methods=['POST', 'GET'])
def stop():
    """Stop current playback."""
    was_playing = stop_current()
    return jsonify({
        "status": "stopped",
        "was_playing": was_playing
    })


@app.route('/status')
def status():
    """Get current playback status."""
    global CURRENT_PROCESS
    is_playing = CURRENT_PROCESS is not None and CURRENT_PROCESS.poll() is None
    return jsonify({
        "is_playing": is_playing,
        "audio_directory": str(AUDIO_DIR),
        "available_files": len(get_audio_files())
    })


if __name__ == '__main__':
    # Ensure audio directory exists
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    
    print(f"Audio Player Server")
    print(f"Audio directory: {AUDIO_DIR}")
    print(f"Starting on http://0.0.0.0:5000")
    
    app.run(host='0.0.0.0', port=5000, debug=False)
