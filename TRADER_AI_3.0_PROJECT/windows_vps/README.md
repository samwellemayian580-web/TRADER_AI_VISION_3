# TRADER AI VISION 3.0 - Windows VPS

## Purpose

This Windows environment runs the MetaTrader 5 terminal and the
read-only TRADER AI bridge for initial HFM demo-account verification.

It does not place, modify, or close trades.

## Requirements

- Windows 10/11 or Windows Server, 64-bit
- Python 3.12, 64-bit
- MetaTrader 5 desktop terminal
- HFM demo account
- Tailscale installed on both the VPS and the Android phone

## Initial setup

1. Install Python 3.12 (64-bit).
2. Install the MetaTrader 5 desktop terminal.
3. Log in to the HFM DEMO account in MT5.
4. Keep the terminal open.
5. Open PowerShell in this project folder.
6. Run:

   powershell -ExecutionPolicy Bypass -File .\windows_vps\setup.ps1

## Start the read-only bridge

Generate a strong token:

   python -c "import secrets; print(secrets.token_urlsafe(48))"

Copy the generated token securely. In the same PowerShell session, set it:

   $env:MT5_BRIDGE_TOKEN = "PASTE_YOUR_TOKEN_HERE"

Then start the bridge:

   powershell -ExecutionPolicy Bypass -File .\windows_vps\start.ps1

The bridge listens on 127.0.0.1:8765.

## Secure phone connectivity

Do not expose port 8765 directly to the public internet.

Use Tailscale on the Windows VPS and Android phone. Configure Tailscale
Serve to provide HTTPS access to the local bridge, restricted to your
private tailnet. Use the HTTPS machine URL supplied by Tailscale as
MT5_BRIDGE_URL on the phone-side backend.

Keep the bearer token private. Never put it in the APK, GitHub, screenshots,
or a publicly shared file.

## Verification

The bridge provides read-only endpoints:

- /api/v1/health
- /api/v1/mt5/status
- /api/v1/mt5/account
- /api/v1/mt5/quote/XAUUSD

The bridge rejects other symbols and has no order-placement endpoint.

Verify the HFM demo server, account currency, equity, XAUUSD tick values,
contract size, volume limits, and stop restrictions before using broker
specifications in position sizing.

Live execution is not enabled by this bridge.
