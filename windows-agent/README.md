# Windows Agent (spybot-agent)

Agent HTTP pada PC utama Windows untuk menerima perintah dari server Ubuntu.

## Isi folder

- `app.py` — aplikasi agent
- `agent_features.py` — screenshot, camera, explorer, download
- `power_actions.py` — restart/shutdown PC
- `startup.py` — auto-start via registry Run user login
- `boot_notify.py` — notifikasi online ke Telegram
- `build.bat` — build EXE dengan PyInstaller
- `.env.example` — template konfigurasi runtime
- `tests/` — test dasar agent

## Endpoint agent

- `GET /health`
- `GET /info`
- `GET /status`
- `GET /screenshot`
- `GET /camera`
- `GET /explorer?path=<folder>`
- `GET /download?path=<file>`
- `POST /restart`
- `POST /shutdown`

Header wajib:

- `X-Agent-Token: <AGENT_TOKEN>`

## 1. Siapkan folder kerja

Catatan penting:
- Folder `windows-agent/` di repo ini adalah source tunggal resmi untuk build Windows agent.
- Jangan build dari salinan folder lain seperti `spybot-v1.1` agar seluruh fungsi dan patch terbaru ikut ke EXE.

Contoh di PC utama:

```powershell
mkdir C:\spybot-agent
```

Salin seluruh isi folder `windows-agent/` ke sana.

## 2. Konfigurasi `.env`

Salin:

```powershell
copy .env.example .env
```

Isi parameter penting:

- `AGENT_HOST=0.0.0.0` atau IP ZeroTier/LAN yang akan dipakai
- `AGENT_PORT=8787`
- `AGENT_TOKEN=ubah-dengan-token-aman-sendiri`
- `AGENT_NAME=nama-pc-utama`
- `TELEGRAM_BOT_TOKEN=isi-token-bot-telegram`
- `TELEGRAM_CHAT_ID=-100xxxxxxxxxx`  (boleh group ID)
- `START_WITH_WINDOWS=true`

## 3. Jalankan dari source Python (opsi development)

```powershell
python -m venv venv
venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python app.py
```

## 4. Uji dari Windows lokal

```powershell
Invoke-RestMethod -Headers @{"X-Agent-Token"="isi-token-aman"} -Uri "http://127.0.0.1:8787/health"
```

## 5. Uji dari server Ubuntu

```bash
curl -s -H "X-Agent-Token: isi-token-aman" http://IP_PC_UTAMA:8787/health
curl -s -H "X-Agent-Token: isi-token-aman" http://IP_PC_UTAMA:8787/status
```

## 6. Build EXE

Di Windows:

```powershell
build.bat
```

Hasil build ada di `dist\spybot-agent.exe`

## 7. Deploy EXE

Contoh runtime final:

```text
C:\spybot-agent\spybot-agent.exe
C:\spybot-agent\.env
C:\spybot-agent\logs\
```

Penting:
- `.env` harus berada di folder yang sama dengan EXE
- jalankan EXE minimal sekali agar auto-start registry terpasang

## 8. Auto-start setelah restart Windows

Jika `START_WITH_WINDOWS=true`, agent akan menulis registry:

```text
HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run
```

Catatan:
- agent otomatis berjalan setelah user Windows login kembali
- ini bukan Windows Service sistem-level

## 9. Notifikasi online agent

Saat agent start, ia akan mencoba kirim notifikasi ke Telegram memakai:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID` atau `TELEGRAM_GROUP_ID`

## 10. Troubleshooting

### EXE error `No module named ...`
- pastikan dependency sudah masuk `requirements.txt`
- jalankan ulang `build.bat`

### Unauthorized dari Ubuntu
- cek `AGENT_TOKEN` di `.env`
- samakan dengan `PC_AGENT_TOKEN` di `ubuntu-controller/masterwol.py`

### Explorer tidak bisa buka folder tertentu
- bisa jadi permission Windows menolak akses
- cek folder sensitif / protected directory

### Screenshot/camera gagal
- pastikan desktop session aktif
- webcam tersedia dan tidak dipakai aplikasi lain

### Agent tidak aktif setelah restart
- pastikan EXE pernah dijalankan sekali
- pastikan login ke user Windows yang sama
- cek registry Run user
