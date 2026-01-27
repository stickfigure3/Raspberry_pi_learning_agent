#!/usr/bin/env python3
"""
Enhanced Audio Player Server for Raspberry Pi
Upload files, schedule playback, and control audio remotely.
"""

import os
import subprocess
import signal
import json
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory, render_template_string
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Configuration
AUDIO_DIR = Path(os.environ.get("AUDIO_DIR", "/home/akash/raspberry_pi/audio_files"))
SCHEDULE_FILE = Path.home() / ".audio_pi" / "schedule.json"
CURRENT_PROCESS = None
CURRENT_FILE = None
PLAYBACK_LOCK = threading.Lock()

# Allowed audio extensions
ALLOWED_EXTENSIONS = {'.mp3', '.wav', '.ogg', '.flac', '.m4a', '.aac'}

# Queue for scheduled playback
playback_queue = []
schedule_thread = None
schedule_running = False


def get_audio_files():
    """List all audio files in the audio directory."""
    if not AUDIO_DIR.exists():
        return []
    
    files = []
    for f in AUDIO_DIR.iterdir():
        if f.is_file() and f.suffix.lower() in ALLOWED_EXTENSIONS:
            size = f.stat().st_size
            files.append({
                "name": f.name,
                "size": size,
                "size_mb": round(size / (1024 * 1024), 2)
            })
    return sorted(files, key=lambda x: x["name"])


def load_schedule():
    """Load scheduled playback items."""
    global playback_queue
    if SCHEDULE_FILE.exists():
        try:
            with open(SCHEDULE_FILE, 'r') as f:
                playback_queue = json.load(f)
        except:
            playback_queue = []
    else:
        playback_queue = []


def save_schedule():
    """Save scheduled playback items."""
    SCHEDULE_FILE.parent.mkdir(exist_ok=True)
    with open(SCHEDULE_FILE, 'w') as f:
        json.dump(playback_queue, f, indent=2)


def stop_current():
    """Stop any currently playing audio."""
    global CURRENT_PROCESS, CURRENT_FILE
    with PLAYBACK_LOCK:
        if CURRENT_PROCESS and CURRENT_PROCESS.poll() is None:
            CURRENT_PROCESS.terminate()
            try:
                CURRENT_PROCESS.wait(timeout=2)
            except subprocess.TimeoutExpired:
                CURRENT_PROCESS.kill()
            CURRENT_PROCESS = None
            CURRENT_FILE = None
            return True
    return False


