# FinCoach Android DNS Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make FinCoach recover from failed carrier DNS resolution of its API while users keep Automatic DNS enabled.

**Architecture:** Install a hostname-scoped `okhttp3.Dns` implementation through React Native's `OkHttpClientProvider` before React Native starts. Use system DNS first and Google DNS-over-HTTPS only on lookup failure. An Expo config plugin generates the native resolver, startup registration, and Gradle dependency so EAS and repeated prebuild preserve the feature.

**Tech Stack:** Expo SDK 56, React Native 0.85.3, Kotlin, OkHttp/okhttp-dnsoverhttps aligned to the resolved app dependency, Expo config plugins, Node test runner, JUnit, MockWebServer, Vitest.

**Spec:** [2026-10-02-fincoach-dns-fallback-spec.md](2026-10-02-fincoach-dns-fallback-spec.md). Read it before executing this plan.

## Global Constraints

- Canonical edits belong in `fincoach-mobile`; reconcile any existing short-path build-copy changes before syncing.
- Exact fallback hostname comes from `EXPO_PUBLIC_FINCOACH_API_URL`, currently `https://api.chisquaredv10.dpdns.org`.
- Scope recovery to that hostname and `UnknownHostException`; preserve normal DNS for all other hosts.
- DoH endpoint: `https://dns.google/dns-query`. Bootstrap with Google's documented resolver addresses: `8.8.8.8`, `8.8.4.4`, `2001:4860:4860::8888`, and `2001:4860:4860::8844`.
- DoH call/connect/read timeouts: 4/2/3 seconds. Dedicated cache size: 512 KiB. Preserve the coach's existing 90-second timeout.
- Keep original HTTPS hostname, TLS validation, React Native cookies, interceptors, and authentication behavior.
- No new automatic replay of financial writes or coach-message requests.
- No phone DNS-setting change; no backend/database/tunnel change.
- Native folders are generated and ignored by Git and EAS. Tracked templates and a config plugin are the source of truth.
- Preserve installed signing identity, data, and login. Recheck installed versionCode; the new APK must be greater.
- No implementation, build, installation, staging, or commit is authorized by the plan-only request. Implementation begins only after the user approves it.

## Review Focus

1. EAS regenerates Android: startup registration, dependency, and resolver must survive and must not duplicate on a second prebuild. Covered in Task 1.
2. Changing the build's API URL must change the allowlist; local development hosts must not be sent to public DoH. Covered in Task 1.
3. Carrier DNS and DoH can both fail: recovery must be bounded and preserve truthful error behavior. Covered in Tasks 2 and 3.
4. Replacing React Native's client can break cookies/auth or broaden DNS routing: preserve its builder and exact hostname scope. Covered in Task 2 and device checks in Task 4.
5. A new APK may use a different certificate or lower versionCode: inspect before attempting an in-place update; do not uninstall to bypass the problem. Covered in Task 4.

---

### Task 1: Persistent native configuration and build contract

**Files:**
- Create: `fincoach-mobile/plugins/with-fincoach-dns-fallback.js`
- Create: `fincoach-mobile/plugins/with-fincoach-dns-fallback.test.cjs`
- Create: `fincoach-mobile/plugins/android/FinCoachDnsFallback.kt`
- Modify: `fincoach-mobile/app.json` — register the plugin with `{ "enabled": true }`.
- Generated outputs: `android/app/src/main/java/com/fincoach/app/FinCoachDnsFallback.kt`, `MainApplication.kt`, and `android/app/build.gradle`.

**Interfaces:**
- Consumes: Expo Android package, `EXPO_PUBLIC_FINCOACH_API_URL`, and plugin option `{ enabled?: boolean }`, defaulting to true.
- Produces: generated `FinCoachNetwork.install(context: Context)`, configured API hostname, and enabled constant. Task 2 fills in the resolver implementation.

