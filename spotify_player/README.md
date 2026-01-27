# Spotify Player with Queue System

A REST API server for controlling Spotify playback and managing a song queue on your Raspberry Pi.

## 🚀 Setup

### 1. Get Spotify API Credentials

1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Create a new app
3. Copy your **Client ID** and **Client Secret**
4. Add redirect URI: `http://localhost:5001/callback` (or your Pi's IP)

### 2. Configure

```bash
cd ~/raspberry_pi/spotify_player
cp config.example.yaml config.yaml
nano config.yaml
```

Fill in your `client_id` and `client_secret`.

### 3. Install Dependencies

```bash
pip3 install -r ../requirements.txt --break-system-packages
```

### 4. Authorize Spotify Access

Start the server:
```bash
python3 server.py
```

Then visit: `http://192.168.50.225:5001/auth` in your browser and authorize.

### 5. Install as Service

```bash
sudo cp spotify-player.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable spotify-player.service
sudo systemctl start spotify-player.service
```

## 📡 API Usage

### Search for Tracks

```bash
curl "http://192.168.50.225:5001/search?q=bohemian+rhapsody"
```

### Add to Queue

```bash
curl -X POST http://192.168.50.225:5001/queue/add \
  -H "Content-Type: application/json" \
  -d '{"track_id": "0jTvN0xulFDbVhTUVwXaHf"}'
```

### View Queue

```bash
curl http://192.168.50.225:5001/queue
```

### Play Queue

```bash
curl -X POST http://192.168.50.225:5001/play
```

### Play Next Track

```bash
curl -X POST http://192.168.50.225:5001/play/next
```

### Pause/Resume

```bash
curl -X POST http://192.168.50.225:5001/pause
curl -X POST http://192.168.50.225:5001/resume
```

### Get Currently Playing

```bash
curl http://192.168.50.225:5001/now_playing
```

### Set Volume

```bash
curl -X POST http://192.168.50.225:5001/volume \
  -H "Content-Type: application/json" \
  -d '{"volume": 50}'
```

## 🎵 How It Works

1. **Search** tracks using Spotify API
2. **Queue** tracks for playback
3. **Play** tracks via Spotify Connect (requires Spotify Premium)
4. Queue persists across restarts

## ⚠️ Requirements

- **Spotify Premium** account (required for playback)
- Spotify app registered in Developer Dashboard
- OAuth authorization completed

## 🔧 Troubleshooting

**"Not authenticated" error:**
- Visit `/auth` endpoint and authorize again

**"No devices available":**
- Make sure Spotify is open on a device (phone, computer, etc.)
- Or install `spotifyd` on the Pi for headless playback

**Playback not working:**
- Ensure you have Spotify Premium
- Check `/devices` endpoint to see available devices
- Set `device_id` in config.yaml if needed
