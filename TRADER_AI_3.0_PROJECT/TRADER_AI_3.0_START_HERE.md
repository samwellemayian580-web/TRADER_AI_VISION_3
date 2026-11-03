# TRADER AI 3.0 — Project handoff

## What was done in this first pass
- Started from the uploaded TRADER_AI_2.0_COMPLETE source archive.
- Preserved the existing analysis, risk, backtesting, test, and Android source folders.
- Changed the active Android app branding/version to TRADER AI 3.0.
- Added a GitHub Actions workflow to build a debug APK from the Android project.
- Preserved the golden/yellow chart theme in the Live Chart page; other screens keep the existing dark purple/aurora theme.

## Current state — important honesty
This is a **project upgrade baseline**, not a finished production trading app.
The existing app is signal-oriented. The backend is expected at `127.0.0.1:5000`, so it is not a verified HFM/MT5 live connection. No live order execution is enabled. Do not use it to trade real money.

## Build APK with GitHub Actions
1. Upload the contents of this project to your GitHub repository (keep the `.github/workflows/build-android-apk.yml` file).
2. In GitHub, open **Actions**.
3. Select **Build TRADER AI 3.0 Android APK**.
4. Tap **Run workflow** (or push to `main`).
5. When the run succeeds, open the run and download the artifact named `TRADER-AI-3.0-debug-apk`.

## Android build details
- Android application ID: `com.traderai.app`
- Version name: `3.0`
- Minimum Android version: Android 6.0 (API 23)
- The project uses Kotlin and Android Gradle Plugin.
- If GitHub reports that Gradle wrapper files are missing, the workflow falls back to the hosted Gradle command. A wrapper is recommended for a reproducible build.

## Next development milestones
1. Separate Home, Markets/Live Chart, AI Chat, Analysis Centre, Trade Centre, and Settings/Risk Management into fully functional screens.
2. Replace localhost-only data access with a secure authenticated backend/MT5 bridge (likely Windows PC/VPS running MT5; never embed broker credentials in APK).
3. Validate actual broker quotes/account state before displaying anything as live.
4. Add demo-only execution and test safeguards before considering real execution.
5. Verify broker symbol specifications and account-currency/tick-value sizing before enabling order placement.
