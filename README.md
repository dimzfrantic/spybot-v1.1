# SpyBot v1.1

SpyBot v1.1 adalah platform kendali perangkat berbasis Telegram dengan arsitektur controller-agent.

Peran utama:
- `ubuntu-controller/` menjalankan bot Telegram pusat di server Ubuntu.
- `windows-agent/` berjalan di PC Windows utama dan menerima perintah dari controller melalui HTTP API lokal/jaringan.

Mode operasional yang direkomendasikan untuk v1.1 adalah DM-only:
- Admin mengakses semua fitur melalui DM bot.
- Grup Telegram bersifat opsional dan boleh dikosongkan.
- Setiap user dapat dipetakan ke target PC masing-masing; menu dan aksi user hanya berdampak pada PC miliknya.

## Status v1.1

Fitur yang sudah tersedia:
- Bot Telegram pusat di Ubuntu.
- DM admin dengan akses penuh.
- Fallback pesan bot ke DM admin jika grup dikosongkan.
- Target per user via DM, misalnya PC Randy, dengan menu penuh untuk PC miliknya sendiri.
- Wake-on-LAN PC utama dan PC target user lain.
- Status server Ubuntu.
- Status PC utama via Windows Agent.
- Screenshot PC utama.
- Camera PC utama.
- Explorer folder PC utama.
- Download file dari PC utama.
- Restart/shutdown PC utama dengan konfirmasi.
- Restart server Ubuntu dengan konfirmasi, jika sudoers sudah disiapkan.
- Windows Agent auto-start setelah login Windows.
- Test controller dan agent.

## Struktur repo

```text
spybot-v1.1/
├── README.md
├── ubuntu-controller/
│   ├── masterwol.py
│   ├── .env.example
│   ├── dimzbot.service.example
│   ├── requirements.txt
│   ├── tests/
│   └── README.md
└── windows-agent/
    ├── app.py
    ├── agent_features.py
    ├── power_actions.py
    ├── startup.py
    ├── boot_notify.py
    ├── build.bat
    ├── .env.example
    ├── tests/
    └── README.md
```

Panduan detail:
- Controller Ubuntu: `ubuntu-controller/README.md`
- Windows Agent: `windows-agent/README.md`

## Arsitektur singkat

```text
Telegram DM Admin/User
        │
        ▼
Ubuntu Controller
masterwol.py
        │
        ├── Wake-on-LAN ke PC target
        │
        └── HTTP API + X-Agent-Token
            ke Windows Agent
                    │
                    ├── status/info
                    ├── screenshot
                    ├── camera
                    ├── explorer/download
                    └── restart/shutdown
```

Prinsip arsitektur:
1. Hanya controller Ubuntu yang polling Telegram.
2. Windows Agent tidak polling Telegram.
3. Windows Agent hanya menerima HTTP request dari controller.
4. Akses sensitif diarahkan ke DM admin, bukan grup.
5. Setiap user diberi target PC sendiri sesuai konfigurasi `.env`.

## Mode akses

### Admin DM

Admin ditentukan oleh:

```env
ADMIN_TELEGRAM_ID=111111111
```

Admin mendapat akses penuh:
- `/menu`
- `/nyalakanpc`
- `/status_pcutama`
- `/status_server`
- `/screenshot_pcutama`
- `/camera_pcutama`
- `/explorer_pcutama`
- `/download_pcutama C:/path/file.ext`
- tombol restart/shutdown PC utama
- tombol restart server Ubuntu

### Target per user

Setiap user ditentukan oleh Telegram user ID dan target PC. Contoh kompatibel untuk User A/PC Randy:

```env
USER_A_TELEGRAM_ID=987654321
USER_A_PC_NAME=PC User A
USER_A_PC_MAC=11:22:33:44:55:66
USER_A_PC_BROADCAST=192.0.2.255
USER_A_PC_IP=192.0.2.11
USER_A_PC_AGENT_BASE_URL=http://192.0.2.11:8787
USER_A_PC_AGENT_TOKEN=token-agent-user-a
USER_A_PC_CAMERA_INDEX=
USER_A_PC_EXPLORER_ROOT=C:/
PC_EXPLORER_ROOT=C:/
```

Format yang disiapkan untuk banyak user/PC ke depan:

```env
TARGET_1_OWNER_TELEGRAM_ID=222222222
TARGET_1_NAME=PC Staff 1
TARGET_1_MAC=22:33:44:55:66:77
TARGET_1_BROADCAST=192.0.2.255
TARGET_1_IP=192.0.2.12
TARGET_1_AGENT_BASE_URL=http://192.0.2.12:8787
TARGET_1_AGENT_TOKEN=token-agent-target-1
TARGET_1_CAMERA_INDEX=
TARGET_1_EXPLORER_ROOT=C:/
```

User target mendapat menu untuk PC miliknya sendiri:
- `/menu` menampilkan menu PC target miliknya
- `/nyalakanpc` menyalakan PC target miliknya
- Camera, Screenshot, Explorer, Restart, dan Shutdown diarahkan ke Windows Agent PC target miliknya
- Restart server Ubuntu tetap khusus admin dan tidak diberikan kepada target user lain

### Grup Telegram

`GROUP_CHAT_ID` opsional.

Untuk mode DM-only:

```env
GROUP_CHAT_ID=
```

Jika `ADMIN_TELEGRAM_ID` diisi, pesan default/fallback seperti notifikasi startup akan diarahkan ke DM admin.

