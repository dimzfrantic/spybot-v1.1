@echo off
setlocal

if not exist venv (
  python -m venv venv
)

call venv\Scripts\activate
python -m ensurepip --upgrade
python -m pip install -r requirements.txt
python -m pip install pyinstaller

pyinstaller --noconsole --onefile --name "spybot-agent" app.py

if not exist dist\logs mkdir dist\logs
if exist .env copy /Y .env dist\.env >nul

echo Build selesai. File ada di folder dist\
pause
