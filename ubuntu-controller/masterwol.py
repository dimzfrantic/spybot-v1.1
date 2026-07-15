import fcntl
import hashlib
import json
import logging
import ntpath
import os
import socket
import string
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
ADMIN_TELEGRAM_ID = os.getenv("ADMIN_TELEGRAM_ID", "").strip()
USER_A_TELEGRAM_ID = os.getenv("USER_A_TELEGRAM_ID", "").strip()
USER_A_PC_NAME = os.getenv("USER_A_PC_NAME", "PC User A").strip() or "PC User A"
USER_A_PC_MAC = os.getenv("USER_A_PC_MAC", "").strip()
USER_A_PC_BROADCAST = os.getenv("USER_A_PC_BROADCAST", "").strip()
TARGET_MAC = os.getenv("TARGET_MAC", "")
TARGET_PC_IP = os.getenv("TARGET_PC_IP", "")
PC_AGENT_BASE_URL = os.getenv("PC_AGENT_BASE_URL", "")
PC_AGENT_TOKEN = os.getenv("PC_AGENT_TOKEN", "")
PC_CAMERA_INDEX = os.getenv("PC_CAMERA_INDEX", "").strip()


def _env(name, default=""):
    return os.getenv(name, default).strip()


def _target(name, owner_id, mac="", ip="", broadcast="", agent_base_url="", agent_token="", camera_index="", explorer_root="", allow_server_restart=False):
    return {
        "name": name,
        "owner_id": str(owner_id or "").strip(),
        "mac": str(mac or "").strip(),
        "ip": str(ip or "").strip(),
        "broadcast": str(broadcast or "").strip(),
        "agent_base_url": str(agent_base_url or "").strip().rstrip("/"),
        "agent_token": str(agent_token or "").strip(),
        "camera_index": str(camera_index or "").strip(),
        "explorer_root": str(explorer_root or "").strip(),
        "allow_server_restart": bool(allow_server_restart),
    }


def load_target_configs():
    targets = []
    if ADMIN_TELEGRAM_ID:
        targets.append(_target(
            name=_env("PC_UTAMA_NAME", "PC Utama"),
            owner_id=ADMIN_TELEGRAM_ID,
            mac=TARGET_MAC,
            ip=TARGET_PC_IP,
            broadcast=_env("TARGET_BROADCAST"),
            agent_base_url=PC_AGENT_BASE_URL,
            agent_token=PC_AGENT_TOKEN,
            camera_index=PC_CAMERA_INDEX,
            explorer_root=_env("PC_EXPLORER_ROOT"),
            allow_server_restart=True,
        ))
    if USER_A_TELEGRAM_ID:
        targets.append(_target(
            name=USER_A_PC_NAME,
            owner_id=USER_A_TELEGRAM_ID,
            mac=USER_A_PC_MAC,
            ip=_env("USER_A_PC_IP"),
            broadcast=USER_A_PC_BROADCAST,
            agent_base_url=_env("USER_A_PC_AGENT_BASE_URL"),
            agent_token=_env("USER_A_PC_AGENT_TOKEN"),
            camera_index=_env("USER_A_PC_CAMERA_INDEX"),
            explorer_root=_env("USER_A_PC_EXPLORER_ROOT", "C:/"),
            allow_server_restart=False,
        ))

    # Future-ready indexed targets. Example:
    # TARGET_1_OWNER_TELEGRAM_ID=123; TARGET_1_NAME=PC Staff; TARGET_1_MAC=...
    for idx in range(1, 51):
        prefix = f"TARGET_{idx}"
        owner_id = _env(f"{prefix}_OWNER_TELEGRAM_ID")
        if not owner_id:
            continue
        targets.append(_target(
            name=_env(f"{prefix}_NAME", f"PC User {idx}"),
            owner_id=owner_id,
            mac=_env(f"{prefix}_MAC"),
            ip=_env(f"{prefix}_IP"),
            broadcast=_env(f"{prefix}_BROADCAST"),
            agent_base_url=_env(f"{prefix}_AGENT_BASE_URL"),
            agent_token=_env(f"{prefix}_AGENT_TOKEN"),
            camera_index=_env(f"{prefix}_CAMERA_INDEX"),
            explorer_root=_env(f"{prefix}_EXPLORER_ROOT", "C:/"),
            # Restart server is intentionally reserved for the admin target only.
            allow_server_restart=False,
        ))
    return targets


