-- Run once during the OpenRouter free-provider rollout.
-- No table or enum changes: users who previously allowed recorded-spending
-- context must review the new third-party provider disclosure in the new APK.
-- Deliberately preserve denied and withdrawn decisions.
update public.profiles
set spending_records_consent = 'unset'
where spending_records_consent = 'granted';
