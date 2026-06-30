# FinCoach - Agent Notes

These notes apply only to this `fincoach-mobile` project.

## Expo HAS CHANGED
Read the exact versioned docs at https://docs.expo.dev/versions/v56.0.0/ before writing any code.

## Architecture / stack
- **Mobile app:** React Native + Expo (SDK 56), expo-router. This repo.
- **Backend: FastAPI (Python) — NOT Node.js.** This is the custom backend, used for the
  AI coaching / RAG. Never propose, scaffold, or assume a Node.js/Express server.
- **Data/auth backend:** Supabase (PostgreSQL + Auth + Storage), called directly from the
  app for normal CRUD. FastAPI is added only for AI coaching (holds LLM keys, runs RAG).
- **Vector store:** Supabase `pgvector`.
- **RAG:** LangChain (Python). More RAG frameworks/tools may be added later.

> Note: `node_modules` / Node.js in this repo are **build tooling only** (npm, Metro,
> Expo CLI) — they are **not** a backend. The server side is FastAPI + Supabase, never Node.

## Target devices
- **Physical phone:** Honor 200 (arm64-v8a), the primary test device. Connects to
  Metro over WiFi by default; needs USB + USB debugging for local installs.
- **Emulator:** Pixel 8 (`emulator-5554`, x86_64).
- Test on both Honor 200 and Pixel 8 emulator when device-specific behavior is relevant.
- A local `gradlew assembleDebug` defaults to whatever arch is passed; build for
  **all archs (or arm64-v8a)** when targeting the Honor 200, **x86_64** for the emulator.

## UI must fit ALL Android phones (hard rule)
Development targets **every Android phone** — varied heights, aspect ratios, notches /
punch-holes / Dynamic-Island-style cutouts, and gesture vs button navigation. Every
screen must be responsive and must **never clip or hide content** on any device:
- Use `useSafeAreaInsets()` for top/bottom padding (`SafeAreaProvider` is in the root
  layout). Never hardcode status-bar / notch / gesture-bar offsets.
- Keep scrollable/form screens inside a `ScrollView` so shorter devices scroll
  gracefully instead of clipping; tune spacing so typical phones fit **without** scrolling.
- Avoid fixed pixel heights for full-screen layouts; prefer flex distribution and the
  `md`-scale spacing tokens over large hardcoded gaps.
- Always render text via `AppText` / `AppTextInput` (font scaling is locked) so a user's
  system font size can't overflow the layout.
- Before calling a screen done, sanity-check it on a **small** screen and on the Honor 200.

## Workflow
- **Now:** developing with Expo development builds. Metro hot-reload covers JS changes.
- **Native changes:** rebuild/reinstall the development build when native modules or native
  config change.
- **Deploy:** ship an **APK** installed on the phone, using EAS or a local release build.

## Build environment (Android)
- Android builds require **JDK 17**, pinned via `org.gradle.java.home` in
  `android/gradle.properties` (machine default is JDK 25, which is unsupported).
  Re-add that line if `expo prebuild --clean` regenerates the file.

## Deployment (APK)
- Distribute a standalone APK with the **preview** EAS profile (already set to
  `buildType: apk`, `distribution: internal`):
  `eas build --profile preview --platform android` → share the download link/QR.
- It's a release build (no Metro/dev-client). EAS builds from **git**, so commit first;
  `EXPO_PUBLIC_*` env vars are baked in via `eas.json`.
- `production` profile outputs an **AAB** for the Play Store; `development` is the dev-client APK.

## Google Sign-In SHA-1 (per signing key, NOT per device)
Native Google Sign-In needs an **Android OAuth client** in Google Cloud (package
`com.fincoach.app` + the build's SHA-1) in the **same project** as the Web Client ID.
A given `package + SHA-1` is globally unique to one OAuth client. SHA-1 follows the
**signing keystore**, so any device running the same signed APK works — it's never per-device.
- **debug keystore** (`android/app/debug.keystore`) → emulator / local builds.
  SHA-1: `5E:8F:16:06:2E:A3:CD:2C:4A:0D:54:78:76:BA:A6:F3:8C:AB:F6:25`
- **EAS keystore** → `preview`/`development` builds (the Honor 200). SHA-1 via `eas credentials`.
  Already registered → Google login works on every device that installs the EAS APK.
- **Play App Signing key** → ONLY if publishing to the Play Store, which **re-signs** the
  app with a new key. Get that SHA-1 from Play Console → Setup → App signing and register it,
  or Google login breaks for all Store installs. (Not needed for plain APK distribution.)
