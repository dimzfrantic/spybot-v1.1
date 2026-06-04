import fcntl
import hashlib
import json
import logging
import ntpath
import os
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

import psutil
import requests
from requests import RequestException
from wakeonlan import send_magic_packet

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = Path(os.getenv("DIMZBOT_ENV_FILE", str(BASE_DIR / ".env")))


def load_env_file(path):
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


load_env_file(ENV_PATH)

TOKEN = os.getenv("TOKEN", "")
GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID", "")
TARGET_MAC = os.getenv("TARGET_MAC", "")
TARGET_PC_IP = os.getenv("TARGET_PC_IP", "")
PC_AGENT_BASE_URL = os.getenv("PC_AGENT_BASE_URL", "")
PC_AGENT_TOKEN = os.getenv("PC_AGENT_TOKEN", "")
PC_CAMERA_INDEX = os.getenv("PC_CAMERA_INDEX", "").strip()

API_BASE = f"https://api.telegram.org/bot{TOKEN}"
CONNECT_TIMEOUT = 5
READ_TIMEOUT = 20
POLL_TIMEOUT = 10
ERROR_RETRY_DELAY = 3
MAX_CONSECUTIVE_FAILURES = 10
LOCK_PATH = "/tmp/dimzbot.lock"
STARTUP_MARKER_PATH = "/tmp/dimzbot-startup-marker.json"
STARTUP_NOTIFY_COOLDOWN_SECONDS = 300
OFFSET = 0
MY_HOSTNAME = socket.gethostname().lower()
SESSION = requests.Session()
LOCK_FILE = None
TMP_DOWNLOAD_DIR = Path("/tmp/dimzbot-agent-cache")
TMP_DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
EXPLORER_TOKEN_CACHE = {}
EXPLORER_PAGE_SIZE = 12

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("dimzbot")