def play_audio(filename, volume=100):
    """Play an audio file using mpv."""
    global CURRENT_PROCESS, CURRENT_FILE
    
    filepath = AUDIO_DIR / filename
    if not filepath.exists():
        return False, f"File not found: {filename}"
    
    # Stop any current playback
    stop_current()
    
    with PLAYBACK_LOCK:
        try:
            # Force headphone output (card 2, device 0)
            # This ensures audio goes to the 3.5mm jack
            cmd = [
                "mpv", 
                "--no-video", 
                f"--volume={volume}",
                "--audio-device=alsa/plughw:2,0",  # Force headphone output
                "--really-quiet",  # Suppress output
                str(filepath)
            ]
            CURRENT_PROCESS = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            CURRENT_FILE = filename
            return True, f"Playing: {filename}"
        except FileNotFoundError:
            if filepath.suffix.lower() == '.wav':
                # Try aplay with specific device
                CURRENT_PROCESS = subprocess.Popen(
                    ["aplay", "-D", "plughw:2,0", str(filepath)],  # Headphones device
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                CURRENT_FILE = filename
                return True, f"Playing: {filename}"
            return False, "mpv not installed. Run: sudo apt install mpv"


def schedule_worker():
    """Background thread that checks and plays scheduled items."""
    global schedule_running, playback_queue
    
    while schedule_running:
        try:
            now = datetime.now()
            to_remove = []
            
            for i, item in enumerate(playback_queue):
                if item.get('status') == 'pending':
                    play_time = datetime.fromisoformat(item['play_at'])
                    
                    if now >= play_time:
                        # Time to play!
                        filename = item['filename']
                        volume = item.get('volume', 100)
                        play_audio(filename, volume)
                        item['status'] = 'played'
                        item['played_at'] = now.isoformat()
                        save_schedule()
            
            # Remove old played items (older than 1 day)
            playback_queue = [
                item for item in playback_queue
                if item.get('status') != 'played' or 
                (datetime.now() - datetime.fromisoformat(item.get('played_at', '2000-01-01'))).days < 1
            ]
            save_schedule()
            
        except Exception as e:
            print(f"Schedule worker error: {e}")
        
        time.sleep(1)  # Check every second


def start_schedule_worker():
    """Start the schedule monitoring thread."""
    global schedule_thread, schedule_running
    
    if not schedule_running:
        schedule_running = True
        schedule_thread = threading.Thread(target=schedule_worker, daemon=True)
        schedule_thread.start()


# Load schedule on startup
load_schedule()
start_schedule_worker()


# =============================================================================
# Web UI
# =============================================================================

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Raspberry Pi Audio Player</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 12px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            overflow: hidden;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }
        .header h1 { font-size: 2em; margin-bottom: 10px; }
        .content { padding: 30px; }
        .section { margin-bottom: 40px; }
        .section h2 {
            color: #333;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid #667eea;
        }
        .upload-area {
            border: 3px dashed #667eea;
            border-radius: 8px;
            padding: 40px;
            text-align: center;
            background: #f8f9fa;
            cursor: pointer;
            transition: all 0.3s;
        }
        .upload-area:hover { background: #e9ecef; border-color: #764ba2; }
        .upload-area.dragover { background: #e7f3ff; border-color: #667eea; }
        input[type="file"] { display: none; }
        .btn {
            background: #667eea;
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 16px;
            transition: all 0.3s;
            margin: 5px;
        }
        .btn:hover { background: #764ba2; transform: translateY(-2px); }
        .btn-danger { background: #dc3545; }
        .btn-danger:hover { background: #c82333; }
        .file-list {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 15px;
            margin-top: 20px;
        }
        .file-card {
            background: #f8f9fa;
            border-radius: 8px;
            padding: 15px;
            border: 2px solid transparent;
            transition: all 0.3s;
        }
        .file-card:hover { border-color: #667eea; transform: translateY(-2px); }
        .file-card.selected { border-color: #667eea; background: #e7f3ff; }
        .file-name {
            font-weight: bold;
            margin-bottom: 5px;
            word-break: break-word;
        }
        .file-size { color: #666; font-size: 0.9em; }
        .schedule-form {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            margin-top: 20px;
        }
        .form-group {
            margin-bottom: 15px;
        }
        .form-group label {
            display: block;
            margin-bottom: 5px;
            color: #333;
            font-weight: 500;
        }
        .form-group input {
            width: 100%;
            padding: 10px;
            border: 2px solid #ddd;
            border-radius: 6px;
            font-size: 16px;
        }
        .form-group input:focus {
            outline: none;
            border-color: #667eea;
        }
        .schedule-list {
            margin-top: 20px;
        }
        .schedule-item {
            background: white;
            border: 2px solid #ddd;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 10px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .schedule-item.pending { border-left: 4px solid #ffc107; }
        .schedule-item.played { border-left: 4px solid #28a745; opacity: 0.7; }
        .status {
            padding: 5px 10px;
            border-radius: 4px;
            font-size: 0.9em;
            font-weight: bold;
        }
        .status.pending { background: #fff3cd; color: #856404; }
        .status.playing { background: #d4edda; color: #155724; }
        .status.played { background: #e2e3e5; color: #383d41; }
        .now-playing {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            text-align: center;
        }
        .now-playing h3 { margin-bottom: 10px; }
        .alert {
            padding: 15px;
            border-radius: 6px;
            margin-bottom: 20px;
        }
        .alert-success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .alert-error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎵 Raspberry Pi Audio Player</h1>
            <p>Upload files and schedule playback</p>
        </div>
        <div class="content">
            <div id="alert-container"></div>
            
            <div class="section">
                <h2>📤 Upload Audio Files</h2>
                <div class="upload-area" onclick="document.getElementById('file-input').click()">
                    <p>📁 Click or drag files here to upload</p>
                    <p style="color: #666; margin-top: 10px;">Supports: MP3, WAV, OGG, FLAC, M4A, AAC</p>
                </div>
                <input type="file" id="file-input" multiple accept="audio/*" onchange="handleFiles(event)">
            </div>
            
            <div class="section">
                <h2>📋 Available Files</h2>
                <div id="file-list" class="file-list"></div>
            </div>
            
            <div class="section">
                <h2>⏰ Schedule Playback</h2>
                <div class="schedule-form">
                    <div class="form-group">
                        <label>Select File:</label>
                        <select id="schedule-file" style="width: 100%; padding: 10px; border: 2px solid #ddd; border-radius: 6px;">
                            <option value="">-- Select a file --</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Play At (Date & Time):</label>
                        <input type="datetime-local" id="schedule-time">
                    </div>
                    <div class="form-group">
                        <label>Volume (0-100):</label>
                        <input type="number" id="schedule-volume" value="100" min="0" max="100">
                    </div>
                    <button class="btn" onclick="schedulePlayback()">Schedule Playback</button>
                </div>
                <div class="schedule-list" id="schedule-list"></div>
            </div>
        </div>
    </div>
    
    <script>
        let selectedFiles = [];
        
        function showAlert(message, type = 'success') {
            const container = document.getElementById('alert-container');
            container.innerHTML = `<div class="alert alert-${type}">${message}</div>`;
            setTimeout(() => container.innerHTML = '', 5000);
        }
        
        function handleFiles(event) {
            const files = Array.from(event.target.files);
            uploadFiles(files);
        }
        
        async function uploadFiles(files) {
            const formData = new FormData();
            files.forEach(file => formData.append('files', file));
            
            try {
                const response = await fetch('/upload', {
                    method: 'POST',
                    body: formData
                });
                const data = await response.json();
                if (response.ok) {
                    showAlert(`Uploaded ${data.uploaded} file(s) successfully!`, 'success');
                    loadFiles();
                } else {
                    showAlert(data.error || 'Upload failed', 'error');
                }
            } catch (error) {
                showAlert('Upload failed: ' + error.message, 'error');
            }
        }
        
        async function loadFiles() {
            const response = await fetch('/files');
            const data = await response.json();
            const fileList = document.getElementById('file-list');
            const scheduleSelect = document.getElementById('schedule-file');
            
            fileList.innerHTML = '';
            scheduleSelect.innerHTML = '<option value="">-- Select a file --</option>';
            
            data.files.forEach(file => {
                const card = document.createElement('div');
                card.className = 'file-card';
                card.innerHTML = `
                    <div class="file-name">${file.name}</div>
                    <div class="file-size">${file.size_mb} MB</div>
                    <button class="btn" onclick="playNow('${file.name}')" style="width: 100%; margin-top: 10px;">Play Now</button>
                `;
                fileList.appendChild(card);
                
                const option = document.createElement('option');
                option.value = file.name;
                option.textContent = file.name;
                scheduleSelect.appendChild(option);
            });
        }
        
        async function playNow(filename) {
            try {
                const response = await fetch('/play', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({file: filename})
                });
                const data = await response.json();
                if (response.ok) {
                    showAlert(data.message || 'Playing...', 'success');
                } else {
                    showAlert(data.message || 'Playback failed', 'error');
                }
            } catch (error) {
                showAlert('Error: ' + error.message, 'error');
            }
        }
        
        async function schedulePlayback() {
            const filename = document.getElementById('schedule-file').value;
            const playTime = document.getElementById('schedule-time').value;
            const volume = parseInt(document.getElementById('schedule-volume').value);
            
            if (!filename || !playTime) {
                showAlert('Please select a file and time', 'error');
                return;
            }
            
            try {
                const response = await fetch('/schedule', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({filename, play_at: playTime, volume})
                });
                const data = await response.json();
                if (response.ok) {
                    showAlert('Scheduled successfully!', 'success');
                    loadSchedule();
                } else {
                    showAlert(data.error || 'Scheduling failed', 'error');
                }
            } catch (error) {
                showAlert('Error: ' + error.message, 'error');
            }
        }
        
        async function loadSchedule() {
            const response = await fetch('/schedule');
            const data = await response.json();
            const scheduleList = document.getElementById('schedule-list');
            
            scheduleList.innerHTML = '';
            data.schedule.forEach((item, index) => {
                const div = document.createElement('div');
                div.className = `schedule-item ${item.status}`;
                const playAt = new Date(item.play_at).toLocaleString();
                div.innerHTML = `
                    <div>
                        <strong>${item.filename}</strong><br>
                        <small>Play at: ${playAt}</small>
                    </div>
                    <div>
                        <span class="status ${item.status}">${item.status}</span>
                        ${item.status === 'pending' ? `<button class="btn btn-danger" onclick="cancelSchedule(${index})">Cancel</button>` : ''}
                    </div>
                `;
                scheduleList.appendChild(div);
            });
        }
        
        async function cancelSchedule(index) {
            try {
                const response = await fetch(`/schedule/${index}`, {method: 'DELETE'});
                if (response.ok) {
                    showAlert('Schedule cancelled', 'success');
                    loadSchedule();
                }
            } catch (error) {
                showAlert('Error: ' + error.message, 'error');
            }
        }
        
        async function updateStatus() {
            const response = await fetch('/status');
            const data = await response.json();
            // Could show currently playing here
        }
        
        // Drag and drop
        const uploadArea = document.querySelector('.upload-area');
        uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadArea.classList.add('dragover');
        });
        uploadArea.addEventListener('dragleave', () => {
            uploadArea.classList.remove('dragover');
        });
        uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadArea.classList.remove('dragover');
            const files = Array.from(e.dataTransfer.files);
            uploadFiles(files);
        });
        
        // Load on page load
        loadFiles();
        loadSchedule();
        setInterval(() => { loadSchedule(); updateStatus(); }, 5000);
    </script>
</body>
</html>
"""


# =============================================================================
# API Routes
# =============================================================================

@app.route('/')
def index():
    """Serve the web UI."""
    return render_template_string(HTML_TEMPLATE)


@app.route('/files')
def list_files():
    """List all available audio files."""
    files = get_audio_files()
    return jsonify({
        "audio_directory": str(AUDIO_DIR),
        "files": files,
        "count": len(files)
    })


@app.route('/upload', methods=['POST'])
def upload():
    """Upload audio files."""
    if 'files' not in request.files:
        return jsonify({"error": "No files provided"}), 400
    
    files = request.files.getlist('files')
    uploaded = 0
    
    for file in files:
        if file.filename == '':
            continue
        
        filename = secure_filename(file.filename)
        if not any(filename.lower().endswith(ext) for ext in ALLOWED_EXTENSIONS):
            continue
        
        filepath = AUDIO_DIR / filename
        file.save(str(filepath))
        uploaded += 1
    
    return jsonify({
        "status": "success",
        "uploaded": uploaded,
        "message": f"Uploaded {uploaded} file(s)"
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
    global CURRENT_PROCESS, CURRENT_FILE
    is_playing = CURRENT_PROCESS is not None and CURRENT_PROCESS.poll() is None
    return jsonify({
        "is_playing": is_playing,
        "current_file": CURRENT_FILE,
        "audio_directory": str(AUDIO_DIR),
        "available_files": len(get_audio_files())
    })


@app.route('/schedule', methods=['GET'])
def get_schedule():
    """Get scheduled playback items."""
    return jsonify({
        "schedule": playback_queue,
        "count": len(playback_queue)
    })


@app.route('/schedule', methods=['POST'])
def add_schedule():
    """Schedule a file for playback."""
    data = request.get_json() or {}
    filename = data.get('filename')
    play_at = data.get('play_at')
    volume = data.get('volume', 100)
    
    if not filename or not play_at:
        return jsonify({"error": "Missing 'filename' or 'play_at' parameter"}), 400
    
    # Validate file exists
    filepath = AUDIO_DIR / filename
    if not filepath.exists():
        return jsonify({"error": "File not found"}), 404
    
    # Parse datetime
    try:
        play_time = datetime.fromisoformat(play_at.replace('Z', '+00:00'))
        if play_time < datetime.now():
            return jsonify({"error": "Play time must be in the future"}), 400
    except:
        return jsonify({"error": "Invalid datetime format"}), 400
    
    item = {
        "filename": filename,
        "play_at": play_time.isoformat(),
        "volume": volume,
        "status": "pending",
        "created_at": datetime.now().isoformat()
    }
    
    playback_queue.append(item)
    save_schedule()
    
    return jsonify({
        "status": "scheduled",
        "item": item,
        "message": f"Scheduled {filename} for {play_time.strftime('%Y-%m-%d %H:%M:%S')}"
    })


@app.route('/schedule/<int:index>', methods=['DELETE'])
def cancel_schedule(index):
    """Cancel a scheduled item."""
    if 0 <= index < len(playback_queue):
        item = playback_queue.pop(index)
        save_schedule()
        return jsonify({
            "status": "cancelled",
            "item": item
        })
    return jsonify({"error": "Invalid index"}), 404


if __name__ == '__main__':
    # Ensure audio directory exists
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    
    print(f"Enhanced Audio Player Server")
    print(f"Audio directory: {AUDIO_DIR}")
    print(f"Starting on http://0.0.0.0:5000")
    print(f"Web UI available at http://0.0.0.0:5000")
    
    app.run(host='0.0.0.0', port=5000, debug=False)
