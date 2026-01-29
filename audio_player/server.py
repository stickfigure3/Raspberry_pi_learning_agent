#!/usr/bin/env python3
"""
Raspberry Pi Control Panel
A web interface for controlling audio playback and Pi management.
"""

import os
import subprocess
import signal
import json
import threading
import time
from datetime import datetime
from pathlib import Path
from flask import Flask, jsonify, request, render_template_string

app = Flask(__name__)

# Configuration
AUDIO_DIR = Path(os.environ.get("AUDIO_DIR", "/home/akash/raspberry_pi/audio_files"))
COMMAND_QUEUE_FILE = Path("/home/akash/raspberry_pi/logs/command_queue.json")
AUDIO_DEVICE = "alsa/plughw:2,0"

# State
CURRENT_PROCESS = None
CURRENT_FILE = None
CURRENT_VOLUME = 50

# Ensure directories exist
COMMAND_QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)


def get_audio_files():
    """Get list of audio files."""
    if not AUDIO_DIR.exists():
        return []
    
    extensions = {'.mp3', '.wav', '.ogg', '.flac', '.m4a', '.aac', '.opus'}
    files = []
    for f in sorted(AUDIO_DIR.iterdir()):
        if f.is_file() and f.suffix.lower() in extensions:
            files.append({
                'name': f.name,
                'size': f.stat().st_size,
                'size_mb': round(f.stat().st_size / (1024 * 1024), 1)
            })
    return files


def stop_current():
    """Stop currently playing audio."""
    global CURRENT_PROCESS, CURRENT_FILE
    if CURRENT_PROCESS:
        try:
            CURRENT_PROCESS.terminate()
            CURRENT_PROCESS.wait(timeout=2)
        except:
            try:
                CURRENT_PROCESS.kill()
            except:
                pass
    CURRENT_PROCESS = None
    CURRENT_FILE = None
    # Also kill any orphaned mpv processes
    subprocess.run(["pkill", "-9", "mpv"], capture_output=True)


def play_audio(filename, volume=50):
    """Play an audio file."""
    global CURRENT_PROCESS, CURRENT_FILE, CURRENT_VOLUME
    
    filepath = AUDIO_DIR / filename
    if not filepath.exists():
        return False, f"File not found: {filename}"
    
    stop_current()
    CURRENT_VOLUME = volume
    
    try:
        cmd = [
            "mpv", "--no-video",
            f"--volume={volume}",
            f"--audio-device={AUDIO_DEVICE}",
            "--really-quiet",
            str(filepath)
        ]
        CURRENT_PROCESS = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        CURRENT_FILE = filename
        return True, f"Playing: {filename}"
    except Exception as e:
        return False, str(e)


def set_volume(volume):
    """Change volume of current playback."""
    global CURRENT_VOLUME, CURRENT_PROCESS, CURRENT_FILE
    CURRENT_VOLUME = max(0, min(150, volume))
    
    if CURRENT_FILE:
        # Restart with new volume
        play_audio(CURRENT_FILE, CURRENT_VOLUME)
        return True
    return False


