# ChainPulse — Multi-Chain Portfolio & Wallet Security

[![Version](https://img.shields.io/badge/version-8.0.0-blue)](https://github.com/chainpulse-labs/chainpulse-api)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Render](https://img.shields.io/badge/deploy-Render-46e3b7)](https://render.com)

Real-time multi-chain portfolio tracker with built-in wallet security auditing.

## Features

- **7 EVM chains** — Ethereum, BSC, Polygon, Arbitrum, Optimism, Base, Avalanche
- **Bitcoin, Solana, TRON** — native balance scanning
- **Wallet hygiene score** — 0–100 based on approvals, dust, activity
- **HTML export** — professional security reports
- **Dark UI** — Tkinter desktop app

## Quick Start

```bash
npx wallet-health-check
```

Or clone:

```bash
git clone https://github.com/chainpulse-labs/chainpulse-app.git
cd chainpulse-app
pip install -r requirements.txt
python main.py
```

## API (Telemetry)

The app sends anonymous usage telemetry to help improve the product.
No wallet data is ever transmitted. See [PRIVACY.md](PRIVACY.md).

## Build from source

```bash
python builder/generate.py --target linux --exe --name ChainPulse
```

## Disclaimer

This tool is for educational and authorized security auditing only.
Always obtain permission before scanning wallets you do not own.
