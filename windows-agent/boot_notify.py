import socket

import requests

from config import AGENT_NAME, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


def notify_agent_boot() -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": (
            "✅ *PC Agent Windows Online*\n"
            f"Host: `{AGENT_NAME}`\n"
            f"Hostname: `{socket.gethostname()}`"
        ),
        "parse_mode": "Markdown",
    }

    response = requests.post(url, data=payload, timeout=(5, 15))
    response.raise_for_status()
    return True