## Konfigurasi utama controller

File aktif controller adalah `.env` di folder `ubuntu-controller/`.

Contoh aman:

```env
# Bot Telegram
TOKEN=isi-token-bot-telegram
GROUP_CHAT_ID=
ADMIN_TELEGRAM_ID=111111111

# PC utama
TARGET_MAC=AA:BB:CC:DD:EE:FF
TARGET_PC_IP=192.168.1.10
PC_AGENT_BASE_URL=http://192.168.1.10:8787
PC_AGENT_TOKEN=ubah-dengan-token-aman-sendiri
PC_CAMERA_INDEX=1
PC_EXPLORER_ROOT=C:/

# User A / PC target user
USER_A_TELEGRAM_ID=987654321
USER_A_PC_NAME=PC User A
USER_A_PC_MAC=11:22:33:44:55:66
USER_A_PC_BROADCAST=192.0.2.255
USER_A_PC_IP=192.0.2.11
USER_A_PC_AGENT_BASE_URL=http://192.0.2.11:8787
USER_A_PC_AGENT_TOKEN=token-agent-user-a
USER_A_PC_CAMERA_INDEX=
USER_A_PC_EXPLORER_ROOT=C:/
PC_EXPLORER_ROOT=C:/
```

Catatan:
- Jangan commit file `.env`.
- Gunakan nilai dummy di dokumentasi publik.
- Samakan `PC_AGENT_TOKEN` di controller dengan `AGENT_TOKEN` di Windows Agent.

## Konfigurasi utama Windows Agent

File aktif agent adalah `.env` di folder runtime Windows Agent.

Parameter penting:

```env
AGENT_HOST=0.0.0.0
AGENT_PORT=8787
AGENT_TOKEN=ubah-dengan-token-aman-sendiri
AGENT_NAME=nama-pc-utama
START_WITH_WINDOWS=true
CAMERA_INDEX=
```

Jika kamera default salah, isi `CAMERA_INDEX=1` atau index lain yang sesuai.

## Instalasi cepat

### 1. Controller Ubuntu

```bash
cd ubuntu-controller
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
cp .env.example .env
nano .env
python3 masterwol.py
```

Untuk production, gunakan systemd. Lihat:

```text
ubuntu-controller/README.md
```

### 2. Windows Agent

Di PC Windows:

```powershell
cd windows-agent
python -m venv venv
venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
copy .env.example .env
notepad .env
python app.py
```

Untuk build EXE:

```powershell
build.bat
```

Hasilnya ada di:

```text
dist\spybot-agent.exe
```

## Test

Dari root repo:

```bash
pytest -q ubuntu-controller/tests windows-agent/tests
python3 -m py_compile ubuntu-controller/masterwol.py
```

Target saat ini:

```text
34 passed
```

## Checklist deploy

Controller Ubuntu:
- `.env` sudah dibuat dari `.env.example`
- `TOKEN` valid
- `ADMIN_TELEGRAM_ID` terisi
- `GROUP_CHAT_ID` dikosongkan jika DM-only
- `TARGET_MAC` benar
- `PC_AGENT_BASE_URL` dapat diakses dari Ubuntu
- `PC_AGENT_TOKEN` sama dengan token agent
- `dimzbot.service` aktif dan hanya satu proses yang polling Telegram

Windows Agent:
- `.env` berada di folder yang sama dengan EXE atau `app.py`
- `AGENT_TOKEN` sama dengan `PC_AGENT_TOKEN`
- firewall membuka port agent
- agent pernah dijalankan sekali jika memakai auto-start registry
- kamera/screenshot diuji dari controller

Target user tambahan:
- `USER_A_TELEGRAM_ID` atau `TARGET_N_OWNER_TELEGRAM_ID` sudah benar
- MAC address adalah MAC adapter LAN target
- Wake-on-LAN aktif di BIOS/UEFI dan driver Windows target
- broadcast sesuai jaringan fisik target
- agent URL/token diisi jika target diberi fitur status/camera/screenshot/explorer/restart/shutdown

## Troubleshooting singkat

### Bot tidak merespons

Cek:

```bash
sudo systemctl status dimzbot.service --no-pager -l
journalctl -u dimzbot.service -n 100 --no-pager -l
```

Penyebab umum:
- token bot salah
- service belum membaca `.env`
- ada proses lain polling token yang sama
- koneksi ke Telegram API timeout

### Error 409 Conflict

Ada lebih dari satu proses memakai token bot yang sama. Hentikan proses manual atau service lama, lalu jalankan satu controller saja.

### Wake-on-LAN gagal

Cek:
- MAC address benar
- PC target memakai kabel LAN
- Wake-on-LAN aktif di BIOS/UEFI
- Wake on Magic Packet aktif di driver Windows
- broadcast IP sesuai subnet

### Camera/Screenshot/Explorer gagal

Cek:
- Windows Agent berjalan
- `PC_AGENT_BASE_URL` benar
- `PC_AGENT_TOKEN` cocok
- firewall Windows mengizinkan port agent
- desktop session Windows aktif
- `CAMERA_INDEX` sesuai kamera yang ingin dipakai

## Catatan keamanan publik

Repo publik tidak boleh berisi:
- token bot Telegram asli
- token agent asli
- chat ID/user ID asli
- IP internal asli
- MAC address asli
- nama instansi atau identitas internal
- path server operasional asli

Gunakan `.env` untuk konfigurasi nyata dan `.env.example` untuk template dummy.
