#!/usr/bin/env python3
"""
Raspberry Pi Control Panel
A web interface for controlling audio playback with music library organization.
"""

import os
import subprocess
import signal
import json
import threading
import time
import re
from datetime import datetime
from pathlib import Path
from flask import Flask, jsonify, request, render_template_string

app = Flask(__name__)

# Configuration
AUDIO_DIR = Path(os.environ.get("AUDIO_DIR", "/home/akash/raspberry_pi/audio_files"))
LIBRARY_FILE = AUDIO_DIR / "music_library.json"
COMMAND_QUEUE_FILE = Path("/home/akash/raspberry_pi/logs/command_queue.json")
AUDIO_DEVICE = "alsa/plughw:2,0"

# State
CURRENT_PROCESS = None
CURRENT_FILE = None
CURRENT_VOLUME = 50

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
    # Try "Artist - Title" format
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
    
    # Organize by artist
    by_artist = {}
    for f in files:
        artist = f['artist']
        if artist not in by_artist:
            by_artist[artist] = []
        by_artist[artist].append(f)
    
    # Organize by playlist
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
        play_audio(CURRENT_FILE, CURRENT_VOLUME)
        return True
    return False


# HTML Template with Music Library Browser
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
            --warning: #ffa502;
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
        .volume-control { margin: 20px 0; }
        
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
        
        .control-btn.play { background: var(--accent); color: var(--bg-dark); }
        .control-btn.stop { background: rgba(255,255,255,0.1); color: var(--text); }
        .control-btn:hover { transform: scale(1.1); }
        .control-btn:active { transform: scale(0.95); }
        
        /* Tabs */
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
        
        /* Search */
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
            transition: border-color 0.2s;
        }
        
        .search-box:focus {
            border-color: var(--accent);
        }
        
        .search-box::placeholder {
            color: var(--text-dim);
        }
        
        /* Song List */
        .song-list {
            max-height: 400px;
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
        
        .song-item:hover { background: var(--bg-hover); }
        
        .song-item.active {
            background: var(--accent-glow);
            border-left: 3px solid var(--accent);
        }
        
        .song-details {
            flex: 1;
            overflow: hidden;
            margin-right: 10px;
        }
        
        .song-title {
            font-size: 0.95rem;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        
        .song-artist {
            font-size: 0.8rem;
            color: var(--text-dim);
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        
        .song-size {
            font-size: 0.75rem;
            color: var(--text-dim);
            white-space: nowrap;
        }
        
        /* Group Headers */
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
        
        .group-songs {
            margin-left: 10px;
            border-left: 2px solid rgba(255,255,255,0.1);
            padding-left: 10px;
        }
        
        /* Stats */
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
        
        .system-btn .icon { font-size: 1.5rem; }
        .system-btn.primary { background: var(--accent); color: var(--bg-dark); }
        .system-btn.secondary { background: rgba(255,255,255,0.1); color: var(--text); }
        .system-btn.danger { background: rgba(255,71,87,0.2); color: var(--danger); }
        .system-btn:hover { transform: translateY(-2px); }
        .system-btn:active { transform: translateY(0); }
        
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
        
        .toast.error { border-color: var(--danger); }
        
        @keyframes slideUp {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        /* Empty State */
        .empty-state {
            text-align: center;
            padding: 40px 20px;
            color: var(--text-dim);
        }
        
        .empty-state .icon { font-size: 3rem; margin-bottom: 15px; }
        
        /* Responsive */
        @media (max-width: 480px) {
            body { padding: 15px; }
            h1 { font-size: 1.5rem; }
            .card { padding: 15px; }
            .control-btn { width: 50px; height: 50px; font-size: 1.2rem; }
            .tabs { gap: 3px; }
            .tab { padding: 8px 12px; font-size: 0.8rem; }
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
        
        <!-- Music Library -->
        <div class="card">
            <div class="card-title">🎧 Music Library</div>
            
            <div class="stats" id="library-stats">
                <div class="stat">
                    <span>Songs:</span>
                    <span class="stat-value" id="stat-songs">0</span>
                </div>
                <div class="stat">
                    <span>Artists:</span>
                    <span class="stat-value" id="stat-artists">0</span>
                </div>
                <div class="stat">
                    <span>Playlists:</span>
                    <span class="stat-value" id="stat-playlists">0</span>
                </div>
            </div>
            
            <div class="tabs">
                <button class="tab active" data-view="all">All Songs</button>
                <button class="tab" data-view="playlists">Playlists</button>
                <button class="tab" data-view="artists">Artists</button>
            </div>
            
            <input type="text" class="search-box" id="search-box" placeholder="🔍 Search songs, artists...">
            
            <div class="song-list" id="song-list">
                <div class="empty-state">
                    <div class="icon">🎵</div>
                    <p>Loading songs...</p>
                </div>
            </div>
        </div>
        
        <!-- System Controls -->
        <div class="card">
            <div class="card-title">⚙️ System</div>
            <div class="system-grid">
                <button class="system-btn secondary" onclick="gitPull()">
                    <span class="icon">📥</span>
                    Git Pull
                </button>
                <button class="system-btn secondary" onclick="refreshLibrary()">
                    <span class="icon">🔄</span>
                    Refresh
                </button>
                <button class="system-btn danger" onclick="systemAction('reboot')">
                    <span class="icon">🔁</span>
                    Reboot
                </button>
                <button class="system-btn danger" onclick="systemAction('shutdown')">
                    <span class="icon">⏻</span>
                    Shutdown
                </button>
            </div>
        </div>
    </div>
    
    <div class="toast-container" id="toast-container"></div>
    
    <script>
        // State
        let library = { all: [], by_artist: {}, by_playlist: {}, stats: {} };
        let selectedSong = null;
        let currentView = 'all';
        let searchQuery = '';
        let currentVolume = 50;
        let expandedGroups = new Set();
        
        // Load saved state
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
        
        // Toast
        function showToast(message, isError = false) {
            const container = document.getElementById('toast-container');
            const toast = document.createElement('div');
            toast.className = 'toast' + (isError ? ' error' : '');
            toast.textContent = message;
            container.appendChild(toast);
            setTimeout(() => toast.remove(), 3000);
        }
        
        // Fetch library
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
        
        // Render based on current view
        function renderLibrary() {
            const list = document.getElementById('song-list');
            const query = searchQuery.toLowerCase();
            
            if (currentView === 'all') {
                renderAllSongs(list, query);
            } else if (currentView === 'artists') {
                renderByArtist(list, query);
            } else if (currentView === 'playlists') {
                renderByPlaylist(list, query);
            }
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
            
            const sortedArtists = Object.keys(artists).sort();
            
            for (const artist of sortedArtists) {
                let songs = artists[artist];
                
                if (query) {
                    songs = songs.filter(s => 
                        s.name.toLowerCase().includes(query) ||
                        artist.toLowerCase().includes(query) ||
                        s.title.toLowerCase().includes(query)
                    );
                }
                
                if (songs.length === 0) continue;
                
                const isExpanded = expandedGroups.has('artist-' + artist);
                
                html += `
                    <div class="group-header" onclick="toggleGroup('artist-${artist.replace(/'/g, "\\'")}')">
                        <h3>👤 ${artist}</h3>
                        <span class="count">${songs.length} songs</span>
                    </div>
                `;
                
                if (isExpanded) {
                    html += '<div class="group-songs">';
                    html += songs.map(song => renderSongItem(song)).join('');
                    html += '</div>';
                }
            }
            
            if (!html) {
                container.innerHTML = '<div class="empty-state"><div class="icon">👤</div><p>No artists found</p></div>';
                return;
            }
            
            container.innerHTML = html;
        }
        
        function renderByPlaylist(container, query) {
            const playlists = library.by_playlist || {};
            let html = '';
            
            const sortedPlaylists = Object.keys(playlists).sort();
            
            for (const name of sortedPlaylists) {
                let songs = playlists[name].songs || [];
                
                if (query) {
                    songs = songs.filter(s => 
                        s.name.toLowerCase().includes(query) ||
                        name.toLowerCase().includes(query) ||
                        s.title.toLowerCase().includes(query)
                    );
                }
                
                if (songs.length === 0 && !name.toLowerCase().includes(query)) continue;
                
                const isExpanded = expandedGroups.has('playlist-' + name);
                
                html += `
                    <div class="group-header playlist" onclick="toggleGroup('playlist-${name.replace(/'/g, "\\'")}')">
                        <h3>📁 ${name}</h3>
                        <span class="count">${songs.length} songs</span>
                    </div>
                `;
                
                if (isExpanded) {
                    html += '<div class="group-songs">';
                    if (songs.length > 0) {
                        html += songs.map(song => renderSongItem(song)).join('');
                    } else {
                        html += '<div class="empty-state"><p>No songs in this playlist</p></div>';
                    }
                    html += '</div>';
                }
            }
            
            if (!html) {
                container.innerHTML = '<div class="empty-state"><div class="icon">📁</div><p>No playlists found</p></div>';
                return;
            }
            
            container.innerHTML = html;
        }
        
        function renderSongItem(song) {
            const isActive = selectedSong === song.name;
            return `
                <div class="song-item ${isActive ? 'active' : ''}" onclick="selectSong('${song.name.replace(/'/g, "\\'")}')">
                    <div class="song-details">
                        <div class="song-title">${song.title || song.name}</div>
                        <div class="song-artist">${song.artist || 'Unknown'}</div>
                    </div>
                    <span class="song-size">${song.size_mb} MB</span>
                </div>
            `;
        }
        
        function toggleGroup(groupId) {
            if (expandedGroups.has(groupId)) {
                expandedGroups.delete(groupId);
            } else {
                expandedGroups.add(groupId);
            }
            renderLibrary();
        }
        
        // Tab switching
        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                currentView = tab.dataset.view;
                renderLibrary();
            });
        });
        
        // Search
        document.getElementById('search-box').addEventListener('input', (e) => {
            searchQuery = e.target.value;
            renderLibrary();
        });
        
        // Select song
        function selectSong(name) {
            selectedSong = name;
            renderLibrary();
        }
        
        // Play selected
        function playSelected() {
            if (!selectedSong) {
                showToast('Select a song first', true);
                return;
            }
            
            fetch('/api/play', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({file: selectedSong, volume: currentVolume})
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    const song = library.all.find(s => s.name === selectedSong);
                    document.getElementById('current-track').textContent = song ? song.title : selectedSong;
                    document.getElementById('current-status').textContent = song ? song.artist : 'Playing';
                    showToast('Playing: ' + (song ? song.title : selectedSong));
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
            fetch('/api/volume', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({volume: currentVolume})
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) showToast('Volume: ' + currentVolume + '%');
            });
        });
        
        // Git pull
        async function gitPull() {
            showToast('Pulling updates...');
            try {
                const res = await fetch('/api/execute', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({action: 'git_pull'})
                });
                const data = await res.json();
                showToast(data.success ? 'Updated!' : 'Pull failed', !data.success);
                if (data.success) fetchLibrary();
            } catch (e) {
                showToast('Connection error', true);
            }
        }
        
        // System action
        function systemAction(action) {
            if (!confirm(`Are you sure you want to ${action} the Pi?`)) return;
            
            fetch('/api/execute', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({action: action})
            })
            .then(res => res.json())
            .then(data => showToast(data.message))
            .catch(() => showToast('Connection error', true));
        }
        
        // Refresh library
        async function refreshLibrary() {
            showToast('Refreshing...');
            await fetchLibrary();
            await refreshStatus();
            showToast('Refreshed!');
        }
        
        // Refresh status
        async function refreshStatus() {
            try {
                const res = await fetch('/api/status');
                const data = await res.json();
                
                if (data.playing && data.file) {
                    const song = library.all.find(s => s.name === data.file);
                    document.getElementById('current-track').textContent = song ? song.title : data.file;
                    document.getElementById('current-status').textContent = song ? song.artist : 'Playing';
                } else {
                    document.getElementById('current-track').textContent = 'Nothing playing';
                    document.getElementById('current-status').textContent = 'Stopped';
                }
                
                if (data.volume !== undefined) {
                    currentVolume = data.volume;
                    document.getElementById('volume-slider').value = currentVolume;
                    document.getElementById('volume-display').textContent = currentVolume + '%';
                }
            } catch (e) {
                console.error('Status refresh failed');
            }
        }
        
        // Initialize
        loadState();
        fetchLibrary();
        refreshStatus();
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


@app.route('/api/library')
def api_library():
    return jsonify(get_organized_library())


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


if __name__ == '__main__':
    print("🍓 Pi Control Panel starting...")
    print(f"   Audio directory: {AUDIO_DIR}")
    print(f"   Audio device: {AUDIO_DEVICE}")
    print("   Open http://YOUR_PI_IP:5000 in your browser")
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
