#!/usr/bin/env python3
"""
Raspberry Pi Control Panel
A web interface for controlling audio playback with playlist/shuffle support.
"""

import os
import subprocess
import signal
import json
import threading
import time
import re
import random
from datetime import datetime
from pathlib import Path
from flask import Flask, jsonify, request, render_template_string

app = Flask(__name__)

# Configuration
AUDIO_DIR = Path(os.environ.get("AUDIO_DIR", "/home/akash/raspberry_pi/audio_files"))
LIBRARY_FILE = AUDIO_DIR / "music_library.json"
COMMAND_QUEUE_FILE = Path("/home/akash/raspberry_pi/logs/command_queue.json")
AUDIO_DEVICE = "alsa/plughw:2,0"

# Playback State
CURRENT_PROCESS = None
CURRENT_FILE = None
CURRENT_VOLUME = 50
PLAY_QUEUE = []  # List of filenames to play
QUEUE_INDEX = 0  # Current position in queue
SHUFFLE_MODE = False
REPEAT_MODE = False  # Repeat queue when finished
PLAYBACK_LOCK = threading.Lock()
MONITOR_THREAD = None
STOP_MONITOR = False

# Ensure directories exist
COMMAND_QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)


def load_library():
    """Load the music library metadata."""
    if LIBRARY_FILE.exists():
        try:
            with open(LIBRARY_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {"songs": [], "playlists": {}}


def save_library(library):
    """Save the music library metadata."""
    with open(LIBRARY_FILE, 'w') as f:
        json.dump(library, f, indent=2)


def parse_song_filename(filename):
    """Parse artist and title from filename."""
    name = Path(filename).stem
    parts = name.split(' - ', 1)
    if len(parts) == 2:
        return {'artist': parts[0].strip(), 'title': parts[1].strip()}
    return {'artist': 'Unknown', 'title': name}


def get_audio_files():
    """Get list of audio files with metadata."""
    if not AUDIO_DIR.exists():
        return []
    
    extensions = {'.mp3', '.wav', '.ogg', '.flac', '.m4a', '.aac', '.opus'}
    library = load_library()
    library_songs = {s.get('filename'): s for s in library.get('songs', [])}
    
    files = []
    for f in sorted(AUDIO_DIR.iterdir()):
        if f.is_file() and f.suffix.lower() in extensions:
            info = library_songs.get(f.name, {})
            parsed = parse_song_filename(f.name)
            
            files.append({
                'name': f.name,
                'artist': info.get('artist', parsed['artist']),
                'title': info.get('title', parsed['title']),
                'playlists': info.get('playlists', []),
                'size': f.stat().st_size,
                'size_mb': round(f.stat().st_size / (1024 * 1024), 1)
            })
    return files


def get_organized_library():
    """Get library organized by playlist and artist."""
    files = get_audio_files()
    library = load_library()
    
    by_artist = {}
    for f in files:
        artist = f['artist']
        if artist not in by_artist:
            by_artist[artist] = []
        by_artist[artist].append(f)
    
    by_playlist = {}
    for name, info in library.get('playlists', {}).items():
        playlist_files = []
        for song_name in info.get('songs', []):
            for f in files:
                if f['name'] == song_name:
                    playlist_files.append(f)
                    break
        by_playlist[name] = {
            'created': info.get('created', ''),
            'songs': playlist_files
        }
    
    return {
        'all': files,
        'by_artist': by_artist,
        'by_playlist': by_playlist,
        'stats': {
            'total_songs': len(files),
            'total_artists': len(by_artist),
            'total_playlists': len(by_playlist)
        }
    }


def stop_playback():
    """Stop currently playing audio and clear queue."""
    global CURRENT_PROCESS, CURRENT_FILE, PLAY_QUEUE, QUEUE_INDEX, STOP_MONITOR
    
    with PLAYBACK_LOCK:
        STOP_MONITOR = True
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
        PLAY_QUEUE = []
        QUEUE_INDEX = 0
    
    subprocess.run(["pkill", "-9", "mpv"], capture_output=True)


def play_file(filename):
    """Play a single audio file (internal)."""
    global CURRENT_PROCESS, CURRENT_FILE
    
    filepath = AUDIO_DIR / filename
    if not filepath.exists():
        return False
    
    # Kill any existing playback
    if CURRENT_PROCESS:
        try:
            CURRENT_PROCESS.terminate()
            CURRENT_PROCESS.wait(timeout=1)
        except:
            pass
    subprocess.run(["pkill", "-9", "mpv"], capture_output=True)
    
    try:
        cmd = [
            "mpv", "--no-video",
            f"--volume={CURRENT_VOLUME}",
            f"--audio-device={AUDIO_DEVICE}",
            "--really-quiet",
            str(filepath)
        ]
        CURRENT_PROCESS = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        CURRENT_FILE = filename
        return True
    except Exception as e:
        print(f"Play error: {e}")
        return False


def playback_monitor():
    """Background thread to monitor playback and play next song."""
    global CURRENT_PROCESS, QUEUE_INDEX, STOP_MONITOR
    
    while True:
        if STOP_MONITOR:
            break
        
        time.sleep(1)
        
        with PLAYBACK_LOCK:
            if STOP_MONITOR:
                break
            
            # Check if current song finished
            if CURRENT_PROCESS and CURRENT_PROCESS.poll() is not None:
                # Song finished, play next
                if PLAY_QUEUE and QUEUE_INDEX < len(PLAY_QUEUE) - 1:
                    QUEUE_INDEX += 1
                    play_file(PLAY_QUEUE[QUEUE_INDEX])
                elif PLAY_QUEUE and REPEAT_MODE:
                    # Restart queue
                    QUEUE_INDEX = 0
                    if SHUFFLE_MODE:
                        random.shuffle(PLAY_QUEUE)
                    play_file(PLAY_QUEUE[QUEUE_INDEX])
                else:
                    # Queue finished
                    CURRENT_PROCESS = None
                    CURRENT_FILE = None


def start_monitor():
    """Start the playback monitor thread."""
    global MONITOR_THREAD, STOP_MONITOR
    
    STOP_MONITOR = False
    if MONITOR_THREAD is None or not MONITOR_THREAD.is_alive():
        MONITOR_THREAD = threading.Thread(target=playback_monitor, daemon=True)
        MONITOR_THREAD.start()


def play_audio(filename, volume=50):
    """Play a single audio file."""
    global CURRENT_VOLUME, PLAY_QUEUE, QUEUE_INDEX, STOP_MONITOR
    
    with PLAYBACK_LOCK:
        STOP_MONITOR = True
        time.sleep(0.1)
        
        CURRENT_VOLUME = volume
        PLAY_QUEUE = [filename]
        QUEUE_INDEX = 0
        
        success = play_file(filename)
        
        STOP_MONITOR = False
        start_monitor()
        
        if success:
            return True, f"Playing: {filename}"
        return False, f"Failed to play: {filename}"


def play_queue(files, shuffle=False, volume=None):
    """Play a queue of files with optional shuffle."""
    global CURRENT_VOLUME, PLAY_QUEUE, QUEUE_INDEX, SHUFFLE_MODE, REPEAT_MODE, STOP_MONITOR
    
    if not files:
        return False, "No files to play"
    
    with PLAYBACK_LOCK:
        STOP_MONITOR = True
        time.sleep(0.1)
        
        if volume is not None:
            CURRENT_VOLUME = volume
        
        SHUFFLE_MODE = shuffle
        REPEAT_MODE = True  # Keep playing
        PLAY_QUEUE = list(files)
        
        if shuffle:
            random.shuffle(PLAY_QUEUE)
        
        QUEUE_INDEX = 0
        success = play_file(PLAY_QUEUE[0])
        
        STOP_MONITOR = False
        start_monitor()
        
        mode = "shuffle" if shuffle else "queue"
        if success:
            return True, f"Playing {len(PLAY_QUEUE)} songs ({mode})"
        return False, "Failed to start playback"


def skip_track():
    """Skip to next track in queue."""
    global QUEUE_INDEX
    
    with PLAYBACK_LOCK:
        if PLAY_QUEUE and QUEUE_INDEX < len(PLAY_QUEUE) - 1:
            QUEUE_INDEX += 1
            play_file(PLAY_QUEUE[QUEUE_INDEX])
            return True, f"Skipped to: {PLAY_QUEUE[QUEUE_INDEX]}"
        elif PLAY_QUEUE and REPEAT_MODE:
            QUEUE_INDEX = 0
            if SHUFFLE_MODE:
                random.shuffle(PLAY_QUEUE)
            play_file(PLAY_QUEUE[QUEUE_INDEX])
            return True, f"Restarted queue: {PLAY_QUEUE[QUEUE_INDEX]}"
        return False, "No next track"


def prev_track():
    """Go to previous track in queue."""
    global QUEUE_INDEX
    
    with PLAYBACK_LOCK:
        if PLAY_QUEUE and QUEUE_INDEX > 0:
            QUEUE_INDEX -= 1
            play_file(PLAY_QUEUE[QUEUE_INDEX])
            return True, f"Previous: {PLAY_QUEUE[QUEUE_INDEX]}"
        return False, "No previous track"


def set_volume(volume):
    """Change volume using amixer (no restart needed)."""
    global CURRENT_VOLUME
    CURRENT_VOLUME = max(0, min(150, volume))
    
    amixer_vol = min(100, int(volume * 100 / 150))
    try:
        subprocess.run(
            ["amixer", "-c", "2", "sset", "PCM", f"{amixer_vol}%"],
            capture_output=True,
            timeout=5
        )
    except:
        pass
    
    return True


# HTML Template with Shuffle/Queue Controls
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
            --accent-2: #ff6b9d;
            --accent-3: #a78bfa;
            --text: #e8e8e8;
            --text-dim: #888;
            --danger: #ff4757;
        }
        
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            font-family: 'Outfit', sans-serif;
            background: var(--bg-dark);
            color: var(--text);
            min-height: 100vh;
            padding: 20px;
            padding-bottom: 100px;
        }
        
        .container { max-width: 700px; margin: 0 auto; }
        
        header { text-align: center; margin-bottom: 30px; padding: 20px; }
        
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
        
        .now-playing {
            background: linear-gradient(135deg, var(--bg-card) 0%, #1a1a2e 100%);
            border: 1px solid var(--accent-dim);
            box-shadow: 0 0 40px var(--accent-glow);
        }
        
        .now-playing-info {
            display: flex;
            align-items: center;
            gap: 15px;
            margin-bottom: 15px;
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
        
        .queue-info {
            font-size: 0.8rem;
            color: var(--accent);
            margin-top: 5px;
        }
        
        .volume-control { margin: 15px 0; }
        
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
        
        .controls {
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 12px;
            margin-top: 20px;
        }
        
        .control-btn {
            border: none;
            border-radius: 50%;
            font-size: 1.2rem;
            cursor: pointer;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .control-btn.small {
            width: 45px;
            height: 45px;
            background: rgba(255,255,255,0.1);
            color: var(--text);
        }
        
        .control-btn.play {
            width: 65px;
            height: 65px;
            background: var(--accent);
            color: var(--bg-dark);
            font-size: 1.5rem;
        }
        
        .control-btn.stop {
            width: 50px;
            height: 50px;
            background: rgba(255,255,255,0.1);
            color: var(--text);
        }
        
        .control-btn:hover { transform: scale(1.1); }
        .control-btn:active { transform: scale(0.95); }
        
        .control-btn.active {
            background: var(--accent);
            color: var(--bg-dark);
        }
        
        .mode-toggles {
            display: flex;
            justify-content: center;
            gap: 15px;
            margin-top: 15px;
        }
        
        .mode-btn {
            padding: 8px 16px;
            border: 1px solid rgba(255,255,255,0.2);
            border-radius: 20px;
            background: transparent;
            color: var(--text-dim);
            font-size: 0.85rem;
            cursor: pointer;
            transition: all 0.2s;
        }
        
        .mode-btn.active {
            background: var(--accent);
            color: var(--bg-dark);
            border-color: var(--accent);
        }
        
        .tabs {
            display: flex;
            gap: 5px;
            margin-bottom: 15px;
            overflow-x: auto;
            padding-bottom: 5px;
        }
        
        .tab {
            padding: 10px 18px;
            border: none;
            border-radius: 20px;
            font-family: 'Outfit', sans-serif;
            font-size: 0.85rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            white-space: nowrap;
            background: rgba(255,255,255,0.05);
            color: var(--text-dim);
        }
        
        .tab.active {
            background: var(--accent);
            color: var(--bg-dark);
        }
        
        .tab:hover:not(.active) {
            background: rgba(255,255,255,0.1);
            color: var(--text);
        }
        
        .search-box {
            width: 100%;
            padding: 12px 15px;
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 10px;
            background: rgba(255,255,255,0.05);
            color: var(--text);
            font-family: 'Outfit', sans-serif;
            font-size: 0.95rem;
            margin-bottom: 15px;
            outline: none;
        }
        
        .search-box:focus { border-color: var(--accent); }
        .search-box::placeholder { color: var(--text-dim); }
        
        .song-list { max-height: 400px; overflow-y: auto; }
        
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
        
        .song-item:hover { background: var(--bg-hover); }
        
        .song-item.active {
            background: var(--accent-glow);
            border-left: 3px solid var(--accent);
        }
        
        .song-item.in-queue {
            border-left: 3px solid var(--accent-3);
        }
        
        .song-details { flex: 1; overflow: hidden; margin-right: 10px; }
        
        .song-title {
            font-size: 0.95rem;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        
        .song-artist {
            font-size: 0.8rem;
            color: var(--text-dim);
        }
        
        .song-actions {
            display: flex;
            gap: 8px;
        }
        
        .song-btn {
            width: 32px;
            height: 32px;
            border: none;
            border-radius: 50%;
            background: rgba(255,255,255,0.1);
            color: var(--text);
            cursor: pointer;
            font-size: 0.9rem;
            transition: all 0.2s;
        }
        
        .song-btn:hover {
            background: var(--accent);
            color: var(--bg-dark);
        }
        
        .group-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px 15px;
            margin: 10px 0 5px 0;
            background: rgba(255,255,255,0.03);
            border-radius: 8px;
            cursor: pointer;
        }
        
        .group-header h3 {
            font-size: 0.9rem;
            font-weight: 600;
            color: var(--accent-2);
        }
        
        .group-header.playlist h3 { color: var(--accent-3); }
        
        .group-header .count {
            font-size: 0.75rem;
            color: var(--text-dim);
            background: rgba(255,255,255,0.1);
            padding: 3px 10px;
            border-radius: 10px;
        }
        
        .group-header .play-all {
            padding: 5px 12px;
            border: none;
            border-radius: 15px;
            background: var(--accent);
            color: var(--bg-dark);
            font-size: 0.75rem;
            cursor: pointer;
            margin-left: 10px;
        }
        
        .group-songs {
            margin-left: 10px;
            border-left: 2px solid rgba(255,255,255,0.1);
            padding-left: 10px;
        }
        
        .stats {
            display: flex;
            gap: 20px;
            margin-bottom: 15px;
            flex-wrap: wrap;
        }
        
        .stat {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 0.85rem;
            color: var(--text-dim);
        }
        
        .stat-value {
            font-family: 'Space Mono', monospace;
            color: var(--accent);
        }
        
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
        
        .system-btn .icon { font-size: 1.5rem; }
        .system-btn.primary { background: var(--accent); color: var(--bg-dark); }
        .system-btn.secondary { background: rgba(255,255,255,0.1); color: var(--text); }
        .system-btn.danger { background: rgba(255,71,87,0.2); color: var(--danger); }
        .system-btn:hover { transform: translateY(-2px); }
        
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
        
        .toast.error { border-color: var(--danger); }
        
        @keyframes slideUp {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        .empty-state {
            text-align: center;
            padding: 40px 20px;
            color: var(--text-dim);
        }
        
        .empty-state .icon { font-size: 3rem; margin-bottom: 15px; }
        
        @media (max-width: 480px) {
            body { padding: 15px; }
            h1 { font-size: 1.5rem; }
            .card { padding: 15px; }
            .control-btn.play { width: 55px; height: 55px; font-size: 1.3rem; }
            .control-btn.small { width: 40px; height: 40px; font-size: 1rem; }
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
                    <p class="queue-info" id="queue-info"></p>
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
                <button class="control-btn small" onclick="prevTrack()" title="Previous">⏮</button>
                <button class="control-btn stop" onclick="stopAudio()" title="Stop">⏹</button>
                <button class="control-btn play" onclick="playSelected()" title="Play">▶</button>
                <button class="control-btn small" onclick="skipTrack()" title="Next">⏭</button>
            </div>
            
            <div class="mode-toggles">
                <button class="mode-btn" id="shuffle-btn" onclick="toggleShuffle()">🔀 Shuffle</button>
                <button class="mode-btn active" id="repeat-btn" onclick="toggleRepeat()">🔁 Repeat</button>
            </div>
        </div>
        
        <!-- Music Library -->
        <div class="card">
            <div class="card-title">🎧 Music Library</div>
            
            <div class="stats">
                <div class="stat">Songs: <span class="stat-value" id="stat-songs">0</span></div>
                <div class="stat">Artists: <span class="stat-value" id="stat-artists">0</span></div>
                <div class="stat">Playlists: <span class="stat-value" id="stat-playlists">0</span></div>
            </div>
            
            <div class="tabs">
                <button class="tab active" data-view="all">All Songs</button>
                <button class="tab" data-view="playlists">Playlists</button>
                <button class="tab" data-view="artists">Artists</button>
            </div>
            
            <input type="text" class="search-box" id="search-box" placeholder="🔍 Search songs, artists...">
            
            <div class="song-list" id="song-list">
                <div class="empty-state"><div class="icon">🎵</div><p>Loading...</p></div>
            </div>
        </div>
        
        <!-- System Controls -->
        <div class="card">
            <div class="card-title">⚙️ System</div>
            <div class="system-grid">
                <button class="system-btn secondary" onclick="gitPull()">
                    <span class="icon">📥</span>Git Pull
                </button>
                <button class="system-btn secondary" onclick="refreshLibrary()">
                    <span class="icon">🔄</span>Refresh
                </button>
                <button class="system-btn danger" onclick="systemAction('reboot')">
                    <span class="icon">🔁</span>Reboot
                </button>
                <button class="system-btn danger" onclick="systemAction('shutdown')">
                    <span class="icon">⏻</span>Shutdown
                </button>
            </div>
        </div>
    </div>
    
    <div class="toast-container" id="toast-container"></div>
    
    <script>
        let library = { all: [], by_artist: {}, by_playlist: {}, stats: {} };
        let selectedSong = null;
        let currentView = 'all';
        let searchQuery = '';
        let currentVolume = 50;
        let expandedGroups = new Set();
        let shuffleMode = false;
        let repeatMode = true;
        
        function loadState() {
            const savedVolume = localStorage.getItem('piControlVolume');
            if (savedVolume) {
                currentVolume = parseInt(savedVolume);
                document.getElementById('volume-slider').value = currentVolume;
                document.getElementById('volume-display').textContent = currentVolume + '%';
            }
        }
        
        function saveState() {
            localStorage.setItem('piControlVolume', currentVolume.toString());
        }
        
        function showToast(message, isError = false) {
            const container = document.getElementById('toast-container');
            const toast = document.createElement('div');
            toast.className = 'toast' + (isError ? ' error' : '');
            toast.textContent = message;
            container.appendChild(toast);
            setTimeout(() => toast.remove(), 3000);
        }
        
        async function fetchLibrary() {
            try {
                const res = await fetch('/api/library');
                library = await res.json();
                document.getElementById('stat-songs').textContent = library.stats.total_songs || 0;
                document.getElementById('stat-artists').textContent = library.stats.total_artists || 0;
                document.getElementById('stat-playlists').textContent = library.stats.total_playlists || 0;
                renderLibrary();
            } catch (e) {
                showToast('Failed to load library', true);
            }
        }
        
        function renderLibrary() {
            const list = document.getElementById('song-list');
            const query = searchQuery.toLowerCase();
            
            if (currentView === 'all') renderAllSongs(list, query);
            else if (currentView === 'artists') renderByArtist(list, query);
            else if (currentView === 'playlists') renderByPlaylist(list, query);
        }
        
        function renderAllSongs(container, query) {
            let songs = library.all || [];
            if (query) {
                songs = songs.filter(s => 
                    s.name.toLowerCase().includes(query) ||
                    s.artist.toLowerCase().includes(query) ||
                    s.title.toLowerCase().includes(query)
                );
            }
            
            if (songs.length === 0) {
                container.innerHTML = '<div class="empty-state"><div class="icon">🔍</div><p>No songs found</p></div>';
                return;
            }
            
            container.innerHTML = songs.map(song => renderSongItem(song)).join('');
        }
        
        function renderByArtist(container, query) {
            const artists = library.by_artist || {};
            let html = '';
            
            for (const artist of Object.keys(artists).sort()) {
                let songs = artists[artist];
                if (query) {
                    songs = songs.filter(s => 
                        s.name.toLowerCase().includes(query) ||
                        artist.toLowerCase().includes(query)
                    );
                }
                if (songs.length === 0) continue;
                
                const isExpanded = expandedGroups.has('artist-' + artist);
                const artistFiles = songs.map(s => s.name);
                
                html += `
                    <div class="group-header" onclick="toggleGroup('artist-${artist.replace(/'/g, "\\'")}')">
                        <h3>👤 ${artist}</h3>
                        <div>
                            <span class="count">${songs.length}</span>
                            <button class="play-all" onclick="event.stopPropagation(); playArtist('${artist.replace(/'/g, "\\'")}')">▶ Play All</button>
                        </div>
                    </div>
                `;
                
                if (isExpanded) {
                    html += '<div class="group-songs">' + songs.map(song => renderSongItem(song)).join('') + '</div>';
                }
            }
            
            container.innerHTML = html || '<div class="empty-state"><div class="icon">👤</div><p>No artists found</p></div>';
        }
        
        function renderByPlaylist(container, query) {
            const playlists = library.by_playlist || {};
            let html = '';
            
            for (const name of Object.keys(playlists).sort()) {
                let songs = playlists[name].songs || [];
                if (query && !name.toLowerCase().includes(query)) {
                    songs = songs.filter(s => s.name.toLowerCase().includes(query));
                }
                if (songs.length === 0 && !name.toLowerCase().includes(query)) continue;
                
                const isExpanded = expandedGroups.has('playlist-' + name);
                
                html += `
                    <div class="group-header playlist" onclick="toggleGroup('playlist-${name.replace(/'/g, "\\'")}')">
                        <h3>📁 ${name}</h3>
                        <div>
                            <span class="count">${songs.length}</span>
                            <button class="play-all" onclick="event.stopPropagation(); playPlaylist('${name.replace(/'/g, "\\'")}')">▶ Shuffle</button>
                        </div>
                    </div>
                `;
                
                if (isExpanded) {
                    html += '<div class="group-songs">';
                    html += songs.length > 0 ? songs.map(song => renderSongItem(song)).join('') : '<div class="empty-state"><p>Empty playlist</p></div>';
                    html += '</div>';
                }
            }
            
            container.innerHTML = html || '<div class="empty-state"><div class="icon">📁</div><p>No playlists</p></div>';
        }
        
        function renderSongItem(song) {
            const isActive = selectedSong === song.name;
            return `
                <div class="song-item ${isActive ? 'active' : ''}" onclick="selectSong('${song.name.replace(/'/g, "\\'")}')">
                    <div class="song-details">
                        <div class="song-title">${song.title || song.name}</div>
                        <div class="song-artist">${song.artist || 'Unknown'}</div>
                    </div>
                    <div class="song-actions">
                        <button class="song-btn" onclick="event.stopPropagation(); playSingle('${song.name.replace(/'/g, "\\'")}')">▶</button>
                    </div>
                </div>
            `;
        }
        
        function toggleGroup(groupId) {
            if (expandedGroups.has(groupId)) expandedGroups.delete(groupId);
            else expandedGroups.add(groupId);
            renderLibrary();
        }
        
        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                currentView = tab.dataset.view;
                renderLibrary();
            });
        });
        
        document.getElementById('search-box').addEventListener('input', (e) => {
            searchQuery = e.target.value;
            renderLibrary();
        });
        
        function selectSong(name) {
            selectedSong = name;
            renderLibrary();
        }
        
        function playSingle(name) {
            fetch('/api/play', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({file: name, volume: currentVolume})
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    selectedSong = name;
                    refreshStatus();
                    showToast('Playing: ' + name);
                } else {
                    showToast(data.error || 'Failed', true);
                }
            });
        }
        
        function playSelected() {
            if (!selectedSong) {
                showToast('Select a song first', true);
                return;
            }
            playSingle(selectedSong);
        }
        
        function playPlaylist(name) {
            const playlist = library.by_playlist[name];
            if (!playlist || !playlist.songs.length) {
                showToast('Playlist is empty', true);
                return;
            }
            
            const files = playlist.songs.map(s => s.name);
            fetch('/api/queue', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({files: files, shuffle: true, volume: currentVolume})
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    shuffleMode = true;
                    document.getElementById('shuffle-btn').classList.add('active');
                    refreshStatus();
                    showToast('Shuffling ' + name);
                } else {
                    showToast(data.error || 'Failed', true);
                }
            });
        }
        
        function playArtist(artist) {
            const songs = library.by_artist[artist];
            if (!songs || !songs.length) return;
            
            const files = songs.map(s => s.name);
            fetch('/api/queue', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({files: files, shuffle: shuffleMode, volume: currentVolume})
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    refreshStatus();
                    showToast('Playing ' + artist);
                }
            });
        }
        
        function stopAudio() {
            fetch('/api/stop', {method: 'POST'})
            .then(res => res.json())
            .then(data => {
                document.getElementById('current-track').textContent = 'Nothing playing';
                document.getElementById('current-status').textContent = 'Stopped';
                document.getElementById('queue-info').textContent = '';
                showToast('Stopped');
            });
        }
        
        function skipTrack() {
            fetch('/api/skip', {method: 'POST'})
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    refreshStatus();
                    showToast('Skipped');
                }
            });
        }
        
        function prevTrack() {
            fetch('/api/prev', {method: 'POST'})
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    refreshStatus();
                    showToast('Previous');
                }
            });
        }
        
        function toggleShuffle() {
            shuffleMode = !shuffleMode;
            document.getElementById('shuffle-btn').classList.toggle('active', shuffleMode);
            showToast('Shuffle: ' + (shuffleMode ? 'ON' : 'OFF'));
        }
        
        function toggleRepeat() {
            repeatMode = !repeatMode;
            document.getElementById('repeat-btn').classList.toggle('active', repeatMode);
            fetch('/api/repeat', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({repeat: repeatMode})
            });
            showToast('Repeat: ' + (repeatMode ? 'ON' : 'OFF'));
        }
        
        document.getElementById('volume-slider').addEventListener('input', function(e) {
            currentVolume = parseInt(e.target.value);
            document.getElementById('volume-display').textContent = currentVolume + '%';
            saveState();
        });
        
        document.getElementById('volume-slider').addEventListener('change', function(e) {
            fetch('/api/volume', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({volume: currentVolume})
            });
        });
        
        async function gitPull() {
            showToast('Pulling...');
            const res = await fetch('/api/execute', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({action: 'git_pull'})
            });
            const data = await res.json();
            showToast(data.success ? 'Updated!' : 'Failed', !data.success);
            if (data.success) fetchLibrary();
        }
        
        function systemAction(action) {
            if (!confirm(`${action} the Pi?`)) return;
            fetch('/api/execute', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({action: action})
            }).then(res => res.json()).then(data => showToast(data.message));
        }
        
        async function refreshLibrary() {
            await fetchLibrary();
            await refreshStatus();
            showToast('Refreshed!');
        }
        
        async function refreshStatus() {
            try {
                const res = await fetch('/api/status');
                const data = await res.json();
                
                if (data.playing && data.file) {
                    const song = library.all.find(s => s.name === data.file);
                    document.getElementById('current-track').textContent = song ? song.title : data.file;
                    document.getElementById('current-status').textContent = song ? song.artist : 'Playing';
                    
                    if (data.queue_length > 1) {
                        document.getElementById('queue-info').textContent = 
                            `Track ${data.queue_index + 1} of ${data.queue_length}` + 
                            (data.shuffle ? ' (shuffle)' : '');
                    } else {
                        document.getElementById('queue-info').textContent = '';
                    }
                } else {
                    document.getElementById('current-track').textContent = 'Nothing playing';
                    document.getElementById('current-status').textContent = 'Stopped';
                    document.getElementById('queue-info').textContent = '';
                }
                
                if (data.volume !== undefined) {
                    currentVolume = data.volume;
                    document.getElementById('volume-slider').value = currentVolume;
                    document.getElementById('volume-display').textContent = currentVolume + '%';
                }
            } catch (e) {}
        }
        
        loadState();
        fetchLibrary();
        refreshStatus();
        setInterval(refreshStatus, 3000);
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