- [ ] Write Node tests for the plugin's pure config/transform helpers: parsed API hostname; alternate HTTPS hostname; disabled option; malformed/missing API URL when enabled; local/IP/http development URL; Kotlin package rendering; insertion before `loadReactNative(this)`; applying the transform twice creates exactly one registration and one dependency.
- [ ] Run `node --test plugins/with-fincoach-dns-fallback.test.cjs` from `fincoach-mobile`; confirm the assertions fail before implementation.
- [ ] Implement the config plugin using Expo's MainApplication, app Gradle, and Android file-generation mods. Read the API URL from the build environment, normalize the hostname, and generate Kotlin constants rather than duplicating the API hostname in app.json.
- [ ] When enabled and the API URL is malformed or missing, fail generation with a specific build error. For a valid local/IP/http development URL, retain system DNS and report that recovery is inactive for that build. When disabled, generate an inactive implementation so repeated prebuild removes any active behavior.
- [ ] Generate a namespaced `FinCoachNetwork.install(this)` startup call immediately after `super.onCreate()`, before `loadReactNative(this)`. Fail clearly if the startup anchor cannot be identified instead of silently shipping an unregistered resolver.
- [ ] Resolve the existing app's OkHttp version with `gradlew.bat :app:dependencyInsight --dependency okhttp --configuration releaseRuntimeClasspath`. The catalog baseline is 4.9.2; select matching DoH and native test artifacts for the resolved version and record the result. Do not introduce a speculative major/version upgrade.
- [ ] Register the plugin in app.json and rerun its Node tests. In an isolated prebuild-check copy, run `npx expo prebuild --platform android --no-install` twice and verify the generated resolver/dependency/startup call each occur once. Do not run `--clean` against the user's active native build directory.

**Deliverable:** Repeatable generation of an inactive, compiling native scaffold and its build configuration. No runtime recovery is claimed yet.

### Task 2: Hostname-scoped native resolver and HTTP-client integration

**Files:**
- Modify: `fincoach-mobile/plugins/android/FinCoachDnsFallback.kt`
- Create: `fincoach-mobile/plugins/android/FinCoachDnsFallbackTest.kt`
- Modify: `fincoach-mobile/plugins/with-fincoach-dns-fallback.js` — generate native test source and matching test-only dependencies.
- Generated test output: `android/app/src/test/java/com/fincoach/app/FinCoachDnsFallbackTest.kt`.

**Interfaces:**
- `FinCoachDnsFallback(apiHost: String, systemDns: Dns, fallbackDns: Dns) : Dns`
- `override fun lookup(hostname: String): List<InetAddress>`
- `FinCoachNetwork.install(context: Context): Unit`
- Consumes: Task 1's hostname, enabled flag, and dependency version.
- Produces: React Native's network client with API-only DNS recovery. No JS bridge or request-body change is required.

- [ ] Write failing JUnit tests with injected fake DNS implementations: system success returns unchanged results without consulting DoH; API lookup failure uses DoH; non-API lookup failure propagates without consulting DoH; both resolvers failing propagate a resolution failure; empty/unusable fallback answers fail; A/AAAA answers remain supported.
- [ ] Add native integration assertions with MockWebServer: a forced system lookup failure still delivers one original HTTP request through the resolver; hostname/certificate mismatch remains rejected; DoH HTTP failure and a delayed DoH server are bounded; the DoH client has no app authorization or cookies; native client creation preserves React Native's cookie container and default request timeout settings.
- [ ] Run `gradlew.bat :app:testDebugUnitTest --tests com.fincoach.app.FinCoachDnsFallbackTest` in the verified native build copy and confirm tests fail before implementing recovery.
- [ ] Implement system-first lookup, with fallback only for an exact case-normalized API-host match after `UnknownHostException`. Propagate failures for all other hosts and do not trigger recovery from HTTP/TLS errors.
- [ ] Build a dedicated Google DoH client with bootstrap addresses, 4/2/3-second timeouts, A/AAAA support, a dedicated 512 KiB cache, and no inherited auth headers, cookies, or application interceptors. Guard failures and close resources using the selected library's supported APIs.
- [ ] Register `OkHttpClientProvider.setOkHttpClientFactory(...)` using `OkHttpClientProvider.createClientBuilder(context).dns(scopedResolver).build()`. Do not create a generic replacement client that drops React Native defaults, and do not call `getOkHttpClient()` while constructing its factory.
- [ ] Add debug-build-only log events for `system_success`, `fallback_started`, `fallback_success`, and `fallback_failed`. Record only the public API hostname and event; never tokens, bodies, message content, or financial records. Keep log calls off the user-facing UI.
- [ ] Rerun native tests and plugin tests. Inspect `releaseRuntimeClasspath` to verify a consistent OkHttp/DoH version and compile the release variant.

**Deliverable:** Deterministic proof that native DNS recovery works while HTTP semantics, TLS, and unrelated DNS traffic remain intact.