def load_command_queue():
    """Load pending commands from file."""
    if COMMAND_QUEUE_FILE.exists():
        try:
            with open(COMMAND_QUEUE_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return []


def save_command_queue(queue):
    """Save command queue to file."""
    with open(COMMAND_QUEUE_FILE, 'w') as f:
        json.dump(queue, f, indent=2)


def execute_command(cmd):
    """Execute a queued command."""
    action = cmd.get('action')
    
    if action == 'play':
        success, msg = play_audio(cmd.get('file', ''), cmd.get('volume', 50))
        return {'success': success, 'message': msg}
    
    elif action == 'stop':
        stop_current()
        return {'success': True, 'message': 'Stopped'}
    
    elif action == 'volume':
        set_volume(cmd.get('volume', 50))
        return {'success': True, 'message': f'Volume set to {CURRENT_VOLUME}%'}
    
    elif action == 'shutdown':
        subprocess.Popen(['sudo', 'shutdown', 'now'])
        return {'success': True, 'message': 'Shutting down...'}
    
    elif action == 'reboot':
        subprocess.Popen(['sudo', 'reboot'])
        return {'success': True, 'message': 'Rebooting...'}
    
    return {'success': False, 'message': 'Unknown action'}


# HTML Template with modern responsive design
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
    <title>Pi Control</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Outfit:wght@300;400;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-dark: #0a0a0f;
            --bg-card: #12121a;
            --bg-hover: #1a1a25;
            --accent: #00ff88;
            --accent-dim: #00cc6a;
            --accent-glow: rgba(0, 255, 136, 0.15);
            --text: #e8e8e8;
            --text-dim: #888;
            --danger: #ff4757;
            --warning: #ffa502;
        }
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Outfit', sans-serif;
            background: var(--bg-dark);
            color: var(--text);
            min-height: 100vh;
            padding: 20px;
            padding-bottom: 100px;
        }
        
        .container {
            max-width: 600px;
            margin: 0 auto;
        }
        
        header {
            text-align: center;
            margin-bottom: 30px;
            padding: 20px;
        }
        
        h1 {
            font-family: 'Space Mono', monospace;
            font-size: 1.8rem;
            color: var(--accent);
            text-shadow: 0 0 30px var(--accent-glow);
            margin-bottom: 5px;
        }
        
        .status-indicator {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            font-size: 0.85rem;
            color: var(--text-dim);
        }
        
        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--accent);
            animation: pulse 2s infinite;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.4; }
        }
        
        .card {
            background: var(--bg-card);
            border-radius: 16px;
            padding: 20px;
            margin-bottom: 20px;
            border: 1px solid rgba(255,255,255,0.05);
        }
        
        .card-title {
            font-family: 'Space Mono', monospace;
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 2px;
            color: var(--text-dim);
            margin-bottom: 15px;
        }
        
        /* Now Playing */
        .now-playing {
            background: linear-gradient(135deg, var(--bg-card) 0%, #1a1a2e 100%);
            border: 1px solid var(--accent-dim);
            box-shadow: 0 0 40px var(--accent-glow);
        }
        
        .now-playing-info {
            display: flex;
            align-items: center;
            gap: 15px;
            margin-bottom: 20px;
        }
        
        .music-icon {
            width: 60px;
            height: 60px;
            background: var(--accent-glow);
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.5rem;
        }
        
        .track-info h2 {
            font-size: 1.1rem;
            font-weight: 600;
            margin-bottom: 4px;
            word-break: break-word;
        }
        
        .track-info p {
            font-size: 0.85rem;
            color: var(--text-dim);
        }
        
        /* Volume Control */
        .volume-control {
            margin: 20px 0;
        }
        
        .volume-label {
            display: flex;
            justify-content: space-between;
            margin-bottom: 10px;
            font-size: 0.9rem;
        }
        
        .volume-slider {
            width: 100%;
            height: 8px;
            -webkit-appearance: none;
            background: rgba(255,255,255,0.1);
            border-radius: 4px;
            outline: none;
        }
        
        .volume-slider::-webkit-slider-thumb {
            -webkit-appearance: none;
            width: 24px;
            height: 24px;
            background: var(--accent);
            border-radius: 50%;
            cursor: pointer;
            box-shadow: 0 0 10px var(--accent);
        }
        
        /* Playback Controls */
        .controls {
            display: flex;
            justify-content: center;
            gap: 15px;
            margin-top: 20px;
        }
        
        .control-btn {
            width: 60px;
            height: 60px;
            border: none;
            border-radius: 50%;
            font-size: 1.5rem;
            cursor: pointer;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .control-btn.play {
            background: var(--accent);
            color: var(--bg-dark);
        }
        
        .control-btn.stop {
            background: rgba(255,255,255,0.1);
            color: var(--text);
        }
        
        .control-btn:hover {
            transform: scale(1.1);
        }
        
        .control-btn:active {
            transform: scale(0.95);
        }
        
        /* Song List */
        .song-list {
            max-height: 300px;
            overflow-y: auto;
        }
        
        .song-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px 15px;
            border-radius: 10px;
            cursor: pointer;
            transition: background 0.2s;
            margin-bottom: 5px;
        }
        
        .song-item:hover {
            background: var(--bg-hover);
        }
        
        .song-item.active {
            background: var(--accent-glow);
            border-left: 3px solid var(--accent);
        }
        
        .song-name {
            font-size: 0.95rem;
            flex: 1;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            margin-right: 10px;
        }
        
        .song-size {
            font-size: 0.8rem;
            color: var(--text-dim);
            white-space: nowrap;
        }
        
        /* Command Queue */
        .queue-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px;
            background: rgba(255,255,255,0.03);
            border-radius: 8px;
            margin-bottom: 8px;
        }
        
        .queue-item .action {
            font-family: 'Space Mono', monospace;
            font-size: 0.85rem;
            color: var(--accent);
        }
        
        .queue-item .details {
            font-size: 0.8rem;
            color: var(--text-dim);
            flex: 1;
            margin: 0 10px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        
        .queue-item .remove-btn {
            background: none;
            border: none;
            color: var(--danger);
            cursor: pointer;
            padding: 5px;
            font-size: 1.2rem;
        }
        
        .empty-queue {
            text-align: center;
            color: var(--text-dim);
            padding: 20px;
            font-size: 0.9rem;
        }
        
        /* System Controls */
        .system-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 10px;
        }
        
        .system-btn {
            padding: 15px;
            border: none;
            border-radius: 12px;
            font-family: 'Outfit', sans-serif;
            font-size: 0.9rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 8px;
        }
        
        .system-btn .icon {
            font-size: 1.5rem;
        }
        
        .system-btn.primary {
            background: var(--accent);
            color: var(--bg-dark);
        }
        
        .system-btn.secondary {
            background: rgba(255,255,255,0.1);
            color: var(--text);
        }
        
        .system-btn.danger {
            background: rgba(255,71,87,0.2);
            color: var(--danger);
        }
        
        .system-btn:hover {
            transform: translateY(-2px);
        }
        
        .system-btn:active {
            transform: translateY(0);
        }
        
        /* Toast Notifications */
        .toast-container {
            position: fixed;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            z-index: 1000;
        }
        
        .toast {
            background: var(--bg-card);
            border: 1px solid var(--accent);
            border-radius: 10px;
            padding: 12px 20px;
            margin-top: 10px;
            animation: slideUp 0.3s ease;
            box-shadow: 0 5px 20px rgba(0,0,0,0.5);
        }
        
        .toast.error {
            border-color: var(--danger);
        }
        
        @keyframes slideUp {
            from {
                opacity: 0;
                transform: translateY(20px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        /* Loading */
        .loading {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 2px solid rgba(255,255,255,0.3);
            border-radius: 50%;
            border-top-color: var(--accent);
            animation: spin 1s linear infinite;
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        
        /* Responsive */
        @media (max-width: 480px) {
            body {
                padding: 15px;
            }
            
            h1 {
                font-size: 1.5rem;
            }
            
            .card {
                padding: 15px;
            }
            
            .control-btn {
                width: 50px;
                height: 50px;
                font-size: 1.2rem;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🍓 Pi Control</h1>
            <div class="status-indicator">
                <span class="status-dot"></span>
                <span id="connection-status">Connected</span>
            </div>
        </header>
        
        <!-- Now Playing -->
        <div class="card now-playing">
            <div class="card-title">Now Playing</div>
            <div class="now-playing-info">
                <div class="music-icon">🎵</div>
                <div class="track-info">
                    <h2 id="current-track">Nothing playing</h2>
                    <p id="current-status">Select a song below</p>
                </div>
            </div>
            
            <div class="volume-control">
                <div class="volume-label">
                    <span>🔊 Volume</span>
                    <span id="volume-display">50%</span>
                </div>
                <input type="range" class="volume-slider" id="volume-slider" min="0" max="150" value="50">
            </div>
            
            <div class="controls">
                <button class="control-btn stop" onclick="stopAudio()" title="Stop">⏹</button>
                <button class="control-btn play" onclick="playSelected()" title="Play">▶</button>
            </div>
        </div>
        
        <!-- Song Library -->
        <div class="card">
            <div class="card-title">🎧 Library</div>
            <div class="song-list" id="song-list">
                <div class="empty-queue">Loading songs...</div>
            </div>
        </div>
        
        <!-- Command Queue -->
        <div class="card">
            <div class="card-title">📋 Queued Commands</div>
            <div id="command-queue">
                <div class="empty-queue">No commands queued</div>
            </div>
            <button class="system-btn primary" style="width: 100%; margin-top: 15px;" onclick="executeQueue()">
                Execute All Commands
            </button>
        </div>
        
        <!-- System Controls -->
        <div class="card">
            <div class="card-title">⚙️ System</div>
            <div class="system-grid">
                <button class="system-btn secondary" onclick="queueCommand('git_pull')">
                    <span class="icon">📥</span>
                    Git Pull
                </button>
                <button class="system-btn secondary" onclick="refreshStatus()">
                    <span class="icon">🔄</span>
                    Refresh
                </button>
                <button class="system-btn danger" onclick="queueCommand('reboot')">
                    <span class="icon">🔁</span>
                    Reboot
                </button>
                <button class="system-btn danger" onclick="queueCommand('shutdown')">
                    <span class="icon">⏻</span>
                    Shutdown
                </button>
            </div>
        </div>
    </div>
    
    <div class="toast-container" id="toast-container"></div>
    
    <script>
        // State
        let songs = [];
        let selectedSong = null;
        let commandQueue = [];
        let currentVolume = 50;
        
        // Load saved state from localStorage
        function loadState() {
            const saved = localStorage.getItem('piControlQueue');
            if (saved) {
                commandQueue = JSON.parse(saved);
                renderQueue();
            }
            
            const savedVolume = localStorage.getItem('piControlVolume');
            if (savedVolume) {
                currentVolume = parseInt(savedVolume);
                document.getElementById('volume-slider').value = currentVolume;
                document.getElementById('volume-display').textContent = currentVolume + '%';
            }
        }
        
        // Save state to localStorage
        function saveState() {
            localStorage.setItem('piControlQueue', JSON.stringify(commandQueue));
            localStorage.setItem('piControlVolume', currentVolume.toString());
        }
        
        // Toast notification
        function showToast(message, isError = false) {
            const container = document.getElementById('toast-container');
            const toast = document.createElement('div');
            toast.className = 'toast' + (isError ? ' error' : '');
            toast.textContent = message;
            container.appendChild(toast);
            
            setTimeout(() => {
                toast.remove();
            }, 3000);
        }
        
        // Fetch songs
        async function fetchSongs() {
            try {
                const res = await fetch('/api/files');
                const data = await res.json();
                songs = data.files || [];
                renderSongs();
            } catch (e) {
                showToast('Failed to load songs', true);
            }
        }
        
        // Render song list
        function renderSongs() {
            const list = document.getElementById('song-list');
            if (songs.length === 0) {
                list.innerHTML = '<div class="empty-queue">No songs found</div>';
                return;
            }
            
            list.innerHTML = songs.map((song, i) => `
                <div class="song-item ${selectedSong === song.name ? 'active' : ''}" 
                     onclick="selectSong('${song.name.replace(/'/g, "\\'")}')">
                    <span class="song-name">${song.name}</span>
                    <span class="song-size">${song.size_mb} MB</span>
                </div>
            `).join('');
        }
        
        // Select song
        function selectSong(name) {
            selectedSong = name;
            renderSongs();
        }
        
        // Play selected song
        function playSelected() {
            if (!selectedSong) {
                showToast('Select a song first', true);
                return;
            }
            
            // Immediate play
            fetch('/api/play', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({file: selectedSong, volume: currentVolume})
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    document.getElementById('current-track').textContent = selectedSong;
                    document.getElementById('current-status').textContent = 'Playing';
                    showToast('Playing: ' + selectedSong);
                } else {
                    showToast(data.error || 'Failed to play', true);
                }
            })
            .catch(() => showToast('Connection error', true));
        }
        
        // Stop audio
        function stopAudio() {
            fetch('/api/stop', {method: 'POST'})
            .then(res => res.json())
            .then(data => {
                document.getElementById('current-track').textContent = 'Nothing playing';
                document.getElementById('current-status').textContent = 'Stopped';
                showToast('Stopped');
            })
            .catch(() => showToast('Connection error', true));
        }
        
        // Volume control
        document.getElementById('volume-slider').addEventListener('input', function(e) {
            currentVolume = parseInt(e.target.value);
            document.getElementById('volume-display').textContent = currentVolume + '%';
            saveState();
        });
        
        document.getElementById('volume-slider').addEventListener('change', function(e) {
            // Update volume on server
            fetch('/api/volume', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({volume: currentVolume})
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    showToast('Volume: ' + currentVolume + '%');
                }
            });
        });
        
        // Queue a command
        function queueCommand(action, details = {}) {
            const cmd = {
                id: Date.now(),
                action: action,
                details: details,
                timestamp: new Date().toISOString()
            };
            
            // Special handling for dangerous commands
            if (action === 'shutdown' || action === 'reboot') {
                if (!confirm(`Are you sure you want to ${action} the Pi?`)) {
                    return;
                }
            }
            
            commandQueue.push(cmd);
            saveState();
            renderQueue();
            showToast(`Queued: ${action}`);
        }
        
        // Remove command from queue
        function removeCommand(id) {
            commandQueue = commandQueue.filter(c => c.id !== id);
            saveState();
            renderQueue();
        }
        
        // Render command queue
        function renderQueue() {
            const container = document.getElementById('command-queue');
            
            if (commandQueue.length === 0) {
                container.innerHTML = '<div class="empty-queue">No commands queued</div>';
                return;
            }
            
            container.innerHTML = commandQueue.map(cmd => `
                <div class="queue-item">
                    <span class="action">${cmd.action}</span>
                    <span class="details">${JSON.stringify(cmd.details) || ''}</span>
                    <button class="remove-btn" onclick="removeCommand(${cmd.id})">×</button>
                </div>
            `).join('');
        }
        
        // Execute all queued commands
        async function executeQueue() {
            if (commandQueue.length === 0) {
                showToast('No commands to execute');
                return;
            }
            
            showToast('Executing commands...');
            
            for (const cmd of [...commandQueue]) {
                try {
                    const res = await fetch('/api/execute', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify(cmd)
                    });
                    const data = await res.json();
                    
                    if (data.success) {
                        removeCommand(cmd.id);
                        showToast(`Done: ${cmd.action}`);
                    } else {
                        showToast(`Failed: ${cmd.action}`, true);
                    }
                } catch (e) {
                    showToast(`Error: ${cmd.action}`, true);
                }
                
                // Small delay between commands
                await new Promise(r => setTimeout(r, 500));
            }
            
            refreshStatus();
        }
        
        // Refresh status
        async function refreshStatus() {
            try {
                const res = await fetch('/api/status');
                const data = await res.json();
                
                if (data.playing) {
                    document.getElementById('current-track').textContent = data.file || 'Unknown';
                    document.getElementById('current-status').textContent = 'Playing';
                } else {
                    document.getElementById('current-track').textContent = 'Nothing playing';
                    document.getElementById('current-status').textContent = 'Stopped';
                }
                
                if (data.volume !== undefined) {
                    currentVolume = data.volume;
                    document.getElementById('volume-slider').value = currentVolume;
                    document.getElementById('volume-display').textContent = currentVolume + '%';
                }
                
                showToast('Status refreshed');
            } catch (e) {
                showToast('Connection error', true);
            }
            
            fetchSongs();
        }
        
        // Initialize
        loadState();
        fetchSongs();
        refreshStatus();
        
        // Periodic refresh
        setInterval(refreshStatus, 30000);
    </script>
</body>
</html>
'''


# API Routes
@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/files')
def api_files():
    return jsonify({'files': get_audio_files()})


@app.route('/api/play', methods=['POST'])
def api_play():
    data = request.get_json() or {}
    filename = data.get('file', '')
    volume = data.get('volume', 50)
    
    if not filename:
        return jsonify({'success': False, 'error': 'No file specified'})
    
    success, msg = play_audio(filename, volume)
    return jsonify({'success': success, 'message': msg, 'error': None if success else msg})


@app.route('/api/stop', methods=['POST'])
def api_stop():
    stop_current()
    return jsonify({'success': True, 'message': 'Stopped'})


@app.route('/api/volume', methods=['POST'])
def api_volume():
    data = request.get_json() or {}
    volume = data.get('volume', 50)
    set_volume(volume)
    return jsonify({'success': True, 'volume': CURRENT_VOLUME})


@app.route('/api/status')
def api_status():
    return jsonify({
        'playing': CURRENT_PROCESS is not None and CURRENT_PROCESS.poll() is None,
        'file': CURRENT_FILE,
        'volume': CURRENT_VOLUME
    })


@app.route('/api/execute', methods=['POST'])
def api_execute():
    data = request.get_json() or {}
    action = data.get('action', '')
    
    if action == 'play':
        details = data.get('details', {})
        success, msg = play_audio(details.get('file', ''), details.get('volume', 50))
        return jsonify({'success': success, 'message': msg})
    
    elif action == 'stop':
        stop_current()
        return jsonify({'success': True, 'message': 'Stopped'})
    
    elif action == 'volume':
        details = data.get('details', {})
        set_volume(details.get('volume', 50))
        return jsonify({'success': True, 'message': f'Volume: {CURRENT_VOLUME}%'})
    
    elif action == 'git_pull':
        try:
            result = subprocess.run(
                ['git', 'pull'],
                cwd='/home/akash/raspberry_pi',
                capture_output=True,
                text=True,
                timeout=30
            )
            return jsonify({
                'success': result.returncode == 0,
                'message': result.stdout or result.stderr
            })
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)})
    
    elif action == 'shutdown':
        subprocess.Popen(['sudo', 'shutdown', 'now'])
        return jsonify({'success': True, 'message': 'Shutting down...'})
    
    elif action == 'reboot':
        subprocess.Popen(['sudo', 'reboot'])
        return jsonify({'success': True, 'message': 'Rebooting...'})
    
    return jsonify({'success': False, 'message': 'Unknown action'})


@app.route('/api/queue', methods=['GET', 'POST'])
def api_queue():
    if request.method == 'GET':
        return jsonify({'queue': load_command_queue()})
    else:
        data = request.get_json() or {}
        queue = data.get('queue', [])
        save_command_queue(queue)
        return jsonify({'success': True})


if __name__ == '__main__':
    print("🍓 Pi Control Panel starting...")
    print(f"   Audio directory: {AUDIO_DIR}")
    print(f"   Audio device: {AUDIO_DEVICE}")
    print("   Open http://YOUR_PI_IP:5000 in your browser")
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
