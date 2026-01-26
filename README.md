# Raspberry Pi Server Project

A self-updating Raspberry Pi server that automatically pulls changes from Git.

## 🚀 Quick Start

### On Your Mac (Development Machine)

1. **Create a Git repository** (GitHub, GitLab, etc.) and push this project:

```bash
cd /Users/akash/Desktop/Employnmnet\ 2026/Projects/raspberry_pi
git add .
git commit -m "Your changes"
git push
```

2. **Make changes locally, commit, and push** — Your Pi will automatically pull them!

---

### On Your Raspberry Pi

#### Option A: One-Line Setup (Recommended)

SSH into your Pi and run:

```bash
curl -sSL https://raw.githubusercontent.com/stickfigure3/Raspberry_pi_learning_agent/main/scripts/pi_setup.sh | bash -s -- git@github.com:stickfigure3/Raspberry_pi_learning_agent.git
```

#### Option B: Manual Setup

1. **SSH into your Raspberry Pi:**
```bash
ssh akash@192.168.50.225
```

2. **Install Git and Python:**
```bash
sudo apt-get update
sudo apt-get install -y git python3 python3-pip
```

3. **Clone this repository:**
```bash
git clone git@github.com:stickfigure3/Raspberry_pi_learning_agent.git ~/raspberry_pi
cd ~/raspberry_pi
```

4. **Run the setup script:**
```bash
chmod +x scripts/pi_setup.sh
./scripts/pi_setup.sh git@github.com:stickfigure3/Raspberry_pi_learning_agent.git
```

---

## 📁 Project Structure

```
raspberry_pi/
├── auto_deploy/
│   ├── git_sync.py        # Auto-pull daemon
│   └── git-sync.service   # Systemd service file
├── scripts/
│   ├── pi_setup.sh        # Initial Pi setup script
│   └── on_update.sh       # Runs after each pull (customize this!)
├── logs/                  # Sync logs (auto-created)
└── README.md
```

## ⚙️ Configuration

The sync service is configured via environment variables in the systemd service file:

| Variable | Default | Description |
|----------|---------|-------------|
| `GIT_SYNC_REPO_PATH` | `/home/$USER/raspberry_pi` | Path to the local repository |
| `GIT_SYNC_BRANCH` | `main` | Git branch to track |
| `GIT_SYNC_INTERVAL` | `60` | Seconds between update checks |
| `GIT_SYNC_POST_PULL` | `scripts/on_update.sh` | Script to run after updates |

To change settings, edit the service file:

```bash
sudo nano /etc/systemd/system/git-sync.service
sudo systemctl daemon-reload
sudo systemctl restart git-sync
```

## 🔧 Managing the Service

```bash
# View real-time logs
journalctl -u git-sync -f

# Check status
sudo systemctl status git-sync

# Restart the service
sudo systemctl restart git-sync

# Stop the service
sudo systemctl stop git-sync

# Disable auto-start
sudo systemctl disable git-sync
```

## 📝 Adding Your Application

1. **Add your code** to this repository
2. **Edit `scripts/on_update.sh`** to restart your services after updates:

```bash
#!/bin/bash
# Example: Restart a Python app
cd ~/raspberry_pi
pip3 install -r requirements.txt
sudo systemctl restart my-app.service
```

3. **Commit and push** — Your Pi will automatically update!

## 🔐 Using SSH Keys (Recommended for Private Repos)

1. **Generate SSH key on your Pi:**
```bash
ssh-keygen -t ed25519 -C "akash@raspberrypi"
cat ~/.ssh/id_ed25519.pub
```

2. **Add the public key** to your GitHub/GitLab account

3. **Use SSH URL** when cloning:
```bash
git clone git@github.com:username/repo.git
```

## 🛠️ Troubleshooting

**Service won't start:**
```bash
journalctl -u git-sync -n 50 --no-pager
```

**Permission issues:**
```bash
sudo chown -R $USER:$USER ~/raspberry_pi
```

**Network issues:**
```bash
# Test Git connection
cd ~/raspberry_pi && git fetch origin

# Check if DNS works
ping github.com
```

**Force manual pull:**
```bash
cd ~/raspberry_pi
git fetch origin
git reset --hard origin/main
```

---

## 📜 License

MIT License - Do whatever you want with this!
