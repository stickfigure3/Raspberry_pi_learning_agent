#!/usr/bin/env python3
"""
Spotify API wrapper for searching tracks and managing playback.
"""

import os
import base64
import requests
from typing import Optional, Dict, List
import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".spotify_pi"
TOKEN_FILE = CONFIG_DIR / "token.json"


class SpotifyAPI:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.token_type: str = "Bearer"
        self._load_tokens()
    
    def _load_tokens(self):
        """Load saved tokens from file."""
        if TOKEN_FILE.exists():
            try:
                with open(TOKEN_FILE, 'r') as f:
                    data = json.load(f)
                    self.access_token = data.get('access_token')
                    self.refresh_token = data.get('refresh_token')
            except:
                pass
    
    def _save_tokens(self):
        """Save tokens to file."""
        CONFIG_DIR.mkdir(exist_ok=True)
        with open(TOKEN_FILE, 'w') as f:
            json.dump({
                'access_token': self.access_token,
                'refresh_token': self.refresh_token
            }, f)
    
    def _get_auth_header(self) -> str:
        """Get base64 encoded client credentials."""
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"
    
    def get_auth_url(self) -> str:
        """Get the authorization URL for user to visit."""
        scopes = "user-read-playback-state user-modify-playback-state user-read-currently-playing streaming"
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "scope": scopes,
            "show_dialog": "true"
        }
        query = "&".join([f"{k}={v}" for k, v in params.items()])
        return f"https://accounts.spotify.com/authorize?{query}"
    
    def exchange_code_for_token(self, code: str) -> bool:
        """Exchange authorization code for access token."""
        url = "https://accounts.spotify.com/api/token"
        headers = {
            "Authorization": self._get_auth_header(),
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri
        }
        
        response = requests.post(url, headers=headers, data=data)
        if response.status_code == 200:
            token_data = response.json()
            self.access_token = token_data["access_token"]
            self.refresh_token = token_data.get("refresh_token")
            self._save_tokens()
            return True
        return False
    
    def _refresh_access_token(self) -> bool:
        """Refresh the access token using refresh token."""
        if not self.refresh_token:
            return False
        
        url = "https://accounts.spotify.com/api/token"
        headers = {
            "Authorization": self._get_auth_header(),
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token
        }
        
        response = requests.post(url, headers=headers, data=data)
        if response.status_code == 200:
            token_data = response.json()
            self.access_token = token_data["access_token"]
            if "refresh_token" in token_data:
                self.refresh_token = token_data["refresh_token"]
            self._save_tokens()
            return True
        return False
    
    def _get_headers(self) -> Dict[str, str]:
        """Get headers for API requests."""
        if not self.access_token:
            if not self._refresh_access_token():
                raise Exception("Not authenticated. Please authorize first.")
        
        return {
            "Authorization": f"{self.token_type} {self.access_token}",
            "Content-Type": "application/json"
        }
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> Optional[Dict]:
        """Make an API request with automatic token refresh."""
        url = f"https://api.spotify.com/v1{endpoint}"
        headers = self._get_headers()
        
        response = requests.request(method, url, headers=headers, **kwargs)
        
        if response.status_code == 401:
            # Token expired, try refreshing
            if self._refresh_access_token():
                headers = self._get_headers()
                response = requests.request(method, url, headers=headers, **kwargs)
        
        if response.status_code >= 400:
            return None
        
        return response.json() if response.content else {}
    
    def search_tracks(self, query: str, limit: int = 20) -> List[Dict]:
        """Search for tracks."""
        result = self._make_request("GET", f"/search?q={query}&type=track&limit={limit}")
        if result and "tracks" in result:
            tracks = []
            for item in result["tracks"]["items"]:
                tracks.append({
                    "id": item["id"],
                    "name": item["name"],
                    "artist": ", ".join([a["name"] for a in item["artists"]]),
                    "album": item["album"]["name"],
                    "duration_ms": item["duration_ms"],
                    "uri": item["uri"],
                    "external_url": item["external_urls"]["spotify"]
                })
            return tracks
        return []
    
    def get_track(self, track_id: str) -> Optional[Dict]:
        """Get track details by ID."""
        result = self._make_request("GET", f"/tracks/{track_id}")
        if result:
            return {
                "id": result["id"],
                "name": result["name"],
                "artist": ", ".join([a["name"] for a in result["artists"]]),
                "album": result["album"]["name"],
                "duration_ms": result["duration_ms"],
                "uri": result["uri"],
                "external_url": result["external_urls"]["spotify"]
            }
        return None
    
    def get_devices(self) -> List[Dict]:
        """Get available Spotify devices."""
        result = self._make_request("GET", "/me/player/devices")
        if result and "devices" in result:
            return result["devices"]
        return []
    
    def play_track(self, track_uri: str, device_id: Optional[str] = None) -> bool:
        """Play a track on a device."""
        endpoint = "/me/player/play"
        if device_id:
            endpoint += f"?device_id={device_id}"
        
        data = {"uris": [track_uri]}
        result = self._make_request("PUT", endpoint, json=data)
        return result is not None
    
    def play_queue(self, track_uris: List[str], device_id: Optional[str] = None) -> bool:
        """Play a queue of tracks."""
        endpoint = "/me/player/play"
        if device_id:
            endpoint += f"?device_id={device_id}"
        
        data = {"uris": track_uris}
        result = self._make_request("PUT", endpoint, json=data)
        return result is not None
    
    def pause(self, device_id: Optional[str] = None) -> bool:
        """Pause playback."""
        endpoint = "/me/player/pause"
        if device_id:
            endpoint += f"?device_id={device_id}"
        result = self._make_request("PUT", endpoint)
        return result is not None
    
    def resume(self, device_id: Optional[str] = None) -> bool:
        """Resume playback."""
        endpoint = "/me/player/play"
        if device_id:
            endpoint += f"?device_id={device_id}"
        result = self._make_request("PUT", endpoint)
        return result is not None
    
    def next_track(self, device_id: Optional[str] = None) -> bool:
        """Skip to next track."""
        endpoint = "/me/player/next"
        if device_id:
            endpoint += f"?device_id={device_id}"
        result = self._make_request("POST", endpoint)
        return result is not None
    
    def previous_track(self, device_id: Optional[str] = None) -> bool:
        """Go to previous track."""
        endpoint = "/me/player/previous"
        if device_id:
            endpoint += f"?device_id={device_id}"
        result = self._make_request("POST", endpoint)
        return result is not None
    
    def get_currently_playing(self) -> Optional[Dict]:
        """Get currently playing track."""
        result = self._make_request("GET", "/me/player/currently-playing")
        if result and "item" in result:
            item = result["item"]
            return {
                "id": item["id"],
                "name": item["name"],
                "artist": ", ".join([a["name"] for a in item["artists"]]),
                "album": item["album"]["name"],
                "duration_ms": item["duration_ms"],
                "progress_ms": result.get("progress_ms", 0),
                "is_playing": result.get("is_playing", False)
            }
        return None
    
    def set_volume(self, volume: int, device_id: Optional[str] = None) -> bool:
        """Set playback volume (0-100)."""
        endpoint = f"/me/player/volume?volume_percent={volume}"
        if device_id:
            endpoint += f"&device_id={device_id}"
        result = self._make_request("PUT", endpoint)
        return result is not None
