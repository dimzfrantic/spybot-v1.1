import os
import threading
import time

from config import ALLOW_REMOTE_POWER_ACTIONS, RESTART_DELAY_SECONDS, SHUTDOWN_DELAY_SECONDS


def _delayed_command(command: str, delay_seconds: float):
    time.sleep(delay_seconds)
    os.system(command)


def _schedule_command(command: str, delay_seconds: float):
    worker = threading.Thread(target=_delayed_command, args=(command, delay_seconds), daemon=True)
    worker.start()


def restart_pc() -> dict:
    if not ALLOW_REMOTE_POWER_ACTIONS:
        return {
            "ok": False,
            "error": "power_actions_disabled",
            "message": "Remote power actions are disabled",
        }
    _schedule_command("shutdown /r /f /t 0", RESTART_DELAY_SECONDS)
    return {
        "ok": True,
        "message": "Restart command accepted",
    }


def shutdown_pc() -> dict:
    if not ALLOW_REMOTE_POWER_ACTIONS:
        return {
            "ok": False,
            "error": "power_actions_disabled",
            "message": "Remote power actions are disabled",
        }
    _schedule_command("shutdown /s /f /t 0", SHUTDOWN_DELAY_SECONDS)
    return {
        "ok": True,
        "message": "Shutdown command accepted",
    }
