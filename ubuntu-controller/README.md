# Ubuntu Controller (dimzbot)

Bot Telegram pusat yang berjalan di server Ubuntu dan mengendalikan PC utama Windows melalui HTTP agent.

## Isi folder

- `masterwol.py` — source bot pusat
- `requirements.txt` — dependency Python
- `dimzbot.service.example` — contoh service systemd
- `tests/` — test dasar helper/controller

## Prasyarat server Ubuntu

- Ubuntu/Debian berbasis systemd
- Python 3.10+ direkomendasikan
- Akses internet ke Telegram API
- Akses jaringan ke PC utama Windows pada port agent (default 8787)
- Jika ingin restart server via bot: sudoers terbatas untuk `systemctl reboot`

## 1. Siapkan folder kerja

Contoh:

```bash
sudo mkdir -p /opt/spybot
sudo chown -R $USER:$USER /opt/spybot
cd /opt/spybot
cp -r /path/ke/repo/ubuntu-controller ./ubuntu-controller
cd ubuntu-controller
```

## 2. Install dependency Python

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

## 3. Isi konfigurasi di `masterwol.py`

Edit nilai placeholder berikut:

- `TOKEN`
- `GROUP_CHAT_ID`
- `TARGET_MAC`
- `TARGET_PC_IP`
- `PC_AGENT_BASE_URL`
- `PC_AGENT_TOKEN`

Contoh:

```python
TOKEN = "isi-token-bot-telegram"
GROUP_CHAT_ID = "-100xxxxxxxxxx"
TARGET_MAC = "AA:BB:CC:DD:EE:FF"
TARGET_PC_IP = "192.168.1.10"
PC_AGENT_BASE_URL = "http://192.168.1.10:8787"
PC_AGENT_TOKEN = "ubah-dengan-token-aman-sendiri"
```

## 4. Uji manual

```bash
python3 masterwol.py
```

Jika berhasil, bot akan mulai polling Telegram.

## 5. Jadikan service systemd

Salin contoh unit:

```bash
sudo cp dimzbot.service.example /etc/systemd/system/dimzbot.service
```

Sesuaikan `ExecStart`, `WorkingDirectory`, dan `User` bila perlu. Jika memakai virtualenv, ubah contoh `ExecStart` menjadi:

```ini
ExecStart=/opt/spybot/ubuntu-controller/.venv/bin/python /opt/spybot/ubuntu-controller/masterwol.py
```

Lalu aktifkan:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now dimzbot.service
sudo systemctl status dimzbot.service --no-pager -l
```

## 6. Izinkan restart server dari Telegram (opsional)

Tambahkan sudoers terbatas:

```bash
sudo visudo -f /etc/sudoers.d/dimzbot-restart
```

Isi:

```sudoers
ubnt ALL=(root) NOPASSWD: /usr/bin/systemctl reboot
```

Verifikasi:

```bash
sudo visudo -c
sudo -n -l
```

## 7. Fitur bot yang tersedia

- `/menu`
- `/nyalakanpc`
- `/status_pcutama`
- `/status_server`
- `/screenshot_pcutama`
- `/camera_pcutama`
- `/explorer_pcutama`
- `/download_pcutama C:/path/file.ext`

## 8. Troubleshooting

### Bot tidak merespons Telegram
- cek token bot valid
- cek service:
```bash
sudo systemctl status dimzbot.service --no-pager -l
journalctl -u dimzbot.service -n 100 --no-pager -l
```

### Error 404 ke Telegram API
- token bot tidak valid / terpotong

### Error 409 Conflict
- ada script lain yang masih polling token bot yang sama
- pastikan hanya server Ubuntu yang menjalankan polling Telegram

### Restart server tidak jalan
- cek sudoers terbatas untuk `systemctl reboot`

### Explorer/download gagal
- cek agent Windows berjalan
- cek IP/port agent dapat diakses dari Ubuntu
- cek permission folder/file pada Windows