@app.route('/api/library')
def api_library():
    return jsonify(get_organized_library())


@app.route('/api/play', methods=['POST'])
def api_play():
    data = request.get_json() or {}
    filename = data.get('file', '')
    volume = data.get('volume', CURRENT_VOLUME)
    
    if not filename:
        return jsonify({'success': False, 'error': 'No file specified'})
    
    success, msg = play_audio(filename, volume)
    return jsonify({'success': success, 'message': msg, 'error': None if success else msg})


@app.route('/api/queue', methods=['POST'])
def api_queue():
    data = request.get_json() or {}
    files = data.get('files', [])
    shuffle = data.get('shuffle', False)
    volume = data.get('volume')
    
    success, msg = play_queue(files, shuffle=shuffle, volume=volume)
    return jsonify({'success': success, 'message': msg})


@app.route('/api/stop', methods=['POST'])
def api_stop():
    stop_playback()
    return jsonify({'success': True, 'message': 'Stopped'})


@app.route('/api/skip', methods=['POST'])
def api_skip():
    success, msg = skip_track()
    return jsonify({'success': success, 'message': msg})


@app.route('/api/prev', methods=['POST'])
def api_prev():
    success, msg = prev_track()
    return jsonify({'success': success, 'message': msg})


@app.route('/api/volume', methods=['POST'])
def api_volume():
    data = request.get_json() or {}
    volume = data.get('volume', 50)
    set_volume(volume)
    return jsonify({'success': True, 'volume': CURRENT_VOLUME})


