#!/usr/bin/env python3
"""
Queue manager for Spotify tracks.
"""

from typing import List, Dict, Optional
from collections import deque
import threading
import json
from pathlib import Path

QUEUE_FILE = Path.home() / ".spotify_pi" / "queue.json"


class QueueManager:
    def __init__(self, max_size: int = 100):
        self.queue: deque = deque(maxlen=max_size)
        self.current_index: int = -1
        self.lock = threading.Lock()
        self.max_size = max_size
        self._load_queue()
    
    def _load_queue(self):
        """Load queue from disk."""
        if QUEUE_FILE.exists():
            try:
                with open(QUEUE_FILE, 'r') as f:
                    data = json.load(f)
                    self.queue = deque(data.get('queue', []), maxlen=self.max_size)
                    self.current_index = data.get('current_index', -1)
            except:
                pass
    
    def _save_queue(self):
        """Save queue to disk."""
        QUEUE_FILE.parent.mkdir(exist_ok=True)
        with open(QUEUE_FILE, 'w') as f:
            json.dump({
                'queue': list(self.queue),
                'current_index': self.current_index
            }, f)
    
    def add(self, track: Dict) -> bool:
        """Add a track to the queue."""
        with self.lock:
            # Check if already in queue
            if any(t.get('id') == track.get('id') for t in self.queue):
                return False
            
            self.queue.append(track)
            self._save_queue()
            return True
    
    def add_multiple(self, tracks: List[Dict]) -> int:
        """Add multiple tracks to the queue. Returns number added."""
        added = 0
        for track in tracks:
            if self.add(track):
                added += 1
        return added
    
    def remove(self, index: int) -> Optional[Dict]:
        """Remove a track from the queue by index."""
        with self.lock:
            if 0 <= index < len(self.queue):
                track = self.queue[index]
                del self.queue[index]
                if index <= self.current_index:
                    self.current_index -= 1
                self._save_queue()
                return track
            return None
    
    def clear(self):
        """Clear the entire queue."""
        with self.lock:
            self.queue.clear()
            self.current_index = -1
            self._save_queue()
    
    def get_queue(self) -> List[Dict]:
        """Get the current queue."""
        with self.lock:
            return list(self.queue)
    
    def get_next(self) -> Optional[Dict]:
        """Get the next track in queue."""
        with self.lock:
            self.current_index += 1
            if self.current_index < len(self.queue):
                self._save_queue()
                return self.queue[self.current_index]
            self.current_index = len(self.queue) - 1
            return None
    
    def get_current(self) -> Optional[Dict]:
        """Get the current track."""
        with self.lock:
            if 0 <= self.current_index < len(self.queue):
                return self.queue[self.current_index]
            return None
    
    def peek_next(self) -> Optional[Dict]:
        """Peek at the next track without advancing."""
        with self.lock:
            next_index = self.current_index + 1
            if next_index < len(self.queue):
                return self.queue[next_index]
            return None
    
    def size(self) -> int:
        """Get queue size."""
        return len(self.queue)
    
    def is_empty(self) -> bool:
        """Check if queue is empty."""
        return len(self.queue) == 0
    
    def move_up(self, index: int) -> bool:
        """Move a track up in the queue."""
        with self.lock:
            if index > 0 and index < len(self.queue):
                self.queue[index], self.queue[index - 1] = self.queue[index - 1], self.queue[index]
                self._save_queue()
                return True
            return False
    
    def move_down(self, index: int) -> bool:
        """Move a track down in the queue."""
        with self.lock:
            if index >= 0 and index < len(self.queue) - 1:
                self.queue[index], self.queue[index + 1] = self.queue[index + 1], self.queue[index]
                self._save_queue()
                return True
            return False
