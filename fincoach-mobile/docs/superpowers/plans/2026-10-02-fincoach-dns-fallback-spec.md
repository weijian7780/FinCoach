# FinCoach Android DNS Fallback Specification

## Goal

Let the FinCoach Android app reach its existing HTTPS API when a phone's default resolver cannot resolve that hostname, while the phone remains on Automatic Private DNS.

## Observed failure, 2 October 2026

- The ADB-connected Honor 200 was using mobile data and Automatic Private DNS (`opportunistic`, with no provider hostname).
- The installed APK, versionCode 31, contained `https://api.chisquaredv10.dpdns.org`.
- Android's system lookup returned `unknown host` for that API, but resolved `dns.google`.
- Temporarily selecting Google Private DNS made the API resolve and Coach load. Docker logged successful conversation and message-history GET requests.
- Restoring Automatic Private DNS made the API lookup fail again.
- No new AI message was sent during diagnosis. The carrier's internal reason for the DNS failure was not established.

## Required behavior

1. Try Android system DNS first.
2. On `UnknownHostException`, use Google DNS-over-HTTPS (DoH) only for the exact API hostname derived from the build's `EXPO_PUBLIC_FINCOACH_API_URL`.
3. Preserve the original HTTPS URL, Host header, TLS server name, certificate validation, authentication, and React Native networking defaults.
4. Perform fallback during DNS resolution before the original request is sent. Add no new automatic HTTP replay, especially for POST/PATCH/DELETE.
5. Keep the phone's DNS settings unchanged.
6. Register the native client before React Native networking initializes.
7. Preserve the customization through Expo prebuild and EAS builds using a tracked config plugin and tracked Kotlin templates.
8. Bound each DoH call to 4 seconds, with a 2-second connection timeout and a 3-second read timeout. Leave the existing coach request timeout unchanged.
9. Retain A and AAAA resolution. Do not disable IPv6 to mask this failure.
10. Use a separate credential-free DoH client, with Google resolver bootstrap addresses so it can start even if system resolution of `dns.google` fails.
11. Use the resolver's standard HTTP caching with a dedicated 512 KiB cache. Respect response cache headers; introduce no permanent API-IP cache.
12. Support a build-time `enabled: false` plugin option for rollback.

## Boundaries

- Android only for this change. Other platforms continue using their existing network clients.
- Scope the fallback to the configured API hostname; Supabase, Google sign-in, and unrelated destinations continue using their existing resolution behavior.
- The DoH provider receives the public DNS hostname and connection metadata, not coach messages, tokens, financial records, or request bodies.
- No backend, Docker, tunnel-route, database, or domain change is required by this feature.
- DoH is recovery from a resolver failure. It cannot recover a stopped backend, an offline phone, invalid public DNS, a TLS failure, or a blocked DoH service.
- A successful but incorrect DNS answer is outside this first implementation; fallback is triggered by lookup failure, not by arbitrary HTTP or TLS failures.
- Do not replace HTTPS URLs with Cloudflare IP addresses or relax TLS verification.
- Show a neutral server-connectivity error when an online device still cannot connect; do not assert that every network failure is DNS-related.

## Delivery constraints

- Canonical source: `fincoach-mobile` in the FYP workspace. A short-path build copy is secondary and must be reconciled before copying or rebuilding.
- Current repository versions: Expo SDK 56 and React Native 0.85.3. React Native's dependency catalog declares OkHttp 4.9.2; verify the resolved Gradle version and align `okhttp-dnsoverhttps` with it instead of upgrading networking dependencies speculatively.
- Both Git and EAS currently exclude the generated `android/` directory. Edits confined to that directory are insufficient.
- Preserve the installed package, signing identity, app data, and authentication session. The release APK must have a versionCode greater than the currently installed version, rechecked at installation time.
- The workspace already contains unrelated edits. Review diffs and keep this feature's changes scoped; do not auto-commit or stage unrelated changes.

## Acceptance

- Unit/integration tests deterministically force system lookup failure and prove the native resolver recovers through DoH.
- With Automatic DNS and mobile data, the rebuilt Honor app loads Coach and reaches the Docker backend. Send one harmless coaching message and verify one successful user-visible response and one submitted message.
- Confirm whether the live device run actually exercised fallback; a naturally recovered carrier DNS result alone is not fallback proof.
- Working system DNS, offline mode, DoH failure, non-API destinations, TLS validation, existing auth, and repeated prebuild remain correct.
- No app/device network-setting changes are left behind by verification.

## References

- [Expo SDK 56 documentation](https://docs.expo.dev/versions/v56.0.0/)
- [Expo config plugins](https://docs.expo.dev/config-plugins/introduction/)
- [Native changes require rebuilding](https://docs.expo.dev/develop/development-builds/use-development-builds/)
- [Google DNS-over-HTTPS](https://developers.google.com/speed/public-dns/docs/doh)
- [OkHttp DNS-over-HTTPS implementation](https://raw.githubusercontent.com/square/okhttp/parent-4.12.0/okhttp-dnsoverhttps/src/main/kotlin/okhttp3/dnsoverhttps/DnsOverHttps.kt) — API reference; this does not prescribe a dependency upgrade.