def acquire_single_instance_lock():
    global LOCK_FILE
    LOCK_FILE = open(LOCK_PATH, "w")
    try:
        fcntl.flock(LOCK_FILE.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        logger.error("Another dimzbot instance is already running; exiting")
        raise SystemExit(1)

    LOCK_FILE.write(str(os.getpid()))
    LOCK_FILE.flush()
    os.fsync(LOCK_FILE.fileno())


def is_pc_utama_online():
    response = os.system(f"ping -c 1 -W 1 {TARGET_PC_IP} > /dev/null 2>&1")
    return response == 0


def cek_pc_utama():
    if is_pc_utama_online():
        return "✅ *PC UTAMA:* `ONLINE`"
    return "❌ *PC UTAMA:* `OFFLINE / SHUTDOWN`"


def get_ubuntu_status():
    cpu = psutil.cpu_percent(interval=1)
    ram = psutil.virtual_memory().percent
    uptime_sec = time.time() - psutil.boot_time()
    uptime = f"{int(uptime_sec // 3600)} jam {int((uptime_sec % 3600) // 60)} menit"

    return (
        "🐧 *STATUS PC MASTER (UBUNTU)*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"📛 *Host:* `{socket.gethostname()}`\n"
        f"⚙️ *CPU:* `{cpu}%` | *RAM:* `{ram}%`\n"
        f"⏱ *Uptime:* `{uptime}`\n"
        f"🕒 _Update: {datetime.now().strftime('%H:%M:%S WIB')}_"
    )


def send_msg(text, reply_markup=None):
    url = f"{API_BASE}/sendMessage"
    payload = {
        "chat_id": GROUP_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": json.dumps(reply_markup) if reply_markup else None,
    }
    payload = {k: v for k, v in payload.items() if v is not None}
    response = SESSION.post(
        url,
        data=payload,
        timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
    )
    response.raise_for_status()
    return response.json()


def send_photo_file(file_path, caption=None):
    url = f"{API_BASE}/sendDocument"
    data = {
        "chat_id": GROUP_CHAT_ID,
        "caption": caption,
        "parse_mode": "Markdown",
    }
    data = {k: v for k, v in data.items() if v is not None}
    with open(file_path, "rb") as fh:
        response = SESSION.post(
            url,
            data=data,
            files={"document": (Path(file_path).name, fh)},
            timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
        )
    response.raise_for_status()
    return response.json()


def _get_filename_from_headers(response, fallback_name):
    disposition = response.headers.get("Content-Disposition", "")
    for part in disposition.split(";"):
        part = part.strip()
        if part.startswith("filename="):
            return part.split("=", 1)[1].strip().strip('"')
    return fallback_name


def send_document_file(file_path, caption=None):
    url = f"{API_BASE}/sendDocument"
    data = {
        "chat_id": GROUP_CHAT_ID,
        "caption": caption,
        "parse_mode": "Markdown",
    }
    data = {k: v for k, v in data.items() if v is not None}
    with open(file_path, "rb") as fh:
        response = SESSION.post(
            url,
            data=data,
            files={"document": (Path(file_path).name, fh)},
            timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
        )
    response.raise_for_status()
    return response.json()


def call_pc_agent(method, path, params=None, stream=False):
    url = f"{PC_AGENT_BASE_URL}{path}"
    headers = {"X-Agent-Token": PC_AGENT_TOKEN}
    response = SESSION.request(
        method=method,
        url=url,
        headers=headers,
        params=params,
        timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
        stream=stream,
    )
    response.raise_for_status()
    return response


def call_pc_agent_json(method, path, params=None):
    response = call_pc_agent(method, path, params=params, stream=False)
    return response.json()


def download_agent_file(path, suggested_name=None):
    response = call_pc_agent("GET", path, stream=True)
    parsed = urlparse(path)
    query_path = parse_qs(parsed.query).get("path", [None])[0]
    fallback_name = suggested_name or (Path(query_path).name if query_path else None) or Path(parsed.path).name or f"agent-{int(time.time())}.bin"
    filename = _get_filename_from_headers(response, fallback_name)
    target = TMP_DOWNLOAD_DIR / filename
    with open(target, "wb") as fh:
        for chunk in response.iter_content(chunk_size=1024 * 64):
            if chunk:
                fh.write(chunk)
    return target


def get_pc_agent_status_text():
    payload = call_pc_agent_json("GET", "/status")
    data = payload.get("data", {})
    return (
        "🖥 *STATUS PC UTAMA (WINDOWS AGENT)*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"📛 *Host:* `{data.get('host', '-')}`\n"
        f"👤 *User:* `{data.get('user', '-')}`\n"
        f"🌐 *IP:* `{data.get('ip', '-')}`\n"
        f"⚙️ *CPU:* `{data.get('cpu_percent', '-')}`%\n"
        f"🌡 *Suhu CPU:* `{data.get('cpu_temp', '-')}`\n"
        f"🧠 *RAM:* `{data.get('ram_percent', '-')}`% ({data.get('ram_used_mb', '-')}MB)\n"
        f"⏱ *Uptime:* `{data.get('uptime_text', '-')}`\n"
        f"🕒 _Update: {data.get('timestamp', '-')}_"
    )


def format_explorer_text(data):
    current_path = data.get("path", "drives:/")
    item_count = len(data.get("items", []))
    return (
        "🗂 *EXPLORER PC UTAMA*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"📍 *Path:* `{current_path}`\n"
        f"📦 *Jumlah item:* `{item_count}`\n"
        "Silakan pilih tombol folder atau file di bawah ini."
    )


def format_agent_error(exc, prefix):
    try:
        payload = exc.response.json()
        detail = payload.get("message") or payload.get("error")
        if detail:
            return f"⚠️ {prefix}: {detail}"
    except Exception:
        pass
    return f"⚠️ {prefix} (`{type(exc).__name__}`)."


def send_pc_screenshot():
    target = download_agent_file("/screenshot", f"pc-utama-screenshot-{int(time.time())}.jpg")
    send_photo_file(target, "🖼 *Screenshot PC utama berhasil diambil.*")


def send_pc_camera():
    camera_path = "/camera"
    if PC_CAMERA_INDEX:
        camera_path = f"/camera?index={quote(PC_CAMERA_INDEX, safe='')}"
    target = download_agent_file(camera_path, f"pc-utama-camera-{int(time.time())}.jpg")
    send_photo_file(target, "📷 *Hasil camera PC utama berhasil diambil.*")


def send_pc_download(target_path):
    encoded_path = quote(target_path, safe="")
    target = download_agent_file(f"/download?path={encoded_path}")
    send_document_file(target, f"📦 *File dari PC utama:* `{target_path}`")


def get_parent_windows_path(target_path):
    if not target_path or target_path == "drives:/":
        return "drives:/"
    normalized = target_path.replace("\\", "/")
    if len(normalized) == 3 and normalized[1:] == ":/":
        return normalized
    parent = ntpath.dirname(normalized.rstrip("/"))
    if not parent:
        return "drives:/"
    if len(parent) == 2 and parent[1] == ":":
        parent = parent + "/"
    return parent.replace("\\", "/")


def build_explorer_callback(kind, target_path, page=None):
    if not target_path:
        callback = f"explorer|{kind}|"
    else:
        token = hashlib.sha1(target_path.encode("utf-8")).hexdigest()[:16]
        EXPLORER_TOKEN_CACHE[token] = target_path
        callback = f"explorer|{kind}|{token}"
    if page is not None:
        callback = f"{callback}|{page}"
    return callback


def resolve_explorer_path(token_or_path):
    if not token_or_path:
        return None
    return EXPLORER_TOKEN_CACHE.get(token_or_path, token_or_path)


def get_confirmation_menu(action, title):
    return {
        "text": f"⚠️ *Konfirmasi*\n{title}",
        "inline_keyboard": [
            [{"text": "✅ Ya", "callback_data": f"confirm|{action}|yes"}],
            [{"text": "❌ Batal", "callback_data": f"confirm|{action}|no"}],
            [{"text": "🔙 Kembali ke Menu", "callback_data": "menu|open"}],
        ]
    }


def restart_server_now():
    command = ["sudo", "-n", "/usr/bin/systemctl", "reboot"]
    worker = subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return worker.pid


def get_main_menu(pc_online):
    buttons = []
    if pc_online:
        buttons.append([{"text": "🖥 Status PC Utama", "callback_data": "menu|status_pcutama"}])
        buttons.append([
            {"text": "🖼 Screenshot", "callback_data": "menu|screenshot_pcutama"},
            {"text": "📷 Camera", "callback_data": "menu|camera_pcutama"},
        ])
        buttons.append([{"text": "🗂 Explorer", "callback_data": "menu|explorer_root"}])
        buttons.append([
            {"text": "🔄 Restart PC Utama", "callback_data": "menu|restart_pcutama"},
            {"text": "🛑 Shutdown PC Utama", "callback_data": "menu|shutdown_pcutama"},
        ])
        buttons.append([{"text": "🔁 Restart PC Server", "callback_data": "menu|restart_server"}])
    else:
        buttons.append([{"text": "🚀 Nyalakan PC Utama", "callback_data": "menu|nyalakanpc"}])
        buttons.append([{"text": "🔁 Restart PC Server", "callback_data": "menu|restart_server"}])

    return {"inline_keyboard": buttons}


def get_explorer_menu(items, current_path, page=0):
    rows = []
    safe_page = max(page, 0)
    directories = [item for item in items if item.get("type") == "dir"]
    files = [item for item in items if item.get("type") == "file"]

    first_page_dir_count = min(10, len(directories))
    first_page_file_count = min(2, len(files))

    first_page_total = first_page_dir_count + first_page_file_count
    if first_page_total < EXPLORER_PAGE_SIZE:
        extra_dirs = min(EXPLORER_PAGE_SIZE - first_page_total, len(directories) - first_page_dir_count)
        first_page_dir_count += extra_dirs
        first_page_total = first_page_dir_count + first_page_file_count
    if first_page_total < EXPLORER_PAGE_SIZE:
        extra_files = min(EXPLORER_PAGE_SIZE - first_page_total, len(files) - first_page_file_count)
        first_page_file_count += extra_files

    first_page_items = directories[:first_page_dir_count] + files[:first_page_file_count]
    remaining_items = directories[first_page_dir_count:] + files[first_page_file_count:]

    if safe_page == 0:
        page_items = first_page_items
    else:
        start = (safe_page - 1) * EXPLORER_PAGE_SIZE
        end = start + EXPLORER_PAGE_SIZE
        page_items = remaining_items[start:end]

    for item in page_items:
        icon = "📁" if item.get("type") == "dir" else "📄"
        item_kind = "dir" if item.get("type") == "dir" else "file"
        rows.append([{
            "text": f"{icon} {item.get('name', '-')}",
            "callback_data": build_explorer_callback(item_kind, item.get('path', '')),
        }])

    nav_row = []
    if safe_page > 0:
        nav_row.append({
            "text": "⬅️ Sebelumnya",
            "callback_data": build_explorer_callback("dir", current_path if current_path != "drives:/" else "", page=safe_page - 1),
        })
    if (safe_page == 0 and remaining_items) or (safe_page > 0 and safe_page * EXPLORER_PAGE_SIZE < len(remaining_items)):
        nav_row.append({
            "text": "➡️ Berikutnya",
            "callback_data": build_explorer_callback("dir", current_path if current_path != "drives:/" else "", page=safe_page + 1),
        })
    if nav_row:
        rows.append(nav_row)

    if current_path and current_path != "drives:/":
        parent_path = get_parent_windows_path(current_path)
        if parent_path != current_path:
            rows.append([{
                "text": "⬆️ Folder Atas",
                "callback_data": build_explorer_callback("dir", parent_path if parent_path != "drives:/" else ""),
            }])
    rows.append([{"text": "🏠 Root Drive", "callback_data": "explorer|dir|"}])
    rows.append([{"text": "🔙 Kembali ke Menu", "callback_data": "menu|open"}])
    return {"inline_keyboard": rows}


def send_explorer_listing(target_path=None, page=0):
    payload = call_pc_agent_json("GET", "/explorer", params={"path": target_path} if target_path else None)
    data = payload.get("data", {})
    resolved_path = data.get("path", target_path or "drives:/")
    send_msg(
        format_explorer_text(data),
        get_explorer_menu(data.get("items", []), resolved_path, page=page),
    )


def handle_command(text):
    txt = text.lower().strip()

    if txt == "/menu":
        pc_online = is_pc_utama_online()
        status_server = get_ubuntu_status()
        status_pc = cek_pc_utama()
        send_msg(
            f"{status_server}\n\n{status_pc}",
            get_main_menu(pc_online),
        )
        return

    if txt == "/nyalakanpc":
        send_msg("🚀 *Perintah Diterima*\nMenyalakan PC...")
        for _ in range(3):
            send_magic_packet(TARGET_MAC)
            time.sleep(0.5)
        send_msg("✅ _Magic Packet_ telah dikirimkan melalui LAN.")
        return

    if txt == "/status_pcutama":
        try:
            send_msg(get_pc_agent_status_text())
        except Exception as exc:
            logger.exception("Failed to fetch Windows agent status for /status_pcutama")
            send_msg(f"⚠️ Gagal mengambil status PC utama dari agent (`{type(exc).__name__}`).")
        return

    if txt == "/screenshot_pcutama":
        try:
            send_pc_screenshot()
        except Exception as exc:
            logger.exception("Failed to fetch screenshot for /screenshot_pcutama")
            send_msg(f"⚠️ Gagal mengambil screenshot PC utama (`{type(exc).__name__}`).")
        return

    if txt == "/camera_pcutama":
        try:
            send_pc_camera()
        except Exception as exc:
            logger.exception("Failed to fetch camera for /camera_pcutama")
            send_msg(f"⚠️ Gagal mengambil camera PC utama (`{type(exc).__name__}`).")
        return

    if txt.startswith("/explorer_pcutama"):
        target_path = text[len("/explorer_pcutama"):].strip() or None
        try:
            send_explorer_listing(target_path)
        except Exception as exc:
            logger.exception("Failed to open explorer for /explorer_pcutama")
            send_msg(f"⚠️ Gagal membuka explorer PC utama (`{type(exc).__name__}`).")
        return

    if txt.startswith("/download_pcutama"):
        target_path = text[len("/download_pcutama"):].strip()
        if not target_path:
            send_msg("⚠️ Format download: `/download_pcutama C:/path/file.ext`")
            return
        try:
            send_pc_download(target_path)
        except Exception as exc:
            logger.exception("Failed to download file for /download_pcutama")
            send_msg(f"⚠️ Gagal mengunduh file PC utama (`{type(exc).__name__}`).")
        return

    if txt in ["/status_server", "/status_all", f"/status_{MY_HOSTNAME}"]:
        send_msg(get_ubuntu_status())
        return



def handle_callback(callback_data, message_id=None):
    if callback_data == "menu|open":
        pc_online = is_pc_utama_online()
        send_msg(f"{get_ubuntu_status()}\n\n{cek_pc_utama()}", get_main_menu(pc_online))
        return

    if callback_data == "menu|status_pcutama":
        try:
            send_msg(get_pc_agent_status_text())
        except Exception as exc:
            logger.exception("Failed to fetch Windows agent status from callback")
            send_msg(f"⚠️ Gagal mengambil status PC utama dari agent (`{type(exc).__name__}`).")
        return

    if callback_data == "menu|screenshot_pcutama":
        send_msg("🖼 *Screenshot sedang diproses...*\nMohon tunggu sebentar.")
        try:
            send_pc_screenshot()
        except Exception as exc:
            logger.exception("Failed to fetch screenshot from agent")
            send_msg(f"⚠️ Gagal mengambil screenshot PC utama (`{type(exc).__name__}`).")
        return

    if callback_data == "menu|camera_pcutama":
        send_msg("📷 *Camera sedang diproses...*\nMohon tunggu sebentar.")
        try:
            send_pc_camera()
        except Exception as exc:
            logger.exception("Failed to fetch camera image from agent")
            send_msg(f"⚠️ Gagal mengambil camera PC utama (`{type(exc).__name__}`).")
        return

    if callback_data == "menu|explorer_root":
        try:
            send_explorer_listing()
        except Exception as exc:
            logger.exception("Failed to open explorer root from agent")
            send_msg(format_agent_error(exc, "Gagal membuka explorer PC utama"))
        return

    if callback_data.startswith("explorer|dir|"):
        _, _, raw_target, *rest = callback_data.split("|")
        target_token = raw_target or None
        target_path = resolve_explorer_path(target_token)
        page = 0
        if rest:
            try:
                page = max(int(rest[0]), 0)
            except ValueError:
                page = 0
        try:
            send_explorer_listing(target_path, page=page)
        except Exception as exc:
            logger.exception("Failed to browse directory from agent")
            send_msg(format_agent_error(exc, "Gagal membuka folder PC utama"))
        return

    if callback_data.startswith("explorer|file|"):
        _, _, raw_target, *_ = callback_data.split("|")
        target_token = raw_target
        target_path = resolve_explorer_path(target_token)
        try:
            send_pc_download(target_path)
        except Exception as exc:
            logger.exception("Failed to download file from agent")
            send_msg(format_agent_error(exc, "Gagal mengunduh file PC utama"))
        return

    if callback_data == "menu|nyalakanpc":
        send_msg("🚀 *Perintah Diterima*\nMenyalakan PC...")
        for _ in range(3):
            send_magic_packet(TARGET_MAC)
            time.sleep(0.5)
        send_msg("✅ _Magic Packet_ telah dikirimkan melalui LAN.")
        return

    if callback_data == "menu|restart_pcutama":
        confirmation = get_confirmation_menu("restart_pcutama", "Apakah Bapak yakin ingin merestart PC utama?")
        send_msg(confirmation["text"], {"inline_keyboard": confirmation["inline_keyboard"]})
        return

    if callback_data == "menu|shutdown_pcutama":
        confirmation = get_confirmation_menu("shutdown_pcutama", "Apakah Bapak yakin ingin mematikan PC utama?")
        send_msg(confirmation["text"], {"inline_keyboard": confirmation["inline_keyboard"]})
        return

    if callback_data == "menu|restart_server":
        confirmation = get_confirmation_menu("restart_server", "Apakah Bapak yakin ingin merestart PC server?")
        send_msg(confirmation["text"], {"inline_keyboard": confirmation["inline_keyboard"]})
        return

    if callback_data.startswith("confirm|"):
        _, action, decision = callback_data.split("|", 2)
        if decision == "no":
            send_msg("✅ *Aksi dibatalkan.*")
            return

        if action == "restart_pcutama":
            try:
                call_pc_agent_json("POST", "/restart")
                send_msg("🔄 *Perintah restart PC utama telah diteruskan ke Windows agent.*")
            except Exception as exc:
                logger.exception("Failed to restart PC utama via agent")
                send_msg(f"⚠️ Gagal meneruskan restart PC utama (`{type(exc).__name__}`).")
            return

        if action == "shutdown_pcutama":
            try:
                call_pc_agent_json("POST", "/shutdown")
                send_msg("🛑 *Perintah shutdown PC utama telah diteruskan ke Windows agent.*")
            except Exception as exc:
                logger.exception("Failed to shutdown PC utama via agent")
                send_msg(f"⚠️ Gagal meneruskan shutdown PC utama (`{type(exc).__name__}`).")
            return

        if action == "restart_server":
            send_msg("🔁 *PC server sedang diproses untuk restart...*\nMohon tunggu sebentar.")
            try:
                restart_server_now()
            except Exception as exc:
                logger.exception("Failed to restart PC server")
                send_msg(f"⚠️ Gagal menjalankan restart PC server (`{type(exc).__name__}`).")
            return

    if callback_data == "menu|status_server":
        send_msg(get_ubuntu_status())
        return


def handle_updates():
    global OFFSET
    url = f"{API_BASE}/getUpdates"
    response = SESSION.get(
        url,
        params={"offset": OFFSET, "timeout": POLL_TIMEOUT},
        timeout=(CONNECT_TIMEOUT, POLL_TIMEOUT + 10),
    )
    response.raise_for_status()
    payload = response.json()

    for up in payload.get("result", []):
        OFFSET = up["update_id"] + 1

        callback_query = up.get("callback_query")
        if callback_query:
            callback_id = callback_query.get("id")
            callback_data = callback_query.get("data", "")
            if callback_id:
                try:
                    SESSION.post(
                        f"{API_BASE}/answerCallbackQuery",
                        data={"callback_query_id": callback_id},
                        timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                    ).raise_for_status()
                except Exception:
                    logger.exception("Failed to answer callback query")
            if callback_data:
                logger.info("Received callback: %s", callback_data)
                handle_callback(callback_data, callback_query.get("message", {}).get("message_id"))
            continue

        message = up.get("message", {})
        text = message.get("text")
        if not text:
            continue
        logger.info("Received command: %s", text)
        handle_command(text)


def should_send_startup_notification():
    now = time.time()
    try:
        with open(STARTUP_MARKER_PATH, "r") as fh:
            marker = json.load(fh)
        last_sent = float(marker.get("last_sent", 0))
        last_boot_time = float(marker.get("boot_time", 0))
        current_boot_time = float(psutil.boot_time())
        if current_boot_time == last_boot_time and now - last_sent < STARTUP_NOTIFY_COOLDOWN_SECONDS:
            logger.info("Skipping startup notification due to cooldown")
            return False
    except FileNotFoundError:
        pass
    except Exception:
        logger.exception("Failed to read startup marker; proceeding with notification")

    try:
        with open(STARTUP_MARKER_PATH, "w") as fh:
            json.dump({
                "last_sent": now,
                "host": MY_HOSTNAME,
                "boot_time": float(psutil.boot_time()),
            }, fh)
    except Exception:
        logger.exception("Failed to write startup marker")

    return True


def send_startup_notification():
    if not should_send_startup_notification():
        return

    send_msg(
        f"✅ *PC Master (Ubuntu) Online*\n"
        f"Host: `{MY_HOSTNAME}`\n"
        "Ketik /menu untuk status lengkap atau /nyalakanpc untuk menyalakan PC Utama"
    )


def main():
    acquire_single_instance_lock()
    consecutive_failures = 0

    try:
        send_startup_notification()
    except Exception:
        logger.exception("Failed to send startup notification")

    while True:
        try:
            handle_updates()
            consecutive_failures = 0
        except RequestException:
            consecutive_failures += 1
            logger.exception("Telegram polling failed (%s/%s)", consecutive_failures, MAX_CONSECUTIVE_FAILURES)
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                logger.error("Max consecutive failures reached; exiting for service recovery")
                raise SystemExit(1)
            time.sleep(ERROR_RETRY_DELAY)
        except Exception:
            consecutive_failures += 1
            logger.exception("Unexpected bot loop failure (%s/%s)", consecutive_failures, MAX_CONSECUTIVE_FAILURES)
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                logger.error("Max consecutive failures reached due to unexpected errors; exiting")
                raise SystemExit(1)
            time.sleep(ERROR_RETRY_DELAY)


if __name__ == "__main__":
    main()
