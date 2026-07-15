# Ubuntu Controller (DimzBot)

Controller Telegram untuk menjalankan Wake-on-LAN dan mengakses Windows Agent dari server Ubuntu.

Mode yang direkomendasikan adalah DM-only:
- Admin memakai DM bot untuk akses penuh.
- Grup Telegram boleh dikosongkan atau tidak dipakai.
- Setiap user dapat dipetakan ke target PC masing-masing; menu yang sama hanya berdampak pada PC milik user tersebut.

## Fitur

Admin DM:
- `/menu`
- `/nyalakanpc` untuk PC utama
- `/status_pcutama`
- `/status_server`
- `/screenshot_pcutama`
- `/camera_pcutama`
- `/explorer_pcutama`
- `/download_pcutama C:/path/file.ext`
- tombol restart/shutdown PC utama
- tombol restart server Ubuntu, jika sudoers sudah disiapkan

User/target tambahan, misalnya PC Randy:
- `/menu` menampilkan menu penuh untuk PC miliknya sendiri
- `/nyalakanpc`, Camera, Screenshot, Explorer, Restart, dan Shutdown hanya diarahkan ke PC milik user tersebut
- tidak bisa restart server Ubuntu kecuali `ALLOW_SERVER_RESTART=true`

## Isi folder

- `masterwol.py` — source utama controller bot
- `.env.example` — template konfigurasi aman untuk disalin menjadi `.env`
- `requirements.txt` — dependency Python
- `dimzbot.service.example` — contoh unit systemd
- `tests/` — test controller

## Prasyarat

- Ubuntu/Debian berbasis systemd
- Python 3.10+
- Akses internet ke Telegram API
- Akses jaringan ke PC Windows yang menjalankan Windows Agent
- Wake-on-LAN aktif di BIOS/UEFI dan adapter LAN PC target
- Token bot Telegram dari BotFather
- Telegram user ID admin dari `@myidbot` atau log update bot

## Instalasi

Contoh lokasi instalasi:

```bash
sudo mkdir -p /opt/spybot
sudo chown -R "$USER:$USER" /opt/spybot
cd /opt/spybot
cp -r /path/ke/repo/ubuntu-controller ./ubuntu-controller
cd ubuntu-controller
```

Siapkan virtualenv:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

## Konfigurasi `.env`

Salin template:

```bash
cp .env.example .env
nano .env
```

Contoh konfigurasi aman:

```dotenv
# Bot Telegram
TOKEN=isi-token-bot-telegram

# Mode DM-only. Kosongkan GROUP_CHAT_ID jika tidak memakai grup.
GROUP_CHAT_ID=
ADMIN_TELEGRAM_ID=111111111

# PC utama
TARGET_MAC=AA:BB:CC:DD:EE:FF
TARGET_PC_IP=192.168.1.10
PC_AGENT_BASE_URL=http://192.168.1.10:8787
PC_AGENT_TOKEN=ubah-dengan-token-aman-sendiri

# Kosongkan agar controller memanggil /camera biasa.
# Isi 1/2/dst jika klik Camera harus memakai /camera?index=N.
PC_CAMERA_INDEX=1

# User A / PC Randy - akses penuh untuk PC miliknya sendiri
USER_A_TELEGRAM_ID=987654321
USER_A_PC_NAME=PC User A
USER_A_PC_MAC=11:22:33:44:55:66
USER_A_PC_BROADCAST=172.16.71.255
USER_A_PC_IP=172.16.71.98
USER_A_PC_AGENT_BASE_URL=http://172.16.71.98:8787
USER_A_PC_AGENT_TOKEN=token-agent-user-a
USER_A_PC_CAMERA_INDEX=

# Format target tambahan untuk banyak user
TARGET_1_OWNER_TELEGRAM_ID=222222222
TARGET_1_NAME=PC Staff 1
TARGET_1_MAC=22:33:44:55:66:77
TARGET_1_BROADCAST=172.16.71.255
TARGET_1_IP=172.16.71.99
TARGET_1_AGENT_BASE_URL=http://172.16.71.99:8787
TARGET_1_AGENT_TOKEN=token-agent-target-1
TARGET_1_CAMERA_INDEX=
TARGET_1_ALLOW_SERVER_RESTART=false
```

Keterangan penting:
- `.env` jangan di-commit ke Git.
- `ADMIN_TELEGRAM_ID` menjadi fallback/default tujuan pesan bot jika `GROUP_CHAT_ID` kosong.
- `GROUP_CHAT_ID` hanya diperlukan jika masih ingin mempertahankan grup Telegram lama.
- `USER_A_PC_BROADCAST` boleh dikosongkan jika broadcast default Wake-on-LAN sudah cukup di jaringan tersebut.

