#!/usr/bin/env python3
"""
Spotify Player Server with Queue Management
REST API to search, queue, and play Spotify tracks.
"""

import os
import yaml
from pathlib import Path
from flask import Flask, jsonify, request, redirect
from spotify_api import SpotifyAPI
from queue_manager import QueueManager

app = Flask(__name__)

# Configuration
CONFIG_FILE = Path(__file__).parent / "config.yaml"
CONFIG_EXAMPLE = Path(__file__).parent / "config.example.yaml"

# Initialize components
spotify_api: SpotifyAPI = None
queue_manager: QueueManager = None
device_id: str = None


def load_config():
    """Load configuration from YAML file."""
    global spotify_api, queue_manager, device_id
    
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(
            f"Config file not found: {CONFIG_FILE}\n"
            f"Copy {CONFIG_EXAMPLE} to {CONFIG_FILE} and fill in your Spotify credentials."
        )
    
    with open(CONFIG_FILE, 'r') as f:
        config = yaml.safe_load(f)
    
    spotify_config = config.get('spotify', {})
    spotify_api = SpotifyAPI(
        client_id=spotify_config['client_id'],
        client_secret=spotify_config['client_secret'],
        redirect_uri=spotify_config['redirect_uri']
    )
    
    queue_config = config.get('queue', {})
    queue_manager = QueueManager(max_size=queue_config.get('max_size', 100))
    
    device_id = config.get('playback', {}).get('device_id')


# =============================================================================
# API Routes
# =============================================================================

@app.route('/')
def index():
    """API documentation."""
    return jsonify({
        "name": "Spotify Player with Queue",
        "endpoints": {
            "GET /": "This documentation",
            "GET /auth": "Get authorization URL",
            "GET /callback": "OAuth callback (handles authorization)",
            "GET /search": "Search tracks. Query: ?q=search+term",
            "GET /queue": "Get current queue",
            "POST /queue/add": "Add track to queue. Body: {\"track_id\": \"...\"}",
            "POST /queue/add_multiple": "Add multiple tracks. Body: {\"track_ids\": [...]}",
            "DELETE /queue/<index>": "Remove track from queue",
            "POST /queue/clear": "Clear queue",
            "POST /play": "Play current queue or specific track",
            "POST /play/next": "Play next track in queue",
            "POST /pause": "Pause playback",
            "POST /resume": "Resume playback",
            "GET /now_playing": "Get currently playing track",
            "GET /devices": "List available Spotify devices",
            "POST /volume": "Set volume. Body: {\"volume\": 50}"
        }
    })


@app.route('/auth')
def auth():
    """Get authorization URL."""
    if not spotify_api:
        return jsonify({"error": "Not configured"}), 500
    
    auth_url = spotify_api.get_auth_url()
    return jsonify({
        "auth_url": auth_url,
        "message": "Visit this URL to authorize, then you'll be redirected back"
    })


@app.route('/callback')
def callback():
    """Handle OAuth callback."""
    code = request.args.get('code')
    if not code:
        return jsonify({"error": "No authorization code provided"}), 400
    
    if spotify_api.exchange_code_for_token(code):
        return jsonify({
            "status": "success",
            "message": "Authorization successful! You can now use the API."
        })
    else:
        return jsonify({"error": "Failed to exchange code for token"}), 400