TARGET_CONFIGS = load_target_configs()


def get_target_for_user(user_id):
    uid = str(user_id or "").strip()
    for target in TARGET_CONFIGS:
        if target.get("owner_id") == uid:
            return target
    return None


def get_default_admin_target():
    return get_target_for_user(ADMIN_TELEGRAM_ID) or (TARGET_CONFIGS[0] if TARGET_CONFIGS else None)


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


def is_pc_online(target=None):
    target = target or get_default_admin_target()
    ip = (target or {}).get("ip") or ""
    if not ip:
        return False
    response = os.system(f"ping -c 1 -W 1 {ip} > /dev/null 2>&1")
    return response == 0


def is_pc_utama_online():
    return is_pc_online(get_default_admin_target())


def cek_pc_status(target=None):
    target = target or get_default_admin_target() or {"name": "PC"}
    name = target.get("name", "PC")
    if is_pc_online(target):
        return f"✅ *{name.upper()}:* `ONLINE`"
    return f"❌ *{name.upper()}:* `OFFLINE / SHUTDOWN`"


def cek_pc_utama():
    return cek_pc_status(get_default_admin_target())


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


def resolve_chat_id(chat_id=None):
    return str(chat_id or ADMIN_TELEGRAM_ID or GROUP_CHAT_ID)


def is_private_admin(user_id):
    return bool(ADMIN_TELEGRAM_ID and str(user_id or "") == ADMIN_TELEGRAM_ID)


def is_limited_user_a(user_id):
    # Backward-compatible name: User A is now a normal per-user target owner.
    return bool(USER_A_TELEGRAM_ID and str(user_id or "") == USER_A_TELEGRAM_ID)


def is_group_admin_chat(chat_id):
    return bool(GROUP_CHAT_ID and str(chat_id or "") == str(GROUP_CHAT_ID))


def is_authorized_context(chat_id=None, user_id=None, chat_type=None):
    if chat_type == "private":
        return get_target_for_user(user_id) is not None
    if chat_id is None and user_id is None and chat_type is None:
        return True
    return is_group_admin_chat(chat_id)


def send_access_denied(chat_id=None):
    send_msg("⛔ Maaf, akun Telegram ini tidak memiliki akses ke fitur tersebut.", chat_id=chat_id)


def send_wol_packet(mac_address, broadcast=None):
    if broadcast:
        return send_magic_packet(mac_address, ip_address=broadcast)
    return send_magic_packet(mac_address)


def wake_pc(mac_address, pc_name, chat_id=None, broadcast=None):
    if not mac_address:
        send_msg(f"⚠️ MAC address untuk {pc_name} belum dikonfigurasi.", chat_id=chat_id)
        return False
    send_msg(f"🚀 *Perintah Diterima*\nMenyalakan {pc_name}...", chat_id=chat_id)
    for _ in range(3):
        send_wol_packet(mac_address, broadcast)
        time.sleep(0.5)
    send_msg(f"✅ _Magic Packet_ untuk {pc_name} telah dikirimkan melalui LAN.", chat_id=chat_id)
    return True


