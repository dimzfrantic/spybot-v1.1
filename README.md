# spybot-v1.1

Platform kendali jarak jauh berbasis Telegram dengan arsitektur controller-agent: server Ubuntu sebagai pusat kontrol dan Windows agent sebagai eksekutor, mendukung status perangkat, Wake-on-LAN, restart/shutdown, screenshot, camera, explorer, dan transfer file.

## Struktur repo

- `ubuntu-controller/` — bot Telegram pusat (dimzbot) yang berjalan di server Ubuntu
- `windows-agent/` — agent HTTP untuk PC utama Windows (spybot-agent)

## Fitur utama

- Menu Telegram terpusat dari server Ubuntu
- Wake-on-LAN untuk menyalakan PC utama
- Status server Ubuntu dan status PC utama Windows
- Restart/shutdown PC utama dengan konfirmasi
- Restart server Ubuntu dengan konfirmasi
- Screenshot dan camera dari PC utama
- Explorer file dan download file dari PC utama
- Auto-start Windows agent setelah login Windows
- Notifikasi saat Windows agent online

## Arsitektur singkat

1. Telegram hanya dipolling oleh `ubuntu-controller/masterwol.py`
2. PC utama Windows tidak melakukan polling Telegram
3. PC utama menjalankan `windows-agent/app.py` atau `spybot-agent.exe`
4. Server Ubuntu memanggil endpoint HTTP agent Windows untuk aksi operasional

## Keamanan

Sebelum digunakan, ganti seluruh placeholder sensitif berikut:

- token bot Telegram
- group ID Telegram
- token agent HTTP
- IP target dan MAC target

Jangan pernah commit kredensial riil ke repo publik.

## Instalasi lengkap

- Panduan server Ubuntu: lihat `ubuntu-controller/README.md`
- Panduan PC utama Windows: lihat `windows-agent/README.md`
