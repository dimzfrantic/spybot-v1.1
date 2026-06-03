import os
import socket
import time
from datetime import datetime

import psutil


def get_uptime_text() -> str:
    uptime_seconds = time.time() - psutil.boot_time()
    days, rem = divmod(int(uptime_seconds), 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    parts = []
    if days > 0:
        parts.append(f"{days} hari")
    if hours > 0:
        parts.append(f"{hours} jam")
    if minutes > 0:
        parts.append(f"{minutes} menit")
    return ", ".join(parts) if parts else "Baru saja menyala"


def get_cpu_temp_text() -> str:
    try:
        temps = psutil.sensors_temperatures()
        if not temps:
            return "Tidak Terdeteksi"
        for _, entries in temps.items():
            if entries:
                return f"{entries[0].current}°C"
    except Exception:
        pass
    return "Tidak Terdeteksi"


def get_local_ip() -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        local_ip = sock.getsockname()[0]
        sock.close()
        return local_ip
    except Exception:
        return "Offline"


def get_status_payload() -> dict:
    ram = psutil.virtual_memory()
    cpu_percent = psutil.cpu_percent(interval=1)
    return {
        "host": socket.gethostname(),
        "hostname": socket.gethostname().lower(),
        "user": os.getlogin(),
        "ip": get_local_ip(),
        "cpu_percent": cpu_percent,
        "cpu_temp": get_cpu_temp_text(),
        "ram_percent": ram.percent,
        "ram_used_mb": int(ram.used / 1048576),
        "uptime_text": get_uptime_text(),
        "boot_time": psutil.boot_time(),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