@app.route('/api/repeat', methods=['POST'])
def api_repeat():
    global REPEAT_MODE
    data = request.get_json() or {}
    REPEAT_MODE = data.get('repeat', True)
    return jsonify({'success': True, 'repeat': REPEAT_MODE})


@app.route('/api/status')
def api_status():
    return jsonify({
        'playing': CURRENT_PROCESS is not None and CURRENT_PROCESS.poll() is None,
        'file': CURRENT_FILE,
        'volume': CURRENT_VOLUME,
        'queue_length': len(PLAY_QUEUE),
        'queue_index': QUEUE_INDEX,
        'shuffle': SHUFFLE_MODE,
        'repeat': REPEAT_MODE
    })


@app.route('/api/execute', methods=['POST'])
def api_execute():
    data = request.get_json() or {}
    action = data.get('action', '')
    
    if action == 'git_pull':
        try:
            result = subprocess.run(
                ['git', 'pull'],
                cwd='/home/akash/raspberry_pi',
                capture_output=True,
                text=True,
                timeout=30
            )
            return jsonify({'success': result.returncode == 0, 'message': result.stdout or result.stderr})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)})
    
    elif action == 'shutdown':
        subprocess.Popen(['sudo', 'shutdown', 'now'])
        return jsonify({'success': True, 'message': 'Shutting down...'})
    
    elif action == 'reboot':
        subprocess.Popen(['sudo', 'reboot'])
        return jsonify({'success': True, 'message': 'Rebooting...'})
    
    return jsonify({'success': False, 'message': 'Unknown action'})


if __name__ == '__main__':
    print("🍓 Pi Control Panel starting...")
    print(f"   Audio directory: {AUDIO_DIR}")
    start_monitor()
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
