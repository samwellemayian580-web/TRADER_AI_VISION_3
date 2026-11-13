# TRADER AI VISION 3.0 — Windows MT5 VPS Bridge

This service connects TRADER AI VISION 3.0 to HFM MetaTrader 5 running on a Windows VPS.

## Supported HFM profiles

| Mode | Server | Symbol |
|---|---|---|
| DEMO | HFMarketsKE-Demo2 | XAUUSD |
| LIVE | HFMarketsKE-Live2 | XAUUSD |

DEMO is the default profile. LIVE is selectable but must be configured separately.

## 1. Requirements

- Windows VPS
- Python 3.11 (64-bit)
- HFM MetaTrader 5 terminal
- HFM DEMO and/or LIVE account
- Network access to the VPS

## 2. Install dependencies

Open Command Prompt in this folder and run:

    py -3.11 -m venv .venv
    .venv\Scripts\activate
    python -m pip install --upgrade pip
    pip install -r requirements.txt

## 3. Configure private credentials

Configure these Windows environment variables:

    MT5_BRIDGE_TOKEN
    MT5_DEMO_PATH
    MT5_DEMO_LOGIN
    MT5_DEMO_PASSWORD
    MT5_LIVE_PATH
    MT5_LIVE_LOGIN
    MT5_LIVE_PASSWORD

Use the actual terminal executable paths and account details for each profile.

Never put passwords or bridge tokens in GitHub, the Android APK, source files, screenshots, or chat.

Use a long, randomly generated bridge token. Keep it private.

## 4. Start the bridge

With the virtual environment activated, run:

    python bridge_server.py

The initial service listens on:

    http://127.0.0.1:8765

It is bound to localhost only and is not directly accessible from the internet.

## 5. Available API routes

All routes require:

    Authorization: Bearer YOUR_PRIVATE_TOKEN

- GET `/v1/health` — bridge service status
- POST `/v1/account` — read the selected account
- POST `/v1/quote` — read the selected XAUUSD quote
- POST `/v1/orders` — not enabled yet
- PATCH `/v1/orders/<ticket>` — not enabled yet
- POST `/v1/orders/<ticket>/close` — not enabled yet

For account and quote requests, send JSON such as:

    {"mode": "DEMO"}

or:

    {"mode": "LIVE"}

## 6. Safety and current limitations

- Start with the DEMO account.
- The current bridge supports account and quote connectivity only.
- Order placement, modification, and closing are deliberately disabled.
- Do not enable live trading until execution, risk checks, and demo tests have been completed.
- The current bridge switches between account profiles; it does not maintain two simultaneous MT5 connections.
- Do not expose the Flask development server directly to the internet.
- External access must use a properly secured HTTPS deployment with authentication and firewall restrictions.

## 7. Before live trading

The project must validate broker symbol specifications, minimum and maximum volume, volume step, tick value, spread, commission, slippage, margin, and server-side risk limits.

The configured risk limits must remain unchanged unless the user explicitly authorizes a change.
