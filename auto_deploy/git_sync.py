#!/usr/bin/env python3
"""
Git Auto-Sync Service for Raspberry Pi
Polls the remote repository and pulls updates automatically.
"""

import subprocess
import time
import logging
import os
import sys
from pathlib import Path
from datetime import datetime

# Configuration
REPO_PATH = os.environ.get("GIT_SYNC_REPO_PATH", "/home/pi/raspberry_pi")
BRANCH = os.environ.get("GIT_SYNC_BRANCH", "main")
POLL_INTERVAL = int(os.environ.get("GIT_SYNC_INTERVAL", 60))  # seconds
POST_PULL_SCRIPT = os.environ.get("GIT_SYNC_POST_PULL", "")

# Logging setup
LOG_DIR = Path(REPO_PATH) / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "git_sync.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def run_command(cmd: list[str], cwd: str = None) -> tuple[int, str, str]:
    """Run a shell command and return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd or REPO_PATH,
            capture_output=True,
            text=True,
            timeout=120
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except Exception as e:
        return -1, "", str(e)


def get_local_commit() -> str:
    """Get the current local HEAD commit hash."""
    code, out, _ = run_command(["git", "rev-parse", "HEAD"])
    return out if code == 0 else ""


def get_remote_commit() -> str:
    """Fetch and get the remote HEAD commit hash."""
    # Fetch latest from remote
    code, _, err = run_command(["git", "fetch", "origin", BRANCH])
    if code != 0:
        logger.error(f"Failed to fetch: {err}")
        return ""
    
    # Get remote commit hash
    code, out, _ = run_command(["git", "rev-parse", f"origin/{BRANCH}"])
    return out if code == 0 else ""


def pull_updates() -> bool:
    """Pull the latest changes from remote."""
    logger.info("Pulling updates...")
    
    # Reset any local changes (ensures clean pull)
    run_command(["git", "reset", "--hard", f"origin/{BRANCH}"])
    
    code, out, err = run_command(["git", "pull", "origin", BRANCH])
    
    if code == 0:
        logger.info(f"Pull successful: {out}")
        return True
    else:
        logger.error(f"Pull failed: {err}")
        return False


def run_post_pull_hook():
    """Run the post-pull script if configured."""
    if not POST_PULL_SCRIPT:
        return
    
    script_path = Path(REPO_PATH) / POST_PULL_SCRIPT
    if not script_path.exists():
        logger.warning(f"Post-pull script not found: {script_path}")
        return
    
    logger.info(f"Running post-pull script: {POST_PULL_SCRIPT}")
    code, out, err = run_command(["bash", str(script_path)])
    
    if code == 0:
        logger.info(f"Post-pull script completed: {out}")
    else:
        logger.error(f"Post-pull script failed: {err}")


def check_and_sync():
    """Check for updates and sync if needed."""
    local = get_local_commit()
    remote = get_remote_commit()
    
    if not local or not remote:
        logger.warning("Could not get commit hashes, skipping this cycle")
        return False
    
    if local != remote:
        logger.info(f"Update detected: {local[:8]} -> {remote[:8]}")
        if pull_updates():
            run_post_pull_hook()
            return True
    else:
        logger.debug("No updates available")
    
    return False


def main():
    """Main sync loop."""
    logger.info("=" * 50)
    logger.info("Git Auto-Sync Service Started")
    logger.info(f"Repository: {REPO_PATH}")
    logger.info(f"Branch: {BRANCH}")
    logger.info(f"Poll interval: {POLL_INTERVAL}s")
    logger.info("=" * 50)
    
    # Verify repo exists
    if not Path(REPO_PATH).exists():
        logger.error(f"Repository path does not exist: {REPO_PATH}")
        sys.exit(1)
    
    # Verify it's a git repo
    if not (Path(REPO_PATH) / ".git").exists():
        logger.error(f"Not a git repository: {REPO_PATH}")
        sys.exit(1)
    
    while True:
        try:
            check_and_sync()
        except Exception as e:
            logger.exception(f"Error during sync: {e}")
        
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
