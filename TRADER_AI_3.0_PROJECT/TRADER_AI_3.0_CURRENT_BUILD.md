# TRADER AI 3.0 — Current build update

This project reuses the existing analysis/risk/backend foundation while updating the Android app toward the new TRADER AI 3.0 build.

## Current Android UI changes
- Midnight Aurora purple/blue theme remains on the main app screens.
- Live Chart has a distinctly golden chart surface, golden grid and dark/high-contrast price labels/candles.
- Chart timeframe selector is limited to the currently supported feed intervals: 5m, 15m, 1H, 4H.
- Home, AI, Trade Centre, and Settings remain separate screens.

## Important status
- The Android app still calls a local Flask backend at `http://127.0.0.1:5000`.
- A Twelve Data key must be configured privately in the backend environment; do not paste it into chat or hardcode it in the APK.
- HFM/MT5 live order execution is NOT implemented or enabled. The current app is not ready for live-money trading.
- Python tests: 76 passed (5 subtests passed) when run from the project root with `PYTHONPATH=.`.
- This is an updated source project, not a compiled APK. APK compilation still requires Android Gradle build infrastructure.