### Task 3: Honest user-facing failure message

**Files:**
- Modify: `fincoach-mobile/src/lib/coach-domain.ts`
- Modify: `fincoach-mobile/src/lib/coach-domain.test.ts`
- Existing regression suite: `fincoach-mobile/src/lib/coach-api.test.ts`.

**Interfaces:**
- Existing `coachErrorMessage(error: unknown): string`; existing `CoachApiError.code` remains the contract.

- [ ] Add a failing assertion that `{ status: 0, code: 'network' }` displays `FinCoach could not reach its server. Try again shortly or switch networks.`
- [ ] Preserve the existing offline, timeout, consent, expired-session, and HTTP-status messages. A generic React Native fetch error must not be called a proven DNS failure.
- [ ] Implement only the new `network` message branch; do not add connectivity preflight requests, HTTP retries, or extra request replay in `coach-api.ts`.
- [ ] Run `npm test -- src/lib/coach-domain.test.ts src/lib/coach-api.test.ts`, then `npm run typecheck`.

**Deliverable:** An online user's remaining server-connectivity failure no longer implies they necessarily have no internet connection.

### Task 4: Signed APK and real-device validation

**Files:**
- Modify: `fincoach-mobile/docs/device-demo-evidence.md` — append observed evidence only.
- Review only unless needed: `fincoach-mobile/eas.json` — existing preview APK profile, API URL, and automatic version increment.

**Interfaces:**
- Consumes: Tasks 1–3 and the existing preview build/signing configuration.
- Produces: compatible APK plus separately labeled local-test, installed-device, and backend-request evidence.

- [ ] Reinspect the dirty canonical workspace and any `C:\fcb` copy. Reconcile copy-only source edits before syncing. Verify absolute targets before any file move/delete; do not blindly invoke a mirror/delete command over the build copy.
- [ ] Prefer the existing EAS preview signing identity for the release APK: `npx eas-cli build --platform android --profile preview`. Verify that the uploaded source includes the plugin/templates while generated Android stays excluded. A compatible local release build is an alternative only after verifying its actual signing identity.
- [ ] Recheck `adb -s AJ4UVB5217000493 shell dumpsys package com.fincoach.app`. Compare APK signing certificates with `apksigner verify --print-certs` and check package/version with the installed Android SDK tooling. Use a versionCode greater than the current installed value (31 during diagnosis). Do not uninstall or bypass certificate/version checks.
- [ ] Install the compatible APK using `adb -s AJ4UVB5217000493 install -r <verified-apk-path>` and confirm existing login/data remain present.
- [ ] On Honor, keep mobile data and Automatic Private DNS. Test cold app startup, conversation loading, and one harmless coaching message such as `Explain what an emergency fund is.` Correlate the request and response with Docker logs; verify exactly one submitted message and a completed answer.
- [ ] Check whether device debug events prove fallback was used. If carrier DNS has recovered naturally, label the Honor result as system-DNS success and separately run deterministic native integration tests with a failing injected resolver. Do not claim live fallback proof from HTTP 200 alone.
- [ ] On the Pixel 8 emulator, test normal DNS, forced lookup failure in the test harness, offline mode, and unavailable DoH. Confirm bounded failures and clear UI messages.
- [ ] Smoke-test login/session persistence, one receipt-screen load, and normal Supabase reads. Verify no phone network settings changed during the feature test.
- [ ] Record APK version/hash, tested device/network, actual resolver path observed, relevant successful request statuses, and untested conditions. Remove temporary testing instrumentation; keep only the specified debug-build resolver events.

**Deliverable:** Verified APK and real-device evidence. A passing health endpoint alone is insufficient to mark AI coaching verified.

## Rollback and practical limits

- Set the plugin's `enabled` option to false and rebuild/install a compatible, higher-version APK to restore system-only DNS. The domain and backend stay the same.
- Recovery adds a Google DoH dependency when default API resolution fails; it is not a guarantee of connectivity on every network.
- Maintain correct public DNS delegation independently. This feature does not repair expired registration, missing records, stopped tunnels, or an offline Docker host.
- No new paid hosting service or domain is required by this plan. Native rebuilding is required; EAS build availability/charges depend on the user's account, so do not promise a free cloud build.
- Proposed execution method after approval: implement sequentially in this chat. Preserve unrelated work and review only the feature's intended diffs. Do not auto-commit.