def send_msg(text, reply_markup=None, chat_id=None):
    url = f"{API_BASE}/sendMessage"
    payload = {
        "chat_id": resolve_chat_id(chat_id),
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


def send_photo_file(file_path, caption=None, chat_id=None):
    url = f"{API_BASE}/sendDocument"
    data = {
        "chat_id": resolve_chat_id(chat_id),
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


def send_document_file(file_path, caption=None, chat_id=None):
    url = f"{API_BASE}/sendDocument"
    data = {
        "chat_id": resolve_chat_id(chat_id),
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


def call_pc_agent(method, path, params=None, stream=False, target=None):
    target = target or get_default_admin_target() or {}
    base_url = (target.get("agent_base_url") or PC_AGENT_BASE_URL).rstrip("/")
    agent_token = target.get("agent_token") or PC_AGENT_TOKEN
    if not base_url or not agent_token:
        raise RuntimeError(f"Agent untuk {target.get('name', 'PC')} belum dikonfigurasi")
    url = f"{base_url}{path}"
    headers = {"X-Agent-Token": agent_token}
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


def call_pc_agent_json(method, path, params=None, target=None):
    response = call_pc_agent(method, path, params=params, stream=False, target=target)
    return response.json()


def download_agent_file(path, suggested_name=None, target=None):
    response = call_pc_agent("GET", path, stream=True, target=target)
    parsed = urlparse(path)
    query_path = parse_qs(parsed.query).get("path", [None])[0]
    fallback_name = suggested_name or (Path(query_path).name if query_path else None) or Path(parsed.path).name or f"agent-{int(time.time())}.bin"
    filename = _get_filename_from_headers(response, fallback_name)
    target_file = TMP_DOWNLOAD_DIR / filename
    with open(target_file, "wb") as fh:
        for chunk in response.iter_content(chunk_size=1024 * 64):
            if chunk:
                fh.write(chunk)
    return target_file


def get_pc_agent_status_text(target=None):
    target = target or get_default_admin_target() or {"name": "PC"}
    payload = call_pc_agent_json("GET", "/status", target=target)
    data = payload.get("data", {})
    name = target.get("name", "PC")
    return (
        f"🖥 *STATUS {name.upper()} (WINDOWS AGENT)*\n"
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


def format_explorer_text(data, target=None):
    target = target or get_default_admin_target() or {"name": "PC"}
    name = target.get("name", "PC")
    current_path = data.get("path", "drives:/")
    item_count = len(data.get("items", []))
    return (
        f"🗂 *EXPLORER {name.upper()}*\n"
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


def send_pc_screenshot(chat_id=None, target=None):
    target = target or get_default_admin_target() or {"name": "PC"}
    slug = target.get("name", "pc").lower().replace(" ", "-")
    target_file = download_agent_file("/screenshot", f"{slug}-screenshot-{int(time.time())}.jpg", target=target)
    send_photo_file(target_file, f"🖼 *Screenshot {target.get('name', 'PC')} berhasil diambil.*", chat_id=chat_id)


def send_pc_camera(chat_id=None, target=None):
    target = target or get_default_admin_target() or {"name": "PC"}
    camera_path = "/camera"
    camera_index = target.get("camera_index") or ""
    if camera_index:
        camera_path = f"/camera?index={quote(camera_index, safe='')}"
    slug = target.get("name", "pc").lower().replace(" ", "-")
    target_file = download_agent_file(camera_path, f"{slug}-camera-{int(time.time())}.jpg", target=target)
    send_photo_file(target_file, f"📷 *Hasil camera {target.get('name', 'PC')} berhasil diambil.*", chat_id=chat_id)


def send_pc_download(target_path, chat_id=None, target=None):
    target = target or get_default_admin_target() or {"name": "PC"}
    encoded_path = quote(target_path, safe="")
    target_file = download_agent_file(f"/download?path={encoded_path}", target=target)
    send_document_file(target_file, f"📦 *File dari {target.get('name', 'PC')}:* `{target_path}`", chat_id=chat_id)


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


def get_main_menu(pc_online, target=None):
    target = target or get_default_admin_target() or {"name": "PC", "allow_server_restart": False}
    name = target.get("name", "PC")
    buttons = []
    if pc_online:
        buttons.append([{"text": f"🖥 Status {name}", "callback_data": "menu|status_pcutama"}])
        buttons.append([
            {"text": "🖼 Screenshot", "callback_data": "menu|screenshot_pcutama"},
            {"text": "📷 Camera", "callback_data": "menu|camera_pcutama"},
        ])
        buttons.append([{"text": "🗂 Explorer", "callback_data": "menu|explorer_root"}])
        buttons.append([
            {"text": f"🔄 Restart {name}", "callback_data": "menu|restart_pcutama"},
            {"text": f"🛑 Shutdown {name}", "callback_data": "menu|shutdown_pcutama"},
        ])
    else:
        buttons.append([{"text": f"🚀 Nyalakan {name}", "callback_data": "menu|nyalakanpc"}])
    if target.get("allow_server_restart"):
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


def send_explorer_listing(target_path=None, page=0, chat_id=None, target=None):
    target = target or get_default_admin_target() or {}
    requested_path = target_path if target_path else target.get("explorer_root", "C:/")
    try:
        payload = call_pc_agent_json("GET", "/explorer", params={"path": requested_path} if requested_path else None, target=target)
    except Exception as exc:
        if target_path or requested_path:
            raise
        payload = probe_windows_drive_listing(target=target, original_error=exc)
    data = payload.get("data", {})
    resolved_path = data.get("path", requested_path or "drives:/")
    send_msg(
        format_explorer_text(data, target=target),
        get_explorer_menu(data.get("items", []), resolved_path, page=page),
        chat_id=chat_id,
    )


def probe_windows_drive_listing(target=None, original_error=None):
    items = []
    for letter in string.ascii_uppercase:
        drive_path = f"{letter}:/"
        try:
            call_pc_agent_json("GET", "/explorer", params={"path": drive_path}, target=target)
        except Exception:
            continue
        items.append({"name": f"{letter}:", "path": drive_path, "type": "dir"})

    if not items and original_error:
        raise original_error
    return {"ok": True, "data": {"ok": True, "path": "drives:/", "items": items}}


def handle_command(text, chat_id=None, user_id=None, chat_type=None):
    txt = text.lower().strip()
    target_chat_id = resolve_chat_id(chat_id)
    target = get_target_for_user(user_id)

    if not is_authorized_context(chat_id=target_chat_id, user_id=user_id, chat_type=chat_type):
        if chat_type == "private":
            send_msg("⛔ Maaf, akun Telegram ini tidak memiliki akses ke DimzBot.", chat_id=target_chat_id)
            return True
        logger.warning("Ignoring unauthorized command from chat_id=%s user_id=%s type=%s", chat_id, user_id, chat_type)
        return False

    if target is None:
        target = get_default_admin_target()
    target_name = (target or {}).get("name", "PC")

    if txt in ["/menu", "/start"]:
        pc_online = is_pc_online(target)
        status_server = get_ubuntu_status() if (target or {}).get("allow_server_restart") else ""
        status_pc = cek_pc_status(target)
        message = f"{status_server}\n\n{status_pc}" if status_server else status_pc
        send_msg(message, get_main_menu(pc_online, target), chat_id=target_chat_id)
        return True

    if txt == "/nyalakanpc":
        wake_pc((target or {}).get("mac"), target_name, chat_id=target_chat_id, broadcast=(target or {}).get("broadcast"))
        return True

    if txt in ["/status", "/status_pcutama"]:
        try:
            send_msg(get_pc_agent_status_text(target=target), chat_id=target_chat_id)
        except Exception as exc:
            logger.exception("Failed to fetch Windows agent status for %s", target_name)
            send_msg(f"⚠️ Gagal mengambil status {target_name} dari agent (`{type(exc).__name__}`).", chat_id=target_chat_id)
        return True

    if txt in ["/screenshot", "/screenshot_pcutama"]:
        try:
            send_pc_screenshot(chat_id=target_chat_id, target=target)
        except Exception as exc:
            logger.exception("Failed to fetch screenshot for %s", target_name)
            send_msg(format_agent_error(exc, f"Gagal mengambil screenshot {target_name}"), chat_id=target_chat_id)
        return True

    if txt in ["/camera", "/camera_pcutama"]:
        try:
            send_pc_camera(chat_id=target_chat_id, target=target)
        except Exception as exc:
            logger.exception("Failed to fetch camera for %s", target_name)
            send_msg(format_agent_error(exc, f"Gagal mengambil camera {target_name}"), chat_id=target_chat_id)
        return True

    if txt.startswith("/explorer") or txt.startswith("/explorer_pcutama"):
        if txt.startswith("/explorer_pcutama"):
            target_path = text[len("/explorer_pcutama"):].strip() or None
        else:
            target_path = text[len("/explorer"):].strip() or None
        try:
            send_explorer_listing(target_path, chat_id=target_chat_id, target=target)
        except Exception as exc:
            logger.exception("Failed to open explorer for %s", target_name)
            send_msg(f"⚠️ Gagal membuka explorer {target_name} (`{type(exc).__name__}`).", chat_id=target_chat_id)
        return True

    if txt.startswith("/download") or txt.startswith("/download_pcutama"):
        if txt.startswith("/download_pcutama"):
            target_path = text[len("/download_pcutama"):].strip()
        else:
            target_path = text[len("/download"):].strip()
        if not target_path:
            send_msg("⚠️ Format download: `/download C:/path/file.ext`", chat_id=target_chat_id)
            return True
        try:
            send_pc_download(target_path, chat_id=target_chat_id, target=target)
        except Exception as exc:
            logger.exception("Failed to download file for %s", target_name)
            send_msg(f"⚠️ Gagal mengunduh file {target_name} (`{type(exc).__name__}`).", chat_id=target_chat_id)
        return True

    if txt in ["/status_server", "/status_all", f"/status_{MY_HOSTNAME}"]:
        if (target or {}).get("allow_server_restart"):
            send_msg(get_ubuntu_status(), chat_id=target_chat_id)
        else:
            send_access_denied(chat_id=target_chat_id)
        return True

    return False


def handle_callback(callback_data, message_id=None, chat_id=None, user_id=None, chat_type=None):
    target_chat_id = resolve_chat_id(chat_id)
    target = get_target_for_user(user_id)
    if not is_authorized_context(chat_id=target_chat_id, user_id=user_id, chat_type=chat_type):
        if chat_type == "private":
            send_msg("⛔ Maaf, akun Telegram ini tidak memiliki akses ke DimzBot.", chat_id=target_chat_id)
            return True
        logger.warning("Ignoring unauthorized callback from chat_id=%s user_id=%s type=%s", chat_id, user_id, chat_type)
        return False

    if target is None:
        target = get_default_admin_target()
    target_name = (target or {}).get("name", "PC")

    if callback_data in ["menu|open", "limited|open"]:
        pc_online = is_pc_online(target)
        status_server = get_ubuntu_status() if (target or {}).get("allow_server_restart") else ""
        status_pc = cek_pc_status(target)
        message = f"{status_server}\n\n{status_pc}" if status_server else status_pc
        send_msg(message, get_main_menu(pc_online, target), chat_id=target_chat_id)
        return True

    if callback_data == "menu|status_pcutama":
        try:
            send_msg(get_pc_agent_status_text(target=target), chat_id=target_chat_id)
        except Exception as exc:
            logger.exception("Failed to fetch Windows agent status from callback for %s", target_name)
            send_msg(f"⚠️ Gagal mengambil status {target_name} dari agent (`{type(exc).__name__}`).", chat_id=target_chat_id)
        return True

    if callback_data == "menu|screenshot_pcutama":
        send_msg("🖼 *Screenshot sedang diproses...*\nMohon tunggu sebentar.", chat_id=target_chat_id)
        try:
            send_pc_screenshot(chat_id=target_chat_id, target=target)
        except Exception as exc:
            logger.exception("Failed to fetch screenshot from agent for %s", target_name)
            send_msg(format_agent_error(exc, f"Gagal mengambil screenshot {target_name}"), chat_id=target_chat_id)
        return True

    if callback_data == "menu|camera_pcutama":
        send_msg("📷 *Camera sedang diproses...*\nMohon tunggu sebentar.", chat_id=target_chat_id)
        try:
            send_pc_camera(chat_id=target_chat_id, target=target)
        except Exception as exc:
            logger.exception("Failed to fetch camera image from agent for %s", target_name)
            send_msg(format_agent_error(exc, f"Gagal mengambil camera {target_name}"), chat_id=target_chat_id)
        return True

    if callback_data == "menu|explorer_root":
        try:
            send_explorer_listing(chat_id=target_chat_id, target=target)
        except Exception as exc:
            logger.exception("Failed to open explorer root from agent for %s", target_name)
            send_msg(format_agent_error(exc, f"Gagal membuka explorer {target_name}"), chat_id=target_chat_id)
        return True

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
            send_explorer_listing(target_path, page=page, chat_id=target_chat_id, target=target)
        except Exception as exc:
            logger.exception("Failed to browse directory from agent for %s", target_name)
            send_msg(format_agent_error(exc, f"Gagal membuka folder {target_name}"), chat_id=target_chat_id)
        return True

    if callback_data.startswith("explorer|file|"):
        _, _, raw_target, *_ = callback_data.split("|")
        target_path = resolve_explorer_path(raw_target)
        try:
            send_pc_download(target_path, chat_id=target_chat_id, target=target)
        except Exception as exc:
            logger.exception("Failed to download file from agent for %s", target_name)
            send_msg(format_agent_error(exc, f"Gagal mengunduh file {target_name}"), chat_id=target_chat_id)
        return True

    if callback_data in ["menu|nyalakanpc", "limited|nyalakanpc"]:
        wake_pc((target or {}).get("mac"), target_name, chat_id=target_chat_id, broadcast=(target or {}).get("broadcast"))
        return True

    if callback_data == "menu|restart_pcutama":
        confirmation = get_confirmation_menu("restart_pcutama", f"Apakah yakin ingin merestart {target_name}?")
        send_msg(confirmation["text"], {"inline_keyboard": confirmation["inline_keyboard"]}, chat_id=target_chat_id)
        return True

    if callback_data == "menu|shutdown_pcutama":
        confirmation = get_confirmation_menu("shutdown_pcutama", f"Apakah yakin ingin mematikan {target_name}?")
        send_msg(confirmation["text"], {"inline_keyboard": confirmation["inline_keyboard"]}, chat_id=target_chat_id)
        return True

    if callback_data == "menu|restart_server":
        if not (target or {}).get("allow_server_restart"):
            send_access_denied(chat_id=target_chat_id)
            return True
        confirmation = get_confirmation_menu("restart_server", "Apakah Bapak yakin ingin merestart PC server?")
        send_msg(confirmation["text"], {"inline_keyboard": confirmation["inline_keyboard"]}, chat_id=target_chat_id)
        return True

    if callback_data.startswith("confirm|"):
        _, action, decision = callback_data.split("|", 2)
        if decision == "no":
            send_msg("✅ *Aksi dibatalkan.*", chat_id=target_chat_id)
            return True

        if action == "restart_pcutama":
            try:
                call_pc_agent_json("POST", "/restart", target=target)
                send_msg(f"🔄 *Perintah restart {target_name} telah diteruskan ke Windows agent.*", chat_id=target_chat_id)
            except Exception as exc:
                logger.exception("Failed to restart %s via agent", target_name)
                send_msg(f"⚠️ Gagal meneruskan restart {target_name} (`{type(exc).__name__}`).", chat_id=target_chat_id)
            return True

        if action == "shutdown_pcutama":
            try:
                call_pc_agent_json("POST", "/shutdown", target=target)
                send_msg(f"🛑 *Perintah shutdown {target_name} telah diteruskan ke Windows agent.*", chat_id=target_chat_id)
            except Exception as exc:
                logger.exception("Failed to shutdown %s via agent", target_name)
                send_msg(f"⚠️ Gagal meneruskan shutdown {target_name} (`{type(exc).__name__}`).", chat_id=target_chat_id)
            return True

        if action == "restart_server":
            if not (target or {}).get("allow_server_restart"):
                send_access_denied(chat_id=target_chat_id)
                return True
            send_msg("🔁 *PC server sedang diproses untuk restart...*\nMohon tunggu sebentar.", chat_id=target_chat_id)
            try:
                restart_server_now()
            except Exception as exc:
                logger.exception("Failed to restart PC server")
                send_msg(f"⚠️ Gagal menjalankan restart PC server (`{type(exc).__name__}`).", chat_id=target_chat_id)
            return True

    if callback_data == "menu|status_server":
        if (target or {}).get("allow_server_restart"):
            send_msg(get_ubuntu_status(), chat_id=target_chat_id)
        else:
            send_access_denied(chat_id=target_chat_id)
        return True

    return False

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
            callback_message = callback_query.get("message", {})
            callback_chat = callback_message.get("chat", {})
            callback_from = callback_query.get("from", {})
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
                logger.info(
                    "Received callback: %s from chat=%s user=%s type=%s",
                    callback_data,
                    callback_chat.get("id"),
                    callback_from.get("id"),
                    callback_chat.get("type"),
                )
                handle_callback(
                    callback_data,
                    callback_message.get("message_id"),
                    chat_id=callback_chat.get("id"),
                    user_id=callback_from.get("id"),
                    chat_type=callback_chat.get("type"),
                )
            continue

        message = up.get("message", {})
        text = message.get("text")
        if not text:
            continue
        chat = message.get("chat", {})
        sender = message.get("from", {})
        logger.info(
            "Received command: %s from chat=%s user=%s type=%s",
            text,
            chat.get("id"),
            sender.get("id"),
            chat.get("type"),
        )
        handle_command(
            text,
            chat_id=chat.get("id"),
            user_id=sender.get("id"),
            chat_type=chat.get("type"),
        )


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
