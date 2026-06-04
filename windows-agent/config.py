import os
import sys
from pathlib import Path

from dotenv import load_dotenv

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

AGENT_HOST = os.getenv("AGENT_HOST", "0.0.0.0")
AGENT_PORT = int(os.getenv("AGENT_PORT", "8787"))
AGENT_TOKEN = os.getenv("AGENT_TOKEN", "change-me")
AGENT_NAME = os.getenv("AGENT_NAME", os.getenv("COMPUTERNAME", "windows-agent"))
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
_log_file_value = os.getenv("LOG_FILE", "logs/spybot-agent.log")
LOG_FILE = str((BASE_DIR / _log_file_value).resolve()) if not Path(_log_file_value).is_absolute() else _log_file_value
Path(LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
ALLOW_REMOTE_POWER_ACTIONS = os.getenv("ALLOW_REMOTE_POWER_ACTIONS", "true").lower() == "true"
START_WITH_WINDOWS = os.getenv("START_WITH_WINDOWS", "true").lower() == "true"
RESTART_DELAY_SECONDS = float(os.getenv("RESTART_DELAY_SECONDS", "1.5"))
SHUTDOWN_DELAY_SECONDS = float(os.getenv("SHUTDOWN_DELAY_SECONDS", "1.5"))
AGENT_BOOT_NOTIFY_URL = os.getenv("AGENT_BOOT_NOTIFY_URL", "")
AGENT_BOOT_NOTIFY_TOKEN = os.getenv("AGENT_BOOT_NOTIFY_TOKEN", "")
_camera_index_value = os.getenv("CAMERA_INDEX", "").strip()
CAMERA_INDEX = int(_camera_index_value) if _camera_index_value else None