@app.route('/search')
def search():
    """Search for tracks."""
    query = request.args.get('q', '')
    limit = request.args.get('limit', 20, type=int)
    
    if not query:
        return jsonify({"error": "Missing 'q' parameter"}), 400
    
    try:
        tracks = spotify_api.search_tracks(query, limit)
        return jsonify({
            "query": query,
            "tracks": tracks,
            "count": len(tracks)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/queue')
def get_queue():
    """Get current queue."""
    queue = queue_manager.get_queue()
    current = queue_manager.get_current()
    
    return jsonify({
        "queue": queue,
        "current_index": queue_manager.current_index,
        "current_track": current,
        "size": len(queue),
        "next_track": queue_manager.peek_next()
    })


@app.route('/queue/add', methods=['POST'])
def add_to_queue():
    """Add a track to the queue."""
    data = request.get_json() or {}
    track_id = data.get('track_id') or request.args.get('track_id')
    
    if not track_id:
        return jsonify({"error": "Missing 'track_id' parameter"}), 400
    
    try:
        track = spotify_api.get_track(track_id)
        if not track:
            return jsonify({"error": "Track not found"}), 404
        
        if queue_manager.add(track):
            return jsonify({
                "status": "added",
                "track": track,
                "queue_size": queue_manager.size()
            })
        else:
            return jsonify({
                "status": "already_in_queue",
                "track": track
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/queue/add_multiple', methods=['POST'])
def add_multiple_to_queue():
    """Add multiple tracks to the queue."""
    data = request.get_json() or {}
    track_ids = data.get('track_ids', [])
    
    if not track_ids:
        return jsonify({"error": "Missing 'track_ids' parameter"}), 400
    
    try:
        tracks = []
        for track_id in track_ids:
            track = spotify_api.get_track(track_id)
            if track:
                tracks.append(track)
        
        added = queue_manager.add_multiple(tracks)
        return jsonify({
            "status": "added",
            "added_count": added,
            "total_tracks": len(tracks),
            "queue_size": queue_manager.size()
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/queue/<int:index>', methods=['DELETE'])
def remove_from_queue(index):
    """Remove a track from the queue."""
    track = queue_manager.remove(index)
    if track:
        return jsonify({
            "status": "removed",
            "track": track,
            "queue_size": queue_manager.size()
        })
    else:
        return jsonify({"error": "Invalid index"}), 404


@app.route('/queue/clear', methods=['POST'])
def clear_queue():
    """Clear the queue."""
    queue_manager.clear()
    return jsonify({"status": "cleared"})


@app.route('/play', methods=['POST'])
def play():
    """Play the queue or a specific track."""
    data = request.get_json() or {}
    track_id = data.get('track_id')
    track_uri = data.get('track_uri')
    
    try:
        if track_id:
            # Play specific track
            track = spotify_api.get_track(track_id)
            if not track:
                return jsonify({"error": "Track not found"}), 404
            
            if spotify_api.play_track(track['uri'], device_id):
                return jsonify({
                    "status": "playing",
                    "track": track
                })
        elif track_uri:
            # Play by URI
            if spotify_api.play_track(track_uri, device_id):
                return jsonify({"status": "playing"})
        else:
            # Play queue
            queue = queue_manager.get_queue()
            if not queue:
                return jsonify({"error": "Queue is empty"}), 400
            
            uris = [track['uri'] for track in queue]
            if spotify_api.play_queue(uris, device_id):
                return jsonify({
                    "status": "playing",
                    "queue_size": len(queue)
                })
        
        return jsonify({"error": "Failed to play"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/play/next', methods=['POST'])
def play_next():
    """Play next track in queue."""
    try:
        next_track = queue_manager.get_next()
        if next_track:
            if spotify_api.play_track(next_track['uri'], device_id):
                return jsonify({
                    "status": "playing",
                    "track": next_track
                })
        else:
            # Use Spotify's next track
            if spotify_api.next_track(device_id):
                return jsonify({"status": "skipped"})
        
        return jsonify({"error": "No next track"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/pause', methods=['POST'])
def pause():
    """Pause playback."""
    try:
        if spotify_api.pause(device_id):
            return jsonify({"status": "paused"})
        return jsonify({"error": "Failed to pause"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/resume', methods=['POST'])
def resume():
    """Resume playback."""
    try:
        if spotify_api.resume(device_id):
            return jsonify({"status": "resumed"})
        return jsonify({"error": "Failed to resume"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/now_playing')
def now_playing():
    """Get currently playing track."""
    try:
        track = spotify_api.get_currently_playing()
        if track:
            return jsonify({
                "status": "playing",
                "track": track
            })
        else:
            return jsonify({
                "status": "not_playing"
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/devices')
def devices():
    """List available Spotify devices."""
    try:
        devices = spotify_api.get_devices()
        return jsonify({
            "devices": devices,
            "count": len(devices)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/volume', methods=['POST'])
def set_volume():
    """Set playback volume (0-100)."""
    data = request.get_json() or {}
    volume = data.get('volume') or request.args.get('volume', type=int)
    
    if volume is None or not (0 <= volume <= 100):
        return jsonify({"error": "Volume must be between 0 and 100"}), 400
    
    try:
        if spotify_api.set_volume(volume, device_id):
            return jsonify({
                "status": "volume_set",
                "volume": volume
            })
        return jsonify({"error": "Failed to set volume"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    try:
        load_config()
        print("Spotify Player Server")
        print("Starting on http://0.0.0.0:5001")
        print("\n⚠️  Make sure you've authorized Spotify access at /auth")
        app.run(host='0.0.0.0', port=5001, debug=False)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        exit(1)
