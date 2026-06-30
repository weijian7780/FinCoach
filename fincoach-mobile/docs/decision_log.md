# FinCoach — Decision Log

A running record of notable technical decisions, why they were made, and what
alternatives were considered. Most recent decisions at the top.

_Last updated: 2026-06-20_

---

## 13. Edit Profile redesign + Module 1 "fully functional" (proper ERD tables)
**Decision:** Replaced the wizard-as-editor with a dedicated **Edit Profile**
screen ([src/app/profile/edit.tsx](../src/app/profile/edit.tsx)) styled on the
reference mockup: indigo banner, editable avatar, then form sections. Made the
Categories / Budget / Savings sections **persist for real**, backed by **proper
normalized ERD tables** rather than denormalized columns on `profiles`:
- `categories` — shared lookup (ERD CATEGORY, no `USR_ID`), seeded with 6 standard
  categories; read-only to users.
- `user_categories` — M:N junction recording which categories each user tracks.
- `budgets` — ERD BUDGET, **per category, per month** (`unique(user_id, category_id, month)`).
- `savings_goals` — ERD SAVINGS_GOAL, **many per user** (full add/edit/delete list).
- `avatars` Storage bucket — public read, owner-only write (`<user_id>/avatar.<ext>`).

**Why:** User chose ERD-consistency over speed. Categories as a shared menu +
picks (Option A) keeps "Food" stored once and matches the ERD; per-category
budgets (Option B) are what later power budget alerts ("over on Food"). Both were
confirmed by the user via visual explainers before building.

**Avatar:** `expo-image-picker` (native) → base64 → `base64-arraybuffer` decode →
`supabase.storage.upload`. The My Profile card now renders the photo when present.

**Consequences / notes:**
- This effectively builds the **data layer for Modules 2–4** (Categories, Budget,
  Savings) inside Module 1 — note this when documenting module boundaries.
- **Requires a rebuild** (`expo-image-picker` is a native module + new `app.json`
  plugin) and **running the updated `schema.sql`** on Supabase (new tables +
  bucket + RLS).
- The first-run setup wizard's category/budget/savings steps are still the old
  placeholders that don't persist — only Edit Profile does. Pending: make the
  wizard persist too, or strip its dead steps.

---

## 12. Optimize onboarding swipe performance with UI-thread scroll tracking
**Decision:** Track the onboarding carousel's scroll offset with Reanimated's
`useScrollViewOffset` on an `Animated.ScrollView`, instead of a JS-thread
`onScroll` handler writing a shared value each frame.

**Why:** The JS `onScroll` updated `scrollX.value` ~60×/sec, hopping JS→UI thread
every frame to drive the parallax fade and pager dots — the classic Reanimated
scroll-jank pattern. `useScrollViewOffset` keeps it entirely on the UI thread.

**Note:** The dev build is inherently laggier (unminified JS + Reanimated debug
checks). Final smoothness should be judged on a `preview`/`production` build.

**Follow-up (optional):** Floating category tiles on slide 2 loop continuously
even when off-screen; could be gated to the active slide.

---

## 11. Coach card (onboarding slide 3) redesign + entrance animation
**Decision:** Replaced the flat bar + floating dot with a weekly chart that has a
dashed **budget line**, a **coral over-budget bar** crossing it, a "+15%" value
tag, day labels, a "FinCoach AI" header, and a filled "Set a limit" button. Bars
grow up (staggered) and the tag pops in when the slide becomes active.

**Why:** The original "told" the over-budget story in text but didn't *show* it.
The redesign makes it visual and uses semantic color (coral = alert) instead of
the muddy brown/tertiary.

---

## 10. Brand logo + app launcher icon
**Decision:** Replaced the wallet icon with `assets/images/fincoach-logo.png` on
login, forgot-password, and the onboarding intro; pointed `app.json` `icon` and
Android `adaptiveIcon.foregroundImage` at the same file.

**Notes:** Logo is currently white-background (no alpha) — handled via a white
card (login/forgot) and circle-clipping (onboarding). A transparent, padded PNG
under the same filename would look crisper. **Launcher icon requires an EAS
rebuild;** in-app logo is hot-reload.

---

## 9. Bundle Hanken Grotesk + lock font scaling (auth/onboarding)
**Decision:** Loaded Hanken Grotesk via `@expo-google-fonts/hanken-grotesk`
(`useFonts` gating render in `_layout`); `authType` tokens reference per-weight
families. Locked text size against the device font-scale setting with `AppText`/
`AppTextInput` wrappers.