## Alur akses

### Admin DM

Jika `ADMIN_TELEGRAM_ID` cocok dengan pengirim DM:
- bot menampilkan menu penuh
- semua balasan command, tombol inline, file, screenshot, dan camera dikirim ke chat asal
- hasil tidak bocor ke grup

### Target per user

Jika `USER_A_TELEGRAM_ID` atau `TARGET_N_OWNER_TELEGRAM_ID` cocok dengan pengirim DM:
- `/menu` menampilkan menu untuk PC milik user tersebut
- `/nyalakanpc` mengirim magic packet ke MAC target user tersebut
- Camera, Screenshot, Explorer, Restart, dan Shutdown diarahkan ke agent target user tersebut
- Restart server Ubuntu tetap hanya untuk target yang diberi `allow_server_restart`

### User lain

Jika akun tidak terdaftar:
- DM ditolak singkat
- menu admin tidak diberikan

## Uji manual

Jalankan sementara dari terminal:

```bash
source .venv/bin/activate
python3 masterwol.py
```

Lalu uji dari Telegram:
- Admin DM `/menu` harus mendapat menu penuh.
- User target tambahan DM `/menu` harus mendapat menu PC miliknya sendiri.
- User target tambahan mencoba Camera/Screenshot/Explorer harus mengenai agent PC miliknya, bukan PC admin.

Hentikan uji manual dengan `Ctrl+C` sebelum menjalankan systemd agar tidak terjadi `409 Conflict` dari Telegram API.

## Systemd service

Salin contoh unit:

```bash
sudo cp dimzbot.service.example /etc/systemd/system/dimzbot.service
sudo systemctl daemon-reload
sudo systemctl enable --now dimzbot.service
```

Jika memakai virtualenv di `/opt/spybot/ubuntu-controller/.venv`, pastikan `ExecStart` mengarah ke Python virtualenv:

```ini
[Unit]
Description=DimzBot Controller
After=network.target

[Service]
Type=simple
User=spybot
WorkingDirectory=/opt/spybot/ubuntu-controller
ExecStart=/opt/spybot/ubuntu-controller/.venv/bin/python /opt/spybot/ubuntu-controller/masterwol.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Cek status:

```bash
sudo systemctl status dimzbot.service --no-pager -l
journalctl -u dimzbot.service -n 100 --no-pager -l
```

## Izin restart server Ubuntu (opsional)

Fitur restart server hanya perlu jika tombol restart server ingin dipakai.

Buat sudoers terbatas:

```bash
sudo visudo -f /etc/sudoers.d/dimzbot-restart
```

Contoh isi, sesuaikan nama user service:

```sudoers
spybot ALL=(root) NOPASSWD: /usr/bin/systemctl reboot
```

Verifikasi:

```bash
sudo visudo -c
sudo -n -l
```

## Test

Jalankan dari root repo:

```bash
pytest -q ubuntu-controller/tests windows-agent/tests
python3 -m py_compile ubuntu-controller/masterwol.py
```

## Troubleshooting

### Bot tidak merespons

Cek service dan log:

```bash
sudo systemctl status dimzbot.service --no-pager -l
journalctl -u dimzbot.service -n 100 --no-pager -l
```

Cek juga:
- token bot valid
- `.env` berada di folder yang sama dengan `masterwol.py`
- hanya satu proses yang polling token bot yang sama

### Error 409 Conflict

Artinya ada proses lain memakai token bot yang sama. Hentikan proses manual atau service lama, lalu jalankan hanya satu controller.

### Error Telegram 404

Token bot salah, terpotong, atau tidak terbaca dari `.env`.

### Wake-on-LAN tidak menyalakan PC

Cek:
- MAC address adapter LAN benar
- PC tersambung kabel LAN
- Wake-on-LAN aktif di BIOS/UEFI
- Wake on Magic Packet aktif di driver Windows
- broadcast IP sesuai jaringan PC target

### Camera/Screenshot/Explorer gagal

Cek:
- Windows Agent berjalan
- `PC_AGENT_BASE_URL` benar
- `PC_AGENT_TOKEN` sama dengan token agent
- server Ubuntu dapat mengakses IP/port agent
- firewall Windows mengizinkan koneksi agent

## Catatan keamanan

- Jangan commit `.env`.
- Jangan hardcode token, chat ID asli, user ID asli, IP internal nyata, atau nama instansi di repo publik.
- Gunakan DM-only untuk fitur sensitif.
- Gunakan target per user agar aksi satu user tidak berdampak ke PC user lain.