**Why:** Devices (e.g. the test Honor 200) override the system font + size,
which clipped long labels ("Get Started" → "Get"). Wrappers were required
because RN 0.85 / React 19 **no longer honors `Text.defaultProps`** (verified in
RN source), so the common global hack is a no-op.

**Scope:** Applied to the redesigned indigo screens. Green screens get the same
treatment when re-themed.

---

## 8. Onboarding: full swipe + animation
**Decision:** Rebuilt onboarding as a paging `Animated.ScrollView` (swipe + button),
with scroll-driven entrance fade/slide, animated pager dots, and looping floating
category tiles — all Reanimated (already installed, no rebuild).

**Earlier sub-decision:** Replaced the original `ScrollView` layout (which forced
vertical scrolling on some phones) with a flex-distributed full-screen layout so
content fits any height.

---

## 7. Removed the PIN feature entirely
**Decision:** Deleted the PIN setup + unlock screens, `lib/pin.ts`, `PinDots`,
`markPinEnabled`, and the `pin_enabled` profile field/routing.

**Why:** User request — no PIN gate. There was no unlock screen in the Stitch
design anyway. New flow: onboarding → sign-up → profile setup → app.

**Consequence:** Supabase `profiles.pin_enabled` column is now unused (harmless;
can be dropped later).

---

## 6. UI redesign to the Stitch indigo design system
**Decision:** Rebuilt the auth + onboarding screens to faithfully match the Stitch
mockups: Material-3 **indigo** palette (`primary #4648d4`, `surface #fcf8ff`),
pill inputs, exact copy. Tokens live in `src/constants/auth-theme.ts`, scoped to
these screens; the rest of the app still uses the green `src/constants/design.ts`.

**Why:** The implemented UI used a green theme and different layout/copy that did
not match the approved design.

**Alternatives:** Re-theme only (keep structure) — rejected in favor of a full
faithful match. Migrating the global theme now — deferred to keep changes
scoped; green screens pending.

---

## 5. Email confirmation via deep link (not disabled)
**Decision:** Keep email confirmation ON and route the confirmation link back into
the app via the `fincoach://` deep link (Supabase Site URL + redirect URLs +
`auth/callback`).

**Why:** Production-appropriate; the default `localhost` Site URL caused the
"localhost" error on phones. Disabling confirmation was the simpler alternative
but less suitable for a real release.

**Constraint:** PKCE stores a verifier on-device, so the email must be opened on
the same phone that signed up.

---

## 4. Native Google Sign-In (not browser redirect)
**Decision:** Use `@react-native-google-signin/google-signin` with
`supabase.auth.signInWithIdToken` for a native account-picker popup.

**Why:** Smoother native UX; matches the OAuth clients created (Android client by
package + SHA-1, Web client as the token audience).

**Key facts:** The **Web client ID** is what the code (`webClientId`) and Supabase
("Authorized Client IDs") use; the Android client just establishes trust. Package
name set to `com.fincoach.app`. Native sign-in needs a **dev build** (not Expo Go).
On Google Play, the **Play App Signing SHA-1** must be added as a new Android
client or sign-in breaks in the store build.

---

## 3. Build with EAS development build (not Expo Go)
**Decision:** Use EAS Build (`development` profile, APK) installed on device/
emulator; develop against the Metro dev server.

**Why:** The project is on Expo SDK 56 (newer than the installed Expo Go), and
native modules (Google Sign-In) can't run in Expo Go regardless. Added
`eas.json` (development/preview/production, APK output) and `babel.config.js`
(`babel-preset-expo`, which bundles the Reanimated worklets plugin).

**Rebuild needed only for native changes** (native deps, `app.json` native
config, config plugins, SDK upgrades). JS/asset changes, `@expo/vector-icons`,
fonts via `useFonts`, and env vars are hot-reload / Metro-restart only.

---

## 2. Local Android emulator config
**Decision:** Use a Play Store (Google APIs) system image at a **stable, non-16 KB
API level (36.0)** for AVDs.

**Why:** Play Store image is required for Google Sign-In (has Play Services);
"16 KB page size" images can break native libraries not compiled for them; API 37
is preview-level and needs a large download.

---

## 1. Move the project off Google Drive to local disk
**Decision:** Relocated `fincoach-mobile` from `G:\My Drive\...` to
`C:\Users\User\Desktop\School\UMS SEM 6\FYP Develop\fincoach-mobile`. Use Git/
GitHub for backup instead of Drive sync.

**Why:** Google Drive's virtual filesystem can't sync `node_modules`' tens of
thousands of files — it caused a corrupt half-deleted folder
(`_node_modules_partial_delete_me`), slow installs, and file-lock errors. After
moving, `npm install` ran cleanly in ~23s.
